"""Тесты защиты от лимитов API: бюджет, ротация, cooldown."""

import os
import tempfile
import unittest
from unittest import mock

from rb_tui import guard


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = os.path.join(self.tmp.name, "probe-state.json")
        patcher = mock.patch.object(guard, "PROBE_STATE", self.state_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_when_state_missing(self):
        state = guard.load_state()
        self.assertEqual(state["cooldown_until"], 0)
        self.assertEqual(state["last_probe"], {})
        self.assertEqual(state["day_probes"], 0)

    def test_corrupt_state_falls_back_to_defaults(self):
        with open(self.state_path, "w", encoding="utf-8") as f:
            f.write("{это не json")
        state = guard.load_state()
        self.assertEqual(state["total_probes"], 0)
        self.assertEqual(state["last_probe"], {})

    def test_rotation_prefers_unprobed_models(self):
        live = ["a", "b", "c", "d", "e"]
        first = guard.pick_targets(live, budget=2)
        self.assertEqual(first, ["a", "b"])
        guard.mark_probed(first)

        second = guard.pick_targets(live, budget=2)
        self.assertEqual(second, ["c", "d"])
        self.assertFalse(set(first) & set(second))
        guard.mark_probed(second)

        self.assertEqual(guard.pick_targets(live, budget=2), ["e", "a"])

    def test_budget_never_exceeds_available_models(self):
        self.assertEqual(guard.pick_targets(["only"], budget=10), ["only"])

    def test_daily_limit_and_clamp(self):
        with mock.patch.object(guard, "DEFAULT_DAILY_BUDGET", 2):
            guard.mark_probed(["a", "b"])
            self.assertEqual(guard.daily_remaining(), 0)
            self.assertEqual(guard.clamp_budget(10), 0)

    def test_reserve_counts_every_request(self):
        ok, msg = guard.reserve(3, ["a"])
        self.assertTrue(ok, msg)
        self.assertEqual(guard.daily_used(), 3)
        self.assertEqual(guard.load_state()["total_probes"], 3)
        self.assertIn("a", guard.load_state()["last_probe"])

    def test_can_reserve_does_not_spend_until_commit(self):
        ok, msg = guard.can_reserve(3)
        self.assertTrue(ok, msg)
        self.assertEqual(guard.daily_used(), 0)
        guard.commit(3, ["a"])
        self.assertEqual(guard.daily_used(), 3)
        self.assertIn("a", guard.load_state()["last_probe"])

    def test_reserve_refuses_over_daily_limit_without_spending(self):
        with mock.patch.object(guard, "DEFAULT_DAILY_BUDGET", 2):
            ok, msg = guard.reserve(3, ["a"])
        self.assertFalse(ok)
        self.assertIn("лимит", msg)
        self.assertEqual(guard.daily_used(), 0)

    def test_reserve_refuses_during_cooldown(self):
        guard.set_cooldown(60, "catalog_probe_detected")
        ok, msg = guard.reserve(1, ["a"])
        self.assertFalse(ok)
        self.assertIn("паузе", msg)
        self.assertEqual(guard.daily_used(), 0)

    def test_daily_counter_resets_on_new_day(self):
        guard.mark_probed(["a"])
        state = guard.load_state()
        state["day"] = "2000-01-01"
        state["day_probes"] = 99
        guard.save_state(state)
        self.assertEqual(guard.daily_used(), 0)

    def test_cooldown_roundtrip(self):
        self.assertIsNone(guard.cooldown_status_line())
        guard.set_cooldown(60, "catalog_probe_detected")
        line = guard.cooldown_status_line()
        self.assertIsNotNone(line)
        self.assertIn("паузе", line)
        self.assertGreater(guard.cooldown_remaining(), 0)
        guard.clear_cooldown()
        self.assertIsNone(guard.cooldown_status_line())

    def test_human_left(self):
        self.assertEqual(guard.human_left(30), "30 сек")
        self.assertEqual(guard.human_left(120), "2 мин")
        self.assertEqual(guard.human_left(3660), "1 ч 1 мин")

    def test_jitter_stays_within_bounds(self):
        for _ in range(20):
            value = guard.jitter(3.0)
            self.assertGreaterEqual(value, 3.0)
            self.assertLessEqual(value, 3.0 + 1.2 + 1e-9)


if __name__ == "__main__":
    unittest.main()