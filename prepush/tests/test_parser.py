from pathlib import Path

import pytest

from prepush.parser import (
    WorkflowError,
    _expand_matrix,
    find_workflow_files,
    load_workflow,
)


def _write_wf(tmp_path: Path, content: str, name: str = "ci.yml") -> Path:
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    p = wf_dir / name
    p.write_text(content)
    return p


def test_find_workflow_files(tmp_path: Path):
    _write_wf(tmp_path, "name: a\njobs: {}\n", "a.yml")
    _write_wf(tmp_path, "name: b\njobs: {}\n", "b.yaml")
    (tmp_path / ".github" / "workflows" / "notes.txt").write_text("ignore")
    files = find_workflow_files(tmp_path)
    assert [f.name for f in files] == ["a.yml", "b.yaml"]


def test_find_single_file(tmp_path: Path):
    p = _write_wf(tmp_path, "name: a\njobs: {}\n")
    assert find_workflow_files(p) == [p]


def test_load_basic_workflow(tmp_path: Path):
    p = _write_wf(
        tmp_path,
        """
name: CI
env:
  GLOBAL: g
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      JOBVAR: j
    steps:
      - name: checkout
        uses: actions/checkout@v4
      - name: test
        run: echo hi
        env:
          STEPVAR: s
""",
    )
    wf = load_workflow(p)
    assert wf.name == "CI"
    assert wf.env == {"GLOBAL": "g"}
    assert len(wf.jobs) == 1
    job = wf.jobs[0]
    assert job.job_id == "build"
    assert job.env == {"JOBVAR": "j"}
    assert job.runs_on == "ubuntu-latest"
    assert len(job.steps) == 2
    assert job.steps[0].uses == "actions/checkout@v4"
    assert job.steps[1].run == "echo hi"
    assert job.steps[1].env == {"STEPVAR": "s"}


def test_matrix_expansion_cartesian():
    combos = _expand_matrix(
        {"matrix": {"os": ["linux", "mac"], "py": ["3.11", "3.12"]}}
    )
    assert len(combos) == 4
    assert {"os": "linux", "py": "3.11"} in combos
    assert {"os": "mac", "py": "3.12"} in combos


def test_matrix_exclude():
    combos = _expand_matrix(
        {
            "matrix": {
                "os": ["linux", "mac"],
                "py": ["3.11", "3.12"],
                "exclude": [{"os": "mac", "py": "3.11"}],
            }
        }
    )
    assert {"os": "mac", "py": "3.11"} not in combos
    assert len(combos) == 3


def test_matrix_include_adds_entry():
    combos = _expand_matrix(
        {"matrix": {"os": ["linux"], "include": [{"os": "windows", "extra": "x"}]}}
    )
    assert {"os": "windows", "extra": "x"} in combos


def test_matrix_produces_multiple_jobs(tmp_path: Path):
    p = _write_wf(
        tmp_path,
        """
name: Matrix
jobs:
  test:
    strategy:
      matrix:
        py: ['3.11', '3.12']
    steps:
      - run: echo ${{ matrix.py }}
""",
    )
    wf = load_workflow(p)
    assert len(wf.jobs) == 2
    assert {j.matrix["py"] for j in wf.jobs} == {"3.11", "3.12"}


def test_invalid_yaml_raises(tmp_path: Path):
    p = _write_wf(tmp_path, "name: [unclosed\n")
    with pytest.raises(WorkflowError):
        load_workflow(p)


def test_non_mapping_top_level_raises(tmp_path: Path):
    p = _write_wf(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(WorkflowError):
        load_workflow(p)


def test_runs_on_list_joined(tmp_path: Path):
    p = _write_wf(
        tmp_path,
        "name: x\njobs:\n  a:\n    runs-on: [self-hosted, linux]\n    steps:\n      - run: true\n",
    )
    wf = load_workflow(p)
    assert wf.jobs[0].runs_on == "self-hosted, linux"
