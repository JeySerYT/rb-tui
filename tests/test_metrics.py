"""Тесты метрик: запись, обрезка истории, статусы, агрегаты."""

import unittest

from rb_tui import metrics


def ok_entry():
    return {"ts": "2026-01-01 00:00", "status": "OK", "ttft": 1.0,
            "total_time": 1.0, "tokens": 3}


class AddMetricTest(unittest.TestCase):
    def test_stores_error_message(self):
        data = metrics.add_metric({}, "m", "ERR", None, 0.2, 0,
                                  msg="no_channel_for_model")
        self.assertEqual(data["m"][0]["status"], "ERR")
        self.assertEqual(data["m"][0]["msg"], "no_channel_for_model")

    def test_skips_empty_message(self):
        data = metrics.add_metric({}, "m", "OK", 1.0, 1.0, 3)
        self.assertNotIn("msg", data["m"][0])

    def test_trims_history(self):
        data = {}
        for _ in range(metrics.MAX_HISTORY + 5):
            data = metrics.add_metric(data, "m", "OK", 1.0, 1.0, 3)
        self.assertEqual(len(data["m"]), metrics.MAX_HISTORY)

    def test_trims_to_latest_entries(self):
        data = {}
        for i in range(metrics.MAX_HISTORY + 1):
            data = metrics.add_metric(data, "m", "OK", float(i), 1.0, 3)
        self.assertEqual(data["m"][0]["ttft"], 1.0)


class StatusTest(unittest.TestCase):
    def test_unknown_without_history(self):
        self.assertEqual(metrics.model_status({}, "m"), "unknown")

    def test_stable_after_three_ok(self):
        data = {}
        for _ in range(3):
            data = metrics.add_metric(data, "m", "OK", 1.0, 1.0, 3)
        self.assertEqual(metrics.model_status(data, "m"), "stable")

    def test_dead_when_errors_dominate(self):
        data = {"m": [dict(ok_entry(), status="ERR", ttft=None) for _ in range(3)]}
        self.assertEqual(metrics.model_status(data, "m"), "dead")

    def test_unstable_on_mixed_results(self):
        data = {"m": [ok_entry(), dict(ok_entry(), status="ERR", ttft=None)]}
        self.assertEqual(metrics.model_status(data, "m"), "unstable")


class AggregatesTest(unittest.TestCase):
    def test_success_rate_avg_and_min(self):
        data = {"m": [
            dict(ok_entry(), ttft=1.0),
            dict(ok_entry(), status="ERR", ttft=None),
            dict(ok_entry(), ttft=3.0),
        ]}
        self.assertEqual(metrics.success_rate(data, "m"), 67)
        self.assertEqual(metrics.avg_ttft(data, "m"), 2.0)
        self.assertEqual(metrics.shortest_ttft(data, "m"), 1.0)

    def test_empty_aggregates_are_none(self):
        self.assertIsNone(metrics.avg_ttft({}, "m"))
        self.assertIsNone(metrics.success_rate({}, "m"))
        self.assertIsNone(metrics.full_stats({}, "m"))

    def test_health_score_without_data(self):
        self.assertEqual(metrics.health_score({}), 50)

    def test_full_stats_counts(self):
        data = {}
        data = metrics.add_metric(data, "m", "OK", 1.0, 1.0, 3)
        data = metrics.add_metric(data, "m", "ERR", None, 0.5, 0, msg="no_channel_for_model")
        stats = metrics.full_stats(data, "m")
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["ok"], 1)
        self.assertEqual(stats["err"], 1)
        self.assertEqual(stats["success_rate"], 50)


if __name__ == "__main__":
    unittest.main()