from datetime import date
from pathlib import Path
import re
from types import SimpleNamespace

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import get_template, render_to_string
from django.test import SimpleTestCase
from django.urls import reverse

from apps.cash.forms import CashCountBatchForm, CloseDayForm, ReopenDayForm


class FrontendAssetsTests(SimpleTestCase):
    def test_migrated_templates_compile_and_reference_existing_assets(self):
        assets = {
            "sales/sale_list.html": ["css/sales/sale_list.css", "js/sales/sale_list.js"],
            "sales/sale_form.html": ["js/product-search.js", "js/sales/sale_form.js"],
            "sales/comanda_detail.html": ["js/product-search.js", "js/sales/comanda_detail.js", "js/credit-warning.js"],
            "customers/customer_list.html": ["js/customers/customer_list.js"],
            "cash/dashboard.html": ["css/cash/dashboard.css"],
            "cash/cash_count.html": ["css/cash/cash_count.css", "js/cash/cash_count_batch.js"],
            "cash/cash_count_detail.html": ["js/cash/cash_count_detail.js"],
            "planning/plan_dashboard.html": ["js/planning/plan_dashboard.js"],
            "ai_assistant/analysis_list.html": ["css/ai_assistant/analysis.css"],
        }
        for template_name, paths in assets.items():
            with self.subTest(template=template_name):
                get_template(template_name)
                source = (Path(settings.BASE_DIR) / "templates" / template_name).read_text(encoding="utf-8")
                for path in paths:
                    self.assertIn(path, source)
                    self.assertIsNotNone(finders.find(path), path)

    def test_no_inline_css_or_executable_javascript_in_templates(self):
        templates_dir = Path(settings.BASE_DIR) / "templates"
        inline_code = re.compile(r"<style\b|<script\s*>|\sstyle\s*=|\son[a-z]+\s*=", re.IGNORECASE)
        for template_path in templates_dir.rglob("*.html"):
            with self.subTest(template=str(template_path.relative_to(templates_dir))):
                self.assertIsNone(inline_code.search(template_path.read_text(encoding="utf-8")))

    def test_comanda_dependency_order_and_confirmation_markers(self):
        source = (Path(settings.BASE_DIR) / "templates/sales/comanda_detail.html").read_text(encoding="utf-8")
        self.assertLess(source.index("js/product-search.js"), source.index("js/sales/comanda_detail.js"))
        self.assertLess(source.index("js/sales/comanda_detail.js"), source.index("js/credit-warning.js"))
        self.assertEqual(source.count("data-confirm="), 3)
        self.assertIn('id="payment-customer-field" hidden', source)
        self.assertIn('id="edit-payment-customer-field" hidden', source)

    def test_cash_count_preserves_selected_date_without_filter(self):
        selected_date = date(2026, 11, 13)
        adjustments = [{
            "payment_method": "dinheiro", "label": "Dinheiro",
            "expected_amount": 0, "counted_amount": None,
            "revision": 0, "checked": False, "stale": False,
        }]
        batch_form = CashCountBatchForm(adjustments=adjustments, initial={"date": selected_date})
        context = {
            "selected_date": selected_date,
            "is_operator": False,
            "adjustments": adjustments,
            "batch_form": batch_form,
            "count_rows": [{
                "item": adjustments[0], "counted": batch_form["counted_dinheiro"],
                "expected": batch_form["expected_dinheiro"],
                "revision": batch_form["revision_dinheiro"],
            }],
            "close_form": CloseDayForm(initial={"date": selected_date}),
            "reopen_form": ReopenDayForm(initial={"date": selected_date}),
        }
        for is_closed in (False, True):
            with self.subTest(is_closed=is_closed):
                html = render_to_string("cash/cash_count.html", {**context, "is_closed": is_closed})
                self.assertIn("Data da conferência:", html)
                self.assertIn("13/11/2026", html)
                self.assertNotIn('id="cash-count-date"', html)
                self.assertNotIn("Data a conferir", html)
                self.assertNotIn(">Consultar</button>", html)
                self.assertNotIn("/static/js/cash/cash_count.js", html)
                self.assertIn('type="hidden" name="date" value="2026-11-13"', html)
                if not is_closed:
                    self.assertIn(f'{reverse("cash:cash_count")}?date=2026-11-13', html)
                    self.assertIn('name="counted_dinheiro"', html)
                    self.assertIn("Salvar conferências", html)
                    self.assertIn(reverse("cash:close_day"), html)
                else:
                    self.assertIn(reverse("cash:reopen_day"), html)
                    self.assertIn("Confirmar reabertura", html)
                    self.assertNotIn('name="reason"', html)

    def test_service_worker_registration_only_for_authenticated_users(self):
        for authenticated in (False, True):
            with self.subTest(authenticated=authenticated):
                html = render_to_string("base.html", {"user": SimpleNamespace(is_authenticated=authenticated)})
                self.assertEqual("/static/js/pwa-register.js" in html, authenticated)
                if authenticated:
                    self.assertIn('data-service-worker-url="/service-worker.js"', html)
        self.assertIsNotNone(finders.find("js/pwa-register.js"))
