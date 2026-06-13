# afferent

**A backend-agnostic sensorimotor protocol — eyes and hands for cognitive agents driving a computer.**

A cognitive layer (a *brain*) plans; an embodiment layer (a *body*) acts.
`afferent` is the conduit between them. It carries **afferent** signals up
(eyes — `observe` / `locate` / `verify` / `read_text`) and **efferent**
signals down (hands — `click` / `type_text` / `key` / `scroll`), as typed,
safety-gated calls over a **pluggable backend**.

```
   ┌─────────┐   afferent (eyes) ↑    ┌────────────┐   actions   ┌──────────┐
   │  brain  │ ◀───────────────────── │  afferent  │ ──────────▶ │   body   │
   │ (plans) │ ──────────────────────▶│ (protocol) │ ◀────────── │ (backend)│
   └─────────┘   efferent (hands) ↓    └────────────┘  observations└──────────┘
```

The core is **dependency-free** (stdlib only). It ships three backends —
`FakeBackend` (scripted, hardware-free), `MacOSBackend` (drives the host Mac
via `screencapture` + `cliclick`), and `PiHidBackend` (drives a *remote*
machine through a Bluetooth-HID gateway) — plus a `Backend` ABC you subclass
to drive any other body. The protocol doesn't care which.

## Why it exists

Most computer-use agents fuse perception, planning, and action into one
monolith. `afferent` deliberately splits the *body* from the *mind* with a
narrow, typed seam, so:

- the planner stays free to be anything (an LLM loop, a cognitive
  architecture, a script);
- the body stays free to be anything (a real desktop, a browser, a VM, a
  fake);
- and the whole loop is **unit-testable offline** via the scripted fake
  backend — no hardware, no network, no API keys.

## Install

```bash
pip install afferent
```

That's it — no dependencies. (Dev tooling: `pip install afferent[dev]`.)

## Quickstart — offline, scripted body (works immediately)

```python
from afferent import Embodiment
from afferent.types import Observation, VisualElement

screen0 = Observation(
    ts=0.0, frontmost_app="Firefox",
    elements=[VisualElement("Run", (0.80, 0.20, 0.10, 0.04), kind="button")],
)
screen1 = Observation(ts=1.0, frontmost_app="Firefox", ocr_text="running…")

em = Embodiment.fake(script=[screen0, screen1])     # read_only=False for the demo

print(em.observe().render_text())                   # afferent: see the screen
res = em.click("Run")                               # efferent: locate + click
print(res.ok, res.steps, res.state_after.ocr_text)  # grounded outcome
```

## Quickstart — live, your Mac

```python
from afferent import Embodiment

# Eyes only by default (read_only=True) — zero blast radius.
em = Embodiment.macos()
print(em.capabilities())                 # {'pixels','click','type','key'} if cliclick installed
print(em.observe().render_text())        # frontmost app + screenshot frame

# Opt into hands, gated by a confirm callback you control:
em = Embodiment.macos(read_only=False, confirm=lambda d: input(f"{d}? [y/N] ") == "y")
em.click_at(0.5, 0.5)
```

Eyes use the built-in `screencapture` (grant **Screen Recording**); hands use
[`cliclick`](https://github.com/BlueM/cliclick) (`brew install cliclick`, grant
**Accessibility**). Missing tools degrade gracefully — `capabilities()` reflects
what's actually available.

## Driving a *remote* machine — the BT HID gateway

`MacOSBackend` drives the host it runs on. To drive a **different** computer —
one you can't run code on — `afferent` ships a Bluetooth-HID body: a Raspberry
Pi bonded to one or more targets like a multi-device keyboard/mouse, exposing a
REST API. The consumer side is stdlib-only:

```python
from afferent import Embodiment, PiHidBackend

# Pin to one target by its Bluetooth MAC; several can stay connected at once
# and only the addressed machine receives input.
be = PiHidBackend(base_url="http://10.0.0.2:8080",
                  host_mac="84:2F:57:7D:85:21")
em = Embodiment(be, read_only=False)

em.key("cmd+tab")              # app switch on that machine
em.type_text("hello\n")        # types only on that host
be.client.set_active_host(...) # or route unaddressed calls
```

A gateway is **hands without eyes** — it sends *relative* motion and key/text
reports, so `type_text` / `key` / `scroll` work directly, but absolute
`click_at(x_pct, y_pct)` needs a `homer=` (a visual servo that watches the
screen and drives the cursor to the target). Inject one if your consumer has
eyes; otherwise pct clicks return `ok=False` with a clear reason.

**Pi side** (`pip install afferent[gateway]`, runs the L2CAP multi-host HID
server + REST gateway):

```bash
afferent-gateway            # serves http://0.0.0.0:8080
```

See `scripts/afferent-gateway.service` for a systemd unit and
`scripts/macos-devmouse-autoconnect.sh` for a macOS agent that keeps a target
auto-reconnected like a real Bluetooth mouse (`--install`, `--pause`, `--status`).

## The protocol

All coordinates are `pct` — fractions in `[0, 1]`, top-left origin,
resolution-independent (so they're stable world-model keys across machines).

Typed results (`afferent.types`): `Frame`, `VisualElement`, `Observation`,
`LocateResult`, `VerifyResult`, `ActionResult`.

`Observation.render_text()` is a **stable, compact, embeddable** one-screen
string — feed it to an embedding model and use it as a key in a learned world
model. Determinism is guaranteed (same observation → byte-identical string).

`ActionResult` carries **grounding** for predictive-coding / world-model
consumers: `steps` (e.g. visual-servo iterations), `duration_ms`,
`final_cursor_pct`, `frame_before` / `frame_after`, and a `state_after`
observation bracketing the action.

## Safety

`SafetyGate` sits in front of every efferent action (eyes are never gated):

- `read_only=True` is the **default** — hands refuse until you opt in.
- `confirm(desc) -> bool` — a per-action veto your planner drives.
- `allowed_apps` — refuse when the frontmost app isn't allowed.
- `max_actions_per_min` — rate limit against runaway loops.
- `panic()` — latch into a permanent refusing state.

This is *additive* to whatever gates a backend enforces internally. Both must
pass.

## Writing a backend

Subclass `afferent.Backend`, implement the eyes (`observe`, optionally
`locate` / `verify` / `read_text`) and the raw hands (`do_click_at`,
`do_type_text`, `do_key`, optionally `do_move_to` / `do_scroll`), and declare
`capabilities()`. `Embodiment` applies the `SafetyGate` and the post-action
observation for you — a backend only answers "how do I see / move", never
"should I".

```python
from afferent import Backend, Embodiment
from afferent.types import Observation, ActionResult

class MyBackend(Backend):
    name = "mybody"
    def capabilities(self):
        return {"pixels", "click", "type", "key"}
    def observe(self, *, ocr=False, locate=None) -> Observation:
        ...   # capture your screen → Observation
    def do_click_at(self, x_pct, y_pct, button, count) -> ActionResult:
        ...   # drive your mouse; return ActionResult(ok=True, ...)
    def do_type_text(self, text, secret, append_enter) -> ActionResult:
        ...
    def do_key(self, combo) -> ActionResult:
        ...

em = Embodiment(MyBackend(), read_only=False)
```

`FakeBackend` (in `afferent/backends/fake.py`) is a complete, readable
reference implementation of the contract.

## Develop

```bash
pip install -e ".[dev]"
python -m unittest discover -s tests -v     # fully offline, no deps
# or: pytest
```

## Releasing

Publishing is automatic. Bump `__version__` in `afferent/__init__.py`,
commit, and **push to `main`** — `.github/workflows/publish.yml` builds, tests,
and publishes to PyPI via Trusted Publishing (no tokens). Pushes that don't
change the version are a no-op (the workflow checks PyPI and skips).

One-time setup is in the workflow header (add a "pending publisher" on PyPI).

For a manual / TestPyPI publish, use the local script:

```bash
scripts/release.sh --test     # TestPyPI
scripts/release.sh            # PyPI
```

## License

MIT.
