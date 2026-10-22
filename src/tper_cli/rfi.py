"""Live station boards from RFI, the railway infrastructure manager.

RFI publishes "Monitor arrivi e partenze live" for its stations on rfi.it: the same boards
shown at the station, with the carrier, platform, delay in minutes and the next stops of
each train. They cover every train that calls at an RFI station, including Trenitalia Tper
regional services. The CLI finds the station on rfi.it, reads its board over plain HTTP
and, to follow a train, looks it up on the boards of the stations you name.
"""

from __future__ import annotations

import html as htmllib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tper_cli import search
from tper_cli.errors import NotFoundError, UpstreamError
from tper_cli.htmlutil import Node, parse_html
from tper_cli.http import Http

SERVICE = "rfi"
STATIONS_URL = "https://www.rfi.it/it/stazioni.html"
STATION_URL = "https://www.rfi.it/it/stazioni/{slug}.html"
MONITOR_URL = "https://iechub.rfi.it/ArriviPartenze/ArrivalsDepartures/Monitor"
CACHE_TTL = timedelta(days=30)
ROME = ZoneInfo("Europe/Rome")
DEFAULT_STATIONS = ("Bologna Centrale", "Ferrara", "Modena", "Imola", "Parma", "Rimini")
_NAMES = re.compile(r'searchStationsJSON"\s*value="([^"]*)"')
_PLACE_ID = re.compile(r"placeId=(\d+)")
_UPDATED = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s+alle ore\s+(\d{2}):(\d{2}):(\d{2})")
_STOP = re.compile(r"\s*([^()]+?)\s*\((\d{2}:\d{2})\)")
_ROUTE_HEAD = re.compile(r"^(?:.*?FERMATE\s+\w+)?\s*(?:FERMA A\s*:)?", re.IGNORECASE | re.DOTALL)
_CANCELLED = re.compile(r"soppress|cancell", re.IGNORECASE)


def slugify(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name.replace("'", "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


@dataclass(frozen=True)
class TrainRow:
    number: str
    carrier: str
    category: str
    place: str  # destination on a departures board, origin on an arrivals board
    time: str
    delay: int
    status: str  # onTime | delayed | cancelled
    platform: str
    departing: bool
    stops: list[dict[str, str]] = field(default_factory=list)
    info: str = ""

    @property
    def expected(self) -> str:
        hour, minute = (int(x) for x in self.time.split(":"))
        moved = datetime(2000, 1, 1, hour, minute) + timedelta(minutes=self.delay)
        return moved.strftime("%H:%M")

    def to_dict(self, kind: str) -> dict[str, object]:
        data: dict[str, object] = {
            "train": self.number,
            "carrier": self.carrier,
            "category": self.category,
            "destination" if kind == "departures" else "origin": self.place,
            "time": self.time,
            "expectedTime": self.expected,
            "delayMinutes": self.delay,
            "status": self.status,
            "platform": self.platform or None,
            "departing": self.departing,
        }
        if self.stops:
            data["stops"] = self.stops
        if self.info:
            data["info"] = self.info
        return data


@dataclass
class Board:
    station: str
    kind: str  # departures | arrivals
    updated_at: datetime | None
    trains: list[TrainRow]

    def find(self, number: str) -> TrainRow | None:
        return next((t for t in self.trains if t.number == number), None)


def _alt(cell: Node) -> str:
    image = cell.find("img")
    text = image.get("alt") if image is not None else ""
    return htmllib.unescape(text).removeprefix("Categoria ").strip()


def parse_board(markup: str, station: str, kind: str) -> Board:
    root = parse_html(markup)
    rows = [tr for tr in root.find_all("tr") if tr.get("name") == "treno"]
    stamp = _UPDATED.search(root.text())
    if not stamp and not root.find_all("th"):
        raise UpstreamError(
            f"The RFI board of {station} is not in the expected format",
            service=SERVICE,
            reason="unexpectedResponse",
            hint="RFI may have changed the page. Please report it.",
        )
    updated = None
    if stamp:
        day, month, year, hour, minute, second = (int(x) for x in stamp.groups())
        updated = datetime(year, month, day, hour, minute, second, tzinfo=ROME)
    trains: list[TrainRow] = []
    for tr in rows:
        cells = [c for c in tr.children if c.tag == "td"]
        if len(cells) < 9:
            continue
        number = cells[2].text() or tr.get("id")
        delay_text = cells[5].text()
        details = cells[8].text()
        info = details.split("Informazioni", 1)[1].strip() if "Informazioni" in details else ""
        route = details.split("Informazioni", 1)[0]
        route = _ROUTE_HEAD.sub("", route)
        stops = [{"station": s.strip(" -").strip(), "time": t} for s, t in _STOP.findall(route)]
        cancelled = bool(_CANCELLED.search(details + " " + delay_text))
        delay = int(delay_text) if delay_text.isdigit() else 0
        status = "cancelled" if cancelled else "delayed" if delay > 0 else "onTime"
        trains.append(
            TrainRow(
                number=number,
                carrier=_alt(cells[0]),
                category=_alt(cells[1]),
                place=cells[3].text(),
                time=cells[4].text(),
                delay=delay,
                status=status,
                platform=cells[6].text(),
                departing=bool(cells[7].text()),
                stops=[s for s in stops if s["station"]],
                info=info,
            )
        )
    return Board(station, kind, updated, trains)


class Rfi:
    def __init__(self, http: Http, cache: Path, now: Callable[[], datetime]) -> None:
        self.http = http
        self.path = cache / "rfi-stations.json"
        self.now = now
        self._boards: dict[tuple[str, str], Board] = {}

    # ------------------------------------------------------------------ cache

    def _read(self) -> dict[str, object]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def _fresh(self, data: dict[str, object]) -> bool:
        try:
            return self.now() - datetime.fromisoformat(str(data["checkedAt"])) < CACHE_TTL
        except (KeyError, ValueError):
            return False

    # ------------------------------------------------------------------ stations

    def station_names(self) -> list[str]:
        data = self._read()
        if data.get("names") and self._fresh(data):
            return [str(n) for n in data["names"]]  # type: ignore[attr-defined]
        page = self.http.get(STATIONS_URL, service=SERVICE).text
        found = _NAMES.search(page)
        names = sorted(
            {n.strip() for n in htmllib.unescape(found.group(1)).split(",") if n.strip()}
            if found
            else set()
        )
        if not names:
            raise UpstreamError(
                "rfi.it did not list its stations",
                service=SERVICE,
                reason="unexpectedResponse",
                hint="RFI may have changed the page. Please report it.",
            )
        data = {
            "checkedAt": self.now().isoformat(),
            "names": names,
            "placeIds": data.get("placeIds", {}),
        }
        self._write(data)
        return names

    def resolve(self, query: str) -> str:
        return search.pick(
            self.station_names(),
            query,
            noun="station",
            hint="List station names with `tper rail stations --rfi -q TEXT`.",
        )

    def place_id(self, name: str) -> int:
        data = self._read()
        known = data.get("placeIds") or {}
        if isinstance(known, dict) and name in known:
            return int(known[name])
        page = self.http.get(STATION_URL.format(slug=slugify(name)), service=SERVICE).text
        found = _PLACE_ID.search(page)
        if not found:
            raise NotFoundError(
                f"RFI has no live board for {name}",
                hint="Small stations may not have one.",
                reason="boardNotAvailable",
            )
        if isinstance(known, dict):
            known[name] = int(found.group(1))
            data["placeIds"] = known
            data.setdefault("checkedAt", self.now().isoformat())
            data.setdefault("names", [])
            self._write(data)
        return int(found.group(1))

    # ------------------------------------------------------------------ boards

    def board(self, station: str, *, arrivals: bool = False) -> Board:
        name = self.resolve(station)
        kind = "arrivals" if arrivals else "departures"
        if (name, kind) in self._boards:
            return self._boards[(name, kind)]
        params = {"placeId": str(self.place_id(name)), "arrivals": "True" if arrivals else "False"}
        page = self.http.get(MONITOR_URL, service=SERVICE, params=params).text
        board = parse_board(page, name, kind)
        self._boards[(name, kind)] = board
        return board

    def track(self, number: str, stations: list[str]) -> tuple[Board, TrainRow] | None:
        """Look for a train on the departure and arrival boards of ``stations``, in order."""
        for station in stations:
            for arrivals in (False, True):
                board = self.board(station, arrivals=arrivals)
                row = board.find(number)
                if row is not None:
                    return board, row
        return None
