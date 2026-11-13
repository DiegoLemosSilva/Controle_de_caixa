from decimal import Decimal

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase


class SaleListAssetsTests(SimpleTestCase):
    def test_page_loads_specific_static_files(self):
        html = render_to_string('sales/sale_list.html', {
            'month_label': 'Novembro',
            'year': 2026,
            'previous_year': 2026,
            'previous_month': 10,
            'next_year': 2026,
            'next_month': 12,
            'month_total': Decimal('100.00'),
            'sales_paid_at_sale': Decimal('60.00'),
            'total_received': Decimal('60.00'),
            'received_sales_total': Decimal('60.00'),
            'received_fiado_total': Decimal('0.00'),
            'fiado_total': Decimal('40.00'),
        })

        self.assertIn('/static/css/sales/sale_list.css', html)
        self.assertIn('/static/js/sales/sale_list.js', html)
        self.assertIn('id="toggle-values-btn"', html)
        self.assertIn('Fiado lançado no mês', html)
        self.assertIn('Pago na venda', html)
        self.assertIn('class="js-money-value" data-value="60,00"', html)
        self.assertIn('class="js-money-value" data-value="40,00"', html)
        self.assertIsNotNone(finders.find('css/sales/sale_list.css'))
        self.assertIsNotNone(finders.find('js/sales/sale_list.js'))

    def test_received_breakdown_shows_sales_and_fiado_portions(self):
        context = {
            'received_sales_total': Decimal('50.00'),
            'received_fiado_total': Decimal('20.00'),
        }
        html = render_to_string('sales/sale_list.html', context)
        for label, amount in (
            ('Vendas recebidas', '50,00'),
            ('Recebido de fiado', '20,00'),
        ):
            self.assertIn(label, html)
            self.assertIn(f'class="js-money-value" data-value="{amount}"', html)

    def test_cancellation_forms_use_external_confirmation_handler(self):
        html = render_to_string('sales/sale_list.html', {
            'sales_by_day': [{
                'sales': [{
                    'pk': 1,
                    'status': 'completed',
                    'total_amount': Decimal('10.00'),
                }],
                'total': Decimal('10.00'),
                'fiado_total': Decimal('0.00'),
                'received_fiado_total': Decimal('0.00'),
                'count': 1,
            }],
        })

        self.assertEqual(html.count('js-confirm-sale-cancel'), 2)
        self.assertNotIn('onsubmit=', html)
