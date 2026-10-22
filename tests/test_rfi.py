from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
import responses

from tper_cli.errors import AmbiguousError, NotFoundError, UpstreamError
from tper_cli.http import Http
from tper_cli.rfi import MONITOR_URL, STATION_URL, STATIONS_URL, Rfi, parse_board, slugify

from .conftest import NOW, fixture_text


def test_slugify_matches_the_rfi_station_urls() -> None:
    assert slugify("Bologna Centrale") == "bologna-centrale"
    assert slugify("Bologna S.Vitale") == "bologna-s-vitale"
    assert slugify("Mondovì") == "mondovi"
    assert slugify("Piano d'Orta Bolognano") == "piano-dorta-bolognano"


def test_parse_board_reads_every_column() -> None:
    board = parse_board(fixture_text("rfi_board.html"), "Bologna Centrale", "departures")
    assert [t.number for t in board.trains] == ["8823", "17709", "9997", "90035"]
    assert board.updated_at is not None and board.updated_at.tzinfo is not None
    tper = board.find("17709")
    assert tper is not None
    assert (tper.carrier, tper.category, tper.place) == ("TRENITALIA TPER", "REG", "PIANORO")
    assert (tper.time, tper.delay, tper.status, tper.platform) == ("19:46", 20, "delayed", "3")
    assert tper.expected == "20:06"
    assert tper.stops[0] == {"station": "BOLOGNA S.VITALE", "time": "19:50"}
    assert tper.stops[-1]["station"] == "PIANORO"
    assert board.find("90035").status == "onTime"  # type: ignore[union-attr]
    assert board.find("1") is None


def test_italo_rows_keep_the_carrier_and_the_information() -> None:
    row = parse_board(fixture_text("rfi_board.html"), "x", "departures").find("9997")
    assert row is not None and row.carrier == "ITALO"
    assert row.info.startswith("CARROZZA 1")


def test_to_dict_names_the_place_by_direction() -> None:
    row = parse_board(fixture_text("rfi_board.html"), "x", "departures").trains[0]
    assert "destination" in row.to_dict("departures") and "origin" not in row.to_dict("departures")
    assert "origin" in row.to_dict("arrivals")


def test_a_cancelled_train_is_flagged() -> None:
    page = fixture_text("rfi_board.html").replace(
        "Fermate successive", "TRENO SOPPRESSO Fermate successive", 1
    )
    assert parse_board(page, "x", "departures").trains[0].status == "cancelled"


def test_an_unrelated_page_is_an_upstream_error() -> None:
    with pytest.raises(UpstreamError) as err:
        parse_board("<html><body>maintenance</body></html>", "x", "departures")
    assert err.value.reason == "unexpectedResponse"


@pytest.fixture
def rfi(rsps: responses.RequestsMock, tmp_path: Path) -> Rfi:
    rsps.add(responses.GET, STATIONS_URL, body=fixture_text("rfi_stations.html"))
    rsps.add(
        responses.GET,
        STATION_URL.format(slug="bologna-centrale"),
        body=fixture_text("rfi_station_page.html"),
    )
    rsps.add(
        responses.GET,
        STATION_URL.format(slug="ferrara"),
        body=fixture_text("rfi_station_page.html").replace("683", "1309"),
    )
    rsps.add(responses.GET, MONITOR_URL, body=fixture_text("rfi_board.html"))
    return Rfi(Http(), tmp_path, lambda: NOW)


def test_station_names_are_cached(rfi: Rfi, rsps: responses.RequestsMock) -> None:
    assert "Mondovì" in rfi.station_names()
    assert rfi.station_names() == sorted(rfi.station_names())
    assert len(rsps.calls) == 1
    rfi.now = lambda: NOW + timedelta(days=31)
    rfi.station_names()
    assert len(rsps.calls) == 2


def test_station_names_missing_from_the_page(rsps: responses.RequestsMock, tmp_path: Path) -> None:
    rsps.add(responses.GET, STATIONS_URL, body="<html/>")
    with pytest.raises(UpstreamError):
        Rfi(Http(), tmp_path, lambda: NOW).station_names()


def test_resolve(rfi: Rfi) -> None:
    assert rfi.resolve("bologna centrale") == "Bologna Centrale"
    assert rfi.resolve("ferrara") == "Ferrara"
    with pytest.raises(AmbiguousError):
        rfi.resolve("reggio")
    with pytest.raises(NotFoundError):
        rfi.resolve("atlantide")


def test_board_requests_the_station_place_id_and_direction(
    rfi: Rfi, rsps: responses.RequestsMock
) -> None:
    board = rfi.board("bologna centrale", arrivals=True)
    assert board.kind == "arrivals" and board.station == "Bologna Centrale"
    monitor = next(c for c in rsps.calls if c.request.url.startswith(MONITOR_URL))
    assert "placeId=683" in monitor.request.url and "arrivals=True" in monitor.request.url


def test_place_ids_and_boards_are_cached(rfi: Rfi, rsps: responses.RequestsMock) -> None:
    rfi.board("Bologna Centrale")
    rfi.board("Bologna Centrale")
    again = Rfi(Http(), rfi.path.parent, lambda: NOW)  # new process: the place id is on disk
    again.board("Bologna Centrale")
    pages = [c for c in rsps.calls if "/it/stazioni/bologna-centrale" in c.request.url]
    assert len(pages) == 1


def test_a_station_page_without_a_board(rfi: Rfi, rsps: responses.RequestsMock) -> None:
    rsps.replace(responses.GET, STATION_URL.format(slug="ferrara"), body="<html>no board</html>")
    with pytest.raises(NotFoundError) as err:
        rfi.board("Ferrara")
    assert err.value.reason == "boardNotAvailable"


def test_track_looks_at_departures_then_arrivals_of_each_station(rfi: Rfi) -> None:
    hit = rfi.track("17709", ["Bologna Centrale", "Ferrara"])
    assert hit is not None and hit[0].kind == "departures" and hit[1].delay == 20
    assert rfi.track("123456", ["Bologna Centrale"]) is None
