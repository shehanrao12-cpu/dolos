"""Build the GitHub Actions expression contexts from the local environment.

prepush approximates the ``github`` and ``runner`` contexts using local git
metadata and the host platform, so that expressions referencing them resolve to
sensible values during a local run.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any


def _git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _repo_slug(cwd: Path) -> str:
    url = _git(["config", "--get", "remote.origin.url"], cwd)
    if not url:
        return ""
    url = url.removesuffix(".git")
    if url.startswith("git@") and ":" in url:
        return url.split(":", 1)[1]
    # https://host/owner/repo -> owner/repo
    parts = url.split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return ""


def runner_os() -> str:
    system = platform.system()
    return {"Linux": "Linux", "Darwin": "macOS", "Windows": "Windows"}.get(
        system, system
    )


def runner_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "X64"
    if machine in {"aarch64", "arm64"}:
        return "ARM64"
    return machine.upper()


def build_github_context(cwd: Path) -> dict[str, Any]:
    slug = _repo_slug(cwd)
    ref_name = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) or "main"
    sha = _git(["rev-parse", "HEAD"], cwd)
    owner = slug.split("/")[0] if "/" in slug else ""
    return {
        "repository": slug,
        "repository_owner": owner,
        "ref": f"refs/heads/{ref_name}",
        "ref_name": ref_name,
        "ref_type": "branch",
        "sha": sha,
        "actor": os.environ.get("USER") or os.environ.get("USERNAME") or "local",
        "workflow": "",
        "event_name": "push",
        "workspace": str(cwd),
        "run_id": "0",
        "run_number": "0",
        "server_url": "https://github.com",
    }


def build_runner_context(cwd: Path) -> dict[str, Any]:
    return {
        "os": runner_os(),
        "arch": runner_arch(),
        "name": "prepush-local",
        "temp": os.environ.get("RUNNER_TEMP", "/tmp"),
        "workspace": str(cwd),
    }


def base_context(cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    """Assemble the full base context (everything except matrix/step-specific)."""
    return {
        "github": build_github_context(cwd),
        "runner": build_runner_context(cwd),
        "env": dict(env),
        # secrets/vars are sourced from the local environment as a best effort.
        "secrets": dict(os.environ),
        "vars": dict(os.environ),
        "matrix": {},
        "strategy": {},
        "job": {"status": "success"},
        "steps": {},
    }
