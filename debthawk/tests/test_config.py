from pathlib import Path

from debthawk.config import from_table, load
from debthawk.tags import DEFAULT_TAGS


def test_defaults():
    cfg = from_table({})
    assert cfg.tags == DEFAULT_TAGS
    assert cfg.blame is True
    assert cfg.case_sensitive is True


def test_tags_dict_overrides_weights():
    cfg = from_table({"tags": {"TODO": 9, "WAT": 7}})
    assert cfg.tags == {"TODO": 9, "WAT": 7}


def test_tags_list_uses_defaults():
    cfg = from_table({"tags": ["TODO", "CUSTOM"]})
    assert cfg.tags["TODO"] == DEFAULT_TAGS["TODO"]
    assert cfg.tags["CUSTOM"] == 1


def test_ignore_and_staleness():
    cfg = from_table({"ignore": ["*.min.js"], "stale_days": 30, "stale_multiplier": 3})
    assert cfg.ignore_globs == ["*.min.js"]
    assert cfg.stale_days == 30
    assert cfg.stale_multiplier == 3.0


def test_load_from_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.debthawk]\nstale_days = 42\nignore = ['build/*']\n"
    )
    cfg = load(tmp_path)
    assert cfg.stale_days == 42
    assert cfg.ignore_globs == ["build/*"]


def test_debthawk_toml_overrides_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.debthawk]\nstale_days = 42\n")
    (tmp_path / "debthawk.toml").write_text("stale_days = 7\n")
    cfg = load(tmp_path)
    assert cfg.stale_days == 7


def test_load_missing_files_returns_defaults(tmp_path: Path):
    cfg = load(tmp_path)
    assert cfg.stale_days == from_table({}).stale_days
