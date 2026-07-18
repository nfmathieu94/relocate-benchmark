import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dashboard_reports"
ENTRYPOINTS = {
    Path("dashboard/app.py"): "RelocaTE benchmark dashboard",
    Path("dashboard/pages/02_accuracy.py"): "Accuracy",
    Path("dashboard/pages/03_somatic.py"): "Somatic insertion performance",
    Path("dashboard/pages/04_resources.py"): "Computational resources",
    Path("dashboard/pages/05_provenance.py"): "Provenance and interpretation",
}


@unittest.skipUnless(HAS_STREAMLIT, "streamlit is not installed")
class TestDashboardUI(unittest.TestCase):
    def test_every_page_renders_fixture_reports_without_exception(self):
        from streamlit.testing.v1 import AppTest

        for path, expected_title in ENTRYPOINTS.items():
            with self.subTest(page=str(path)):
                app = AppTest.from_file(path, default_timeout=20)
                with patch.dict(
                    os.environ,
                    {"RELOCATE_REPORT_DIR": str(FIXTURE_DIR)},
                ):
                    app.run()
                self.assertEqual(list(app.exception), [])
                self.assertIn(expected_title, [title.value for title in app.title])
                self.assertEqual(len(app.sidebar.multiselect), 6)
                self.assertEqual(len(app.sidebar.button), 1)


if __name__ == "__main__":
    unittest.main()

