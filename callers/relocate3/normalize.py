#!/usr/bin/env python3
"""Normalize RelocaTE3 characterized output -> calls.normalized.tsv."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.calls import parse_characterized_txt, write_normalized


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", required=True, type=Path)   # the caller OUTDIR
    ap.add_argument("--sample", required=True)
    ap.add_argument("--te-name", default="mPing")
    ap.add_argument("--target", default="ALL")
    args = ap.parse_args(argv)

    txt = (
        args.outdir
        / "raw"
        / "results"
        / f"{args.target}.{args.te_name}.all_nonref_insert.characTErized.txt"
    )
    if not txt.is_file():
        raise FileNotFoundError(f"RelocaTE3 characterized TXT missing: {txt}")

    rows = list(parse_characterized_txt(txt, caller="relocate3", sample=args.sample))
    write_normalized(rows, args.outdir / "calls.normalized.tsv")
    print(f"relocate3 {args.sample}: {len(rows)} calls", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
