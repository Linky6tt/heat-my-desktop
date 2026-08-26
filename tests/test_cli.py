"""
Tests for CLI argument parser and command line operations.
"""

import unittest

from cli import build_parser
from thermal.config import ConfigConstraints


class TestCLI(unittest.TestCase):

    def setUp(self):
        self.parser = build_parser()

    def test_parser_defaults(self):
        args = self.parser.parse_args([])
        self.assertFalse(args.headless)
        self.assertIsNone(args.target)
        self.assertIsNone(args.duration)
        self.assertIsNone(args.maintain)
        self.assertFalse(args.status)

    def test_parser_custom_args(self):
        args = self.parser.parse_args([
            "--headless",
            "--target", "65.5",
            "--duration", "600",
            "--maintain",
            "--sensor", "k10temp-pci-00c3::Tctl"
        ])
        self.assertTrue(args.headless)
        self.assertEqual(args.target, 65.5)
        self.assertEqual(args.duration, 600)
        self.assertTrue(args.maintain)
        self.assertEqual(args.sensor, "k10temp-pci-00c3::Tctl")

    def test_service_flags(self):
        args = self.parser.parse_args(["--generate-service"])
        self.assertTrue(args.generate_service)

        args_uninst = self.parser.parse_args(["--uninstall-service"])
        self.assertTrue(args_uninst.uninstall_service)

    def test_check_target_reached(self):
        from cli import check_target_reached

        # Within 1.5 tolerance
        self.assertTrue(check_target_reached(55.0, 55.0))
        self.assertTrue(check_target_reached(56.5, 55.0))
        self.assertTrue(check_target_reached(53.5, 55.0))

        # Outside 1.5 tolerance
        self.assertFalse(check_target_reached(56.6, 55.0))
        self.assertFalse(check_target_reached(53.4, 55.0))
        self.assertFalse(check_target_reached(45.0, 30.0))


if __name__ == "__main__":
    unittest.main()
