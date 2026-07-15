"""Parse the caller-shared characterized insertion TXT into the common schema.

RelocaTE2 and RelocaTE3 both write an identical 8-column table:
    strain  TE  TSD  chrom:start..end  strand  avg_flankers  spanners  status
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterator

NORMALIZED_HEADER = ["chrom", "position", "te_family", "tsd", "strand", "status", "caller", "sample"]
_COORD = re.compile(r"^([^:]+):(\d+)\.\.(\d+)$")


def parse_characterized_txt(path: str | Path, caller: str, sample: str) -> Iterator[dict]:
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            f = line.split("\t")
            if len(f) < 8:
                continue
            # Skip only the true header row (first field "strain" AND the coord
            # column is a header label, never a real "chrom:start..end" token).
            # This keeps samples literally named "strain..." from being dropped.
            if f[0].lower() == "strain" and not _COORD.match(f[3]):
                continue
            _strain, te, tsd, chrom_pos, strand, _flank, _span, status = f[:8]
            m = _COORD.match(chrom_pos)
            if not m:
                continue
            yield {
                "chrom": m.group(1),
                "position": int(m.group(2)),
                "te_family": te,
                "tsd": tsd,
                "strand": strand,
                "status": status,
                "caller": caller,
                "sample": sample,
            }


def write_normalized(rows: list[dict], out_path: str | Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=NORMALIZED_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
