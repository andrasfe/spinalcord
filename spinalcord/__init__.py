"""spinalcord — a backend-agnostic sensorimotor protocol for cognitive agents.

A cognitive layer (a "brain") plans; an embodiment layer (a "body") acts.
``spinalcord`` is the conduit between them: it carries **afferent** signals
up (eyes — observe / locate / verify / read) and **efferent** signals down
(hands — click / type / key / scroll), as typed, safety-gated calls over a
pluggable backend.

The reference backend (`HandsneyesBackend`) talks to a running ``handsneyes``
Command Center over HTTP — none of handsneyes' vision / servo / model code is
duplicated here. A `FakeBackend` provides scripted, hardware-free operation so
consumers can unit-test a full observe→act→observe loop offline.

Core (`Embodiment`, `FakeBackend`, the type protocol, `SafetyGate`) imports
with **zero third-party dependencies**. `HandsneyesBackend` needs ``httpx``
(``pip install spinalcord[handsneyes]``) and is imported lazily.
"""
from __future__ import annotations

from .backends.base import Backend
from .backends.fake import FakeBackend
from .embodiment import Embodiment
from .safety import SafetyGate
from .types import (
    ActionResult,
    Frame,
    LocateResult,
    Observation,
    VerifyResult,
    VisualElement,
)

__version__ = "0.1.0"

__all__ = [
    "Embodiment",
    "Backend",
    "FakeBackend",
    "SafetyGate",
    "Frame",
    "VisualElement",
    "Observation",
    "LocateResult",
    "VerifyResult",
    "ActionResult",
    "HandsneyesBackend",  # lazy — see __getattr__
]


def __getattr__(name: str):  # PEP 562 — lazy optional backend
    if name == "HandsneyesBackend":
        # Imported lazily so the core stays dependency-free; this backend
        # needs httpx (spinalcord[handsneyes]).
        from .backends.handsneyes_cc import HandsneyesBackend

        return HandsneyesBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
