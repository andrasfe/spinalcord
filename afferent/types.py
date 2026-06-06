"""The sensorimotor protocol — typed results, stdlib only.

These dataclasses are the contract between a cognitive consumer and any
backend. They are intentionally small and JSON-friendly so an HTTP backend
can construct them from a response body and a fake backend can be scripted
with literals.

All screen coordinates are ``pct`` — fractions in ``[0.0, 1.0]`` with a
top-left origin. This keeps them resolution-independent, which matters when a
consumer uses them as keys in a learned world model across machines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class Frame:
    """A captured image of the target screen."""

    id: str                       # stable id (frame sequence / path stem)
    ts: float                     # capture time (epoch seconds)
    width: int = 0                # pixels (0 if unknown)
    height: int = 0
    path: Optional[str] = None    # local path if persisted, else None


@dataclass
class VisualElement:
    """A thing detected on screen (OCR text, a button, an icon, a field)."""

    label: str                                            # OCR text / detector label
    bounds_pct: Tuple[float, float, float, float]          # x, y, w, h in [0,1]
    confidence: float = 1.0
    kind: str = "unknown"                                  # text|button|icon|field|unknown

    def center_pct(self) -> Tuple[float, float]:
        x, y, w, h = self.bounds_pct
        return (x + w / 2.0, y + h / 2.0)


@dataclass
class Observation:
    """One snapshot of perceptual state. The afferent payload."""

    ts: float
    frame: Optional[Frame] = None
    frontmost_app: Optional[str] = None       # may be None (e.g. webcam targets)
    elements: list = field(default_factory=list)   # list[VisualElement]
    ocr_text: Optional[str] = None            # set only when OCR requested
    cursor_pct: Optional[Tuple[float, float]] = None

    def find(self, label_substr: str) -> list:
        """Case-insensitive substring match over element labels."""
        q = (label_substr or "").lower()
        return [e for e in self.elements if q and q in (e.label or "").lower()]

    def render_text(self, limit: int = 40) -> str:
        """A STABLE, compact, embeddable description of this screen.

        Determinism is a hard requirement: the same Observation must render to
        a byte-identical string every call (consumers embed this and use it as
        a world-model key). Elements are sorted by (y, x, label).
        """
        parts = [f"app={self.frontmost_app or '?'}"]
        if self.cursor_pct is not None:
            parts.append(f"cursor={self.cursor_pct[0]:.2f},{self.cursor_pct[1]:.2f}")
        els = sorted(
            self.elements,
            key=lambda e: (round(e.bounds_pct[1], 3), round(e.bounds_pct[0], 3), e.label),
        )[:limit]
        if els:
            rendered = " ".join(
                f"[{e.kind} {e.label!r}@{e.center_pct()[0]:.2f},{e.center_pct()[1]:.2f}]"
                for e in els
            )
            parts.append("visible: " + rendered)
        if self.ocr_text:
            txt = " ".join(self.ocr_text.split())[:200]
            parts.append(f"text: {txt!r}")
        return "; ".join(parts)


@dataclass
class LocateResult:
    """Result of asking 'where is <description> on screen?'"""

    found: bool
    x_pct: Optional[float] = None
    y_pct: Optional[float] = None
    bounds_pct: Optional[Tuple[float, float, float, float]] = None
    confidence: float = 0.0
    reason: str = ""


@dataclass
class VerifyResult:
    """Result of a visual yes/no question ('is a login screen showing?')."""

    answer: bool
    confidence: float = 0.0
    reason: str = ""

    def __bool__(self) -> bool:
        return self.answer


@dataclass
class ActionResult:
    """Outcome of an efferent (motor) action.

    Superset of a backend's native outcome plus *grounding* fields a consumer
    needs for predictive coding and learned world models: the visual-servo
    ``steps`` it took, wall-clock ``duration_ms``, the final cursor position,
    and frame ids / a post-action observation bracketing the action.
    """

    ok: bool
    action: str                              # canonical, e.g. "click_at(0.80,0.20)"
    reason: str = ""
    refused: bool = False                    # blocked by the SafetyGate
    refusal_reason: Optional[str] = None
    # grounding
    steps: Optional[int] = None              # visual-servo iterations, if any
    duration_ms: Optional[float] = None
    final_cursor_pct: Optional[Tuple[float, float]] = None
    frame_before: Optional[str] = None       # Frame.id
    frame_after: Optional[str] = None        # Frame.id
    state_after: Optional[Observation] = None

    def __bool__(self) -> bool:
        return self.ok
