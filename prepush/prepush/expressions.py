"""A pragmatic evaluator for the GitHub Actions expression subset.

GitHub Actions interpolates ``${{ <expression> }}`` against a set of *contexts*
(``github``, ``env``, ``matrix``, ``runner``, ``secrets``, ``vars``, ``job``,
``steps``, ``strategy``). This module implements the commonly used subset of
that language: context lookups, string/number/boolean/null literals, the
logical/comparison operators, and the most common built-in functions.

Unsupported constructs degrade gracefully (to an empty string / ``False``)
rather than raising, which suits prepush's goal of a *best-effort, fast* local
preview rather than a perfect reimplementation of GitHub's runner.
"""

from __future__ import annotations

import json
import re
from typing import Any

_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<string>'(?:[^']|'')*')          # single-quoted string ('' escapes ')
      | (?P<number>-?\d+(?:\.\d+)?)
      | (?P<op><=|>=|==|!=|&&|\|\||[()!,<>.\[\]])
      | (?P<ident>[A-Za-z_][A-Za-z0-9_-]*)
    )
    """,
    re.VERBOSE,
)

_KEYWORDS = {"true": True, "false": False, "null": None}


class _Tok:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: Any) -> None:
        self.kind = kind
        self.value = value


def _tokenize(expr: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    pos = 0
    while pos < len(expr):
        if expr[pos].isspace():
            pos += 1
            continue
        m = _TOKEN_RE.match(expr, pos)
        if not m or m.end() == pos:
            # Unknown character; skip it to stay resilient.
            pos += 1
            continue
        pos = m.end()
        if m.group("string") is not None:
            raw = m.group("string")[1:-1].replace("''", "'")
            tokens.append(_Tok("lit", raw))
        elif m.group("number") is not None:
            num = m.group("number")
            tokens.append(_Tok("lit", float(num) if "." in num else int(num)))
        elif m.group("op") is not None:
            tokens.append(_Tok("op", m.group("op")))
        elif m.group("ident") is not None:
            ident = m.group("ident")
            if ident in _KEYWORDS:
                tokens.append(_Tok("lit", _KEYWORDS[ident]))
            else:
                tokens.append(_Tok("ident", ident))
    tokens.append(_Tok("end", None))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Tok], context: dict[str, Any]) -> None:
        self.tokens = tokens
        self.i = 0
        self.context = context

    def _peek(self) -> _Tok:
        if self.i >= len(self.tokens):
            return self.tokens[-1]  # the sentinel "end" token
        return self.tokens[self.i]

    def _next(self) -> _Tok:
        tok = self._peek()
        if self.i < len(self.tokens) - 1:
            self.i += 1
        return tok

    def _accept(self, value: str) -> bool:
        tok = self._peek()
        if tok.kind == "op" and tok.value == value:
            self.i += 1
            return True
        return False

    # precedence: or -> and -> comparison -> unary -> primary
    def parse(self) -> Any:
        return self._parse_or()

    def _parse_or(self) -> Any:
        left = self._parse_and()
        while self._accept("||"):
            right = self._parse_and()
            left = left if _truthy(left) else right
        return left

    def _parse_and(self) -> Any:
        left = self._parse_cmp()
        while self._accept("&&"):
            right = self._parse_cmp()
            left = right if _truthy(left) else left
        return left

    def _parse_cmp(self) -> Any:
        left = self._parse_unary()
        tok = self._peek()
        if tok.kind == "op" and tok.value in {"==", "!=", "<", "<=", ">", ">="}:
            self._next()
            right = self._parse_unary()
            return _compare(tok.value, left, right)
        return left

    def _parse_unary(self) -> Any:
        if self._accept("!"):
            return not _truthy(self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> Any:
        if self._accept("("):
            val = self._parse_or()
            self._accept(")")
            return val
        tok = self._peek()
        if tok.kind == "lit":
            self._next()
            return tok.value
        if tok.kind == "ident":
            return self._parse_ident_chain()
        if tok.kind == "end":
            return ""
        # Unexpected token; consume and yield empty.
        self._next()
        return ""

    def _parse_ident_chain(self) -> Any:
        name = self._next().value
        # Function call?
        if self._peek().kind == "op" and self._peek().value == "(":
            args = self._parse_args()
            return _call_function(name, args)
        # Property access chain: name.prop.prop ...
        path = [name]
        while self._peek().kind == "op" and self._peek().value == ".":
            self._next()
            nxt = self._peek()
            if nxt.kind == "ident":
                path.append(self._next().value)
            else:
                break
        return _resolve(path, self.context)

    def _parse_args(self) -> list[Any]:
        self._accept("(")
        args: list[Any] = []
        if self._peek().kind == "op" and self._peek().value == ")":
            self._next()
            return args
        args.append(self._parse_or())
        while self._accept(","):
            args.append(self._parse_or())
        self._accept(")")
        return args


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value != ""
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def _compare(op: str, left: Any, right: Any) -> bool:
    if op == "==":
        return _loose_eq(left, right)
    if op == "!=":
        return not _loose_eq(left, right)
    try:
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
    except TypeError:
        return False
    return False


def _loose_eq(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return _truthy(left) == _truthy(right)
    if isinstance(left, (int, float)) and isinstance(right, str):
        return str(left) == right
    if isinstance(right, (int, float)) and isinstance(left, str):
        return str(right) == left
    return left == right


def _resolve(path: list[str], context: dict[str, Any]) -> Any:
    cur: Any = context
    for part in path:
        if isinstance(cur, dict):
            # Context keys are case-insensitive in practice for env/matrix.
            if part in cur:
                cur = cur[part]
            else:
                lowered = {k.lower(): v for k, v in cur.items()}
                cur = lowered.get(part.lower(), "")
        else:
            return ""
    return cur


def _call_function(name: str, args: list[Any]) -> Any:
    fn = name.lower()
    if fn == "success":
        return _STATE.get("job_status", "success") == "success"
    if fn == "failure":
        return _STATE.get("job_status", "success") == "failure"
    if fn == "cancelled":
        return _STATE.get("job_status", "success") == "cancelled"
    if fn == "always":
        return True
    if fn == "contains":
        if len(args) >= 2:
            return str(args[1]) in str(args[0])
        return False
    if fn == "startswith":
        return len(args) >= 2 and str(args[0]).startswith(str(args[1]))
    if fn == "endswith":
        return len(args) >= 2 and str(args[0]).endswith(str(args[1]))
    if fn == "format":
        if not args:
            return ""
        template = str(args[0])
        for idx, value in enumerate(args[1:]):
            template = template.replace("{" + str(idx) + "}", _stringify(value))
        return template
    if fn == "join":
        if not args:
            return ""
        arr = args[0] if isinstance(args[0], list) else [args[0]]
        sep = str(args[1]) if len(args) > 1 else ","
        return sep.join(_stringify(x) for x in arr)
    if fn == "tojson":
        try:
            return json.dumps(args[0] if args else None)
        except (TypeError, ValueError):
            return "null"
    if fn == "fromjson":
        try:
            return json.loads(str(args[0])) if args else None
        except (TypeError, ValueError):
            return ""
    if fn == "hashfiles":
        # Not meaningful for a local dry-run; return a stable placeholder.
        return ""
    return ""


# Module-level state for status functions (success()/failure()), set per step.
_STATE: dict[str, str] = {"job_status": "success"}


def set_job_status(status: str) -> None:
    """Set the status used by ``success()`` / ``failure()`` / ``cancelled()``."""
    _STATE["job_status"] = status


def _stringify(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    return str(value)


def evaluate(expr: str, context: dict[str, Any]) -> Any:
    """Evaluate a single expression (no surrounding ``${{ }}``)."""
    tokens = _tokenize(expr.strip())
    return _Parser(tokens, context).parse()


_INTERP_RE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)


def expand(text: str, context: dict[str, Any]) -> str:
    """Interpolate every ``${{ ... }}`` in ``text`` and return a string."""
    if "${{" not in text:
        return text

    def repl(match: re.Match[str]) -> str:
        return _stringify(evaluate(match.group(1), context))

    return _INTERP_RE.sub(repl, text)


def evaluate_condition(expr: str | bool | None, context: dict[str, Any]) -> bool:
    """Evaluate an ``if:`` condition to a boolean.

    GitHub treats a bare ``if`` value as an expression even without ``${{ }}``.
    A missing condition means "run".
    """
    if expr is None:
        return True
    if isinstance(expr, bool):
        return expr
    text = str(expr).strip()
    if not text:
        return True
    # Strip an optional wrapping ${{ ... }} so both styles work.
    m = re.fullmatch(r"\$\{\{(.*)\}\}", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    return _truthy(evaluate(text, context))
