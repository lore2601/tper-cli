from __future__ import annotations

from datetime import date

import pytest
import responses

from tper_cli.errors import UpstreamError, ValidationError
from tper_cli.http import Http
from tper_cli.news import FEEDS, NewsFeeds, mentions_line, parse_feed

from .conftest import FIXTURES, fixture_text

BASE = "https://www.tper.it"


def feed() -> bytes:
    return (FIXTURES / "news_bologna.xml").read_bytes()


def test_parse_feed_extracts_items_and_cleans_the_summary() -> None:
    items = parse_feed(feed(), "bologna")
    assert len(items) == 4
    first = items[0]
    assert first.title.startswith("Martedì 15 settembre")
    assert first.link.startswith("https://www.tper.it/")
    assert first.published is not None and first.published.year == 2026
    assert "<" not in first.summary and "LEGGI TUTTO" not in first.summary
    assert first.to_dict()["category"] == "bologna"


def test_long_summaries_are_shortened_unless_full() -> None:
    item = parse_feed(feed(), "bologna")[0]
    assert len(str(item.to_dict()["summary"])) <= 280
    assert len(str(item.to_dict(full=True)["summary"])) >= len(str(item.to_dict()["summary"]))


def test_invalid_xml_is_an_upstream_error() -> None:
    with pytest.raises(UpstreamError):
        parse_feed(b"<html><p>oops", "bologna")


def test_hostile_xml_entities_are_rejected() -> None:
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><rss><channel>&b;</channel></rss>'
    with pytest.raises(Exception):  # noqa: B017, PT011 - defusedxml raises its own exception types
        parse_feed(bomb, "x")


@pytest.mark.parametrize(
    ("text", "line", "expected"),
    [
        ("Dal 15 settembre è attiva la linea 449", "449", True),
        ("Linee 44 e 449", "44", True),
        ("Linea 4490", "449", False),
        ("Linea 27A deviata", "27A", True),
        ("Linea 27 deviata", "27A", False),
    ],
)
def test_mentions_line_is_a_whole_word_match(text: str, line: str, expected: bool) -> None:
    item = parse_feed(feed(), "bologna")[0]
    item = type(item)(title=text, link="l", published=None, summary="", category="bologna")
    assert mentions_line(item, line) is expected


def test_latest_merges_feeds_dedupes_by_link_and_sorts(rsps: responses.RequestsMock) -> None:
    for name, path in FEEDS.items():
        rsps.add(
            responses.GET,
            BASE + path,
            body=feed() if name in {"bologna", "rail"} else "<rss><channel/></rss>",
        )
    items = NewsFeeds(Http()).latest("all")
    links = [i.link for i in items]
    assert len(links) == len(set(links)) == 4  # bologna and rail returned the same four
    dates = [i.published for i in items if i.published]
    assert dates == sorted(dates, reverse=True)


def test_latest_filters_by_line_and_date(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, BASE + FEEDS["bologna"], body=feed())
    feeds = NewsFeeds(Http())
    assert "449" in next(i.title for i in feeds.latest("bologna", line="449"))
    assert feeds.latest("bologna", since=date(2030, 1, 1)) == []


def test_unknown_category() -> None:
    with pytest.raises(ValidationError):
        NewsFeeds(Http()).latest("nope")
    with pytest.raises(ValidationError):
        NewsFeeds(Http()).fetch("all")


def test_fixture_is_valid_text() -> None:
    assert "<rss" in fixture_text("news_bologna.xml")
