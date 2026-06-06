"""Embodiment — the facade a cognitive consumer holds.

Wraps a `Backend` with a `SafetyGate`. Eyes pass straight through (no blast
radius). Hands run through the gate first; on approval they call the backend's
raw ``do_*`` primitive and then — unless told otherwise — take a fresh
observation so the returned `ActionResult` is bracketed by before/after state
(the grounding a consumer's predictive-coding / world-model machinery wants).

Synchronous on purpose: consumers' main loops are typically sync. Any async
in a backend's transport is its own concern.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from .backends.base import Backend
from .backends.fake import FakeBackend
from .safety import SafetyGate
from .types import ActionResult, Frame, LocateResult, Observation, VerifyResult


class Embodiment:
    def __init__(self, backend: Backend, *,
                 read_only: bool = True,
                 confirm: Optional[Callable[[str], bool]] = None,
                 allowed_apps: Optional[list] = None,
                 max_actions_per_min: Optional[float] = 30.0,
                 settle_ms: int = 400,
                 observe_after: bool = True,
                 gate: Optional[SafetyGate] = None):
        self.backend = backend
        self.settle_ms = settle_ms
        self.observe_after_default = observe_after
        self.gate = gate or SafetyGate(
            read_only=read_only,
            confirm=confirm,
            allowed_apps=allowed_apps,
            max_actions_per_min=max_actions_per_min,
        )

    # ── convenience constructors ─────────────────────────────────────────────
    @classmethod
    def fake(cls, script: Optional[list] = None, *, read_only: bool = False,
             settle_ms: int = 0, **kw) -> "Embodiment":
        """An offline embodiment over a scripted FakeBackend. Defaults to
        ``read_only=False`` and ``settle_ms=0`` so tests can act immediately
        without sleeping."""
        return cls(FakeBackend(script=script), read_only=read_only,
                   settle_ms=settle_ms, **kw)

    @classmethod
    def macos(cls, *, capture_dir: Optional[str] = None, **kw) -> "Embodiment":
        """A live embodiment over the host Mac (screencapture + cliclick).
        Defaults to ``read_only=True`` (eyes only) like the base constructor —
        opt into hands explicitly with ``read_only=False``."""
        from .backends.macos import MacOSBackend
        return cls(MacOSBackend(capture_dir=capture_dir), **kw)

    # ── meta ──────────────────────────────────────────────────────────────────
    def capabilities(self) -> set:
        return self.backend.capabilities()

    def health(self) -> bool:
        return self.backend.health()

    def panic(self) -> None:
        self.gate.panic()

    def close(self) -> None:
        self.backend.close()

    # ── eyes (never gated) ────────────────────────────────────────────────────
    def observe(self, *, ocr: bool = False, locate: Optional[list] = None) -> Observation:
        return self.backend.observe(ocr=ocr, locate=locate)

    def screenshot(self) -> Frame:
        return self.backend.screenshot()

    def locate(self, description: str) -> LocateResult:
        return self.backend.locate(description)

    def verify(self, question: str) -> VerifyResult:
        return self.backend.verify(question)

    def read_text(self, region_pct: Optional[tuple] = None) -> str:
        return self.backend.read_text(region_pct)

    # ── hands (gated) ──────────────────────────────────────────────────────────
    def _gated(self, desc: str, run: Callable[[], ActionResult],
               observe_after: Optional[bool]) -> ActionResult:
        app = self.backend.frontmost_app()
        allowed, reason = self.gate.check(desc, app=app)
        if not allowed:
            return ActionResult(ok=False, action=desc, reason=reason,
                                refused=True, refusal_reason=reason)
        frame_before = None
        try:
            fb = self.backend.screenshot()
            frame_before = fb.id if fb else None
        except Exception:
            pass
        res = run()
        if res.frame_before is None:
            res.frame_before = frame_before
        return self._post(res, observe_after)

    def _post(self, res: ActionResult, observe_after: Optional[bool]) -> ActionResult:
        do_observe = self.observe_after_default if observe_after is None else observe_after
        if res.ok and do_observe:
            if self.settle_ms > 0:
                time.sleep(self.settle_ms / 1000.0)
            try:
                obs = self.backend.observe()
                res.state_after = obs
                res.frame_after = obs.frame.id if obs.frame else None
            except Exception:
                pass
        return res

    def click_at(self, x_pct: float, y_pct: float, *, button: str = "left",
                 count: int = 1, observe_after: Optional[bool] = None) -> ActionResult:
        desc = f"click_at({x_pct:.3f},{y_pct:.3f},button={button},count={count})"
        return self._gated(desc, lambda: self.backend.do_click_at(x_pct, y_pct, button, count),
                           observe_after)

    def click(self, description: str, *, button: str = "left", count: int = 1,
              observe_after: Optional[bool] = None) -> ActionResult:
        """Locate a described target, then click its center."""
        loc = self.backend.locate(description)
        if not loc.found or loc.x_pct is None:
            return ActionResult(ok=False, action=f"click({description!r})",
                                reason=f"locate failed: {loc.reason}")
        return self.click_at(loc.x_pct, loc.y_pct, button=button, count=count,
                             observe_after=observe_after)

    def move_to(self, x_pct: float, y_pct: float,
                observe_after: Optional[bool] = None) -> ActionResult:
        desc = f"move_to({x_pct:.3f},{y_pct:.3f})"
        return self._gated(desc, lambda: self.backend.do_move_to(x_pct, y_pct), observe_after)

    def type_text(self, text: str, *, secret: bool = False, append_enter: bool = False,
                  observe_after: Optional[bool] = None) -> ActionResult:
        shown = f"<{len(text)} chars>" if secret else text[:40]
        desc = f"type_text({shown!r},append_enter={append_enter})"
        return self._gated(desc, lambda: self.backend.do_type_text(text, secret, append_enter),
                           observe_after)

    def key(self, combo: str, observe_after: Optional[bool] = None) -> ActionResult:
        desc = f"key({combo})"
        return self._gated(desc, lambda: self.backend.do_key(combo), observe_after)

    def scroll(self, amount: int, *, at_pct: Optional[tuple] = None,
               observe_after: Optional[bool] = None) -> ActionResult:
        desc = f"scroll({amount},at={at_pct})"
        return self._gated(desc, lambda: self.backend.do_scroll(amount, at_pct), observe_after)
