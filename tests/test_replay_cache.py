"""Tests for the RelocaTE3 replay-cache guard (dev tier)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "callers" / "relocate3-replay" / "check_cache.py"
_spec = importlib.util.spec_from_file_location("check_cache", SCRIPT)
check_cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_cache)

GIT = ["git", "-c", "user.name=test", "-c", "user.email=test@example.org"]


def make_rt3_repo(root: Path) -> tuple[Path, str]:
    """A tiny git repo shaped like RelocaTE3; return (path, HEAD sha)."""
    repo = root / "rt3"
    pkg = repo / "src" / "RelocaTE3"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "aligners.py").write_text("BLAT = 1\n")
    (pkg / "ReadLibrary.py").write_text("NAMES = 1\n")
    (pkg / "librelocate.py").write_text("TRIM = 1\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*GIT, "-C", str(repo), "add", "-A"], check=True)
    subprocess.run([*GIT, "-C", str(repo), "commit", "-qm", "init"], check=True)
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return repo, sha


def make_cache(root: Path, sample: str = "s1") -> Path:
    """A completed checkpoint sample with every cached file present."""
    sample_dir = root / "runs" / "ds" / "src-caller" / sample
    raw = sample_dir / "raw"
    raw.mkdir(parents=True)
    for path in check_cache.cached_files(raw, sample):
        path.write_text(path.name)
    (sample_dir / ".run_complete").write_text("done\n")
    return sample_dir


class ReplayCacheTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo, self.rev = make_rt3_repo(self.root)
        self.sample_dir = make_cache(self.root)
        self.library = self.root / "library.fa"
        self.library.write_text(">te\nACGT\n")
        self.manifest = self.root / "manifest.json"
        check_cache.register(
            run_root=self.root / "runs",
            source_caller="src-caller",
            source_rev=self.rev,
            libraries={"ds": self.library},
            out=self.manifest,
            te_aligner="blat",
        )
        # Inputs that predate the cache, set explicitly rather than by write order.
        self.read1 = self.root / "R1.fq"
        self.read1.write_text("@r\nA\n+\nI\n")
        os.utime(self.sample_dir / ".run_complete", (2_000_000_000, 2_000_000_000))
        os.utime(self.read1, (1_000_000_000, 1_000_000_000))

    def tearDown(self):
        self._tmp.cleanup()

    def check(self, **overrides):
        kwargs = dict(
            manifest=self.manifest, repo=self.repo, dataset="ds",
            sample="s1", te_library=self.library, te_aligner="blat",
            inputs=(self.read1,),
        )
        kwargs.update(overrides)
        return check_cache.check(**kwargs)

    def test_register_records_rev_caller_and_library_hash(self):
        data = json.loads(self.manifest.read_text())
        self.assertEqual(data["source_rev"], self.rev)
        self.assertEqual(data["source_caller"], "src-caller")
        self.assertEqual(data["te_library_sha256"]["ds"], check_cache.sha256(self.library))
        self.assertEqual(data["guarded_files"], list(check_cache.GUARDED_FILES))
        self.assertEqual(data["te_aligner"], "blat")

    def test_te_aligner_match_passes(self):
        self.assertEqual(self.check(te_aligner="blat"), self.sample_dir / "raw")

    def test_te_aligner_mismatch_fails(self):
        with self.assertRaisesRegex(
            check_cache.CacheError,
            "replay caller TE aligner minimap2 does not match cache TE aligner blat; "
            "run the full tier",
        ):
            self.check(te_aligner="minimap2")

    def test_input_newer_than_cache_fails(self):
        os.utime(self.read1, (2_000_000_100, 2_000_000_100))
        with self.assertRaisesRegex(
            check_cache.CacheError, f"input {self.read1} changed after the cache was built"
        ):
            self.check()

    def test_input_older_than_cache_passes(self):
        os.utime(self.read1, (1_999_999_000, 1_999_999_000))
        self.assertEqual(self.check(), self.sample_dir / "raw")

    def test_missing_input_fails(self):
        with self.assertRaisesRegex(check_cache.CacheError, "missing.fq"):
            self.check(inputs=(self.root / "missing.fq",))

    def test_register_refuses_to_overwrite(self):
        with self.assertRaises(check_cache.CacheError):
            check_cache.register(
                run_root=self.root / "runs", source_caller="src-caller",
                source_rev=self.rev, libraries={"ds": self.library}, out=self.manifest,
                te_aligner="blat",
            )

    def test_unchanged_tree_returns_cached_raw_dir(self):
        self.assertEqual(self.check(), self.sample_dir / "raw")

    def test_uncommitted_edit_to_guarded_file_fails(self):
        (self.repo / "src/RelocaTE3/aligners.py").write_text("BLAT = 2\n")
        with self.assertRaisesRegex(check_cache.CacheError, "aligners.py"):
            self.check()

    def test_committed_edit_to_guarded_file_fails(self):
        (self.repo / "src/RelocaTE3/ReadLibrary.py").write_text("NAMES = 2\n")
        subprocess.run([*GIT, "-C", str(self.repo), "commit", "-qam", "edit"], check=True)
        with self.assertRaisesRegex(check_cache.CacheError, "ReadLibrary.py"):
            self.check()

    def test_edit_to_trim_code_is_allowed(self):
        (self.repo / "src/RelocaTE3/librelocate.py").write_text("TRIM = 2\n")
        self.assertEqual(self.check(), self.sample_dir / "raw")

    def test_te_library_mismatch_fails(self):
        self.library.write_text(">te\nACGTT\n")
        with self.assertRaisesRegex(check_cache.CacheError, "TE library"):
            self.check()

    def test_unregistered_dataset_fails(self):
        with self.assertRaisesRegex(check_cache.CacheError, "not registered"):
            self.check(dataset="other")

    def test_missing_cached_bam_fails(self):
        (self.sample_dir / "raw" / "s1.right.bam").unlink()
        with self.assertRaisesRegex(check_cache.CacheError, "s1.right.bam"):
            self.check()

    def test_missing_index_fails(self):
        (self.sample_dir / "raw" / "s1.original_reads.sorted.bam.bai").unlink()
        with self.assertRaisesRegex(check_cache.CacheError, "original_reads"):
            self.check()

    def test_incomplete_source_run_fails(self):
        (self.sample_dir / ".run_complete").unlink()
        with self.assertRaisesRegex(check_cache.CacheError, ".run_complete"):
            self.check()

    def test_register_rejects_non_sha_rev(self):
        for rev in ("HEAD", "main", self.rev[:7], self.rev.upper() + "0"):
            with self.subTest(rev=rev):
                with self.assertRaisesRegex(check_cache.CacheError, "40-hex"):
                    check_cache.register(
                        run_root=self.root / "runs", source_caller="src-caller",
                        source_rev=rev, libraries={"ds": self.library},
                        out=self.root / f"other-{len(rev)}.json",
                        te_aligner="blat",
                    )

    def test_subdirectory_repo_unchanged_passes(self):
        self.assertEqual(self.check(repo=self.repo / "src"), self.sample_dir / "raw")

    def test_subdirectory_repo_edit_fails(self):
        (self.repo / "src/RelocaTE3/aligners.py").write_text("BLAT = 2\n")
        with self.assertRaisesRegex(check_cache.CacheError, "aligners.py"):
            self.check(repo=self.repo / "src")

    def test_guarded_file_missing_from_working_tree_fails(self):
        (self.repo / "src/RelocaTE3/aligners.py").unlink()
        with self.assertRaisesRegex(check_cache.CacheError, "aligners.py"):
            self.check(repo=self.repo / "src")

    def test_empty_cached_file_fails(self):
        (self.sample_dir / "raw" / "s1.left.bam.bai").write_bytes(b"")
        with self.assertRaisesRegex(check_cache.CacheError, "s1.left.bam.bai"):
            self.check()

    def test_cli_prints_raw_dir_or_exits_2(self):
        base = [
            sys.executable, str(SCRIPT), "check", "--manifest", str(self.manifest),
            "--rt3-repo", str(self.repo), "--dataset", "ds", "--sample", "s1",
            "--te-library", str(self.library), "--te-aligner", "blat",
            "--input", str(self.read1),
        ]
        ok = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(ok.stdout.strip(), str(self.sample_dir / "raw"))
        (self.repo / "src/RelocaTE3/aligners.py").write_text("BLAT = 3\n")
        bad = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(bad.stdout, "")
        self.assertIn("full tier", bad.stderr)

    def test_cli_requires_te_aligner(self):
        args = [
            sys.executable, str(SCRIPT), "check", "--manifest", str(self.manifest),
            "--rt3-repo", str(self.repo), "--dataset", "ds", "--sample", "s1",
            "--te-library", str(self.library),
        ]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--te-aligner", result.stderr)

    def test_cli_register_records_te_aligner(self):
        out = self.root / "cli-manifest.json"
        result = subprocess.run([
            sys.executable, str(SCRIPT), "register", "--run-root", str(self.root / "runs"),
            "--source-caller", "src-caller", "--source-rev", self.rev,
            "--te-library", f"ds={self.library}", "--te-aligner", "blat", "--out", str(out),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(out.read_text())["te_aligner"], "blat")

    def test_cli_input_newer_than_cache_exits_2(self):
        os.utime(self.read1, (2_000_000_100, 2_000_000_100))
        result = subprocess.run([
            sys.executable, str(SCRIPT), "check", "--manifest", str(self.manifest),
            "--rt3-repo", str(self.repo), "--dataset", "ds", "--sample", "s1",
            "--te-library", str(self.library), "--te-aligner", "blat",
            "--input", str(self.read1),
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("changed after the cache was built", result.stderr)


if __name__ == "__main__":
    unittest.main()
