import unittest
from pathlib import Path

from dashboard.data.loaders import load_reports
from dashboard.data.transforms import accuracy_summary, somatic_summary, te_group_summary
from dashboard.plots.overview import (
    dataset_comparison_figure,
    divergence_figure,
)
from dashboard.plots.accuracy import (
    accuracy_figure,
    caller_comparison_figure,
    somatic_figure,
    te_group_figure,
    te_group_heatmap,
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
        taxonomy = bundle.correctness.copy()
        taxonomy["te_group"] = [
            "LINE" if index % 2 == 0 else "SINE"
            for index in range(len(taxonomy))
        ]
        taxonomy["te_class"] = "Class_I"
        taxonomy["te_order"] = taxonomy["te_group"]
        taxonomy["te_superfamily"] = taxonomy["te_group"]
        cls.te_data = te_group_summary(taxonomy, "detection_recall")

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

    def test_te_group_figures_render_taxonomy(self):
        coverage = te_group_figure(
            self.te_data, "Recall by TE group", "Detection recall"
        )
        annotations = _annotation_texts(coverage)
        self.assertIn("LINE", annotations)
        self.assertIn("SINE", annotations)
        self.assertEqual(annotations.count("Coverage (x)"), 1)
        heatmap = te_group_heatmap(self.te_data, "Mean recall")
        self.assertEqual(set(heatmap.data[0].y), {"LINE", "SINE"})


if __name__ == "__main__":
    unittest.main()


class TestOverviewPlots(unittest.TestCase):
    """The cross-dataset page must obey the same axis conventions as every
    other page: canonical label names, and exactly one shared axis title on a
    faceted figure so titles never stack or overprint.
    """

    @classmethod
    def setUpClass(cls):
        import pandas as pd

        cls.summary = pd.DataFrame(
            {
                "dataset_key": ["mping", "mping", "ricetelib", "ricetelib"],
                "dataset_label": [
                    "mPing only", "mPing only", "riceTElib multi-TE", "riceTElib multi-TE"
                ],
                "caller": ["RelocaTE2", "RelocaTE3", "RelocaTE2", "RelocaTE3"],
                "detection_recall": [0.81, 0.77, 0.46, 0.44],
                "mean_sample_precision": [1.0, 1.0, 0.83, 0.80],
                "f1": [0.895, 0.870, 0.591, 0.566],
            }
        )
        cls.divergence = pd.DataFrame(
            {
                "caller": ["RelocaTE2"] * 6 + ["RelocaTE3"] * 6,
                "divergence_percent": [0.0, 5.0, 20.0] * 4,
                "coverage": [5, 5, 5, 30, 30, 30] * 2,
                "recall": [0.6, 0.4, 0.0, 0.8, 0.6, 0.01] * 2,
            }
        )

    def test_dataset_figure_uses_canonical_axis_names(self):
        figure = dataset_comparison_figure(self.summary, "f1", "F1 score")
        self.assertEqual(figure.layout.xaxis.title.text, "Dataset")
        self.assertEqual(figure.layout.yaxis.title.text, "F1 score")
        self.assertEqual(figure.layout.legend.title.text, "Caller")

    def test_dataset_figure_is_bounded_to_the_unit_interval(self):
        figure = dataset_comparison_figure(self.summary, "f1", "F1 score")
        self.assertEqual(tuple(figure.layout.yaxis.range), (0, 1))

    def test_divergence_figure_has_one_shared_x_title_and_clean_facets(self):
        figure = divergence_figure(self.divergence)
        annotations = _annotation_texts(figure)
        # No raw "coverage=5" facet headers.
        self.assertNotIn(True, ["=" in text for text in annotations])
        # Exactly one shared x title, never one per facet.
        self.assertEqual(annotations.count("TE divergence (%)"), 1)
        self.assertTrue(all(title is None for title in _axis_titles(figure)))

    def test_divergence_figure_uses_the_sidebar_wording_for_divergence(self):
        """The sidebar filter and glossary both say 'TE divergence (%)'."""
        figure = divergence_figure(self.divergence)
        self.assertIn("TE divergence (%)", _annotation_texts(figure))

    def test_divergence_facets_read_as_coverage_values(self):
        figure = divergence_figure(self.divergence)
        annotations = _annotation_texts(figure)
        self.assertIn("5x", annotations)
        self.assertIn("30x", annotations)
