from django import forms

from .models import Payable, WEEKDAY_CHOICES


class PayableForm(forms.ModelForm):
    class Meta:
        model = Payable
        fields = ['description', 'supplier_name', 'original_amount', 'due_date']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_name': forms.TextInput(attrs={'class': 'form-control'}),
            'original_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'due_date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'
            ),
        }


class PayableUpdateForm(forms.ModelForm):
    """
    Edição de uma conta a pagar já cadastrada. O valor original não é
    editável aqui: é um lançamento financeiro fixo, assim como em
    outros registros do sistema (ex.: valor de uma venda).
    """

    class Meta:
        model = Payable
        fields = ['description', 'supplier_name', 'due_date']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier_name': forms.TextInput(attrs={'class': 'form-control'}),
            'due_date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'
            ),
        }


class PayablePaymentForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )


class PayableCreateForm(forms.Form):
    """
    Formulário único de criação de conta a pagar, cobrindo tanto uma
    conta "Única" (comportamento padrão de sempre) quanto a criação de
    uma série recorrente (Fixa, Semanal ou Parcelada).

    O campo `mode` é controlado pela interface (seletor visual) e
    determina quais dos demais campos são obrigatórios. Mantido como
    forms.Form (não ModelForm) porque os campos extras de recorrência
    não pertencem ao modelo Payable.
    """

    MODE_SINGLE = 'single'
    MODE_FIXED = 'fixed'
    MODE_WEEKLY = 'weekly'
    MODE_INSTALLMENT = 'installment'
    MODE_CHOICES = [
        (MODE_SINGLE, 'Única'),
        (MODE_FIXED, 'Fixa'),
        (MODE_WEEKLY, 'Semanal'),
        (MODE_INSTALLMENT, 'Parcelada'),
    ]

    mode = forms.ChoiceField(
        choices=MODE_CHOICES, initial=MODE_SINGLE,
        widget=forms.HiddenInput(),
    )
    description = forms.CharField(
        max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    supplier_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    day_of_month = forms.IntegerField(
        required=False, min_value=1, max_value=31,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    weekday = forms.ChoiceField(
        choices=WEEKDAY_CHOICES, required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    total_installments = forms.IntegerField(
        required=False, min_value=2, max_value=120,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get('mode')

        if mode == self.MODE_FIXED and not cleaned.get('day_of_month'):
            self.add_error('day_of_month', 'Informe o dia do mês para uma conta fixa.')
        if mode == self.MODE_WEEKLY and cleaned.get('weekday') in (None, ''):
            self.add_error('weekday', 'Informe o dia da semana para uma conta semanal.')
        if mode == self.MODE_INSTALLMENT and not cleaned.get('total_installments'):
            self.add_error(
                'total_installments', 'Informe o número de parcelas.'
            )
        return cleaned


class PayableSeriesUpdateForm(forms.Form):
    """
    Edição em massa de uma série fixa/semanal: aplica a mudança a
    todas as ocorrências futuras ainda não personalizadas manualmente
    (ver apps.payables.series_services.update_series_and_future_occurrences).
    """

    description = forms.CharField(
        max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    supplier_name = forms.CharField(
        max_length=150, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
