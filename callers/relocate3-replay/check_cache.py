#!/usr/bin/env python3
"""Register and guard the RelocaTE3 replay cache for the development tier.

``register`` records a completed full-tier run whose TE-search BAMs
(``<sample>.left/right.bam``) and all-read genotyping BAM
(``<sample>.original_reads.sorted.bam``) may be replayed.

``check`` verifies that one sample may be replayed against the RelocaTE3 tree
under test and prints that sample's cached ``raw/`` directory. It refuses when
the TE-search source, the TE library or the TE aligner no longer matches the
cache, or when an input file changed after the cache was built, because the
replay would then silently score stale TE-search output.

Input freshness (``--input``) is an mtime check, not a content check: an input
whose modification time is newer than the source sample's ``.run_complete`` is
refused. A file rewritten with identical content is refused too; a file changed
while preserving an old mtime (``cp -p``, ``touch -d``) is not detected.

``identity`` prints ``<HEAD sha> <sha256>`` for a RelocaTE3 tree, where the
digest covers ``git diff HEAD`` under ``src/`` plus every untracked file there
(path and content; ``__pycache__`` and ``*.pyc`` are ignored). The RelocaTE3
adapter records it in ``replay_source.txt`` so a completed dev-tier result is
never silently reused for a different tree.

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
import re
import subprocess
import sys
from pathlib import Path

# Source that produced the cached TE-search BAMs: BLAT invocation and
# parameters, query chunking, PSL->SAM conversion, and read-file naming.
GUARDED_FILES = ("src/RelocaTE3/aligners.py", "src/RelocaTE3/ReadLibrary.py")
_FULL_SHA = re.compile(r"[0-9a-f]{40}")


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


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def check_source(repo: Path, rev: str) -> None:
    """Fail unless the guarded files in ``repo``'s working tree equal ``rev``.

    ``repo`` may be any directory inside the RelocaTE3 checkout; guarded paths
    are anchored at the top level so a subdirectory cannot silently match nothing.
    """
    top = _git(repo, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise CacheError(f"not a git work tree: {repo}: {top.stderr.strip()}")
    toplevel = Path(top.stdout.strip())
    for path in GUARDED_FILES:
        if _git(repo, "cat-file", "-e", f"{rev}:{path}").returncode != 0:
            raise CacheError(f"guarded file {path} not found at cache revision {rev}")
        if not (toplevel / path).is_file():
            raise CacheError(f"guarded file {path} missing from working tree {toplevel}")
    pathspecs = [f":(top){path}" for path in GUARDED_FILES]
    result = _git(repo, "diff", "--quiet", rev, "--", *pathspecs)
    if result.returncode == 1:
        changed = _git(repo, "diff", "--name-only", rev, "--", *pathspecs).stdout.split()
        raise CacheError(
            f"TE-search source differs from cache revision {rev}: "
            f"{', '.join(changed)}; the cached BAMs are stale, run the full tier"
        )
    if result.returncode != 0:
        raise CacheError(f"cannot compare {repo} with {rev}: {result.stderr.strip()}")


def _is_bytecode(path: str) -> bool:
    return "__pycache__" in path.split("/") or path.endswith((".pyc", ".pyo"))


def tree_identity(repo) -> str:
    """Return ``"<HEAD sha> <sha256>"`` identifying ``repo``'s ``src/`` tree.

    The digest covers uncommitted changes to tracked files (``git diff HEAD``)
    and the path and content of each untracked, non-ignored file under ``src/``.
    Bytecode caches are skipped so importing the package does not change it.
    """
    top = _git(Path(repo), "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise CacheError(f"not a git work tree: {repo}: {top.stderr.strip()}")
    toplevel = Path(top.stdout.strip())

    def git_bytes(*args: str) -> bytes:
        result = subprocess.run(["git", "-C", str(toplevel), *args], capture_output=True)
        if result.returncode != 0:
            raise CacheError(f"git {args[0]} failed in {toplevel}: "
                             f"{result.stderr.decode(errors='replace').strip()}")
        return result.stdout

    head = git_bytes("rev-parse", "HEAD").decode().strip()
    digest = hashlib.sha256()
    digest.update(git_bytes("diff", "--no-ext-diff", "--no-textconv", "--binary",
                            "HEAD", "--", ":(top)src"))
    untracked = git_bytes("ls-files", "--others", "--exclude-standard", "-z",
                          "--", ":(top)src").decode().split("\0")
    for path in sorted(p for p in untracked if p and not _is_bytecode(p)):
        digest.update(b"\0untracked\0" + path.encode() + b"\0")
        digest.update((toplevel / path).read_bytes())
    return f"{head} {digest.hexdigest()}"


def register(run_root, source_caller, source_rev, libraries, out, te_aligner) -> dict:
    out = Path(out)
    if out.exists():
        raise CacheError(f"refusing to overwrite existing manifest: {out}")
    if not _FULL_SHA.fullmatch(source_rev):
        raise CacheError(
            f"source_rev must be a full 40-hex commit SHA, not {source_rev!r}; "
            "a branch, tag or short SHA could later resolve to another commit"
        )
    manifest = {
        "source_rev": source_rev,
        "run_root": str(run_root),
        "source_caller": source_caller,
        "te_aligner": te_aligner,
        "guarded_files": list(GUARDED_FILES),
        "te_library_sha256": {
            dataset: sha256(path) for dataset, path in sorted(libraries.items())
        },
        "registered": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def check(manifest, repo, dataset, sample, te_library, te_aligner, inputs=()) -> Path:
    data = json.loads(Path(manifest).read_text())
    if "te_aligner" not in data:
        raise CacheError(f"manifest {manifest} records no te_aligner; re-register it")
    if te_aligner != data["te_aligner"]:
        raise CacheError(
            f"replay caller TE aligner {te_aligner} does not match cache TE aligner "
            f"{data['te_aligner']}; run the full tier"
        )
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
    built = (sample_dir / ".run_complete").stat().st_mtime_ns
    for path in inputs:
        if not Path(path).is_file():
            raise CacheError(f"input missing: {path}")
        if Path(path).stat().st_mtime_ns > built:
            raise CacheError(
                f"input {path} changed after the cache was built "
                f"({sample_dir / '.run_complete'}); run the full tier"
            )
    raw = sample_dir / "raw"
    missing = [str(path) for path in cached_files(raw, sample) if not path.is_file()]
    if missing:
        raise CacheError("cached file(s) missing: " + ", ".join(missing))
    empty = [str(path) for path in cached_files(raw, sample) if path.stat().st_size == 0]
    if empty:
        raise CacheError("cached file(s) empty: " + ", ".join(empty))
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
    reg.add_argument("--te-aligner", required=True,
                     help="TE aligner the cached TE-search BAMs were built with")
    reg.add_argument("--out", required=True)
    chk = sub.add_parser("check", help="verify one sample; print its cached raw/ dir")
    chk.add_argument("--manifest", required=True)
    chk.add_argument("--rt3-repo", required=True)
    chk.add_argument("--dataset", required=True)
    chk.add_argument("--sample", required=True)
    chk.add_argument("--te-library", required=True)
    chk.add_argument("--te-aligner", required=True,
                     help="TE aligner the replay caller is configured with")
    chk.add_argument("--input", action="append", default=[], metavar="FILE",
                     help="input that must predate the cache (mtime check; repeatable)")
    ident = sub.add_parser("identity", help="print '<HEAD sha> <sha256>' of RT3 src/")
    ident.add_argument("--rt3-repo", required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "register":
            register(args.run_root, args.source_caller, args.source_rev,
                     dict(args.te_library), args.out, args.te_aligner)
            print(f"registered replay cache: {args.out}", file=sys.stderr)
        elif args.mode == "identity":
            print(tree_identity(args.rt3_repo))
        else:
            print(check(args.manifest, args.rt3_repo, args.dataset, args.sample,
                        args.te_library, args.te_aligner, args.input))
    except (CacheError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: replay cache: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
