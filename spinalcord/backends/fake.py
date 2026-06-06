"""FakeBackend — scripted, hardware-free. The offline-test substrate.

Feed it a list of `Observation`s. ``observe()`` returns the current one;
each successful action advances to the next (modeling "the screen changed").
Actions are recorded in ``recorded_actions`` for assertions. Touches no
network and no hardware, needs nothing beyond stdlib.

    obs0 = Observation(ts=0, elements=[VisualElement("Run", (0.8,0.2,0.05,0.03), kind="button")])
    obs1 = Observation(ts=1, frontmost_app="App")
    be = FakeBackend(script=[obs0, obs1])
    em = Embodiment(be, read_only=False)
    em.click("Run")                 # locate→click_at; advances to obs1
    assert be.recorded_actions[0][0] == "click_at"
"""
from __future__ import annotations

from typing import Optional

from ..types import ActionResult, Frame, LocateResult, Observation, VerifyResult
from .base import Backend


class FakeBackend(Backend):
    name = "fake"

    def __init__(self, script: Optional[list] = None, *,
                 default_steps: int = 3,
                 default_duration_ms: float = 120.0,
                 capabilities: Optional[set] = None):
        self._script = list(script or [])
        self._idx = 0
        self.recorded_actions: list = []
        self._default_steps = default_steps
        self._default_duration_ms = default_duration_ms
        self._caps = capabilities or {
            "pixels", "ocr", "locate", "verify", "click", "type", "key", "scroll",
        }

    # ── script cursor ────────────────────────────────────────────────────────
    def _current(self) -> Optional[Observation]:
        if not self._script:
            return None
        return self._script[min(self._idx, len(self._script) - 1)]

    def _advance(self) -> None:
        if self._idx < len(self._script) - 1:
            self._idx += 1

    # ── meta ──────────────────────────────────────────────────────────────────
    def capabilities(self) -> set:
        return set(self._caps)

    def health(self) -> bool:
        return True

    def frontmost_app(self) -> Optional[str]:
        o = self._current()
        return o.frontmost_app if o else None

    # ── eyes ──────────────────────────────────────────────────────────────────
    def observe(self, *, ocr: bool = False, locate: Optional[list] = None) -> Observation:
        o = self._current()
        if o is None:
            return Observation(ts=0.0)
        return o

    def screenshot(self) -> Frame:
        o = self._current()
        if o and o.frame:
            return o.frame
        return Frame(id=f"fake-{self._idx}", ts=0.0)

    def locate(self, description: str) -> LocateResult:
        o = self._current()
        if o:
            hits = o.find(description)
            if hits:
                cx, cy = hits[0].center_pct()
                return LocateResult(True, cx, cy, hits[0].bounds_pct,
                                    hits[0].confidence, f"matched {hits[0].label!r}")
        return LocateResult(False, reason="no match in scripted observation")

    def verify(self, question: str) -> VerifyResult:
        o = self._current()
        if o:
            ql = question.lower()
            for e in o.elements:
                if e.label and e.label.lower() in ql:
                    return VerifyResult(True, e.confidence, f"saw {e.label!r}")
        return VerifyResult(False, 0.5, "not found in scripted observation")

    def read_text(self, region_pct: Optional[tuple] = None) -> str:
        o = self._current()
        return (o.ocr_text or "") if o else ""

    # ── hands ─────────────────────────────────────────────────────────────────
    def _record(self, verb: str, **kw) -> ActionResult:
        self.recorded_actions.append((verb, kw))
        self._advance()
        canonical = verb + "(" + ",".join(f"{k}={v}" for k, v in kw.items()) + ")"
        return ActionResult(
            ok=True, action=canonical, reason="fake",
            steps=self._default_steps, duration_ms=self._default_duration_ms,
        )

    def do_click_at(self, x_pct, y_pct, button, count) -> ActionResult:
        res = self._record("click_at", x_pct=round(x_pct, 4), y_pct=round(y_pct, 4),
                           button=button, count=count)
        res.final_cursor_pct = (x_pct, y_pct)
        return res

    def do_move_to(self, x_pct, y_pct) -> ActionResult:
        res = self._record("move_to", x_pct=round(x_pct, 4), y_pct=round(y_pct, 4))
        res.final_cursor_pct = (x_pct, y_pct)
        return res

    def do_type_text(self, text, secret, append_enter) -> ActionResult:
        shown = "***" if secret else text
        return self._record("type_text", text=shown, append_enter=append_enter)

    def do_key(self, combo) -> ActionResult:
        return self._record("key", combo=combo)

    def do_scroll(self, amount, at_pct) -> ActionResult:
        return self._record("scroll", amount=amount, at_pct=at_pct)
