import csv, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scoring.score_calls import score, main


def _write(path, header, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, delimiter="\t")
        w.writeheader(); w.writerows(rows)


class TestScore(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.truth = self.d / "truth.tsv"
        self.calls = self.d / "calls.tsv"
        _write(self.truth,
               ["event_id","chrom","position","te_family","biological_class","tsd"],
               [{"event_id":"E1","chrom":"Chr1","position":1000,"te_family":"mPing","biological_class":"homozygous","tsd":"TTA"},
                {"event_id":"E2","chrom":"Chr1","position":5000,"te_family":"mPing","biological_class":"somatic_insertion","tsd":"TAA"}])
        _write(self.calls,
               ["chrom","position","te_family","tsd","strand","status","caller","sample"],
               [{"chrom":"Chr1","position":1003,"te_family":"mPing","tsd":"TTA","strand":"+","status":"homozygous","caller":"relocate3","sample":"S1"},
                {"chrom":"Chr1","position":9999,"te_family":"mPing","tsd":"XX","strand":"+","status":"homozygous","caller":"relocate3","sample":"S1"}])

    def test_score(self):
        summary, matches, fps = score(self.truth, self.calls, sample="S1", caller="relocate3", window=10)
        by_class = {r["biological_class"]: r for r in summary}
        self.assertEqual(by_class["homozygous"]["detected_events"], 1)
        self.assertEqual(by_class["homozygous"]["status_correct_events"], 1)
        self.assertEqual(by_class["homozygous"]["tsd_exact_events"], 1)
        self.assertEqual(by_class["somatic_insertion"]["detected_events"], 0)
        self.assertEqual(len(fps), 1)

    def test_somatic_status_mapping(self):
        # A matched somatic event: truth biological_class="somatic_insertion",
        # call status="somatic". _norm maps somatic_insertion -> somatic, so this
        # must count as detected AND status-correct. Fails if that mapping is removed.
        truth = self.d / "truth_som.tsv"
        calls = self.d / "calls_som.tsv"
        _write(truth,
               ["event_id","chrom","position","te_family","biological_class","tsd"],
               [{"event_id":"S1","chrom":"Chr1","position":3000,"te_family":"mPing","biological_class":"somatic_insertion","tsd":"TTA"}])
        _write(calls,
               ["chrom","position","te_family","tsd","strand","status","caller","sample"],
               [{"chrom":"Chr1","position":3004,"te_family":"mPing","tsd":"TTA","strand":"+","status":"somatic","caller":"relocate3","sample":"S1"}])
        summary, matches, fps = score(truth, calls, sample="S1", caller="relocate3", window=10)
        by_class = {r["biological_class"]: r for r in summary}
        self.assertEqual(by_class["somatic_insertion"]["detected_events"], 1)
        self.assertEqual(by_class["somatic_insertion"]["status_correct_events"], 1)
        self.assertEqual(len(fps), 0)

    def test_main_writes_reports(self):
        # Truth/calls where every call matches a truth event -> zero false positives,
        # exercising the empty-file branch of _write for false_positive_calls.tsv.
        truth = self.d / "truth_main.tsv"
        calls = self.d / "calls_main.tsv"
        outdir = self.d / "report"
        _write(truth,
               ["event_id","chrom","position","te_family","biological_class","tsd"],
               [{"event_id":"M1","chrom":"Chr1","position":1000,"te_family":"mPing","biological_class":"homozygous","tsd":"TTA"}])
        _write(calls,
               ["chrom","position","te_family","tsd","strand","status","caller","sample"],
               [{"chrom":"Chr1","position":1002,"te_family":"mPing","tsd":"TTA","strand":"+","status":"homozygous","caller":"relocate3","sample":"S1"}])
        argv = ["--truth", str(truth), "--calls", str(calls),
                "--sample", "S1", "--caller", "relocate3",
                "--window", "10", "--outdir", str(outdir)]
        rc = main(argv)
        self.assertEqual(rc, 0)
        for name in ("matches.tsv", "false_positive_calls.tsv", "correctness.tsv", ".complete"):
            self.assertTrue((outdir / name).exists(), f"missing {name}")
        # zero false positives -> empty file
        self.assertEqual((outdir / "false_positive_calls.tsv").read_text(), "")
        # second run into the now non-empty dir must refuse
        with self.assertRaises(FileExistsError):
            main(argv)


if __name__ == "__main__":
    unittest.main()
