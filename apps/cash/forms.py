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
    """Formulário de reabertura de um dia fechado, com justificativa obrigatória."""

    date = forms.DateField(widget=forms.HiddenInput())
    reason = forms.CharField(
        label='Motivo da reabertura',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
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
    reason = forms.CharField(
        label='Justificativa',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        help_text='Obrigatória apenas se o valor contado for diferente do esperado.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].initial = timezone.localdate()

    def clean_counted_amount(self):
        value = self.cleaned_data['counted_amount']
        if value < 0:
            raise forms.ValidationError('O valor contado não pode ser negativo.')
        return value
