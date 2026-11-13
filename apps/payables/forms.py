from django import forms

from .models import Payable


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
