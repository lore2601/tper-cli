"""Client for TPER Hello Bus, the public real-time web service for bus arrivals.

Service definition: https://hellobuswsweb.tper.it/web-services/hellobus.asmx
The service answers with one line of text wrapped in a small XML document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from defusedxml import ElementTree

from tper_cli.errors import NotFoundError, UpstreamError, ValidationError
from tper_cli.http import Http

URL = "https://hellobuswsweb.tper.it/web-services/hellobus.asmx"
SERVICE = "hellobus"
_ENTRY = re.compile(
    r"^(?P<line>\S+)\s+(?P<kind>[A-Za-z]+)\s+(?P<time>\d{2}:\d{2})"
    r"(?:\s*\((?P<extra>[^)]*)\))?$"
)
_REQUESTED = re.compile(r"^\(x(?P<time>\d{2}:\d{2})\)\s*")
_BUS = re.compile(r"Bus(\d+)")
_RESALE = re.compile(r"^Rivendita a (?P<m>\d+)m da fermata (?P<stop>\d+): (?P<what>.+)$")
KINDS = {"DaSatellite": "realtime", "Previsto": "scheduled"}


@dataclass(frozen=True)
class Arrival:
    line: str
    kind: str  # realtime | scheduled | the raw word if TPER adds a new one
    time: str  # HH:MM, Europe/Rome
    bus: str | None
    wheelchair: bool | None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"line": self.line, "type": self.kind, "time": self.time}
        if self.bus:
            data["bus"] = self.bus
        if self.wheelchair is not None:
            data["wheelchair"] = self.wheelchair
        return data


@dataclass
class Reply:
    arrivals: list[Arrival] = field(default_factory=list)
    requested_time: str | None = None
    message: str | None = None
    unparsed: list[str] = field(default_factory=list)


def unwrap(body: str) -> str:
    """The text inside ``<string xmlns=...>text</string>``."""
    try:
        root = ElementTree.fromstring(body.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise UpstreamError(
            "Hello Bus returned something that is not XML",
            service=SERVICE,
            reason="unexpectedResponse",
        ) from exc
    return (root.text or "").strip()


def parse_reply(text: str) -> Reply:
    """Parse the text answer of ``QueryHellobus``."""
    if text.startswith("HellobusHelp:"):
        detail = text.removeprefix("HellobusHelp:").strip()
        if "NON GESTITA" in detail.upper():
            raise NotFoundError(
                f"Hello Bus does not know this stop: {detail.split(',')[0]}",
                hint="Find the code with `tper bus stops search NAME`.",
                reason="stopNotFound",
            )
        raise ValidationError(f"Hello Bus rejected the request: {detail}")
    if not text.startswith("TperHellobus:"):
        raise UpstreamError(
            f"Unexpected Hello Bus answer: {text[:120]!r}",
            service=SERVICE,
            reason="unexpectedResponse",
        )
    body = text.removeprefix("TperHellobus:").strip()
    reply = Reply()
    requested = _REQUESTED.match(body)
    if requested:
        reply.requested_time = requested.group("time")
        body = body[requested.end() :]
    for chunk in (c.strip() for c in body.split(",")):
        if not chunk:
            continue
        match = _ENTRY.match(chunk)
        if not match:
            reply.unparsed.append(chunk)
            continue
        extra = match.group("extra") or ""
        bus = _BUS.search(extra)
        reply.arrivals.append(
            Arrival(
                line=match.group("line").upper(),
                kind=KINDS.get(match.group("kind"), match.group("kind").lower()),
                time=match.group("time"),
                bus=bus.group(1) if bus else None,
                wheelchair=True if "CON PEDANA" in extra.upper() else None,
            )
        )
    if not reply.arrivals:
        reply.message = body or None
        reply.unparsed = []
    return reply


class HelloBus:
    def __init__(self, http: Http) -> None:
        self.http = http

    def arrivals(self, stop: str, line: str | None = None, at: str | None = None) -> Reply:
        """Arrivals at ``stop``. ``at`` (HHMM) asks for the timetable instead of live data."""
        params = {"fermata": stop, "linea": line or "", "oraHHMM": at or ""}
        response = self.http.get(f"{URL}/QueryHellobus", service=SERVICE, params=params)
        return parse_reply(unwrap(response.text))

    def nearest_retailer(self, stop: str) -> dict[str, object] | None:
        """The ticket retailer closest to the stop, as reported by ``QueryResale``."""
        response = self.http.get(f"{URL}/QueryResale", service=SERVICE, params={"fermata": stop})
        match = _RESALE.match(unwrap(response.text))
        if not match:
            return None
        return {"distanceMeters": int(match.group("m")), "description": match.group("what")}
