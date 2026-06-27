from pathlib import Path

from debthawk.scanner import ScanConfig, scan, scan_file, _build_pattern, iter_files
from debthawk.tags import DEFAULT_TAGS


def _config(**kw):
    base = dict(tags=dict(DEFAULT_TAGS))
    base.update(kw)
    return ScanConfig(**base)


def test_detects_basic_tags(tmp_path: Path):
    f = tmp_path / "a.py"
    f.write_text(
        "x = 1  # TODO: refactor this\n"
        "# FIXME broken edge case\n"
        "print('no tag here')\n"
    )
    findings = scan(tmp_path, _config())
    tags = {x.tag for x in findings}
    assert tags == {"TODO", "FIXME"}
    todo = next(x for x in findings if x.tag == "TODO")
    assert todo.message == "refactor this"
    assert todo.line == 1


def test_captures_owner_annotation(tmp_path: Path):
    f = tmp_path / "b.js"
    f.write_text("// TODO(alice): wire up handler\n")
    findings = scan(tmp_path, _config())
    assert len(findings) == 1
    assert findings[0].message == "(alice) wire up handler"


def test_case_sensitive_by_default(tmp_path: Path):
    f = tmp_path / "c.txt"
    f.write_text("this is a todo but lowercase\nTODO: real one\n")
    findings = scan(tmp_path, _config())
    assert len(findings) == 1
    assert findings[0].line == 2


def test_case_insensitive_mode(tmp_path: Path):
    f = tmp_path / "c.txt"
    f.write_text("lowercase fixme: please\n")
    findings = scan(tmp_path, _config(case_sensitive=False))
    assert len(findings) == 1
    assert findings[0].tag == "FIXME"


def test_skips_ignored_dirs(tmp_path: Path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("// TODO ignore me\n")
    (tmp_path / "src.js").write_text("// TODO keep me\n")
    findings = scan(tmp_path, _config())
    assert len(findings) == 1
    assert findings[0].path.endswith("src.js")


def test_ignore_globs(tmp_path: Path):
    (tmp_path / "keep.py").write_text("# TODO keep\n")
    (tmp_path / "skip.py").write_text("# TODO skip\n")
    findings = scan(tmp_path, _config(ignore_globs=["skip.py"]))
    assert len(findings) == 1
    assert findings[0].path.endswith("keep.py")


def test_skips_binary_files(tmp_path: Path):
    binp = tmp_path / "data.bin"
    binp.write_bytes(b"TODO: not real\x00\x01\x02binary")
    findings = scan(tmp_path, _config())
    assert findings == []


def test_skips_large_files(tmp_path: Path):
    big = tmp_path / "big.txt"
    big.write_text("# TODO big\n" + ("x" * 5000))
    findings = scan(tmp_path, _config(max_file_bytes=100))
    assert findings == []


def test_weights_assigned(tmp_path: Path):
    f = tmp_path / "w.py"
    f.write_text("# FIXME critical\n# NOTE minor\n")
    findings = {x.tag: x for x in scan(tmp_path, _config())}
    assert findings["FIXME"].weight == DEFAULT_TAGS["FIXME"]
    assert findings["NOTE"].weight == DEFAULT_TAGS["NOTE"]


def test_single_file_scan(tmp_path: Path):
    f = tmp_path / "one.py"
    f.write_text("# HACK quick fix\n")
    findings = scan(f, _config())
    assert len(findings) == 1
    assert findings[0].tag == "HACK"


def test_pattern_word_boundary(tmp_path: Path):
    f = tmp_path / "wb.py"
    # "TODOLIST" should not match the TODO tag.
    f.write_text("TODOLIST = []\nTODO: yes\n")
    findings = scan(tmp_path, _config())
    assert len(findings) == 1
    assert findings[0].line == 2


def test_results_sorted(tmp_path: Path):
    (tmp_path / "b.py").write_text("# TODO b\n")
    (tmp_path / "a.py").write_text("# TODO a1\n# TODO a2\n")
    findings = scan(tmp_path, _config())
    paths = [(f.path, f.line) for f in findings]
    assert paths == sorted(paths)
