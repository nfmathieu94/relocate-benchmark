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
  indices              Print 0-based canonical task indices matching filters.

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


def _task_records(cfg: dict) -> list[dict]:
    """Return canonical task records (STABLE order: callers sorted x manifest).

    Each record has keys: caller, sample, coverage, replicate, r1, r2.
    This is the single source of truth for `tasks`, `count`, and `indices`.
    """
    panel_root = Path(cfg["dataset"]["panel_root"])
    rows = _manifest_rows(panel_root)
    records = []
    # Deterministic: outer loop = enabled callers sorted, inner = manifest order.
    for caller in _enabled_callers(cfg):
        for row in rows:
            records.append(
                {
                    "caller": caller,
                    "sample": row["sample"],
                    "coverage": row["coverage"],
                    "replicate": row["replicate"],
                    "r1": str(panel_root / row["r1"]),
                    "r2": str(panel_root / row["r2"]),
                }
            )
    return records


def _tasks(cfg: dict) -> str:
    out = [
        "\t".join(
            [
                rec["caller"],
                rec["sample"],
                rec["coverage"],
                rec["replicate"],
                rec["r1"],
                rec["r2"],
            ]
        )
        for rec in _task_records(cfg)
    ]
    return "".join(line + "\n" for line in out)


def _parse_filter(value) -> set[str] | None:
    """Split a comma-separated filter value into a set; None = no constraint."""
    if value is None:
        return None
    return {item for item in value.split(",")}


def _indices(cfg: dict, filters: dict) -> str:
    """Print comma-separated 0-based task indices matching ALL given filters.

    filters maps record-key -> comma-separated string (or None). An index is
    included iff, for every provided filter, the task's value is in the filter's
    comma list. With no filters, all indices are returned.
    """
    wanted = {key: _parse_filter(val) for key, val in filters.items()}
    matched = []
    for idx, rec in enumerate(_task_records(cfg)):
        if all(
            allowed is None or rec[key] in allowed
            for key, allowed in wanted.items()
        ):
            matched.append(idx)
    return ",".join(str(i) for i in matched) + "\n"


def _count(cfg: dict) -> str:
    return f"{len(_task_records(cfg))}\n"


def run(argv=None) -> str:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/benchmark.toml", type=Path)
    ap.add_argument(
        "mode",
        choices=["globals", "callers", "caller-env", "tasks", "count", "indices"],
    )
    ap.add_argument("name", nargs="?", help="caller name (for caller-env)")
    # Filters for `indices` (each a comma-separated list; omitted = no constraint).
    ap.add_argument("--caller", help="filter indices by caller (indices mode)")
    ap.add_argument("--coverage", help="filter indices by coverage (indices mode)")
    ap.add_argument("--replicate", help="filter indices by replicate (indices mode)")
    ap.add_argument("--sample", help="filter indices by sample (indices mode)")
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
    if args.mode == "indices":
        return _indices(
            cfg,
            {
                "caller": args.caller,
                "coverage": args.coverage,
                "replicate": args.replicate,
                "sample": args.sample,
            },
        )
    ap.error(f"unknown mode: {args.mode}")  # unreachable (choices-guarded)


def main(argv=None) -> int:
    sys.stdout.write(run(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
