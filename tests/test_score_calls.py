import csv, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scoring.score_calls import score


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


if __name__ == "__main__":
    unittest.main()
