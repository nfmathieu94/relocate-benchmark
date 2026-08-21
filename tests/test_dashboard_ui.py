import csv
import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dashboard_reports"
# path -> (expected title, renders the shared sidebar data filters). The
# Information page is a static glossary and intentionally has no data filters.
ENTRYPOINTS = {
    Path("dashboard/app.py"): ("RelocaTE benchmark dashboard", True),
    # The cross-dataset page compares datasets side by side, so it uses the
    # whole suite and deliberately renders no per-dataset sidebar filters.
    Path("dashboard/pages/00_R3_vs_R2.py"): ("RelocaTE3 vs RelocaTE2", False),
    Path("dashboard/pages/01_information.py"): ("Information & metrics glossary", False),
    Path("dashboard/pages/02_accuracy.py"): ("Accuracy", True),
    Path("dashboard/pages/03_somatic.py"): ("Somatic insertion performance", True),
    Path("dashboard/pages/04_te_groups.py"): ("Performance by TE group", True),
    Path("dashboard/pages/04_resources.py"): ("Computational resources", True),
    Path("dashboard/pages/05_provenance.py"): ("Provenance and interpretation", True),
}


@unittest.skipUnless(HAS_STREAMLIT, "streamlit is not installed")
class TestDashboardUI(unittest.TestCase):
    def test_every_page_renders_fixture_reports_without_exception(self):
        from streamlit.testing.v1 import AppTest

        for path, (expected_title, has_filters) in ENTRYPOINTS.items():
            with self.subTest(page=str(path)):
                app = AppTest.from_file(path, default_timeout=20)
                with patch.dict(
                    os.environ,
                    {"RELOCATE_REPORT_DIR": str(FIXTURE_DIR)},
                ):
                    app.run()
                self.assertEqual(list(app.exception), [])
                self.assertIn(expected_title, [title.value for title in app.title])
                if has_filters:
                    self.assertEqual(len(app.sidebar.multiselect), 6)
                    self.assertEqual(len(app.sidebar.button), 1)

    def test_switching_dataset_does_not_leak_stale_sample_filter(self):
        # Regression: two datasets with disjoint sample names. The sidebar
        # filter widgets are keyed, so switching the dataset selector used to
        # carry the first dataset's sample selection into the second. None of
        # those samples exist in the second dataset, so the Sample filter
        # collapsed to empty and `isin([])` zeroed every row, rendering
        # "No accuracy rows match the active filters." for a fully populated
        # dataset.
        from streamlit.testing.v1 import AppTest

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "reports"
            (root / "datasets").mkdir(parents=True)
            shutil.copytree(FIXTURE_DIR, root / "datasets" / "alpha")
            shutil.copytree(FIXTURE_DIR, root / "datasets" / "beta")
            # Make beta's samples disjoint from alpha's by prefixing them.
            for name in ("correctness.tsv", "precision.tsv", "resources.tsv"):
                path = root / "datasets" / "beta" / name
                with path.open(newline="") as handle:
                    reader = csv.DictReader(handle, delimiter="\t")
                    fields = reader.fieldnames
                    rows = list(reader)
                for row in rows:
                    row["sample"] = f"beta_{row['sample']}"
                with path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
                    writer.writeheader()
                    writer.writerows(rows)
            (root / "datasets.tsv").write_text(
                "dataset\tlabel\treport_dir\n"
                "alpha\tAlpha panel\tdatasets/alpha\n"
                "beta\tBeta panel\tdatasets/beta\n"
            )

            app = AppTest.from_file("dashboard/pages/02_accuracy.py", default_timeout=30)
            with patch.dict(os.environ, {"RELOCATE_REPORT_DIR": str(root)}):
                app.run()
                app.sidebar.selectbox[0].set_value("Beta panel").run()

            self.assertEqual(list(app.exception), [])
            sample_widget = [m for m in app.sidebar.multiselect if m.label == "Sample"]
            self.assertTrue(sample_widget, "Sample filter widget missing")
            self.assertNotEqual(
                sample_widget[0].value,
                [],
                "Sample filter leaked to empty after switching datasets",
            )
            self.assertNotIn(
                "No accuracy rows match the active filters.",
                [message.value for message in app.info],
            )


if __name__ == "__main__":
    unittest.main()
