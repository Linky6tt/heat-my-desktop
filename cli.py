"""
Headless CLI and Daemon runner for CPU Thermal Controller.
Executes warmup trajectory in background/service without requiring graphical display.
"""

import argparse
import logging
import signal
import sys
import time
from typing import List, Optional

from service.systemd import (
    disable_user_service,
    enable_user_service,
    generate_service_content,
    get_service_status,
    install_user_service,
)
from thermal.config import ConfigConstraints, ThermalConfig
from thermal.engine import EngineState, ThermalEngine, ThermalStatus
from thermal.monitor import TemperatureMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("thermal_daemon")


def print_sensor_status() -> None:
    """Prints current hardware sensors and detected primary CPU temperature."""
    monitor = TemperatureMonitor()
    readings = monitor.fetch_all_temperatures()
    print("=" * 60)
    print("DETECTED HARDWARE SENSORS")
    print("=" * 60)
    if not readings:
        print("No temperature sensors detected.")
        return

    primary_key = monitor.detect_cpu_sensor_key(readings)
    for key, val in sorted(readings.items()):
        marker = " <-- PRIMARY CPU SENSOR" if key == primary_key else ""
        print(f"  • {key:40s} : {val:5.1f} °C{marker}")
    print("=" * 60)


def check_target_reached(final_temp_c: float, target_temp_c: float, tolerance_c: float = 1.5) -> bool:
    """
    Checks if final temperature is within tolerance of target temperature.
    """
    return abs(final_temp_c - target_temp_c) <= tolerance_c


def run_headless_daemon(config: ThermalConfig) -> int:
    """
    Executes the thermal warmup and maintenance control loop headlessly.
    """
    logger.info("Starting Headless CPU Thermal Controller")
    logger.info(
        "Config: Target=%.1f°C, Duration=%ds, Maintain=%s, Sensor=%s",
        config.target_temp_c,
        config.duration_seconds,
        config.maintain_after_warmup,
        config.sensor_name or "Auto",
    )

    monitor = TemperatureMonitor(preferred_sensor=config.sensor_name)
    engine = ThermalEngine(config=config, monitor=monitor)

    stop_requested = False

    def handle_signal(signum, frame):
        nonlocal stop_requested
        logger.info("Received signal %d; shutting down engine...", signum)
        stop_requested = True
        engine.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    def on_tick_log(status: ThermalStatus) -> None:
        state_str = status.state.value
        elapsed_str = f"{int(status.elapsed_seconds)}s/{status.total_duration_seconds}s"
        logger.info(
            "[%s] CPU: %5.1f°C | Expected: %5.1f°C | Target: %5.1f°C | Workers: %d/%d | Time: %s",
            state_str,
            status.current_temp_c,
            status.expected_temp_c,
            status.target_temp_c,
            status.active_workers,
            status.max_workers,
            elapsed_str,
        )

    current_idle = monitor.read_cpu_temperature()
    if current_idle is not None and config.target_temp_c <= current_idle:
        logger.info(
            "CPU is already at or above target temperature (Target: %.1f°C <= Current: %.1f°C).",
            config.target_temp_c,
            current_idle,
        )
        from service.notify import notify_already_at_target
        try:
            notify_already_at_target(current_idle, config.target_temp_c)
        except Exception:
            pass
        logger.info("Gracefully exiting.")
        return 0

    started = engine.start(config)
    if not started:
        logger.error("Failed to start ThermalEngine.")
        return 1

    try:
        while engine.is_running and not stop_requested:
            time.sleep(ConfigConstraints.SAMPLE_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        engine.stop()

    last_st = engine.last_status
    final_temp = last_st.current_temp_c if last_st else (monitor.read_cpu_temperature() or 40.0)
    failsafe = last_st.failsafe_triggered if last_st else False

    if failsafe:
        logger.critical("Engine terminated due to 90°C failsafe kill-switch!")
        logger.info("Target temperature was not reached.")
        return 2

    if check_target_reached(final_temp, config.target_temp_c):
        logger.info("Target temperature reached.")
    else:
        logger.info("Target temperature was not reached.")

    logger.info("Daemon finished.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CPU Thermal Controller & Warmup Widget / Startup Daemon",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless daemon mode without launching GUI widget.",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=None,
        help=f"Target temperature in °C ({ConfigConstraints.MIN_TARGET_TEMP_C} to {ConfigConstraints.MAX_TARGET_TEMP_C}).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help=f"Warmup duration in seconds (1 to {ConfigConstraints.MAX_DURATION_SECONDS}).",
    )
    parser.add_argument(
        "--maintain",
        action="store_true",
        default=None,
        help="Maintain target temperature after warmup timeframe completes.",
    )
    parser.add_argument(
        "--sensor",
        type=str,
        default=None,
        help="Specific sensor identifier (e.g. 'k10temp-pci-00c3::Tctl').",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print current temperature sensor readings and exit.",
    )
    parser.add_argument(
        "--generate-service",
        action="store_true",
        help="Print systemd user service file content and exit.",
    )
    parser.add_argument(
        "--install-service",
        action="store_true",
        help="Install systemd user service unit file and exit.",
    )
    parser.add_argument(
        "--uninstall-service",
        action="store_true",
        help="Stop, disable, and remove systemd user service unit file and exit.",
    )
    parser.add_argument(
        "--enable-service",
        action="store_true",
        help="Enable and start user systemd startup service.",
    )
    parser.add_argument(
        "--disable-service",
        action="store_true",
        help="Disable and stop user systemd startup service.",
    )
    return parser
