"""Tests for the frozen-baseline caller adapter."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN = REPO_ROOT / "callers" / "frozen" / "run.sh"
NORMALIZE = REPO_ROOT / "callers" / "frozen" / "normalize.py"
CALLS = (
    "chrom\tposition\tte_family\ttsd\tstrand\tstatus\tcaller\tsample\n"
    "Chr1\t100\tmPing\tTAA\t+\thomozygous\trelocate2\ts1\n"
)


class FrozenAdapterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / "src" / "ds" / "relocate2" / "s1"
        self.source.mkdir(parents=True)
        (self.source / "calls.normalized.tsv").write_text(CALLS)
        (self.source / ".run_complete").write_text("done\n")
        self.outdir = self.root / "out" / "s1"
        self.env = {
            **os.environ,
            "DATASET": "ds",
            "SAMPLE": "s1",
            "OUTDIR": str(self.outdir),
            "FROZEN_SOURCE_ROOT": str(self.root / "src"),
            "FROZEN_SOURCE_CALLER": "relocate2",
        }

    def tearDown(self):
        self._tmp.cleanup()

    def run_adapter(self):
        return subprocess.run(["bash", str(RUN)], env=self.env,
                              capture_output=True, text=True)

    def test_copies_calls_and_records_provenance(self):
        result = self.run_adapter()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.outdir / "calls.normalized.tsv").read_text(), CALLS)
        self.assertTrue((self.outdir / ".run_complete").is_file())
        self.assertIn(str(self.source), (self.outdir / "frozen_source.tsv").read_text())

    def test_incomplete_source_is_refused(self):
        (self.source / ".run_complete").unlink()
        result = self.run_adapter()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.outdir / ".run_complete").exists())

    def test_rerun_is_a_no_op(self):
        self.assertEqual(self.run_adapter().returncode, 0)
        (self.source / "calls.normalized.tsv").write_text(CALLS + "changed\n")
        self.assertEqual(self.run_adapter().returncode, 0)
        self.assertEqual((self.outdir / "calls.normalized.tsv").read_text(), CALLS)

    def test_nonempty_incomplete_outdir_is_refused(self):
        self.outdir.mkdir(parents=True)
        (self.outdir / "stray").write_text("x")
        self.assertNotEqual(self.run_adapter().returncode, 0)

    def test_normalize_validates_copied_calls(self):
        self.run_adapter()
        ok = subprocess.run(
            [sys.executable, str(NORMALIZE), "--outdir", str(self.outdir),
             "--sample", "s1"], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("1 calls", ok.stderr)
        (self.outdir / "calls.normalized.tsv").unlink()
        missing = subprocess.run(
            [sys.executable, str(NORMALIZE), "--outdir", str(self.outdir),
             "--sample", "s1"], capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)


if __name__ == "__main__":
    unittest.main()
