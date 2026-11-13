from decimal import Decimal

from django import forms

WEEKDAYS = [
    (0, 'Segunda-feira'),
    (1, 'Terça-feira'),
    (2, 'Quarta-feira'),
    (3, 'Quinta-feira'),
    (4, 'Sexta-feira'),
    (5, 'Sábado'),
    (6, 'Domingo'),
]


class WeekdayValuesForm(forms.Form):
    monday = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Segunda-feira',
    )
    tuesday = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Terça-feira',
    )
    wednesday = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Quarta-feira',
    )
    thursday = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Quinta-feira',
    )
    friday = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Sexta-feira',
    )
    saturday = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Sábado',
    )
    sunday = forms.DecimalField(
        required=False, min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Domingo',
    )

    def get_weekday_values(self):
        field_to_weekday = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6,
        }
        values = {}
        for field, weekday in field_to_weekday.items():
            amount = self.cleaned_data.get(field)
            if amount is not None:
                values[weekday] = amount
        return values


class DailyValueForm(forms.Form):
    date = forms.DateField(
        widget=forms.DateInput(
            attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'
        ),
    )
    amount = forms.DecimalField(
        min_value=Decimal('0'), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
