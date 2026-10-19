"""Gate: dev-tier outputs must reproduce the checkpoint exactly."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "compare_replay_gate.py"
_spec = importlib.util.spec_from_file_location("gate", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

HEADER = "chrom\tposition\tte_family\ttsd\tstrand\tstatus\tcaller\tsample\n"


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class GateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def calls(self, root, caller, rows):
        write(self.root / root / "ds" / caller / "s1" / "calls.normalized.tsv",
              HEADER + "".join(f"Chr1\t{p}\tmPing\tTAA\t+\thomozygous\t{caller}\ts1\n"
                               for p in rows))

    def test_identical_calls_ignoring_caller_and_order_pass(self):
        self.calls("dev", "relocate3-replay", [200, 100])
        self.calls("ckpt", "relocate3-blat-bwaaln", [100, 200])
        rows = gate.compare_calls(self.root / "dev", self.root / "ckpt",
                                  {"relocate3-replay": "relocate3-blat-bwaaln"})
        self.assertEqual([r["status"] for r in rows], ["identical"])

    def test_differing_calls_fail_with_counts(self):
        self.calls("dev", "relocate3-replay", [100, 300])
        self.calls("ckpt", "relocate3-blat-bwaaln", [100, 200])
        (row,) = gate.compare_calls(self.root / "dev", self.root / "ckpt",
                                    {"relocate3-replay": "relocate3-blat-bwaaln"})
        self.assertEqual((row["status"], row["dev_only"], row["source_only"]),
                         ("different", 1, 1))

    def test_missing_dev_sample_is_reported(self):
        self.calls("ckpt", "relocate3-blat-bwaaln", [100])
        (row,) = gate.compare_calls(self.root / "dev", self.root / "ckpt",
                                    {"relocate3-replay": "relocate3-blat-bwaaln"})
        self.assertEqual(row["status"], "missing")

    def test_precision_tables_compare_without_caller_column(self):
        head = "caller\tsample\ttotal_calls\tmatched_calls\n"
        write(self.root / "rdev/datasets/ds/per_sample/relocate2-frozen/s1/precision.tsv",
              head + "relocate2-frozen\ts1\t10\t9\n")
        write(self.root / "rck/datasets/ds/per_sample/relocate2/s1/precision.tsv",
              head + "relocate2\ts1\t10\t9\n")
        (row,) = gate.compare_precision(self.root / "rdev", self.root / "rck",
                                        {"relocate2-frozen": "relocate2"})
        self.assertEqual(row["status"], "identical")


class GateCliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, dev_positions):
        for caller, root, positions in (
            ("relocate3-replay", "runs/dev", dev_positions),
            ("relocate3-blat-bwaaln", "runs/ck", [100, 200]),
        ):
            write(self.root / root / "ds" / caller / "s1" / "calls.normalized.tsv",
                  HEADER + "".join(f"Chr1\t{p}\tmPing\tTAA\t+\thomozygous\t{caller}\ts1\n"
                                   for p in positions))
        head = "caller\tsample\ttotal_calls\n"
        for caller, root in (("relocate3-replay", "reports/dev"),
                             ("relocate3-blat-bwaaln", "reports/ck")):
            write(self.root / root / "datasets/ds/per_sample" / caller / "s1/precision.tsv",
                  head + f"{caller}\ts1\t2\n")

    def run_cli(self):
        out = self.root / "out" / "gate.tsv"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--dev-runs", str(self.root / "runs/dev"),
             "--source-runs", str(self.root / "runs/ck"),
             "--dev-reports", str(self.root / "reports/dev"),
             "--source-reports", str(self.root / "reports/ck"),
             "--out", str(out)],
            capture_output=True, text=True)
        return proc, out

    def test_exit_zero_when_identical(self):
        self.build([200, 100])
        proc, out = self.run_cli()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(out.is_file())
        self.assertIn("identical", out.read_text())

    def test_exit_one_when_different(self):
        self.build([100, 999])
        proc, out = self.run_cli()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("different", out.read_text())


if __name__ == "__main__":
    unittest.main()
