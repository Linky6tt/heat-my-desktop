"""
Configuration and constraints management for CPU Thermal Controller.
Enforces logic constraints, failsafes, and JSON persistence.
"""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigConstraints:
    """Hardcoded limits and safety thresholds."""
    MIN_TARGET_TEMP_C: float = 30.0
    MAX_TARGET_TEMP_C: float = 90.0
    EXTREME_MAX_TARGET_TEMP_C: float = 100.0  # One-time interactive UI extreme test limit
    MAX_DURATION_SECONDS: int = 3600  # 1 hour
    MIN_DURATION_SECONDS: int = 1     # 1 second
    DEFAULT_MAINTAIN: bool = False    # Defaults to OFF
    CRITICAL_FAILSAFE_TEMP_C: float = 90.0  # Standard absolute kill-switch threshold
    SAMPLE_INTERVAL_SECONDS: float = 0.25  # Monitor and control frequency (4 checks/sec)


@dataclass
class ThermalConfig:
    """User configuration parameters."""
    target_temp_c: float = 55.0
    duration_seconds: int = 300
    maintain_after_warmup: bool = ConfigConstraints.DEFAULT_MAINTAIN
    sensor_name: Optional[str] = None  # Optional specific sensor name override
    allow_extreme_temp: bool = False   # One-time session flag for >90°C extreme stress test

    def __post_init__(self) -> None:
        self.validate()

    def validate(self, is_daemon: bool = False) -> None:
        """Validates parameters against system constraints."""
        max_allowed = ConfigConstraints.MAX_TARGET_TEMP_C
        if self.allow_extreme_temp and not is_daemon:
            max_allowed = ConfigConstraints.EXTREME_MAX_TARGET_TEMP_C

        if not (ConfigConstraints.MIN_TARGET_TEMP_C <= self.target_temp_c <= max_allowed):
            if self.target_temp_c > ConfigConstraints.MAX_TARGET_TEMP_C and is_daemon:
                raise ValueError("Extreme temperature (>90.0°C) is not permitted in daemon mode.")
            raise ValueError(
                f"Target temperature ({self.target_temp_c}°C) must be between "
                f"{ConfigConstraints.MIN_TARGET_TEMP_C}°C and {max_allowed}°C."
            )
        if not (ConfigConstraints.MIN_DURATION_SECONDS <= self.duration_seconds <= ConfigConstraints.MAX_DURATION_SECONDS):
            raise ValueError(
                f"Warmup duration ({self.duration_seconds}s) must be between "
                f"{ConfigConstraints.MIN_DURATION_SECONDS}s and {ConfigConstraints.MAX_DURATION_SECONDS}s."
            )
        if not isinstance(self.maintain_after_warmup, bool):
            raise ValueError("maintain_after_warmup must be a boolean.")

    @classmethod
    def clamp(cls, target_temp_c: float, duration_seconds: int, maintain: bool = False, sensor_name: Optional[str] = None) -> "ThermalConfig":
        """Clamps inputs to valid constraint ranges (always enforces standard 90°C default limit)."""
        clamped_temp = max(ConfigConstraints.MIN_TARGET_TEMP_C, min(ConfigConstraints.MAX_TARGET_TEMP_C, float(target_temp_c)))
        clamped_dur = max(ConfigConstraints.MIN_DURATION_SECONDS, min(ConfigConstraints.MAX_DURATION_SECONDS, int(duration_seconds)))
        return cls(
            target_temp_c=clamped_temp,
            duration_seconds=clamped_dur,
            maintain_after_warmup=bool(maintain),
            sensor_name=sensor_name,
            allow_extreme_temp=False  # Never default to extreme mode
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes config to dictionary, guaranteeing defaults remain safe (max 90°C)."""
        safe_target = min(ConfigConstraints.MAX_TARGET_TEMP_C, self.target_temp_c)
        return {
            "target_temp_c": safe_target,
            "duration_seconds": self.duration_seconds,
            "maintain_after_warmup": self.maintain_after_warmup,
            "sensor_name": self.sensor_name
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThermalConfig":
        """Deserializes config from dictionary with validation/clamping."""
        return cls.clamp(
            target_temp_c=data.get("target_temp_c", 55.0),
            duration_seconds=data.get("duration_seconds", 300),
            maintain=data.get("maintain_after_warmup", ConfigConstraints.DEFAULT_MAINTAIN),
            sensor_name=data.get("sensor_name")
        )

    @staticmethod
    def get_default_config_path() -> Path:
        """Returns standard configuration file path (~/.config/cpu_thermal_controller/config.json)."""
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config_home:
            base_dir = Path(xdg_config_home)
        else:
            base_dir = Path.home() / ".config"
        return base_dir / "cpu_thermal_controller" / "config.json"

    def save_to_file(self, path: Optional[Path] = None) -> Path:
        """Saves config to JSON file."""
        target_path = path or self.get_default_config_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=4)
        return target_path

    @classmethod
    def load_from_file(cls, path: Optional[Path] = None) -> "ThermalConfig":
        """Loads config from JSON file or returns default if not found."""
        target_path = path or cls.get_default_config_path()
        if not target_path.exists():
            return cls()
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception:
            return cls()
