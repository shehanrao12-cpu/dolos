from pathlib import Path

from prepush.parser import load_workflow
from prepush.runner import RunOptions, Status, run_job


def _wf(tmp_path: Path, content: str):
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    p = wf_dir / "ci.yml"
    p.write_text(content)
    return load_workflow(p)


def _opts(tmp_path: Path, **kw):
    return RunOptions(cwd=tmp_path, **kw)


def test_successful_run_step(tmp_path: Path):
    wf = _wf(tmp_path, "name: x\njobs:\n  a:\n    steps:\n      - run: 'true'\n")
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.SUCCESS
    assert not result.failed


def test_failing_step_marks_job_failed(tmp_path: Path):
    wf = _wf(tmp_path, "name: x\njobs:\n  a:\n    steps:\n      - run: exit 7\n")
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.FAILED
    assert result.steps[0].returncode == 7
    assert result.failed


def test_failure_stops_subsequent_steps(tmp_path: Path):
    wf = _wf(
        tmp_path,
        "name: x\njobs:\n  a:\n    steps:\n      - run: exit 1\n      - run: echo second\n",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert len(result.steps) == 1  # second step never ran


def test_keep_going_runs_all(tmp_path: Path):
    wf = _wf(
        tmp_path,
        "name: x\njobs:\n  a:\n    steps:\n      - run: exit 1\n      - run: 'true'\n",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path, keep_going=True))
    assert len(result.steps) == 2
    assert result.steps[1].status is Status.SUCCESS


def test_continue_on_error_warns(tmp_path: Path):
    wf = _wf(
        tmp_path,
        "name: x\njobs:\n  a:\n    steps:\n      - run: exit 1\n        continue-on-error: true\n      - run: 'true'\n",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.WARNED
    assert not result.failed
    assert result.steps[1].status is Status.SUCCESS


def test_uses_checkout_skipped(tmp_path: Path):
    wf = _wf(
        tmp_path,
        "name: x\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.SKIPPED
    assert "checkout" in result.steps[0].reason


def test_uses_other_skipped_with_note(tmp_path: Path):
    wf = _wf(
        tmp_path,
        "name: x\njobs:\n  a:\n    steps:\n      - uses: actions/setup-node@v4\n",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.SKIPPED
    assert "setup-node" in result.steps[0].reason


def test_if_condition_skips(tmp_path: Path):
    wf = _wf(
        tmp_path,
        "name: x\njobs:\n  a:\n    steps:\n      - run: echo no\n        if: runner.os == 'Windows'\n",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.SKIPPED
    assert "condition" in result.steps[0].reason


def test_env_interpolation_in_run(tmp_path: Path):
    out_file = tmp_path / "out.txt"
    wf = _wf(
        tmp_path,
        f"""
name: x
env:
  GREETING: hello
jobs:
  a:
    steps:
      - run: echo "${{{{ env.GREETING }}}}" > {out_file.name}
""",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.SUCCESS
    assert out_file.read_text().strip() == "hello"


def test_env_available_as_process_env(tmp_path: Path):
    out_file = tmp_path / "out.txt"
    wf = _wf(
        tmp_path,
        f"""
name: x
jobs:
  a:
    env:
      MYVAR: fromjob
    steps:
      - run: printf "$MYVAR" > {out_file.name}
""",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.SUCCESS
    assert out_file.read_text() == "fromjob"


def test_working_directory(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    wf = _wf(
        tmp_path,
        "name: x\njobs:\n  a:\n    steps:\n      - run: pwd > here.txt\n        working-directory: sub\n",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.SUCCESS
    assert (sub / "here.txt").exists()


def test_dry_run_does_not_execute(tmp_path: Path):
    marker = tmp_path / "ran.txt"
    wf = _wf(
        tmp_path,
        f"name: x\njobs:\n  a:\n    steps:\n      - run: touch {marker.name}\n",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path, dry_run=True))
    assert result.steps[0].status is Status.SKIPPED
    assert not marker.exists()


def test_matrix_value_in_run(tmp_path: Path):
    out = tmp_path / "m.txt"
    wf = _wf(
        tmp_path,
        f"""
name: x
jobs:
  a:
    strategy:
      matrix:
        word: [alpha]
    steps:
      - run: echo "${{{{ matrix.word }}}}" > {out.name}
""",
    )
    result = run_job(wf, wf.jobs[0], _opts(tmp_path))
    assert result.steps[0].status is Status.SUCCESS
    assert out.read_text().strip() == "alpha"
