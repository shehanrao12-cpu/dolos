"""debthawk — hunt down technical debt in your codebase.

A fast, zero-dependency CLI that scans a source tree for debt markers
(TODO, FIXME, HACK, ...), enriches them with git-blame author/age data,
scores severity, flags stale debt, and gates CI.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
