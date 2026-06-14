"""afferent — a backend-agnostic sensorimotor protocol for cognitive agents.

A cognitive layer (a "brain") plans; an embodiment layer (a "body") acts.
``afferent`` is the conduit between them: it carries **afferent** signals
up (eyes — observe / locate / verify / read) and **efferent** signals down
(hands — click / type / key / scroll), as typed, safety-gated calls over a
pluggable `Backend`.

The package is **dependency-free** (stdlib only). It ships `FakeBackend`
(scripted, hardware-free) for tests, `MacOSBackend` (drives the host Mac via
the built-in `screencapture` + `cliclick`), and a `Backend` ABC you subclass
to drive any other body (browser automation, a VM driver, a remote HID
bridge, …). `Embodiment` wraps any backend with a `SafetyGate` and
post-action observation.
"""
from __future__ import annotations

from .backends.base import Backend, BackendUnavailable
from .backends.fake import FakeBackend
from .backends.macos import MacOSBackend
from .backends.pi_hid import GatewayClient, PiHidBackend
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

__version__ = "0.3.2"

__all__ = [
    "Embodiment",
    "Backend",
    "BackendUnavailable",
    "FakeBackend",
    "MacOSBackend",
    "PiHidBackend",
    "GatewayClient",
    "SafetyGate",
    "Frame",
    "VisualElement",
    "Observation",
    "LocateResult",
    "VerifyResult",
    "ActionResult",
]
