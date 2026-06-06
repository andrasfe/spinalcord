"""MacOSBackend tests — mock subprocess; no real screen/cliclick needed.

Verifies command construction, pct→points conversion, key-combo parsing, and
graceful degradation when cliclick / screencapture are absent.
"""
from __future__ import annotations

import unittest
from unittest import mock

from afferent.backends.macos import MacOSBackend


def _backend_with(cliclick=True, screencapture=True, osascript=True, screen=(1000, 800)):
    be = MacOSBackend()
    be._cliclick = "/usr/local/bin/cliclick" if cliclick else None
    be._screencapture = "/usr/sbin/screencapture" if screencapture else None
    be._osascript = "/usr/bin/osascript" if osascript else None
    be._screen_pts = screen
    return be


class CapabilityTests(unittest.TestCase):
    def test_full_capabilities(self):
        be = _backend_with()
        self.assertEqual(be.capabilities(), {"pixels", "click", "type", "key"})

    def test_eyes_only_without_cliclick(self):
        be = _backend_with(cliclick=False)
        self.assertEqual(be.capabilities(), {"pixels"})

    def test_no_capabilities_without_tools(self):
        be = _backend_with(cliclick=False, screencapture=False)
        self.assertEqual(be.capabilities(), set())

    def test_hands_degrade_gracefully_without_cliclick(self):
        be = _backend_with(cliclick=False)
        res = be.do_click_at(0.5, 0.5, "left", 1)
        self.assertFalse(res.ok)
        self.assertIn("cliclick", res.reason)


class ClickTests(unittest.TestCase):
    def test_left_click_command_and_pct_conversion(self):
        be = _backend_with(screen=(1000, 800))
        with mock.patch("afferent.backends.macos.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            res = be.do_click_at(0.80, 0.25, "left", 1)
        args = run.call_args[0][0]
        # cliclick path + "c:800,200"  (0.80*1000, 0.25*800)
        self.assertEqual(args[0], be._cliclick)
        self.assertEqual(args[1], "c:800,200")
        self.assertTrue(res.ok)
        self.assertEqual(res.final_cursor_pct, (0.80, 0.25))

    def test_right_click_uses_rc(self):
        be = _backend_with()
        with mock.patch("afferent.backends.macos.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            be.do_click_at(0.5, 0.5, "right", 1)
        self.assertTrue(run.call_args[0][0][1].startswith("rc:"))

    def test_double_click_uses_dc(self):
        be = _backend_with()
        with mock.patch("afferent.backends.macos.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            be.do_click_at(0.5, 0.5, "left", 2)
        self.assertTrue(run.call_args[0][0][1].startswith("dc:"))

    def test_nonzero_returncode_is_not_ok(self):
        be = _backend_with()
        with mock.patch("afferent.backends.macos.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=1, stdout="", stderr="denied")
            res = be.do_click_at(0.5, 0.5, "left", 1)
        self.assertFalse(res.ok)
        self.assertIn("denied", res.reason)


class TypeAndKeyTests(unittest.TestCase):
    def test_type_text(self):
        be = _backend_with()
        with mock.patch("afferent.backends.macos.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            be.do_type_text("hello", False, False)
        self.assertEqual(run.call_args[0][0][1], "t:hello")

    def test_type_text_append_enter(self):
        be = _backend_with()
        with mock.patch("afferent.backends.macos.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            be.do_type_text("hi", False, True)
        cmd = run.call_args[0][0]
        self.assertIn("t:hi", cmd)
        self.assertIn("kp:return", cmd)

    def test_key_combo_with_modifier(self):
        be = _backend_with()
        with mock.patch("afferent.backends.macos.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            be.do_key("cmd+c")
        cmd = run.call_args[0][0][1:]   # drop the cliclick path
        self.assertEqual(cmd, ["kd:cmd", "t:c", "ku:cmd"])

    def test_key_special_uses_kp(self):
        be = _backend_with()
        with mock.patch("afferent.backends.macos.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            be.do_key("return")
        self.assertEqual(run.call_args[0][0][1:], ["kp:return"])

    def test_key_combo_aliases_modifier(self):
        be = _backend_with()
        with mock.patch("afferent.backends.macos.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            be.do_key("command+shift+left")
        cmd = run.call_args[0][0][1:]
        self.assertEqual(cmd, ["kd:cmd", "kd:shift", "kp:arrow-left", "ku:shift", "ku:cmd"])

    def test_unknown_modifier_rejected(self):
        be = _backend_with()
        res = be.do_key("hyper+x")
        self.assertFalse(res.ok)
        self.assertIn("unknown modifier", res.reason)


class ObserveTests(unittest.TestCase):
    def test_observe_builds_frame_from_capture(self):
        be = _backend_with(screen=(1440, 900))
        with mock.patch("afferent.backends.macos.subprocess.run") as run, \
             mock.patch("afferent.backends.macos.os.path.exists", return_value=True), \
             mock.patch("afferent.backends.macos.os.makedirs"):
            run.return_value = mock.Mock(returncode=0, stdout="MyApp", stderr="")
            obs = be.observe()
        self.assertIsNotNone(obs.frame)
        self.assertEqual((obs.frame.width, obs.frame.height), (1440, 900))

    def test_screenshot_none_when_no_screencapture(self):
        be = _backend_with(screencapture=False)
        f = be.screenshot()
        self.assertEqual(f.id, "none")


if __name__ == "__main__":
    unittest.main(verbosity=2)
