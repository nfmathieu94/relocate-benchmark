"""Runtime configuration for the dashboard entry points."""
from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

REPORT_DIR_ENV = "RELOCATE_REPORT_DIR"


def report_dir_from_args(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return CLI report dir, then environment dir, then ``reports``.

    ``parse_known_args`` is intentional: Streamlit adds its own process
    arguments before the application arguments following ``--``.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--report-dir", type=Path)
    args, _unknown = parser.parse_known_args(argv)
    if args.report_dir is not None:
        return args.report_dir
    env = os.environ if environ is None else environ
    return Path(env.get(REPORT_DIR_ENV, "reports"))

