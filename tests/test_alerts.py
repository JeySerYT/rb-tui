"""Тесты уведомлений: дедупликация, форматы вебхука, повторы."""

import os
import tempfile
import unittest
from unittest import mock

from rb_tui import alerts, metrics


def ok_entry(**kw):
    base = {"ts": "2026-01-01 00:00", "status": "OK", "ttft": 1.0,
            "total_time": 1.0, "tokens": 3}
    base.update(kw)
    return base


class AlertsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(
            alerts, "ALERTS_STATE", os.path.join(self.tmp.name, "alerts.json"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dedup_window(self):
        self.assertTrue(alerts._should_notify("k", hours=1))
        self.assertFalse(alerts._should_notify("k", hours=1))
        self.assertTrue(alerts._should_notify("other", hours=1))

    def test_notify_anomalies_is_deduplicated(self):
        data = {"m": [
            ok_entry(ttft=1.0), ok_entry(ttft=1.0),
            ok_entry(ttft=1.0), ok_entry(ttft=5.0),
        ]}
        with mock.patch.object(alerts, "desktop_notify") as notify:
            alerts.notify_anomalies(data)
            alerts.notify_anomalies(data)
        self.assertEqual(notify.call_count, 1)

    def test_webhook_formats_have_text(self):
        data = {"m": [ok_entry()]}
        for fmt in ("slack", "discord", "generic"):
            payload = alerts.build_webhook_payload(data, fmt=fmt)
            self.assertIsInstance(payload.get("text") or payload.get("content"), str)
        self.assertIn("blocks", alerts.build_webhook_payload(data, fmt="slack"))

    def test_webhook_format_detection(self):
        self.assertEqual(alerts.webhook_format("https://hooks.slack.com/x"), "slack")
        self.assertEqual(alerts.webhook_format("https://discord.com/api/webhooks/x"), "discord")
        self.assertEqual(alerts.webhook_format("https://example.com/hook"), "generic")

    def test_send_webhook_retries(self):
        calls = []

        def fake_urlopen(req, timeout=10):
            calls.append(req)
            if len(calls) < 3:
                raise OSError("network")
            return mock.MagicMock()

        with mock.patch.object(alerts.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(alerts.time, "sleep", lambda *_: None):
            ok = alerts.send_webhook("https://example.com", {"text": "x"}, retries=2)
        self.assertTrue(ok)
        self.assertEqual(len(calls), 3)

    def test_success_drop_uses_percentages(self):
        data = {"m": [ok_entry() for _ in range(5)]
                      + [ok_entry(status="ERR") for _ in range(5)]}
        text = alerts.build_webhook_payload(data, fmt="generic")["text"]
        self.assertIn("success 100.0% → 0.0%", text)

        with mock.patch.object(alerts, "desktop_notify") as notify:
            alerts.notify_anomalies(data)
        self.assertIn("100.0% → 0.0%", notify.call_args.args[1])

    def test_fingerprint_anomaly_has_message(self):
        data = {"m": [
            ok_entry(fp="a"), ok_entry(fp="a"),
            ok_entry(fp="b", fp_changed={"from": "a", "to": "b"}),
            ok_entry(fp="b"),
        ]}
        with mock.patch.object(alerts, "desktop_notify") as notify:
            alerts.notify_anomalies(data)
        self.assertIn("fingerprint", notify.call_args.args[1].lower())


class DesktopNotifyTest(unittest.TestCase):
    def test_dispatch_by_os(self):
        with mock.patch.object(alerts, "_notify_windows", return_value=True) as win, \
                mock.patch.object(alerts, "_notify_macos", return_value=True) as mac, \
                mock.patch.object(alerts, "_notify_linux", return_value=True) as lin:
            alerts.desktop_notify("t", "m", system="Windows")
            alerts.desktop_notify("t", "m", system="Darwin")
            alerts.desktop_notify("t", "m", system="Linux")
        win.assert_called_once()
        mac.assert_called_once()
        lin.assert_called_once()

    def test_hint_differs_per_os(self):
        hints = {alerts.notify_hint(name) for name in ("Windows", "Darwin", "Linux")}
        self.assertEqual(len(hints), 3)

    def test_macos_passes_text_as_arguments(self):
        with mock.patch.object(alerts.shutil, "which", return_value="/usr/bin/osascript"), \
                mock.patch.object(alerts, "_run", return_value=True) as run:
            self.assertTrue(alerts._notify_macos("t", "m", "normal"))
        args = run.call_args.args[0]
        self.assertEqual(args[0], "osascript")
        self.assertEqual(args[-2:], ["t", "m"])

    def test_macos_without_osascript_fails(self):
        with mock.patch.object(alerts.shutil, "which", return_value=None):
            self.assertFalse(alerts._notify_macos("t", "m", "normal"))

    def test_windows_passes_text_via_env(self):
        with mock.patch.object(alerts.shutil, "which", return_value="powershell"), \
                mock.patch.object(alerts, "_run", return_value=True) as run:
            alerts._notify_windows("Заголовок", "Текст", "normal")
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["RB_TUI_NOTIFY_TITLE"], "Заголовок")
        self.assertEqual(env["RB_TUI_NOTIFY_MESSAGE"], "Текст")


if __name__ == "__main__":
    unittest.main()