"""Тесты проб: детект защиты, остановка прогона, повторы, SSE."""

import io
import json
import unittest
import urllib.error
from unittest import mock

from rb_tui import probe


OK = ("OK", 0.5, 0.6, 0.9, 3, "", "")


class ThrottleDetectionTest(unittest.TestCase):
    def test_known_protection_errors(self):
        for msg in (
            "catalog_probe_detected",
            "token_concurrency_limit",
            "HTTP 429",
            "rate limit exceeded",
            "too many requests",
            "temporarily blocked",
        ):
            self.assertTrue(probe.is_throttle_error(msg), msg)

    def test_regular_errors_are_not_throttle(self):
        for msg in ("no_channel_for_model", "HTTP 500", "timeout", ""):
            self.assertFalse(probe.is_throttle_error(msg), msg)


class ProbeAllTest(unittest.TestCase):
    def test_stops_on_throttle_and_keeps_partial_results(self):
        calls = []

        def fake(base, key, model):
            calls.append(model)
            if model == "b":
                return "THROTTLE", None, None, 0.1, 0, "", "catalog_probe_detected"
            return OK

        with mock.patch.object(probe, "probe_with_metrics", fake), \
                mock.patch.object(probe.time, "sleep", lambda *_: None):
            with self.assertRaises(probe.ProbeThrottled) as ctx:
                probe.probe_all("x", "k", ["a", "b", "c"], delay=0)

        self.assertEqual([r[0] for r in ctx.exception.results], ["a"])
        self.assertEqual(ctx.exception.msg, "catalog_probe_detected")
        self.assertEqual(calls, ["a", "b"])  # после детекта запросов не было

    def test_budget_limits_number_of_probes(self):
        calls = []

        def fake(base, key, model):
            calls.append(model)
            return OK

        with mock.patch.object(probe, "probe_with_metrics", fake), \
                mock.patch.object(probe.time, "sleep", lambda *_: None):
            results = probe.probe_all("x", "k", ["a", "b", "c"], budget=2, delay=0)

        self.assertEqual(calls, ["a", "b"])
        self.assertEqual(len(results), 2)
        self.assertEqual(len(results[0]), 8)  # model + 7 полей пробы

    def test_sleeps_between_requests_only(self):
        sleeps = []
        with mock.patch.object(probe, "probe_with_metrics", lambda *a: OK), \
                mock.patch.object(probe.time, "sleep", sleeps.append):
            probe.probe_all("x", "k", ["a", "b", "c"], delay=1.0)
        self.assertEqual(len(sleeps), 2)


class ProbeWithMetricsTest(unittest.TestCase):
    def test_retries_transient_error(self):
        sequence = [
            ("ERR", None, None, 0.1, 0, "", "HTTP 503"),
            OK,
        ]
        with mock.patch.object(probe, "_probe_once", side_effect=sequence) as once, \
                mock.patch.object(probe.time, "sleep", lambda *_: None):
            result = probe.probe_with_metrics("x", "k", "m", retries=1)
        self.assertEqual(result[0], "OK")
        self.assertEqual(once.call_count, 2)

    def test_does_not_retry_protection(self):
        with mock.patch.object(
            probe, "_probe_once",
            return_value=("THROTTLE", None, None, 0.1, 0, "", "catalog_probe_detected"),
        ) as once, mock.patch.object(probe.time, "sleep", lambda *_: None):
            result = probe.probe_with_metrics("x", "k", "m", retries=3)
        self.assertEqual(result[0], "THROTTLE")
        self.assertEqual(once.call_count, 1)

    def test_does_not_retry_model_errors(self):
        with mock.patch.object(
            probe, "_probe_once",
            return_value=("ERR", None, None, 0.1, 0, "", "no_channel_for_model"),
        ) as once, mock.patch.object(probe.time, "sleep", lambda *_: None):
            probe.probe_with_metrics("x", "k", "m", retries=3)
        self.assertEqual(once.call_count, 1)


class ReadStreamTest(unittest.TestCase):
    def test_parses_ttft_tts_usage(self):
        lines = [
            b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n',
            b'data: {"choices":[{"delta":{"content":"o"}}]}\n',
            b'data: {"choices":[{"delta":{"content":"k"}}]}\n',
            b'data: {"choices":[],"usage":{"total_tokens":5}}\n',
            b'data: [DONE]\n',
        ]
        clock = iter([10.0, 10.2, 10.9])
        with mock.patch.object(probe.time, "monotonic", side_effect=lambda: next(clock)):
            ttft, tts, total, tokens = probe._read_stream(lines, 0.0)

        self.assertEqual(ttft, 10.0)
        self.assertEqual(tts, 10.2)
        self.assertEqual(total, 10.9)
        self.assertEqual(tokens, 2)  # контент-чанки, без usage промпта

    def test_falls_back_when_stream_unsupported(self):
        class FakeResponse:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"ok"}}],"usage":{"total_tokens":4}}'

        payloads = []
        error = urllib.error.HTTPError(
            "http://x", 400, "Bad Request", {},
            io.BytesIO(b'{"error":{"message":"stream is not supported"}}'),
        )

        def fake_urlopen(req, timeout=30):
            payloads.append(json.loads(req.data))
            if len(payloads) == 1:
                raise error
            return FakeResponse()

        with mock.patch.object(probe.urllib.request, "urlopen", fake_urlopen):
            status, ttft, tts, total, tokens, fp, msg = probe._probe_once("http://x", "k", "m")

        self.assertEqual(status, "OK")
        self.assertTrue(payloads[0].get("stream"))
        self.assertNotIn("stream", payloads[1])
        self.assertIsNone(tts)
        self.assertEqual(tokens, 4)
        self.assertEqual(msg, "")
        error.close()


if __name__ == "__main__":
    unittest.main()