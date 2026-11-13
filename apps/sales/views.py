import itertools
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.businesses.mixins import BusinessRequiredMixin
from apps.core.constants import PAYMENT_METHOD_CHOICES, PAYMENT_METHOD_FIADO
from apps.customers.services import credit_balances, credit_warning_data, projected_credit
from apps.products.models import Product

from apps.receivables.models import ReceivablePayment

from .forms import ComandaForm, ComandaItemForm, ComandaPaymentForm, SaleForm
from .models import Comanda, ComandaItem, ComandaPayment, Sale, SalePayment
from .services import (
    add_comanda_item,
    cancel_sale,
    create_sale,
    delete_empty_comanda,
    finalize_comanda,
    open_comanda,
    register_comanda_payment,
    remove_comanda_item,
    remove_comanda_payment,
    update_comanda_item,
    update_comanda_payment,
)

def warn_credit_limit(request, business, customer):
    """Avisa após o lançamento sem bloquear a operação."""
    if customer is not None and customer.credit_limit is not None:
        total = projected_credit(customer, credit_balances(business))
        if total > customer.credit_limit:
            messages.warning(
                request,
                f'O limite de fiado de {customer.name} foi ultrapassado. '
                'O lançamento foi registrado normalmente.',
            )


MONTH_NAMES_PT = [
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]


class SaleListView(BusinessRequiredMixin, ListView):
    template_name = 'sales/sale_list.html'
    context_object_name = 'sales'

    def get_month_year(self):
        today = timezone.localdate()
        try:
            year = int(self.request.GET.get('year', today.year))
            month = int(self.request.GET.get('month', today.month))
        except (TypeError, ValueError):
            year, month = today.year, today.month

        # Normaliza meses fora do intervalo 1-12 (navegação para frente/trás).
        month_index = (year * 12 + (month - 1))
        year, month = divmod(month_index, 12)
        month += 1
        return year, month

    def get_queryset(self):
        year, month = self.get_month_year()
        return Sale.objects.filter(
            business=self.business, sold_at__year=year, sold_at__month=month
        ).order_by('-sold_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, month = self.get_month_year()

        month_sales = self.get_queryset().exclude(status=Sale.STATUS_CANCELLED)

        total = month_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

        # Composição das vendas do mês, independentemente da data em que
        # pagamentos de uma comanda finalizada foram recebidos.
        sales_paid_at_sale = SalePayment.objects.filter(sale__in=month_sales).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        # Entradas efetivas do mês, conforme a data do recebimento. Pagamentos
        # de comandas abertas ainda não possuem SalePayment e não entram aqui.
        month_sale_payments = SalePayment.objects.filter(
            sale__business=self.business,
            received_at__year=year,
            received_at__month=month,
        ).exclude(sale__status=Sale.STATUS_CANCELLED)
        totals_by_method = month_sale_payments.values('method').annotate(total=Sum('amount'))
        totals_by_method_map = {row['method']: row['total'] for row in totals_by_method}

        fiado_total = month_sales.filter(receivables__isnull=False).aggregate(
            total=Sum('receivables__original_amount')
        )['total'] or Decimal('0.00')

        payment_method_totals = [
            {'label': label, 'total': totals_by_method_map.get(code, Decimal('0.00'))}
            for code, label in PAYMENT_METHOD_CHOICES
        ]
        received_sales_total = sum((item['total'] for item in payment_method_totals), Decimal('0.00'))

        # Recebido Fiado: pagamentos de dívidas de clientes efetivamente
        # recebidos neste mês (podem ser referentes a vendas fiado de
        # meses anteriores). Isso explica por que o "Recebido" do mês
        # pode incluir valores de fiado pago, sem duplicar a venda de
        # origem nem o indicador de Faturamento do Planejamento.
        month_receivable_payments = ReceivablePayment.objects.filter(
            receivable__business=self.business,
            paid_at__year=year,
            paid_at__month=month,
        ).exclude(status=ReceivablePayment.STATUS_CANCELLED)
        received_fiado_total = month_receivable_payments.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

        total_received = received_sales_total + received_fiado_total

        # Pagamentos de fiado recebidos no mês, agrupados por dia local em
        # que foram recebidos (não pela data da venda de origem), para
        # mostrar "Recebido de fiado" no Resumo diário, incluindo a lista
        # de quem pagou (drill-down).
        received_fiado_by_day = {}
        received_fiado_payments_by_day = {}
        month_fiado_payments = ReceivablePayment.objects.select_related(
            'receivable__customer'
        ).filter(
            receivable__business=self.business,
            paid_at__year=year,
            paid_at__month=month,
        ).exclude(status=ReceivablePayment.STATUS_CANCELLED)
        for payment in month_fiado_payments:
            day = timezone.localtime(payment.paid_at).date()
            received_fiado_by_day[day] = received_fiado_by_day.get(day, Decimal('0.00')) + payment.amount
            received_fiado_payments_by_day.setdefault(day, []).append(payment)

        # Pagamentos diretos de venda recebidos no mês, agrupados pelo dia
        # local do recebimento (não pela data da venda de origem), para
        # compor o mini-resumo "Vendas recebidas" dentro de cada dia do
        # Resumo diário, com a mesma lógica usada no card do topo.
        received_sales_by_day = {}
        for payment in month_sale_payments:
            day = timezone.localtime(payment.received_at).date()
            received_sales_by_day[day] = received_sales_by_day.get(day, Decimal('0.00')) + payment.amount

        # Pago na venda, agrupado pelo dia local da venda de origem (não
        # pela data do recebimento), para compor o mini-resumo "Pago na
        # venda" dentro de cada dia do Resumo diário.
        paid_at_sale_by_day = {}
        for payment in SalePayment.objects.filter(sale__in=month_sales).select_related('sale'):
            day = timezone.localtime(payment.sale.sold_at).date()
            paid_at_sale_by_day[day] = paid_at_sale_by_day.get(day, Decimal('0.00')) + payment.amount

        # Agrupa as vendas (incluindo canceladas) por dia, do mais recente
        # para o mais antigo, com total e quantidade de vendas de cada dia.
        #
        # IMPORTANTE: o campo sold_at é armazenado em UTC (USE_TZ=True).
        # Usar sale.sold_at.date() diretamente agruparia pela data em UTC,
        # fazendo vendas feitas à noite (horário de Brasília) aparecerem no
        # dia seguinte. É obrigatório converter para o horário local antes
        # de extrair a data, para que a contagem bata com o dia real.
        sales_by_day = []
        for day, sales_of_day in itertools.groupby(
            self.get_queryset(),
            key=lambda sale: timezone.localtime(sale.sold_at).date(),
        ):
            sales_of_day = list(sales_of_day)
            day_total = sum(
                (s.total_amount for s in sales_of_day if s.status != Sale.STATUS_CANCELLED),
                Decimal('0.00'),
            )
            # Parte do total do dia que ficou como fiado (venda a prazo),
            # para deixar claro, ao lado do valor total, quanto daquilo
            # ainda não entrou de fato no caixa.
            day_fiado_total = sum(
                (
                    r.original_amount
                    for s in sales_of_day if s.status != Sale.STATUS_CANCELLED
                    for r in s.receivables.all()
                ),
                Decimal('0.00'),
            )
            sales_by_day.append({
                'day': day,
                'sales': sales_of_day,
                'total': day_total,
                'count': len(sales_of_day),
                'fiado_total': day_fiado_total,
                'received_fiado_total': received_fiado_by_day.get(day, Decimal('0.00')),
                'received_fiado_payments': received_fiado_payments_by_day.get(day, []),
                'paid_at_sale_total': paid_at_sale_by_day.get(day, Decimal('0.00')),
                'received_sales_total': received_sales_by_day.get(day, Decimal('0.00')),
            })

        # Dias em que houve recebimento de fiado mas nenhuma venda nova
        # (ex.: cliente pagou uma dívida antiga em um dia sem vendas) não
        # aparecem no loop acima; são adicionados aqui para não "sumir"
        # com esse recebimento do resumo diário.
        days_with_sales = {entry['day'] for entry in sales_by_day}
        for day, amount in received_fiado_by_day.items():
            if day not in days_with_sales:
                sales_by_day.append({
                    'day': day,
                    'sales': [],
                    'total': Decimal('0.00'),
                    'count': 0,
                    'fiado_total': Decimal('0.00'),
                    'received_fiado_total': amount,
                    'received_fiado_payments': received_fiado_payments_by_day.get(day, []),
                    'paid_at_sale_total': paid_at_sale_by_day.get(day, Decimal('0.00')),
                    'received_sales_total': received_sales_by_day.get(day, Decimal('0.00')),
                })
        sales_by_day.sort(key=lambda entry: entry['day'], reverse=True)

        current_month_date = date(year, month, 1)
        previous_index = year * 12 + (month - 1) - 1
        previous_year, previous_month = divmod(previous_index, 12)
        previous_month += 1
        next_index = year * 12 + (month - 1) + 1
        next_year, next_month = divmod(next_index, 12)
        next_month += 1

        context.update({
            'year': year,
            'month': month,
            'month_label': MONTH_NAMES_PT[month],
            'current_month_date': current_month_date,
            'previous_year': previous_year,
            'previous_month': previous_month,
            'next_year': next_year,
            'next_month': next_month,
            'month_total': total,
            'sales_paid_at_sale': sales_paid_at_sale,
            'received_sales_total': received_sales_total,
            'received_fiado_total': received_fiado_total,
            'total_received': total_received,
            'fiado_total': fiado_total,
            'payment_method_totals': payment_method_totals,
            'sales_by_day': sales_by_day,
        })
        return context


class SaleCreateView(BusinessRequiredMixin, FormView):
    template_name = 'sales/sale_form.html'
    form_class = SaleForm
    success_url = reverse_lazy('sales:sale_list')
    operator_allowed = True

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.business
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = Product.objects.filter(
            business=self.business, is_active=True
        ).order_by('name')
        context['products'] = products
        context['products_json'] = [
            {'id': p.pk, 'name': p.name, 'price': str(p.price)} for p in products
        ]
        context['credit_warnings'] = credit_warning_data(
            self.business, context['form'].fields['customer'].queryset
        )
        return context

    def form_valid(self, form):
        payments = form.get_payments()
        total_amount = form.get_total_amount()
        fiado_amount = form.cleaned_data.get('fiado_amount') or Decimal('0.00')

        try:
            create_sale(
                business=self.business,
                user=self.request.user,
                total_amount=total_amount,
                payments=payments,
                customer=form.cleaned_data.get('customer'),
                description=form.cleaned_data.get('description', ''),
                sold_at=form.cleaned_data['sold_at'],
                fiado_amount=fiado_amount,
            )
        except ValidationError as exc:
            messages.error(self.request, str(exc.message) if hasattr(exc, 'message') else str(exc))
            return self.form_invalid(form)

        messages.success(self.request, 'Venda registrada com sucesso.')
        if fiado_amount > 0:
            warn_credit_limit(self.request, self.business, form.cleaned_data.get('customer'))
        return super().form_valid(form)


class SaleCancelView(BusinessRequiredMixin, View):
    operator_allowed = True

    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, business=self.business)
        reason = request.POST.get('reason', '')
        try:
            cancel_sale(sale, request.user, reason)
            messages.success(request, 'Venda cancelada com sucesso.')
        except ValidationError as exc:
            messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
        return redirect('sales:sale_list')


class ComandaCreateView(BusinessRequiredMixin, FormView):
    template_name = 'sales/comanda_form.html'
    form_class = ComandaForm
    operator_allowed = True

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['business'] = self.business
        return kwargs

    def form_valid(self, form):
        comanda = open_comanda(
            self.business,
            self.request.user,
            identifier=form.cleaned_data.get('identifier', ''),
            customer=form.cleaned_data.get('customer'),
        )
        messages.success(self.request, 'Comanda aberta com sucesso.')
        return redirect('sales:comanda_detail', pk=comanda.pk)


class ComandaDetailView(BusinessRequiredMixin, DetailView):
    template_name = 'sales/comanda_detail.html'
    context_object_name = 'comanda'
    operator_allowed = True

    def get_queryset(self):
        return Comanda.objects.filter(business=self.business)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item_form'] = ComandaItemForm()
        context['payment_form'] = ComandaPaymentForm(business=self.business)
        context['credit_warnings'] = credit_warning_data(
            self.business, context['payment_form'].fields['customer'].queryset
        )
        products = Product.objects.filter(
            business=self.business, is_active=True
        ).order_by('name')
        context['products'] = products
        context['products_json'] = [
            {'id': p.pk, 'name': p.name, 'price': str(p.price)} for p in products
        ]
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if 'add_item' in request.POST:
            form = ComandaItemForm(request.POST)
            if form.is_valid():
                try:
                    add_comanda_item(
                        self.object,
                        form.cleaned_data['description'],
                        form.cleaned_data['quantity'],
                        form.cleaned_data['unit_price'],
                    )
                    messages.success(request, 'Item adicionado à comanda.')
                except ValidationError as exc:
                    messages.error(request, str(exc))
            else:
                messages.error(request, 'Dados do item inválidos.')

        elif 'edit_item' in request.POST:
            item = get_object_or_404(ComandaItem, pk=request.POST.get('item_id'), comanda=self.object)
            form = ComandaItemForm(request.POST)
            if form.is_valid():
                try:
                    update_comanda_item(
                        item,
                        form.cleaned_data['description'],
                        form.cleaned_data['quantity'],
                        form.cleaned_data['unit_price'],
                    )
                    messages.success(request, 'Item atualizado com sucesso.')
                except ValidationError as exc:
                    messages.error(request, str(exc))
            else:
                messages.error(request, 'Dados do item inválidos.')

        elif 'delete_item' in request.POST:
            item = get_object_or_404(ComandaItem, pk=request.POST.get('item_id'), comanda=self.object)
            try:
                remove_comanda_item(item)
                messages.success(request, 'Item removido da comanda.')
            except ValidationError as exc:
                messages.error(request, str(exc))

        elif 'delete_comanda' in request.POST:
            try:
                delete_empty_comanda(self.object)
                messages.success(request, 'Comanda excluída com sucesso.')
                return redirect('cash:dashboard')
            except ValidationError as exc:
                messages.error(request, str(exc))

        elif 'register_payment' in request.POST:
            form = ComandaPaymentForm(request.POST, business=self.business)
            if form.is_valid():
                try:
                    register_comanda_payment(
                        self.object,
                        form.cleaned_data['method'],
                        form.cleaned_data['amount'],
                        request.user,
                        customer=form.cleaned_data.get('customer'),
                    )
                    messages.success(request, 'Pagamento registrado com sucesso.')
                    if form.cleaned_data['method'] == PAYMENT_METHOD_FIADO:
                        warn_credit_limit(request, self.business, form.cleaned_data.get('customer'))
                except ValidationError as exc:
                    messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
            else:
                for error_list in form.errors.values():
                    for error in error_list:
                        messages.error(request, error)

        elif 'edit_payment' in request.POST:
            payment = get_object_or_404(
                ComandaPayment, pk=request.POST.get('payment_id'), comanda=self.object
            )
            form = ComandaPaymentForm(request.POST, business=self.business)
            if form.is_valid():
                try:
                    update_comanda_payment(
                        payment,
                        form.cleaned_data['method'],
                        form.cleaned_data['amount'],
                        customer=form.cleaned_data.get('customer'),
                    )
                    messages.success(request, 'Pagamento atualizado com sucesso.')
                    if form.cleaned_data['method'] == PAYMENT_METHOD_FIADO:
                        warn_credit_limit(request, self.business, form.cleaned_data.get('customer'))
                except ValidationError as exc:
                    messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
            else:
                for error_list in form.errors.values():
                    for error in error_list:
                        messages.error(request, error)

        elif 'delete_payment' in request.POST:
            payment = get_object_or_404(
                ComandaPayment, pk=request.POST.get('payment_id'), comanda=self.object
            )
            try:
                remove_comanda_payment(payment)
                messages.success(request, 'Pagamento removido com sucesso.')
            except ValidationError as exc:
                messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))

        return self.get(request, *args, **kwargs)


class ComandaFinalizeView(BusinessRequiredMixin, View):
    operator_allowed = True

    def post(self, request, pk):
        comanda = get_object_or_404(Comanda, pk=pk, business=self.business)

        try:
            finalize_comanda(comanda, request.user)
            messages.success(request, 'Comanda finalizada com sucesso.')
        except ValidationError as exc:
            messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
            return redirect('sales:comanda_detail', pk=comanda.pk)

        return redirect('cash:dashboard')
