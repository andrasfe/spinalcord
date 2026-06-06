"""Backends — pluggable embodiment implementations.

`Backend` is the ABC you subclass to drive a real body. `FakeBackend` is a
scripted, hardware-free reference implementation (stdlib only) used for tests
and as a worked example of the contract.
"""
from __future__ import annotations

from .base import Backend
from .fake import FakeBackend

__all__ = ["Backend", "FakeBackend"]
