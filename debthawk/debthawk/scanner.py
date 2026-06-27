"""Source-tree scanning and tag detection."""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

# Directories that are virtually never worth scanning. Used in addition to any
# user-supplied ignore patterns.
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "target",
        "dist",
        "build",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        "vendor",
        ".next",
        ".cache",
    }
)

# Files larger than this are skipped outright (likely generated/minified/binary).
DEFAULT_MAX_FILE_BYTES: int = 2 * 1024 * 1024  # 2 MiB

# Number of bytes sampled from the head of a file to decide if it is binary.
_BINARY_SNIFF_BYTES: int = 4096


@dataclass(frozen=True)
class Finding:
    """A single detected debt marker."""

    tag: str
    message: str
    path: str
    line: int
    raw: str
    weight: int = 0
    author: str | None = None
    age_days: int | None = None
    stale: bool = False
    score: float = 0.0

    def with_score(self, score: float, *, stale: bool) -> "Finding":
        """Return a copy with severity scoring applied."""
        return Finding(
            tag=self.tag,
            message=self.message,
            path=self.path,
            line=self.line,
            raw=self.raw,
            weight=self.weight,
            author=self.author,
            age_days=self.age_days,
            stale=stale,
            score=score,
        )


@dataclass
class ScanConfig:
    """Knobs controlling a scan."""

    tags: dict[str, int]
    ignore_globs: list[str] = field(default_factory=list)
    ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    case_sensitive: bool = True


def _build_pattern(tags: Iterable[str], case_sensitive: bool) -> re.Pattern[str]:
    """Compile a regex that matches any of ``tags`` as a standalone word.

    The trailing message and an optional ``(owner)`` annotation are captured,
    e.g. ``TODO(alice): wire this up`` -> tag ``TODO``, message ``wire this up``.
    """
    alternation = "|".join(re.escape(t) for t in sorted(tags, key=len, reverse=True))
    # word-boundary tag, optional (owner), optional separators, then message
    pattern = rf"\b({alternation})\b\s*(?:\(([^)]*)\))?\s*[:\-]?\s*(.*)"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def _is_binary(path: Path) -> bool:
    """Heuristically decide whether a file is binary by sniffing for NUL bytes."""
    try:
        with path.open("rb") as fh:
            chunk = fh.read(_BINARY_SNIFF_BYTES)
    except OSError:
        return True
    return b"\x00" in chunk


def _is_ignored(rel_path: str, ignore_globs: Iterable[str]) -> bool:
    """Return True if ``rel_path`` matches any user ignore glob."""
    return any(fnmatch.fnmatch(rel_path, g) for g in ignore_globs)


def iter_files(root: Path, config: ScanConfig) -> Iterator[Path]:
    """Yield candidate files under ``root`` honoring ignore rules."""
    root = root.resolve()
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in place so os.walk does not descend.
        dirnames[:] = [d for d in dirnames if d not in config.ignore_dirs]
        for name in filenames:
            full = Path(dirpath) / name
            rel = os.path.relpath(full, root)
            if _is_ignored(rel, config.ignore_globs):
                continue
            try:
                if full.stat().st_size > config.max_file_bytes:
                    continue
            except OSError:
                continue
            yield full


def scan_file(path: Path, pattern: re.Pattern[str], tags: dict[str, int]) -> list[Finding]:
    """Scan a single file, returning all findings it contains."""
    if _is_binary(path):
        return []
    findings: list[Finding] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, start=1):
                match = pattern.search(line)
                if not match:
                    continue
                tag = match.group(1)
                owner = match.group(2)
                message = match.group(3).strip()
                # Resolve the canonical tag spelling/weight (handles case-insensitive).
                canonical = _canonical_tag(tag, tags)
                if canonical is None:
                    continue
                if owner and not message:
                    message = ""
                if owner:
                    message = f"({owner}) {message}".strip()
                findings.append(
                    Finding(
                        tag=canonical,
                        message=message,
                        path=str(path),
                        line=lineno,
                        raw=line.rstrip("\n"),
                        weight=tags[canonical],
                    )
                )
    except OSError:
        return []
    return findings


def _canonical_tag(found: str, tags: dict[str, int]) -> str | None:
    """Map a matched tag back to its canonical key (case-insensitive aware)."""
    if found in tags:
        return found
    upper = found.upper()
    for key in tags:
        if key.upper() == upper:
            return key
    return None


def scan(root: Path, config: ScanConfig) -> list[Finding]:
    """Scan ``root`` and return all findings, sorted by file then line."""
    pattern = _build_pattern(config.tags, config.case_sensitive)
    results: list[Finding] = []
    for path in iter_files(root, config):
        results.extend(scan_file(path, pattern, config.tags))
    results.sort(key=lambda f: (f.path, f.line))
    return results
