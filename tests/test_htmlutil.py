from __future__ import annotations

from tper_cli.htmlutil import form_fields, parse_html

PAGE = """
<html><body>
<form id="f" method="post">
  <input type="hidden" name="__VIEWSTATE" value="abc&amp;def">
  <input type="text" name="a" value="1">
  <input type="radio" name="r" value="x"><input type="radio" name="r" value="y" checked>
  <input type="checkbox" name="c" value="on"><input type="checkbox" name="d" checked>
  <input type="submit" name="go" value="Go">
  <select name="s"><option value="1">One</option><option value="2" selected>Two</option></select>
  <textarea name="t">hello</textarea>
</form>
<div class="a b" id="x"><p>One <b>two</b></p><p>three<br>four</p><script>var x=1;</script></div>
</body></html>
"""


def test_tree_queries() -> None:
    root = parse_html(PAGE)
    div = root.by_id("x")
    assert div is not None
    assert div.classes == {"a", "b"}
    assert div.text() == "One two three four"
    assert div.paragraphs() == ["One two", "three four"]
    assert root.find("div", cls="a") is div
    assert len(root.find_all("input")) == 7


def test_void_elements_do_not_swallow_following_siblings() -> None:
    root = parse_html("<div><br><span>a</span><img src=x><span>b</span></div>")
    assert [s.text() for s in root.find_all("span")] == ["a", "b"]


def test_form_fields_match_what_a_browser_sends() -> None:
    fields = form_fields(parse_html(PAGE))
    assert fields == {
        "__VIEWSTATE": "abc&def",
        "a": "1",
        "r": "y",
        "d": "on",
        "s": "2",
        "t": "hello",
    }


def test_unclosed_tags_are_tolerated() -> None:
    root = parse_html("<ul><li>one<li>two</ul><p>after")
    assert next(n.text() for n in root.find_all("li")).startswith("one")
    assert root.find("p") is not None
