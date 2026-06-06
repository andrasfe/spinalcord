"""Protocol type tests — render_text determinism, element geometry."""
from __future__ import annotations

import unittest

from afferent.types import Observation, VisualElement


class VisualElementTests(unittest.TestCase):
    def test_center(self):
        e = VisualElement("Run", (0.80, 0.20, 0.10, 0.04), kind="button")
        cx, cy = e.center_pct()
        self.assertAlmostEqual(cx, 0.85, places=4)
        self.assertAlmostEqual(cy, 0.22, places=4)


class ObservationTests(unittest.TestCase):
    def _obs(self):
        return Observation(
            ts=123.0,
            frontmost_app="Firefox",
            cursor_pct=(0.41, 0.38),
            elements=[
                VisualElement("Sign in", (0.90, 0.05, 0.06, 0.03), kind="link"),
                VisualElement("Run", (0.80, 0.20, 0.10, 0.04), kind="button"),
                VisualElement("search", (0.30, 0.10, 0.20, 0.03), kind="field"),
            ],
            ocr_text="  the   quick brown   fox  ",
        )

    def test_render_text_is_deterministic(self):
        o = self._obs()
        a = o.render_text()
        b = o.render_text()
        self.assertEqual(a, b)

    def test_render_text_sorts_by_position(self):
        o = self._obs()
        rendered = o.render_text()
        # 'Sign in' (y=0.05) sorts before 'search' (y=0.10) before 'Run' (y=0.20)
        i_sign = rendered.index("Sign in")
        i_search = rendered.index("search")
        i_run = rendered.index("Run")
        self.assertLess(i_sign, i_search)
        self.assertLess(i_search, i_run)

    def test_render_text_collapses_ocr_whitespace(self):
        o = self._obs()
        self.assertIn("'the quick brown fox'", o.render_text())

    def test_render_includes_app_and_cursor(self):
        o = self._obs()
        r = o.render_text()
        self.assertIn("app=Firefox", r)
        self.assertIn("cursor=0.41,0.38", r)

    def test_find_substring_case_insensitive(self):
        o = self._obs()
        hits = o.find("RUN")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].label, "Run")
        self.assertEqual(o.find("nonexistent"), [])

    def test_empty_observation_renders(self):
        o = Observation(ts=0.0)
        self.assertEqual(o.render_text(), "app=?")


if __name__ == "__main__":
    unittest.main(verbosity=2)
