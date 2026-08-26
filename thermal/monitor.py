"""
Temperature monitor module using lm_sensors (sensors) and sysfs fallback.
Samples CPU temperature every 0.5s with robust JSON and regex parsers.
"""

import json
import logging
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Preferred CPU sensor chips and label keys in order of precedence
CPU_CHIP_PATTERNS = [
    r"k10temp",
    r"coretemp",
    r"zenpower",
    r"cpu_thermal",
    r"soc_thermal",
    r"nct668\d",
    r"it87\d\d",
    r"w836\d\d",
    r"acpitz",
]

CPU_LABEL_PATTERNS = [
    r"^tctl$",
    r"^tdie$",
    r"^package id \d+$",
    r"^physical id \d+$",
    r"^cpu(?:_?temp(?:erature)?)?$",
    r"^cputin$",
    r"^tccd\d+$",
    r"^core \d+$",
    r"^temp1$",
]


def parse_sensors_json(json_str: str) -> Dict[str, float]:
    """
    Parses `sensors -j` output into a flattened mapping of 'ChipName - Label': temperature_c.
    Handles extra text before or after valid JSON output.
    """
    results: Dict[str, float] = {}
    if not json_str:
        return results

    # Locate valid JSON substring if stderr or warnings were interleaved in stdout
    start_idx = json_str.find("{")
    end_idx = json_str.rfind("}")
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return results

    clean_json = json_str[start_idx : end_idx + 1]
    try:
        data = json.loads(clean_json)
    except Exception as e:
        logger.debug("Failed to parse sensors JSON: %s", e)
        return results

    for chip_name, chip_data in data.items():
        if not isinstance(chip_data, dict):
            continue
        for label, sensor_data in chip_data.items():
            if label == "Adapter" or not isinstance(sensor_data, dict):
                continue
            for key, val in sensor_data.items():
                if (key.startswith("temp") or "temp" in key) and key.endswith("_input") and isinstance(val, (int, float)):
                    identifier = f"{chip_name}::{label}"
                    results[identifier] = float(val)
                    break

    return results


def parse_sensors_text(text: str) -> Dict[str, float]:
    """
    Fallback parser for standard `sensors` human-readable text output.
    Matches lines like: 'Tctl:         +41.1°C' or 'Core 0:        +45.0°C'
    """
    results: Dict[str, float] = {}
    current_chip = "generic"
    
    # Regex to match chip header (starts at column 0 without colon and without indent)
    chip_header_pattern = re.compile(r"^([a-zA-Z0-9_\-\.]+)(?:-[a-zA-Z0-9_\-\.]+)?$")
    # Regex to match temp line e.g., 'Tctl:         +41.1°C'
    temp_pattern = re.compile(r"^\s*([A-Za-z0-9_\s\(\)]+?):\s*([\+\-]?[0-9]+\.[0-9]+)\s*°C", re.UNICODE)

    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue

        if not line.startswith(" ") and not line.startswith("\t") and ":" not in line:
            current_chip = line_clean.split()[0] if line_clean else "generic"
            continue

        match = temp_pattern.match(line)
        if match:
            label = match.group(1).strip()
            temp_val = float(match.group(2))
            identifier = f"{current_chip}::{label}"
            results[identifier] = temp_val

    return results


def read_sysfs_temperatures() -> Dict[str, float]:
    """
    Reads hardware temperatures directly from /sys/class/hwmon/ and /sys/class/thermal/
    used as fallback when lm-sensors binary is not available.
    """
    results: Dict[str, float] = {}
    
    # /sys/class/hwmon
    hwmon_base = Path("/sys/class/hwmon")
    if hwmon_base.exists():
        try:
            for hwmon_dir in hwmon_base.iterdir():
                name_file = hwmon_dir / "name"
                chip_name = name_file.read_text().strip() if name_file.exists() else hwmon_dir.name
                for temp_input in hwmon_dir.glob("temp*_input"):
                    try:
                        millidegrees = int(temp_input.read_text().strip())
                        temp_c = millidegrees / 1000.0
                        label_file = hwmon_dir / temp_input.name.replace("_input", "_label")
                        label = label_file.read_text().strip() if label_file.exists() else temp_input.name
                        results[f"{chip_name}::{label}"] = temp_c
                    except Exception:
                        continue
        except Exception as e:
            logger.debug("Error reading sysfs hwmon: %s", e)

    # /sys/class/thermal
    thermal_base = Path("/sys/class/thermal")
    if thermal_base.exists():
        try:
            for zone_dir in thermal_base.glob("thermal_zone*"):
                type_file = zone_dir / "type"
                temp_file = zone_dir / "temp"
                if temp_file.exists():
                    try:
                        zone_type = type_file.read_text().strip() if type_file.exists() else zone_dir.name
                        millidegrees = int(temp_file.read_text().strip())
                        results[f"thermal_zone::{zone_type}"] = millidegrees / 1000.0
                    except Exception:
                        continue
        except Exception as e:
            logger.debug("Error reading sysfs thermal: %s", e)

    return results


def parse_sensors_output(output: str) -> Dict[str, float]:
    """Parses output string from sensors using JSON parser first, with text regex fallback."""
    json_results = parse_sensors_json(output)
    if json_results:
        return json_results
    return parse_sensors_text(output)


class TemperatureMonitor:
    """
    Monitors CPU thermal readings via lm_sensors subprocess every 0.5s.
    Auto-detects the most suitable CPU temperature sensor.
    """

    def __init__(self, preferred_sensor: Optional[str] = None) -> None:
        self.preferred_sensor = preferred_sensor
        self._last_reading: Optional[float] = None
        self._last_reading_time: float = 0.0
        self._detected_sensor_key: Optional[str] = None
        self._all_sensors_cache: Dict[str, float] = {}

    def fetch_all_temperatures(self) -> Dict[str, float]:
        """
        Executes `sensors -j` or falls back to `sensors` text or sysfs.
        Returns a dictionary of sensor_identifier -> temperature_c.
        """
        readings: Dict[str, float] = {}

        # 1. Try `sensors -j`
        try:
            res = subprocess.run(
                ["sensors", "-j"],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False
            )
            if res.stdout:
                readings = parse_sensors_json(res.stdout)
        except Exception as e:
            logger.debug("sensors -j execution failed: %s", e)

        # 2. Try standard `sensors` text
        if not readings:
            try:
                res = subprocess.run(
                    ["sensors"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                    check=False
                )
                if res.stdout:
                    readings = parse_sensors_text(res.stdout)
            except Exception as e:
                logger.debug("sensors text execution failed: %s", e)

        # 3. Try /sys/class/hwmon /sys/class/thermal fallback
        if not readings:
            readings = read_sysfs_temperatures()

        self._all_sensors_cache = readings
        return readings

    def detect_cpu_sensor_key(self, readings: Dict[str, float]) -> Optional[str]:
        """
        Heuristically selects the primary CPU temperature sensor from readings.
        """
        if not readings:
            return None

        # User preferred override
        if self.preferred_sensor and self.preferred_sensor in readings:
            return self.preferred_sensor

        # Check by chip pattern and label priority
        for chip_pat in CPU_CHIP_PATTERNS:
            chip_regex = re.compile(chip_pat, re.IGNORECASE)
            matching_chips = [k for k in readings.keys() if chip_regex.search(k.split("::")[0])]
            
            if matching_chips:
                # Find best label in this chip
                for label_pat in CPU_LABEL_PATTERNS:
                    label_regex = re.compile(label_pat, re.IGNORECASE)
                    for key in matching_chips:
                        label = key.split("::")[-1]
                        if label_regex.search(label):
                            return key
                # Return first sensor of matching CPU chip if no label pattern matched
                return matching_chips[0]

        # Generic fallback: look for 'cpu' or 'temp1'
        for key in readings.keys():
            if "cpu" in key.lower() or "tctl" in key.lower() or "package" in key.lower():
                return key

        # Fallback to the highest reading or first sensor
        if readings:
            return max(readings.keys(), key=lambda k: readings[k])

        return None

    def read_cpu_temperature(self) -> Optional[float]:
        """
        Fetches the current CPU temperature in °C.
        Returns float temperature or None if no sensor could be read.
        """
        readings = self.fetch_all_temperatures()
        if not readings:
            return None

        if not self._detected_sensor_key or self._detected_sensor_key not in readings:
            self._detected_sensor_key = self.detect_cpu_sensor_key(readings)

        if self._detected_sensor_key and self._detected_sensor_key in readings:
            temp = readings[self._detected_sensor_key]
            self._last_reading = temp
            self._last_reading_time = time.time()
            return temp

        return None

    @property
    def detected_sensor_name(self) -> Optional[str]:
        """Returns the identified sensor name/key."""
        return self._detected_sensor_key

    @property
    def last_reading(self) -> Optional[float]:
        """Returns the last recorded temperature reading."""
        return self._last_reading

    def get_available_sensors(self) -> List[str]:
        """Returns a list of all detected temperature sensor keys."""
        if not self._all_sensors_cache:
            self.fetch_all_temperatures()
        return list(self._all_sensors_cache.keys())
