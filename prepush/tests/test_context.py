import subprocess
from pathlib import Path

from prepush import context


def test_runner_os_and_arch():
    assert context.runner_os() in {"Linux", "macOS", "Windows"}
    assert context.runner_arch()  # non-empty


def test_base_context_shape(tmp_path: Path):
    ctx = context.base_context(tmp_path, {"FOO": "bar"})
    assert ctx["env"] == {"FOO": "bar"}
    assert "github" in ctx and "runner" in ctx
    assert ctx["github"]["workspace"] == str(tmp_path)
    assert ctx["runner"]["os"] in {"Linux", "macOS", "Windows"}


def test_github_context_from_git(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:acme/widget.git"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "f").write_text("x")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=tmp_path, check=True)

    gh = context.build_github_context(tmp_path)
    assert gh["repository"] == "acme/widget"
    assert gh["repository_owner"] == "acme"
    assert len(gh["sha"]) == 40


def test_repo_slug_https(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/foo/bar.git"],
        cwd=tmp_path,
        check=True,
    )
    gh = context.build_github_context(tmp_path)
    assert gh["repository"] == "foo/bar"
