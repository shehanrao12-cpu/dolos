"""Scoring, aggregation, and output formatting."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

from .config import Config
from .scanner import Finding


@dataclass
class Summary:
    """Aggregate statistics for a set of findings."""

    total: int
    stale: int
    total_score: float
    by_tag: dict[str, int]
    by_author: dict[str, int]


def score_findings(findings: list[Finding], config: Config) -> list[Finding]:
    """Apply staleness + severity scoring, returning findings sorted by score."""
    scored: list[Finding] = []
    for f in findings:
        is_stale = f.age_days is not None and f.age_days >= config.stale_days
        score = float(f.weight)
        if is_stale:
            score *= config.stale_multiplier
        scored.append(f.with_score(score, stale=is_stale))
    scored.sort(key=lambda f: (-f.score, f.path, f.line))
    return scored


def summarize(findings: list[Finding]) -> Summary:
    """Compute aggregate statistics over ``findings``."""
    by_tag: dict[str, int] = {}
    by_author: dict[str, int] = {}
    stale = 0
    total_score = 0.0
    for f in findings:
        by_tag[f.tag] = by_tag.get(f.tag, 0) + 1
        if f.author:
            by_author[f.author] = by_author.get(f.author, 0) + 1
        if f.stale:
            stale += 1
        total_score += f.score
    return Summary(
        total=len(findings),
        stale=stale,
        total_score=round(total_score, 2),
        by_tag=dict(sorted(by_tag.items(), key=lambda kv: (-kv[1], kv[0]))),
        by_author=dict(sorted(by_author.items(), key=lambda kv: (-kv[1], kv[0]))),
    )


def _finding_dict(f: Finding) -> dict:
    return {
        "tag": f.tag,
        "message": f.message,
        "path": f.path,
        "line": f.line,
        "weight": f.weight,
        "score": f.score,
        "author": f.author,
        "age_days": f.age_days,
        "stale": f.stale,
        "raw": f.raw,
    }


def render_json(findings: list[Finding], summary: Summary) -> str:
    payload = {
        "summary": {
            "total": summary.total,
            "stale": summary.stale,
            "total_score": summary.total_score,
            "by_tag": summary.by_tag,
            "by_author": summary.by_author,
        },
        "findings": [_finding_dict(f) for f in findings],
    }
    return json.dumps(payload, indent=2)


def render_csv(findings: list[Finding]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["tag", "score", "stale", "age_days", "author", "path", "line", "message"]
    )
    for f in findings:
        writer.writerow(
            [
                f.tag,
                f.score,
                f.stale,
                "" if f.age_days is None else f.age_days,
                f.author or "",
                f.path,
                f.line,
                f.message,
            ]
        )
    return buf.getvalue().rstrip("\n")


def render_markdown(findings: list[Finding], summary: Summary) -> str:
    lines: list[str] = []
    lines.append("# Technical Debt Report")
    lines.append("")
    lines.append(f"**Total findings:** {summary.total}  ")
    lines.append(f"**Stale findings:** {summary.stale}  ")
    lines.append(f"**Debt score:** {summary.total_score}")
    lines.append("")
    if summary.by_tag:
        lines.append("## By tag")
        lines.append("")
        lines.append("| Tag | Count |")
        lines.append("| --- | ----- |")
        for tag, count in summary.by_tag.items():
            lines.append(f"| {tag} | {count} |")
        lines.append("")
    if findings:
        lines.append("## Findings")
        lines.append("")
        lines.append("| Score | Tag | Location | Age (d) | Author | Message |")
        lines.append("| ----- | --- | -------- | ------- | ------ | ------- |")
        for f in findings:
            age = "" if f.age_days is None else str(f.age_days)
            author = f.author or ""
            stale_mark = " ⏳" if f.stale else ""
            msg = f.message.replace("|", "\\|") or "—"
            lines.append(
                f"| {f.score:g}{stale_mark} | {f.tag} | `{f.path}:{f.line}` "
                f"| {age} | {author} | {msg} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip("\n")


# --- terminal rendering -----------------------------------------------------

class _Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"


def _tag_color(tag: str, weight: int) -> str:
    if weight >= 4:
        return _Color.RED
    if weight >= 2:
        return _Color.YELLOW
    return _Color.CYAN


def render_terminal(findings: list[Finding], summary: Summary, *, color: bool) -> str:
    def c(text: str, code: str) -> str:
        return f"{code}{text}{_Color.RESET}" if color else text

    lines: list[str] = []
    if not findings:
        lines.append(c("No technical debt markers found. ✨", _Color.CYAN))
        return "\n".join(lines)

    for f in findings:
        loc = c(f"{f.path}:{f.line}", _Color.DIM)
        tag = c(f"{f.tag:<10}", _tag_color(f.tag, f.weight))
        meta = []
        if f.author:
            meta.append(f.author)
        if f.age_days is not None:
            age_str = f"{f.age_days}d"
            if f.stale:
                age_str = c(age_str + " STALE", _Color.MAGENTA)
            meta.append(age_str)
        meta_str = c(f"  ({', '.join(meta)})", _Color.DIM) if meta else ""
        msg = f.message or c("(no message)", _Color.DIM)
        lines.append(f"{tag} {msg}{meta_str}")
        lines.append(f"           {loc}")

    lines.append("")
    header = c("Summary", _Color.BOLD)
    lines.append(header)
    lines.append(
        f"  {summary.total} findings, {summary.stale} stale, "
        f"score {summary.total_score}"
    )
    if summary.by_tag:
        tag_bits = ", ".join(f"{t}={n}" for t, n in summary.by_tag.items())
        lines.append(f"  {tag_bits}")
    return "\n".join(lines)
