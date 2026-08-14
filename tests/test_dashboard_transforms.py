import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

from dashboard.data.loaders import load_reports
from dashboard.data.transforms import (
    FilterSelection,
    accuracy_summary,
    apply_filters,
    available_filters,
    _f1,
    cross_dataset_summary,
    head_to_head_long,
    overall_summary,
    precision_summary,
    resource_summary,
    somatic_summary,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dashboard_reports"


class TestDashboardTransforms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_reports(FIXTURE_DIR)

    def test_available_filters_are_data_driven(self):
        options = available_filters(self.bundle)
        self.assertEqual(options["callers"], ("caller_a", "caller_b"))
        self.assertEqual(options["coverages"], (5, 15))
        self.assertEqual(options["cellular_fractions"], (0.2, 0.4, 1.0))

    def test_combined_filters(self):
        selected = FilterSelection(
            callers=("caller_a",), coverages=(15,), classes=("somatic_insertion",)
        )
        result = apply_filters(self.bundle.correctness, selected)
        self.assertEqual(len(result), 2)
        self.assertEqual(set(result["cellular_fraction"]), {0.2, 0.4})

    def test_empty_filter_means_no_selected_rows(self):
        result = apply_filters(self.bundle.correctness, FilterSelection(callers=()))
        self.assertTrue(result.empty)

    def test_optional_divergence_filter(self):
        frame = self.bundle.correctness.copy()
        frame["divergence_percent"] = [0 if i % 2 == 0 else 5 for i in range(len(frame))]
        result = apply_filters(
            frame, FilterSelection(divergences=(5,))
        )
        self.assertFalse(result.empty)
        self.assertEqual(set(result["divergence_percent"]), {5})

    def test_precision_comes_from_precision_table(self):
        data = precision_summary(self.bundle.precision, "overall_precision")
        value = data.query("caller == 'caller_a' and coverage == 5")["value"].iloc[0]
        self.assertAlmostEqual(value, 0.9375)
        self.assertNotAlmostEqual(value, self.bundle.correctness["class_call_share"].mean())

    def test_accuracy_uses_authoritative_counts(self):
        data = accuracy_summary(self.bundle.correctness, "exact_tsd_accuracy_given_detected")
        value = data.query(
            "caller == 'caller_a' and coverage == 5 and biological_class == 'homozygous'"
        )["value"].iloc[0]
        self.assertAlmostEqual(value, 8 / 9)

    def test_somatic_rows_and_values(self):
        data = somatic_summary(self.bundle.correctness)
        self.assertEqual(set(data["cellular_fraction"]), {0.2, 0.4})
        value = data.query(
            "caller == 'caller_a' and coverage == 15 and cellular_fraction == 0.4"
        )["detection_recall"].iloc[0]
        self.assertAlmostEqual(value, 0.7)

    def test_head_to_head_is_n_caller_tidy(self):
        data = head_to_head_long(self.bundle.head_to_head)
        self.assertEqual(set(data["caller"]), {"caller_a", "caller_b"})
        self.assertEqual(len(data), 12)
        value = data.query(
            "caller == 'caller_b' and coverage == 15 and biological_class == 'homozygous'"
        )["detection_recall"].iloc[0]
        self.assertAlmostEqual(value, 0.9)

    def test_overall_and_resource_summaries(self):
        overall = overall_summary(self.bundle.correctness, self.bundle.precision)
        self.assertEqual(set(overall["caller"]), {"caller_a", "caller_b"})
        resources = resource_summary(self.bundle.resources)
        row = resources.query("caller == 'caller_a' and coverage == 5").iloc[0]
        self.assertAlmostEqual(row["wall_minutes"], 2.0)
        self.assertAlmostEqual(row["max_rss_gib"], 1.0)


if __name__ == "__main__":
    unittest.main()


class TestCrossDatasetSummary(unittest.TestCase):
    """One row per dataset x caller, so the presentation can open with a
    single R3-vs-R2 view instead of switching the dataset selector six times.
    """

    @classmethod
    def setUpClass(cls):
        from dashboard.data.loaders import BenchmarkSuite

        bundle = load_reports(FIXTURE_DIR)
        cls.suite = BenchmarkSuite(
            report_dir=FIXTURE_DIR,
            datasets=(
                replace(bundle, dataset_key="mping", dataset_label="mPing only"),
                replace(bundle, dataset_key="ricetelib", dataset_label="riceTElib"),
            ),
        )

    def test_one_row_per_dataset_and_caller(self):
        summary = cross_dataset_summary(self.suite)
        self.assertEqual(
            set(summary["dataset_key"]), {"mping", "ricetelib"}
        )
        self.assertEqual(len(summary), 4)  # 2 datasets x 2 callers

    def test_carries_recall_precision_and_f1(self):
        summary = cross_dataset_summary(self.suite)
        for column in ("detection_recall", "mean_sample_precision", "f1"):
            self.assertIn(column, summary.columns)

    def test_f1_is_the_harmonic_mean_of_recall_and_precision(self):
        summary = cross_dataset_summary(self.suite)
        row = summary.iloc[0]
        r, p = row["detection_recall"], row["mean_sample_precision"]
        self.assertAlmostEqual(row["f1"], 2 * r * p / (r + p), places=9)

    def test_f1_is_zero_when_recall_and_precision_are_both_zero(self):
        """Guard the 0/0 that would otherwise produce NaN in the headline table."""
        frame = pd.DataFrame(
            {"detection_recall": [0.0], "mean_sample_precision": [0.0]}
        )
        self.assertEqual(list(_f1(frame)), [0.0])

    def test_dataset_label_is_preserved_for_display(self):
        summary = cross_dataset_summary(self.suite)
        self.assertEqual(
            set(summary["dataset_label"]), {"mPing only", "riceTElib"}
        )
