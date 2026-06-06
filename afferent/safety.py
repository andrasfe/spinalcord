"""SafetyGate — the consumer-driven guard on every efferent action.

A cognitive consumer (e.g. an amygdala / basal-ganglia veto) drives this. It
sits *in front of* every motor action; eyes (observation) are never gated.

Defaults are SAFE: ``read_only=True`` means hands refuse until the consumer
explicitly opts in. This lets a new integration run eyes-only (zero blast
radius) and flip to acting only once its perception loop is trusted.

This is additive to whatever gates the backend itself enforces (a backend may,
for instance, refuse to type unless it visually confirms a login screen). Both
must pass.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class SafetyGate:
    read_only: bool = True
    confirm: Optional[Callable[[str], bool]] = None       # per-action veto
    allowed_apps: Optional[list] = None                   # None = any; [] = none
    max_actions_per_min: Optional[float] = 30.0           # None = unlimited
    time_fn: Callable[[], float] = time.monotonic         # injectable for tests
    _stamps: deque = field(default_factory=deque, repr=False)
    _panicked: bool = field(default=False, repr=False)

    def panic(self) -> None:
        """Latch into a refusing state. Irreversible for this gate instance."""
        self._panicked = True
        self.read_only = True

    @property
    def panicked(self) -> bool:
        return self._panicked

    def check(self, action_desc: str, app: Optional[str] = None) -> "tuple[bool, str]":
        """Return (allowed, reason). Order is chosen so a denied confirm or
        an off-allowlist app does NOT consume a rate-limit slot."""
        if self._panicked:
            return (False, "panicked")
        if self.read_only:
            return (False, "read_only")
        if self.allowed_apps is not None and app is not None and app not in self.allowed_apps:
            return (False, f"app {app!r} not in allowlist")
        if self.confirm is not None and not self.confirm(action_desc):
            return (False, "confirm_denied")
        if self.max_actions_per_min is not None:
            now = self.time_fn()
            while self._stamps and now - self._stamps[0] >= 60.0:
                self._stamps.popleft()
            if len(self._stamps) >= self.max_actions_per_min:
                return (False, "rate_limited")
            self._stamps.append(now)
        return (True, "")
