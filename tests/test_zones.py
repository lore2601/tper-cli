from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import responses

from tper_cli.data.catalog import Catalog
from tper_cli.data.opendata import OpenDataStore
from tper_cli.errors import AmbiguousError, NotFoundError, UpstreamError
from tper_cli.http import Http
from tper_cli.zones import URL, ZoneCalculator, match_key, pick_place

from .conftest import NOW

NAMES = [
    "BOLOGNA",
    "FERRARA",
    "IMOLA",
    "SAN GIOVANNI IN PERSICETO",
    "SAN GIORGIO DI PIANO",
    "ZOLA PREDOSA",
]


def calculator_page(result: str | None = None) -> str:
    items = "".join(f'<li class="rcbItem">{n}</li>' for n in ["", *NAMES])
    label = (
        f'<span id="ContentPlaceHolderMain_lblZoneAttraversate">{result}</span>'
        if result is not None
        else ""
    )
    return f"""<html><body><form method="post" action="./zone-calculator.aspx" id="wfrmSite">
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="VS">
<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="EV">
<input type="radio" name="ctl00$ContentPlaceHolderMain$rbtlstTipoCalcolo" value="G" checked>
<input name="ctl00$ContentPlaceHolderMain$cboZonaOrigine" type="text" value="">
<div id="ctl00_ContentPlaceHolderMain_cboZonaOrigine_DropDown"><ul class="rcbList">{items}</ul></div>
<input name="ctl00$ContentPlaceHolderMain$cboZonaDestinazione" type="text" value="">
<input type="submit" name="ctl00$ContentPlaceHolderMain$btCalcola_input" value="Calcola">
{label}</form></body></html>"""


@pytest.fixture
def calc(mock_opendata: responses.RequestsMock, tmp_path: Path) -> ZoneCalculator:
    catalog = Catalog(OpenDataStore(Http(), tmp_path, lambda: NOW))
    return ZoneCalculator(Http(), catalog, tmp_path, lambda: NOW)


def answer(rsps: responses.RequestsMock, counts: dict[frozenset[str], str]) -> list[dict[str, str]]:
    posted: list[dict[str, str]] = []

    def respond(request: Any) -> tuple[int, dict[str, str], str]:
        from urllib.parse import parse_qsl

        form = dict(parse_qsl(request.body, keep_blank_values=True))
        posted.append(form)
        pair = frozenset(
            (
                form["ctl00$ContentPlaceHolderMain$cboZonaOrigine"],
                form["ctl00$ContentPlaceHolderMain$cboZonaDestinazione"],
            )
        )
        return 200, {}, calculator_page(counts.get(pair, ""))

    rsps.add(responses.GET, URL, body=calculator_page())
    rsps.add_callback(responses.POST, URL, callback=respond)
    return posted


def test_match_key_ignores_abbreviations_and_small_words() -> None:
    assert match_key("SAN GIOVANNI IN PERSICETO") == match_key("S.GIOVANNI PERSICETO")
    assert match_key("Sant'Agata") == "sant agata"


def test_pick_place_resolves_clear_matches() -> None:
    assert pick_place(NAMES, "bologna") == "BOLOGNA"
    assert pick_place(NAMES, "zola") == "ZOLA PREDOSA"
    assert pick_place(NAMES, "San Giovanni in Persiceto") == "SAN GIOVANNI IN PERSICETO"


def test_pick_place_lists_candidates_when_unsure() -> None:
    with pytest.raises(AmbiguousError) as err:
        pick_place(NAMES, "san gio")
    assert len(err.value.to_dict()["error"]["candidates"]) >= 2


def test_pick_place_unknown() -> None:
    with pytest.raises(NotFoundError):
        pick_place(NAMES, "atlantide")


def test_trip_asks_the_calculator_with_the_official_names(
    calc: ZoneCalculator, rsps: responses.RequestsMock
) -> None:
    posted = answer(rsps, {frozenset(("BOLOGNA", "SAN GIOVANNI IN PERSICETO")): "3"})
    trip = calc.trip("bologna", "san giovanni in persiceto")
    assert (trip.zones, trip.source, trip.urban_network) == (3, "calculator", None)
    assert trip.origin.zone == "500"
    assert trip.destination.zone == "553"  # matched to the open data despite the different spelling
    sent = posted[0]
    assert sent["ctl00$ContentPlaceHolderMain$btCalcola_input"] == "Calcola"
    assert sent["__VIEWSTATE"] == "VS" and sent["__EVENTTARGET"] == ""
    state = json.loads(sent["ctl00_ContentPlaceHolderMain_cboZonaOrigine_ClientState"])
    assert state["text"] == "BOLOGNA"


def test_trip_answers_are_cached(calc: ZoneCalculator, rsps: responses.RequestsMock) -> None:
    answer(rsps, {frozenset(("BOLOGNA", "FERRARA")): "5"})
    assert calc.trip("Bologna", "Ferrara").zones == 5
    posts = len([c for c in rsps.calls if c.request.method == "POST"])
    again = calc.trip("Ferrara", "Bologna")  # same trip, other direction
    assert (again.zones, again.source) == (5, "cache")
    assert len([c for c in rsps.calls if c.request.method == "POST"]) == posts


def test_cache_expires(calc: ZoneCalculator, rsps: responses.RequestsMock) -> None:
    answer(rsps, {frozenset(("BOLOGNA", "FERRARA")): "5"})
    calc.trip("Bologna", "Ferrara")
    calc.now = lambda: NOW + timedelta(days=31)
    assert calc.trip("Bologna", "Ferrara").source == "calculator"


def test_same_city_is_urban_and_makes_no_request(
    calc: ZoneCalculator, rsps: responses.RequestsMock
) -> None:
    rsps.add(responses.GET, URL, body=calculator_page())
    trip = calc.trip("Bologna", "bologna")
    assert (trip.zones, trip.urban_network, trip.source) == (None, "bologna", "same-place")
    assert trip.to_dict()["area"] == "urban"
    assert not [c for c in rsps.calls if c.request.method == "POST"]


def test_same_place_outside_the_cities_is_one_zone(
    calc: ZoneCalculator, rsps: responses.RequestsMock
) -> None:
    rsps.add(responses.GET, URL, body=calculator_page())
    assert calc.trip("Zola Predosa", "zola predosa").zones == 1


def test_an_empty_answer_is_reported_with_a_way_out(
    calc: ZoneCalculator, rsps: responses.RequestsMock
) -> None:
    answer(rsps, {})
    with pytest.raises(UpstreamError) as err:
        calc.trip("Bologna", "Ferrara")
    assert "--zones" in (err.value.hint or "")


def test_a_changed_page_is_reported(calc: ZoneCalculator, rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, URL, body="<html><body>maintenance</body></html>")
    with pytest.raises(UpstreamError) as err:
        calc.names()
    assert err.value.reason == "unexpectedResponse"


def test_place_names_are_cached(calc: ZoneCalculator, rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, URL, body=calculator_page())
    assert "IMOLA" in calc.names()
    assert calc.names() == sorted(NAMES)
    assert len(rsps.calls) == 1
