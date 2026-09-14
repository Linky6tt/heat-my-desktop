"""
Tests for systemd service generation and installation.
"""

from pathlib import Path
import tempfile
import unittest

from service.systemd import (
    SERVICE_UNIT_NAME,
    generate_service_content,
    install_user_service,
    is_service_installed,
    uninstall_user_service,
)
from thermal.config import ThermalConfig


class TestSystemdService(unittest.TestCase):

    def test_generate_service_content(self):
        cfg = ThermalConfig(target_temp_c=65.0, duration_seconds=600, maintain_after_warmup=True)
        content = generate_service_content(
            config=cfg,
            python_bin="/usr/bin/python3",
            entrypoint_script=Path("/opt/warmup/main.py")
        )

        self.assertIn("Description=CPU Thermal Controller", content)
        self.assertIn("/usr/bin/python3 /opt/warmup/main.py --headless --target 65.0 --duration 600 --maintain", content)
        self.assertIn("WantedBy=default.target", content)

        cfg_no_m = ThermalConfig(target_temp_c=65.0, duration_seconds=600, maintain_after_warmup=False)
        content_no_m = generate_service_content(
            config=cfg_no_m,
            python_bin="/usr/bin/python3",
            entrypoint_script=Path("/opt/warmup/main.py")
        )
        self.assertIn("--no-maintain", content_no_m)

    def test_install_and_uninstall_service(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            cfg = ThermalConfig(target_temp_c=50.0, duration_seconds=120, maintain_after_warmup=False)
            
            self.assertFalse(is_service_installed(destination_dir=dest))

            service_path = install_user_service(cfg, destination_dir=dest)
            self.assertEqual(service_path.name, SERVICE_UNIT_NAME)
            self.assertTrue(service_path.exists())
            self.assertTrue(is_service_installed(destination_dir=dest))

            ok, msg = uninstall_user_service(destination_dir=dest)
            self.assertTrue(ok)
            self.assertFalse(is_service_installed(destination_dir=dest))
            self.assertFalse(service_path.exists())

    def test_legacy_service_cleanup_and_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            legacy_file = dest / "cpu-thermal-warmup.service"
            legacy_file.write_text("dummy legacy service")

            self.assertTrue(is_service_installed(destination_dir=dest))

            cfg = ThermalConfig(target_temp_c=50.0, duration_seconds=120, maintain_after_warmup=False)
            service_path = install_user_service(cfg, destination_dir=dest)
            self.assertEqual(service_path.name, SERVICE_UNIT_NAME)
            self.assertTrue(service_path.exists())
            self.assertFalse(legacy_file.exists())

            legacy_file.write_text("dummy legacy service")
            self.assertTrue(is_service_installed(destination_dir=dest))
            ok, msg = uninstall_user_service(destination_dir=dest)
            self.assertTrue(ok)
            self.assertFalse(service_path.exists())
            self.assertFalse(legacy_file.exists())
            self.assertFalse(is_service_installed(destination_dir=dest))


if __name__ == "__main__":
    unittest.main()
