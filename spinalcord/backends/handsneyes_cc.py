"""HandsneyesBackend — HTTP client to a running handsneyes Command Center.

This is the reference backend. It contains NONE of handsneyes' vision / servo
/ pointer-accel / agent code — it just calls the cc's REST API. All the
hard-won quality (the `VisualServoHomer`, the learned pointer-accel models,
the tiered agents) stays in handsneyes and is reached over HTTP. handsneyes
is unchanged by this package.

Requires httpx: ``pip install spinalcord[handsneyes]``.

Endpoint assumptions (see handsneyes' BRAIN_INTEGRATION_SPEC.md). Where an
endpoint isn't yet exposed by a given handsneyes version, the corresponding
method degrades gracefully (capability omitted / ``found=False`` /
``ok=False`` with a clear reason) rather than raising — so a consumer can
probe `capabilities()` and adapt.
"""
from __future__ import annotations

import time
from typing import Optional

try:
    import httpx
except ImportError as e:  # pragma: no cover - only hit without the extra
    raise ImportError(
        "HandsneyesBackend needs httpx. Install with: pip install spinalcord[handsneyes]"
    ) from e

from ..types import ActionResult, Frame, LocateResult, Observation, VerifyResult, VisualElement
from .base import Backend, BackendUnavailable


class HandsneyesBackend(Backend):
    name = "handsneyes"

    def __init__(self, base_url: str = "http://localhost:8765",
                 target: Optional[str] = None,
                 timeout_s: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.target = target
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout_s)
        self._caps_cache: Optional[set] = None

    # ── transport helpers ─────────────────────────────────────────────────────
    def _post(self, path: str, body: Optional[dict] = None) -> "tuple[int, dict]":
        try:
            r = self._client.post(path, json=body or {})
        except httpx.HTTPError as e:
            raise BackendUnavailable(f"handsneyes cc unreachable at {self.base_url}: {e}") from e
        try:
            data = r.json() if r.content else {}
        except ValueError:
            data = {}
        return r.status_code, data

    def _get(self, path: str) -> "tuple[int, dict]":
        try:
            r = self._client.get(path)
        except httpx.HTTPError as e:
            raise BackendUnavailable(f"handsneyes cc unreachable at {self.base_url}: {e}") from e
        try:
            data = r.json() if r.content else {}
        except ValueError:
            data = {}
        return r.status_code, data

    # ── meta ──────────────────────────────────────────────────────────────────
    def health(self) -> bool:
        try:
            status, _ = self._get("/api/runs")
        except BackendUnavailable:
            return False
        return status < 500

    def capabilities(self) -> set:
        # Conservative: assume the documented stable endpoints exist when the
        # service is healthy. locate/verify/scroll are probed lazily and may be
        # absent on older handsneyes versions (calls degrade gracefully).
        if self._caps_cache is not None:
            return set(self._caps_cache)
        caps: set = set()
        if self.health():
            caps |= {"pixels", "ocr", "click", "type", "key"}
            # Optional endpoints — presence probed on first use; advertise
            # optimistically so consumers attempt them.
            caps |= {"locate", "verify", "scroll"}
        self._caps_cache = caps
        return set(caps)

    # ── eyes ──────────────────────────────────────────────────────────────────
    def _frame_from(self, data: dict) -> Optional[Frame]:
        fid = data.get("frame_id") or data.get("id") or data.get("path")
        if not fid:
            return None
        return Frame(
            id=str(fid),
            ts=float(data.get("ts", time.time())),
            width=int(data.get("width", 0) or 0),
            height=int(data.get("height", 0) or 0),
            path=data.get("path"),
        )

    def _elements_from(self, data: dict) -> list:
        out = []
        for e in data.get("elements", []) or []:
            try:
                b = e["bounds_pct"]
                out.append(VisualElement(
                    label=str(e.get("label", "")),
                    bounds_pct=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                    confidence=float(e.get("confidence", 1.0)),
                    kind=str(e.get("kind", "unknown")),
                ))
            except (KeyError, TypeError, ValueError, IndexError):
                continue
        return out

    def observe(self, *, ocr: bool = False, locate: Optional[list] = None) -> Observation:
        status, data = self._post("/api/snapshot", {"dedup": False})
        if status >= 400:
            return Observation(ts=time.time())
        ocr_text = None
        if ocr:
            ocr_text = self.read_text() or None
        cur = data.get("cursor_pct")
        cursor = tuple(cur) if isinstance(cur, (list, tuple)) and len(cur) == 2 else None
        return Observation(
            ts=float(data.get("ts", time.time())),
            frame=self._frame_from(data),
            frontmost_app=data.get("frontmost_app"),
            elements=self._elements_from(data),
            ocr_text=ocr_text,
            cursor_pct=cursor,
        )

    def screenshot(self) -> Frame:
        status, data = self._post("/api/snapshot", {"dedup": False})
        return self._frame_from(data) or Frame(id="none", ts=time.time())

    def read_text(self, region_pct: Optional[tuple] = None) -> str:
        body: dict = {}
        if region_pct and len(region_pct) >= 2:
            body = {"x_pct": region_pct[0], "y_pct": region_pct[1]}
            if len(region_pct) >= 3:
                body["band_pct"] = region_pct[2]
        status, data = self._post("/api/sync-text-from-host", body)
        if status >= 400:
            return ""
        return str(data.get("text", "") or "")

    def locate(self, description: str) -> LocateResult:
        status, data = self._post("/api/locate", {"description": description})
        if status == 404:
            return LocateResult(False, reason="/api/locate not available on this handsneyes version")
        if status >= 400:
            return LocateResult(False, reason=f"locate failed (status {status})")
        if not data.get("found"):
            return LocateResult(False, reason=str(data.get("reason", "not found")))
        return LocateResult(
            found=True,
            x_pct=data.get("x_pct"),
            y_pct=data.get("y_pct"),
            bounds_pct=tuple(data["bounds_pct"]) if data.get("bounds_pct") else None,
            confidence=float(data.get("confidence", 0.0)),
            reason=str(data.get("reason", "")),
        )

    def verify(self, question: str) -> VerifyResult:
        status, data = self._post("/api/verify", {"question": question})
        if status == 404:
            return VerifyResult(False, reason="/api/verify not available on this handsneyes version")
        if status >= 400:
            return VerifyResult(False, reason=f"verify failed (status {status})")
        return VerifyResult(
            answer=bool(data.get("answer")),
            confidence=float(data.get("confidence", 0.0)),
            reason=str(data.get("reason", "")),
        )

    # ── hands ─────────────────────────────────────────────────────────────────
    def do_click_at(self, x_pct, y_pct, button, count) -> ActionResult:
        t0 = time.time()
        status, data = self._post("/api/mouse/click_at", {
            "x_pct": x_pct, "y_pct": y_pct, "button": button, "count": count,
        })
        dur = (time.time() - t0) * 1000.0
        canonical = f"click_at({x_pct:.3f},{y_pct:.3f},button={button},count={count})"
        if status >= 400:
            return ActionResult(False, canonical, reason=f"click_at failed (status {status})",
                                duration_ms=dur)
        fc = data.get("final_cursor_pct")
        return ActionResult(
            ok=bool(data.get("clicked", True)),
            action=canonical,
            reason=str(data.get("reason", "")),
            steps=data.get("steps"),
            duration_ms=dur,
            final_cursor_pct=tuple(fc) if isinstance(fc, (list, tuple)) and len(fc) == 2 else None,
        )

    def do_type_text(self, text, secret, append_enter) -> ActionResult:
        t0 = time.time()
        status, data = self._post("/api/keyboard/text", {
            "text": text, "secret": secret, "append_enter": append_enter,
        })
        dur = (time.time() - t0) * 1000.0
        shown = f"<{len(text)} chars>" if secret else text[:40]
        canonical = f"type_text({shown!r},append_enter={append_enter})"
        ok = status < 400
        return ActionResult(ok, canonical,
                            reason="" if ok else f"type failed (status {status})",
                            duration_ms=dur)

    def do_key(self, combo) -> ActionResult:
        t0 = time.time()
        status, data = self._post("/api/keyboard/key", {"key": combo})
        dur = (time.time() - t0) * 1000.0
        ok = status < 400
        return ActionResult(ok, f"key({combo})",
                            reason="" if ok else f"key failed (status {status})",
                            duration_ms=dur)

    def do_scroll(self, amount, at_pct) -> ActionResult:
        t0 = time.time()
        body: dict = {"amount": amount}
        if at_pct and len(at_pct) == 2:
            body["x_pct"], body["y_pct"] = at_pct[0], at_pct[1]
        status, data = self._post("/api/mouse/scroll", body)
        dur = (time.time() - t0) * 1000.0
        if status == 404:
            return ActionResult(False, f"scroll({amount})",
                                reason="/api/mouse/scroll not available on this handsneyes version",
                                duration_ms=dur)
        ok = status < 400
        return ActionResult(ok, f"scroll({amount})",
                            reason="" if ok else f"scroll failed (status {status})",
                            duration_ms=dur)

    def close(self) -> None:
        self._client.close()
