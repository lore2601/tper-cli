from __future__ import annotations

import io
import json

import pytest

from tper_cli.output import (
    Printer,
    col,
    print_error,
    project,
    render_table,
    resolve_format,
    sanitize_terminal,
)


class Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_resolve_format() -> None:
    assert resolve_format("json") == "json"
    assert resolve_format("auto", Tty()) == "table"
    assert resolve_format("auto", io.StringIO()) == "json"


def test_sanitize_terminal_removes_escape_sequences() -> None:
    assert sanitize_terminal("ok\x1b[31mred\x1b[0m\x07\x00end") == "okredend"
    assert sanitize_terminal("\x1b]0;title\x07x") == "x"


def test_table_cells_cannot_inject_terminal_codes() -> None:
    out = render_table([{"t": "bad\x1b[2Jtext"}], [col("t", "t")])
    assert "\x1b" not in out


def test_project_dotted_paths() -> None:
    item = {"a": 1, "b": {"c": 2, "d": 3}}
    assert project(item, ["a", "b.c"]) == {"a": 1, "b": {"c": 2}}
    assert project(item, []) == item
    assert project(item, ["zzz"]) == {}


def test_table_shrinks_and_truncates() -> None:
    out = render_table([{"t": "x" * 200}], [col("title", "t", 20)])
    assert out.splitlines()[1].endswith("…") and len(out.splitlines()[1]) == 20
    assert render_table([], [col("t", "t")]) == "(no results)"


def test_lists_are_shown_as_text_in_tables() -> None:
    out = render_table(
        [{"r": ["a", "b"], "e": [], "f": True}], [col("r", "r"), col("e", "e"), col("f", "f")]
    )
    assert "a, b" in out and "yes" in out


def test_json_list_has_extra_keys_and_pagination_flags() -> None:
    buf = io.StringIO()
    Printer("json", out=buf).items(
        [{"a": 1}], [col("a", "a")], kind="xs", extra={"count": 1}, more=True
    )
    assert json.loads(buf.getvalue()) == {"xs": [{"a": 1}], "truncated": True, "count": 1}


def test_ndjson_is_one_object_per_line() -> None:
    buf = io.StringIO()
    Printer("ndjson", out=buf).items([{"a": 1}, {"a": 2}], [col("a", "a")])
    assert [json.loads(line) for line in buf.getvalue().splitlines()] == [{"a": 1}, {"a": 2}]


def test_table_item_is_key_value() -> None:
    buf = Tty()
    Printer("table", out=buf).item({"name": "x", "n": 3})
    assert "name  x" in buf.getvalue()


def test_errors_are_one_json_line_or_text(capsys: pytest.CaptureFixture[str]) -> None:
    payload = {"error": {"exitCode": 3, "reason": "r", "message": "m", "hint": "h"}}
    print_error(payload, "json")
    assert json.loads(capsys.readouterr().err) == payload
    print_error(payload, "table")
    assert capsys.readouterr().err == "error: m\nhint: h\n"
