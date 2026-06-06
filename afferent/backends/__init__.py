"""Backends — pluggable embodiment implementations.

`Backend` is the ABC you subclass to drive a real body. `FakeBackend` is a
scripted, hardware-free reference implementation (stdlib only) used for tests
and as a worked example of the contract. `MacOSBackend` drives the host Mac
via built-in `screencapture` + `cliclick`.
"""
from __future__ import annotations

from .base import Backend
from .fake import FakeBackend
from .macos import MacOSBackend

__all__ = ["Backend", "FakeBackend", "MacOSBackend"]
