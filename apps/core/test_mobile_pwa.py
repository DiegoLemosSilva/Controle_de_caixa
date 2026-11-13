"""Testes sem banco para navegação móvel e recursos públicos do PWA."""

import json
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.urls import reverse

from apps.sales.forms import ComandaItemForm, ComandaPaymentForm, SaleForm
from apps.sales.views import SaleCreateView


class MobileNavigationTests(SimpleTestCase):
    def test_mobile_navigation_respects_operator_menu(self):
        user = SimpleNamespace(is_authenticated=True)
        operator = render_to_string('base.html', {'user': user, 'is_operator': True})
        manager = render_to_string('base.html', {'user': user, 'is_operator': False})
        self.assertIn('aria-label="Atalhos principais"', operator)
        self.assertIn(reverse('sales:comanda_create'), operator)
        self.assertNotIn(reverse('payables:payable_list'), operator)
        self.assertIn(reverse('payables:payable_list'), manager)

    def test_anonymous_has_no_mobile_navigation(self):
        html = render_to_string('base.html', {'user': SimpleNamespace(is_authenticated=False)})
        self.assertNotIn('aria-label="Atalhos principais"', html)


class MobileSalesTests(SimpleTestCase):
    def test_decimal_keyboards_and_validation(self):
        form = SaleForm(data={'sold_at': '2026-11-13T12:00', 'amount_cash': '-1'})
        self.assertFalse(form.is_valid())
        self.assertIn('amount_cash', form.errors)
        for name in ('amount_cash', 'amount_pix', 'amount_debit', 'amount_credit', 'amount_other', 'fiado_amount'):
            self.assertEqual(form.fields[name].widget.attrs['inputmode'], 'decimal')
        self.assertEqual(ComandaItemForm().fields['quantity'].widget.attrs['inputmode'], 'decimal')
        self.assertEqual(ComandaPaymentForm().fields['amount'].widget.attrs['inputmode'], 'decimal')

    def test_invalid_sale_shows_payment_errors_and_operator_cancel(self):
        form = SaleForm(data={'sold_at': '2026-11-13T12:00', 'amount_cash': '-1'})
        self.assertFalse(form.is_valid())
        html = render_to_string('sales/sale_form.html', {
            'user': SimpleNamespace(is_authenticated=True),
            'is_operator': True,
            'form': form,
            'credit_warnings': {},
        })
        self.assertIn('for="id_amount_cash"', html)
        self.assertIn('maior ou igual a 0', html)
        self.assertIn(f'href="{reverse("cash:dashboard")}" class="btn btn-link">Cancelar', html)

    @patch('apps.sales.views.user_is_operator')
    def test_success_url_by_role(self, is_operator):
        view = SaleCreateView()
        view.request = SimpleNamespace(user=object())
        is_operator.return_value = True
        self.assertEqual(view.get_success_url(), reverse('cash:dashboard'))
        is_operator.return_value = False
        self.assertEqual(view.get_success_url(), reverse('sales:sale_list'))


class PWAAssetsTests(SimpleTestCase):
    def test_service_worker_served_at_root_without_authentication(self):
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('application/javascript'))
        self.assertIn('no-cache', response['Cache-Control'])
        body = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn("request.method !== 'GET'", body)
        self.assertIn("request.mode === 'navigate'", body)
        self.assertIn("cache.add(OFFLINE_URL)", body)
        self.assertNotIn('cache.put(', body)

    def test_manifest_icons_exist_with_expected_dimensions(self):
        manifest = json.loads(Path(finders.find('pwa/manifest.json')).read_text(encoding='utf-8'))
        self.assertEqual(manifest['start_url'], '/')
        for icon in manifest['icons']:
            path = finders.find(icon['src'].removeprefix('/static/'))
            self.assertIsNotNone(path)
            data = Path(path).read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            width, height = struct.unpack('!II', data[16:24])
            self.assertEqual(f'{width}x{height}', icon['sizes'])
        self.assertIsNotNone(finders.find('icons/icon-180.png'))
        self.assertIsNotNone(finders.find('pwa/offline.html'))
