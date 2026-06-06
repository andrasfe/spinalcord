"""Backends — pluggable embodiment implementations.

`FakeBackend` is always available (stdlib only). `HandsneyesBackend` needs
httpx and is imported lazily from the top-level package
(`spinalcord.HandsneyesBackend`) so the core stays dependency-free.
"""
from __future__ import annotations

from .base import Backend
from .fake import FakeBackend

__all__ = ["Backend", "FakeBackend"]
