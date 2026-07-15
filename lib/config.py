"""Load a TOML config and expand ${section.key} string references."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REF = re.compile(r"\$\{([^}]+)\}")


def _lookup(cfg: dict, dotted: str) -> str:
    node = cfg
    for part in dotted.split("."):
        node = node[part]
    return str(node)


def _expand(value: str, cfg: dict) -> str:
    prev = None
    while prev != value:
        prev = value
        value = _REF.sub(lambda m: _lookup(cfg, m.group(1).strip()), value)
    return value


def _walk(node, cfg):
    if isinstance(node, dict):
        return {k: _walk(v, cfg) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk(v, cfg) for v in node]
    if isinstance(node, str):
        return _expand(node, cfg)
    return node


def load_config(path: str | Path) -> dict:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    return _walk(raw, raw)
