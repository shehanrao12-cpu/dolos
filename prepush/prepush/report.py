"""Terminal output for prepush runs."""

from __future__ import annotations

from .runner import JobResult, Status


class _C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"


_SYMBOLS = {
    Status.SUCCESS: "✓",
    Status.FAILED: "✗",
    Status.SKIPPED: "•",
    Status.WARNED: "!",
}

_COLORS = {
    Status.SUCCESS: _C.GREEN,
    Status.FAILED: _C.RED,
    Status.SKIPPED: _C.DIM,
    Status.WARNED: _C.YELLOW,
}


def _paint(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{_C.RESET}" if enabled else text


def format_job_header(name: str, color: bool) -> str:
    return _paint(f"▶ {name}", _C.BOLD + _C.CYAN, color)


def format_step(result, color: bool) -> str:
    sym = _SYMBOLS[result.status]
    col = _COLORS[result.status]
    line = f"  {_paint(sym, col, color)} {result.name}"
    extras = []
    if result.duration:
        extras.append(f"{result.duration:.2f}s")
    if result.reason and result.status in (Status.SKIPPED, Status.FAILED, Status.WARNED):
        extras.append(result.reason)
    if extras:
        line += _paint(f"  ({', '.join(extras)})", _C.DIM, color)
    return line


def format_summary(jobs: list[JobResult], color: bool) -> str:
    total = sum(len(j.steps) for j in jobs)
    counts = {s: 0 for s in Status}
    for job in jobs:
        for step in job.steps:
            counts[step.status] += 1

    parts = [
        _paint(f"{counts[Status.SUCCESS]} passed", _C.GREEN, color),
        _paint(f"{counts[Status.FAILED]} failed", _C.RED, color)
        if counts[Status.FAILED]
        else "0 failed",
        _paint(f"{counts[Status.WARNED]} warned", _C.YELLOW, color)
        if counts[Status.WARNED]
        else "0 warned",
        f"{counts[Status.SKIPPED]} skipped",
    ]
    body = ", ".join(parts)
    any_failed = counts[Status.FAILED] > 0
    headline = "FAILED" if any_failed else "OK"
    headline = _paint(headline, _C.RED if any_failed else _C.GREEN, color)
    return f"\n{_paint('Summary', _C.BOLD, color)}: {headline} — {body} ({total} steps)"
