"""``tper bus``: live arrivals, stops and lines."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import click

from tper_cli import validation
from tper_cli.commands._common import limit_option, pass_app, resolve_stop, stop_view
from tper_cli.context import AppContext
from tper_cli.data.catalog import Stop
from tper_cli.data.opendata import ATTRIBUTION
from tper_cli.errors import NotFoundError
from tper_cli.hellobus import Arrival
from tper_cli.output import info
from tper_cli.views import ARRIVALS, LINES, NEAR, STOPS


@click.group("bus")
def group() -> None:
    """Live bus arrivals (TPER Hello Bus), stops and lines for Bologna and Ferrara."""


def minutes_until(arrival: Arrival, now: datetime) -> int | None:
    """Minutes from ``now`` to a real-time arrival (None for timetable entries)."""
    if arrival.kind != "realtime":
        return None
    hour, minute = (int(x) for x in arrival.time.split(":"))
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when < now - timedelta(hours=2):  # just after midnight: the bus is due tomorrow
        when += timedelta(days=1)
    return max(0, round((when - now).total_seconds() / 60))


@group.command("arrivals")
@click.argument("stop")
@click.option("-l", "--line", default=None, help="Only this line (e.g. 11, 27A).")
@click.option(
    "--at",
    "at",
    default=None,
    metavar="HH:MM",
    help="Timetable for the first buses after this time instead of live positions.",
)
@pass_app
def arrivals(app: AppContext, stop: str, line: str | None, at: str | None) -> None:
    """Next buses at STOP: a stop code (4476) or a name that identifies one stop.

    Without --at you get live arrivals (type "realtime", from GPS). With --at you get
    the timetable (type "scheduled").
    """
    code, known = resolve_stop(app, stop)
    wanted_line = validation.line_code(line) if line else None
    hhmm = validation.hhmm(at) if at else None
    reply = app.hellobus.arrivals(code, wanted_line, hhmm)
    now = app.now()
    items: list[dict[str, Any]] = []
    for arrival in reply.arrivals:
        item = arrival.to_dict()
        item["minutes"] = minutes_until(arrival, now)
        items.append(item)
    for leftover in reply.unparsed:
        info(f"warning: could not read this Hello Bus entry: {leftover!r}")
    extra: dict[str, Any] = {
        "stop": code,
        "stopName": known.name if known else None,
        "mode": "scheduled" if hhmm else "realtime",
        "requestedTime": reply.requested_time,
        "line": wanted_line,
        "fetchedAt": now.isoformat(timespec="seconds"),
        "source": "TPER Hello Bus",
    }
    if reply.message:
        extra["message"] = reply.message
    if known and app.printer.fmt == "table":
        info(f"{known.name} ({known.address}, {known.municipality})")
    app.printer.items(items, ARRIVALS, kind="arrivals", extra=extra)


@group.group("stops")
def stops() -> None:
    """Search and inspect bus stops (TPER open data)."""


@stops.command("search")
@click.argument("query")
@click.option("-m", "--municipality", default=None, help="Only stops in this municipality.")
@limit_option(10)
@pass_app
def stops_search(app: AppContext, query: str, municipality: str | None, limit: int) -> None:
    """Find stops by name or address, tolerant to accents and small typos."""
    ranked = app.catalog.search_stops(query, municipality=municipality)
    items = [stop_view(s) for _, s in ranked[:limit]]
    app.printer.items(
        items, STOPS, kind="stops", extra={"count": len(items), "source": ATTRIBUTION}
    )


@stops.command("near")
@click.argument("lat", type=float)
@click.argument("lon", type=float)
@click.option(
    "-r",
    "--radius",
    type=click.IntRange(min=10, max=5000),
    default=400,
    show_default=True,
    help="Radius in metres.",
)
@limit_option(10)
@pass_app
def stops_near(app: AppContext, lat: float, lon: float, radius: int, limit: int) -> None:
    """Stops within RADIUS metres of a point (LAT LON in decimal degrees)."""
    validation.latitude(lat)
    validation.longitude(lon)
    found = app.catalog.stops_near(lat, lon, radius)[:limit]
    items = [{**stop_view(s), "distanceMeters": round(d)} for d, s in found]
    app.printer.items(items, NEAR, kind="stops", extra={"count": len(items), "source": ATTRIBUTION})


@stops.command("get")
@click.argument("stop")
@click.option(
    "--retailer", is_flag=True, help="Also ask Hello Bus for the nearest ticket retailer."
)
@pass_app
def stops_get(app: AppContext, stop: str, retailer: bool) -> None:
    """Details of one stop: position, fare zone and the lines that serve it."""
    code, _ = resolve_stop(app, stop)
    found = app.catalog.stops_by_code.get(code)
    if found is None:
        raise NotFoundError(f"Stop {code} is not in the TPER open data", reason="stopNotFound")
    data: dict[str, Any] = {**stop_view(found), "lat": found.lat, "lon": found.lon}
    data["lines"] = app.catalog.lines_at_stop(code)
    zone = app.catalog.zones.get(found.zone)
    data["zoneName"] = zone.name if zone else None
    if retailer:
        data["nearestRetailer"] = app.hellobus.nearest_retailer(code)
    app.printer.item(data)


@group.command("lines")
@click.option("-q", "--query", default=None, help="Only lines starting with this text.")
@pass_app
def lines(app: AppContext, query: str | None) -> None:
    """List the bus lines in the open data."""
    codes = app.catalog.line_codes
    if query:
        codes = [c for c in codes if c.upper().startswith(query.strip().upper())]
    items = [{"line": c} for c in codes]
    app.printer.items(
        items, LINES, kind="lines", extra={"count": len(items), "source": ATTRIBUTION}
    )


@group.command("line")
@click.argument("line")
@pass_app
def line_stops(app: AppContext, line: str) -> None:
    """Stops served by LINE. The open data does not give their order along the route."""
    code = validation.line_code(line)
    found: list[Stop] = app.catalog.stops_of_line(code)
    if not found:
        raise NotFoundError(
            f"No stops for line {code}",
            hint="List the lines with `tper bus lines`.",
            reason="lineNotFound",
        )
    app.printer.items(
        [stop_view(s) for s in found],
        STOPS,
        kind="stops",
        extra={"line": code, "count": len(found), "source": ATTRIBUTION},
    )
