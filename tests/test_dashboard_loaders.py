import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dashboard.data.loaders import load_reports
from dashboard.data.validation import ReportValidationError


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dashboard_reports"


class TestDashboardLoaders(unittest.TestCase):
    def test_loads_and_types_all_reports(self):
        bundle = load_reports(FIXTURE_DIR)
        self.assertEqual(set(bundle.frames()), {"correctness", "precision", "head_to_head", "resources"})
        self.assertEqual(len(bundle.correctness), 12)
        self.assertTrue(pd.api.types.is_integer_dtype(bundle.correctness["coverage"]))
        self.assertTrue(pd.api.types.is_float_dtype(bundle.precision["overall_precision"]))
        self.assertEqual(bundle.resources.loc[0, "percent_cpu"], 600.0)

    def _copy_fixture(self, root: Path) -> Path:
        target = root / "reports"
        shutil.copytree(FIXTURE_DIR, target)
        return target

    def test_missing_report_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = self._copy_fixture(Path(tmp))
            (report_dir / "precision.tsv").unlink()
            with self.assertRaisesRegex(ReportValidationError, "precision.tsv.*does not exist"):
                load_reports(report_dir)

    def test_empty_report_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = self._copy_fixture(Path(tmp))
            (report_dir / "resources.tsv").write_text("")
            with self.assertRaisesRegex(ReportValidationError, "resources.tsv.*empty"):
                load_reports(report_dir)

    def test_missing_column_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = self._copy_fixture(Path(tmp))
            path = report_dir / "precision.tsv"
            frame = pd.read_csv(path, sep="\t").drop(columns="overall_precision")
            frame.to_csv(path, sep="\t", index=False)
            with self.assertRaisesRegex(ReportValidationError, "overall_precision"):
                load_reports(report_dir)

    def test_invalid_numeric_value_is_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = self._copy_fixture(Path(tmp))
            path = report_dir / "resources.tsv"
            frame = pd.read_csv(path, sep="\t", dtype="string")
            frame.loc[0, "wall_seconds"] = "twelve"
            frame.to_csv(path, sep="\t", index=False)
            with self.assertRaisesRegex(ReportValidationError, "wall_seconds.*twelve"):
                load_reports(report_dir)

    def test_duplicate_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = self._copy_fixture(Path(tmp))
            path = report_dir / "precision.tsv"
            frame = pd.read_csv(path, sep="\t")
            pd.concat([frame, frame.iloc[[0]]]).to_csv(path, sep="\t", index=False)
            with self.assertRaisesRegex(ReportValidationError, "duplicate row"):
                load_reports(report_dir)


if __name__ == "__main__":
    unittest.main()
