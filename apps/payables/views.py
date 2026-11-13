from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.businesses.mixins import BusinessRequiredMixin

from .forms import PayableForm, PayablePaymentForm, PayableUpdateForm
from .models import Payable
from .services import mark_payable_as_paid, register_payment, reopen_payable

MONTH_NAMES_PT = [
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]


class PayableListView(BusinessRequiredMixin, ListView):
    template_name = 'payables/payable_list.html'
    context_object_name = 'payables'
    paginate_by = 50

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
        ).order_by('due_date')

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


class PayableCreateView(BusinessRequiredMixin, CreateView):
    template_name = 'payables/payable_form.html'
    form_class = PayableForm
    success_url = reverse_lazy('payables:payable_list')

    def form_valid(self, form):
        form.instance.business = self.business
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Conta a pagar cadastrada com sucesso.')
        return super().form_valid(form)


class PayableUpdateView(BusinessRequiredMixin, UpdateView):
    template_name = 'payables/payable_form.html'
    form_class = PayableUpdateForm
    success_url = reverse_lazy('payables:payable_list')

    def get_queryset(self):
        return Payable.objects.filter(business=self.business)

    def form_valid(self, form):
        messages.success(self.request, 'Conta a pagar atualizada com sucesso.')
        return super().form_valid(form)


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
