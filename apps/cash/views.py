from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.businesses.mixins import BusinessRequiredMixin

from apps.core.constants import PAYMENT_METHOD_CHOICES

from .forms import CashCountBatchForm, CashCountForm, CloseDayForm, OpenCashSessionForm, ReopenDayForm
from .services import (
    close_cash_session,
    expected_amount_for_method,
    get_open_session,
    get_session_for_date,
    is_date_closed,
    latest_adjustments_for_date,
    open_cash_session,
    open_comandas_blocking_closure,
    register_cash_count,
    register_cash_counts_batch,
    reopen_cash_session,
)

PAYMENT_METHOD_LABELS = dict(PAYMENT_METHOD_CHOICES)


def _parse_date(value, default):
    if value:
        try:
            return timezone.datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            pass
    return default


class DashboardView(BusinessRequiredMixin, TemplateView):
    """
    Painel do Caixa com foco no dia: mostra os indicadores financeiros
    da data selecionada, com navegação para o dia anterior/seguinte.

    Por padrão, o caixa está fechado para qualquer data: se a data
    selecionada não tiver uma sessão de caixa aberta, exibe a tela de
    abertura de caixa (exigindo o valor inicial em dinheiro) em vez do
    resumo financeiro e das comandas.
    """

    template_name = 'cash/dashboard.html'
    operator_allowed = True

    def get_selected_date(self):
        return _parse_date(self.request.GET.get('date'), timezone.localdate())

    def get_context_data(self, **kwargs):
        from apps.sales.models import Comanda

        context = super().get_context_data(**kwargs)
        selected_date = self.get_selected_date()
        search_query = self.request.GET.get('q', '').strip()

        session = get_session_for_date(self.business, selected_date)
        is_closed = is_date_closed(self.business, selected_date)

        context['selected_date'] = selected_date
        context['is_today'] = selected_date == timezone.localdate()
        context['previous_date'] = selected_date - timedelta(days=1)
        context['next_date'] = selected_date + timedelta(days=1)
        context['is_closed'] = is_closed
        context['session'] = session

        if is_closed:
            # Sem sessão aberta: nada de financeiro é mostrado, apenas o
            # formulário de abertura de caixa (ou aviso, se já fechado).
            context['open_form'] = OpenCashSessionForm(initial={'date': selected_date})
            context['already_closed_today'] = session is not None and not session.is_open

            # Se existir um caixa aberto em OUTRA data, avisa claramente
            # em vez de apenas oferecer o formulário de abertura, evitando
            # que o usuário tente abrir um novo caixa sem saber que já
            # existe um em aberto em outro dia (regra de caixa único).
            other_open_session = get_open_session(self.business)
            if other_open_session is not None and other_open_session.date != selected_date:
                context['other_open_session'] = other_open_session

            return context

        comandas = Comanda.objects.filter(
            business=self.business, status=Comanda.STATUS_OPEN
        ).order_by('-opened_at')

        if search_query:
            comandas = comandas.filter(
                Q(identifier__icontains=search_query)
                | Q(customer__name__icontains=search_query)
            )

        now = timezone.now()
        for comanda in comandas:
            elapsed = now - comanda.opened_at
            total_minutes = int(elapsed.total_seconds() // 60)
            if total_minutes < 60:
                comanda.elapsed_label = f'{total_minutes} min'
            else:
                hours, minutes = divmod(total_minutes, 60)
                comanda.elapsed_label = f'{hours}h{minutes:02d}'

        context['comandas'] = comandas
        context['search_query'] = search_query
        return context


class OpenCashSessionView(BusinessRequiredMixin, View):
    """Abre o caixa de uma data, exigindo o valor inicial em dinheiro."""

    operator_allowed = True

    def post(self, request):
        form = OpenCashSessionForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Informe um valor de abertura válido.')
            return redirect(f"{reverse('cash:dashboard')}?date={request.POST.get('date')}")

        selected_date = form.cleaned_data['date']
        try:
            open_cash_session(
                self.business,
                request.user,
                selected_date,
                form.cleaned_data['opening_amount'],
            )
            messages.success(request, f'Caixa do dia {selected_date:%d/%m/%Y} aberto com sucesso.')
        except ValidationError as exc:
            messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))

        return redirect(f"{reverse('cash:dashboard')}?date={selected_date:%Y-%m-%d}")


class CashCountView(BusinessRequiredMixin, TemplateView):
    """
    Painel de conferência do caixa físico com envio conjunto por data.
    As conferências registradas mantêm o histórico de cada forma de pagamento.

    Quando todas as formas de pagamento estiverem conferidas, permite
    fechar o caixa do dia, bloqueando novos lançamentos financeiros
    para aquela data.
    """

    template_name = 'cash/cash_count.html'
    operator_allowed = True

    def get_selected_date(self):
        return _parse_date(self.request.GET.get('date'), timezone.localdate())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_date = self.get_selected_date()
        adjustments = latest_adjustments_for_date(self.business, selected_date)
        form = kwargs.get('batch_form')
        if form is None:
            form = CashCountBatchForm(adjustments=adjustments, initial={'date': selected_date})
        context['selected_date'] = selected_date
        context['adjustments'] = adjustments
        context['batch_form'] = form
        context['count_rows'] = [
            {
                'item': item,
                'counted': form[f"counted_{item['payment_method']}"],
                'expected': form[f"expected_{item['payment_method']}"],
                'revision': form[f"revision_{item['payment_method']}"],
            }
            for item in adjustments
        ]
        context['all_checked'] = all(item['checked'] for item in adjustments)
        context['is_closed'] = is_date_closed(self.business, selected_date)
        context['open_comandas'] = open_comandas_blocking_closure(self.business, selected_date)
        context['close_form'] = CloseDayForm(initial={'date': selected_date})
        context['reopen_form'] = ReopenDayForm(initial={'date': selected_date})
        return context

    def post(self, request):
        selected_date = self.get_selected_date()
        adjustments = latest_adjustments_for_date(self.business, selected_date)
        form = CashCountBatchForm(request.POST, adjustments=adjustments)
        if form.is_valid():
            if form.cleaned_data['date'] != selected_date:
                form.add_error(None, 'A data da conferência não corresponde à data selecionada.')
            else:
                entries = {
                    item['payment_method']: {
                        'counted': form.cleaned_data[f"counted_{item['payment_method']}"],
                        'expected': form.cleaned_data[f"expected_{item['payment_method']}"],
                        'revision': form.cleaned_data[f"revision_{item['payment_method']}"],
                    }
                    for item in adjustments
                }
                try:
                    register_cash_counts_batch(self.business, request.user, selected_date, entries)
                except ValidationError as exc:
                    form.add_error(None, exc)
                else:
                    messages.success(request, 'Conferências registradas com sucesso.')
                    return redirect(f"{reverse('cash:cash_count')}?date={selected_date:%Y-%m-%d}")
        return self.render_to_response(self.get_context_data(batch_form=form))


class CashCountDetailView(BusinessRequiredMixin, FormView):
    """
    Conferência de uma única forma de pagamento: mostra o valor esperado
    pelo sistema e permite confirmar o valor contado. Se os valores
    coincidirem, basta confirmar. Divergências não exigem justificativa.
    """

    template_name = 'cash/cash_count_detail.html'
    form_class = CashCountForm
    operator_allowed = True

    def get_selected_date(self):
        return _parse_date(
            self.request.GET.get('date') or self.request.POST.get('date'),
            timezone.localdate(),
        )

    def get_payment_method(self):
        return self.kwargs['payment_method']

    def dispatch(self, request, *args, **kwargs):
        if self.get_payment_method() not in PAYMENT_METHOD_LABELS:
            from django.http import Http404
            raise Http404('Forma de pagamento inválida.')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        selected_date = self.get_selected_date()
        initial['date'] = selected_date
        initial['payment_method'] = self.get_payment_method()
        initial['counted_amount'] = expected_amount_for_method(
            self.business, selected_date, self.get_payment_method()
        )
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_date = self.get_selected_date()
        payment_method = self.get_payment_method()

        context['selected_date'] = selected_date
        context['payment_method'] = payment_method
        context['payment_method_label'] = PAYMENT_METHOD_LABELS[payment_method]
        context['expected_amount'] = expected_amount_for_method(
            self.business, selected_date, payment_method
        )

        existing = next(
            (
                item for item in latest_adjustments_for_date(self.business, selected_date)
                if item['payment_method'] == payment_method and item['checked']
            ),
            None,
        )
        context['existing_adjustment'] = existing
        return context

    def get_success_url(self):
        return f"{reverse('cash:cash_count')}?date={self.get_selected_date():%Y-%m-%d}"

    def form_valid(self, form):
        try:
            register_cash_count(
                business=self.business,
                user=self.request.user,
                date=form.cleaned_data['date'],
                payment_method=form.cleaned_data['payment_method'],
                counted_amount=form.cleaned_data['counted_amount'],
                reason='',
            )
            messages.success(self.request, 'Conferência registrada com sucesso.')
        except ValidationError as exc:
            messages.error(self.request, str(exc.message) if hasattr(exc, 'message') else str(exc))
            return self.form_invalid(form)
        return super().form_valid(form)


class CloseDayView(BusinessRequiredMixin, View):
    """Fecha o caixa do dia, exigindo que todas as formas já estejam conferidas."""

    operator_allowed = True

    def post(self, request):
        form = CloseDayForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Data inválida para fechamento.')
            return self._redirect(request.POST.get('date'))

        selected_date = form.cleaned_data['date']
        try:
            close_cash_session(self.business, request.user, selected_date)
            messages.success(request, f'Caixa do dia {selected_date:%d/%m/%Y} fechado com sucesso.')
        except ValidationError as exc:
            messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))

        return self._redirect(selected_date)

    def _redirect(self, date):
        return redirect(f"{reverse('cash:cash_count')}?date={date}")


class ReopenDayView(BusinessRequiredMixin, View):
    """
    Reabre o caixa de um dia fechado.

    Exclusiva para usuários que não pertencem ao grupo "Operador": a
    reabertura de um caixa fechado é uma decisão gerencial, não uma
    operação do dia a dia do caixa.
    """

    def post(self, request):
        form = ReopenDayForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Data inválida para reabertura.')
            return self._redirect(request.POST.get('date'))

        selected_date = form.cleaned_data['date']
        try:
            reopen_cash_session(self.business, request.user, selected_date)
            messages.success(request, f'Caixa do dia {selected_date:%d/%m/%Y} reaberto com sucesso.')
        except ValidationError as exc:
            messages.error(request, str(exc.message) if hasattr(exc, 'message') else str(exc))

        return self._redirect(selected_date)

    def _redirect(self, date):
        return redirect(f"{reverse('cash:cash_count')}?date={date}")
