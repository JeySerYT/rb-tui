"""Тесты метрик: запись, обрезка истории, статусы, агрегаты."""

import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

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

    def test_stores_tts_and_computes_tps(self):
        data = metrics.add_metric({}, "m", "OK", 1.0, 2.0, 11, tts=1.5)
        entry = data["m"][0]
        self.assertEqual(entry["tts"], 1.5)
        self.assertEqual(entry["tps"], 5.5)

    def test_no_tps_without_stream(self):
        data = metrics.add_metric({}, "m", "OK", 1.0, 2.0, 11)
        self.assertNotIn("tts", data["m"][0])
        self.assertNotIn("tps", data["m"][0])

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
        self.assertIsNone(metrics.avg_tts({}, "m"))
        self.assertIsNone(metrics.avg_tps({}, "m"))
        self.assertIsNone(metrics.success_rate({}, "m"))
        self.assertIsNone(metrics.full_stats({}, "m"))

    def test_tts_and_tps_aggregates(self):
        data = {"m": [
            dict(ok_entry(), tts=1.2, tps=12.0),
            dict(ok_entry(), tts=1.6, tps=8.0),
            dict(ok_entry(), tts=None),
        ]}
        self.assertEqual(metrics.avg_tts(data, "m"), 1.4)
        self.assertEqual(metrics.avg_tps(data, "m"), 10.0)
        stats = metrics.full_stats(data, "m")
        self.assertEqual(stats["avg_tts"], 1.4)
        self.assertEqual(stats["avg_tps"], 10.0)
        self.assertEqual(stats["min_tts"], 1.2)
        self.assertEqual(stats["max_tts"], 1.6)

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


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = os.path.join(self.tmp.name, "metrics.jsonl")
        self.hot = os.path.join(self.tmp.name, "metrics.json")
        for patcher in (
            mock.patch.object(metrics, "METRICS_LOG", self.log),
            mock.patch.object(metrics, "METRICS_HISTORY", self.hot),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_record_metric_appends_full_history(self):
        data = metrics.record_metric(
            {}, "m", "OK", 1.0, 2.0, 10, fingerprint="fp1", tts=1.2,
        )
        metrics.record_metric(
            data, "m", "OK", 1.0, 2.0, 10, fingerprint="fp2", tts=1.2,
        )
        history = metrics.load_history("m")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["model"], "m")
        self.assertEqual(history[1]["fp"], "fp2")

    def test_marks_fingerprint_change(self):
        data = metrics.record_metric({}, "m", "OK", 1.0, 1.0, 3, fingerprint="a")
        data = metrics.record_metric(data, "m", "OK", 1.0, 1.0, 3, fingerprint="b")
        self.assertEqual(data["m"][-1]["fp_changed"], {"from": "a", "to": "b"})

    def test_prune_history_removes_old_entries(self):
        lines = [
            {"ts": "2000-01-01 00:00", "model": "m", "status": "OK"},
            {"ts": "2999-01-01 00:00", "model": "m", "status": "OK"},
        ]
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in lines) + "\n")
        metrics.save_metrics({"m": [
            dict(lines[0]), dict(lines[1]),
        ]})
        kept, removed = metrics.prune_history(days=1)
        self.assertEqual((kept, removed), (1, 1))
        self.assertEqual(len(metrics.load_history()), 1)
        self.assertEqual(len(metrics.load_metrics()["m"]), 1)

    def test_timestamp_has_offset(self):
        data = metrics.add_metric({}, "m", "OK", 1.0, 1.0, 1)
        self.assertIsNotNone(datetime.fromisoformat(data["m"][0]["ts"]).tzinfo)

    def test_prune_history_mixed_timestamp_formats(self):
        lines = [
            {"ts": "2000-01-01T00:00:00+00:00", "model": "m", "status": "OK"},
            {"ts": "2000-01-01 00:00", "model": "m", "status": "OK"},
            {"ts": "2999-01-01T00:00:00+00:00", "model": "m", "status": "OK"},
        ]
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in lines) + "\n")
        kept, removed = metrics.prune_history(days=1)
        self.assertEqual((kept, removed), (1, 2))

    def test_prune_history_skips_null_timestamp(self):
        lines = [
            {"ts": None, "model": "m", "status": "OK"},
            {"ts": "2999-01-01 00:00", "model": "m", "status": "OK"},
        ]
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(x) for x in lines) + "\n")
        kept, removed = metrics.prune_history(days=1)
        self.assertEqual((kept, removed), (1, 1))


class AnomaliesTest(unittest.TestCase):
    def _ok(self, **kw):
        entry = dict(ok_entry(), **kw)
        return entry

    def test_requires_absolute_ttft_delta(self):
        data = {"m": [self._ok(ttft=0.1), self._ok(ttft=0.1),
                      self._ok(ttft=0.2), self._ok(ttft=0.2)]}
        types = [a["type"] for a in metrics.find_anomalies(data)]
        self.assertNotIn("ttft_spike", types)

    def test_detects_tts_spike(self):
        data = {"m": [self._ok(tts=1.0), self._ok(tts=1.0),
                      self._ok(tts=1.0), self._ok(tts=3.0)]}
        types = [a["type"] for a in metrics.find_anomalies(data)]
        self.assertIn("tts_spike", types)

    def test_detects_tps_drop(self):
        data = {"m": [self._ok(tps=20.0), self._ok(tps=20.0),
                      self._ok(tps=20.0), self._ok(tps=2.0)]}
        types = [a["type"] for a in metrics.find_anomalies(data)]
        self.assertIn("tps_drop", types)

    def test_detects_fingerprint_change(self):
        data = {"m": [
            self._ok(fp="a"), self._ok(fp="a"),
            self._ok(fp="b", fp_changed={"from": "a", "to": "b"}),
            self._ok(fp="b"),
        ]}
        found = [a for a in metrics.find_anomalies(data)
                 if a["type"] == "fingerprint_change"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["from"], "a")
        self.assertEqual(found[0]["to"], "b")


if __name__ == "__main__":
    unittest.main()