"""PiHidBackend — drive a target machine through the multi-host BT HID gateway.

This is the "remote HID bridge" backend the package docstring promises. The
hands are a Raspberry Pi running ``afferent.gateway`` (a Bluetooth HID device
bonded to one or more host machines, like a multi-device keyboard/mouse); this
backend POSTs to its REST API. Every report is addressed to exactly ONE host
by MAC, so several targets can stay connected at once and only the addressed
one receives input.

Stdlib only (``urllib``) — no httpx, honouring the package's dependency-free
core.

Abstraction note — a gateway is **hands without eyes**. It speaks *relative*
mouse motion and key/text reports; it has no idea where the cursor is on
screen. So ``do_type_text`` / ``do_key`` / ``do_scroll`` work directly, but
``do_click_at`` / ``do_move_to`` (which need an *absolute* pct → cursor
landing) require a ``homer`` callable to be injected — a visual-servo that
watches the screen and drives relative moves until the cursor lands. Without
one, pct moves return ``ok=False`` with a clear reason rather than guessing.
A consumer that has eyes (a webcam, a screen grab + cursor detector) supplies
the homer; a consumer that only needs to type/hotkey doesn't.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from ..types import ActionResult, Observation
from .base import Backend, BackendUnavailable

# afferent's OS-agnostic modifier names → USB HID modifier names the gateway
# accepts. The macOS Command key IS the USB GUI/Meta modifier, so cmd→meta.
_MOD_TO_HID = {
    "cmd": "meta", "command": "meta", "win": "meta", "super": "meta",
    "meta": "meta", "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "option": "alt", "opt": "alt",
    "shift": "shift", "fn": "fn",
}
# Named keys → the gateway's key map (which is case-sensitive: "Tab", not
# "tab"). Anything not here is sent as-is (single literal characters).
_KEY_TO_HID = {
    "return": "Enter", "enter": "Enter", "tab": "Tab", "space": "Space",
    "esc": "Escape", "escape": "Escape", "delete": "Delete",
    "backspace": "Backspace", "up": "Up", "down": "Down",
    "left": "Left", "right": "Right", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
}

# A homer turns an absolute pct target into a landed click/move using vision.
HomerFn = Callable[[float, float, str, int, bool], ActionResult]


class GatewayClient:
    """Thin stdlib HTTP client for one ``afferent.gateway`` instance.

    ``host_mac`` pins every ``/bt/*`` request to one target machine. When set
    it is added to each request body, so the gateway routes the report to that
    host even with several connected. Leave it ``None`` to use the gateway's
    active-host (or single-connection) default.
    """

    def __init__(
        self,
        base_url: str = "http://10.0.0.2:8080",
        *,
        host_mac: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.host_mac = host_mac.strip().upper() if host_mac else None
        self.timeout = timeout

    # ── transport ─────────────────────────────────────────────────────────────
    def _request(self, method: str, path: str, body: Optional[dict]) -> dict:
        if body is not None and self.host_mac and path.startswith("/bt"):
            body = {**body, "host": self.host_mac}
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read()).get("detail", "")
            except Exception:
                pass
            raise BackendUnavailable(
                f"gateway {method} {path} -> HTTP {e.code}: {detail}"
            ) from e
        except urllib.error.URLError as e:
            raise BackendUnavailable(
                f"gateway {method} {path} unreachable: {e.reason}"
            ) from e

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, body)

    def _get(self, path: str) -> dict:
        return self._request("GET", path, None)

    # ── meta / hosts ──────────────────────────────────────────────────────────
    def health(self) -> dict:
        return self._get("/health")

    def hosts(self) -> dict:
        """{'connected': [mac, ...], 'active': mac|None}."""
        return self._get("/bt/hosts")

    def set_active_host(self, mac: str) -> dict:
        return self._post("/bt/active-host", {"host": mac})

    def is_hid_up(self) -> bool:
        """True when the gateway reports an open HID link for this client's
        host (or any host, if unpinned)."""
        try:
            h = self.health()
        except BackendUnavailable:
            return False
        if not h.get("bt_hid_connected"):
            return False
        if self.host_mac:
            return self.host_mac in [
                m.upper() for m in h.get("bt_hosts", [])
            ]
        return True

    # ── low-level hands (relative; no cursor positioning) ─────────────────────
    def move(self, dx: int, dy: int) -> dict:
        return self._post("/bt/mouse/move", {"x": int(dx), "y": int(dy)})

    def click(self, button: str = "left", count: int = 1) -> dict:
        return self._post(
            "/bt/mouse/click", {"button": button, "count": int(count)}
        )

    def press(self, button: str = "left") -> dict:
        return self._post("/bt/mouse/press", {"button": button})

    def release(self, button: str = "left") -> dict:
        return self._post("/bt/mouse/release", {"button": button})

    def scroll(self, amount: int) -> dict:
        return self._post("/bt/mouse/scroll", {"amount": int(amount)})

    def key_combo(self, modifiers: list, key: str) -> dict:
        return self._post(
            "/bt/key-combo", {"modifiers": list(modifiers), "key": key}
        )

    def keystroke(self, key: str) -> dict:
        return self._post("/bt/keystroke", {"key": key})

    def text(self, s: str, *, warmup: bool = True) -> dict:
        return self._post("/bt/text", {"text": s, "warmup": warmup})


class PiHidBackend(Backend):
    name = "pi_hid"

    def __init__(
        self,
        client: Optional[GatewayClient] = None,
        *,
        base_url: str = "http://10.0.0.2:8080",
        host_mac: Optional[str] = None,
        homer: Optional[HomerFn] = None,
        timeout: float = 10.0,
    ) -> None:
        self.client = client or GatewayClient(
            base_url, host_mac=host_mac, timeout=timeout
        )
        # Injected visual-servo for absolute pct clicks/moves. None = this
        # body has no eyes; pct moves are refused with a clear reason.
        self.homer = homer

    # ── meta ────────────────────────────────────────────────────────────────
    def capabilities(self) -> set:
        caps = {"type", "key", "scroll"}
        if self.homer is not None:
            caps.add("click")
        return caps

    def health(self) -> bool:
        return self.client.is_hid_up()

    def frontmost_app(self) -> Optional[str]:
        return None  # a gateway has no eyes

    # ── eyes (none — hands-only body) ─────────────────────────────────────────
    def observe(self, *, ocr: bool = False, locate: Optional[list] = None) -> Observation:
        return Observation(ts=time.time(), frame=None, frontmost_app=None)

    # ── hands ─────────────────────────────────────────────────────────────────
    def do_type_text(self, text, secret, append_enter) -> ActionResult:
        shown = f"<{len(text)} chars>" if secret else text[:40]
        action = f"type_text({shown!r},append_enter={append_enter})"
        t0 = time.time()
        try:
            self.client.text(text)
            if append_enter:
                self.client.keystroke("Enter")
        except BackendUnavailable as e:
            return ActionResult(False, action, reason=str(e))
        return ActionResult(True, action, duration_ms=(time.time() - t0) * 1000)

    def do_key(self, combo) -> ActionResult:
        action = f"key({combo})"
        parts = [p.strip().lower() for p in str(combo).split("+") if p.strip()]
        if not parts:
            return ActionResult(False, action, reason="empty combo")
        *mods, key = parts
        hid_mods = []
        for m in mods:
            hm = _MOD_TO_HID.get(m)
            if hm is None:
                return ActionResult(False, action, reason=f"unknown modifier {m!r}")
            hid_mods.append(hm)
        hid_key = _KEY_TO_HID.get(key, key if len(key) == 1 else key.capitalize())
        t0 = time.time()
        try:
            if hid_mods:
                self.client.key_combo(hid_mods, hid_key)
            else:
                self.client.keystroke(hid_key)
        except BackendUnavailable as e:
            return ActionResult(False, action, reason=str(e))
        return ActionResult(True, action, duration_ms=(time.time() - t0) * 1000)

    def do_scroll(self, amount, at_pct) -> ActionResult:
        action = f"scroll({amount},at={at_pct})"
        # at_pct needs the homer to position first; without eyes we scroll at
        # the current cursor location.
        if at_pct is not None and self.homer is not None:
            self.homer(at_pct[0], at_pct[1], "left", 0, False)
        try:
            self.client.scroll(int(amount))
        except BackendUnavailable as e:
            return ActionResult(False, action, reason=str(e))
        return ActionResult(True, action)

    def do_click_at(self, x_pct, y_pct, button, count) -> ActionResult:
        action = f"click_at({x_pct:.3f},{y_pct:.3f},button={button},count={count})"
        if self.homer is None:
            return ActionResult(
                False, action,
                reason="pct clicks need a homer — this gateway has no eyes; "
                "inject homer= (a visual servo) or use a backend with a cursor oracle",
            )
        return self.homer(x_pct, y_pct, button, count, True)

    def do_move_to(self, x_pct, y_pct) -> ActionResult:
        action = f"move_to({x_pct:.3f},{y_pct:.3f})"
        if self.homer is None:
            return ActionResult(
                False, action,
                reason="pct moves need a homer — this gateway has no eyes",
            )
        return self.homer(x_pct, y_pct, "left", 0, False)
