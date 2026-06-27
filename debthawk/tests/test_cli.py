import json
import subprocess
from pathlib import Path

import pytest

from debthawk.cli import run


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text(
        "# TODO: add tests\n"
        "def f():\n"
        "    pass  # FIXME handle errors\n"
    )
    (tmp_path / "util.py").write_text("# HACK temporary shim\n")
    return tmp_path


def test_run_terminal(sample_tree, capsys):
    code = run([str(sample_tree), "--no-blame", "--no-color"])
    out = capsys.readouterr().out
    assert code == 0
    assert "TODO" in out and "FIXME" in out and "HACK" in out
    assert "3 findings" in out


def test_run_json(sample_tree, capsys):
    code = run([str(sample_tree), "--no-blame", "--format", "json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert data["summary"]["total"] == 3


def test_max_debt_gate(sample_tree, capsys):
    code = run([str(sample_tree), "--no-blame", "--max-debt", "2"])
    assert code == 1
    code_ok = run([str(sample_tree), "--no-blame", "--max-debt", "5"])
    assert code_ok == 0


def test_max_score_gate(sample_tree, capsys):
    # FIXME(5) + TODO(2) + HACK(3) = 10
    assert run([str(sample_tree), "--no-blame", "--max-score", "9"]) == 1
    assert run([str(sample_tree), "--no-blame", "--max-score", "10"]) == 0


def test_tag_filter(sample_tree, capsys):
    code = run([str(sample_tree), "--no-blame", "--tag", "TODO", "--format", "json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["summary"]["total"] == 1
    assert data["findings"][0]["tag"] == "TODO"


def test_custom_tag_weight(sample_tree, capsys):
    (sample_tree / "x.py").write_text("# WAT: huh\n")
    code = run(
        [str(sample_tree), "--no-blame", "--tag", "WAT=8", "--format", "json"]
    )
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["findings"][0]["weight"] == 8


def test_missing_path():
    assert run(["/nonexistent/path/xyz"]) == 2


def test_fail_on_stale_without_blame(sample_tree):
    # Without blame there is no age data, so nothing is stale.
    assert run([str(sample_tree), "--no-blame", "--fail-on-stale"]) == 0


def test_blame_enrichment_real_repo(tmp_path: Path, capsys):
    # Build a real git repo so blame produces author/age data.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, check=True)
    f = tmp_path / "main.py"
    f.write_text("# TODO: blame me\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)

    code = run([str(tmp_path), "--format", "json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 0
    finding = data["findings"][0]
    assert finding["author"] == "Tester"
    assert finding["age_days"] is not None
