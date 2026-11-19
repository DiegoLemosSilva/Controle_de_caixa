from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, UpdateView

from apps.businesses.mixins import BusinessRequiredMixin

from .forms import (
    PayableCreateForm,
    PayablePaymentForm,
    PayableSeriesUpdateForm,
    PayableUpdateForm,
)
from .models import Payable, PayableSeries
from .series_services import (
    cancel_future_occurrences,
    create_series,
    ensure_series_occurrences,
    mark_detached_if_diverges,
    update_series_and_future_occurrences,
)
from .services import mark_payable_as_paid, register_payment, reopen_payable

MONTH_NAMES_PT = [
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]


class PayableListView(BusinessRequiredMixin, ListView):
    template_name = 'payables/payable_list.html'
    context_object_name = 'payables'
    paginate_by = 50

    def get(self, request, *args, **kwargs):
        # Geração "lazy" das próximas ocorrências de séries fixas/
        # semanais ativas, sempre que a listagem é acessada. Idempotente
        # e sem dependências externas (ver AGENTS.md sobre não usar
        # jobs em background).
        ensure_series_occurrences(self.business, request.user)
        return super().get(request, *args, **kwargs)

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
        return Payable.objects.filter(
            business=self.business, due_date__year=year, due_date__month=month
        ).select_related('series').order_by('due_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year, month = self.get_month_year()

        previous_index = year * 12 + (month - 1) - 1
        previous_year, previous_month = divmod(previous_index, 12)
        previous_month += 1
        next_index = year * 12 + (month - 1) + 1
        next_year, next_month = divmod(next_index, 12)
        next_month += 1

        active_month_payables = self.get_queryset().exclude(status=Payable.STATUS_CANCELLED)
        paid_total = Decimal('0.00')
        pending_total = Decimal('0.00')
        for payable in active_month_payables:
            paid_total += payable.paid_amount
            pending_total += payable.balance

        month_total = paid_total + pending_total
        if month_total > 0:
            percent_paid = (paid_total / month_total) * Decimal('100')
        else:
            percent_paid = Decimal('0')

        overdue_payables = Payable.objects.filter(
            business=self.business,
            due_date__lt=timezone.localdate(),
        ).exclude(
            status__in=[Payable.STATUS_PAID, Payable.STATUS_CANCELLED]
        ).order_by('due_date')

        context.update({
            'year': year,
            'month': month,
            'month_label': MONTH_NAMES_PT[month],
            'previous_year': previous_year,
            'previous_month': previous_month,
            'next_year': next_year,
            'next_month': next_month,
            'paid_total': paid_total,
            'pending_total': pending_total,
            'percent_paid': percent_paid,
            'overdue_payables': overdue_payables,
        })
        return context


class PayableCreateView(BusinessRequiredMixin, View):
    """
    Criação de conta a pagar: Única (comportamento padrão de sempre)
    ou recorrente (Fixa, Semanal, Parcelada), conforme o campo `mode`
    escolhido na interface.
    """

    template_name = 'payables/payable_form.html'

    def get(self, request, *args, **kwargs):
        form = PayableCreateForm(initial={'due_date': timezone.localdate()})
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        form = PayableCreateForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        data = form.cleaned_data
        mode = data['mode']

        if mode == PayableCreateForm.MODE_SINGLE:
            Payable.objects.create(
                business=self.business,
                description=data['description'],
                supplier_name=data['supplier_name'],
                original_amount=data['amount'],
                due_date=data['due_date'],
                created_by=request.user,
            )
            messages.success(request, 'Conta a pagar cadastrada com sucesso.')
            return redirect('payables:payable_list')

        kind_map = {
            PayableCreateForm.MODE_FIXED: PayableSeries.KIND_FIXED,
            PayableCreateForm.MODE_WEEKLY: PayableSeries.KIND_WEEKLY,
            PayableCreateForm.MODE_INSTALLMENT: PayableSeries.KIND_INSTALLMENT,
        }
        try:
            create_series(
                business=self.business,
                user=request.user,
                kind=kind_map[mode],
                description=data['description'],
                supplier_name=data['supplier_name'],
                amount=data['amount'],
                start_date=data['due_date'],
                day_of_month=data.get('day_of_month'),
                weekday=int(data['weekday']) if data.get('weekday') not in (None, '') else None,
                total_installments=data.get('total_installments'),
            )
            messages.success(request, 'Série de contas a pagar criada com sucesso.')
        except ValidationError as exc:
            messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
            return render(request, self.template_name, {'form': form})

        return redirect('payables:payable_list')


class PayableUpdateView(BusinessRequiredMixin, UpdateView):
    template_name = 'payables/payable_form.html'
    form_class = PayableUpdateForm
    success_url = reverse_lazy('payables:payable_list')

    def get_queryset(self):
        return Payable.objects.filter(business=self.business)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['single_edit'] = True
        return context

    def form_valid(self, form):
        original = self.get_object()
        original_description = original.description
        original_amount = original.original_amount
        original_due_date = original.due_date

        response = super().form_valid(form)

        mark_detached_if_diverges(
            self.object, original_description, original_amount, original_due_date
        )

        messages.success(self.request, 'Conta a pagar atualizada com sucesso.')
        return response


class PayableDetailView(BusinessRequiredMixin, DetailView):
    template_name = 'payables/payable_detail.html'
    context_object_name = 'payable'

    def get_queryset(self):
        return Payable.objects.filter(business=self.business)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['payment_form'] = PayablePaymentForm()
        context['payments'] = self.object.payments.order_by('paid_at')
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = PayablePaymentForm(request.POST)

        if form.is_valid():
            try:
                register_payment(
                    self.object,
                    request.user,
                    form.cleaned_data['amount'],
                    timezone.now(),
                )
                messages.success(request, 'Pagamento registrado com sucesso.')
            except ValidationError as exc:
                messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
        else:
            messages.error(request, 'Dados de pagamento inválidos.')

        return self.get(request, *args, **kwargs)


class PayableMarkAsPaidView(BusinessRequiredMixin, View):
    def post(self, request, pk):
        payable = get_object_or_404(Payable, pk=pk, business=self.business)
        try:
            mark_payable_as_paid(payable, request.user)
            messages.success(request, f'Conta "{payable.description}" marcada como paga.')
        except ValidationError as exc:
            messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
        return redirect('payables:payable_list')


class PayableReopenView(BusinessRequiredMixin, View):
    def post(self, request, pk):
        payable = get_object_or_404(Payable, pk=pk, business=self.business)
        try:
            reopen_payable(payable)
            messages.success(request, f'Conta "{payable.description}" marcada como aberta.')
        except ValidationError as exc:
            messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
        return redirect('payables:payable_list')


class PayableSeriesDetailView(BusinessRequiredMixin, DetailView):
    """Mostra todas as ocorrências (passadas e futuras) de uma série."""

    template_name = 'payables/payable_series_detail.html'
    context_object_name = 'series'

    def get_queryset(self):
        return PayableSeries.objects.filter(business=self.business)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['occurrences'] = self.object.payables.order_by('due_date')
        context['update_form'] = PayableSeriesUpdateForm(initial={
            'description': self.object.description,
            'supplier_name': self.object.supplier_name,
            'amount': self.object.amount,
        })
        return context


class PayableSeriesUpdateView(BusinessRequiredMixin, View):
    """Edita o molde da série e aplica a mudança às ocorrências futuras elegíveis."""

    def post(self, request, pk):
        series = get_object_or_404(PayableSeries, pk=pk, business=self.business)
        form = PayableSeriesUpdateForm(request.POST)

        if form.is_valid():
            try:
                count = update_series_and_future_occurrences(
                    series,
                    form.cleaned_data['description'],
                    form.cleaned_data['supplier_name'],
                    form.cleaned_data['amount'],
                )
                messages.success(
                    request,
                    f'Série atualizada. {count} ocorrência(s) futura(s) foram ajustadas.',
                )
            except ValidationError as exc:
                messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
        else:
            messages.error(request, 'Dados inválidos para atualizar a série.')

        return redirect('payables:payable_series_detail', pk=series.pk)


class PayableSeriesCancelView(BusinessRequiredMixin, View):
    """Cancela as ocorrências futuras não pagas da série e pausa a geração."""

    def post(self, request, pk):
        series = get_object_or_404(PayableSeries, pk=pk, business=self.business)
        count = cancel_future_occurrences(series, request.user)
        messages.success(
            request,
            f'Série cancelada. {count} ocorrência(s) futura(s) foram canceladas.',
        )
        return redirect('payables:payable_list')
