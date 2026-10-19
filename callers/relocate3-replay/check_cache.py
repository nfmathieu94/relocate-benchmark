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
