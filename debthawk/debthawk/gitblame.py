"""Optional git-blame enrichment for findings.

When a scan runs inside a git working tree, each finding can be annotated with
the author and the age (in days) of the line it sits on. This turns a flat list
of TODOs into something actionable: *who* introduced a marker and *how long* it
has been festering.
"""

from __future__ import annotations

import subprocess
import time
from functools import lru_cache
from pathlib import Path


def is_git_repo(root: Path) -> bool:
    """Return True if ``root`` is inside a git working tree."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root if root.is_dir() else root.parent,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


@lru_cache(maxsize=512)
def _blame_file(path: str) -> dict[int, tuple[str, int]]:
    """Blame an entire file once, returning ``{line: (author, author_time)}``.

    Results are cached per path so multiple findings in the same file incur a
    single ``git blame`` invocation. Returns an empty mapping on any failure.
    """
    p = Path(path)
    try:
        result = subprocess.run(
            ["git", "blame", "--porcelain", "--", p.name],
            cwd=p.parent,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    return _parse_porcelain(result.stdout)


def _parse_porcelain(output: str) -> dict[int, tuple[str, int]]:
    """Parse ``git blame --porcelain`` output into ``{line: (author, time)}``."""
    blame: dict[int, tuple[str, int]] = {}
    current_line = 0
    author = "unknown"
    author_time = 0
    for raw in output.splitlines():
        if not raw:
            continue
        parts = raw.split(" ")
        # A header line looks like: "<sha> <orig-line> <final-line> [<count>]"
        if len(parts) >= 3 and len(parts[0]) == 40 and _is_hex(parts[0]):
            try:
                current_line = int(parts[2])
            except ValueError:
                continue
        elif raw.startswith("author "):
            author = raw[len("author ") :].strip() or "unknown"
        elif raw.startswith("author-time "):
            try:
                author_time = int(raw[len("author-time ") :].strip())
            except ValueError:
                author_time = 0
        elif raw.startswith("\t"):
            # The actual source line; commit its accumulated metadata.
            if current_line:
                blame[current_line] = (author, author_time)
    return blame


def _is_hex(token: str) -> bool:
    try:
        int(token, 16)
        return True
    except ValueError:
        return False


def lookup(path: str, line: int, *, now: int | None = None) -> tuple[str | None, int | None]:
    """Return ``(author, age_days)`` for a line, or ``(None, None)`` if unknown."""
    blame = _blame_file(path)
    info = blame.get(line)
    if info is None:
        return (None, None)
    author, author_time = info
    if author_time <= 0:
        return (author, None)
    current = time.time() if now is None else now
    age_days = max(0, int((current - author_time) // 86400))
    return (author, age_days)


def clear_cache() -> None:
    """Clear the per-file blame cache (primarily for tests)."""
    _blame_file.cache_clear()
