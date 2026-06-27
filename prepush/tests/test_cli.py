from pathlib import Path

import pytest

from prepush.cli import run


def _wf(tmp_path: Path, content: str, name: str = "ci.yml") -> None:
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / name).write_text(content)


def test_run_success_exit_zero(tmp_path: Path, capsys):
    _wf(tmp_path, "name: x\njobs:\n  a:\n    steps:\n      - run: 'true'\n")
    code = run([str(tmp_path), "--no-color"])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK" in out


def test_run_failure_exit_one(tmp_path: Path, capsys):
    _wf(tmp_path, "name: x\njobs:\n  a:\n    steps:\n      - run: exit 3\n")
    code = run([str(tmp_path), "--no-color"])
    out = capsys.readouterr().out
    assert code == 1
    assert "FAILED" in out


def test_list(tmp_path: Path, capsys):
    _wf(
        tmp_path,
        "name: CI\njobs:\n  build:\n    steps:\n      - name: t\n        run: 'true'\n",
    )
    code = run([str(tmp_path), "--list", "--no-color"])
    out = capsys.readouterr().out
    assert code == 0
    assert "job: build" in out
    assert "- t  (run)" in out


def test_job_filter(tmp_path: Path, capsys):
    _wf(
        tmp_path,
        """
name: x
jobs:
  a:
    steps:
      - run: echo a
  b:
    steps:
      - run: exit 1
""",
    )
    # Only run job 'a', so overall should pass despite b failing.
    code = run([str(tmp_path), "--job", "a", "--no-color"])
    assert code == 0


def test_workflow_filter_no_match(tmp_path: Path, capsys):
    _wf(tmp_path, "name: CI\njobs:\n  a:\n    steps:\n      - run: 'true'\n")
    code = run([str(tmp_path), "--workflow", "nonexistent"])
    assert code == 2


def test_no_workflows(tmp_path: Path, capsys):
    code = run([str(tmp_path)])
    assert code == 2


def test_missing_path():
    assert run(["/no/such/path/here"]) == 2


def test_dry_run(tmp_path: Path, capsys):
    marker = tmp_path / "ran.txt"
    _wf(tmp_path, f"name: x\njobs:\n  a:\n    steps:\n      - run: touch {marker.name}\n")
    code = run([str(tmp_path), "--dry-run", "--no-color"])
    assert code == 0
    assert not marker.exists()


def test_extra_env_flag(tmp_path: Path, capsys):
    out = tmp_path / "o.txt"
    _wf(
        tmp_path,
        f"name: x\njobs:\n  a:\n    steps:\n      - run: printf \"$INJECTED\" > {out.name}\n",
    )
    code = run([str(tmp_path), "--env", "INJECTED=hi", "--no-color"])
    assert code == 0
    assert out.read_text() == "hi"
