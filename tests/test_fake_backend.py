"""FakeBackend tests — scripting, advancing, recording, locate/verify."""
from __future__ import annotations

import unittest

from afferent import FakeBackend
from afferent.types import Observation, VisualElement


class FakeBackendTests(unittest.TestCase):
    def _script(self):
        s0 = Observation(ts=0.0, frontmost_app="App",
                         elements=[VisualElement("Run", (0.8, 0.2, 0.1, 0.04), kind="button")])
        s1 = Observation(ts=1.0, frontmost_app="App", ocr_text="done")
        return [s0, s1]

    def test_observe_returns_current_then_advances_on_action(self):
        be = FakeBackend(script=self._script())
        self.assertEqual(be.observe().ts, 0.0)
        be.do_click_at(0.5, 0.5, "left", 1)        # advances
        self.assertEqual(be.observe().ts, 1.0)

    def test_action_recorded(self):
        be = FakeBackend(script=self._script())
        be.do_click_at(0.8, 0.25, "left", 1)
        be.do_type_text("hello", False, True)
        self.assertEqual(be.recorded_actions[0][0], "click_at")
        self.assertEqual(be.recorded_actions[1][0], "type_text")
        self.assertEqual(be.recorded_actions[1][1]["text"], "hello")

    def test_secret_type_is_redacted_in_record(self):
        be = FakeBackend(script=self._script())
        be.do_type_text("hunter2", True, False)
        self.assertEqual(be.recorded_actions[0][1]["text"], "***")

    def test_locate_matches_scripted_element(self):
        be = FakeBackend(script=self._script())
        loc = be.locate("run")
        self.assertTrue(loc.found)
        self.assertAlmostEqual(loc.x_pct, 0.85, places=3)

    def test_locate_miss(self):
        be = FakeBackend(script=self._script())
        self.assertFalse(be.locate("nonexistent").found)

    def test_verify(self):
        be = FakeBackend(script=self._script())
        self.assertTrue(be.verify("is the Run button visible?").answer)
        self.assertFalse(be.verify("is there a giraffe?").answer)

    def test_action_result_has_grounding(self):
        be = FakeBackend(script=self._script(), default_steps=5)
        res = be.do_click_at(0.8, 0.25, "left", 1)
        self.assertTrue(res.ok)
        self.assertEqual(res.steps, 5)
        self.assertEqual(res.final_cursor_pct, (0.8, 0.25))

    def test_empty_script_is_safe(self):
        be = FakeBackend()
        self.assertEqual(be.observe().frontmost_app, None)
        self.assertTrue(be.do_key("enter").ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
