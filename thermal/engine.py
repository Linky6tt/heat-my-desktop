"""
Thermal Controller Engine.
Calculates target temperature rate curve, scales FPU workers every 0.5s,
and enforces hardcoded 90°C failsafe kill-switch.
"""

from dataclasses import dataclass
from enum import Enum
import logging
import threading
import time
from typing import Callable, Optional

from .config import ConfigConstraints, ThermalConfig
from .generator import HeatGenerator
from .monitor import TemperatureMonitor
from service.notify import (
    notify_already_at_target,
    notify_emergency_failsafe,
    notify_warmup_started,
    notify_warmup_stopped,
)

logger = logging.getLogger(__name__)


class EngineState(str, Enum):
    IDLE = "IDLE"
    WARMUP = "WARMUP"
    MAINTAINING = "MAINTAINING"
    COMPLETED = "COMPLETED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass
class ThermalStatus:
    """Snapshot of engine status emitted every tick (0.5s)."""
    current_temp_c: float
    expected_temp_c: float
    target_temp_c: float
    start_temp_c: float
    elapsed_seconds: float
    total_duration_seconds: int
    active_workers: int
    max_workers: int
    state: EngineState
    failsafe_triggered: bool = False
    message: str = ""


class ThermalEngine:
    """
    Core engine managing the warmup trajectory, 0.5s monitor loop,
    proportional worker scaling, and failsafe safety stops.
    """

    def __init__(
        self,
        config: Optional[ThermalConfig] = None,
        monitor: Optional[TemperatureMonitor] = None,
        generator: Optional[HeatGenerator] = None,
        on_tick: Optional[Callable[[ThermalStatus], None]] = None,
    ) -> None:
        self.config = config or ThermalConfig()
        self.monitor = monitor or TemperatureMonitor(preferred_sensor=self.config.sensor_name)
        self.generator = generator or HeatGenerator()
        self.on_tick = on_tick

        self._state: EngineState = EngineState.IDLE
        self._start_time: float = 0.0
        self._start_temp_c: float = 0.0
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_status: Optional[ThermalStatus] = None

    @property
    def state(self) -> EngineState:
        with self._lock:
            return self._state

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def last_status(self) -> Optional[ThermalStatus]:
        with self._lock:
            return self._last_status

    def calculate_expected_temperature(self, elapsed_seconds: float) -> float:
        """
        Calculates the expected temperature at timestamp t along the target rate curve.
        T_expected(t) = T_start + (elapsed / total_duration) * (T_target - T_start)
        """
        duration = max(1, self.config.duration_seconds)
        if elapsed_seconds >= duration:
            return self.config.target_temp_c

        progress = max(0.0, min(1.0, elapsed_seconds / float(duration)))
        expected = self._start_temp_c + progress * (self.config.target_temp_c - self._start_temp_c)
        return expected

    def start(self, config: Optional[ThermalConfig] = None) -> bool:
        """
        Starts the thermal warmup controller.
        """
        with self._lock:
            if self._running:
                logger.warning("Engine is already running.")
                return False

            if config:
                self.config = config
                self.config.validate()
                self.monitor.preferred_sensor = self.config.sensor_name

            # Read initial temperature
            initial_temp = self.monitor.read_cpu_temperature()
            if initial_temp is None:
                # If cannot read temp, fallback to reasonable ambient estimate or log error
                initial_temp = 35.0
                logger.warning("Could not read initial CPU temp; using 35.0°C fallback.")

            # Determine active failsafe threshold (90°C standard, or 100°C extreme testing mode)
            failsafe_limit = (
                ConfigConstraints.EXTREME_MAX_TARGET_TEMP_C
                if self.config.allow_extreme_temp
                else ConfigConstraints.CRITICAL_FAILSAFE_TEMP_C
            )

            # Check critical failsafe right at start
            if initial_temp >= failsafe_limit:
                self._state = EngineState.EMERGENCY_STOP
                logger.error("Initial temperature %.1f°C exceeds safety limit %.1f°C! Aborting.", initial_temp, failsafe_limit)
                return False

            # Check if target temperature is already met by idle temperature
            if self.config.target_temp_c <= initial_temp:
                logger.info(
                    "CPU is already at or above target temperature (Target: %.1f°C <= Current: %.1f°C).",
                    self.config.target_temp_c,
                    initial_temp,
                )
                try:
                    notify_already_at_target(initial_temp, self.config.target_temp_c)
                except Exception as e:
                    logger.debug("Failed to send notification: %s", e)
                return False

            self._start_temp_c = initial_temp
            self._start_time = time.time()
            self._state = EngineState.WARMUP
            self._running = True

            self._thread = threading.Thread(target=self._control_loop, daemon=True)
            self._thread.start()
            mode_str = " [EXTREME TESTING MODE - 90°C KILL-SWITCH DISABLED]" if self.config.allow_extreme_temp else ""
            logger.info(
                "ThermalEngine started. Target: %.1f°C, Duration: %ds%s",
                self.config.target_temp_c,
                self.config.duration_seconds,
                mode_str,
            )
            try:
                notify_warmup_started(self.config.target_temp_c, self.config.duration_seconds, self.config.maintain_after_warmup)
            except Exception as e:
                logger.debug("Failed to send start notification: %s", e)
            return True

    def stop(self, state: EngineState = EngineState.IDLE, message: str = "") -> None:
        """
        Stops the thermal controller and terminates all worker processes.
        """
        was_running = False
        with self._lock:
            was_running = self._running
            self._running = False
            self._state = state

        # Instantly terminate workers
        self.generator.stop_all()
        logger.info("ThermalEngine stopped with state %s: %s", state.value, message)

        if was_running and state != EngineState.EMERGENCY_STOP and state != EngineState.COMPLETED:
            try:
                curr_temp = self.monitor.read_cpu_temperature() or (self._last_status.current_temp_c if self._last_status else 0.0)
                notify_warmup_stopped(curr_temp, self.config.target_temp_c, state.value)
            except Exception as e:
                logger.debug("Failed to send stop notification: %s", e)

    def _control_loop(self) -> None:
        """Main control loop executed every 0.5 seconds."""
        while True:
            with self._lock:
                if not self._running:
                    break

            start_tick = time.monotonic()
            self._tick()

            # Sleep remainder of interval
            elapsed_tick = time.monotonic() - start_tick
            sleep_time = max(0.01, ConfigConstraints.SAMPLE_INTERVAL_SECONDS - elapsed_tick)
            time.sleep(sleep_time)

    def _tick(self) -> None:
        """Single iteration of the control loop."""
        current_temp = self.monitor.read_cpu_temperature()
        if current_temp is None:
            current_temp = self.monitor.last_reading or self._start_temp_c

        elapsed = time.time() - self._start_time
        failsafe_triggered = False
        message = ""

        # 1. Critical Failsafe (90°C standard kill-switch, or 100°C extreme limit if unlocked)
        failsafe_threshold = (
            ConfigConstraints.EXTREME_MAX_TARGET_TEMP_C
            if self.config.allow_extreme_temp
            else ConfigConstraints.CRITICAL_FAILSAFE_TEMP_C
        )

        if current_temp >= failsafe_threshold:
            failsafe_triggered = True
            message = f"CRITICAL FAILSAFE: Temperature ({current_temp:.1f}°C) exceeded {failsafe_threshold:.1f}°C limit! Workers killed."
            logger.critical(message)
            self.generator.stop_all()
            with self._lock:
                self._state = EngineState.EMERGENCY_STOP
                self._running = False

            try:
                notify_emergency_failsafe(current_temp)
            except Exception:
                pass

            status = ThermalStatus(
                current_temp_c=current_temp,
                expected_temp_c=self.config.target_temp_c,
                target_temp_c=self.config.target_temp_c,
                start_temp_c=self._start_temp_c,
                elapsed_seconds=elapsed,
                total_duration_seconds=self.config.duration_seconds,
                active_workers=0,
                max_workers=self.generator.max_workers,
                state=EngineState.EMERGENCY_STOP,
                failsafe_triggered=True,
                message=message,
            )
            self._emit_status(status)
            return

        # 2. Check Warmup vs Maintain vs Completed
        current_state = self._state
        if current_state == EngineState.WARMUP:
            if elapsed >= self.config.duration_seconds:
                if self.config.maintain_after_warmup:
                    with self._lock:
                        self._state = EngineState.MAINTAINING
                    current_state = EngineState.MAINTAINING
                    message = f"Warmup completed. Maintaining {self.config.target_temp_c:.1f}°C."
                else:
                    self.generator.stop_all()
                    with self._lock:
                        self._state = EngineState.COMPLETED
                        self._running = False
                    message = "Warmup completed successfully."

                    try:
                        notify_warmup_stopped(current_temp, self.config.target_temp_c, "Completed")
                    except Exception:
                        pass

                    status = ThermalStatus(
                        current_temp_c=current_temp,
                        expected_temp_c=self.config.target_temp_c,
                        target_temp_c=self.config.target_temp_c,
                        start_temp_c=self._start_temp_c,
                        elapsed_seconds=elapsed,
                        total_duration_seconds=self.config.duration_seconds,
                        active_workers=0,
                        max_workers=self.generator.max_workers,
                        state=EngineState.COMPLETED,
                        failsafe_triggered=False,
                        message=message,
                    )
                    self._emit_status(status)
                    return

        # 3. Compute expected curve temperature
        if current_state == EngineState.WARMUP:
            expected_temp = self.calculate_expected_temperature(elapsed)
        else:  # MAINTAINING
            expected_temp = self.config.target_temp_c

        # 4. Controller Engine Logic: Scale processes up or down
        active_count = self.generator.active_worker_count
        if current_temp < expected_temp:
            # Below expected curve: spawn more multiprocessing workers
            if active_count < self.generator.max_workers:
                self.generator.spawn_worker()
                message = f"Below curve ({current_temp:.1f}°C < {expected_temp:.1f}°C): spawned worker."
        elif current_temp > expected_temp:
            # Above expected curve: kill workers to slow heating
            if active_count > 0:
                self.generator.kill_worker()
                message = f"Above curve ({current_temp:.1f}°C > {expected_temp:.1f}°C): killed worker."
        else:
            message = f"On curve ({current_temp:.1f}°C)."

        status = ThermalStatus(
            current_temp_c=current_temp,
            expected_temp_c=expected_temp,
            target_temp_c=self.config.target_temp_c,
            start_temp_c=self._start_temp_c,
            elapsed_seconds=elapsed,
            total_duration_seconds=self.config.duration_seconds,
            active_workers=self.generator.active_worker_count,
            max_workers=self.generator.max_workers,
            state=current_state,
            failsafe_triggered=failsafe_triggered,
            message=message,
        )
        self._emit_status(status)

    def _emit_status(self, status: ThermalStatus) -> None:
        with self._lock:
            self._last_status = status
        if self.on_tick:
            try:
                self.on_tick(status)
            except Exception as e:
                logger.error("Error in on_tick callback: %s", e)
