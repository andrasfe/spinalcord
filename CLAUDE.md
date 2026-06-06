# CLAUDE.md

Guidance for AI agents (and humans) working in this repository.
**This file is yours to edit** — keep it current as the code changes. If you
add a backend, change the protocol, or alter the release flow, update the
relevant section here in the same change.

## What this is

`spinalcord` is a **backend-agnostic sensorimotor protocol**: the typed,
safety-gated seam between a cognitive layer ("brain", the planner) and an
embodiment layer ("body", the backend). Afferent signals go up (eyes:
`observe` / `locate` / `verify` / `read_text`); efferent signals go down
(hands: `click` / `type_text` / `key` / `scroll`).

It is a standalone library — no ties to any particular body or planner. The
package is **stdlib-only** (zero runtime dependencies). It is published to
PyPI as `spinalcord`.

## Design rules (load-bearing — don't break these)

1. **Core stays dependency-free.** `spinalcord/types.py`, `safety.py`,
   `embodiment.py`, `backends/base.py`, `backends/fake.py`, and the package
   `__init__` must import with **stdlib only**. A real-body backend may need
   third-party packages (httpx, a CV stack, pyautogui, …) — put those behind
   an optional extra and import them lazily/inside the backend module, never
   at package import time.
2. **Backends answer "how", the gate answers "should".** A `Backend`
   implements raw primitives (`observe`, `do_click_at`, …) and never gates
   itself for policy reasons. `Embodiment` applies the `SafetyGate` and the
   post-action observation. Keep that split.
3. **Eyes are never gated.** Observation has no blast radius; only efferent
   (`do_*`) actions pass through the gate.
4. **`read_only=True` is the default.** Hands refuse until a consumer opts in.
   Don't change the default.
5. **Coordinates are `pct`** — fractions in `[0,1]`, top-left origin,
   resolution-independent. All backends and results use this.
6. **`Observation.render_text()` must stay deterministic** — same observation
   → byte-identical string. Consumers embed it and use it as a world-model
   key. If you change the format, keep it stable and update the test.
7. **`do_*` methods don't raise for ordinary failures** — return
   `ActionResult(ok=False, reason=...)`. They may raise `BackendUnavailable`
   when the transport/device is unreachable.

## Layout

```
spinalcord/
  __init__.py          # public surface + __version__ (single source of truth)
  types.py             # Frame, VisualElement, Observation, LocateResult,
                       #   VerifyResult, ActionResult  (the protocol)
  safety.py            # SafetyGate (read_only, confirm, allowed_apps, rate, panic)
  embodiment.py        # Embodiment facade — wraps a Backend with the gate
  backends/
    base.py            # Backend ABC + BackendUnavailable
    fake.py            # FakeBackend — scripted, hardware-free reference impl
tests/                 # unittest, fully offline (no deps, no network)
scripts/release.sh     # build + publish to PyPI / TestPyPI
.github/workflows/publish.yml   # Trusted-Publishing release workflow
pyproject.toml         # hatchling; version is dynamic from __init__.py
```

## Adding a backend

Subclass `Backend`. Required: `capabilities()`, `observe()`, `do_click_at`,
`do_type_text`, `do_key`. Optional (sensible defaults provided): `health`,
`frontmost_app`, `screenshot`, `locate`, `verify`, `read_text`, `do_move_to`,
`do_scroll`, `close`. `FakeBackend` is the worked example. If the backend
needs third-party deps, add an extra in `pyproject.toml`
(`[project.optional-dependencies]`) and import them inside the backend module
so the core import stays clean. Add it to `backends/__init__.py` only if it's
dependency-free; otherwise document the import path.

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py' -t .   # offline, no deps
# or, with dev extras: pytest
```

Every test must run offline with zero third-party deps. Drive new behavior
through `FakeBackend`. When you add a public method or a protocol field, add a
test for it.

## Releasing

Version is single-sourced from `__version__` in `spinalcord/__init__.py`
(hatchling reads it; `pyproject.toml` declares `dynamic = ["version"]`).

- **CI (primary):** bump `__version__`, commit, push to `main`.
  `.github/workflows/publish.yml` runs on every push to main, but only
  builds+publishes when the version isn't already on PyPI (it queries the PyPI
  JSON API and skips otherwise). Publishes via Trusted Publishing — no tokens.
  One-time PyPI "pending publisher" config is documented in the workflow
  header. **So: a version bump is the release trigger; ordinary pushes are
  no-ops.**
- **Local / TestPyPI:** `scripts/release.sh --test` then `scripts/release.sh`.
  `--tag` pushes a `vX.Y.Z` git tag after a real upload.

## Conventions

- Keep public surface in `spinalcord/__init__.py:__all__` current.
- Docstrings explain *why*; code says *what*. No emojis in code.
- `from __future__ import annotations` in every module (supports Python 3.9).
- Target Python ≥ 3.9; avoid 3.10+ runtime syntax (no `match`, no runtime
  `X | Y` in `isinstance`, etc.).
