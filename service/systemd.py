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
    if config.sensor_name:
        args.append(f"--sensor \"{config.sensor_name}\"")

    exec_start_cmd = " ".join(args)

    content = f"""[Unit]
Description=CPU Thermal Controller and Warmup Headless Service
Documentation=https://github.com/
After=default.target

[Service]
Type=simple
ExecStart={exec_start_cmd}
Restart=on-failure
RestartSec=5s
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
    """
    dest_dir = destination_dir or get_default_service_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    service_file = dest_dir / SERVICE_UNIT_NAME
    
    content = generate_service_content(config)
    service_file.write_text(content, encoding="utf-8")
    
    # Reload systemd daemon if systemctl is available
    if shutil.which("systemctl"):
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
        except Exception:
            pass

    return service_file


def enable_user_service() -> Tuple[bool, str]:
    """
    Enables and starts the user systemd service via systemctl --user.
    """
    if not shutil.which("systemctl"):
        return False, "systemctl command not found on this system."

    try:
        res = subprocess.run(
            ["systemctl", "--user", "enable", "--now", SERVICE_UNIT_NAME],
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            return True, f"Service {SERVICE_UNIT_NAME} enabled and started successfully."
        return False, f"Failed to enable service: {res.stderr.strip()}"
    except Exception as e:
        return False, f"Error enabling service: {e}"


def disable_user_service() -> Tuple[bool, str]:
    """
    Stops and disables the user systemd service.
    """
    if not shutil.which("systemctl"):
        return False, "systemctl command not found on this system."

    try:
        res = subprocess.run(
            ["systemctl", "--user", "disable", "--now", SERVICE_UNIT_NAME],
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            return True, f"Service {SERVICE_UNIT_NAME} disabled successfully."
        return False, f"Failed to disable service: {res.stderr.strip()}"
    except Exception as e:
        return False, f"Error disabling service: {e}"


def is_service_installed(destination_dir: Optional[Path] = None) -> bool:
    """
    Checks if the systemd unit file currently exists in the user service directory.
    """
    dest_dir = destination_dir or get_default_service_dir()
    service_file = dest_dir / SERVICE_UNIT_NAME
    return service_file.exists()


def uninstall_user_service(destination_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Stops, disables, and deletes the systemd user service unit file.
    """
    dest_dir = destination_dir or get_default_service_dir()
    service_file = dest_dir / SERVICE_UNIT_NAME

    # First disable/stop service if running
    if shutil.which("systemctl"):
        try:
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", SERVICE_UNIT_NAME],
                capture_output=True,
                check=False
            )
        except Exception:
            pass

    # Delete the service file
    if service_file.exists():
        try:
            service_file.unlink()
        except Exception as e:
            return False, f"Failed to delete service file: {e}"

    # Reload systemd daemon
    if shutil.which("systemctl"):
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
            subprocess.run(["systemctl", "--user", "reset-failed"], check=False, capture_output=True)
        except Exception:
            pass

    return True, f"Service {SERVICE_UNIT_NAME} uninstalled successfully."


def get_service_status() -> Tuple[bool, str]:
    """
    Checks the status of the user systemd service.
    """
    if not shutil.which("systemctl"):
        return False, "systemctl command not available."

    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_UNIT_NAME],
            capture_output=True,
            text=True,
            check=False
        )
        status_str = res.stdout.strip()
        is_active = (status_str == "active")
        return is_active, status_str
    except Exception as e:
        return False, str(e)


def is_service_enabled() -> bool:
    """
    Checks if the user systemd service is enabled on boot.
    """
    if not shutil.which("systemctl"):
        return False

    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-enabled", SERVICE_UNIT_NAME],
            capture_output=True,
            text=True,
            check=False
        )
        return res.stdout.strip() == "enabled"
    except Exception:
        return False
