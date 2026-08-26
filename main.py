#!/usr/bin/env python3
"""
CPU Thermal Controller & Warmup Application Entrypoint.
Supports both modern GNOME-styled PyQt6 GUI widget and headless startup daemon.
"""

import os
import sys

from cli import build_parser, print_sensor_status, run_headless_daemon
from service.systemd import (
    disable_user_service,
    enable_user_service,
    generate_service_content,
    install_user_service,
    uninstall_user_service,
)
from thermal.config import ThermalConfig


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # 1. Quick utility actions
    if args.status:
        print_sensor_status()
        return 0

    # Load saved base config
    config = ThermalConfig.load_from_file()

    # Override with explicit CLI arguments if provided
    if args.target is not None:
        config.target_temp_c = args.target
    if args.duration is not None:
        config.duration_seconds = args.duration
    if args.maintain is not None:
        config.maintain_after_warmup = args.maintain
    if args.sensor is not None:
        config.sensor_name = args.sensor

    # Validate configuration (enforce strictly <= 90.0°C for daemon / headless mode)
    is_headless_mode = bool(args.headless or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")))
    try:
        config.validate(is_daemon=is_headless_mode)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # 2. Systemd service management actions
    if args.generate_service:
        print(generate_service_content(config))
        return 0

    if args.install_service:
        path = install_user_service(config)
        print(f"Installed systemd service unit to: {path}")
        return 0

    if args.uninstall_service:
        ok, msg = uninstall_user_service()
        print(msg)
        return 0 if ok else 1

    if args.enable_service:
        install_user_service(config)
        ok, msg = enable_user_service()
        print(msg)
        return 0 if ok else 1

    if args.disable_service:
        ok, msg = disable_user_service()
        print(msg)
        return 0 if ok else 1

    # 3. Headless Daemon Mode vs GUI Mode
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if args.headless or not has_display:
        if not has_display and not args.headless:
            print("No X11 or Wayland display detected. Falling back to headless daemon mode.")
        return run_headless_daemon(config)

    # 4. Launch PyQt6 GUI Application
    try:
        from PyQt6.QtWidgets import QApplication
        from gui.style import get_icon
        from gui.widget import ThermalWidget

        app = QApplication(sys.argv)
        app.setApplicationName("CPU Thermal Controller")
        app.setApplicationDisplayName("CPU Thermal Controller & Warmup")
        app.setWindowIcon(get_icon("flame", 64))

        widget = ThermalWidget(config=config)
        widget.show()

        return app.exec()
    except ImportError as e:
        print(f"PyQt6 is required for GUI mode ({e}). Falling back to headless mode.", file=sys.stderr)
        return run_headless_daemon(config)


if __name__ == "__main__":
    sys.exit(main())
