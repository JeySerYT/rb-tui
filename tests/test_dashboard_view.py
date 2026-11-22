"""Тесты view-model и HTML-сборки дашборда."""

import unittest

from rb_tui import dashboard, metrics
from rb_tui.dashboard_view import build_view


def sample_metrics():
    data = {}
    for _ in range(3):
        data = metrics.add_metric(
            data, "alpha/model", "OK", 1.0, 2.0, 11, tts=1.5)
    for _ in range(3):
        data = metrics.add_metric(
            data, "beta/model", "ERR", None, 0.2, 0, msg="no_channel_for_model")
    return data


class BuildViewTest(unittest.TestCase):
    def test_counts_and_averages(self):
        view = build_view(sample_metrics())

        self.assertEqual(view["counts"]["stable"], 1)
        self.assertEqual(view["counts"]["dead"], 1)
        self.assertEqual(view["checks"], 6)
        self.assertAlmostEqual(view["averages"]["ttft"], 1.0)
        self.assertAlmostEqual(view["averages"]["tts"], 1.5)
        self.assertAlmostEqual(view["averages"]["tps"], 5.5)
        self.assertAlmostEqual(view["averages"]["success"], 50.0)
        self.assertIsInstance(view["health"], int)

    def test_stable_models_come_first(self):
        view = build_view(sample_metrics())
        self.assertEqual(view["models"][0]["id"], "alpha/model")
        self.assertEqual(view["models"][0]["status"], "stable")
        self.assertEqual(view["models"][1]["id"], "beta/model")

    def test_empty_metrics(self):
        view = build_view({})
        self.assertEqual(view["models"], [])
        self.assertEqual(view["checks"], 0)
        self.assertEqual(view["counts"], {"stable": 0, "unstable": 0, "dead": 0, "unknown": 0})
        self.assertIsNone(view["averages"]["tts"])
        self.assertEqual(view["health"], 50)

    def test_owner_tag_and_last_error(self):
        data = sample_metrics()
        view = build_view(
            data,
            owned={"alpha/model": "deepseek"},
            tags={"beta/model": "coding"},
        )
        by_id = {m["id"]: m for m in view["models"]}
        self.assertEqual(by_id["alpha/model"]["owner"], "deepseek")
        self.assertEqual(by_id["beta/model"]["tag"], "coding")
        self.assertEqual(by_id["beta/model"]["last_error"], "no_channel_for_model")

    def test_model_detail_uses_history(self):
        from rb_tui.dashboard_view import build_model_detail
        data = sample_metrics()
        detail = build_model_detail(data, "alpha/model")
        self.assertEqual(detail["model"], "alpha/model")
        self.assertEqual(len(detail["history"]), 3)
        self.assertEqual(detail["stats"]["status"], "stable")
        self.assertIsNone(build_model_detail(data, "missing"))


class RenderHtmlTest(unittest.TestCase):
    def test_embeds_initial_data(self):
        html = dashboard.render_html(build_view(sample_metrics()))
        self.assertNotIn("__INITIAL__", html)
        self.assertIn("alpha/model", html)
        self.assertIn('id="kpi-tts"', html)
        self.assertIn('id="drawer"', html)
        self.assertIn('href="/export.csv"', html)

    def test_escapes_script_breakout(self):
        data = metrics.add_metric(
            {}, "bad</script><b>x", "OK", 1.0, 2.0, 11, tts=1.5)
        html = dashboard.render_html(build_view(data))
        self.assertNotIn("bad</script>", html)
        self.assertIn("bad\\u003c/script", html)


if __name__ == "__main__":
    unittest.main()