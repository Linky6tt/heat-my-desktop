"""
Tests for desktop notification helper.
"""

import unittest
from unittest.mock import patch

from service.notify import (
    notify_emergency_failsafe,
    notify_warmup_started,
    notify_warmup_stopped,
    send_desktop_notification,
)


class TestNotify(unittest.TestCase):

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/notify-send")
    def test_send_desktop_notification(self, mock_which, mock_run):
        ok = send_desktop_notification("Test Title", "Test Message", urgency="low")
        self.assertTrue(ok)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("notify-send", args)
        self.assertIn("Test Title", args)
        self.assertIn("Test Message", args)
        self.assertIn("--urgency=low", args)
        self.assertIn("--hint=string:sound-name:", args)  # Silent hint

    @patch("service.notify.send_desktop_notification")
    def test_notify_events(self, mock_send):
        notify_warmup_started(55.0, 300, False)
        mock_send.assert_called()
        self.assertIn("Started", mock_send.call_args[0][0])

        notify_warmup_stopped(54.0, 55.0, "Completed")
        self.assertIn("Completed", mock_send.call_args[0][0])

        notify_emergency_failsafe(92.0)
        self.assertIn("Failsafe", mock_send.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
