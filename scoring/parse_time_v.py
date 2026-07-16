#!/usr/bin/env python3
"""Convert GNU ``time -v`` output into one stable benchmark resource record.

Parses a ``/usr/bin/time -v`` capture file and writes a single-row TSV with the
resource metrics keyed by ``caller``/``sample``/``coverage``/``replicate``.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


PATTERNS = {
    "wall_seconds": r"Elapsed \(wall clock\) time .*?: (.+)",
    "max_rss_kb": r"Maximum resident set size \(kbytes\): (.+)",
    "user_seconds": r"User time \(seconds\): (.+)",
    "system_seconds": r"System time \(seconds\): (.+)",
    "percent_cpu": r"Percent of CPU this job got: (.+)",
}


def _wall_to_seconds(raw: str) -> str:
    """Convert an Elapsed wall-clock value (``h:mm:ss`` or ``m:ss(.ss)``) to seconds."""
    raw = raw.strip()
    parts = raw.split(":")
    try:
        seconds = 0.0
        for part in parts:
            seconds = seconds * 60.0 + float(part)
    except ValueError:
        return "NA"
    # Preserve fractional precision without trailing float noise.
    return ("%.2f" % seconds).rstrip("0").rstrip(".")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--time-v", required=True, type=Path)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--caller", required=True)
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--replicate", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.time_v.is_file():
        raise FileNotFoundError(f"Missing time -v file: {args.time_v}")
    text = args.time_v.read_text()

    record = {
        "caller": args.caller,
        "sample": args.sample,
        "coverage": args.coverage,
        "replicate": args.replicate,
    }
    for key, pattern in PATTERNS.items():
        match = re.search(pattern, text)
        value = match.group(1).strip() if match else "NA"
        if key == "wall_seconds" and match:
            value = _wall_to_seconds(value)
        record[key] = value

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(record.keys()), delimiter="\t")
        writer.writeheader()
        writer.writerow(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
