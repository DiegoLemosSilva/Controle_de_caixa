from pathlib import Path
import re
from types import SimpleNamespace

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import get_template, render_to_string
from django.test import SimpleTestCase


class FrontendAssetsTests(SimpleTestCase):
    def test_migrated_templates_compile_and_reference_existing_assets(self):
        assets = {
            "sales/sale_list.html": ["css/sales/sale_list.css", "js/sales/sale_list.js"],
            "sales/sale_form.html": ["js/product-search.js", "js/sales/sale_form.js"],
            "sales/comanda_detail.html": ["js/product-search.js", "js/sales/comanda_detail.js", "js/credit-warning.js"],
            "customers/customer_list.html": ["js/customers/customer_list.js"],
            "cash/dashboard.html": ["css/cash/dashboard.css"],
            "cash/cash_count.html": ["js/cash/cash_count.js"],
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

    def test_cash_date_filter_has_manual_submit(self):
        html = render_to_string("cash/cash_count.html", {"is_closed": True, "is_operator": True})
        self.assertIn('id="cash-count-date"', html)
        self.assertIn('type="submit" class="btn btn-outline-secondary">Consultar', html)
        self.assertIn("/static/js/cash/cash_count.js", html)

    def test_service_worker_registration_only_for_authenticated_users(self):
        for authenticated in (False, True):
            with self.subTest(authenticated=authenticated):
                html = render_to_string("base.html", {"user": SimpleNamespace(is_authenticated=authenticated)})
                self.assertEqual("/static/js/pwa-register.js" in html, authenticated)
                if authenticated:
                    self.assertIn('data-service-worker-url="/service-worker.js"', html)
        self.assertIsNotNone(finders.find("js/pwa-register.js"))
