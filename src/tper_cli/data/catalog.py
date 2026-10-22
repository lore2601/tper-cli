"""Typed views over the TPER open data tables."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property

from tper_cli import search
from tper_cli.data.opendata import OpenDataStore


def to_float(value: str) -> float | None:
    """Parse ``44,505762`` (decimal comma) or ``44.8582``; empty means unknown."""
    text = value.strip().replace(",", ".")
    try:
        return float(text) if text else None
    except ValueError:
        return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Stop:
    code: str
    name: str
    address: str
    municipality: str
    lat: float | None
    lon: float | None
    zone: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "name": self.name,
            "address": self.address,
            "municipality": self.municipality,
            "lat": self.lat,
            "lon": self.lon,
            "zone": self.zone,
        }


@dataclass(frozen=True)
class Station:
    code: str
    name: str
    address: str
    municipality: str
    zone: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "name": self.name,
            "address": self.address,
            "municipality": self.municipality,
            "zone": self.zone or None,
        }


@dataclass(frozen=True)
class Locality:
    name: str
    zone: str


@dataclass(frozen=True)
class Zone:
    code: str
    name: str
    technical: bool
    reference: str


@dataclass(frozen=True)
class Retailer:
    code: str
    name: str
    address: str
    municipality: str
    hours: str
    lat: float | None
    lon: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "name": self.name,
            "address": self.address,
            "municipality": self.municipality,
            "hours": self.hours,
            "lat": self.lat,
            "lon": self.lon,
        }


class Catalog:
    """Lazy, in-memory views of the open data tables."""

    def __init__(self, store: OpenDataStore) -> None:
        self.store = store

    @cached_property
    def stops(self) -> list[Stop]:
        return [
            Stop(
                code=r["codice"],
                name=r["denominazione"],
                address=r.get("ubicazione", ""),
                municipality=r.get("comune", ""),
                lat=to_float(r.get("latitudine", "")),
                lon=to_float(r.get("longitudine", "")),
                zone=r.get("codice_zona", ""),
            )
            for r in self.store.table("fermate")
        ]

    @cached_property
    def stops_by_code(self) -> dict[str, Stop]:
        return {s.code: s for s in self.stops}

    def stop_if_cached(self, code: str) -> Stop | None:
        """Look a stop up without touching the network (None if the table is not cached)."""
        rows = self.store.cached("fermate")
        if rows is None:
            return None
        for r in rows:
            if r["codice"] == code:
                return Stop(
                    code=code,
                    name=r["denominazione"],
                    address=r.get("ubicazione", ""),
                    municipality=r.get("comune", ""),
                    lat=to_float(r.get("latitudine", "")),
                    lon=to_float(r.get("longitudine", "")),
                    zone=r.get("codice_zona", ""),
                )
        return None

    def search_stops(
        self, query: str, *, municipality: str | None = None
    ) -> list[tuple[float, Stop]]:
        stops: list[Stop] = self.stops
        if municipality:
            wanted = search.normalize(municipality)
            stops = [s for s in stops if search.normalize(s.municipality) == wanted]
        return search.rank(query, stops, lambda s: (s.name, f"{s.name} {s.address}"))

    def stops_near(self, lat: float, lon: float, radius_m: float) -> list[tuple[float, Stop]]:
        found = [
            (haversine_m(lat, lon, s.lat, s.lon), s)
            for s in self.stops
            if s.lat is not None and s.lon is not None
        ]
        return sorted((d, s) for d, s in found if d <= radius_m)

    @cached_property
    def line_codes(self) -> list[str]:
        return [r["codice_linea"] for r in self.store.table("linee")]

    @cached_property
    def _line_stops(self) -> dict[str, list[str]]:
        mapping: dict[str, list[str]] = {}
        for r in self.store.table("lineefermate"):
            mapping.setdefault(r["codice_linea"], []).append(r["codice_fermata"])
        return mapping

    def stops_of_line(self, line: str) -> list[Stop]:
        codes = self._line_stops.get(line, [])
        by_code = self.stops_by_code
        return [by_code[c] for c in dict.fromkeys(codes) if c in by_code]

    def lines_at_stop(self, code: str) -> list[str]:
        return sorted(
            (line for line, stops in self._line_stops.items() if code in stops),
            key=lambda x: (len(x), x),
        )

    @cached_property
    def stations(self) -> list[Station]:
        return [
            Station(
                code=r["codice"],
                name=r["denominazione"],
                address=r.get("ubicazione", ""),
                municipality=r.get("comune", ""),
                zone=r.get("codice_zona", ""),
            )
            for r in self.store.table("stazioniferroviarie")
        ]

    @cached_property
    def rail_lines(self) -> list[dict[str, str]]:
        return [
            {"code": r["codice_linea"], "abbreviation": r["sigla"], "name": r["denominazione"]}
            for r in self.store.table("lineeferroviarie")
        ]

    @cached_property
    def zones(self) -> dict[str, Zone]:
        return {
            r["codice"]: Zone(
                code=r["codice"],
                name=r["descrizione"],
                technical=r.get("zona_tecnica", "").lower() == "true",
                reference=r.get("codice_zona_riferimento", ""),
            )
            for r in self.store.table("zone")
        }

    @cached_property
    def localities(self) -> list[Locality]:
        names: dict[str, Locality] = {}
        for r in self.store.table("localitazone"):
            names.setdefault(r["denominazione"], Locality(r["denominazione"], r["codice_zona"]))
        for zone in self.zones.values():
            names.setdefault(zone.name, Locality(zone.name, zone.code))
        return list(names.values())

    @cached_property
    def retailers(self) -> list[Retailer]:
        result: list[Retailer] = []
        for r in self.store.table("rivendite"):
            lat_s, _, lon_s = r.get("coordinate", "").partition(",")
            result.append(
                Retailer(
                    code=r["codice"],
                    name=r["ragione_sociale"],
                    address=r.get("indirizzo_ubicazione", ""),
                    municipality=r.get("comune_indirizzo_ubicazione", ""),
                    hours=" ".join(
                        p for p in (r.get("orari_mattino", ""), r.get("orari_pomeriggio", "")) if p
                    ),
                    lat=to_float(lat_s),
                    lon=to_float(lon_s),
                )
            )
        return result
