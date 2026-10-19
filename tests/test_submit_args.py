"""Argument handling in pipeline/submit_benchmark.sh (no submission)."""
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMIT = REPO_ROOT / "pipeline" / "submit_benchmark.sh"


def submit(*args):
    return subprocess.run(["bash", str(SUBMIT), *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=60)


class SubmitArgsTest(unittest.TestCase):
    def test_help_documents_rt3_repo(self):
        self.assertIn("--rt3-repo", submit("--help").stdout)

    def test_missing_repo_is_rejected_before_submission(self):
        result = submit("--rt3-repo", "/nonexistent/rt3")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--rt3-repo", result.stderr)

    def test_directory_without_relocate3_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = submit("--rt3-repo", tmp)
        self.assertEqual(result.returncode, 1)
        self.assertIn("src/RelocaTE3", result.stderr)
