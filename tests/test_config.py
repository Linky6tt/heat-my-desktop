"""
Tests for ThermalConfig and ConfigConstraints.
"""

import json
from pathlib import Path
import tempfile
import unittest

from thermal.config import ConfigConstraints, ThermalConfig


class TestThermalConfig(unittest.TestCase):

    def test_default_values(self):
        cfg = ThermalConfig()
        self.assertEqual(cfg.target_temp_c, 55.0)
        self.assertEqual(cfg.duration_seconds, 300)
        self.assertFalse(cfg.maintain_after_warmup)  # Step 2: Maintain toggle must default to OFF

    def test_valid_ranges(self):
        # Boundaries: 30°C and 90°C, 1s and 3600s
        cfg_min = ThermalConfig(target_temp_c=30.0, duration_seconds=1, maintain_after_warmup=False)
        cfg_min.validate()

        cfg_max = ThermalConfig(target_temp_c=90.0, duration_seconds=3600, maintain_after_warmup=True)
        cfg_max.validate()

    def test_target_temp_constraints(self):
        # Less than 30°C must fail
        with self.assertRaises(ValueError):
            ThermalConfig(target_temp_c=29.9).validate()

        # Greater than 90°C must fail
        with self.assertRaises(ValueError):
            ThermalConfig(target_temp_c=90.1).validate()

    def test_duration_constraints(self):
        # Less than 1s must fail
        with self.assertRaises(ValueError):
            ThermalConfig(duration_seconds=0).validate()

        # Greater than 3600s (1 hour) must fail
        with self.assertRaises(ValueError):
            ThermalConfig(duration_seconds=3601).validate()

    def test_clamp_helper(self):
        # Clamping below minimums
        c1 = ThermalConfig.clamp(target_temp_c=20.0, duration_seconds=0, maintain=False)
        self.assertEqual(c1.target_temp_c, 30.0)
        self.assertEqual(c1.duration_seconds, 1)

        # Clamping above maximums
        c2 = ThermalConfig.clamp(target_temp_c=105.0, duration_seconds=5000, maintain=True)
        self.assertEqual(c2.target_temp_c, 90.0)
        self.assertEqual(c2.duration_seconds, 3600)
        self.assertTrue(c2.maintain_after_warmup)

    def test_json_serialization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "config.json"
            cfg = ThermalConfig(target_temp_c=65.0, duration_seconds=600, maintain_after_warmup=True)
            saved_path = cfg.save_to_file(file_path)
            self.assertTrue(saved_path.exists())

            loaded_cfg = ThermalConfig.load_from_file(file_path)
            self.assertEqual(loaded_cfg.target_temp_c, 65.0)
            self.assertEqual(loaded_cfg.duration_seconds, 600)
            self.assertTrue(loaded_cfg.maintain_after_warmup)

    def test_extreme_mode_config_validation(self):
        # 95°C with allow_extreme_temp=True in UI mode is valid
        cfg_ext = ThermalConfig(target_temp_c=95.0, duration_seconds=120, allow_extreme_temp=True)
        cfg_ext.validate(is_daemon=False)

        # >100°C must fail even in extreme mode
        with self.assertRaises(ValueError):
            ThermalConfig(target_temp_c=100.1, duration_seconds=120, allow_extreme_temp=True).validate(is_daemon=False)

        # >90°C must fail if allow_extreme_temp is False
        with self.assertRaises(ValueError):
            ThermalConfig(target_temp_c=95.0, duration_seconds=120, allow_extreme_temp=False).validate(is_daemon=False)

        # >90°C must fail in daemon mode even if allow_extreme_temp is True
        with self.assertRaises(ValueError):
            ThermalConfig(target_temp_c=95.0, duration_seconds=120, allow_extreme_temp=True).validate(is_daemon=True)

    def test_extreme_mode_never_saved_as_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "config.json"
            # Attempt to save extreme config with target 98°C
            cfg = ThermalConfig(target_temp_c=98.0, duration_seconds=300, allow_extreme_temp=True)
            cfg.save_to_file(file_path)

            loaded = ThermalConfig.load_from_file(file_path)
            # Default saved target must be clamped to 90.0°C and allow_extreme_temp must be False
            self.assertEqual(loaded.target_temp_c, 90.0)
            self.assertFalse(loaded.allow_extreme_temp)


if __name__ == "__main__":
    unittest.main()
