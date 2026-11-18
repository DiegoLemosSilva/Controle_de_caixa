from django import forms
from django.utils import timezone

from apps.core.constants import PAYMENT_METHOD_CHOICES


class OpenCashSessionForm(forms.Form):
    """Formulário de abertura do caixa, informando o valor inicial em dinheiro."""

    date = forms.DateField(widget=forms.HiddenInput())
    opening_amount = forms.DecimalField(
        label='Valor de abertura (dinheiro)',
        max_digits=12,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        help_text='Valor em dinheiro que está na gaveta ao iniciar o caixa de hoje.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].initial = timezone.localdate()


class CloseDayForm(forms.Form):
    """Formulário de confirmação do fechamento do caixa de um dia."""

    date = forms.DateField(widget=forms.HiddenInput())


class ReopenDayForm(forms.Form):
    """Formulário de reabertura de um dia fechado."""

    date = forms.DateField(widget=forms.HiddenInput())


class CashCountBatchForm(forms.Form):
    """Valores contados e valores esperados exibidos para cada forma."""

    date = forms.DateField(widget=forms.HiddenInput())

    def __init__(self, *args, adjustments, **kwargs):
        super().__init__(*args, **kwargs)
        for item in adjustments:
            method = item['payment_method']
            self.fields[f'counted_{method}'] = forms.DecimalField(
                label=item['label'],
                min_value=0,
                max_digits=12,
                decimal_places=2,
                widget=forms.NumberInput(attrs={
                    'class': 'form-control', 'step': '0.01',
                    'min': '0', 'inputmode': 'decimal',
                }),
                initial=item['counted_amount'] if item['checked'] else None,
            )
            self.fields[f'expected_{method}'] = forms.DecimalField(
                max_digits=12,
                decimal_places=2,
                widget=forms.HiddenInput(),
                initial=item['expected_amount'],
            )
            self.fields[f'revision_{method}'] = forms.IntegerField(
                min_value=0,
                widget=forms.HiddenInput(),
                initial=item['revision'],
            )


class CashCountForm(forms.Form):
    """
    Formulário de conferência de caixa físico para uma forma de pagamento
    em uma data específica.
    """

    date = forms.DateField(
        label='Data conferida',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
    )
    payment_method = forms.ChoiceField(
        label='Forma de pagamento',
        choices=PAYMENT_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    counted_amount = forms.DecimalField(
        label='Valor contado fisicamente',
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].initial = timezone.localdate()

    def clean_counted_amount(self):
        value = self.cleaned_data['counted_amount']
        if value < 0:
            raise forms.ValidationError('O valor contado não pode ser negativo.')
        return value
