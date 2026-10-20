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
