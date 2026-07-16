#!/usr/bin/env python3.12
"""Config-to-shell bridge for the relocate-benchmark pipeline.

Reads config/benchmark.toml (via lib.config.load_config) and emits
shell-consumable output for the SLURM runner. All emitted assignments are
single-quoted and safe to `eval`.

Subcommands:
  globals              Print global env assignments (REFERENCE, THREADS, ...).
  callers              Print each ENABLED caller name, one per line, sorted.
  caller-env <name>    Print a caller's extra env assignments (RT3_*/RT2_*).
  tasks                Print one tab-separated task line per (caller x sample).
  count                Print the integer number of tasks.

Requires python3.12 (tomllib via lib.config).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Make the repo root importable so `from lib.config import load_config` works
# regardless of the current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.config import load_config

# Map each caller's known config keys to their contract env-var names. Unknown
# callers (not present here) yield no caller-specific env.
CALLER_ENV_MAP: dict[str, dict[str, str]] = {
    "relocate3": {"repo": "RT3_REPO", "tsd": "TSD_PATTERN"},
    "relocate2": {
        "aligner": "RT2_ALIGNER",
        "size": "RT2_SIZE",
        "mismatch": "RT2_MISMATCH",
    },
}


def _sq(value) -> str:
    """Single-quote a value for safe shell `eval`."""
    return "'" + str(value).replace("'", "'\\''") + "'"


def _enabled_callers(cfg: dict) -> list[str]:
    callers = cfg.get("callers", {})
    return sorted(
        name for name, tbl in callers.items() if tbl.get("enabled") is True
    )


def _manifest_rows(panel_root: Path) -> list[dict]:
    manifest = panel_root / "panel_manifest.tsv"
    if not manifest.is_file():
        raise FileNotFoundError(f"panel manifest missing: {manifest}")
    with open(manifest, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _globals(cfg: dict) -> str:
    ds = cfg["dataset"]
    lines = [
        f"REFERENCE={_sq(ds['reference'])}",
        f"TE_LIBRARY={_sq(ds['te_library'])}",
        f"REPEATMASKER={_sq(ds['repeatmasker'])}",
        f"TE_NAME={_sq(ds['te_name'])}",
        f"PANEL_ROOT={_sq(ds['panel_root'])}",
        f"WORK_ROOT={_sq(cfg['run']['work_root'])}",
        f"THREADS={_sq(cfg['run']['threads'])}",
        f"MATCH_WINDOW={_sq(cfg['scoring']['match_window'])}",
    ]
    return "\n".join(lines) + "\n"


def _callers(cfg: dict) -> str:
    names = _enabled_callers(cfg)
    return "".join(f"{n}\n" for n in names)


def _caller_env(cfg: dict, name: str) -> str:
    mapping = CALLER_ENV_MAP.get(name)
    tbl = cfg.get("callers", {}).get(name, {})
    if not mapping or not tbl:
        return ""
    lines = [
        f"{env}={_sq(tbl[key])}"
        for key, env in mapping.items()
        if key in tbl
    ]
    return ("\n".join(lines) + "\n") if lines else ""


def _tasks(cfg: dict) -> str:
    panel_root = Path(cfg["dataset"]["panel_root"])
    rows = _manifest_rows(panel_root)
    out = []
    # Deterministic: outer loop = enabled callers sorted, inner = manifest order.
    for caller in _enabled_callers(cfg):
        for row in rows:
            r1 = panel_root / row["r1"]
            r2 = panel_root / row["r2"]
            out.append(
                "\t".join(
                    [
                        caller,
                        row["sample"],
                        row["coverage"],
                        row["replicate"],
                        str(r1),
                        str(r2),
                    ]
                )
            )
    return "".join(line + "\n" for line in out)


def _count(cfg: dict) -> str:
    panel_root = Path(cfg["dataset"]["panel_root"])
    n = len(_enabled_callers(cfg)) * len(_manifest_rows(panel_root))
    return f"{n}\n"


def run(argv=None) -> str:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/benchmark.toml", type=Path)
    ap.add_argument(
        "mode",
        choices=["globals", "callers", "caller-env", "tasks", "count"],
    )
    ap.add_argument("name", nargs="?", help="caller name (for caller-env)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)

    if args.mode == "globals":
        return _globals(cfg)
    if args.mode == "callers":
        return _callers(cfg)
    if args.mode == "caller-env":
        if not args.name:
            ap.error("caller-env requires a caller name")
        return _caller_env(cfg, args.name)
    if args.mode == "tasks":
        return _tasks(cfg)
    if args.mode == "count":
        return _count(cfg)
    ap.error(f"unknown mode: {args.mode}")  # unreachable (choices-guarded)


def main(argv=None) -> int:
    sys.stdout.write(run(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
