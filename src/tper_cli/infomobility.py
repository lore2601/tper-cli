"""Rail disruption notices from the public Trenitalia "Notizie Infomobilità" page."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from tper_cli import search
from tper_cli.errors import UpstreamError
from tper_cli.htmlutil import Node, parse_html
from tper_cli.http import Http

URL = "https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.app.html"
SERVICE = "trenitalia-infomobility"
DEFAULT_REGION = "emilia-romagna"
_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_WORKS = re.compile(r"^INFOLAVORI\s+(?P<region>.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class Notice:
    title: str
    published: date | None
    category: str
    regions: list[str]
    featured: bool
    body: list[str] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)

    @property
    def national(self) -> bool:
        """Not tied to any region (network-wide information, or untagged)."""
        return not self.regions

    @property
    def kind(self) -> str:
        return "works" if _WORKS.match(self.title) else "notice"

    def to_dict(self, *, full: bool = False) -> dict[str, object]:
        data: dict[str, object] = {
            "title": self.title,
            "published": self.published.isoformat() if self.published else None,
            "kind": self.kind,
            "category": self.category,
            "regions": self.regions,
            "featured": self.featured,
        }
        if full:
            data["body"] = self.body
            data["links"] = self.links
        else:
            data["summary"] = (self.body[0] if self.body else "")[:280]
        return data


def region_slug(name: str) -> str:
    return search.normalize(name).replace(" ", "-")


def _first(node: Node, cls: str) -> Node | None:
    return node.find(cls=cls)


def parse_notices(markup: str) -> list[Notice]:
    root = parse_html(markup)
    items = root.find_all("div", cls="accordion-item")
    if not items:
        raise UpstreamError(
            "No notices found on the Trenitalia infomobility page",
            service=SERVICE,
            reason="unexpectedResponse",
            hint="Trenitalia may have changed the page. Please report it.",
        )
    notices: list[Notice] = []
    for item in items:
        title_node = _first(item, "infomobility-title")
        if title_node is None:
            continue
        date_node = _first(item, "infomobility-date")
        match = _DATE.search(date_node.text()) if date_node else None
        published = date(int(match[3]), int(match[2]), int(match[1])) if match else None
        category = item.find("span", cls="visually-hidden")
        tags = [t.text() for t in item.find_all("div", cls="tag-category")]
        body_node = item.find(cls="description")
        links = [
            {"text": a.text(), "url": a.get("href")}
            for a in (body_node.find_all("a") if body_node else [])
            if a.get("href")
        ]
        title = title_node.text()
        regions = [r for r in item.get("data-region").split(",") if r and r != "empty"]
        works = _WORKS.match(title)
        if works and region_slug(works.group("region")) not in regions:
            regions.append(region_slug(works.group("region")))
        notices.append(
            Notice(
                title=title,
                published=published,
                category=category.text() if category else "",
                regions=regions,
                featured=any(search.normalize(t) == "in evidenza" for t in tags),
                body=body_node.paragraphs() if body_node else [],
                links=links,
            )
        )
    return notices


def filter_notices(
    notices: list[Notice], region: str | None, *, include_national: bool
) -> list[Notice]:
    if region is None:
        return notices
    wanted = region_slug(region)
    return [n for n in notices if wanted in n.regions or (include_national and n.national)]


class Infomobility:
    def __init__(self, http: Http) -> None:
        self.http = http

    def notices(self) -> list[Notice]:
        return parse_notices(self.http.get(URL, service=SERVICE).text)


def stamp(now: datetime) -> str:
    return now.isoformat(timespec="minutes")
