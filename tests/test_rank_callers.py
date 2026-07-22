import csv, os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scoring import rank_callers as rc


def _row(truth, detected, status_correct, **kw):
    d = {"truth_events": truth, "detected_events": detected,
         "status_correct_events": status_correct}
    d.update(kw)
    return d


def _write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, delimiter="\t")
        w.writeheader()
        w.writerows(rows)


CORR_HEADER = [
    "caller", "sample", "coverage", "replicate", "biological_class",
    "cellular_fraction", "expected_vaf", "truth_events", "detected_events",
    "detection_recall", "status_correct_events", "status_accuracy_given_detected",
    "tsd_exact_events", "false_positive_calls", "class_call_share",
]

PREC_HEADER = [
    "caller", "sample", "coverage", "replicate", "total_calls", "matched_calls",
    "overall_precision", "false_discovery_rate", "false_positive_calls",
]


def _corr(caller, cov, cls, frac, truth, detected, status_correct):
    return {
        "caller": caller, "sample": "s", "coverage": cov, "replicate": "1",
        "biological_class": cls, "cellular_fraction": frac, "expected_vaf": "1.0",
        "truth_events": str(truth), "detected_events": str(detected),
        "detection_recall": "0.0", "status_correct_events": str(status_correct),
        "status_accuracy_given_detected": "0.0", "tsd_exact_events": "0",
        "false_positive_calls": "0", "class_call_share": "0.5",
    }


def _prec(caller, precision, fp):
    return {
        "caller": caller, "sample": "s", "coverage": "5", "replicate": "1",
        "total_calls": "90", "matched_calls": "90",
        "overall_precision": precision, "false_discovery_rate": "0.0",
        "false_positive_calls": str(fp),
    }


def _fixture_reports(base):
    base = Path(base)
    _write(base / "correctness.tsv", CORR_HEADER, [
        _corr("relocate2", "5", "homozygous", "1.0", 100, 90, 80),
        _corr("relocate3-bwa-bwa", "5", "homozygous", "1.0", 100, 90, 88),
    ])
    _write(base / "precision.tsv", PREC_HEADER, [
        _prec("relocate2", "1.0", 0),
        _prec("relocate3-bwa-bwa", "1.0", 0),
    ])
    return base


class TestPooled(unittest.TestCase):
    def test_event_weighted(self):
        rows = [_row(100, 80, 40), _row(100, 60, 45)]
        m = rc.pooled(rows)
        self.assertEqual(m["recall"], (80 + 60) / 200)
        self.assertEqual(m["status_accuracy"], (40 + 45) / 140)
        self.assertAlmostEqual(m["composite"], 0.70 * (85 / 140))
        self.assertEqual(m["truth"], 200)
        self.assertEqual(m["detected"], 140)

    def test_zero_safe(self):
        m = rc.pooled([_row(0, 0, 0)])
        self.assertEqual(m["recall"], 0.0)
        self.assertEqual(m["status_accuracy"], 0.0)
        self.assertEqual(m["composite"], 0.0)


class TestRank(unittest.TestCase):
    def test_orders_desc_and_flags_ties(self):
        ranked = rc.rank({"a": 0.90, "b": 0.895, "c": 0.70}, tie_eps=0.01)
        self.assertEqual([r[1] for r in ranked], ["a", "b", "c"])
        self.assertTrue(ranked[1][3])   # b within 0.01 of a -> tie
        self.assertFalse(ranked[2][3])  # c not a tie
        self.assertEqual([r[0] for r in ranked], [1, 2, 3])


class TestBreakdowns(unittest.TestCase):
    def test_group_keys(self):
        rows = [
            _corr("x", "5", "homozygous", "1.0", 100, 90, 90),
            _corr("x", "30", "somatic_insertion", "0.1", 100, 50, 10),
            _corr("x", "30", "somatic_insertion", "0.4", 100, 70, 20),
        ]
        bd = rc.breakdowns(rows)
        self.assertEqual(set(bd["by_coverage"]), {"5", "30"})
        self.assertEqual(set(bd["by_class"]), {"homozygous", "somatic_insertion"})
        self.assertEqual(set(bd["by_somatic_fraction"]), {"0.1", "0.4"})
        self.assertIn("__overall__", bd["overall"])


class TestPrecisionByCaller(unittest.TestCase):
    def test_mean_and_fp_with_na(self):
        rows = [
            _prec("a", "1.0", 2),
            _prec("a", "0.5", 3),
            _prec("b", "NA", 1),
            _prec("b", "", 4),
        ]
        pc = rc.precision_by_caller(rows)
        self.assertAlmostEqual(pc["a"]["precision"], 0.75)
        self.assertEqual(pc["a"]["fp"], 5)
        self.assertIsNone(pc["b"]["precision"])
        self.assertEqual(pc["b"]["fp"], 5)


class TestIsStale(unittest.TestCase):
    def test_stale_when_per_sample_newer(self):
        with tempfile.TemporaryDirectory() as d:
            r = _fixture_reports(d)
            marker = r / "per_sample" / "relocate2" / "s" / ".complete"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
            os.utime(r / "correctness.tsv", (1, 1))  # make correctness.tsv old
            self.assertTrue(rc.is_stale(r))

    def test_stale_when_correctness_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(rc.is_stale(Path(d)))

    def test_not_stale_when_up_to_date(self):
        with tempfile.TemporaryDirectory() as d:
            r = _fixture_reports(d)
            self.assertFalse(rc.is_stale(r))


class TestMain(unittest.TestCase):
    def test_writes_report_ranked_by_composite(self):
        with tempfile.TemporaryDirectory() as d:
            r = _fixture_reports(d)
            out = rc.main(["--reports-dir", str(r), "--date", "20260722"])
            self.assertEqual(out, 0)
            md_path = r / "caller_ranking_20260722.md"
            self.assertTrue(md_path.exists())
            text = md_path.read_text()
            self.assertIn("Composite", text)
            self.assertIn("relocate3-bwa-bwa", text)
            self.assertIn("relocate2", text)
            # RT3 higher status accuracy -> higher composite -> ranked first
            self.assertLess(text.index("relocate3-bwa-bwa"), text.index("relocate2"))
            self.assertIn("20260722", text)


if __name__ == "__main__":
    unittest.main()
