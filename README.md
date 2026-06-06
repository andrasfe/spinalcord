# spinalcord

**A backend-agnostic sensorimotor protocol — eyes and hands for cognitive agents driving a computer.**

A cognitive layer (a *brain*) plans; an embodiment layer (a *body*) acts.
`spinalcord` is the conduit between them. It carries **afferent** signals up
(eyes — `observe` / `locate` / `verify` / `read_text`) and **efferent**
signals down (hands — `click` / `type_text` / `key` / `scroll`), as typed,
safety-gated calls over a **pluggable backend**.

```
   ┌─────────┐   afferent (eyes) ↑    ┌────────────┐   actions   ┌──────────┐
   │  brain  │ ◀───────────────────── │ spinalcord │ ──────────▶ │   body   │
   │ (plans) │ ──────────────────────▶│ (protocol) │ ◀────────── │ (acts)   │
   └─────────┘   efferent (hands) ↓    └────────────┘  observations└──────────┘
```

The reference backend talks to [**handsneyes**](https://github.com/andrasfe/handsneyes)
— a physical-telepresence system (webcam vision + Raspberry Pi HID + a learned
closed-loop visual servo) — over its HTTP API. **None of handsneyes' vision,
servo, or model code is duplicated here**; `spinalcord` is a thin, additive
consumer. The same protocol can front any other body (Playwright, pyautogui,
a VM driver, …) — write a `Backend` subclass and you're done.

## Why it exists

Most computer-use agents fuse perception, planning, and action into one
monolith. `spinalcord` deliberately splits the *body* from the *mind* with a
narrow, typed seam, so:

- the planner stays free to be anything (an LLM loop, a cognitive
  architecture, a script);
- the body stays free to be anything (telepresence, local automation, a test
  harness);
- and the whole loop is **unit-testable offline** via a scripted fake backend —
  no hardware, no network, no API keys.

## Install

```bash
pip install spinalcord                 # core: stdlib only, zero deps
pip install spinalcord[handsneyes]     # + the httpx-backed handsneyes backend
```

## Quickstart — offline, fake body (works immediately)

```python
from spinalcord import Embodiment
from spinalcord.types import Observation, VisualElement

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

## Quickstart — live, handsneyes body

```python
from spinalcord import Embodiment

# Defaults to read_only=True (eyes only — zero blast radius).
em = Embodiment.handsneyes(base_url="http://localhost:8765")
print(em.health())
print(em.observe(ocr=True).render_text())

# Opt into acting, with a per-action veto your planner controls:
em = Embodiment.handsneyes(
    read_only=False,
    confirm=lambda desc: input(f"do {desc}? [y/N] ").strip() == "y",
    allowed_apps=["Firefox"],
    max_actions_per_min=20,
)
em.click_at(0.80, 0.20)
```

(Requires a running `handsneyes cc`. See that project's `BRAIN_INTEGRATION_SPEC.md`.)

## The protocol

All coordinates are `pct` — fractions in `[0, 1]`, top-left origin,
resolution-independent (so they're stable world-model keys across machines).

Typed results (`spinalcord.types`): `Frame`, `VisualElement`, `Observation`,
`LocateResult`, `VerifyResult`, `ActionResult`.

`Observation.render_text()` is a **stable, compact, embeddable** one-screen
string — feed it to an embedding model and use it as a key in a learned world
model. Determinism is guaranteed (same observation → byte-identical string).

`ActionResult` carries **grounding** for predictive-coding / world-model
consumers: `steps` (visual-servo iterations), `duration_ms`,
`final_cursor_pct`, `frame_before` / `frame_after`, and a `state_after`
observation bracketing the action.

## Safety

`SafetyGate` sits in front of every efferent action (eyes are never gated):

- `read_only=True` is the **default** — hands refuse until you opt in.
- `confirm(desc) -> bool` — a per-action veto your planner drives.
- `allowed_apps` — refuse when the frontmost app isn't allowed.
- `max_actions_per_min` — rate limit against runaway loops.
- `panic()` — latch into a permanent refusing state.

This is *additive* to whatever gates the backend enforces (handsneyes, e.g.,
won't type without visually confirming a login screen). Both must pass.

## Writing a backend

Subclass `spinalcord.Backend`, implement the eyes (`observe`, optionally
`locate` / `verify` / `read_text`) and the raw hands (`do_click_at`,
`do_type_text`, `do_key`, optionally `do_move_to` / `do_scroll`), and declare
`capabilities()`. `Embodiment` applies the `SafetyGate` and the post-action
observation for you — a backend only answers "how do I see / move", never
"should I".

## Develop

```bash
pip install -e ".[dev]"
python -m unittest discover -s tests -v     # 27 tests, fully offline
# or: pytest
```

## License

MIT.
