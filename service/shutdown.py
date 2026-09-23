"""
Automatic shutdown and restart handler for CPU Thermal Controller.
Ensures that when a user restarts or powers off their PC with the app open:
1. Active heating and worker processes are immediately canceled.
2. Any systemd user service startup configuration is canceled (stopped & disabled).
3. The application cleanly closes its window, hides tray icons, and exits without blocking shutdown.
"""

import logging
import os
from pathlib import Path
import signal
import socket
import sys
from typing import Any, Callable, List, Optional

from service.systemd import (
    SingleInstanceLock,
    cancel_systemd_config,
    configure_kde_session_exclusion,
    kill_rogue_processes,
)

logger = logging.getLogger(__name__)


class SystemShutdownManager:
    """
    Coordinates multi-channel shutdown detection across:
    1. systemd-logind DBus (org.freedesktop.login1.Manager.PrepareForShutdown)
    2. Qt Session Management (commitDataRequest & saveStateRequest)
    3. POSIX Signals (SIGTERM, SIGHUP, SIGINT) via QSocketNotifier
    4. Qt application lifecycle (aboutToQuit)
    """

    def __init__(
        self,
        app: Optional[Any] = None,
        widget: Optional[Any] = None,
        engine: Optional[Any] = None,
        lock: Optional[SingleInstanceLock] = None,
        cancel_systemd_on_shutdown: bool = True,
    ) -> None:
        self.app = app
        self.widget = widget
        self.engine = engine or (getattr(widget, "engine", None) if widget else None)
        self.lock = lock
        self.cancel_systemd_on_shutdown = cancel_systemd_on_shutdown

        self._is_shutting_down = False
        self._dbus_listener: Optional[Any] = None
        self._notifier: Optional[Any] = None
        self._wsock: Optional[socket.socket] = None
        self._rsock: Optional[socket.socket] = None
        self._old_sig_handlers: dict = {}
        self._callbacks: List[Callable[[], None]] = []

    @property
    def is_shutting_down(self) -> bool:
        return self._is_shutting_down

    def add_cleanup_callback(self, callback: Callable[[], None]) -> None:
        """Registers an additional custom callback to run during shutdown."""
        self._callbacks.append(callback)

    def trigger_shutdown(self, reason: str = "unknown") -> None:
        """
        Executes immediate shutdown and cancellation sequence:
        - Cancels current heating & terminates worker processes.
        - Cancels systemd service configuration (disables & stops service).
        - Closes and hides the GUI window and tray icon.
        - Exits the application cleanly.
        """
        if self._is_shutting_down:
            return
        self._is_shutting_down = True
        logger.info("System shutdown/restart detected (reason=%s). Executing cancellation and closing...", reason)

        # 1. Cancel active heating and terminate worker processes
        try:
            if self.widget and hasattr(self.widget, "idle_timer"):
                self.widget.idle_timer.stop()
        except Exception as e:
            logger.debug("Error stopping widget idle timer: %s", e)

        try:
            target_engine = self.engine or (getattr(self.widget, "engine", None) if self.widget else None)
            if target_engine is not None:
                if hasattr(target_engine, "stop"):
                    target_engine.stop()
                if hasattr(target_engine, "generator") and hasattr(target_engine.generator, "stop_all"):
                    target_engine.generator.stop_all()
        except Exception as e:
            logger.error("Error stopping thermal engine during shutdown: %s", e)

        try:
            kill_rogue_processes(kill_current=False)
        except Exception as e:
            logger.debug("Error killing rogue processes during shutdown: %s", e)

        # 2. Cancel systemd user service configuration if requested
        if self.cancel_systemd_on_shutdown:
            try:
                ok, msg = cancel_systemd_config()
                logger.info("Systemd configuration cancellation result: ok=%s, msg=%s", ok, msg)
            except Exception as e:
                logger.error("Error canceling systemd configuration: %s", e)

        # 3. Ensure KDE Plasma session restore will not reopen the app
        try:
            configure_kde_session_exclusion()
        except Exception as e:
            logger.debug("Error configuring KDE session exclusion: %s", e)

        # 4. Run any registered external cleanup callbacks
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.debug("Error in custom shutdown callback: %s", e)

        # 5. Hide and close GUI widget and system tray icon immediately
        try:
            if self.widget is not None:
                if hasattr(self.widget, "tray_icon") and self.widget.tray_icon is not None:
                    self.widget.tray_icon.hide()
                self.widget.hide()
                self.widget.close()
        except Exception as e:
            logger.debug("Error closing widget during shutdown: %s", e)

        # 6. Release lock if acquired
        try:
            if self.lock is not None:
                self.lock.release()
        except Exception as e:
            logger.debug("Error releasing instance lock: %s", e)

        # 7. Quit Qt application cleanly
        try:
            if self.app is not None:
                self.app.quit()
        except Exception as e:
            logger.debug("Error quitting Qt application: %s", e)

    def register(self) -> None:
        """
        Sets up listeners across all available channels:
        - DBus logind PrepareForShutdown
        - Qt Session Management
        - POSIX Signals (SIGTERM, SIGHUP, SIGINT)
        - Qt aboutToQuit
        """
        self._setup_dbus_listener()
        self._setup_qt_session_manager()
        self._setup_posix_signals()
        self._setup_about_to_quit()

    def _setup_dbus_listener(self) -> None:
        """
        Subscribes to org.freedesktop.login1.Manager.PrepareForShutdown via QtDBus.
        When systemd-logind prepares to shut down or reboot, it sends PrepareForShutdown(True).
        """
        try:
            from PyQt6 import QtCore, QtDBus

            class _LogindShutdownListener(QtCore.QObject):
                def __init__(self, manager: "SystemShutdownManager") -> None:
                    super().__init__()
                    self._mgr = manager

                @QtCore.pyqtSlot(bool)
                def on_prepare_for_shutdown(self, is_shutting_down: bool) -> None:
                    if is_shutting_down:
                        logger.info("Received PrepareForShutdown(True) from systemd-logind")
                        self._mgr.trigger_shutdown(reason="systemd_logind_prepare_for_shutdown")

            bus = QtDBus.QDBusConnection.systemBus()
            if bus.isConnected():
                self._dbus_listener = _LogindShutdownListener(self)
                connected = bus.connect(
                    "org.freedesktop.login1",
                    "/org/freedesktop/login1",
                    "org.freedesktop.login1.Manager",
                    "PrepareForShutdown",
                    self._dbus_listener.on_prepare_for_shutdown,
                )
                if connected:
                    logger.debug("Successfully connected to systemd-logind PrepareForShutdown signal.")
                else:
                    logger.debug("Could not connect to systemd-logind PrepareForShutdown signal.")
        except Exception as e:
            logger.debug("QtDBus listener setup skipped: %s", e)

    def _setup_qt_session_manager(self) -> None:
        """
        Connects to Qt QSessionManager commitDataRequest and saveStateRequest.
        """
        if self.app is None:
            return

        try:
            from PyQt6.QtGui import QSessionManager

            def _handle_save_state(manager: QSessionManager) -> None:
                try:
                    manager.setRestartHint(QSessionManager.RestartHint.RestartNever)
                except Exception:
                    pass

            def _handle_commit_data(manager: QSessionManager) -> None:
                try:
                    manager.setRestartHint(QSessionManager.RestartHint.RestartNever)
                except Exception:
                    pass
                self.trigger_shutdown(reason="qt_session_commit_data")
                try:
                    manager.release()
                except Exception:
                    pass

            if hasattr(self.app, "saveStateRequest"):
                self.app.saveStateRequest.connect(_handle_save_state)
            if hasattr(self.app, "commitDataRequest"):
                self.app.commitDataRequest.connect(_handle_commit_data)
        except Exception as e:
            logger.debug("Qt session manager setup skipped: %s", e)

    def _setup_posix_signals(self) -> None:
        """
        Installs POSIX signal handlers for SIGTERM, SIGHUP, and SIGINT using a non-blocking
        socket pair and QSocketNotifier, ensuring signals wake up the Qt C++ event loop safely.
        """
        if self.app is None:
            return

        try:
            from PyQt6.QtCore import QSocketNotifier

            wsock, rsock = socket.socketpair()
            wsock.setblocking(False)
            rsock.setblocking(False)
            self._wsock = wsock
            self._rsock = rsock

            try:
                signal.set_wakeup_fd(wsock.fileno())
            except (ValueError, OSError) as e:
                logger.debug("set_wakeup_fd failed: %s", e)
                return

            def _sig_handler(signum: int, frame: Any) -> None:
                pass

            for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
                try:
                    self._old_sig_handlers[sig] = signal.signal(sig, _sig_handler)
                except Exception:
                    pass

            self._notifier = QSocketNotifier(rsock.fileno(), QSocketNotifier.Type.Read)

            def _on_socket_activated() -> None:
                if self._notifier:
                    self._notifier.setEnabled(False)
                try:
                    data = rsock.recv(1024)
                    sig_nums = list(data)
                    logger.info("Received POSIX signal(s) via wakeup socket: %s", sig_nums)
                    self.trigger_shutdown(reason=f"posix_signal_{sig_nums}")
                except Exception as e:
                    logger.debug("Error reading signal socket: %s", e)
                finally:
                    if self._notifier and not self._is_shutting_down:
                        self._notifier.setEnabled(True)

            self._notifier.activated.connect(_on_socket_activated)
        except Exception as e:
            logger.debug("POSIX signal notifier setup skipped: %s", e)

    def _setup_about_to_quit(self) -> None:
        """
        Connects to QCoreApplication.aboutToQuit as a fallback failsafe.
        """
        if self.app is None:
            return

        try:
            def _on_about_to_quit() -> None:
                self.trigger_shutdown(reason="app_about_to_quit")

            if hasattr(self.app, "aboutToQuit"):
                self.app.aboutToQuit.connect(_on_about_to_quit)
        except Exception as e:
            logger.debug("aboutToQuit setup skipped: %s", e)

    def cleanup(self) -> None:
        """Cleans up sockets, notifiers, and restores original signal handlers."""
        if self._wsock is not None:
            try:
                signal.set_wakeup_fd(-1)
            except Exception:
                pass

        for sig, old_h in self._old_sig_handlers.items():
            try:
                signal.signal(sig, old_h)
            except Exception:
                pass
        self._old_sig_handlers.clear()

        if self._notifier is not None:
            try:
                self._notifier.setEnabled(False)
            except Exception:
                pass
            self._notifier = None

        if self._wsock is not None:
            try:
                self._wsock.close()
            except Exception:
                pass
            self._wsock = None

        if self._rsock is not None:
            try:
                self._rsock.close()
            except Exception:
                pass
            self._rsock = None
