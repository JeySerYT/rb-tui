"""Тесты crash-репортера: санитайзер, отчёт, ссылка на Issue."""

import io
import os
import sys
import tempfile
import unittest
from unittest import mock

from rb_tui import crash


class SanitizeTest(unittest.TestCase):
    def test_hides_api_key(self):
        text = '{"apiKey": "sk-live-secret123"}'
        self.assertNotIn("secret123", crash.sanitize(text))

    def test_hides_bearer_token(self):
        text = "Authorization: Bearer abcdef123456789"
        self.assertNotIn("abcdef123456789", crash.sanitize(text))

    def test_hides_sk_token_anywhere(self):
        self.assertNotIn("sk-abcdef123456", crash.sanitize("ключ sk-abcdef123456"))

    def test_hides_webhook_url(self):
        text = "https://discord.com/api/webhooks/123/SECRET"
        self.assertNotIn("SECRET", crash.sanitize(text))

    def test_hides_slack_webhook_url(self):
        text = "https://hooks.slack.com/services/T00000000/B00000000/SECRET"
        self.assertNotIn("SECRET", crash.sanitize(text))

    def test_diag_masks_webhook_argument(self):
        token = "abcdef1234567890"
        url = "https://example.com/h/" + token
        with mock.patch.object(sys, "argv", ["rb-tui", "--webhook", url]):
            self.assertNotIn(token, crash.diag_block())
        with mock.patch.object(sys, "argv", ["rb-tui", "--webhook=" + url]):
            self.assertNotIn(token, crash.diag_block())

    def test_replaces_home_directory(self):
        home = os.path.expanduser("~")
        if home == "/":
            self.skipTest("домашний каталог — корень")
        self.assertTrue(crash.sanitize(home + "/project").startswith("~"))

    def test_strips_ansi(self):
        self.assertEqual(crash.sanitize("\x1b[31mred\x1b[0m"), "red")


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(crash, "CACHE", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_write_report_keeps_three(self):
        names = []
        for index in range(5):
            with mock.patch.object(
                    crash, "report_path",
                    lambda i=index: os.path.join(self.tmp.name, f"crash-{i}.log")):
                names.append(crash.write_report(f"body {index}"))
        left = sorted(n for n in os.listdir(self.tmp.name) if n.startswith("crash-"))
        self.assertEqual(len(left), crash.KEEP_REPORTS)
        self.assertIn("crash-4.log", left)

    def test_last_report_is_newest(self):
        for name in ("crash-1.log", "crash-9.log", "crash-5.log"):
            with open(os.path.join(self.tmp.name, name), "w", encoding="utf-8") as f:
                f.write("x")
        self.assertTrue(crash.last_report().endswith("crash-9.log"))

    def test_last_report_when_empty(self):
        self.assertIsNone(crash.last_report())

    def test_format_body_has_template_sections(self):
        body = crash.format_body(ValueError, ValueError("boom"))
        for heading in ("### Что случилось", "### Как повторить",
                        "### Ожидалось", "### Диагностика"):
            self.assertIn(heading, body)
        self.assertIn("ValueError: boom", body)

    def test_title_mentions_os_and_error(self):
        title = crash.issue_title(ValueError, ValueError("boom"))
        self.assertIn("ValueError", title)
        self.assertIn("boom", title)

    def test_build_url_prefills_template(self):
        url = crash.build_url("Заголовок", "тело")
        self.assertTrue(url.startswith("https://github.com/"))
        self.assertIn("/issues/new?", url)
        self.assertIn("template=bug_report.md", url)
        self.assertIn("title=", url)
        self.assertIn("body=", url)

    def test_build_url_fits_github_limit(self):
        url = crash.build_url("t", "я" * 20000)
        self.assertLessEqual(len(url), crash.MAX_URL)

    def test_diag_has_version_and_os(self):
        text = crash.diagnostics_text()
        self.assertIn("версия:", text)
        self.assertIn("ОС:", text)


class HandleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(crash, "CACHE", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_non_tty_prints_link_without_prompt(self):
        err = io.StringIO()
        with mock.patch.object(crash, "_can_prompt", return_value=False), \
                mock.patch.object(sys, "stderr", err):
            url = crash.handle(ValueError, ValueError("boom"))
        self.assertIn("отчёт:", err.getvalue())
        self.assertIn(url, err.getvalue())

    def test_prompt_opens_browser(self):
        err = io.StringIO()
        with mock.patch.object(crash, "_can_prompt", return_value=True), \
                mock.patch.object(crash, "open_issue", return_value=True) as opened, \
                mock.patch("builtins.input", return_value=""), \
                mock.patch.object(sys, "stdout", io.StringIO()), \
                mock.patch.object(sys, "stderr", err):
            crash.handle(ValueError, ValueError("boom"))
        opened.assert_called_once()

    def test_send_report_uses_saved_file(self):
        path = os.path.join(self.tmp.name, "crash-1.log")
        with open(path, "w", encoding="utf-8") as f:
            f.write("### Что случилось\n\n`ValueError: boom`\n")
        with mock.patch.object(crash, "open_issue", return_value=True) as opened:
            url = crash.send_report(path)
        opened.assert_called_once_with(url)
        self.assertIn("ValueError", url.replace("%20", " ").replace("%3A", ":"))

    def test_send_report_without_files_raises(self):
        with self.assertRaises(FileNotFoundError):
            crash.send_report()


class HookTest(unittest.TestCase):
    def tearDown(self):
        crash._installed = False

    def test_system_exit_and_keyboard_interrupt_are_ignored(self):
        crash._installed = False
        original = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", original)
        crash.install()
        hook = sys.excepthook
        with mock.patch.object(crash, "handle") as handle, \
                mock.patch.object(sys, "stderr", io.StringIO()):
            for exc_type in (SystemExit, KeyboardInterrupt):
                exc = exc_type()
                hook(exc_type, exc, None)
        handle.assert_not_called()


if __name__ == "__main__":
    unittest.main()