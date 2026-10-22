"""A tiny HTML tree built on the standard library.

Enough for what the CLI parses (the Trenitalia notices page and the ASP.NET
forms of solweb.tper.it) without pulling in a third-party HTML parser.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from html.parser import HTMLParser

VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
SKIP_TEXT = {"script", "style"}
_SPACES = re.compile(r"\s+")


class Node:
    """An element, or a text node when ``tag`` is ``"#text"``."""

    __slots__ = ("attrs", "children", "parent", "tag", "value")

    def __init__(
        self, tag: str, attrs: dict[str, str] | None = None, parent: Node | None = None
    ) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[Node] = []
        self.parent = parent
        self.value = ""

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def get(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    def walk(self) -> Iterator[Node]:
        for child in self.children:
            if child.tag != "#text":
                yield child
                yield from child.walk()

    def find_all(
        self,
        tag: str | None = None,
        *,
        cls: str | None = None,
        where: Callable[[Node], bool] | None = None,
    ) -> list[Node]:
        return [
            n
            for n in self.walk()
            if (tag is None or n.tag == tag)
            and (cls is None or cls in n.classes)
            and (where is None or where(n))
        ]

    def find(
        self,
        tag: str | None = None,
        *,
        cls: str | None = None,
        where: Callable[[Node], bool] | None = None,
    ) -> Node | None:
        found = self.find_all(tag, cls=cls, where=where)
        return found[0] if found else None

    def by_id(self, element_id: str) -> Node | None:
        return self.find(where=lambda n: n.attrs.get("id") == element_id)

    def text(self, sep: str = " ") -> str:
        """Visible text with collapsed whitespace."""
        parts: list[str] = []

        def visit(node: Node) -> None:
            for child in node.children:
                if child.tag == "#text":
                    parts.append(child.value)
                elif child.tag not in SKIP_TEXT:
                    visit(child)

        visit(self)
        return _SPACES.sub(" ", sep.join(parts)).strip()

    def paragraphs(self) -> list[str]:
        """Text of each ``<p>``/``<li>`` block, in order, skipping empty ones."""
        blocks = [n.text() for n in self.walk() if n.tag in {"p", "li"}]
        return [b for b in blocks if b]


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.children.append(node)

    def handle_endtag(self, tag: str) -> None:
        node: Node | None = self.cur
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.cur = node.parent

    def handle_data(self, data: str) -> None:
        text = Node("#text", parent=self.cur)
        text.value = data
        self.cur.children.append(text)


def parse_html(markup: str) -> Node:
    builder = _Builder()
    builder.feed(markup)
    builder.close()
    return builder.root


def form_fields(root: Node, form_id: str | None = None) -> dict[str, str]:
    """Default values of the successful controls of a form, like a browser would send."""
    form = root.find("form", where=(lambda n: n.attrs.get("id") == form_id) if form_id else None)
    scope = form or root
    fields: dict[str, str] = {}
    for node in scope.find_all("input"):
        name = node.get("name")
        kind = node.get("type", "text").lower()
        if not name or kind in {"submit", "button", "image", "reset", "file"}:
            continue
        if kind in {"radio", "checkbox"}:
            if "checked" in node.attrs:
                fields[name] = node.get("value", "on")
            continue
        fields[name] = node.get("value", "")
    for node in scope.find_all("select"):
        name = node.get("name")
        if not name:
            continue
        options = node.find_all("option")
        chosen = next(
            (o for o in options if "selected" in o.attrs), options[0] if options else None
        )
        if chosen is not None:
            fields[name] = chosen.get("value", chosen.text())
    for node in scope.find_all("textarea"):
        if node.get("name"):
            fields[node.get("name")] = node.text()
    return fields
