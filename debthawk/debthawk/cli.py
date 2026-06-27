"""Command-line interface for debthawk."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import Config, load
from .gitblame import is_git_repo, lookup
from .report import (
    render_csv,
    render_json,
    render_markdown,
    render_terminal,
    score_findings,
    summarize,
)
from .scanner import Finding, ScanConfig, scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="debthawk",
        description="Hunt down technical debt (TODO/FIXME/HACK/...) in a codebase.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="File or directory to scan (default: current directory).",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["terminal", "json", "markdown", "csv"],
        default="terminal",
        help="Output format (default: terminal).",
    )
    parser.add_argument(
        "-t",
        "--tag",
        action="append",
        dest="tags",
        metavar="TAG[=WEIGHT]",
        help="Restrict to / add a tag, optionally with a weight (repeatable).",
    )
    parser.add_argument(
        "-i",
        "--ignore",
        action="append",
        dest="ignore",
        metavar="GLOB",
        help="Glob of paths to ignore, relative to scan root (repeatable).",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=None,
        help="Age in days after which a finding is considered stale.",
    )
    parser.add_argument(
        "--max-debt",
        type=int,
        default=None,
        metavar="N",
        help="Exit non-zero if total findings exceed N (for CI gating).",
    )
    parser.add_argument(
        "--max-score",
        type=float,
        default=None,
        metavar="N",
        help="Exit non-zero if the aggregate debt score exceeds N.",
    )
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Exit non-zero if any stale finding is present.",
    )
    parser.add_argument(
        "--no-blame",
        action="store_true",
        help="Disable git-blame enrichment (author/age).",
    )
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="Match tags case-insensitively.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored terminal output.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"debthawk {__version__}",
    )
    return parser


def _parse_tag_args(tag_args: list[str]) -> dict[str, int]:
    """Parse ``--tag NAME`` / ``--tag NAME=WEIGHT`` arguments."""
    from .tags import DEFAULT_TAGS

    parsed: dict[str, int] = {}
    for item in tag_args:
        if "=" in item:
            name, _, weight = item.partition("=")
            try:
                parsed[name.strip()] = int(weight)
            except ValueError:
                parsed[name.strip()] = DEFAULT_TAGS.get(name.strip().upper(), 1)
        else:
            name = item.strip()
            parsed[name] = DEFAULT_TAGS.get(name.upper(), 1)
    return parsed


def _merge_cli(config: Config, args: argparse.Namespace) -> Config:
    """Overlay CLI arguments onto a file/default config."""
    if args.tags:
        config.tags = _parse_tag_args(args.tags)
    if args.ignore:
        config.ignore_globs = list(config.ignore_globs) + list(args.ignore)
    if args.stale_days is not None:
        config.stale_days = args.stale_days
    if args.ignore_case:
        config.case_sensitive = False
    if args.no_blame:
        config.blame = False
    return config


def _enrich_with_blame(findings: list[Finding]) -> list[Finding]:
    """Annotate findings with author and age via git blame."""
    enriched: list[Finding] = []
    for f in findings:
        author, age = lookup(f.path, f.line)
        enriched.append(
            Finding(
                tag=f.tag,
                message=f.message,
                path=f.path,
                line=f.line,
                raw=f.raw,
                weight=f.weight,
                author=author,
                age_days=age,
            )
        )
    return enriched


def run(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    root = Path(args.path)
    if not root.exists():
        print(f"debthawk: path not found: {root}", file=sys.stderr)
        return 2

    config = _merge_cli(load(root), args)

    scan_config = ScanConfig(
        tags=config.tags,
        ignore_globs=config.ignore_globs,
        case_sensitive=config.case_sensitive,
    )
    findings = scan(root, scan_config)

    if config.blame and is_git_repo(root):
        findings = _enrich_with_blame(findings)

    findings = score_findings(findings, config)
    summary = summarize(findings)

    color = sys.stdout.isatty() and not args.no_color
    if args.format == "json":
        print(render_json(findings, summary))
    elif args.format == "markdown":
        print(render_markdown(findings, summary))
    elif args.format == "csv":
        print(render_csv(findings))
    else:
        print(render_terminal(findings, summary, color=color))

    return _exit_code(summary, args)


def _exit_code(summary, args: argparse.Namespace) -> int:
    """Determine the CI gating exit code."""
    if args.max_debt is not None and summary.total > args.max_debt:
        return 1
    if args.max_score is not None and summary.total_score > args.max_score:
        return 1
    if args.fail_on_stale and summary.stale > 0:
        return 1
    return 0


def main() -> None:  # pragma: no cover - thin wrapper
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
