"""
Systemd unit file generator and service manager for CPU Thermal Controller.
Generates ~/.config/systemd/user/heat-my-desktop.service for headless startup.
"""

from pathlib import Path
import shutil
import subprocess
import sys
from typing import Optional, Tuple

from thermal.config import ThermalConfig

SERVICE_UNIT_NAME = "heat-my-desktop.service"
LEGACY_SERVICE_UNIT_NAMES = ["cpu-thermal-warmup.service"]
ALL_SERVICE_UNIT_NAMES = [SERVICE_UNIT_NAME] + LEGACY_SERVICE_UNIT_NAMES


def get_default_service_dir() -> Path:
    """Returns ~/.config/systemd/user directory."""
    return Path.home() / ".config" / "systemd" / "user"


def generate_service_content(
    config: ThermalConfig,
    python_bin: Optional[str] = None,
    entrypoint_script: Optional[Path] = None,
) -> str:
    """
    Generates systemd unit file content with CLI arguments matching configuration.
    """
    py_exec = python_bin or sys.executable
    script_path = entrypoint_script or (Path(__file__).resolve().parent.parent / "main.py")
    script_abs = script_path.resolve()

    args = [
        str(py_exec),
        str(script_abs),
        "--headless",
        f"--target {config.target_temp_c:.1f}",
        f"--duration {config.duration_seconds}",
    ]
    if config.maintain_after_warmup:
        args.append("--maintain")
    else:
        args.append("--no-maintain")
    if config.sensor_name:
        args.append(f"--sensor \"{config.sensor_name}\"")

    exec_start_cmd = " ".join(args)

    content = f"""[Unit]
Description=CPU Thermal Controller and Warmup Headless Service
Documentation=https://github.com/
After=basic.target

[Service]
Type=simple
ExecStart={exec_start_cmd}
Restart=on-failure
RestartSec=5s
RestartPreventExitStatus=2
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    return content


def install_user_service(
    config: ThermalConfig,
    destination_dir: Optional[Path] = None,
) -> Path:
    """
    Writes the systemd service unit file to user systemd directory.
    Checks and stops/disables any existing or legacy service before installing.
    """
    dest_dir = destination_dir or get_default_service_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    service_file = dest_dir / SERVICE_UNIT_NAME

    # If any service (primary or legacy) is already active, stop it first
    if shutil.which("systemctl"):
        for unit in ALL_SERVICE_UNIT_NAMES:
            try:
                subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, check=False)
            except Exception:
                pass

    # Clean up any legacy unit files and disable them
    for legacy_name in LEGACY_SERVICE_UNIT_NAMES:
        legacy_file = dest_dir / legacy_name
        if legacy_file.exists():
            if shutil.which("systemctl"):
                try:
                    subprocess.run(["systemctl", "--user", "disable", "--now", legacy_name], capture_output=True, check=False)
                except Exception:
                    pass
            try:
                legacy_file.unlink()
            except Exception:
                pass

    content = generate_service_content(config)
    service_file.write_text(content, encoding="utf-8")

    # Reload systemd daemon if systemctl is available
    if shutil.which("systemctl"):
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
        except Exception:
            pass

    return service_file


def enable_user_service(destination_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Enables and starts the user systemd service via systemctl --user.
    Checks if any existing or legacy service is installed, disables/cleans up legacy services,
    and restarts the active service to ensure new configuration takes immediate effect.
    """
    if not shutil.which("systemctl"):
        return False, "systemctl command not found on this system."

    dest_dir = destination_dir or get_default_service_dir()

    # Clean up legacy services (e.g. cpu-thermal-warmup.service)
    for legacy_name in LEGACY_SERVICE_UNIT_NAMES:
        legacy_file = dest_dir / legacy_name
        try:
            subprocess.run(["systemctl", "--user", "disable", "--now", legacy_name], capture_output=True, check=False)
            subprocess.run(["systemctl", "--user", "stop", legacy_name], capture_output=True, check=False)
        except Exception:
            pass
        if legacy_file.exists():
            try:
                legacy_file.unlink()
            except Exception:
                pass

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=False)

        res = subprocess.run(
            ["systemctl", "--user", "enable", "--now", SERVICE_UNIT_NAME],
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode != 0:
            return False, f"Failed to enable service: {res.stderr.strip()}"

        # Restart service in case it was already active with old configuration arguments
        subprocess.run(["systemctl", "--user", "restart", SERVICE_UNIT_NAME], capture_output=True, check=False)

        return True, f"Service {SERVICE_UNIT_NAME} enabled and started successfully."
    except Exception as e:
        return False, f"Error enabling service: {e}"


def disable_user_service() -> Tuple[bool, str]:
    """
    Stops and disables the user systemd service across current and legacy units.
    """
    if not shutil.which("systemctl"):
        return False, "systemctl command not found on this system."

    errors = []
    for unit in ALL_SERVICE_UNIT_NAMES:
        try:
            res = subprocess.run(
                ["systemctl", "--user", "disable", "--now", unit],
                capture_output=True,
                text=True,
                check=False
            )
            subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, check=False)
            if res.returncode != 0:
                err = res.stderr.strip()
                if "not loaded" not in err.lower() and "no such file" not in err.lower() and unit == SERVICE_UNIT_NAME:
                    errors.append(err)
        except Exception as e:
            if unit == SERVICE_UNIT_NAME:
                errors.append(str(e))

    if errors:
        return False, f"Failed to disable service: {'; '.join(errors)}"
    return True, f"Service {SERVICE_UNIT_NAME} disabled successfully."


def is_service_installed(destination_dir: Optional[Path] = None) -> bool:
    """
    Checks if any systemd unit file (current or legacy) currently exists in the user service directory.
    """
    dest_dir = destination_dir or get_default_service_dir()
    for unit in ALL_SERVICE_UNIT_NAMES:
        if (dest_dir / unit).exists():
            return True
    return False


def uninstall_user_service(destination_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Stops, disables, and deletes all systemd user service unit files (current and legacy).
    """
    dest_dir = destination_dir or get_default_service_dir()

    # First disable and stop all current and legacy services if running
    if shutil.which("systemctl"):
        for unit in ALL_SERVICE_UNIT_NAMES:
            try:
                subprocess.run(
                    ["systemctl", "--user", "disable", "--now", unit],
                    capture_output=True,
                    check=False
                )
                subprocess.run(
                    ["systemctl", "--user", "stop", unit],
                    capture_output=True,
                    check=False
                )
            except Exception:
                pass

    # Delete all service files
    errors = []
    for unit in ALL_SERVICE_UNIT_NAMES:
        service_file = dest_dir / unit
        if service_file.exists():
            try:
                service_file.unlink()
            except Exception as e:
                errors.append(f"Failed to delete {unit}: {e}")

    # Reload systemd daemon
    if shutil.which("systemctl"):
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
            subprocess.run(["systemctl", "--user", "reset-failed"], check=False, capture_output=True)
        except Exception:
            pass

    if errors:
        return False, "; ".join(errors)
    return True, f"Service {SERVICE_UNIT_NAME} uninstalled successfully."


def get_service_status() -> Tuple[bool, str]:
    """
    Checks the status of the user systemd service across current and legacy units.
    """
    if not shutil.which("systemctl"):
        return False, "systemctl command not available."

    for unit in ALL_SERVICE_UNIT_NAMES:
        try:
            res = subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                capture_output=True,
                text=True,
                check=False
            )
            status_str = res.stdout.strip()
            if status_str == "active":
                return True, f"active ({unit})"
        except Exception:
            pass

    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_UNIT_NAME],
            capture_output=True,
            text=True,
            check=False
        )
        return False, res.stdout.strip()
    except Exception as e:
        return False, str(e)


def is_service_enabled() -> bool:
    """
    Checks if any recognized user systemd service (current or legacy) is enabled on boot.
    """
    if not shutil.which("systemctl"):
        return False

    for unit in ALL_SERVICE_UNIT_NAMES:
        try:
            res = subprocess.run(
                ["systemctl", "--user", "is-enabled", unit],
                capture_output=True,
                text=True,
                check=False
            )
            if res.stdout.strip() == "enabled":
                return True
        except Exception:
            pass
    return False
