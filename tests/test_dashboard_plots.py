import unittest
from pathlib import Path

from dashboard.data.loaders import load_reports
from dashboard.data.transforms import accuracy_summary, somatic_summary
from dashboard.plots.accuracy import (
    accuracy_figure,
    caller_comparison_figure,
    somatic_figure,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dashboard_reports"


def _annotation_texts(figure):
    return [annotation.text for annotation in figure.layout.annotations]


def _axis_titles(figure):
    return [axis.title.text for axis in figure.select_xaxes()]


class TestDashboardAccuracyPlots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = load_reports(FIXTURE_DIR)
        cls.data = accuracy_summary(bundle.correctness, "detection_recall")
        cls.somatic_data = somatic_summary(bundle.correctness)

    def test_coverage_plot_has_clean_facets_and_one_shared_x_title(self):
        figure = accuracy_figure(
            self.data,
            "Detection recall vs. coverage",
            "Detection recall",
        )
        annotations = _annotation_texts(figure)
        self.assertNotIn(True, ["=" in text for text in annotations])
        self.assertIn("Homozygous", annotations)
        self.assertIn("Somatic Insertion", annotations)
        self.assertEqual(annotations.count("Coverage (x)"), 1)
        self.assertTrue(all(title is None for title in _axis_titles(figure)))

    def test_caller_comparison_has_clean_facets_and_one_shared_x_title(self):
        figure = caller_comparison_figure(
            self.data,
            "Detection recall: caller comparison",
            "Detection recall",
        )
        annotations = _annotation_texts(figure)
        self.assertNotIn(True, ["=" in text for text in annotations])
        self.assertIn("5x", annotations)
        self.assertIn("15x", annotations)
        self.assertEqual(annotations.count("Biological Class"), 1)
        self.assertTrue(all(title is None for title in _axis_titles(figure)))
        shared_title = next(
            annotation
            for annotation in figure.layout.annotations
            if annotation.text == "Biological Class"
        )
        self.assertLessEqual(shared_title.y, -0.42)
        self.assertGreaterEqual(figure.layout.margin.b, 140)

    def test_somatic_coverage_facets_use_concise_labels(self):
        figure = somatic_figure(self.somatic_data)
        annotations = _annotation_texts(figure)
        self.assertNotIn(True, ["=" in text for text in annotations])
        self.assertIn("5x", annotations)
        self.assertIn("15x", annotations)


if __name__ == "__main__":
    unittest.main()
