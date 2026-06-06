"""afferent — a backend-agnostic sensorimotor protocol for cognitive agents.

A cognitive layer (a "brain") plans; an embodiment layer (a "body") acts.
``afferent`` is the conduit between them: it carries **afferent** signals
up (eyes — observe / locate / verify / read) and **efferent** signals down
(hands — click / type / key / scroll), as typed, safety-gated calls over a
pluggable `Backend`.

The package is **dependency-free** (stdlib only). It ships one working
backend — `FakeBackend` (scripted, hardware-free) — and a `Backend` ABC you
subclass to drive a real body (browser automation, OS automation, a VM
driver, a remote HID bridge, a test harness, …). `Embodiment` wraps any
backend with a `SafetyGate` and post-action observation.
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
]
