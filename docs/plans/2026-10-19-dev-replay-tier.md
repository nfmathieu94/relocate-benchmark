# Fast Development Tier (RelocaTE3 replay + frozen RelocaTE2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a RelocaTE3 change be benchmarked in hours instead of days by
replaying the post-TE-search stages from cached checkpoint intermediates and
reusing RelocaTE2's frozen calls.

**Architecture:** Benchmark-side only; RelocaTE3 is untouched. A stdlib guard
(`callers/relocate3-replay/check_cache.py`) registers the checkpoint cache and
refuses stale replays. The standard RelocaTE3 adapter gains an opt-in replay
branch (`RT3_REPLAY_MANIFEST`), wrapped by `callers/relocate3-replay/`. A
`callers/frozen/` adapter copies stored normalized calls. A new
`config/benchmark.dev.toml` wires both in. Design:
`docs/plans/2026-10-19-dev-replay-tier-design.md`.

**Tech Stack:** bash adapters, Python 3.12 stdlib, `unittest` (repo convention), git, SLURM.

---

## Conventions for every task

- Work in the worktree:
  `/rhome/nmath020/bigdata/github/github_tools/RelocaTE/relocate_benchmark/relocate-benchmark-dev-replay`
  (branch `feat/dev-replay-tier`). Paths below are relative to it.
- Test interpreter (stdlib + pandas; no pytest). Define once per shell:
  `PYB=../relocate-benchmark/env/benchmark/.pixi/envs/default/bin/python3`
- Run one module: `$PYB -m unittest tests.test_<name> -v` (from repo root;
  existing tests import siblings via `tests/` on sys.path, so use
  `$PYB -m unittest discover -s tests -p 'test_<name>.py' -v`).
- Baseline before Task 1: `$PYB -m unittest discover -s tests` → 125 tests,
  1 import error (`test_coordinate_policy` needs pytest; it passes under
  `../../RelocaTE3_jason/RelocaTE3/.pixi/envs/default/bin/python -m pytest tests/test_coordinate_policy.py`).
  New work must not add failures.
- Never submit SLURM jobs or run real RelocaTE3 from these tasks. Unit tests use
  temp dirs and stub executables only.
- Commit after each task. End every commit message with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1: Cache guard and manifest (`check_cache.py`)

**Files:**
- Create: `callers/relocate3-replay/check_cache.py`
- Test: `tests/test_replay_cache.py`

**Step 1: Write the failing tests**

```python
"""Tests for the RelocaTE3 replay-cache guard (dev tier)."""
import importlib.util
import json
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
        )

    def tearDown(self):
        self._tmp.cleanup()

    def check(self, **overrides):
        kwargs = dict(
            manifest=self.manifest, repo=self.repo, dataset="ds",
            sample="s1", te_library=self.library,
        )
        kwargs.update(overrides)
        return check_cache.check(**kwargs)

    def test_register_records_rev_caller_and_library_hash(self):
        data = json.loads(self.manifest.read_text())
        self.assertEqual(data["source_rev"], self.rev)
        self.assertEqual(data["source_caller"], "src-caller")
        self.assertEqual(data["te_library_sha256"]["ds"], check_cache.sha256(self.library))
        self.assertEqual(data["guarded_files"], list(check_cache.GUARDED_FILES))

    def test_register_refuses_to_overwrite(self):
        with self.assertRaises(check_cache.CacheError):
            check_cache.register(
                run_root=self.root / "runs", source_caller="src-caller",
                source_rev=self.rev, libraries={"ds": self.library}, out=self.manifest,
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

    def test_cli_prints_raw_dir_or_exits_2(self):
        base = [
            sys.executable, str(SCRIPT), "check", "--manifest", str(self.manifest),
            "--rt3-repo", str(self.repo), "--dataset", "ds", "--sample", "s1",
            "--te-library", str(self.library),
        ]
        ok = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(ok.stdout.strip(), str(self.sample_dir / "raw"))
        (self.repo / "src/RelocaTE3/aligners.py").write_text("BLAT = 3\n")
        bad = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(bad.stdout, "")
        self.assertIn("full tier", bad.stderr)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run to verify failure**

Run: `$PYB -m unittest discover -s tests -p 'test_replay_cache.py' -v`
Expected: ERROR — `FileNotFoundError`/no such file `check_cache.py`.

**Step 3: Implement**

```python
#!/usr/bin/env python3
"""Register and guard the RelocaTE3 replay cache for the development tier.

``register`` records a completed full-tier run whose TE-search BAMs
(``<sample>.left/right.bam``) and all-read genotyping BAM
(``<sample>.original_reads.sorted.bam``) may be replayed.

``check`` verifies that one sample may be replayed against the RelocaTE3 tree
under test and prints that sample's cached ``raw/`` directory. It refuses when
the TE-search source or the TE library no longer matches the cache, because the
replay would then silently score stale TE-search output.

Known blind spot: the mapping half of ``librelocate.py`` (``identify_TE_reads``)
is not hashed, since the same file holds the trimming code under development.
Changes to TE search must be measured with the full tier.

Stdlib only: runs under the cluster ``python3.12`` before any pixi activation.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# Source that produced the cached TE-search BAMs: BLAT invocation and
# parameters, query chunking, PSL->SAM conversion, and read-file naming.
GUARDED_FILES = ("src/RelocaTE3/aligners.py", "src/RelocaTE3/ReadLibrary.py")


class CacheError(RuntimeError):
    """The cache cannot be replayed for this sample."""


def sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cached_files(raw: Path, sample: str) -> list[Path]:
    names = (
        f"{sample}.left.bam",
        f"{sample}.right.bam",
        f"{sample}.original_reads.sorted.bam",
    )
    return [raw / name for name in names] + [raw / f"{name}.bai" for name in names]


def check_source(repo: Path, rev: str) -> None:
    """Fail unless the guarded files in ``repo``'s working tree equal ``rev``."""
    command = ["git", "-C", str(repo), "diff", "--quiet", rev, "--", *GUARDED_FILES]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 1:
        changed = subprocess.run(
            ["git", "-C", str(repo), "diff", "--name-only", rev, "--", *GUARDED_FILES],
            capture_output=True, text=True,
        ).stdout.split()
        raise CacheError(
            f"TE-search source differs from cache revision {rev}: "
            f"{', '.join(changed)}; the cached BAMs are stale, run the full tier"
        )
    if result.returncode != 0:
        raise CacheError(f"cannot compare {repo} with {rev}: {result.stderr.strip()}")


def register(run_root, source_caller, source_rev, libraries, out) -> dict:
    out = Path(out)
    if out.exists():
        raise CacheError(f"refusing to overwrite existing manifest: {out}")
    manifest = {
        "source_rev": source_rev,
        "run_root": str(run_root),
        "source_caller": source_caller,
        "guarded_files": list(GUARDED_FILES),
        "te_library_sha256": {
            dataset: sha256(path) for dataset, path in sorted(libraries.items())
        },
        "registered": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def check(manifest, repo, dataset, sample, te_library) -> Path:
    data = json.loads(Path(manifest).read_text())
    check_source(Path(repo), data["source_rev"])
    expected = data["te_library_sha256"].get(dataset)
    if expected is None:
        raise CacheError(f"dataset {dataset!r} is not registered in {manifest}")
    if sha256(te_library) != expected:
        raise CacheError(
            f"TE library {te_library} differs from the one the cache was built with"
        )
    sample_dir = Path(data["run_root"]) / dataset / data["source_caller"] / sample
    if not (sample_dir / ".run_complete").is_file():
        raise CacheError(f"source run is incomplete (no .run_complete): {sample_dir}")
    raw = sample_dir / "raw"
    missing = [str(path) for path in cached_files(raw, sample) if not path.is_file()]
    if missing:
        raise CacheError("cached file(s) missing: " + ", ".join(missing))
    return raw


def _library_arg(value: str) -> tuple[str, Path]:
    dataset, sep, path = value.partition("=")
    if not sep or not dataset or not path:
        raise argparse.ArgumentTypeError("expected DATASET=PATH")
    return dataset, Path(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    reg = sub.add_parser("register", help="record a full-tier run as a replay cache")
    reg.add_argument("--run-root", required=True)
    reg.add_argument("--source-caller", required=True)
    reg.add_argument("--source-rev", required=True)
    reg.add_argument("--te-library", action="append", type=_library_arg, required=True,
                     metavar="DATASET=PATH")
    reg.add_argument("--out", required=True)
    chk = sub.add_parser("check", help="verify one sample; print its cached raw/ dir")
    chk.add_argument("--manifest", required=True)
    chk.add_argument("--rt3-repo", required=True)
    chk.add_argument("--dataset", required=True)
    chk.add_argument("--sample", required=True)
    chk.add_argument("--te-library", required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "register":
            register(args.run_root, args.source_caller, args.source_rev,
                     dict(args.te_library), args.out)
            print(f"registered replay cache: {args.out}", file=sys.stderr)
        else:
            print(check(args.manifest, args.rt3_repo, args.dataset, args.sample,
                        args.te_library))
    except (CacheError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: replay cache: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4: Run to verify pass**

Run: `$PYB -m unittest discover -s tests -p 'test_replay_cache.py' -v`
Expected: 12 tests OK.

**Step 5: Commit**

```bash
git add callers/relocate3-replay/check_cache.py tests/test_replay_cache.py
git commit -m "feat(replay): guard and register the RelocaTE3 replay cache"
```

---

### Task 2: Config bridge exports + `RT3_REPO_OVERRIDE` + array allowlist

**Files:**
- Modify: `pipeline/config_env.py` (`ADAPTER_ENV_MAP`, `_caller_env`, add `import os`)
- Modify: `pipeline/run_benchmark_array.sh` (allowlist `for variable in …`)
- Test: `tests/test_config_env.py` (append a new `TestCase`)

**Step 1: Write the failing tests** (append to `tests/test_config_env.py`)

```python
import os
import re
from unittest.mock import patch

DEV_CALLERS = """
[run]
work_root = "runs"
threads   = 8

[scoring]
match_window = 10

[datasets.d1]
panel_root   = "{panel}"
reference    = "/ref.fa"
te_library   = "/te.fa"
repeatmasker = "/rm.out"
te_name      = "mPing"

[callers.relocate2-frozen]
enabled       = true
adapter       = "callers/frozen"
source_root   = "runs/checkpoint-213a0df"
source_caller = "relocate2"

[callers.relocate3-replay]
enabled         = true
adapter         = "callers/relocate3-replay"
adapter_type    = "relocate3"
repo            = "/configured/rt3"
genome_aligner  = "bwaaln"
replay_manifest = "config/replay/checkpoint-213a0df.json"
"""


class DevTierEnvTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        (tmp / "panel").mkdir()
        (tmp / "panel" / "panel_manifest.tsv").write_text(MANIFEST)
        self.cfg = tmp / "dev.toml"
        self.cfg.write_text(DEV_CALLERS.format(panel=tmp / "panel"))

    def tearDown(self):
        self._tmp.cleanup()

    def env(self, caller):
        return config_env.run(["--config", str(self.cfg), "caller-env", caller])

    def test_frozen_adapter_exports_source(self):
        out = self.env("relocate2-frozen")
        self.assertIn("FROZEN_SOURCE_ROOT='runs/checkpoint-213a0df'", out)
        self.assertIn("FROZEN_SOURCE_CALLER='relocate2'", out)

    def test_replay_caller_exports_manifest(self):
        out = self.env("relocate3-replay")
        self.assertIn(
            "RT3_REPLAY_MANIFEST='config/replay/checkpoint-213a0df.json'", out
        )
        self.assertIn("RT3_REPO='/configured/rt3'", out)

    def test_rt3_repo_override_replaces_configured_repo(self):
        with patch.dict(os.environ, {"RT3_REPO_OVERRIDE": "/work/tree"}):
            out = self.env("relocate3-replay")
        self.assertIn("RT3_REPO='/work/tree'", out)
        self.assertNotIn("/configured/rt3", out)

    def test_override_does_not_add_repo_to_other_adapters(self):
        with patch.dict(os.environ, {"RT3_REPO_OVERRIDE": "/work/tree"}):
            out = self.env("relocate2-frozen")
        self.assertNotIn("RT3_REPO", out)

    def test_array_allowlist_exports_every_mapped_variable(self):
        text = (REPO_ROOT / "pipeline" / "run_benchmark_array.sh").read_text()
        match = re.search(r"for variable in (.*?); do", text, re.S)
        allowlisted = set(match.group(1).replace("\\", " ").split())
        mapped = {
            env for table in config_env.ADAPTER_ENV_MAP.values() for env in table.values()
        }
        self.assertEqual(mapped - allowlisted, set())
```

**Step 2: Run to verify failure**

Run: `$PYB -m unittest discover -s tests -p 'test_config_env.py' -v`
Expected: the 5 new tests FAIL (missing exports); existing tests pass.

**Step 3: Implement**

In `pipeline/config_env.py` add `import os`, then:

```python
ADAPTER_ENV_MAP: dict[str, dict[str, str]] = {
    "relocate3": {
        "repo": "RT3_REPO",
        "tsd": "TSD_PATTERN",
        "te_aligner": "RT3_TE_ALIGNER",
        "genome_aligner": "RT3_GENOME_ALIGNER",
        "require_both_junctions": "RT3_REQUIRE_BOTH_JUNCTIONS",
        "replay_manifest": "RT3_REPLAY_MANIFEST",
    },
    "relocate2": {
        "aligner": "RT2_ALIGNER",
        "size": "RT2_SIZE",
        "mismatch": "RT2_MISMATCH",
    },
    "frozen": {
        "source_root": "FROZEN_SOURCE_ROOT",
        "source_caller": "FROZEN_SOURCE_CALLER",
    },
}
```

and in `_caller_env`, replace the `lines = [...]` comprehension with:

```python
    values = {env: table[key] for key, env in mapping.items() if key in table}
    # submit_benchmark.sh --rt3-repo: test another RelocaTE3 checkout (e.g. a
    # feature worktree) without editing the config.
    override = os.environ.get("RT3_REPO_OVERRIDE")
    if override and "RT3_REPO" in values:
        values["RT3_REPO"] = override
    lines = [f"{env}={_sq(value)}" for env, value in values.items()]
```

In `pipeline/run_benchmark_array.sh` extend the allowlist:

```bash
for variable in RT3_REPO TSD_PATTERN RT3_TE_ALIGNER RT3_GENOME_ALIGNER \
                RT3_REQUIRE_BOTH_JUNCTIONS RT3_REPLAY_MANIFEST \
                RT2_ALIGNER RT2_SIZE RT2_MISMATCH \
                FROZEN_SOURCE_ROOT FROZEN_SOURCE_CALLER; do
```

**Step 4: Verify** — same command; all `test_config_env` tests pass. Then the
whole suite: `$PYB -m unittest discover -s tests` → only the known pytest import error.

**Step 5: Commit**

```bash
git add pipeline/config_env.py pipeline/run_benchmark_array.sh tests/test_config_env.py
git commit -m "feat(config): export replay/frozen caller keys and RT3_REPO_OVERRIDE"
```

---

### Task 3: Frozen-baseline adapter (`callers/frozen/`)

**Files:**
- Create: `callers/frozen/run.sh`, `callers/frozen/normalize.py`
- Test: `tests/test_frozen_adapter.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run to verify failure**

Run: `$PYB -m unittest discover -s tests -p 'test_frozen_adapter.py' -v`
Expected: FAIL (scripts missing; bash exits 127).

**Step 3: Implement**

`callers/frozen/run.sh`:

```bash
#!/usr/bin/bash -l
# Frozen-baseline caller adapter (development tier).
#
# Re-scores a caller that is not under development (RelocaTE2) without rerunning
# it: copies <FROZEN_SOURCE_ROOT>/<DATASET>/<FROZEN_SOURCE_CALLER>/<SAMPLE>/
# calls.normalized.tsv into OUTDIR. Scoring then runs as for any caller, so the
# baseline always follows the current scoring policy. This task's resource
# usage measures a file copy, not the caller.
#
# Contract (env vars): DATASET SAMPLE OUTDIR FROZEN_SOURCE_ROOT FROZEN_SOURCE_CALLER
set -euo pipefail

: "${DATASET:?DATASET must be set}"
: "${SAMPLE:?SAMPLE must be set}"
: "${OUTDIR:?OUTDIR must be set}"
: "${FROZEN_SOURCE_ROOT:?FROZEN_SOURCE_ROOT must be set (config source_root)}"
: "${FROZEN_SOURCE_CALLER:?FROZEN_SOURCE_CALLER must be set (config source_caller)}"

SOURCE_DIR="$FROZEN_SOURCE_ROOT/$DATASET/$FROZEN_SOURCE_CALLER/$SAMPLE"
SOURCE_CALLS="$SOURCE_DIR/calls.normalized.tsv"

if [[ -f "$OUTDIR/.run_complete" ]]; then
  echo "[$(date)] frozen copy already complete for '$SAMPLE'; skipping."
  exit 0
fi
if [[ -d "$OUTDIR" ]] && [[ -n "$(ls -A "$OUTDIR" 2>/dev/null)" ]]; then
  echo "ERROR: refusing incomplete non-empty run dir: $OUTDIR" >&2
  exit 1
fi
if [[ ! -f "$SOURCE_DIR/.run_complete" ]]; then
  echo "ERROR: frozen source run is incomplete (no .run_complete): $SOURCE_DIR" >&2
  exit 1
fi
if [[ ! -f "$SOURCE_CALLS" ]]; then
  echo "ERROR: frozen source calls missing: $SOURCE_CALLS" >&2
  exit 1
fi

echo "[$(date)] frozen baseline: $SOURCE_CALLS"
mkdir -p "$OUTDIR"
cp "$SOURCE_CALLS" "$OUTDIR/calls.normalized.tsv.tmp"
mv -f "$OUTDIR/calls.normalized.tsv.tmp" "$OUTDIR/calls.normalized.tsv"
printf 'source\t%s\n' "$SOURCE_CALLS" > "$OUTDIR/frozen_source.tsv"
date > "$OUTDIR/.run_complete"
```

`callers/frozen/normalize.py`:

```python
#!/usr/bin/env python3
"""Validate a frozen baseline's copied calls.normalized.tsv (already normalized)."""
import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", required=True, type=Path)
    ap.add_argument("--sample", required=True)
    # Accepted for the uniform normalizer CLI; unused here.
    ap.add_argument("--te-name", default="mPing")
    ap.add_argument("--target", default="ALL")
    args = ap.parse_args(argv)
    calls = args.outdir / "calls.normalized.tsv"
    if not calls.is_file():
        print(f"ERROR: frozen calls missing: {calls}", file=sys.stderr)
        return 1
    rows = max(0, len(calls.read_text().splitlines()) - 1)
    print(f"frozen {args.sample}: {rows} calls", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4: Verify** — same command; 5 tests OK.

**Step 5: Commit**

```bash
git add callers/frozen tests/test_frozen_adapter.py
git commit -m "feat(frozen): re-score a frozen caller's calls without rerunning it"
```

---

### Task 4: Replay branch in the RelocaTE3 adapter + `relocate3-replay` wrappers

**Files:**
- Modify: `callers/relocate3/run.sh` (guard before section 2; PYTHONPATH check after
  section 4; branch steps 2+3 and the genotyping-BAM build)
- Create: `callers/relocate3-replay/run.sh`, `callers/relocate3-replay/normalize.py`
- Test: `tests/test_relocate3_replay.py`

**Step 1: Write the failing tests**

The test drives the real adapter with stub executables on a minimal PATH
(`stub/` + `/usr/bin:/bin`). `pixi` and `module` are absent, so `env.sh` falls
through to the stubs. The stub `relocaTE3` logs each call and writes the files
the adapter checks for.

```python
"""End-to-end test of the RelocaTE3 adapter's replay branch with stub tools."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_cache", REPO_ROOT / "callers" / "relocate3-replay" / "check_cache.py")
check_cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_cache)
from test_replay_cache import make_cache, make_rt3_repo  # noqa: E402

STUB_RELOCATE3 = r'''#!{python}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
def opt(*names):
    for name in names:
        if name in args:
            return args[args.index(name) + 1]
cmd = args[0]
if cmd in ("run", "trim"):
    out, name = Path(opt("--outdir")), opt("--name")
    (out / "te_containing").mkdir(parents=True, exist_ok=True)
    (out / "te_containing" / f"{name}.read_repeat_name.txt").write_text("r1\tmPing\n")
    (out / "flanking").mkdir(exist_ok=True)
    (out / "flanking" / f"{name}.left.flankingReads.fq").write_text("@r1\nACGT\n+\nIIII\n")
elif cmd == "align-genome":
    out, name = Path(opt("-o")), opt("-n")
    aligner = opt("--genome-aligner")
    (out / f"{name}.repeat.{aligner}.sorted.bam").write_text("bam")
elif cmd == "find-insertions":
    out = Path(opt("--outdir")) / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{opt('--target')}.{opt('--te-name')}.all_nonref_insert.txt").write_text("")
elif cmd == "characterize":
    sites = Path(opt("-s"))
    out = Path(opt("-o"))
    (out / (sites.stem + ".characTErized.txt")).write_text("")
'''

STUB_MARK = "#!/bin/sh\necho \"$(basename \"$0\") $*\" >> \"$STUB_LOG\"\n"
STUB_SAMTOOLS = r'''#!{python}
import os, sys
from pathlib import Path
with open(os.environ["STUB_LOG"], "a") as log:
    log.write("samtools " + " ".join(sys.argv[1:]) + "\n")
if sys.argv[1] == "sort":
    sys.stdin.read()
    Path(sys.argv[sys.argv.index("-o") + 1]).write_text("bam")
'''


class ReplayAdapterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = self.root = Path(self._tmp.name)
        self.repo, rev = make_rt3_repo(root)
        self.cache_sample = make_cache(root, sample="s1")
        stub = root / "stub"
        stub.mkdir()
        for name, text in (
            ("relocaTE3", STUB_RELOCATE3.format(python=sys.executable)),
            ("samtools", STUB_SAMTOOLS.format(python=sys.executable)),
            ("minimap2", STUB_MARK),
            ("bcftools", STUB_MARK),
        ):
            (stub / name).write_text(text)
            (stub / name).chmod(0o755)
        for name in ("python3", "python3.12"):
            (stub / name).symlink_to(sys.executable)
        inputs = root / "in"
        inputs.mkdir()
        for name in ("R1.fq", "R2.fq", "ref.fa", "ref.fa.fai", "ref.fa.mmi",
                     "lib.fa", "rm.out"):
            (inputs / name).write_text(name)
        self.library = inputs / "lib.fa"
        self.manifest = root / "manifest.json"
        check_cache.register(run_root=root / "runs", source_caller="src-caller",
                             source_rev=rev, libraries={"ds": self.library},
                             out=self.manifest)
        self.log = root / "stub.log"
        self.outdir = root / "out" / "s1"
        self.env = {
            "PATH": f"{stub}:/usr/bin:/bin",
            "HOME": str(root),
            "STUB_LOG": str(self.log),
            "DATASET": "ds", "SAMPLE": "s1",
            "R1": str(inputs / "R1.fq"), "R2": str(inputs / "R2.fq"),
            "REFERENCE": str(inputs / "ref.fa"), "TE_LIBRARY": str(self.library),
            "REPEATMASKER": str(inputs / "rm.out"), "TE_NAME": "mPing",
            "OUTDIR": str(self.outdir), "THREADS": "2", "RT3_REPO": str(self.repo),
            "RT3_TE_ALIGNER": "blat", "RT3_GENOME_ALIGNER": "bwaaln",
            "RT3_REPLAY_MANIFEST": str(self.manifest),
        }

    def tearDown(self):
        self._tmp.cleanup()

    def run_adapter(self, script="callers/relocate3-replay/run.sh"):
        return subprocess.run(["bash", script], cwd=REPO_ROOT, env=self.env,
                              capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()
                if line.startswith("[")]

    def snapshot(self):
        return sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size)
                      for p in self.cache_sample.rglob("*"))

    def test_replay_trims_cached_bams_and_reuses_genotype_bam(self):
        before = self.snapshot()
        result = self.run_adapter()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = [call[0] for call in self.calls()]
        self.assertNotIn("run", commands)
        self.assertEqual(commands[0], "trim")
        trim = self.calls()[0]
        raw = self.outdir / "raw"
        bam_args = trim[trim.index("--bam") + 1: trim.index("--bam") + 3]
        self.assertEqual(bam_args, [str(raw / "s1.left.bam"), str(raw / "s1.right.bam")])
        self.assertEqual(trim[trim.index("--fastq") + 1: trim.index("--fastq") + 3],
                         [self.env["R1"], self.env["R2"]])
        for side in ("left", "right"):
            link = raw / f"s1.{side}.bam"
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(),
                             (self.cache_sample / "raw" / f"s1.{side}.bam").resolve())
        characterize = next(c for c in self.calls() if c[0] == "characterize")
        self.assertEqual(
            Path(characterize[characterize.index("-b") + 1]).resolve(),
            (self.cache_sample / "raw" / "s1.original_reads.sorted.bam").resolve())
        self.assertNotIn("minimap2", self.log.read_text())
        self.assertTrue((self.outdir / ".run_complete").is_file())
        self.assertEqual(self.snapshot(), before)

    def test_stale_te_search_source_is_refused_before_any_output(self):
        (self.repo / "src/RelocaTE3/aligners.py").write_text("BLAT = 9\n")
        result = self.run_adapter()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("full tier", result.stderr)
        self.assertFalse(self.outdir.exists())

    def test_replay_wrapper_requires_manifest(self):
        del self.env["RT3_REPLAY_MANIFEST"]
        result = self.run_adapter()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.outdir.exists())

    def test_full_tier_without_manifest_still_runs_te_search(self):
        del self.env["RT3_REPLAY_MANIFEST"]
        result = self.run_adapter("callers/relocate3/run.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls()[0][0], "run")
        self.assertIn("minimap2", self.log.read_text())

    def test_replay_normalize_delegates_to_relocate3(self):
        wrapper = REPO_ROOT / "callers" / "relocate3-replay" / "normalize.py"
        result = subprocess.run([sys.executable, str(wrapper), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--te-name", result.stdout)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run to verify failure**

Run: `$PYB -m unittest discover -s tests -p 'test_relocate3_replay.py' -v`
Expected: replay tests FAIL (wrapper missing). `test_full_tier_without_manifest_still_runs_te_search`
should already PASS — it pins current full-tier behavior. If it fails, fix the stubs, not the adapter.

**Step 3: Implement**

`callers/relocate3-replay/run.sh`:

```bash
#!/usr/bin/bash -l
# Development-tier RelocaTE3 adapter: the standard adapter in replay mode.
# Reuses a registered full-tier run's TE-search BAMs and genotyping BAM and
# reruns trim, align-genome, find-insertions and characterize from RT3_REPO.
# See docs/plans/2026-10-19-dev-replay-tier-design.md.
set -euo pipefail
: "${RT3_REPLAY_MANIFEST:?replay caller needs replay_manifest in its config table}"
export ADAPTER_DIR="callers/relocate3"
exec bash callers/relocate3/run.sh
```

`callers/relocate3-replay/normalize.py`:

```python
#!/usr/bin/env python3
"""Normalize replay output with the standard RelocaTE3 normalizer (same layout)."""
import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "relocate3" / "normalize.py"),
    run_name="__main__",
)
```

`callers/relocate3/run.sh` — four edits:

(a) Contract comment: add `RT3_REPLAY_MANIFEST` to the "Defaults" list and a line
`#   RT3_REPLAY_MANIFEST set => replay mode (development tier; see callers/relocate3-replay)`.

(b) Insert immediately **before** section 2 (`# 2. Idempotency / run-dir safety.`),
so a refused replay creates no run directory:

```bash
# ---------------------------------------------------------------------------
# 1b. Replay mode (development tier). With RT3_REPLAY_MANIFEST set, reuse a
#     registered full-tier run's TE-search BAMs and all-read genotyping BAM
#     instead of rerunning BLAT and minimap2. The guard refuses when RT3_REPO's
#     TE-search source or the TE library no longer matches the cache.
# ---------------------------------------------------------------------------
REPLAY_RAW=""
if [[ -n "${RT3_REPLAY_MANIFEST:-}" && ! -f "$OUTDIR/.run_complete" ]]; then
  REPLAY_RAW="$(python3.12 callers/relocate3-replay/check_cache.py check \
    --manifest "$RT3_REPLAY_MANIFEST" \
    --rt3-repo "$RT3_REPO" \
    --dataset "${DATASET:?DATASET must be set in replay mode}" \
    --sample "$SAMPLE" \
    --te-library "$TE_LIBRARY")"
fi
```

(c) Immediately **after** `source "$ADAPTER_DIR/env.sh"` in section 4:

```bash
if [[ -n "$REPLAY_RAW" ]]; then
  # Test the tree in RT3_REPO itself, whichever RelocaTE3 the env installed.
  export PYTHONPATH="$RT3_REPO/src${PYTHONPATH:+:$PYTHONPATH}"
  python3 -c 'import os,pathlib,RelocaTE3; root=pathlib.Path(os.environ["RT3_REPO"]).resolve(); p=pathlib.Path(RelocaTE3.__file__).resolve(); print("Replay source:",p); assert p.is_relative_to(root/"src"), p'
fi
```

and add `echo "  replay      : ${REPLAY_RAW:-no (full TE search)}"` to the parameter echo block.

(d) Replace the `relocaTE3 run …` call (Steps 2+3) with:

```bash
if [[ -n "$REPLAY_RAW" ]]; then
  # Same write_trimmed_reads call `run` makes, on the cached TE-search BAMs.
  echo "[$(date)] replay: trim from cached TE-search BAMs in $REPLAY_RAW"
  for side in left right; do
    for ext in bam bam.bai; do
      ln -s "$(readlink -f "$REPLAY_RAW/${SAMPLE}.${side}.${ext}")" \
        "$RAW/${SAMPLE}.${side}.${ext}"
    done
  done
  relocaTE3 trim \
    --bam "$RAW/${SAMPLE}.left.bam" "$RAW/${SAMPLE}.right.bam" \
    --fastq "$R1" "$R2" \
    --name "$SAMPLE" \
    --outdir "$RAW" \
    --min-match "$RT3_MIN_MATCH" \
    --min-trimmed "$RT3_MIN_TRIMMED" \
    --mismatch "$RT3_MISMATCH"
else
  echo "[$(date)] run (map + trim)"
  relocaTE3 run \
    …existing arguments unchanged…
fi
```

and replace the genotyping-BAM block (`building full-reads-to-genome BAM` through
`samtools index`) with:

```bash
if [[ -n "$REPLAY_RAW" ]]; then
  # minimap2 of all reads involves no RelocaTE3 code; reuse it read-only.
  CHARACTERIZATION_BAM="$(readlink -f "$REPLAY_RAW/${SAMPLE}.original_reads.sorted.bam")"
  echo "[$(date)] replay: cached all-read BAM $CHARACTERIZATION_BAM"
else
  echo "[$(date)] building full-reads-to-genome BAM for characterize"
  …existing minimap2 | samtools sort; mv; samtools index unchanged…
fi
```

**Step 4: Verify**

Run: `$PYB -m unittest discover -s tests -p 'test_relocate3_replay.py' -v` → 5 OK.
Run: `bash -n callers/relocate3/run.sh callers/relocate3-replay/run.sh callers/frozen/run.sh`.
Run the whole suite → only the known pytest import error.

**Step 5: Commit**

```bash
git add callers/relocate3/run.sh callers/relocate3-replay tests/test_relocate3_replay.py
git commit -m "feat(replay): replay RelocaTE3 post-TE-search stages from cached BAMs"
```

---

### Task 5: `submit_benchmark.sh --rt3-repo`

**Files:**
- Modify: `pipeline/submit_benchmark.sh` (arg parse, help, validation)
- Test: `tests/test_submit_args.py`

**Step 1: Failing tests**

```python
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
```

**Step 2:** `$PYB -m unittest discover -s tests -p 'test_submit_args.py' -v` → FAIL (unknown argument).

**Step 3: Implement** — add `RT3_REPO_OVERRIDE=""` with the other defaults, the case
arm `--rt3-repo) RT3_REPO_OVERRIDE="$2"; shift 2 ;;`, a help line
`  --rt3-repo <path>    Run RelocaTE3 callers from this checkout (e.g. a worktree)`,
and right after the `if (( SHOW_HELP == 1 ))` block:

```bash
if [[ -n "$RT3_REPO_OVERRIDE" ]]; then
  if [[ ! -d "$RT3_REPO_OVERRIDE/src/RelocaTE3" || ! -f "$RT3_REPO_OVERRIDE/pixi.toml" ]]; then
    echo "ERROR: --rt3-repo must be a RelocaTE3 checkout (src/RelocaTE3 and pixi.toml): $RT3_REPO_OVERRIDE" >&2
    exit 1
  fi
  RT3_REPO_OVERRIDE="$(cd "$RT3_REPO_OVERRIDE" && pwd)"
  # --export=ALL carries this to the array; config_env.py applies it.
  export RT3_REPO_OVERRIDE
  echo "[$(date)] RelocaTE3 callers will use: $RT3_REPO_OVERRIDE"
fi
```

**Step 4:** same command → 3 OK; whole suite clean.

**Step 5: Commit**

```bash
git add pipeline/submit_benchmark.sh tests/test_submit_args.py
git commit -m "feat(submit): --rt3-repo runs RelocaTE3 callers from another checkout"
```

---

### Task 6: Dev config and committed replay manifest

**Files:**
- Create: `config/benchmark.dev.toml`
- Create: `config/replay/checkpoint-213a0df.json` (generated)
- Test: `tests/test_dev_config.py`

**Step 1: Failing test**

```python
"""The committed development-tier config and replay manifest."""
import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "config_env", REPO_ROOT / "pipeline" / "config_env.py")
config_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config_env)
CONFIG = REPO_ROOT / "config" / "benchmark.dev.toml"
MANIFEST = REPO_ROOT / "config" / "replay" / "checkpoint-213a0df.json"


class DevConfigTest(unittest.TestCase):
    def run_mode(self, *args):
        return config_env.run(["--config", str(CONFIG), *args])

    def test_only_frozen_r2_and_replay_r3_are_enabled(self):
        self.assertEqual(self.run_mode("callers").split(),
                         ["relocate2-frozen", "relocate3-replay"])

    def test_outputs_are_isolated_and_scored_like_the_checkpoint(self):
        globals_ = self.run_mode("globals")
        self.assertIn("WORK_ROOT='runs/dev'", globals_)
        self.assertIn("REPORT_ROOT='reports/dev'", globals_)
        self.assertIn("SCORING_COORDINATE_POLICY='tsd-interval'", globals_)

    def test_replay_matches_checkpoint_parity_settings(self):
        env = self.run_mode("caller-env", "relocate3-replay")
        for expected in ("RT3_GENOME_ALIGNER='bwaaln'", "TSD_PATTERN='UNK'",
                         "RT3_REQUIRE_BOTH_JUNCTIONS='1'",
                         "RT3_REPLAY_MANIFEST='config/replay/checkpoint-213a0df.json'"):
            self.assertIn(expected, env)

    def test_manifest_covers_every_dataset_from_the_checkpoint(self):
        data = json.loads(MANIFEST.read_text())
        self.assertEqual(data["source_caller"], "relocate3-blat-bwaaln")
        self.assertEqual(data["run_root"], "runs/checkpoint-213a0df")
        self.assertTrue(data["source_rev"].startswith("213a0df"))
        datasets = self.run_mode("--dataset", "full", "datasets")
        names = {line.split("\t")[0] for line in datasets.splitlines()}
        self.assertEqual(set(data["te_library_sha256"]), names)
```

**Step 2:** run → FAIL (files missing).

**Step 3: Implement**

`config/benchmark.dev.toml` — copy the three `[datasets.*]` tables **verbatim**
from `config/benchmark.checkpoint-213a0df.toml` (lines 9–36), then:

```toml
# Development tier: fast accuracy check for RelocaTE3 changes downstream of the
# TE search. RelocaTE3 replays trim -> characterize from the registered
# checkpoint's cached BLAT BAMs and genotyping BAMs; RelocaTE2 is re-scored from
# its frozen checkpoint calls. Accuracy only: resources.tsv here measures
# replays and file copies, not real runs. Release evidence comes from a full-tier
# run (config/benchmark.toml). Design: docs/plans/2026-10-19-dev-replay-tier-design.md.
#
#   CONFIG=config/benchmark.dev.toml bash pipeline/submit_benchmark.sh --dataset full
#   CONFIG=config/benchmark.dev.toml bash pipeline/submit_benchmark.sh \
#     --dataset full --coverage 5,15 --replicate 1 --rt3-repo ../../RelocaTE3_jason/<worktree>

[benchmark]
default_dataset = "mping"

# [datasets.mping], [datasets.ricetelib], [datasets.ricetelib_divergence]:
# identical to config/benchmark.checkpoint-213a0df.toml.

[run]
work_root   = "runs/dev"
report_root = "reports/dev"
truth_root  = "truth"
threads     = 8

[scoring]
match_window = 10
coordinate_policy = "tsd-interval"

[callers.relocate2-frozen]
enabled       = true
adapter       = "callers/frozen"
source_root   = "runs/checkpoint-213a0df"
source_caller = "relocate2"
label         = "RelocaTE2 (frozen checkpoint)"

[callers.relocate3-replay]
enabled         = true
adapter         = "callers/relocate3-replay"
adapter_type    = "relocate3"
repo            = "/rhome/nmath020/bigdata/github/github_tools/RelocaTE/RelocaTE3_jason/RelocaTE3"
tsd             = "UNK"
te_aligner      = "blat"      # must equal the manifest's te_aligner (guard-enforced)
genome_aligner  = "bwaaln"
require_both_junctions = 1
replay_manifest = "config/replay/checkpoint-213a0df.json"
label           = "RelocaTE3-blat/bwa-aln (replay)"
```

Generate the manifest from the **main checkout's** staged libraries (the worktree
has no `cache/`). Light work (hashing three ≤1.3 MB files):

```bash
MAIN=../relocate-benchmark
python3.12 callers/relocate3-replay/check_cache.py register \
  --run-root runs/checkpoint-213a0df \
  --source-caller relocate3-blat-bwaaln \
  --te-aligner blat \
  --source-rev 213a0df99af71a57fffad726138593b152fc9a77 \
  --te-library mping=$MAIN/cache/te_libraries/mping/library.fa \
  --te-library ricetelib=$MAIN/cache/te_libraries/ricetelib/library.fa \
  --te-library ricetelib_divergence=$MAIN/cache/te_libraries/ricetelib_divergence/library.fa \
  --out config/replay/checkpoint-213a0df.json
```

Cross-check that the checkpoint's TE-search BAMs were built from these same
libraries: their staging mtimes must predate the checkpoint array (Oct 13 2026):
`ls -l --time-style=full-iso $MAIN/cache/te_libraries/*/library.fa`. If any is newer,
stop and report — the manifest would bless a library the cache was not built with.

**Step 4:** run `test_dev_config` → 4 OK; whole suite clean.

**Step 5: Commit**

```bash
git add config/benchmark.dev.toml config/replay/checkpoint-213a0df.json tests/test_dev_config.py
git commit -m "feat(config): development-tier profile and checkpoint replay manifest"
```

---

### Task 7: Acceptance-gate comparison script

**Files:**
- Create: `scripts/compare_replay_gate.py`
- Test: `tests/test_compare_replay_gate.py`

**Step 1: Failing tests**

```python
"""Gate: dev-tier outputs must reproduce the checkpoint exactly."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "gate", REPO_ROOT / "scripts" / "compare_replay_gate.py")
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
```

**Step 2:** run → FAIL (script missing).

**Step 3: Implement** `scripts/compare_replay_gate.py`:

```python
#!/usr/bin/env python3
"""Acceptance gate: dev-tier results must reproduce the checkpoint exactly.

Compares each dev caller's normalized calls (multiset, caller column excluded)
and per-sample precision tables with its checkpoint counterpart. Writes a TSV
and exits 1 on any difference or missing sample. Run from the benchmark root:

  python3.12 scripts/compare_replay_gate.py --out reports/dev/replay_gate.tsv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

DEFAULT_PAIRS = {
    "relocate3-replay": "relocate3-blat-bwaaln",
    "relocate2-frozen": "relocate2",
}


def _rows(path: Path) -> Counter:
    with open(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return Counter(
            tuple((k, v) for k, v in sorted(row.items()) if k != "caller")
            for row in reader
        )


def _compare(dev_files: dict, source_files: dict, kind: str) -> list[dict]:
    results = []
    for key in sorted(source_files):
        dataset, dev_caller, sample = key
        row = {"kind": kind, "dataset": dataset, "caller": dev_caller,
               "sample": sample, "dev_only": 0, "source_only": 0}
        if key not in dev_files:
            row["status"] = "missing"
        else:
            dev, source = _rows(dev_files[key]), _rows(source_files[key])
            row["dev_only"] = sum((dev - source).values())
            row["source_only"] = sum((source - dev).values())
            row["status"] = "identical" if dev == source else "different"
        results.append(row)
    return results


def compare_calls(dev_root: Path, source_root: Path, pairs: dict) -> list[dict]:
    dev_files, source_files = {}, {}
    for dev_caller, source_caller in pairs.items():
        for path in Path(source_root).glob(f"*/{source_caller}/*/calls.normalized.tsv"):
            dataset, sample = path.parts[-4], path.parts[-2]
            source_files[(dataset, dev_caller, sample)] = path
            candidate = Path(dev_root) / dataset / dev_caller / sample / "calls.normalized.tsv"
            if candidate.is_file():
                dev_files[(dataset, dev_caller, sample)] = candidate
    return _compare(dev_files, source_files, "calls")


def compare_precision(dev_reports: Path, source_reports: Path, pairs: dict) -> list[dict]:
    dev_files, source_files = {}, {}
    for dev_caller, source_caller in pairs.items():
        pattern = f"datasets/*/per_sample/{source_caller}/*/precision.tsv"
        for path in Path(source_reports).glob(pattern):
            dataset, sample = path.parts[-5], path.parts[-2]
            source_files[(dataset, dev_caller, sample)] = path
            candidate = (Path(dev_reports) / "datasets" / dataset / "per_sample"
                         / dev_caller / sample / "precision.tsv")
            if candidate.is_file():
                dev_files[(dataset, dev_caller, sample)] = candidate
    return _compare(dev_files, source_files, "precision")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dev-runs", default="runs/dev", type=Path)
    ap.add_argument("--source-runs", default="runs/checkpoint-213a0df", type=Path)
    ap.add_argument("--dev-reports", default="reports/dev", type=Path)
    ap.add_argument("--source-reports", default="reports/checkpoint-213a0df", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    rows = compare_calls(args.dev_runs, args.source_runs, DEFAULT_PAIRS)
    rows += compare_precision(args.dev_reports, args.source_reports, DEFAULT_PAIRS)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["kind", "dataset", "caller", "sample", "status", "dev_only", "source_only"]
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    summary = Counter((r["kind"], r["caller"], r["status"]) for r in rows)
    for (kind, caller, status), n in sorted(summary.items()):
        print(f"{kind}\t{caller}\t{status}\t{n}")
    return 0 if all(r["status"] == "identical" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: the precision comparison for `relocate3-replay` vs `relocate3-blat-bwaaln`
also follows from identical calls; it is kept as an end-to-end scoring check.

**Step 4:** run → 4 OK; whole suite clean.

**Step 5: Commit**

```bash
git add scripts/compare_replay_gate.py tests/test_compare_replay_gate.py
git commit -m "feat(gate): compare dev-tier results with the checkpoint exactly"
```

---

### Task 8: Documentation

**Files:**
- Create: `docs/2026-10-19-dev-replay-tier.md` (dated note: purpose, status, commands,
  guard rules + blind spot, accuracy-only caveat, gate procedure, next steps)
- Modify: `README.md` — add a "Fast development tier" section after "Running a subset",
  with the two submit commands from the dev config header, the `--rt3-repo` flag, the
  "accuracy only" caveat, and "change TE search ⇒ use the full tier".
- Modify: `.gitignore` — confirm `runs/*` already covers `runs/dev/`; add
  `reports/dev/datasets/*/per_sample/`, `reports/dev/datasets/*/resources/`,
  `reports/dev/datasets/*/figures/`, `reports/dev/datasets/*/*.pdf`
  (mirror of the checkpoint rules).

**Step:** write, then `git add` and commit
`docs: development replay tier usage and caveats`.

---

### Task 9: Review, merge, acceptance gate (main checkout)

1. Whole suite green in the worktree; request code review
   (@superpowers:requesting-code-review); fix findings.
2. Push the branch and open a PR to `main` (maintainer merges).
3. After merge, in the **main checkout** (`relocate-benchmark/`, where `runs/`,
   `cache/` and the pixi envs live): `git pull`.
4. Submit the gate (maintainer runs it; 144 tasks — 72 frozen copies + 72 replays):
   ```bash
   CONFIG=config/benchmark.dev.toml bash pipeline/submit_benchmark.sh --dataset full
   ```
   RelocaTE3 must be at `main` `95c8d68` or any revision whose `aligners.py` and
   `ReadLibrary.py` equal `213a0df` (the guard enforces it).
5. After aggregation: `python3.12 scripts/compare_replay_gate.py --out reports/dev/replay_gate.tsv`
   → exit 0, every row `identical` (144 calls rows + 144 precision rows).
6. Record per-sample replay wall time from `reports/dev/datasets/*/resources.tsv`
   (relocate3-replay rows) in `docs/2026-10-19-dev-replay-tier.md`, then remove
   the worktree (`git worktree remove ../relocate-benchmark-dev-replay`).
