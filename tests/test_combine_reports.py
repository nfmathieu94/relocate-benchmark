import csv, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scoring.combine_reports import main


CORR_HEADER = [
    "caller", "sample", "biological_class", "truth_events", "detected_events",
    "detection_recall", "status_correct_events", "status_accuracy_given_detected",
    "tsd_exact_events", "false_positive_calls", "precision",
]


def _write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, delimiter="\t")
        w.writeheader(); w.writerows(rows)


def _corr_row(caller, cls, recall):
    return {
        "caller": caller, "sample": "cov5x_rep1", "biological_class": cls,
        "truth_events": "10", "detected_events": "5", "detection_recall": recall,
        "status_correct_events": "5", "status_accuracy_given_detected": "1.0",
        "tsd_exact_events": "5", "false_positive_calls": "2", "precision": "0.7",
    }


class TestCombineReports(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.report = self.root / "reports"
        _write(self.report / "per_sample" / "relocate2" / "cov5x_rep1" / "correctness.tsv",
               CORR_HEADER, [_corr_row("relocate2", "homozygous", "0.5")])
        _write(self.report / "per_sample" / "relocate3" / "cov5x_rep1" / "correctness.tsv",
               CORR_HEADER, [_corr_row("relocate3", "homozygous", "0.9")])
        self.samples = self.root / "samples.tsv"
        _write(self.samples,
               ["sample", "coverage", "replicate", "r1", "r2", "control_r1", "control_r2"],
               [{"sample": "cov5x_rep1", "coverage": "5", "replicate": "1",
                 "r1": "a", "r2": "b", "control_r1": "c", "control_r2": "d"}])

    def test_union_and_join(self):
        rc = main(["--report-root", str(self.report), "--samples", str(self.samples)])
        self.assertEqual(rc, 0)
        out = self.report / "correctness.tsv"
        with open(out) as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        self.assertEqual(len(rows), 2)
        callers = {r["caller"] for r in rows}
        self.assertEqual(callers, {"relocate2", "relocate3"})
        for r in rows:
            self.assertEqual(r["coverage"], "5")
            self.assertEqual(r["replicate"], "1")
        # coverage/replicate inserted right after sample
        header = out.read_text().splitlines()[0].split("\t")
        self.assertEqual(header[:4], ["caller", "sample", "coverage", "replicate"])

    def test_empty_per_sample_does_not_crash(self):
        empty = self.root / "empty_reports"
        (empty / "per_sample").mkdir(parents=True)
        rc = main(["--report-root", str(empty), "--samples", str(self.samples)])
        self.assertEqual(rc, 0)
        self.assertTrue((empty / "correctness.tsv").exists())

    def test_resources_aggregation(self):
        _write(self.report / "resources" / "relocate2" / "cov5x_rep1.tsv",
               ["caller", "sample", "wall_seconds"],
               [{"caller": "relocate2", "sample": "cov5x_rep1", "wall_seconds": "10"}])
        _write(self.report / "resources" / "relocate3" / "cov5x_rep1.tsv",
               ["caller", "sample", "wall_seconds", "max_rss_kb"],
               [{"caller": "relocate3", "sample": "cov5x_rep1", "wall_seconds": "20",
                 "max_rss_kb": "999"}])
        rc = main(["--report-root", str(self.report), "--samples", str(self.samples)])
        self.assertEqual(rc, 0)
        res = self.report / "resources.tsv"
        with open(res) as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        self.assertEqual(len(rows), 2)
        self.assertIn("max_rss_kb", rows[0].keys())


if __name__ == "__main__":
    unittest.main()
