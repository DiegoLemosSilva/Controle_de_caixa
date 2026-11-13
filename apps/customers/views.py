from decimal import Decimal

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.businesses.mixins import BusinessRequiredMixin
from apps.core.constants import PAYMENT_METHOD_CHOICES
from apps.receivables.models import Receivable, ReceivablePayment
from apps.receivables.services import register_customer_payment

from .forms import CustomerForm
from .models import Customer
from .services import credit_balances


class ReceivablePaymentForm(forms.Form):
    """
    Formulário de recebimento de fiado: o operador informa apenas o
    valor, a forma de pagamento e a data do recebimento. A distribuição
    entre as dívidas em aberto do cliente é feita automaticamente pelo
    sistema (FIFO), sem exigir que o operador escolha qual venda está
    sendo quitada.
    """

    paid_at = forms.DateField(
        label='Data do recebimento',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        initial=timezone.localdate,
    )
    amount = forms.DecimalField(
        label='Valor',
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    method = forms.ChoiceField(
        label='Forma de pagamento',
        choices=PAYMENT_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class CustomerListView(BusinessRequiredMixin, ListView):
    template_name = 'customers/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 50

    def get_queryset(self):
        queryset = Customer.objects.filter(business=self.business).order_by('name', 'pk')
        query = self.request.GET.get('q', '').strip()
        return queryset.filter(name__icontains=query) if query else queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        balances = credit_balances(self.business)
        context['query'] = self.request.GET.get('q', '').strip()
        context['total_open_credit'] = sum(
            (value['open_balance'] for value in balances.values()), Decimal('0.00')
        )
        for customer in context['customers']:
            customer.list_balance = balances.get(customer.pk, {}).get(
                'open_balance', Decimal('0.00')
            )
            customer.over_credit_limit = (
                customer.credit_limit is not None
                and customer.list_balance > customer.credit_limit
            )
        return context


class CustomerCreateView(BusinessRequiredMixin, CreateView):
    template_name = 'customers/customer_form.html'
    form_class = CustomerForm
    success_url = reverse_lazy('customers:customer_list')

    def form_valid(self, form):
        form.instance.business = self.business
        messages.success(self.request, 'Cliente cadastrado com sucesso.')
        return super().form_valid(form)


class CustomerUpdateView(BusinessRequiredMixin, UpdateView):
    template_name = 'customers/customer_form.html'
    form_class = CustomerForm
    success_url = reverse_lazy('customers:customer_list')

    def get_queryset(self):
        return Customer.objects.filter(business=self.business)

    def form_valid(self, form):
        messages.success(self.request, 'Cliente atualizado com sucesso.')
        return super().form_valid(form)


class CustomerDetailView(BusinessRequiredMixin, DetailView):
    template_name = 'customers/customer_detail.html'
    context_object_name = 'customer'

    def get_queryset(self):
        return Customer.objects.filter(business=self.business)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        receivables = self.object.receivables.exclude(
            status=Receivable.STATUS_CANCELLED
        ).order_by('-created_at')
        context['receivables'] = receivables
        context['payment_form'] = ReceivablePaymentForm()
        context['open_balance'] = self.object.open_balance()
        context['has_open_receivable'] = receivables.filter(
            status=Receivable.STATUS_OPEN
        ).exists()

        # Histórico combinado de compras (fiado) e pagamentos, do mais
        # recente para o mais antigo, para dar visão completa da conta
        # do cliente em uma única linha do tempo.
        history = []
        for receivable in receivables:
            history.append({
                'type': 'purchase',
                'date': receivable.created_at,
                'receivable': receivable,
            })
            for payment in receivable.payments.exclude(
                status=ReceivablePayment.STATUS_CANCELLED
            ):
                history.append({
                    'type': 'payment',
                    'date': payment.paid_at,
                    'receivable': receivable,
                    'payment': payment,
                })

        history.sort(key=lambda entry: entry['date'], reverse=True)
        context['history'] = history
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = ReceivablePaymentForm(request.POST)
        if form.is_valid():
            paid_at = timezone.make_aware(
                timezone.datetime.combine(form.cleaned_data['paid_at'], timezone.now().time())
            )
            try:
                register_customer_payment(
                    self.object,
                    request.user,
                    form.cleaned_data['amount'],
                    form.cleaned_data['method'],
                    paid_at,
                )
                messages.success(request, 'Recebimento registrado com sucesso.')
            except ValidationError as exc:
                messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))
        else:
            messages.error(request, 'Dados de pagamento inválidos.')

        return self.get(request, *args, **kwargs)
