import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_relocate2_validation import fixture


spec = importlib.util.spec_from_file_location(
    "r2recovery", "scripts/recover_checkpoint_r2.py"
)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class RecoveryTests(unittest.TestCase):
    def setup_case(self, root):
        work, reports, stage = (
            root / "work",
            root / "reports/datasets",
            root / "recovery",
        )
        old, new = work / "mping/relocate2/sample", stage / "mping/sample"
        for run in (old, new):
            fixture(run)
            (run / "calls.normalized.tsv").write_text(
                "original" if run == old else "recovered"
            )
        (old / ".run_complete").touch()
        (new / ".complete").touch()
        (new / "provenance.json").write_text(json.dumps({"scope": "recovery"}))
        for directory in (
            new / "report",
            reports / "mping/per_sample/relocate2/sample",
        ):
            directory.mkdir(parents=True)
            for name in ("precision.tsv", "correctness.tsv"):
                (directory / name).write_text("placeholder\n")
            (directory / "matches.tsv").write_text(
                "event_id\n" + "".join(f"e{i}\n" for i in range(500))
            )
        resource = reports / "mping/resources/relocate2/sample.tsv"
        resource.parent.mkdir(parents=True)
        resource.write_text("original full-run resource\n")
        return work, reports, stage, old, new

    def test_promotion_archives_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, reports, stage, old, new = self.setup_case(Path(tmp))
            with (
                patch.multiple(
                    recovery,
                    WORK=work,
                    REPORT=reports,
                    RECOVERY=stage,
                    TASKS=[("mping", "sample")],
                ),
                patch.object(recovery, "source_check"),
            ):
                recovery.promote()
                recovery.promote()
            self.assertEqual((old / "calls.normalized.tsv").read_text(), "recovered")
            archive = stage / "original-results/mping/sample"
            self.assertEqual((archive / "calls.normalized.tsv").read_text(), "original")
            self.assertTrue((archive / "original-resource.tsv").is_file())
            self.assertFalse(
                (reports / "mping/resources/relocate2/sample.tsv").exists()
            )
            self.assertTrue((new / ".promoted").is_file())

    def test_one_incomplete_task_prevents_all_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            work, reports, stage, old, new = self.setup_case(Path(tmp))
            with (
                patch.multiple(
                    recovery,
                    WORK=work,
                    REPORT=reports,
                    RECOVERY=stage,
                    TASKS=[("mping", "sample"), ("mping", "missing")],
                ),
                patch.object(recovery, "source_check"),
            ):
                with self.assertRaisesRegex(ValueError, "not complete"):
                    recovery.promote()
            self.assertEqual((old / "calls.normalized.tsv").read_text(), "original")
            self.assertFalse((stage / "original-results").exists())

    def test_worker_failure_propagates_without_overwriting_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "worker.log"
            with self.assertRaises(Exception):
                recovery.checked(["bash", "-c", "exit 7"], log)
            self.assertTrue(log.is_file())
            with self.assertRaises(FileExistsError):
                recovery.checked(["true"], log)

    def test_zero_exit_traceback_is_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "Internal worker"):
                recovery.checked(
                    ["printf", "Traceback (most recent call last):\n"],
                    Path(tmp) / "worker.log",
                )

    def test_login_node_execution_rejected(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SLURM"):
                recovery.run(0, 1)
