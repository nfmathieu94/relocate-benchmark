#!/usr/bin/env python3
"""Fail before expensive benchmark work if code/config differs from the pin."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    manifest = json.loads(Path(sys.argv[1]).read_text())
    repo = Path(manifest["repo"])
    actual = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != manifest["revision"]:
        raise RuntimeError(f"Expected RelocaTE3 {manifest['revision']}, found {actual}")
    for base, files in (
        (repo, manifest["source_sha256"]),
        (Path.cwd(), manifest["benchmark_sha256"]),
    ):
        for path, digest in files.items():
            if hashlib.sha256((base / path).read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Pinned file changed: {base / path}")
    print(f"Verified pinned RelocaTE3 source and benchmark settings: {actual}")


if __name__ == "__main__":
    main()
