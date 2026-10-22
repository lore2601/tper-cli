"""Contract tests against the real services. Run with: ``uv run pytest -m live``.

They fail when TPER or Trenitalia change something the CLI depends on. The weekly
``upstream`` workflow runs them and opens an issue when they break.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tper_cli.claim import form
from tper_cli.context import rome_now
from tper_cli.data.catalog import Catalog
from tper_cli.data.opendata import DATASETS, OpenDataStore
from tper_cli.hellobus import HelloBus
from tper_cli.http import Http
from tper_cli.infomobility import Infomobility
from tper_cli.news import FEEDS, NewsFeeds
from tper_cli.zones import ZoneCalculator

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def http() -> Http:
    return Http()


@pytest.fixture(scope="module")
def catalog(http: Http, tmp_path_factory: pytest.TempPathFactory) -> Catalog:
    return Catalog(OpenDataStore(http, tmp_path_factory.mktemp("cache"), rome_now))


def test_hellobus_answers_for_a_known_stop(http: Http) -> None:
    reply = HelloBus(http).arrivals("4476")
    assert reply.arrivals or reply.message
    assert reply.unparsed == []


def test_hellobus_still_reports_unknown_stops(http: Http) -> None:
    from tper_cli.errors import NotFoundError

    with pytest.raises(NotFoundError):
        HelloBus(http).arrivals("999999")


def test_every_dataset_we_use_is_still_published(http: Http, tmp_path: Path) -> None:
    published = OpenDataStore(http, tmp_path, rome_now).discover()
    assert set(DATASETS) <= set(published)


def test_open_data_has_the_columns_we_read(catalog: Catalog) -> None:
    stop = catalog.stops_by_code["4476"]
    assert stop.name and stop.lat and stop.zone
    assert catalog.lines_at_stop("4476")
    assert catalog.zones["500"].name == "BOLOGNA"
    assert catalog.stations and catalog.rail_lines and catalog.retailers


def test_every_feed_parses(http: Http) -> None:
    feeds = NewsFeeds(http)
    for name in FEEDS:
        assert isinstance(feeds.fetch(name), list), name
    assert feeds.latest("all")


def test_trenitalia_notices_page_still_has_its_structure(http: Http) -> None:
    notices = Infomobility(http).notices()
    assert len(notices) > 3 and all(n.title for n in notices)


def test_zone_calculator_counts_zones(http: Http, catalog: Catalog, tmp_path: Path) -> None:
    calc = ZoneCalculator(http, catalog, tmp_path, rome_now)
    assert {"BOLOGNA", "FERRARA", "IMOLA"} <= set(calc.names())
    trip = calc.trip("Bologna", "Ferrara")
    assert trip.zones is not None and 1 <= trip.zones <= 10


def test_complaint_form_has_the_controls_we_fill(http: Http) -> None:
    from tper_cli.commands.claim import REQUIRED_CONTROLS

    wizard = form.open_form(http)
    assert [name for name in REQUIRED_CONTROLS if not wizard.has(name)] == []


def test_fare_table_matches_the_official_page() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "build_tariffs", root / "tools" / "build_tariffs.py"
    )
    assert spec and spec.loader
    tool = importlib.util.module_from_spec(spec)
    sys.modules["build_tariffs"] = tool
    spec.loader.exec_module(tool)
    import json

    shipped = json.loads((root / "src/tper_cli/data/tariffs.json").read_text(encoding="utf-8"))
    built = tool.build(tool.flatten(tool.fetch()), "x")["products"]
    assert built == shipped["products"], "run `python tools/build_tariffs.py` and review the diff"
