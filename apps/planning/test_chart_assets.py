import json
import re
from decimal import Decimal
from pathlib import Path

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from .annual import build_annual_charts


class AnnualChartAssetTests(SimpleTestCase):
    def test_local_assets_are_available(self):
        for path in (
            'js/vendor/echarts/echarts.min.js',
            'js/vendor/echarts/LICENSE',
            'js/vendor/echarts/NOTICE',
            'js/planning/annual_charts.js',
        ):
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path))

    def test_desktop_chart_grid_is_responsive(self):
        css_path = finders.find('css/planning/annual.css')
        self.assertIsNotNone(css_path)
        css = Path(css_path).read_text(encoding='utf-8')
        self.assertRegex(css, r'@media\s*\(min-width:\s*992px\)')
        self.assertIn('grid-template-columns: repeat(2, minmax(0, 1fr));', css)
        self.assertIn('.annual-chart:first-child,', css)
        self.assertIn('.annual-chart:last-child', css)
        self.assertIn('grid-column: 1 / -1;', css)

    def test_bar_value_labels_and_pending_values_are_configured(self):
        js_path = finders.find('js/planning/annual_charts.js')
        self.assertIsNotNone(js_path)
        js = Path(js_path).read_text(encoding='utf-8')
        self.assertRegex(js, r"label:\s*\{\s*show:\s*true,\s*position:\s*'outside'")
        self.assertIn("if (bar.pending) return null;", js)
        self.assertIn("formatter: (params) => currency.format(params.value)", js)
        self.assertIn("show: !showBarValues", js)

    def test_json_preserves_pending_and_negative_values(self):
        months = [{
            'name': 'Janeiro',
            'status': 'Parcial',
            'revenue_actual': Decimal('60.00'),
            'expenses_actual': Decimal('80.00'),
            'revenue_planned': Decimal('100.00'),
            'expenses_planned': Decimal('40.00'),
            'net_actual': Decimal('-20.00'),
            'net_planned': Decimal('60.00'),
        }, {
            'name': 'Fevereiro',
            'status': 'Futuro',
            'revenue_actual': Decimal('0.00'),
            'expenses_actual': Decimal('15.00'),
            'revenue_planned': Decimal('0.00'),
            'expenses_planned': Decimal('0.00'),
            'net_actual': Decimal('-15.00'),
            'net_planned': Decimal('0.00'),
        }]
        charts = build_annual_charts(months)
        charts[0]['title'] = '</script><script>alert(1)</script>'
        html = render_to_string('planning/_annual_summary.html', {
            'year': 2024,
            'annual_charts': charts,
        })
        match = re.search(
            r'<script id="annual-charts-data" type="application/json">(.*?)</script>',
            html, re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertNotIn('</script><script>alert(1)</script>', html)
        serialized = json.loads(match.group(1))
        self.assertEqual(serialized[0]['title'], charts[0]['title'])
        self.assertTrue(serialized[0]['rows'][1]['bars'][0]['pending'])
        self.assertIsNone(serialized[0]['rows'][1]['bars'][0]['value'])
        self.assertEqual(serialized[0]['rows'][1]['bars'][1]['value'], '15.00')
        self.assertEqual(serialized[3]['rows'][0]['bars'][1]['value'], '-20.00')
        self.assertIn('annual-chart__graphic', html)
        self.assertEqual(html.count('class="annual-chart__accessible-table"'), 4)
        self.assertNotIn('Caixa parcial', html)
        self.assertNotIn('Sem fechamento ou mês futuro', html)
        self.assertNotIn('annual-chart__status-mark', html)
        self.assertNotIn('annual-chart__table-scroll', html)
        titles = [chart['title'] for chart in charts]
        self.assertEqual(titles[1:3], ['Faturamento', 'Gastos'])
        self.assertEqual(html.count('data-orientation="vertical"'), 1)
        self.assertEqual(html.count('data-orientation="horizontal"'), 3)
        chart_elements = re.findall(r'<div class="annual-chart__echarts[^"]*"[^>]*>', html)
        self.assertEqual(len(chart_elements), 4)
        for index, element in enumerate(chart_elements):
            with self.subTest(chart=index):
                self.assertEqual('data-bar-value-labels="true"' in element, index in (1, 2))
