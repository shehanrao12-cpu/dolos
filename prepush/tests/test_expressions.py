from prepush import expressions as E


CTX = {
    "env": {"FOO": "bar", "COUNT": "3"},
    "github": {"ref_name": "main", "sha": "abc123"},
    "matrix": {"os": "ubuntu-latest", "python": "3.12"},
    "runner": {"os": "Linux"},
    "secrets": {"TOKEN": "s3cret"},
}


def test_literal_string_and_number():
    assert E.evaluate("'hello'", CTX) == "hello"
    assert E.evaluate("42", CTX) == 42


def test_context_lookup():
    assert E.evaluate("env.FOO", CTX) == "bar"
    assert E.evaluate("github.ref_name", CTX) == "main"
    assert E.evaluate("matrix.python", CTX) == "3.12"


def test_missing_lookup_is_empty():
    assert E.evaluate("env.NOPE", CTX) == ""
    assert E.evaluate("nothing.here.deep", CTX) == ""


def test_equality_and_inequality():
    assert E.evaluate("env.FOO == 'bar'", CTX) is True
    assert E.evaluate("env.FOO != 'baz'", CTX) is True
    assert E.evaluate("runner.os == 'Windows'", CTX) is False


def test_logical_and_or_not():
    assert E.evaluate("runner.os == 'Linux' && env.FOO == 'bar'", CTX) is True
    assert E.evaluate("runner.os == 'Windows' || env.FOO == 'bar'", CTX) is True
    assert E.evaluate("!(runner.os == 'Windows')", CTX) is True


def test_loose_number_string_equality():
    assert E.evaluate("env.COUNT == '3'", CTX) is True
    assert E.evaluate("3 == '3'", CTX) is True


def test_functions():
    assert E.evaluate("contains('ubuntu-latest', 'ubuntu')", CTX) is True
    assert E.evaluate("startsWith('refs/heads/main', 'refs/')", CTX) is True
    assert E.evaluate("endsWith('main.py', '.py')", CTX) is True
    assert E.evaluate("format('{0}-{1}', 'a', 'b')", CTX) == "a-b"
    assert E.evaluate("join(matrix.os, '/')", {"matrix": {"os": ["a", "b"]}}) == "a/b"


def test_status_functions():
    E.set_job_status("success")
    assert E.evaluate("success()", CTX) is True
    assert E.evaluate("failure()", CTX) is False
    assert E.evaluate("always()", CTX) is True
    E.set_job_status("failure")
    assert E.evaluate("success()", CTX) is False
    assert E.evaluate("failure()", CTX) is True
    E.set_job_status("success")


def test_expand_interpolation():
    assert E.expand("v=${{ env.FOO }}", CTX) == "v=bar"
    assert E.expand("${{ matrix.os }}-${{ matrix.python }}", CTX) == "ubuntu-latest-3.12"
    assert E.expand("no expressions here", CTX) == "no expressions here"


def test_expand_booleans_lowercased():
    assert E.expand("${{ true }}", CTX) == "true"
    assert E.expand("${{ env.FOO == 'bar' }}", CTX) == "true"


def test_evaluate_condition():
    assert E.evaluate_condition(None, CTX) is True
    assert E.evaluate_condition("", CTX) is True
    assert E.evaluate_condition("runner.os == 'Linux'", CTX) is True
    assert E.evaluate_condition("${{ runner.os == 'Windows' }}", CTX) is False
    assert E.evaluate_condition(True, CTX) is True
    assert E.evaluate_condition(False, CTX) is False


def test_resilient_to_garbage():
    # Should not raise on unsupported syntax.
    assert E.evaluate("@#$%", CTX) == ""
