#!/usr/bin/env python3.12
"""Convert a RepeatMasker GFF3 export to the legacy ``.out`` column contract.

The benchmark's RelocaTE2 adapter requires RepeatMasker ``.out`` token
positions, while RelocaTE3 accepts the same format. Coordinates remain 1-based
inclusive. Output is deterministic and written atomically.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import unquote


def _attributes(value: str) -> dict[str, str]:
    result = {}
    for item in value.rstrip(";").split(";"):
        if "=" in item:
            key, val = item.split("=", 1)
            result[key] = unquote(val)
    return result


def _target(value: str) -> tuple[str, int, int]:
    fields = value.rsplit(" ", 2)
    if len(fields) != 3:
        raise ValueError(f"invalid GFF Target attribute: {value!r}")
    return fields[0], int(fields[1]), int(fields[2])


def convert(source: Path, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    count = 0
    try:
        with source.open() as src, temporary.open("w") as out:
            out.write(
                "   SW  perc perc perc  query       position in query    "
                "matching repeat         position in repeat\n"
            )
            out.write(
                "score  div. del. ins.  sequence    begin end (left)  "
                "strand repeat class/family begin end (left) ID\n"
            )
            for line_number, line in enumerate(src, 1):
                if not line.strip() or line.startswith("#"):
                    continue
                columns = line.rstrip("\n").split("\t")
                if len(columns) != 9:
                    raise ValueError(
                        f"{source}:{line_number}: expected 9 GFF columns"
                    )
                chrom, _, _, start, end, score, strand, _, raw_attrs = columns
                attrs = _attributes(raw_attrs)
                repeat, repeat_start, repeat_end = _target(attrs["Target"])
                rm_strand = "+" if strand == "+" else "C"
                # RelocaTE only consumes query, boundaries, strand, and repeat
                # identity. Zero placeholders preserve the standard 15-column
                # layout required by the legacy parser.
                fields = (
                    score if score != "." else "0",
                    attrs.get("PercDiv", "0"),
                    attrs.get("PercDel", "0"),
                    attrs.get("PercIns", "0"),
                    chrom,
                    start,
                    end,
                    "(0)",
                    rm_strand,
                    repeat,
                    attrs.get("Class", "Unknown"),
                    str(repeat_start),
                    str(repeat_end),
                    "(0)",
                    attrs.get("ID", str(count + 1)),
                )
                out.write(" ".join(fields) + "\n")
                count += 1
        if count == 0:
            raise ValueError(f"no RepeatMasker records found in {source}")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output (default: verify and reuse it)",
    )
    args = parser.parse_args(argv)
    if not args.input.is_file():
        parser.error(f"input does not exist: {args.input}")
    if args.output.exists() and not args.force:
        if args.output.stat().st_size == 0:
            parser.error(f"existing output is empty: {args.output}")
        print(f"reusing existing annotation: {args.output}")
        return 0
    count = convert(args.input, args.output)
    print(f"wrote {count} RepeatMasker records: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
