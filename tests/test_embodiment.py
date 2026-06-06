"""Embodiment + SafetyGate tests — gating, observe-after, click-by-locate, panic."""
from __future__ import annotations

import itertools
import unittest

from spinalcord import Embodiment, FakeBackend, SafetyGate
from spinalcord.types import Observation, VisualElement


def _script():
    s0 = Observation(ts=0.0, frontmost_app="Firefox",
                     elements=[VisualElement("Run", (0.8, 0.2, 0.1, 0.04), kind="button")])
    s1 = Observation(ts=1.0, frontmost_app="Firefox", ocr_text="ran")
    return [s0, s1]


class ReadOnlyTests(unittest.TestCase):
    def test_default_is_read_only(self):
        em = Embodiment(FakeBackend(script=_script()))   # default read_only=True
        res = em.click_at(0.5, 0.5)
        self.assertFalse(res.ok)
        self.assertTrue(res.refused)
        self.assertEqual(res.refusal_reason, "read_only")

    def test_eyes_work_under_read_only(self):
        em = Embodiment(FakeBackend(script=_script()))
        self.assertEqual(em.observe().frontmost_app, "Firefox")
        self.assertTrue(em.locate("Run").found)
        self.assertTrue(em.verify("is Run visible?").answer)


class ActingTests(unittest.TestCase):
    def test_click_at_acts_when_not_read_only(self):
        be = FakeBackend(script=_script())
        em = Embodiment.fake(script=_script())  # read_only=False, settle=0
        em.backend = be
        res = em.click_at(0.8, 0.25)
        self.assertTrue(res.ok)
        self.assertEqual(be.recorded_actions[0][0], "click_at")

    def test_observe_after_attaches_state(self):
        em = Embodiment.fake(script=_script())
        res = em.click_at(0.8, 0.25)              # advances script to s1
        self.assertIsNotNone(res.state_after)
        self.assertEqual(res.state_after.ts, 1.0)

    def test_click_by_description_locates_then_clicks(self):
        be = FakeBackend(script=_script())
        em = Embodiment(be, read_only=False, settle_ms=0)
        res = em.click("Run")
        self.assertTrue(res.ok)
        verb, kw = be.recorded_actions[0]
        self.assertEqual(verb, "click_at")
        self.assertAlmostEqual(kw["x_pct"], 0.85, places=2)

    def test_click_by_description_miss_does_not_act(self):
        be = FakeBackend(script=_script())
        em = Embodiment(be, read_only=False, settle_ms=0)
        res = em.click("nonexistent")
        self.assertFalse(res.ok)
        self.assertEqual(be.recorded_actions, [])


class ConfirmTests(unittest.TestCase):
    def test_confirm_denial_refuses(self):
        be = FakeBackend(script=_script())
        em = Embodiment(be, read_only=False, settle_ms=0, confirm=lambda desc: False)
        res = em.click_at(0.5, 0.5)
        self.assertTrue(res.refused)
        self.assertEqual(res.refusal_reason, "confirm_denied")
        self.assertEqual(be.recorded_actions, [])

    def test_confirm_sees_action_description(self):
        seen = []
        be = FakeBackend(script=_script())
        em = Embodiment(be, read_only=False, settle_ms=0,
                        confirm=lambda desc: seen.append(desc) or True)
        em.key("cmd+c")
        self.assertTrue(any("key(cmd+c)" in s for s in seen))


class AllowlistTests(unittest.TestCase):
    def test_allowlist_blocks_other_apps(self):
        be = FakeBackend(script=_script())          # frontmost = Firefox
        em = Embodiment(be, read_only=False, settle_ms=0, allowed_apps=["Terminal"])
        res = em.click_at(0.5, 0.5)
        self.assertTrue(res.refused)
        self.assertIn("allowlist", res.refusal_reason)

    def test_allowlist_permits_listed_app(self):
        be = FakeBackend(script=_script())
        em = Embodiment(be, read_only=False, settle_ms=0, allowed_apps=["Firefox"])
        self.assertTrue(em.click_at(0.5, 0.5).ok)


class RateLimitTests(unittest.TestCase):
    def test_rate_limit_refuses_after_budget(self):
        clock = itertools.count(0, 1)  # 0,1,2,... seconds — all within 60s window
        gate = SafetyGate(read_only=False, max_actions_per_min=3,
                          time_fn=lambda: next(clock))
        be = FakeBackend(script=[Observation(ts=0.0)] * 10)
        em = Embodiment(be, settle_ms=0, gate=gate)
        oks = [em.key("a").ok for _ in range(5)]
        self.assertEqual(oks.count(True), 3)
        self.assertEqual(oks.count(False), 2)


class PanicTests(unittest.TestCase):
    def test_panic_latches_read_only(self):
        be = FakeBackend(script=_script())
        em = Embodiment(be, read_only=False, settle_ms=0)
        self.assertTrue(em.click_at(0.5, 0.5).ok)
        em.panic()
        res = em.click_at(0.5, 0.5)
        self.assertTrue(res.refused)
        self.assertEqual(res.refusal_reason, "panicked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
