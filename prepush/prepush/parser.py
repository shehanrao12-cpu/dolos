"""Parse GitHub Actions workflow files into runnable jobs and steps."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Step:
    name: str
    run: str | None = None
    uses: str | None = None
    shell: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    working_directory: str | None = None
    if_cond: Any = None
    continue_on_error: bool = False
    step_id: str | None = None


@dataclass
class Job:
    job_id: str
    name: str
    steps: list[Step]
    env: dict[str, str] = field(default_factory=dict)
    defaults_run: dict[str, str] = field(default_factory=dict)
    if_cond: Any = None
    runs_on: str = ""
    matrix: dict[str, Any] = field(default_factory=dict)
    needs: list[str] = field(default_factory=list)


@dataclass
class Workflow:
    path: Path
    name: str
    env: dict[str, str]
    jobs: list[Job]


class WorkflowError(Exception):
    """Raised when a workflow file cannot be parsed."""


def find_workflow_files(root: Path) -> list[Path]:
    """Return workflow YAML files under ``root``.

    If ``root`` is a file it is returned directly; otherwise the standard
    ``.github/workflows`` directory is searched.
    """
    if root.is_file():
        return [root]
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    files = sorted(
        p for p in wf_dir.iterdir() if p.suffix in {".yml", ".yaml"} and p.is_file()
    )
    return files


def _as_env(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): "" if v is None else str(v) for k, v in value.items()}


def _expand_matrix(strategy: Any) -> list[dict[str, Any]]:
    """Expand a ``strategy.matrix`` into concrete combinations.

    Supports the cartesian product of list-valued keys plus ``include`` and
    ``exclude`` lists (the most common forms).
    """
    if not isinstance(strategy, dict):
        return [{}]
    matrix = strategy.get("matrix")
    if not isinstance(matrix, dict):
        return [{}]

    include = matrix.get("include") or []
    exclude = matrix.get("exclude") or []
    axes = {k: v for k, v in matrix.items() if k not in {"include", "exclude"}}

    combos: list[dict[str, Any]] = []
    if axes:
        keys = list(axes.keys())
        value_lists = [v if isinstance(v, list) else [v] for v in axes.values()]
        for product in itertools.product(*value_lists):
            combos.append(dict(zip(keys, product)))
    else:
        combos.append({})

    # Apply excludes.
    if exclude:
        combos = [
            c for c in combos if not any(_matches(c, ex) for ex in exclude)
        ]

    # Apply includes (extend matching combos / append new ones).
    for inc in include:
        if not isinstance(inc, dict):
            continue
        merged_any = False
        for combo in combos:
            if _is_compatible(combo, inc):
                combo.update(inc)
                merged_any = True
        if not merged_any:
            combos.append(dict(inc))

    return combos or [{}]


def _matches(combo: dict[str, Any], spec: dict[str, Any]) -> bool:
    return all(combo.get(k) == v for k, v in spec.items())


def _is_compatible(combo: dict[str, Any], inc: dict[str, Any]) -> bool:
    """An include extends a combo if it agrees on all shared keys."""
    return all(combo[k] == v for k, v in inc.items() if k in combo)


def _parse_step(raw: dict[str, Any], index: int) -> Step:
    name = raw.get("name") or raw.get("uses") or f"step {index + 1}"
    run = raw.get("run")
    return Step(
        name=str(name),
        run=str(run) if run is not None else None,
        uses=raw.get("uses"),
        shell=raw.get("shell"),
        env=_as_env(raw.get("env")),
        working_directory=raw.get("working-directory"),
        if_cond=raw.get("if"),
        continue_on_error=bool(raw.get("continue-on-error", False)),
        step_id=raw.get("id"),
    )


def _parse_job(job_id: str, raw: dict[str, Any]) -> list[Job]:
    if not isinstance(raw, dict):
        raise WorkflowError(f"job '{job_id}' is not a mapping")
    raw_steps = raw.get("steps") or []
    steps = [_parse_step(s, i) for i, s in enumerate(raw_steps) if isinstance(s, dict)]
    defaults = raw.get("defaults") or {}
    defaults_run = defaults.get("run") if isinstance(defaults, dict) else {}
    runs_on = raw.get("runs-on") or ""
    if isinstance(runs_on, list):
        runs_on = ", ".join(str(x) for x in runs_on)

    needs = raw.get("needs") or []
    if isinstance(needs, str):
        needs = [needs]

    combos = _expand_matrix(raw.get("strategy"))
    jobs: list[Job] = []
    for combo in combos:
        suffix = ""
        if combo:
            suffix = " (" + ", ".join(f"{k}={v}" for k, v in combo.items()) + ")"
        jobs.append(
            Job(
                job_id=job_id,
                name=str(raw.get("name") or job_id) + suffix,
                steps=steps,
                env=_as_env(raw.get("env")),
                defaults_run=defaults_run if isinstance(defaults_run, dict) else {},
                if_cond=raw.get("if"),
                runs_on=str(runs_on),
                matrix=combo,
                needs=[str(n) for n in needs],
            )
        )
    return jobs


def load_workflow(path: Path) -> Workflow:
    """Parse a single workflow file into a :class:`Workflow`."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise WorkflowError(f"failed to read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkflowError(f"{path}: top-level YAML is not a mapping")

    raw_jobs = data.get("jobs") or {}
    if not isinstance(raw_jobs, dict):
        raise WorkflowError(f"{path}: 'jobs' is not a mapping")

    jobs: list[Job] = []
    for job_id, raw in raw_jobs.items():
        jobs.extend(_parse_job(str(job_id), raw))

    return Workflow(
        path=path,
        name=str(data.get("name") or path.stem),
        env=_as_env(data.get("env")),
        jobs=jobs,
    )
