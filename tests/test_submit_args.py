"""Argument handling in pipeline/submit_benchmark.sh (no submission)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMIT = REPO_ROOT / "pipeline" / "submit_benchmark.sh"


def submit(*args, env=None):
    return subprocess.run(["bash", str(SUBMIT), *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=60, env=env)


def fake_checkout(root: Path, with_env: bool) -> Path:
    """A directory shaped like a RelocaTE3 checkout, optionally with its pixi env."""
    repo = root / "rt3"
    (repo / "src" / "RelocaTE3").mkdir(parents=True)
    (repo / "pixi.toml").write_text("[workspace]\n")
    if with_env:
        exe = repo / ".pixi" / "envs" / "default" / "bin" / "relocaTE3"
        exe.parent.mkdir(parents=True)
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)
    return repo


def guarded_env(root: Path, **extra) -> dict:
    """Environment in which the script cannot do real work past argument checks.

    sbatch only records that it was reached; pixi and python3* fail at once, so
    a regression that lets the script continue stops at its first config query
    instead of activating environments or staging inputs on the login node.
    """
    stub = root / "stub"
    stub.mkdir()
    (stub / "sbatch").write_text(f'#!/bin/sh\ntouch "{root}/sbatch-called"\nexit 1\n')
    for name in ("pixi", "python3", "python3.12"):
        (stub / name).write_text(f'#!/bin/sh\ntouch "{root}/{name}-called"\nexit 1\n')
    for path in stub.iterdir():
        path.chmod(0o755)
    env = {k: v for k, v in os.environ.items()
           if k not in ("CONFIG", "SLURM_SUBMIT_DIR")}
    env["PATH"] = f"{stub}:{env.get('PATH', '/usr/bin:/bin')}"
    env.update(extra)
    return env


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

    def test_checkout_without_pixi_env_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = fake_checkout(root, with_env=False)
            result = submit("--rt3-repo", str(repo), env=guarded_env(root))
            self.assertFalse((root / "sbatch-called").exists())
        self.assertEqual(result.returncode, 1)
        self.assertIn("run `pixi install` in", result.stderr)
        self.assertIn("first (on a compute node)", result.stderr)

    def test_checkpoint_profile_refuses_rt3_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = fake_checkout(root, with_env=True)
            env = guarded_env(root, CONFIG="config/benchmark.checkpoint-213a0df.toml")
            result = submit("--rt3-repo", str(repo), env=env)
            self.assertFalse((root / "sbatch-called").exists())
        self.assertEqual(result.returncode, 1)
        self.assertIn("pinned", result.stderr)
        self.assertIn("benchmark.checkpoint-213a0df.toml", result.stderr)

    def test_checkpoint_profile_refusal_precedes_checkout_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = guarded_env(root, CONFIG="config/benchmark.checkpoint-213a0df.toml")
            result = submit("--rt3-repo", "/nonexistent/rt3", env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("pinned", result.stderr)

    def test_valid_checkout_passes_rt3_repo_checks(self):
        # The stub pixi stops the script right after the --rt3-repo checks.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = fake_checkout(root, with_env=True)
            result = submit("--rt3-repo", str(repo), env=guarded_env(root))
            self.assertFalse((root / "sbatch-called").exists())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"RelocaTE3 callers will use: {repo}", result.stdout)
