import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Load the adapter's normalize.py by path (it lives in callers/relocate3, which
# is not an importable package).
_spec = importlib.util.spec_from_file_location(
    "relocate3_normalize", REPO_ROOT / "callers" / "relocate3" / "normalize.py"
)
normalize = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(normalize)

CHAR_HEADER = "strain\tTE\tTSD\tchromosome.pos\tstrand\tavg_flankers\tspanners\tstatus\n"
CHAR_ROWS = (
    "S1\tmPing\tTTA\tChr1:1000..1002\t+\t5\t2\thomozygous\n"
    "S1\tmPing\tTAA\tChr1:2000..2002\t-\t3\t0\tsomatic\n"
)


def _make_outdir(tmp: Path, *, write_txt: bool = True) -> Path:
    outdir = tmp / "S1"
    if write_txt:
        results = outdir / "raw" / "results"
        results.mkdir(parents=True)
        txt = results / "ALL.mPing.all_nonref_insert.characTErized.txt"
        txt.write_text(CHAR_HEADER + CHAR_ROWS)
    else:
        outdir.mkdir(parents=True)
    return outdir


class TestNormalizeRelocate3(unittest.TestCase):
    def test_writes_normalized_tsv(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = _make_outdir(Path(td))
            rc = normalize.main(["--outdir", str(outdir), "--sample", "S1"])
            self.assertEqual(rc, 0)

            out = outdir / "calls.normalized.tsv"
            self.assertTrue(out.is_file())

            with open(out) as fh:
                reader = csv.reader(fh, delimiter="\t")
                rows = list(reader)

            self.assertEqual(
                rows[0],
                ["chrom", "position", "te_family", "tsd", "strand", "status", "caller", "sample"],
            )
            data = rows[1:]
            self.assertEqual(len(data), 2)
            # caller column (index 6) is "relocate3" for every data row.
            self.assertTrue(all(r[6] == "relocate3" for r in data))
            # first parsed position (index 1) == 1000
            self.assertEqual(data[0][1], "1000")
            self.assertEqual(data[0][0], "Chr1")

    def test_missing_txt_raises(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = _make_outdir(Path(td), write_txt=False)
            with self.assertRaises(FileNotFoundError):
                normalize.main(["--outdir", str(outdir), "--sample", "S1"])


if __name__ == "__main__":
    unittest.main()


class TestNormalizeEmptyResult(unittest.TestCase):
    """A caller that finds nothing is a real benchmark outcome, not an error.

    At 20% TE divergence both callers collapse (measured: RelocaTE2 recall
    0.002, RelocaTE3 0.000), and RelocaTE3 writes a 0-byte table. That point
    must score as zero recall, so the normalizer has to emit a header-only
    TSV instead of raising.
    """

    def test_zero_byte_table_normalizes_to_header_only(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "S1"
            results = outdir / "raw" / "results"
            results.mkdir(parents=True)
            (results / "ALL.mPing.all_nonref_insert.characTErized.txt").write_text("")

            rc = normalize.main(["--outdir", str(outdir), "--sample", "S1"])
            self.assertEqual(rc, 0)

            out = outdir / "calls.normalized.tsv"
            self.assertTrue(out.is_file())
            with open(out) as fh:
                rows = list(csv.reader(fh, delimiter="\t"))
            self.assertEqual(
                rows[0],
                ["chrom", "position", "te_family", "tsd", "strand", "status", "caller", "sample"],
            )
            self.assertEqual(rows[1:], [])

    def test_header_only_table_normalizes_to_header_only(self):
        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "S1"
            results = outdir / "raw" / "results"
            results.mkdir(parents=True)
            (results / "ALL.mPing.all_nonref_insert.characTErized.txt").write_text(CHAR_HEADER)

            rc = normalize.main(["--outdir", str(outdir), "--sample", "S1"])
            self.assertEqual(rc, 0)
            with open(outdir / "calls.normalized.tsv") as fh:
                rows = list(csv.reader(fh, delimiter="\t"))
            self.assertEqual(rows[1:], [])
