"""Тесты учёта бюджета в общих CLI-сценариях."""

import unittest
from unittest import mock

from rb_tui import cli, commands
from rb_tui.probe import ProbeThrottled


class ProbeBudgetTest(unittest.TestCase):
    def test_success_commits_budget(self):
        handler = mock.Mock()
        with mock.patch.object(commands, "reserve_probes", return_value=True), \
                mock.patch.object(cli.guard, "commit") as commit:
            cli._run_probe_command(3, ["m"], handler, "a", "b")
        handler.assert_called_once_with("a", "b")
        commit.assert_called_once_with(3, ["m"])

    def test_throttle_does_not_commit(self):
        def handler(*_args):
            raise ProbeThrottled("catalog_probe_detected")

        with mock.patch.object(commands, "reserve_probes", return_value=True), \
                mock.patch.object(commands, "handle_throttle"), \
                mock.patch.object(cli.guard, "commit") as commit:
            cli._run_probe_command(3, ["m"], handler, "a")
        commit.assert_not_called()
