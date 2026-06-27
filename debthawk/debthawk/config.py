"""Configuration loading and merging.

Configuration is resolved with the following precedence (highest first):

1. Command-line arguments
2. ``[tool.debthawk]`` table in ``pyproject.toml``
3. ``debthawk.toml`` in the scan root
4. Built-in defaults
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .tags import DEFAULT_STALE_DAYS, DEFAULT_STALE_MULTIPLIER, DEFAULT_TAGS


@dataclass
class Config:
    """Fully-resolved configuration for a run."""

    tags: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_TAGS))
    ignore_globs: list[str] = field(default_factory=list)
    stale_days: int = DEFAULT_STALE_DAYS
    stale_multiplier: float = DEFAULT_STALE_MULTIPLIER
    case_sensitive: bool = True
    blame: bool = True


def _load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _table_from_pyproject(data: dict) -> dict:
    return data.get("tool", {}).get("debthawk", {}) if isinstance(data, dict) else {}


def discover(root: Path) -> dict:
    """Find and merge the file-based config table for ``root``.

    ``debthawk.toml`` takes precedence over ``[tool.debthawk]`` in pyproject.
    """
    base = root if root.is_dir() else root.parent
    merged: dict = {}
    pyproject = base / "pyproject.toml"
    if pyproject.is_file():
        merged.update(_table_from_pyproject(_load_toml(pyproject)))
    standalone = base / "debthawk.toml"
    if standalone.is_file():
        merged.update(_load_toml(standalone))
    return merged


def from_table(table: dict) -> Config:
    """Build a :class:`Config` from a parsed config table, filling in defaults."""
    cfg = Config()
    if not isinstance(table, dict):
        return cfg

    tags = table.get("tags")
    if isinstance(tags, dict):
        cfg.tags = {str(k): int(v) for k, v in tags.items()}
    elif isinstance(tags, list):
        # A bare list of tag names uses default weights (or 1 if unknown).
        cfg.tags = {str(t): DEFAULT_TAGS.get(str(t), 1) for t in tags}

    if isinstance(table.get("ignore"), list):
        cfg.ignore_globs = [str(g) for g in table["ignore"]]
    if isinstance(table.get("stale_days"), int):
        cfg.stale_days = table["stale_days"]
    if isinstance(table.get("stale_multiplier"), (int, float)):
        cfg.stale_multiplier = float(table["stale_multiplier"])
    if isinstance(table.get("case_sensitive"), bool):
        cfg.case_sensitive = table["case_sensitive"]
    if isinstance(table.get("blame"), bool):
        cfg.blame = table["blame"]
    return cfg


def load(root: Path) -> Config:
    """Discover and build configuration for ``root``."""
    return from_table(discover(root))
