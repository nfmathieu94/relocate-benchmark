import csv, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scoring.compare_callers import main


HEADER = [
    "caller", "sample", "coverage", "replicate", "biological_class",
    "truth_events", "detected_events", "detection_recall",
    "status_correct_events", "status_accuracy_given_detected",
    "tsd_exact_events", "false_positive_calls", "precision",
]


def _row(caller, cls, recall, precision):
    return {
        "caller": caller, "sample": "cov5x_rep1", "coverage": "5", "replicate": "1",
        "biological_class": cls, "truth_events": "10", "detected_events": "5",
        "detection_recall": recall, "status_correct_events": "5",
        "status_accuracy_given_detected": "1.0", "tsd_exact_events": "5",
        "false_positive_calls": "2", "precision": precision,
    }


class TestCompareCallers(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.corr = self.d / "correctness.tsv"
        with open(self.corr, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=HEADER, delimiter="\t")
            w.writeheader()
            w.writerows([
                _row("relocate2", "homozygous", "0.5", "0.7"),
                _row("relocate3", "homozygous", "0.9", "0.8"),
                _row("relocate2", "heterozygous", "0.4", "0.6"),
                _row("relocate3", "heterozygous", "0.6", "0.5"),
            ])

    def test_pivot_and_delta(self):
        rc = main(["--correctness", str(self.corr), "--outdir", str(self.d)])
        self.assertEqual(rc, 0)
        out = self.d / "head_to_head.tsv"
        with open(out) as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        self.assertEqual(len(rows), 2)
        by_class = {r["biological_class"]: r for r in rows}
        hom = by_class["homozygous"]
        self.assertEqual(hom["relocate2_detection_recall"], "0.5")
        self.assertEqual(hom["relocate3_detection_recall"], "0.9")
        self.assertEqual(hom["relocate2_precision"], "0.7")
        self.assertIn("relocate2_status_accuracy_given_detected", hom)
        # delta column present (unordered pair, alpha order relocate2 < relocate3)
        delta_col = "relocate2_minus_relocate3_recall"
        self.assertIn(delta_col, hom)
        self.assertAlmostEqual(float(hom[delta_col]), 0.5 - 0.9, places=6)
        het = by_class["heterozygous"]
        self.assertAlmostEqual(float(het[delta_col]), 0.4 - 0.6, places=6)

    def test_missing_cell_blank(self):
        # relocate3 missing for a class -> its columns blank, delta blank
        corr = self.d / "c2.tsv"
        with open(corr, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=HEADER, delimiter="\t")
            w.writeheader()
            w.writerows([
                _row("relocate2", "homozygous", "0.5", "0.7"),
                _row("relocate3", "heterozygous", "0.6", "0.5"),
            ])
        rc = main(["--correctness", str(corr), "--outdir", str(self.d)])
        self.assertEqual(rc, 0)
        with open(self.d / "head_to_head.tsv") as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        by_class = {r["biological_class"]: r for r in rows}
        self.assertEqual(by_class["homozygous"]["relocate3_detection_recall"], "")
        self.assertEqual(by_class["homozygous"]["relocate2_minus_relocate3_recall"], "")


if __name__ == "__main__":
    unittest.main()
