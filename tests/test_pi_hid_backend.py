"""PiHidBackend / GatewayClient tests — mock urllib; no real Pi needed.

Verifies host routing, key-combo → HID mapping, capability gating on the
injected homer, and graceful failure when the gateway is unreachable.
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

from afferent.backends.pi_hid import GatewayClient, PiHidBackend
from afferent.types import ActionResult


class _Capture:
    """Stand-in for urlopen: records the Request and returns a canned body."""

    def __init__(self, body=None):
        self.body = body if body is not None else {"status": "ok"}
        self.calls = []

    def __call__(self, req, timeout=None):
        payload = None
        if req.data:
            payload = json.loads(req.data.decode())
        self.calls.append((req.get_method(), req.full_url, payload))
        cap = self

        class _Resp:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def read(self_):
                return json.dumps(cap.body).encode()

        return _Resp()


def _client(host_mac=None, body=None):
    cap = _Capture(body)
    c = GatewayClient("http://10.0.0.2:8080", host_mac=host_mac)
    return c, cap


class GatewayRoutingTests(unittest.TestCase):
    def test_host_mac_injected_into_bt_payload(self):
        c, cap = _client(host_mac="84:2f:57:7d:85:21")
        with mock.patch("urllib.request.urlopen", cap):
            c.move(10, 0)
        method, url, body = cap.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/bt/mouse/move"))
        self.assertEqual(body["host"], "84:2F:57:7D:85:21")  # normalized upper
        self.assertEqual(body["x"], 10)

    def test_move_large_hits_dedicated_endpoint(self):
        c, cap = _client(host_mac="AA:BB:CC:DD:EE:FF")
        with mock.patch("urllib.request.urlopen", cap):
            c.move_large(2000, -1500)
        _, url, body = cap.calls[0]
        self.assertTrue(url.endswith("/bt/mouse/move_large"))
        self.assertEqual((body["x"], body["y"]), (2000, -1500))
        self.assertEqual(body["host"], "AA:BB:CC:DD:EE:FF")

    def test_no_host_mac_leaves_payload_unrouted(self):
        c, cap = _client(host_mac=None)
        with mock.patch("urllib.request.urlopen", cap):
            c.click("left", 2)
        _, _, body = cap.calls[0]
        self.assertNotIn("host", body)
        self.assertEqual(body, {"button": "left", "count": 2})

    def test_host_not_added_to_non_bt_paths(self):
        c, cap = _client(host_mac="AA:BB:CC:DD:EE:FF")
        with mock.patch("urllib.request.urlopen", cap):
            c.health()
        method, url, body = cap.calls[0]
        self.assertEqual(method, "GET")
        self.assertTrue(url.endswith("/health"))
        self.assertIsNone(body)

    def test_is_hid_up_checks_pinned_host(self):
        c, cap = _client(
            host_mac="84:2F:57:7D:85:21",
            body={"bt_hid_connected": True, "bt_hosts": ["84:2F:57:7D:85:21"]},
        )
        with mock.patch("urllib.request.urlopen", cap):
            self.assertTrue(c.is_hid_up())
        c2, cap2 = _client(
            host_mac="84:2F:57:7D:85:21",
            body={"bt_hid_connected": True, "bt_hosts": ["1C:1D:D3:E5:85:33"]},
        )
        with mock.patch("urllib.request.urlopen", cap2):
            self.assertFalse(c2.is_hid_up())  # connected, but a different host


class BackendTests(unittest.TestCase):
    def test_capabilities_gain_click_only_with_homer(self):
        be = PiHidBackend(GatewayClient("http://x"))
        self.assertEqual(be.capabilities(), {"type", "key", "scroll"})
        be2 = PiHidBackend(GatewayClient("http://x"), homer=lambda *a: ActionResult(True, "c"))
        self.assertIn("click", be2.capabilities())

    def test_do_key_maps_cmd_tab_to_meta_Tab(self):
        c, cap = _client()
        be = PiHidBackend(c)
        with mock.patch("urllib.request.urlopen", cap):
            res = be.do_key("cmd+tab")
        self.assertTrue(res.ok)
        _, url, body = cap.calls[0]
        self.assertTrue(url.endswith("/bt/key-combo"))
        self.assertEqual(body["modifiers"], ["meta"])
        self.assertEqual(body["key"], "Tab")

    def test_do_key_literal_char_chord(self):
        c, cap = _client()
        be = PiHidBackend(c)
        with mock.patch("urllib.request.urlopen", cap):
            be.do_key("ctrl+c")
        _, _, body = cap.calls[0]
        self.assertEqual(body["modifiers"], ["ctrl"])
        self.assertEqual(body["key"], "c")

    def test_do_key_bare_key_uses_keystroke(self):
        c, cap = _client()
        be = PiHidBackend(c)
        with mock.patch("urllib.request.urlopen", cap):
            be.do_key("enter")
        _, url, body = cap.calls[0]
        self.assertTrue(url.endswith("/bt/keystroke"))
        self.assertEqual(body["key"], "Enter")

    def test_do_key_unknown_modifier_refused(self):
        be = PiHidBackend(GatewayClient("http://x"))
        res = be.do_key("hyper+a")
        self.assertFalse(res.ok)
        self.assertIn("unknown modifier", res.reason)

    def test_type_text_with_enter(self):
        c, cap = _client()
        be = PiHidBackend(c)
        with mock.patch("urllib.request.urlopen", cap):
            res = be.do_type_text("hello", False, True)
        self.assertTrue(res.ok)
        paths = [url for _, url, _ in cap.calls]
        self.assertTrue(paths[0].endswith("/bt/text"))
        self.assertTrue(paths[1].endswith("/bt/keystroke"))

    def test_click_at_without_homer_refused_clearly(self):
        be = PiHidBackend(GatewayClient("http://x"))
        res = be.do_click_at(0.5, 0.5, "left", 1)
        self.assertFalse(res.ok)
        self.assertIn("no eyes", res.reason)

    def test_click_at_with_homer_delegates(self):
        seen = {}

        def homer(x, y, button, count, click):
            seen.update(x=x, y=y, button=button, count=count, click=click)
            return ActionResult(True, "click_at", final_cursor_pct=(x, y))

        be = PiHidBackend(GatewayClient("http://x"), homer=homer)
        res = be.do_click_at(0.8, 0.2, "right", 2)
        self.assertTrue(res.ok)
        self.assertEqual(seen, {"x": 0.8, "y": 0.2, "button": "right", "count": 2, "click": True})

    def test_unreachable_gateway_returns_not_ok(self):
        c = GatewayClient("http://10.0.0.2:8080")
        be = PiHidBackend(c)

        def boom(req, timeout=None):
            import urllib.error
            raise urllib.error.URLError("connection refused")

        with mock.patch("urllib.request.urlopen", boom):
            res = be.do_type_text("x", False, False)
        self.assertFalse(res.ok)
        self.assertIn("unreachable", res.reason)


if __name__ == "__main__":
    unittest.main()
