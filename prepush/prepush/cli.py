"""Command-line interface for prepush."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .parser import WorkflowError, find_workflow_files, load_workflow
from .report import format_job_header, format_step, format_summary
from .runner import JobResult, RunOptions, Status, job_matches_condition, run_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prepush",
        description="Run your GitHub Actions workflow steps locally — no Docker — "
        "to catch failures before you push.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repo root or a specific workflow file (default: current directory).",
    )
    parser.add_argument(
        "-w", "--workflow", help="Only run workflows whose name/filename contains this."
    )
    parser.add_argument(
        "-j", "--job", action="append", dest="jobs", help="Only run these job id(s)."
    )
    parser.add_argument(
        "-l", "--list", action="store_true", help="List workflows/jobs/steps and exit."
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="Show steps without running them."
    )
    parser.add_argument(
        "-k",
        "--keep-going",
        action="store_true",
        help="Keep running a job's remaining steps after a failure.",
    )
    parser.add_argument(
        "-e",
        "--env",
        action="append",
        dest="env",
        metavar="KEY=VALUE",
        help="Set an environment variable for steps (repeatable).",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output.")
    parser.add_argument("--version", action="version", version=f"prepush {__version__}")
    return parser


def _parse_env(pairs: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in pairs or []:
        key, _, value = item.partition("=")
        out[key.strip()] = value
    return out


def _matches_workflow(name: str, path: Path, needle: str | None) -> bool:
    if not needle:
        return True
    needle = needle.lower()
    return needle in name.lower() or needle in path.name.lower()


def _list(workflows, jobs_filter, color: bool) -> None:
    for wf in workflows:
        print(format_job_header(f"{wf.name}  [{wf.path.name}]", color))
        for job in wf.jobs:
            if jobs_filter and job.job_id not in jobs_filter:
                continue
            print(f"  job: {job.job_id}  {job.name}")
            for step in job.steps:
                kind = "run" if step.run is not None else f"uses {step.uses}"
                print(f"      - {step.name}  ({kind})")


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.path)
    if not root.exists():
        print(f"prepush: path not found: {root}", file=sys.stderr)
        return 2

    files = find_workflow_files(root)
    if not files:
        print(
            f"prepush: no workflow files found under {root}/.github/workflows",
            file=sys.stderr,
        )
        return 2

    workflows = []
    for path in files:
        try:
            wf = load_workflow(path)
        except WorkflowError as exc:
            print(f"prepush: {exc}", file=sys.stderr)
            return 2
        if _matches_workflow(wf.name, path, args.workflow):
            workflows.append(wf)

    if not workflows:
        print("prepush: no workflows matched the filter", file=sys.stderr)
        return 2

    color = sys.stdout.isatty() and not args.no_color
    jobs_filter = set(args.jobs) if args.jobs else None

    if args.list:
        _list(workflows, jobs_filter, color)
        return 0

    cwd = root if root.is_dir() else root.parent
    options = RunOptions(
        cwd=cwd.resolve(),
        dry_run=args.dry_run,
        keep_going=args.keep_going,
        extra_env=_parse_env(args.env),
        on_output=lambda text: print(_indent(text)),
        on_step=lambda result: print(format_step(result, color)),
    )

    results: list[JobResult] = []
    for wf in workflows:
        for job in wf.jobs:
            if jobs_filter and job.job_id not in jobs_filter:
                continue
            if not job_matches_condition(wf, job, options):
                continue
            print(format_job_header(f"{wf.name} / {job.name}", color))
            results.append(run_job(wf, job, options))

    print(format_summary(results, color))
    any_failed = any(j.failed for j in results)
    return 1 if any_failed else 0


def _indent(text: str) -> str:
    return "\n".join("      │ " + line for line in text.splitlines())


def main() -> None:  # pragma: no cover - thin wrapper
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
