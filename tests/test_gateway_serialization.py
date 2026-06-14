"""Per-host serialization of concurrent HID activity.

Two callers targeting the SAME host must not interleave their reports
(a burst/gesture stays atomic); callers targeting DIFFERENT hosts must
not block each other (independent locks).
"""
from __future__ import annotations

import asyncio
import unittest

from afferent.gateway.bt_hid import BluetoothHidServer, _HidClient


class _Sock:
    def close(self) -> None:
        pass


class SerializationTests(unittest.IsolatedAsyncioTestCase):
    async def _server(self, *macs):
        srv = BluetoothHidServer()
        for m in macs:
            srv._clients[m] = _HidClient(m, _Sock(), _Sock())
        self.sent: list = []  # (mac, x) per mouse report

        async def fake_send_mouse(buttons, x, y, wheel, client):
            self.sent.append((client.mac, x))
            await asyncio.sleep(0)  # yield — gives a concurrent task the chance to slice in

        srv._send_mouse_report = fake_send_mouse  # type: ignore[assignment]
        return srv

    async def test_same_host_burst_not_interleaved(self):
        srv = await self._server("AA")
        # 381 = 127*3, so each burst is exactly 3 reports; opposite signs
        # make the two bursts trivially distinguishable.
        await asyncio.gather(
            srv.move_large(381, 0, host="AA"),
            srv.move_large(-381, 0, host="AA"),
        )
        signs = [1 if x > 0 else -1 for _, x in self.sent]
        # With the per-host lock the two 3-report bursts are contiguous.
        self.assertIn(
            signs, ([1, 1, 1, -1, -1, -1], [-1, -1, -1, 1, 1, 1]),
            f"bursts interleaved: {signs}",
        )

    async def test_different_hosts_both_complete(self):
        srv = await self._server("AA", "BB")
        # Independent locks → concurrent bursts to different hosts both
        # finish (no cross-host blocking / deadlock).
        await asyncio.gather(
            srv.move_large(254, 0, host="AA"),   # 2 reports
            srv.move_large(254, 0, host="BB"),   # 2 reports
        )
        from collections import Counter
        counts = Counter(m for m, _ in self.sent)
        self.assertEqual(counts["AA"], 2)
        self.assertEqual(counts["BB"], 2)

    async def test_double_click_not_split_by_concurrent_move(self):
        srv = await self._server("AA")
        # A double-click is 4 button reports (press,rel,press,rel), all with
        # x==0. A concurrent move_large is 3 reports with x!=0. Under the
        # per-host lock the 4 click reports form ONE contiguous run.
        await asyncio.gather(
            srv.click("left", 2, 0, host="AA"),
            srv.move_large(381, 0, host="AA"),
        )
        seq = "".join("C" if x == 0 else "M" for _, x in self.sent)
        self.assertEqual(seq.count("C"), 4)
        self.assertEqual(seq.count("M"), 3)
        # exactly one contiguous run of C (not split by an M)
        self.assertEqual(seq.count("C" * 4), 1, f"double-click split: {seq}")


if __name__ == "__main__":
    unittest.main()
