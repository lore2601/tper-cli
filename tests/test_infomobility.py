from __future__ import annotations

from datetime import date

import pytest
import responses

from tper_cli.errors import UpstreamError
from tper_cli.http import Http
from tper_cli.infomobility import URL, Infomobility, filter_notices, parse_notices, region_slug

from .conftest import fixture_text


def test_parse_notices() -> None:
    notices = parse_notices(fixture_text("infomobility.html"))
    assert len(notices) == 4
    campania = notices[0]
    assert campania.published == date(2026, 10, 22)
    assert campania.regions == ["campania", "lazio"]
    assert campania.featured is True
    assert campania.category.lower() == "attenzione"
    assert campania.body and campania.links


def test_regions_come_from_the_tag_or_from_the_works_title() -> None:
    notices = {n.title: n for n in parse_notices(fixture_text("infomobility.html"))}
    works = notices["INFOLAVORI EMILIA-ROMAGNA"]
    assert works.regions == ["emilia-romagna"]
    assert works.kind == "works"
    untagged = next(n for n in notices.values() if n.national)
    assert untagged.regions == [] and untagged.kind == "notice"


def test_filter_by_region_with_and_without_national() -> None:
    notices = parse_notices(fixture_text("infomobility.html"))
    er = filter_notices(notices, "Emilia Romagna", include_national=False)
    assert [n.title for n in er] == ["INFOLAVORI EMILIA-ROMAGNA"]
    with_national = filter_notices(notices, "emilia-romagna", include_national=True)
    assert len(with_national) == 2
    assert filter_notices(notices, None, include_national=False) == notices


def test_region_slug() -> None:
    assert region_slug("Emilia Romagna") == "emilia-romagna"
    assert region_slug("Friuli Venezia Giulia") == "friuli-venezia-giulia"


def test_compact_and_full_views() -> None:
    notice = parse_notices(fixture_text("infomobility.html"))[0]
    compact = notice.to_dict()
    assert "body" not in compact and len(str(compact["summary"])) <= 280
    full = notice.to_dict(full=True)
    assert full["body"] and full["links"]


def test_a_page_without_notices_is_reported() -> None:
    with pytest.raises(UpstreamError) as err:
        parse_notices("<html><body>maintenance</body></html>")
    assert err.value.reason == "unexpectedResponse"


def test_client(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, URL, body=fixture_text("infomobility.html"))
    assert len(Infomobility(Http()).notices()) == 4
