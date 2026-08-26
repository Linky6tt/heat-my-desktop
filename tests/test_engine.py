"""
Tests for ThermalEngine, rate curve calculations, worker scaling, and failsafe stops.
"""

import time
import unittest
from unittest.mock import MagicMock

from thermal.config import ConfigConstraints, ThermalConfig
from thermal.engine import EngineState, ThermalEngine, ThermalStatus
from thermal.generator import HeatGenerator
from thermal.monitor import TemperatureMonitor


class MockMonitor(TemperatureMonitor):

    def __init__(self, start_temp: float = 40.0):
        super().__init__()
        self.mock_temp = start_temp

    def read_cpu_temperature(self) -> float:
        return self.mock_temp


class TestThermalEngine(unittest.TestCase):

    def setUp(self):
        self.config = ThermalConfig(target_temp_c=60.0, duration_seconds=100, maintain_after_warmup=False)
        self.monitor = MockMonitor(start_temp=40.0)
        self.generator = HeatGenerator(max_workers=4)
        self.engine = ThermalEngine(
            config=self.config,
            monitor=self.monitor,
            generator=self.generator
        )

    def tearDown(self):
        self.engine.stop()
        self.generator.stop_all()

    def test_expected_temperature_rate_curve(self):
        # Starts at 40°C, target is 60°C, total duration = 100s
        self.engine._start_temp_c = 40.0
        
        # t = 0s -> 40.0°C
        self.assertAlmostEqual(self.engine.calculate_expected_temperature(0), 40.0)
        # t = 50s -> 50.0°C (midpoint)
        self.assertAlmostEqual(self.engine.calculate_expected_temperature(50), 50.0)
        # t = 100s -> 60.0°C (target)
        self.assertAlmostEqual(self.engine.calculate_expected_temperature(100), 60.0)
        # t > 100s -> 60.0°C (clamped)
        self.assertAlmostEqual(self.engine.calculate_expected_temperature(150), 60.0)

    def test_worker_scaling_below_curve(self):
        # Current temp (40°C) is below expected (50°C) -> should spawn worker
        self.engine._start_temp_c = 40.0
        self.engine._start_time = time.time() - 50.0  # 50s elapsed
        self.engine._state = EngineState.WARMUP
        self.engine._running = True
        self.monitor.mock_temp = 42.0  # expected is 50.0

        initial_workers = self.generator.active_worker_count
        self.assertEqual(initial_workers, 0)

        self.engine._tick()
        self.assertEqual(self.generator.active_worker_count, 1)

    def test_worker_scaling_above_curve(self):
        # Preset 2 workers
        self.generator.set_worker_count(2)
        self.assertEqual(self.generator.active_worker_count, 2)

        self.engine._start_temp_c = 40.0
        self.engine._start_time = time.time() - 50.0  # 50s elapsed -> expected is 50°C
        self.engine._state = EngineState.WARMUP
        self.engine._running = True
        self.monitor.mock_temp = 55.0  # above curve (55 > 50)

        self.engine._tick()
        # Should have killed 1 worker
        self.assertEqual(self.generator.active_worker_count, 1)

    def test_critical_90c_failsafe(self):
        # Preset workers
        self.generator.set_worker_count(3)
        self.assertEqual(self.generator.active_worker_count, 3)

        self.engine._start_temp_c = 40.0
        self.engine._start_time = time.time() - 10.0
        self.engine._state = EngineState.WARMUP
        self.engine._running = True

        # Simulate temp jumping to 90.5°C
        self.monitor.mock_temp = 90.5

        statuses = []
        self.engine.on_tick = lambda s: statuses.append(s)

        self.engine._tick()

        # Engine must transition to EMERGENCY_STOP and kill all workers
        self.assertEqual(self.engine.state, EngineState.EMERGENCY_STOP)
        self.assertFalse(self.engine.is_running)
        self.assertEqual(self.generator.active_worker_count, 0)
        self.assertTrue(len(statuses) > 0)
        self.assertTrue(statuses[-1].failsafe_triggered)

    def test_start_aborts_if_already_at_or_above_target(self):
        # Target is 40.0, current idle is 45.0
        cfg = ThermalConfig(target_temp_c=40.0, duration_seconds=100)
        self.monitor.mock_temp = 45.0

        started = self.engine.start(cfg)
        self.assertFalse(started)
        self.assertFalse(self.engine.is_running)
        self.assertEqual(self.generator.active_worker_count, 0)

    def test_extreme_mode_allows_temp_above_90c(self):
        # Configure extreme testing mode (95°C target, allow_extreme_temp=True)
        cfg = ThermalConfig(target_temp_c=95.0, duration_seconds=100, allow_extreme_temp=True)
        self.generator.set_worker_count(2)
        self.engine.config = cfg
        self.engine._start_temp_c = 40.0
        self.engine._start_time = time.time() - 50.0
        self.engine._state = EngineState.WARMUP
        self.engine._running = True

        # Temp reaches 91.0°C (above standard 90°C limit)
        self.monitor.mock_temp = 91.0
        self.engine._tick()

        # Engine must NOT trigger emergency stop at 91.0°C when in extreme mode
        self.assertEqual(self.engine.state, EngineState.WARMUP)
        self.assertTrue(self.engine.is_running)

        # But if temp reaches 100.0°C, extreme limit triggers kill-switch
        self.monitor.mock_temp = 100.2
        self.engine._tick()
        self.assertEqual(self.engine.state, EngineState.EMERGENCY_STOP)
        self.assertFalse(self.engine.is_running)
        self.assertEqual(self.generator.active_worker_count, 0)


if __name__ == "__main__":
    unittest.main()
