"""TPER news from the official RSS feeds (https://www.tper.it/content/feed-rss)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from defusedxml import ElementTree

from tper_cli.errors import UpstreamError, ValidationError
from tper_cli.htmlutil import parse_html
from tper_cli.http import Http

BASE = "https://www.tper.it"
SERVICE = "tper-news"
FEEDS = {
    "front": "/rss.xml",
    "bologna": "/taxonomy/term/33/all/rss.xml",
    "ferrara": "/taxonomy/term/34/all/rss.xml",
    "rail": "/linee-ferroviarie/rss.xml",
    "corrente": "/taxonomy/term/438/all/rss.xml",
    "parking": "/taxonomy/term/437/all/rss.xml",
}
CATEGORIES = ("all", *FEEDS)
_READ_MORE = re.compile(r"\s*LEGGI TUTTO\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    published: datetime | None
    summary: str
    category: str

    def to_dict(self, *, full: bool = False) -> dict[str, object]:
        data: dict[str, object] = {
            "title": self.title,
            "published": self.published.isoformat() if self.published else None,
            "category": self.category,
            "link": self.link,
        }
        if full or len(self.summary) <= 280:
            data["summary"] = self.summary
        else:
            data["summary"] = self.summary[:279].rstrip() + "…"
        return data


def _parse_date(text: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_feed(xml: bytes, category: str) -> list[NewsItem]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise UpstreamError(
            f"The {category} feed is not valid XML", service=SERVICE, reason="unexpectedResponse"
        ) from exc
    items: list[NewsItem] = []
    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        if not title or not link:
            continue
        summary = parse_html(node.findtext("description") or "").text()
        items.append(
            NewsItem(
                title=title,
                link=link,
                published=_parse_date(node.findtext("pubDate") or ""),
                summary=_READ_MORE.sub("", summary).strip(),
                category=category,
            )
        )
    return items


def mentions_line(item: NewsItem, line: str) -> bool:
    """True when the title or summary refers to ``line`` as a whole word (``11``, ``27A``)."""
    pattern = re.compile(rf"(?<![0-9A-Za-z]){re.escape(line)}(?![0-9A-Za-z])", re.IGNORECASE)
    return bool(pattern.search(item.title) or pattern.search(item.summary))


class NewsFeeds:
    def __init__(self, http: Http) -> None:
        self.http = http

    def fetch(self, category: str) -> list[NewsItem]:
        if category not in FEEDS:
            raise ValidationError(
                f"Unknown news category {category!r}", hint=f"Use one of {', '.join(CATEGORIES)}."
            )
        response = self.http.get(BASE + FEEDS[category], service=SERVICE)
        return parse_feed(response.content, category)

    def latest(
        self,
        category: str = "all",
        *,
        line: str | None = None,
        since: date | None = None,
    ) -> list[NewsItem]:
        """Items of one feed (or every feed, de-duplicated by link), newest first."""
        if category not in CATEGORIES:
            raise ValidationError(
                f"Unknown news category {category!r}", hint=f"Use one of {', '.join(CATEGORIES)}."
            )
        names = [c for c in FEEDS if c != "front"] if category == "all" else [category]
        seen: dict[str, NewsItem] = {}
        for name in names:
            for item in self.fetch(name):
                seen.setdefault(item.link, item)  # the guid of these feeds is not unique
        items = list(seen.values())
        if since:
            items = [i for i in items if i.published and i.published.date() >= since]
        if line:
            items = [i for i in items if mentions_line(i, line)]
        epoch = datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return sorted(items, key=lambda i: i.published or epoch, reverse=True)
