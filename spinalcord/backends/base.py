"""Backend ABC — the extension point.

A backend implements the raw sensorimotor primitives. It does NOT implement
safety gating — `Embodiment` applies the `SafetyGate` before calling any
``do_*`` method, and fills ``state_after`` by calling ``observe()`` itself.
So a backend only worries about "how do I actually see / move", never "should
I".

Eyes methods (``observe`` / ``screenshot`` / ``locate`` / ``verify`` /
``read_text``) have no side effects and are always callable.

Efferent methods are named ``do_*`` to make it obvious they are the
unguarded primitives. They should return an `ActionResult` and must not raise
for ordinary failures (return ``ok=False`` instead); they may raise
`BackendUnavailable` when the underlying transport is unreachable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..types import ActionResult, Frame, LocateResult, Observation, VerifyResult


class BackendUnavailable(RuntimeError):
    """Raised when the backend's transport (HTTP service, device) is down."""


class Backend(ABC):
    name: str = "backend"

    # ── meta ────────────────────────────────────────────────────────────────
    @abstractmethod
    def capabilities(self) -> set:
        """Subset of {'pixels','ocr','locate','verify','click','type','key','scroll'}."""

    def health(self) -> bool:
        """True if the backend is ready to use right now."""
        return True

    def frontmost_app(self) -> Optional[str]:
        """Best-effort frontmost app id/name, or None if unknown."""
        return None

    # ── eyes (afferent — no side effects) ────────────────────────────────────
    @abstractmethod
    def observe(self, *, ocr: bool = False, locate: Optional[list] = None) -> Observation:
        ...

    def screenshot(self) -> Frame:
        obs = self.observe()
        return obs.frame or Frame(id="none", ts=0.0)

    def locate(self, description: str) -> LocateResult:
        return LocateResult(False, reason="locate not supported by this backend")

    def verify(self, question: str) -> VerifyResult:
        return VerifyResult(False, reason="verify not supported by this backend")

    def read_text(self, region_pct: Optional[tuple] = None) -> str:
        return ""

    # ── hands (efferent — raw, unguarded; Embodiment gates these) ────────────
    @abstractmethod
    def do_click_at(self, x_pct: float, y_pct: float, button: str, count: int) -> ActionResult:
        ...

    def do_move_to(self, x_pct: float, y_pct: float) -> ActionResult:
        return ActionResult(False, "move_to", reason="move_to not supported")

    @abstractmethod
    def do_type_text(self, text: str, secret: bool, append_enter: bool) -> ActionResult:
        ...

    @abstractmethod
    def do_key(self, combo: str) -> ActionResult:
        ...

    def do_scroll(self, amount: int, at_pct: Optional[tuple]) -> ActionResult:
        return ActionResult(False, "scroll", reason="scroll not supported")

    def close(self) -> None:
        pass
