"""MacOSBackend — drive the host Mac with built-in tools.

Eyes: `screencapture` (ships with macOS) for pixels, `osascript` for the
frontmost app name and the logical screen size. No pip dependencies.

Hands: `cliclick` (https://github.com/BlueM/cliclick, `brew install cliclick`)
for mouse + keyboard. Detected at runtime — if it's missing, the hand
capabilities are simply omitted and `do_*` return a clear `ok=False` rather
than raising. So `import afferent.backends.macos` always works; what the
backend can *do* depends on what's installed and permitted.

Coordinates are `pct` (0..1). cliclick works in logical points, and the
logical screen size comes from osascript, so clicks land correctly on Retina
displays (where the screenshot's pixel size is 2× the point size).

Permissions (macOS will prompt / must be granted in System Settings →
Privacy & Security):
  - Screen Recording  → for `screencapture` to see window contents.
  - Accessibility     → for `cliclick` to move the mouse / type.

This backend has no automated coverage of real hardware; its tests mock
`subprocess` to check command construction and capability degradation.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional

from ..types import ActionResult, Frame, Observation
from .base import Backend, BackendUnavailable

# Special keys cliclick names via `kp:`; everything else is typed with `t:`.
_SPECIAL_KEYS = {
    "return": "return", "enter": "return", "tab": "tab", "space": "space",
    "esc": "esc", "escape": "esc", "delete": "delete", "backspace": "delete",
    "up": "arrow-up", "down": "arrow-down", "left": "arrow-left",
    "right": "arrow-right", "home": "home", "end": "end",
    "pageup": "page-up", "pagedown": "page-down",
}
_MODIFIERS = {"cmd", "command", "ctrl", "control", "alt", "option", "opt", "shift", "fn"}
_MOD_ALIAS = {"command": "cmd", "control": "ctrl", "option": "alt", "opt": "alt"}


class MacOSBackend(Backend):
    name = "macos"

    def __init__(self, capture_dir: Optional[str] = None):
        self._cliclick = shutil.which("cliclick")
        self._screencapture = shutil.which("screencapture")
        self._osascript = shutil.which("osascript")
        self._capture_dir = capture_dir
        self._screen_pts: Optional[tuple] = None   # (w, h) logical points, cached
        self._frame_seq = 0

    # ── meta ──────────────────────────────────────────────────────────────────
    def capabilities(self) -> set:
        caps: set = set()
        if self._screencapture:
            caps.add("pixels")
        if self._cliclick:
            caps |= {"click", "type", "key"}
        return caps

    def health(self) -> bool:
        return bool(self._screencapture)

    def frontmost_app(self) -> Optional[str]:
        if not self._osascript:
            return None
        script = ('tell application "System Events" to get name of first '
                  "application process whose frontmost is true")
        try:
            out = subprocess.run([self._osascript, "-e", script],
                                 capture_output=True, text=True, timeout=5)
            name = out.stdout.strip()
            return name or None
        except Exception:
            return None

    # ── eyes ──────────────────────────────────────────────────────────────────
    def _screen_size_pts(self) -> Optional[tuple]:
        if self._screen_pts is not None:
            return self._screen_pts
        if not self._osascript:
            return None
        script = ('tell application "Finder" to get bounds of window of desktop')
        try:
            out = subprocess.run([self._osascript, "-e", script],
                                 capture_output=True, text=True, timeout=5)
            # "0, 0, 1728, 1117"
            parts = [p.strip() for p in out.stdout.strip().split(",")]
            if len(parts) == 4:
                w = int(parts[2]); h = int(parts[3])
                self._screen_pts = (w, h)
                return self._screen_pts
        except Exception:
            pass
        return None

    def observe(self, *, ocr: bool = False, locate: Optional[list] = None) -> Observation:
        frame = self._capture()
        app = self.frontmost_app()
        return Observation(ts=time.time(), frame=frame, frontmost_app=app,
                           elements=[], ocr_text=None, cursor_pct=None)

    def screenshot(self) -> Frame:
        f = self._capture()
        return f or Frame(id="none", ts=time.time())

    def _capture(self) -> Optional[Frame]:
        if not self._screencapture:
            return None
        self._frame_seq += 1
        d = self._capture_dir or tempfile.gettempdir()
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"afferent_frame_{self._frame_seq:05d}.png")
        try:
            # -x: no sound, -t png
            subprocess.run([self._screencapture, "-x", "-t", "png", path],
                           capture_output=True, timeout=15, check=False)
        except Exception as e:
            raise BackendUnavailable(f"screencapture failed: {e}") from e
        if not os.path.exists(path):
            return None
        w = h = 0
        size = self._screen_size_pts()
        if size:
            w, h = size
        return Frame(id=f"macos-{self._frame_seq}", ts=time.time(),
                     width=w, height=h, path=path)

    # ── hands ───────────────────────────────────────────────────────────────────
    def _pct_to_pts(self, x_pct: float, y_pct: float) -> "tuple[int, int]":
        size = self._screen_size_pts() or (1440, 900)
        return (int(round(x_pct * size[0])), int(round(y_pct * size[1])))

    def _run_cliclick(self, args: list, action: str) -> ActionResult:
        if not self._cliclick:
            return ActionResult(False, action,
                                reason="cliclick not installed (brew install cliclick)")
        t0 = time.time()
        try:
            proc = subprocess.run([self._cliclick, *args],
                                  capture_output=True, text=True, timeout=15)
        except Exception as e:
            return ActionResult(False, action, reason=f"cliclick error: {e}")
        dur = (time.time() - t0) * 1000.0
        ok = proc.returncode == 0
        return ActionResult(ok, action,
                            reason="" if ok else (proc.stderr.strip() or "cliclick failed"),
                            duration_ms=dur)

    def do_click_at(self, x_pct, y_pct, button, count) -> ActionResult:
        px, py = self._pct_to_pts(x_pct, y_pct)
        verb = "rc" if button == "right" else ("dc" if count >= 2 else "c")
        action = f"click_at({x_pct:.3f},{y_pct:.3f},button={button},count={count})"
        res = self._run_cliclick([f"{verb}:{px},{py}"], action)
        if res.ok:
            res.final_cursor_pct = (x_pct, y_pct)
        return res

    def do_move_to(self, x_pct, y_pct) -> ActionResult:
        px, py = self._pct_to_pts(x_pct, y_pct)
        res = self._run_cliclick([f"m:{px},{py}"],
                                 f"move_to({x_pct:.3f},{y_pct:.3f})")
        if res.ok:
            res.final_cursor_pct = (x_pct, y_pct)
        return res

    def do_type_text(self, text, secret, append_enter) -> ActionResult:
        shown = f"<{len(text)} chars>" if secret else text[:40]
        action = f"type_text({shown!r},append_enter={append_enter})"
        # cliclick t: types literal text; w:0 = no inter-key delay tweak.
        args = [f"t:{text}"]
        if append_enter:
            args.append("kp:return")
        res = self._run_cliclick(args, action)
        return res

    def do_key(self, combo) -> ActionResult:
        action = f"key({combo})"
        parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
        if not parts:
            return ActionResult(False, action, reason="empty combo")
        *mods, key = parts
        mods = [_MOD_ALIAS.get(m, m) for m in mods]
        for m in mods:
            if m not in _MODIFIERS and _MOD_ALIAS.get(m, m) not in _MODIFIERS:
                return ActionResult(False, action, reason=f"unknown modifier {m!r}")
        args: list = []
        for m in mods:
            args.append(f"kd:{m}")
        if key in _SPECIAL_KEYS:
            args.append(f"kp:{_SPECIAL_KEYS[key]}")
        else:
            # a literal character chord (e.g. cmd+c) — type the char while held
            args.append(f"t:{key}")
        for m in reversed(mods):
            args.append(f"ku:{m}")
        return self._run_cliclick(args, action)

    # scroll: cliclick has no scroll primitive; capability omitted, base
    # default returns ok=False with a clear reason.
