import unittest
from pathlib import Path

from dashboard.config import report_dir_from_args


class TestDashboardConfig(unittest.TestCase):
    def test_default_report_dir(self):
        self.assertEqual(report_dir_from_args([], {}), Path("reports"))

    def test_environment_report_dir(self):
        self.assertEqual(
            report_dir_from_args([], {"RELOCATE_REPORT_DIR": "history/run1"}),
            Path("history/run1"),
        )

    def test_cli_precedes_environment(self):
        self.assertEqual(
            report_dir_from_args(
                ["--report-dir", "history/run2"],
                {"RELOCATE_REPORT_DIR": "history/run1"},
            ),
            Path("history/run2"),
        )


if __name__ == "__main__":
    unittest.main()

