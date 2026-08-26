"""
Desktop notification helper for CPU Thermal Controller.
Sends silent/low-urgency notifications on warmup start, stop, and emergency failsafe.
"""

import logging
import os
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def send_desktop_notification(
    title: str,
    message: str,
    urgency: str = "low",
    timeout_ms: int = 4000,
    icon: str = "dialog-information",
) -> bool:
    """
    Sends a desktop notification using notify-send.
    Default urgency is 'low' with hints to remain silent by default.
    """
    if not shutil.which("notify-send"):
        logger.debug("notify-send binary not found on system.")
        return False

    # Check if DBUS session or display is available
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        logger.debug("No DBUS or display environment found for desktop notifications.")
        return False

    cmd = [
        "notify-send",
        "--app-name=CPU Thermal Controller",
        f"--urgency={urgency}",
        f"--expire-time={timeout_ms}",
        f"--icon={icon}",
        "--hint=int:transient:1",
        "--hint=string:sound-name:",  # Silent notification hint
        title,
        message,
    ]

    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=2.0)
        return True
    except Exception as e:
        logger.debug("Failed to send desktop notification: %s", e)
        return False


def notify_warmup_started(target_temp_c: float, duration_seconds: int, maintain: bool) -> None:
    """Notifies user that CPU warmup has started."""
    mins = duration_seconds // 60
    secs = duration_seconds % 60
    time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
    maintain_str = "ON" if maintain else "OFF"
    title = "CPU Warmup Started"
    body = f"Target: {target_temp_c:.1f}°C | Duration: {time_str} | Maintain: {maintain_str}"
    send_desktop_notification(title, body, urgency="low", icon="weather-clear")


def notify_warmup_stopped(final_temp_c: float, target_temp_c: float, state_name: str) -> None:
    """Notifies user that CPU warmup has stopped or finished."""
    title = f"CPU Warmup {state_name.capitalize()}"
    body = f"Final CPU Temp: {final_temp_c:.1f}°C (Target: {target_temp_c:.1f}°C)"
    send_desktop_notification(title, body, urgency="low", icon="weather-clear")


def notify_emergency_failsafe(current_temp_c: float) -> None:
    """Notifies user that critical 90°C emergency kill-switch triggered."""
    title = "CPU Thermal Failsafe Triggered"
    body = f"CPU reached {current_temp_c:.1f}°C (>= 90.0°C)! All heating workers terminated."
    send_desktop_notification(title, body, urgency="critical", icon="dialog-warning")


def notify_already_at_target(current_temp_c: float = 0.0, target_temp_c: float = 0.0) -> None:
    """Notifies user that CPU is already at or above target temperature."""
    title = "Heat My Desktop"
    body = "CPU is already at or above target temperature"
    send_desktop_notification(title, body, urgency="low", icon="dialog-information")

