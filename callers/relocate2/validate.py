#!/usr/bin/env python3
"""Reject incomplete R2 chromosome workers, while allowing genuine zero calls."""

import argparse
from pathlib import Path
import shlex


def commands(raw, step):
    paths = sorted((raw / "shellscripts" / f"step_{step}").glob("*.sh"))
    if not paths:
        raise ValueError(f"No step {step} worker scripts: {raw}")
    result = []
    program = (
        "relocaTE_insertionFinder.py" if step == 5 else "relocaTE_absenceFinder.py"
    )
    for path in paths:
        args = shlex.split(path.read_text())
        if len(args) < 6 or Path(args[1]).name != program:
            raise ValueError(f"Unexpected worker command: {path}")
        result.append((path, args))
    targets = [(args[3], args[5]) for _, args in result]
    if len(targets) != len(set(targets)):
        raise ValueError("Duplicate chromosome worker")
    return result


def validate(outdir, final=True):
    raw = Path(outdir) / "raw"
    results = raw / "repeat/results"
    for step, kind in ((5, "nonref"), (6, "ref")):
        for _, args in commands(raw, step):
            for suffix in ("txt", "gff"):
                path = results / f"{args[3]}.{args[5]}.all_{kind}_insert.{suffix}"
                if not path.is_file():
                    raise ValueError(f"Missing chromosome output: {path}")
    if final:
        path = results / "ALL.all_nonref_insert.characTErized.txt"
        if not path.is_file() or not path.read_text().startswith("strain\tTE\tTSD\t"):
            raise ValueError(f"Missing/malformed characterized table: {path}")
    log = Path(outdir) / "relocate2.driver.log"
    if log.exists():
        with log.open(errors="replace") as handle:
            for line in handle:
                if "Traceback (most recent call last)" in line:
                    raise ValueError(f"Internal R2 worker exception: {log}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", required=True, type=Path)
    opts = parser.parse_args()
    validate(opts.outdir)
    print(f"Validated R2 chromosome outputs: {opts.outdir}")
