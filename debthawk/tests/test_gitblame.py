import time

from debthawk import gitblame


PORCELAIN = """\
0000000000000000000000000000000000000000 1 1 1
author Alice Example
author-mail <alice@example.com>
author-time 1700000000
author-tz +0000
summary first
\tline one content
1111111111111111111111111111111111111111 2 2 1
author Bob Example
author-time 1600000000
\tline two content
"""


def test_parse_porcelain():
    blame = gitblame._parse_porcelain(PORCELAIN)
    assert blame[1] == ("Alice Example", 1700000000)
    assert blame[2] == ("Bob Example", 1600000000)


def test_is_hex():
    assert gitblame._is_hex("abc123")
    assert not gitblame._is_hex("zzz")


def test_lookup_age_calculation(monkeypatch):
    monkeypatch.setattr(
        gitblame, "_blame_file", lambda p: {1: ("Alice", 1700000000)}
    )
    now = 1700000000 + 86400 * 10
    author, age = gitblame.lookup("whatever.py", 1, now=now)
    assert author == "Alice"
    assert age == 10


def test_lookup_unknown_line(monkeypatch):
    monkeypatch.setattr(gitblame, "_blame_file", lambda p: {})
    assert gitblame.lookup("x.py", 99) == (None, None)
