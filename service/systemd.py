"""
Systemd unit file generator and service manager for CPU Thermal Controller.
Generates ~/.config/systemd/user/heat-my-desktop.service for headless startup.
"""

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Optional, Tuple

from thermal.config import ThermalConfig

SERVICE_UNIT_NAME = "heat-my-desktop.service"
LEGACY_SERVICE_UNIT_NAMES = ["cpu-thermal-warmup.service"]
ALL_SERVICE_UNIT_NAMES = [SERVICE_UNIT_NAME] + LEGACY_SERVICE_UNIT_NAMES


class SingleInstanceLock:
    """
    File-based advisory lock to prevent multiple conflicting instances
    of heat-my-desktop from running simultaneously.
    """

    def __init__(self, name: str = "heat-my-desktop.lock") -> None:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if runtime_dir and Path(runtime_dir).exists():
            self.lock_path = Path(runtime_dir) / name
        else:
            self.lock_path = Path.home() / ".config" / "cpu_thermal_controller" / name
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd: Optional[int] = None

    def acquire(self) -> bool:
        try:
            import fcntl
            self._fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(self._fd, 0)
            os.write(self._fd, f"{os.getpid()}\n".encode())
            return True
        except (IOError, OSError):
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except Exception:
                    pass
                self._fd = None
            return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None


def kill_rogue_processes(kill_current: bool = False) -> int:
    """
    Terminates any orphan FPU heat workers, conflicting heat-my-desktop or
    legacy cpu-thermal-warmup python daemon processes, and stops conflicting systemd units.
    Returns the number of killed processes.
    """
    current_pid = os.getpid()
    killed_count = 0

    # 1. Stop all systemd units
    if shutil.which("systemctl"):
        for unit in ALL_SERVICE_UNIT_NAMES:
            try:
                subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, check=False)
            except Exception:
                pass

    # 2. Search /proc for rogue/orphan processes
    proc_path = Path("/proc")
    pids_to_kill = []
    if proc_path.exists():
        for entry in proc_path.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid == current_pid and not kill_current:
                continue
            try:
                cmdline_file = entry / "cmdline"
                if not cmdline_file.exists():
                    continue
                cmdline = cmdline_file.read_bytes().replace(b"\x00", b" ").decode(errors="ignore")

                is_worker = "_fpu_heat_worker" in cmdline
                is_daemon = (
                    ("heat-my-desktop" in cmdline or "cpu-thermal-warmup" in cmdline)
                    and ("main.py" in cmdline or "cli.py" in cmdline)
                )

                if is_worker or is_daemon:
                    pids_to_kill.append(pid)
            except (PermissionError, ProcessLookupError, FileNotFoundError):
                continue

    # 3. Terminate identified processes (SIGTERM, then SIGKILL)
    for pid in pids_to_kill:
        try:
            os.kill(pid, signal.SIGTERM)
            killed_count += 1
        except ProcessLookupError:
            pass
        except Exception:
            pass

    if pids_to_kill:
        time.sleep(0.15)
        for pid in pids_to_kill:
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception:
                pass

    return killed_count


def configure_kde_session_exclusion() -> bool:
    """
    Configures KDE Plasma session manager (ksmserver) to explicitly exclude
    heat-my-desktop so that restarting the PC with the app open will never
    restore or auto-launch the application on next login.
    """
    ksm_path = Path.home() / ".config" / "ksmserverrc"
    if not ksm_path.parent.exists():
        return False
    try:
        lines = []
        if ksm_path.exists():
            lines = ksm_path.read_text(encoding="utf-8").splitlines()

        general_idx = -1
        exclude_idx = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "[General]":
                general_idx = i
            elif general_idx != -1 and stripped.startswith("["):
                break
            elif general_idx != -1 and stripped.startswith("excludeApps="):
                exclude_idx = i

        target_app = "heat-my-desktop"
        if exclude_idx != -1:
            curr_val = lines[exclude_idx].split("=", 1)[1]
            apps = [a.strip() for a in curr_val.split(",") if a.strip()]
            if target_app not in apps:
                apps.append(target_app)
                lines[exclude_idx] = f"excludeApps={','.join(apps)}"
        elif general_idx != -1:
            lines.insert(general_idx + 1, f"excludeApps={target_app}")
        else:
            lines.append("[General]")
            lines.append(f"excludeApps={target_app}")

        ksm_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def stop_user_service() -> Tuple[bool, str]:
    """Stops all recognized thermal controller user systemd services."""
    if not shutil.which("systemctl"):
        return False, "systemctl command not found on this system."
    for unit in ALL_SERVICE_UNIT_NAMES:
        try:
            subprocess.run(["systemctl", "--user", "stop", unit], capture_output=True, check=False)
        except Exception:
            pass
    return True, "Thermal controller services stopped."


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

    # Clean up rogue processes and orphan workers before installing
    kill_rogue_processes(kill_current=False)

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


def cancel_systemd_config() -> Tuple[bool, str]:
    """
    Cancels any active or boot-enabled systemd service configuration.
    Stops all thermal user services and disables them from starting on boot.
    """
    stop_ok, stop_msg = stop_user_service()
    dis_ok, dis_msg = disable_user_service()
    return (stop_ok and dis_ok), f"Stopped: {stop_msg}; Disabled: {dis_msg}"


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

    # Terminate any rogue processes and orphan workers
    kill_rogue_processes(kill_current=False)

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
