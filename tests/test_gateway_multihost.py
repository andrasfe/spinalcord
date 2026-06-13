"""Multi-host BT HID routing (resolution + isolation semantics).

Stdlib unittest only — afferent's CI runs ``python -m unittest`` with no
pytest installed (that's how the package stays dependency-free).
"""
from __future__ import annotations

import unittest

from afferent.gateway.bt_hid import BluetoothHidServer, BtHidError, _HidClient


class _FakeSock:
    def close(self) -> None:
        pass


def _server_with(*macs: str) -> BluetoothHidServer:
    srv = BluetoothHidServer()
    for mac in macs:
        srv._clients[mac] = _HidClient(mac, _FakeSock(), _FakeSock())
    return srv


class MultiHostRoutingTests(unittest.TestCase):
    def test_resolve_no_clients_raises(self):
        with self.assertRaisesRegex(BtHidError, "No Bluetooth client"):
            _server_with()._resolve(None)

    def test_resolve_single_client_is_default(self):
        srv = _server_with("AA:BB:CC:DD:EE:01")
        self.assertEqual(srv._resolve(None).mac, "AA:BB:CC:DD:EE:01")

    def test_resolve_explicit_host_wins_and_normalizes(self):
        srv = _server_with("AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02")
        srv._active_mac = "AA:BB:CC:DD:EE:01"
        self.assertEqual(
            srv._resolve(" aa:bb:cc:dd:ee:02 ").mac, "AA:BB:CC:DD:EE:02"
        )

    def test_resolve_unknown_host_raises(self):
        srv = _server_with("AA:BB:CC:DD:EE:01")
        with self.assertRaisesRegex(BtHidError, "not connected"):
            srv._resolve("AA:BB:CC:DD:EE:99")

    def test_resolve_ambiguous_without_active_raises(self):
        srv = _server_with("AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02")
        srv._active_mac = None
        with self.assertRaisesRegex(BtHidError, "Multiple hosts"):
            srv._resolve(None)

    def test_active_host_routes_unaddressed(self):
        srv = _server_with("AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02")
        srv.set_active_host("aa:bb:cc:dd:ee:02")
        self.assertEqual(srv._resolve(None).mac, "AA:BB:CC:DD:EE:02")

    def test_set_active_host_requires_connected(self):
        srv = _server_with("AA:BB:CC:DD:EE:01")
        with self.assertRaises(BtHidError):
            srv.set_active_host("AA:BB:CC:DD:EE:99")

    def test_drop_client_reassigns_active(self):
        srv = _server_with("AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02")
        srv._active_mac = "AA:BB:CC:DD:EE:01"
        srv._drop_client("AA:BB:CC:DD:EE:01", "test")
        self.assertEqual(srv.connected_hosts, ["AA:BB:CC:DD:EE:02"])
        self.assertEqual(srv.active_host, "AA:BB:CC:DD:EE:02")

    def test_mouse_button_state_is_per_host(self):
        srv = _server_with("AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02")
        a = srv._resolve("AA:BB:CC:DD:EE:01")
        b = srv._resolve("AA:BB:CC:DD:EE:02")
        a.mouse_buttons |= 1
        self.assertEqual(b.mouse_buttons, 0)


if __name__ == "__main__":
    unittest.main()
