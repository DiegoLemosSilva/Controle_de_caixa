from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.core.constants import COMANDA_PAYMENT_METHOD_CHOICES
from apps.customers.models import Customer

from .models import ComandaItem


class SaleForm(forms.Form):
    """
    Formulário de venda com divisão entre formas de pagamento e fiado.

    Para manter a interface simples (sem JavaScript de linhas dinâmicas),
    o formulário já traz um campo de valor para cada forma de pagamento
    suportada, além do valor fiado. Campos deixados em branco ou com
    valor zero são ignorados na criação da venda.
    """

    description = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Descrição',
    )
    sold_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        label='Data e hora da venda',
    )
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Cliente (obrigatório se houver fiado)',
    )
    amount_cash = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Dinheiro',
    )
    amount_pix = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Pix',
    )
    amount_debit = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Cartão de débito',
    )
    amount_credit = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Cartão de crédito',
    )
    amount_other = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Outro',
    )
    fiado_amount = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Fiado',
    )

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sold_at'].initial = timezone.localtime(timezone.now()).strftime(
            '%Y-%m-%dT%H:%M'
        )
        if business is not None:
            self.fields['customer'].queryset = Customer.objects.filter(
                business=business, is_active=True
            ).order_by('name')

    def get_payments(self):
        """Retorna a lista de pagamentos [{'method': ..., 'amount': ...}, ...]."""
        mapping = [
            ('amount_cash', 'dinheiro'),
            ('amount_pix', 'pix'),
            ('amount_debit', 'debito'),
            ('amount_credit', 'credito'),
            ('amount_other', 'outro'),
        ]
        payments = []
        for field, method in mapping:
            amount = self.cleaned_data.get(field)
            if amount:
                payments.append({'method': method, 'amount': amount})
        return payments

    def get_total_amount(self):
        payments_total = sum(
            (payment['amount'] for payment in self.get_payments()), Decimal('0.00')
        )
        fiado = self.cleaned_data.get('fiado_amount') or Decimal('0.00')
        return payments_total + fiado


class ComandaForm(forms.Form):
    identifier = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Identificação (mesa, nome, etc.)',
    )
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Cliente (opcional)',
    )

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        if business is not None:
            self.fields['customer'].queryset = Customer.objects.filter(
                business=business, is_active=True
            ).order_by('name')


class ComandaItemForm(forms.ModelForm):
    class Meta:
        model = ComandaItem
        fields = ['description', 'quantity', 'unit_price']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class ComandaPaymentForm(forms.Form):
    """
    Formulário de pagamento parcial de uma comanda aberta: cada pessoa
    da mesa registra sua parte, com sua própria forma de pagamento.
    O campo cliente só é exigido quando a forma for Fiado.
    """

    method = forms.ChoiceField(
        choices=COMANDA_PAYMENT_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Forma de pagamento',
    )
    amount = forms.DecimalField(
        min_value=Decimal('0.01'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Valor',
    )
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Cliente (obrigatório se Fiado)',
    )

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        if business is not None:
            self.fields['customer'].queryset = Customer.objects.filter(
                business=business, is_active=True
            ).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('method') == 'fiado' and not cleaned_data.get('customer'):
            self.add_error('customer', 'É obrigatório informar o cliente para pagamento em fiado.')
        return cleaned_data
