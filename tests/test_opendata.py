from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
import responses

from tper_cli.data.catalog import Catalog, haversine_m, to_float
from tper_cli.data.opendata import DATASETS, OpenDataStore, parse_csv
from tper_cli.errors import SetupError, UpstreamError
from tper_cli.http import Http

from .conftest import NOW


def store(tmp_path: Path, **kwargs: object) -> OpenDataStore:
    return OpenDataStore(Http(), tmp_path, lambda: NOW, warn=lambda _m: None, **kwargs)  # type: ignore[arg-type]


def test_parse_csv_handles_bom_cp1252_and_crlf() -> None:
    raw = "codice;nome\r\n1;Caffè\r\n".encode("cp1252")
    assert parse_csv(raw) == [{"codice": "1", "nome": "Caffè"}]
    assert parse_csv(b"\xef\xbb\xbfa;b\n1;2\n") == [{"a": "1", "b": "2"}]


def test_to_float_understands_decimal_commas() -> None:
    assert to_float("44,505762") == pytest.approx(44.505762)
    assert to_float("44.8582") == pytest.approx(44.8582)
    assert to_float("") is None
    assert to_float("n/a") is None


def test_haversine() -> None:
    assert haversine_m(44.5, 11.3, 44.5, 11.3) == 0
    assert 110_000 < haversine_m(44.0, 11.0, 45.0, 11.0) < 112_000


def test_discover_lists_versions(mock_opendata: responses.RequestsMock, tmp_path: Path) -> None:
    versions = store(tmp_path).discover()
    assert set(DATASETS) <= set(versions)
    assert "opendata-versione" not in versions


def test_discover_fails_loudly_when_the_page_changes(
    rsps: responses.RequestsMock, tmp_path: Path
) -> None:
    rsps.add(
        responses.GET, "https://solweb.tper.it/web/tools/open-data/open-data.aspx", body="<html/>"
    )
    with pytest.raises(UpstreamError) as err:
        store(tmp_path).discover()
    assert err.value.reason == "unexpectedResponse"


def test_table_downloads_once_then_uses_the_cache(
    mock_opendata: responses.RequestsMock, tmp_path: Path
) -> None:
    s = store(tmp_path)
    rows = s.table("fermate")
    assert any(r["codice"] == "4476" for r in rows)
    calls = len(mock_opendata.calls)
    again = store(tmp_path).table("fermate")  # a new process
    assert again == rows
    assert len(mock_opendata.calls) == calls


def test_stale_cache_checks_for_a_new_version(
    mock_opendata: responses.RequestsMock, tmp_path: Path
) -> None:
    store(tmp_path).table("linee")
    later = OpenDataStore(Http(), tmp_path, lambda: NOW + timedelta(days=8), warn=lambda _m: None)
    before = len(mock_opendata.calls)
    later.table("linee")
    assert len(mock_opendata.calls) == before + 1  # only the index page: same version, no download


def test_new_version_replaces_the_old_file(
    mock_opendata: responses.RequestsMock, tmp_path: Path
) -> None:
    s = store(tmp_path)
    s.table("linee")
    old = next((tmp_path / "opendata").glob("linee_*.csv"))
    manifest = s._manifest()
    manifest["datasets"]["linee"]["version"] = "19990101"
    old.rename(old.with_name("linee_19990101.csv"))
    s._save_manifest(manifest)
    s.update(["linee"])
    files = sorted(p.name for p in (tmp_path / "opendata").glob("linee_*.csv"))
    assert files == [old.name]


def test_offline_with_a_cache_uses_it_and_warns(
    mock_opendata: responses.RequestsMock, rsps: responses.RequestsMock, tmp_path: Path
) -> None:
    store(tmp_path).table("linee")
    warnings: list[str] = []
    stale = OpenDataStore(
        Http(retries=0), tmp_path, lambda: NOW + timedelta(days=30), warn=warnings.append
    )
    mock_opendata.replace(
        responses.GET, "https://solweb.tper.it/web/tools/open-data/open-data.aspx", status=503
    )
    assert stale.table("linee")
    assert warnings and "cached data" in warnings[0]


def test_offline_without_a_cache_is_a_setup_error(
    rsps: responses.RequestsMock, tmp_path: Path
) -> None:
    rsps.add(responses.GET, "https://solweb.tper.it/web/tools/open-data/open-data.aspx", status=503)
    with pytest.raises(SetupError) as err:
        OpenDataStore(Http(retries=0), tmp_path, lambda: NOW).table("fermate")
    assert err.value.reason == "openDataUnavailable"
    assert err.value.exit_code == 2


def test_html_instead_of_csv_is_refused(
    mock_opendata: responses.RequestsMock, tmp_path: Path
) -> None:
    with pytest.raises(UpstreamError) as err:
        store(tmp_path)._download("archi", "1")  # no fixture file: the mock answers with HTML
    assert err.value.reason == "unexpectedResponse"


def test_unknown_dataset(tmp_path: Path) -> None:
    with pytest.raises(SetupError):
        store(tmp_path).table("nope")


def test_status_and_clear(mock_opendata: responses.RequestsMock, tmp_path: Path) -> None:
    s = store(tmp_path)
    assert not any(r["cached"] for r in s.status())
    s.table("linee")
    assert [r["dataset"] for r in s.status() if r["cached"]] == ["linee"]
    assert s.clear() >= 2
    assert not any(r["cached"] for r in s.status())


def test_cached_never_touches_the_network(rsps: responses.RequestsMock, tmp_path: Path) -> None:
    assert store(tmp_path).cached("fermate") is None
    assert len(rsps.calls) == 0


def test_catalog_stops_lines_and_search(
    mock_opendata: responses.RequestsMock, tmp_path: Path
) -> None:
    catalog = Catalog(store(tmp_path))
    stop = catalog.stops_by_code["4476"]
    assert (stop.name, stop.municipality, stop.zone) == ("LAPIDARI", "BOLOGNA", "500")
    assert stop.lat == pytest.approx(44.536433)
    assert catalog.lines_at_stop("4476") == ["11"]
    assert [s.code for s in catalog.stops_of_line("11")]
    assert catalog.search_stops("lapidari")[0][1].name == "LAPIDARI"
    assert catalog.search_stops("lapidari", municipality="Ferrara") == []
    near = catalog.stops_near(44.5364, 11.3502, 100)
    assert near and near[0][1].code in {"4475", "4476"}
    assert catalog.stop_if_cached("4476") is not None
    assert catalog.stop_if_cached("1234567") is None


def test_catalog_zones_localities_stations_retailers(
    mock_opendata: responses.RequestsMock, tmp_path: Path
) -> None:
    catalog = Catalog(store(tmp_path))
    assert catalog.zones["500"].name == "BOLOGNA"
    assert any(loc.zone == "553" for loc in catalog.localities)
    assert any(s.name == "BOLOGNA CENTRALE" for s in catalog.stations)
    assert {line["abbreviation"] for line in catalog.rail_lines} >= {"BOPOR", "BOVIG"}
    retailer = catalog.retailers[0]
    assert retailer.lat is not None and retailer.to_dict()["code"]
    assert "11" in catalog.line_codes
