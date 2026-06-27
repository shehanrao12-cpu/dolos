"""Execute workflow steps locally, without Docker."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from . import expressions
from .context import base_context
from .parser import Job, Step, Workflow


class Status(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNED = "warned"  # failed but continue-on-error


@dataclass
class StepResult:
    name: str
    status: Status
    returncode: int = 0
    duration: float = 0.0
    reason: str = ""


@dataclass
class JobResult:
    job_id: str
    name: str
    steps: list[StepResult] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(s.status is Status.FAILED for s in self.steps)


@dataclass
class RunOptions:
    cwd: Path
    dry_run: bool = False
    keep_going: bool = False  # continue running steps after a failure
    extra_env: dict[str, str] = field(default_factory=dict)
    on_output: Callable[[str], None] | None = None
    on_step: Callable[["StepResult"], None] | None = None


# Shells we know how to invoke locally, mapped to an argv builder.
def _shell_argv(shell: str, script_path: str) -> list[str] | None:
    shell = shell.lower()
    if shell == "bash":
        return ["bash", "--noprofile", "--norc", "-eo", "pipefail", script_path]
    if shell == "sh":
        return ["sh", "-e", script_path]
    if shell == "python":
        return ["python3", script_path]
    if shell in {"pwsh", "powershell"}:
        exe = shutil.which("pwsh") or shutil.which("powershell")
        return [exe, "-File", script_path] if exe else None
    return None


def _default_shell() -> str:
    return "bash" if shutil.which("bash") else "sh"


def _merge_env(
    workflow: Workflow, job: Job, step: Step, ctx: dict[str, Any]
) -> dict[str, str]:
    """Compute the env context (configured vars), expanding expressions."""
    merged: dict[str, str] = {}
    for layer in (workflow.env, job.env, step.env):
        for key, value in layer.items():
            merged[key] = expressions.expand(value, {**ctx, "env": merged})
    return merged


def _build_context(
    workflow: Workflow, job: Job, options: RunOptions, env_ctx: dict[str, str]
) -> dict[str, Any]:
    ctx = base_context(options.cwd, env_ctx)
    ctx["matrix"] = dict(job.matrix)
    ctx["github"]["workflow"] = workflow.name
    return ctx


def _run_shell_step(
    step: Step,
    shell: str,
    script: str,
    work_dir: Path,
    child_env: dict[str, str],
    options: RunOptions,
) -> StepResult:
    suffix = ".py" if shell == "python" else (".ps1" if "sh" in shell and "pw" in shell else ".sh")
    fd, tmp_path = tempfile.mkstemp(prefix="prepush-", suffix=suffix)
    start = time.monotonic()
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(script)
        argv = _shell_argv(shell, tmp_path)
        if argv is None:
            return StepResult(
                step.name,
                Status.SKIPPED,
                reason=f"shell '{shell}' is not available locally",
            )
        proc = subprocess.run(
            argv,
            cwd=work_dir,
            env=child_env,
            capture_output=True,
            text=True,
        )
        duration = time.monotonic() - start
        if options.on_output:
            if proc.stdout:
                options.on_output(proc.stdout.rstrip("\n"))
            if proc.stderr:
                options.on_output(proc.stderr.rstrip("\n"))
        if proc.returncode == 0:
            return StepResult(step.name, Status.SUCCESS, 0, duration)
        status = Status.WARNED if step.continue_on_error else Status.FAILED
        return StepResult(
            step.name,
            status,
            proc.returncode,
            duration,
            reason=f"exited with code {proc.returncode}",
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_step(
    workflow: Workflow,
    job: Job,
    step: Step,
    options: RunOptions,
    job_status: str,
) -> StepResult:
    """Run a single step and return its result."""
    env_ctx = _merge_env(workflow, job, step, _build_context(workflow, job, options, {}))
    ctx = _build_context(workflow, job, options, env_ctx)
    expressions.set_job_status(job_status)

    if not expressions.evaluate_condition(step.if_cond, ctx):
        return StepResult(step.name, Status.SKIPPED, reason="if condition was false")

    if step.uses:
        action = step.uses.split("@")[0]
        if action.startswith("actions/checkout"):
            return StepResult(
                step.name, Status.SKIPPED, reason="checkout: using local working tree"
            )
        return StepResult(
            step.name,
            Status.SKIPPED,
            reason=f"uses: {step.uses} (run-only mode; ensure this is set up locally)",
        )

    if step.run is None:
        return StepResult(step.name, Status.SKIPPED, reason="no run command")

    shell = step.shell or job.defaults_run.get("shell") or _default_shell()
    script = expressions.expand(step.run, ctx)

    work_dir = options.cwd
    wd = step.working_directory or job.defaults_run.get("working-directory")
    if wd:
        wd_expanded = expressions.expand(wd, ctx)
        work_dir = (options.cwd / wd_expanded).resolve()

    child_env = {**os.environ, **options.extra_env, **env_ctx}

    if options.dry_run:
        return StepResult(step.name, Status.SKIPPED, reason="dry-run")

    return _run_shell_step(step, shell, script, work_dir, child_env, options)


def run_job(workflow: Workflow, job: Job, options: RunOptions) -> JobResult:
    """Run all steps in a job, honoring conditions and failure semantics."""
    result = JobResult(job_id=job.job_id, name=job.name)
    job_status = "success"
    for step in job.steps:
        step_result = run_step(workflow, job, step, options, job_status)
        result.steps.append(step_result)
        if options.on_step:
            options.on_step(step_result)
        if step_result.status is Status.FAILED:
            job_status = "failure"
            if not options.keep_going:
                break
    return result


def job_matches_condition(workflow: Workflow, job: Job, options: RunOptions) -> bool:
    ctx = _build_context(workflow, job, options, {})
    return expressions.evaluate_condition(job.if_cond, ctx)
