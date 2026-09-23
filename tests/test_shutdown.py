"""
Tests for automatic shutdown/restart handling and cancellation.
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import signal
import socket
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

from service.shutdown import SystemShutdownManager
from service.systemd import SingleInstanceLock, cancel_systemd_config

app = QApplication.instance() or QApplication([])


class TestShutdownHandling(unittest.TestCase):

    @patch("service.systemd.stop_user_service", return_value=(True, "Stopped"))
    @patch("service.systemd.disable_user_service", return_value=(True, "Disabled"))
    def test_cancel_systemd_config(self, mock_disable, mock_stop):
        ok, msg = cancel_systemd_config()
        self.assertTrue(ok)
        self.assertIn("Stopped", msg)
        self.assertIn("Disabled", msg)
        mock_stop.assert_called_once()
        mock_disable.assert_called_once()

    @patch("service.shutdown.cancel_systemd_config", return_value=(True, "OK"))
    @patch("service.shutdown.kill_rogue_processes", return_value=0)
    @patch("service.shutdown.configure_kde_session_exclusion", return_value=True)
    def test_shutdown_manager_trigger_shutdown(self, mock_kde, mock_kill, mock_cancel):
        mock_app = MagicMock()
        mock_widget = MagicMock()
        mock_engine = MagicMock()
        mock_generator = MagicMock()
        mock_engine.generator = mock_generator
        mock_widget.engine = mock_engine
        mock_widget.tray_icon = MagicMock()
        mock_widget.idle_timer = MagicMock()
        mock_lock = MagicMock()

        custom_callback = MagicMock()

        mgr = SystemShutdownManager(
            app=mock_app,
            widget=mock_widget,
            engine=mock_engine,
            lock=mock_lock,
            cancel_systemd_on_shutdown=True,
        )
        mgr.add_cleanup_callback(custom_callback)

        self.assertFalse(mgr.is_shutting_down)

        mgr.trigger_shutdown(reason="test_shutdown")

        self.assertTrue(mgr.is_shutting_down)
        mock_widget.idle_timer.stop.assert_called_once()
        mock_engine.stop.assert_called_once()
        mock_generator.stop_all.assert_called_once()
        mock_kill.assert_called_once_with(kill_current=False)
        mock_cancel.assert_called_once()
        mock_kde.assert_called_once()
        custom_callback.assert_called_once()
        mock_widget.tray_icon.hide.assert_called_once()
        mock_widget.hide.assert_called_once()
        mock_widget.close.assert_called_once()
        mock_lock.release.assert_called_once()
        mock_app.quit.assert_called_once()

        # Re-entrant call should be ignored
        mgr.trigger_shutdown(reason="second_call")
        self.assertEqual(mock_engine.stop.call_count, 1)

    @patch("service.shutdown.cancel_systemd_config", return_value=(True, "OK"))
    @patch("service.shutdown.kill_rogue_processes", return_value=0)
    @patch("service.shutdown.configure_kde_session_exclusion", return_value=True)
    def test_logind_prepare_for_shutdown_signal(self, mock_kde, mock_kill, mock_cancel):
        mock_app = MagicMock()
        mgr = SystemShutdownManager(app=mock_app)

        with patch.object(mgr, "trigger_shutdown") as mock_trigger:
            mgr._setup_dbus_listener()
            listener = mgr._dbus_listener
            if listener is not None:
                # PrepareForShutdown(False) indicates canceled shutdown
                listener.on_prepare_for_shutdown(False)
                mock_trigger.assert_not_called()

                # PrepareForShutdown(True) indicates PC is turning off or restarting
                listener.on_prepare_for_shutdown(True)
                mock_trigger.assert_called_once_with(reason="systemd_logind_prepare_for_shutdown")

    @patch("service.shutdown.cancel_systemd_config", return_value=(True, "OK"))
    @patch("service.shutdown.kill_rogue_processes", return_value=0)
    @patch("service.shutdown.configure_kde_session_exclusion", return_value=True)
    def test_qt_session_commit_data_handling(self, mock_kde, mock_kill, mock_cancel):
        mock_app = MagicMock()
        mgr = SystemShutdownManager(app=mock_app)

        with patch.object(mgr, "trigger_shutdown") as mock_trigger:
            mgr._setup_qt_session_manager()

            # Retrieve the commitData handler passed to connect
            self.assertTrue(mock_app.commitDataRequest.connect.called)
            commit_handler = mock_app.commitDataRequest.connect.call_args[0][0]

            mock_session_mgr = MagicMock()
            commit_handler(mock_session_mgr)

            mock_trigger.assert_called_once_with(reason="qt_session_commit_data")
            mock_session_mgr.setRestartHint.assert_called_once()
            mock_session_mgr.release.assert_called_once()

    def test_manager_cleanup(self):
        mock_app = MagicMock()
        mgr = SystemShutdownManager(app=mock_app)
        mgr._setup_posix_signals()

        # Check sockets initialized
        self.assertIsNotNone(mgr._wsock)
        self.assertIsNotNone(mgr._rsock)

        mgr.cleanup()

        self.assertIsNone(mgr._wsock)
        self.assertIsNone(mgr._rsock)
        self.assertIsNone(mgr._notifier)


if __name__ == "__main__":
    unittest.main()
