import csv, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scoring import export_truth


def _write(path, header, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, delimiter="\t")
        w.writeheader(); w.writerows(rows)


class TestExportTruth(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.panel = self.root / "panel"
        self.panel.mkdir()
        self.outdir = self.root / "out"
        _write(
            self.panel / "truth_events.tsv",
            ["event_id", "chrom", "position", "te_id", "te_family",
             "biological_class", "cellular_fraction", "expected_vaf", "strand", "tsd"],
            [{"event_id": "E1", "chrom": "Chr1", "position": 1000, "te_id": "t1",
              "te_family": "mPing", "biological_class": "homozygous",
              "cellular_fraction": "1.0", "expected_vaf": "1.0", "strand": "+", "tsd": "TTA"},
             {"event_id": "E2", "chrom": "Chr1", "position": 200, "te_id": "t2",
              "te_family": "mPing", "biological_class": "heterozygous",
              "cellular_fraction": "0.5", "expected_vaf": "0.5", "strand": "-", "tsd": "TAA"}],
        )
        _write(
            self.panel / "panel_manifest.tsv",
            ["sample", "coverage", "replicate", "r1", "r2", "control_r1", "control_r2"],
            [{"sample": "S1", "coverage": "30", "replicate": "1", "r1": "a_1.fq",
              "r2": "a_2.fq", "control_r1": "c_1.fq", "control_r2": "c_2.fq"}],
        )

    def test_export_and_force(self):
        rc = export_truth.main(["--panel-root", str(self.panel), "--outdir", str(self.outdir)])
        self.assertEqual(rc, 0)

        with open(self.outdir / "truth.tsv") as fh:
            truth_rows = list(csv.DictReader(fh, delimiter="\t"))
        self.assertEqual(len(truth_rows), 2)

        with open(self.outdir / "truth.bed") as fh:
            bed_lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        self.assertEqual(len(bed_lines), 2)
        first = bed_lines[0].split("\t")
        self.assertEqual(first[0], "Chr1")
        self.assertEqual(first[1], "199")
        self.assertEqual(first[2], "200")
        self.assertEqual(first[3], "E2")

        self.assertTrue((self.outdir / ".complete").exists())

        # re-run without --force on non-empty outdir must fail
        with self.assertRaises(FileExistsError):
            export_truth.main(["--panel-root", str(self.panel), "--outdir", str(self.outdir)])

        # re-run WITH --force succeeds
        rc2 = export_truth.main(["--panel-root", str(self.panel), "--outdir", str(self.outdir), "--force"])
        self.assertEqual(rc2, 0)

    def test_missing_panel_files(self):
        empty = self.root / "empty_panel"
        empty.mkdir()
        with self.assertRaises(FileNotFoundError):
            export_truth.main(["--panel-root", str(empty), "--outdir", str(self.root / "out2")])

    def test_row_specific_truth_and_derived_sample(self):
        panel = self.root / "divergence"
        scenario = panel / "div005_rep01"
        scenario.mkdir(parents=True)
        _write(
            scenario / "truth_events.tsv",
            ["event_id", "chrom", "position", "te_family", "biological_class",
             "cellular_fraction", "expected_vaf", "strand", "tsd"],
            [{"event_id": "E1_div005_rep01", "chrom": "Chr1", "position": "100",
              "te_family": "TE1", "biological_class": "homozygous",
              "cellular_fraction": "1", "expected_vaf": "1", "strand": "+",
              "tsd": "TTA"}],
        )
        _write(
            panel / "panel_manifest.tsv",
            ["dataset_id", "divergence_percent", "divergence_replicate",
             "coverage", "truth_tsv", "r1", "r2"],
            [{"dataset_id": "div005_rep01", "divergence_percent": "5",
              "divergence_replicate": "1", "coverage": "15",
              "truth_tsv": "div005_rep01/truth_events.tsv",
              "r1": "reads/R1.fastq.gz", "r2": "reads/R2.fastq.gz"}],
        )
        outdir = self.root / "divergence_truth"
        self.assertEqual(
            export_truth.main(
                ["--panel-root", str(panel), "--outdir", str(outdir)]
            ),
            0,
        )
        with (outdir / "samples.tsv").open() as handle:
            sample = next(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(sample["sample"], "div005_rep01_cov15x")
        self.assertEqual(sample["replicate"], "1")
        exported = outdir / "per_sample" / "div005_rep01_cov15x.tsv"
        self.assertTrue(exported.is_file())
        self.assertIn("E1_div005_rep01", exported.read_text())


if __name__ == "__main__":
    unittest.main()
