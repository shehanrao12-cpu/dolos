"""Default tag definitions and severity weights.

A *tag* is a marker that developers leave in source comments to signal
outstanding work or risk, e.g. ``TODO`` or ``FIXME``. Each tag carries a
severity *weight* used to rank findings and compute an aggregate debt score.
"""

from __future__ import annotations

# Default tags and their relative severity weights. Higher == more urgent.
# These mirror the conventions used across the vast majority of codebases.
DEFAULT_TAGS: dict[str, int] = {
    "FIXME": 5,
    "BUG": 5,
    "XXX": 4,
    "HACK": 3,
    "TODO": 2,
    "OPTIMIZE": 2,
    "DEPRECATED": 3,
    "REFACTOR": 2,
    "NOTE": 1,
    "REVIEW": 1,
}

# Multiplier applied to a finding's weight once it is considered "stale"
# (older than the configured staleness threshold). Stale debt tends to be the
# debt that never gets paid down, so it is surfaced more aggressively.
DEFAULT_STALE_MULTIPLIER: float = 2.0

# A finding is "stale" once it is older than this many days (based on git blame
# author time). Only applied when running inside a git repository.
DEFAULT_STALE_DAYS: int = 180
