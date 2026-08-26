"""
Tests for lm_sensors temperature monitor and parsing logic.
"""

import unittest

from thermal.monitor import (
    TemperatureMonitor,
    parse_sensors_json,
    parse_sensors_output,
    parse_sensors_text,
)

SAMPLE_AMD_JSON = """
{
  "k10temp-pci-00c3": {
    "Adapter": "PCI adapter",
    "Tctl": {
      "temp1_input": 42.500000
    },
    "Tccd1": {
      "temp3_input": 48.000000
    }
  },
  "nvme-pci-0100": {
    "Adapter": "PCI adapter",
    "Composite": {
      "temp1_input": 35.850000
    }
  }
}
"""

SAMPLE_INTEL_TEXT = """
coretemp-isa-0000
Adapter: ISA adapter
Package id 0:  +48.0°C  (high = +100.0°C, crit = +100.0°C)
Core 0:        +45.0°C  (high = +100.0°C, crit = +100.0°C)
Core 1:        +46.0°C  (high = +100.0°C, crit = +100.0°C)

acpitz-acpi-0
Adapter: ACPI interface
temp1:        +27.8°C  (crit = +105.0°C)
"""


class TestThermalMonitor(unittest.TestCase):

    def test_parse_amd_json(self):
        parsed = parse_sensors_json(SAMPLE_AMD_JSON)
        self.assertIn("k10temp-pci-00c3::Tctl", parsed)
        self.assertEqual(parsed["k10temp-pci-00c3::Tctl"], 42.5)
        self.assertIn("k10temp-pci-00c3::Tccd1", parsed)
        self.assertEqual(parsed["k10temp-pci-00c3::Tccd1"], 48.0)

    def test_parse_intel_text(self):
        parsed = parse_sensors_text(SAMPLE_INTEL_TEXT)
        self.assertIn("coretemp-isa-0000::Package id 0", parsed)
        self.assertEqual(parsed["coretemp-isa-0000::Package id 0"], 48.0)
        self.assertIn("coretemp-isa-0000::Core 0", parsed)
        self.assertEqual(parsed["coretemp-isa-0000::Core 0"], 45.0)

    def test_cpu_sensor_auto_detection(self):
        monitor = TemperatureMonitor()
        amd_readings = parse_sensors_json(SAMPLE_AMD_JSON)
        detected = monitor.detect_cpu_sensor_key(amd_readings)
        self.assertEqual(detected, "k10temp-pci-00c3::Tctl")

        intel_readings = parse_sensors_text(SAMPLE_INTEL_TEXT)
        detected_intel = monitor.detect_cpu_sensor_key(intel_readings)
        self.assertEqual(detected_intel, "coretemp-isa-0000::Package id 0")


if __name__ == "__main__":
    unittest.main()
