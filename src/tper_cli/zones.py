"""Fare zones: resolve place names and count zones with the official TPER calculator.

The number of zones of a trip decides the price of extra-urban tickets. TPER publishes
a public calculator (https://solweb.tper.it/web/tools/zone-calculator.aspx) that only
accepts its own list of place names (municipalities and main localities). The CLI loads
that list, resolves what the user typed against it, asks the calculator over plain HTTP
and caches both.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from tper_cli import search
from tper_cli.data.catalog import Catalog
from tper_cli.errors import UpstreamError
from tper_cli.fares import URBAN_ZONES
from tper_cli.http import Http
from tper_cli.webforms import combo, load, submit

URL = "https://solweb.tper.it/web/tools/zone-calculator.aspx"
SERVICE = "tper-zone-calculator"
PREFIX = "ctl00$ContentPlaceHolderMain$"
ORIGIN = f"{PREFIX}cboZonaOrigine"
DESTINATION = f"{PREFIX}cboZonaDestinazione"
BUTTON = (f"{PREFIX}btCalcola_input", "Calcola")
RESULT_ID = "ContentPlaceHolderMain_lblZoneAttraversate"
LIST_ID = "ctl00_ContentPlaceHolderMain_cboZonaOrigine_DropDown"
CACHE_TTL = timedelta(days=30)
URBAN_NAMES = {"BOLOGNA": "bologna", "IMOLA": "imola", "FERRARA": "ferrara"}
_STOPWORDS = {"in", "di", "del", "della", "dell", "d", "sul", "e"}


def match_key(name: str) -> str:
    """Comparison key that tolerates ``S.`` for ``SAN`` and small words (``in``, ``di``)."""
    tokens = [("san" if t == "s" else t) for t in search.normalize(name).split()]
    return " ".join(t for t in tokens if t not in _STOPWORDS)


def pick_place(names: list[str], query: str) -> str:
    """The calculator place that ``query`` refers to, or an error that explains why not."""
    return search.pick(
        names,
        query,
        noun="place",
        hint="Search with `tper fare places QUERY`, or pass --zones N yourself.",
    )


@dataclass(frozen=True)
class Place:
    name: str  # the name the calculator knows
    zone: str | None  # fare zone code, when it can be matched in the open data

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "zone": self.zone}


@dataclass(frozen=True)
class ZoneTrip:
    origin: Place
    destination: Place
    zones: int | None
    urban_network: str | None  # set when the trip stays inside Bologna, Imola or Ferrara
    source: str  # calculator | cache | same-place

    def to_dict(self) -> dict[str, object]:
        return {
            "from": self.origin.to_dict(),
            "to": self.destination.to_dict(),
            "area": "urban" if self.urban_network else "extraurban",
            "urbanNetwork": self.urban_network,
            "zones": self.zones,
            "source": self.source,
        }


class ZoneCalculator:
    def __init__(
        self,
        http: Http,
        catalog: Catalog,
        cache: Path,
        now: Callable[[], datetime],
    ) -> None:
        self.http = http
        self.catalog = catalog
        self.trips_path = cache / "zone-trips.json"
        self.places_path = cache / "zone-places.json"
        self.now = now

    # ------------------------------------------------------------------ cache

    def _read(self, path: Path) -> dict[str, object]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, path: Path, data: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def _fresh(self, stamp: object) -> bool:
        try:
            return self.now() - datetime.fromisoformat(str(stamp)) < CACHE_TTL
        except ValueError:
            return False

    # ------------------------------------------------------------------ places

    def names(self) -> list[str]:
        """Every place name the calculator accepts."""
        cached = self._read(self.places_path)
        if cached.get("names") and self._fresh(cached.get("checkedAt")):
            return [str(n) for n in cached["names"]]  # type: ignore[attr-defined]
        page = load(self.http, URL, SERVICE)
        drop = page.root.by_id(LIST_ID)
        names = sorted({li.text() for li in drop.find_all("li") if li.text()}) if drop else []
        if not names:
            raise UpstreamError(
                "The zone calculator did not list any place",
                service=SERVICE,
                reason="unexpectedResponse",
                hint="Pass the number of zones yourself with --zones N.",
            )
        self._write(self.places_path, {"checkedAt": self.now().isoformat(), "names": names})
        return names

    def zone_of(self, name: str) -> str | None:
        """Best-effort fare zone code of a calculator place, from the open data."""
        key = match_key(name)
        for locality in self.catalog.localities:
            if match_key(locality.name) == key:
                return locality.zone
        return None

    def place(self, query: str) -> Place:
        canonical = pick_place(self.names(), query)
        return Place(canonical, self.zone_of(canonical))

    # ------------------------------------------------------------------ trips

    def trip(self, origin: str, destination: str) -> ZoneTrip:
        a, b = self.place(origin), self.place(destination)
        if a.name == b.name:
            network = URBAN_NAMES.get(a.name) or URBAN_ZONES.get(a.zone or "")
            return ZoneTrip(a, b, None if network else 1, network, "same-place")
        key = "|".join(sorted((a.name, b.name)))
        trips = self._read(self.trips_path)
        entry = trips.get(key)
        if isinstance(entry, dict) and self._fresh(entry.get("checkedAt")):
            return ZoneTrip(a, b, int(entry["zones"]), None, "cache")
        zones = self._ask(a.name, b.name)
        trips[key] = {"zones": zones, "checkedAt": self.now().isoformat()}
        self._write(self.trips_path, trips)
        return ZoneTrip(a, b, zones, None, "calculator")

    def _ask(self, origin: str, destination: str) -> int:
        page = load(self.http, URL, SERVICE)
        values = {
            ORIGIN: origin,
            DESTINATION: destination,
            f"{PREFIX}rbtlstTipoCalcolo": "G",
            **combo("ctl00_ContentPlaceHolderMain_cboZonaOrigine_ClientState", origin),
            **combo("ctl00_ContentPlaceHolderMain_cboZonaDestinazione_ClientState", destination),
            "ctl00_ContentPlaceHolderMain_btCalcola_ClientState": "",
        }
        answer = submit(self.http, page, values, button=BUTTON)
        text = answer.text_of(RESULT_ID)
        if not text or not text.strip().isdigit():
            raise UpstreamError(
                f"The zone calculator gave no result for {origin} -> {destination}",
                service=SERVICE,
                reason="unexpectedResponse",
                hint="Pass the number of zones yourself with --zones N.",
            )
        return int(text.strip())
