import json

from debthawk.config import Config
from debthawk.report import (
    render_csv,
    render_json,
    render_markdown,
    render_terminal,
    score_findings,
    summarize,
)
from debthawk.scanner import Finding


def _finding(tag="TODO", weight=2, age_days=None, author=None, path="a.py", line=1, msg="x"):
    return Finding(
        tag=tag,
        message=msg,
        path=path,
        line=line,
        raw=f"# {tag}: {msg}",
        weight=weight,
        author=author,
        age_days=age_days,
    )


def test_scoring_fresh_vs_stale():
    cfg = Config(stale_days=180, stale_multiplier=2.0)
    fresh = _finding(weight=5, age_days=10)
    stale = _finding(weight=5, age_days=400)
    scored = score_findings([fresh, stale], cfg)
    by_age = {f.age_days: f for f in scored}
    assert by_age[10].score == 5.0
    assert by_age[10].stale is False
    assert by_age[400].score == 10.0
    assert by_age[400].stale is True


def test_scoring_sorts_by_score_desc():
    cfg = Config()
    findings = [_finding(weight=1, line=1), _finding(weight=5, line=2)]
    scored = score_findings(findings, cfg)
    assert scored[0].weight == 5


def test_summarize_counts():
    cfg = Config(stale_days=180)
    findings = score_findings(
        [
            _finding(tag="TODO", weight=2, author="alice", age_days=10),
            _finding(tag="FIXME", weight=5, author="bob", age_days=400),
            _finding(tag="TODO", weight=2, author="alice", age_days=5),
        ],
        cfg,
    )
    s = summarize(findings)
    assert s.total == 3
    assert s.stale == 1
    assert s.by_tag == {"TODO": 2, "FIXME": 1}
    assert s.by_author == {"alice": 2, "bob": 1}


def test_render_json_roundtrip():
    cfg = Config()
    findings = score_findings([_finding(author="alice", age_days=3)], cfg)
    s = summarize(findings)
    payload = json.loads(render_json(findings, s))
    assert payload["summary"]["total"] == 1
    assert payload["findings"][0]["author"] == "alice"
    assert payload["findings"][0]["tag"] == "TODO"


def test_render_csv_has_header_and_row():
    cfg = Config()
    findings = score_findings([_finding(msg="hello")], cfg)
    out = render_csv(findings)
    lines = out.splitlines()
    assert lines[0].startswith("tag,score,stale")
    assert "hello" in lines[1]


def test_render_markdown_structure():
    cfg = Config()
    findings = score_findings([_finding(msg="do it")], cfg)
    s = summarize(findings)
    md = render_markdown(findings, s)
    assert "# Technical Debt Report" in md
    assert "do it" in md
    assert "Total findings:" in md


def test_render_markdown_escapes_pipes():
    cfg = Config()
    findings = score_findings([_finding(msg="a | b")], cfg)
    s = summarize(findings)
    md = render_markdown(findings, s)
    assert "a \\| b" in md


def test_render_terminal_empty():
    out = render_terminal([], summarize([]), color=False)
    assert "No technical debt" in out


def test_render_terminal_no_color_has_no_escapes():
    cfg = Config()
    findings = score_findings([_finding(author="alice", age_days=400)], cfg)
    s = summarize(findings)
    out = render_terminal(findings, s, color=False)
    assert "\033[" not in out
    assert "STALE" in out
