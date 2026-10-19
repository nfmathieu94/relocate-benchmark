#!/usr/bin/env python3
"""Normalize replay output with the standard RelocaTE3 normalizer (same layout)."""
import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "relocate3" / "normalize.py"),
    run_name="__main__",
)
