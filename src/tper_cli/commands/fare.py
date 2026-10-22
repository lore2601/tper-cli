"""``tper fare``: zones, ticket prices, passes and which one is cheapest."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import click

from tper_cli import search, validation
from tper_cli.commands._common import limit_option, pass_app
from tper_cli.config import BASINS, FARE_PROFILES
from tper_cli.context import AppContext
from tper_cli.data.opendata import ATTRIBUTION
from tper_cli.errors import ValidationError
from tper_cli.fares import FareBook, Product, compare, monthly_rides
from tper_cli.output import info
from tper_cli.views import OPTIONS, PLACES, PRODUCTS
from tper_cli.zones import ZoneTrip

URBAN_NETWORKS = ("bologna", "ferrara", "imola")


@click.group("fare")
def group() -> None:
    """Fare zones, ticket and pass prices, and the cheapest way to pay."""


# ---------------------------------------------------------------------- trip options


def trip_options(fn: Any) -> Any:
    for option in (
        click.option(
            "--basin",
            type=click.Choice(BASINS),
            default=None,
            help="Price list for extra-urban fares (default: from the origin zone).",
        ),
        click.option(
            "--urban",
            type=click.Choice(URBAN_NETWORKS),
            default=None,
            help="Urban network instead of a trip.",
        ),
        click.option(
            "--zones",
            "zone_count",
            type=click.IntRange(1, 10),
            default=None,
            help="Number of zones, if you already know it.",
        ),
        click.option("--to", "destination", default=None, help="Destination place."),
        click.option("--from", "origin", default=None, help="Origin place (locality or zone)."),
        click.option(
            "-p",
            "--profile",
            type=click.Choice(FARE_PROFILES),
            default=None,
            help="Reduced fare profile (default from config).",
        ),
    ):
        fn = option(fn)
    return fn


@dataclass
class TripSpec:
    area: str  # urban | extraurban
    network: str  # bologna | ferrara | imola
    zones: int | None
    trip: ZoneTrip | None = None
    notes: list[str] = field(default_factory=list)


def basin_for(trip: ZoneTrip) -> tuple[str, str] | None:
    """Infer the basin from the first digit of the zone code (5xx Bologna, 6xx Ferrara)."""
    for label, zone in (("origin", trip.origin.zone), ("destination", trip.destination.zone)):
        if not zone:
            continue
        if zone.startswith("5"):
            return "bologna", f"basin inferred from the {label} zone {zone}"
        if zone.startswith("6"):
            return "ferrara", f"basin inferred from the {label} zone {zone}"
    return None


def resolve_trip(
    app: AppContext,
    *,
    origin: str | None,
    destination: str | None,
    zone_count: int | None,
    urban: str | None,
    basin: str | None,
) -> TripSpec:
    given = [bool(origin or destination), zone_count is not None, urban is not None]
    if sum(given) != 1:
        raise ValidationError(
            "Say where you travel: --from A --to B, or --zones N, or --urban CITY",
            hint="Example: tper fare quote --from Bologna --to 'San Giovanni in Persiceto'",
        )
    if urban:
        return TripSpec("urban", urban, None)
    default_basin = basin or app.config.basin
    if zone_count is not None:
        validation.zones(zone_count)
        if not default_basin:
            raise ValidationError(
                "--zones needs --basin bologna|ferrara (prices differ)",
                hint="Or set defaults.basin in config.toml.",
            )
        return TripSpec("extraurban", default_basin, zone_count)
    if not (origin and destination):
        raise ValidationError("--from and --to must be used together")
    trip = app.zones.trip(origin, destination)
    if trip.urban_network:
        return TripSpec("urban", trip.urban_network, None, trip)
    notes: list[str] = []
    chosen = basin
    if chosen is None:
        inferred = basin_for(trip)
        if inferred:
            chosen, why = inferred
            notes.append(why)
        elif default_basin:
            chosen = default_basin
            notes.append("basin taken from your config")
        else:
            raise ValidationError(
                "Cannot tell which price list applies (neither zone is in Bologna or Ferrara)",
                hint="Pass --basin bologna|ferrara.",
            )
    if trip.source == "same-place":
        notes.append("origin and destination are the same place: 1 zone")
    return TripSpec("extraurban", chosen, trip.zones, trip, notes)


def products_for(
    app: AppContext, spec: TripSpec, profile: str
) -> tuple[list[tuple[Product, str]], list[tuple[Product, str]]]:
    book = FareBook.load()
    main = book.select(area=spec.area, network=spec.network, profile=profile, zones=spec.zones)
    extra: list[tuple[Product, str]] = []
    if spec.area == "extraurban" and spec.network == "bologna":
        extra = book.select(area="ferrobus", network="bologna", profile=profile, zones=spec.zones)
    return main, extra


def describe(spec: TripSpec) -> dict[str, Any]:
    data: dict[str, Any] = {"area": spec.area, "network": spec.network, "zones": spec.zones}
    if spec.trip:
        data["trip"] = spec.trip.to_dict()
    if spec.notes:
        data["notes"] = spec.notes
    return data


# ---------------------------------------------------------------------- commands


@group.command("places")
@click.argument("query")
@click.option(
    "--localities",
    is_flag=True,
    help="Search the finer open data list (frazioni). Their names are not accepted by "
    "the zone calculator, but show the fare zone.",
)
@limit_option(10)
@pass_app
def places(app: AppContext, query: str, localities: bool, limit: int) -> None:
    """Find a place by name: the names `fare zones/quote --from/--to` understand."""
    zones = app.catalog.zones
    if localities:
        ranked = search.rank(query, app.catalog.localities, lambda loc: (loc.name,), limit=limit)
        items = [
            {
                "name": loc.name,
                "zone": loc.zone,
                "zoneName": zones[loc.zone].name if loc.zone in zones else None,
            }
            for _, loc in ranked
        ]
    else:
        ranked_names = search.rank(query, app.zones.names(), lambda n: (n,), limit=limit)
        items = []
        for _, name in ranked_names:
            code = app.zones.zone_of(name)
            items.append(
                {
                    "name": name,
                    "zone": code,
                    "zoneName": zones[code].name if code and code in zones else None,
                }
            )
    app.printer.items(
        items,
        PLACES,
        kind="places",
        extra={
            "count": len(items),
            "source": "TPER zone calculator" if not localities else ATTRIBUTION,
        },
    )


@group.command("zones")
@click.argument("origin")
@click.argument("destination")
@pass_app
def zones_cmd(app: AppContext, origin: str, destination: str) -> None:
    """How many fare zones a trip crosses (asks TPER's official zone calculator)."""
    trip = app.zones.trip(origin, destination)
    app.printer.item({**trip.to_dict(), "source": "TPER zone calculator"})


@group.command("quote")
@trip_options
@pass_app
def quote(
    app: AppContext,
    origin: str | None,
    destination: str | None,
    zone_count: int | None,
    urban: str | None,
    basin: str | None,
    profile: str | None,
) -> None:
    """Every ticket and pass that fits a trip, with prices.

    Reduced prices (under 27, over 65/70) apply when you pass --profile; where TPER has no
    reduced price the ordinary one is shown and marked as such.
    """
    chosen = profile or app.config.fare_profile
    spec = resolve_trip(
        app, origin=origin, destination=destination, zone_count=zone_count, urban=urban, basin=basin
    )
    main, extra = products_for(app, spec, chosen)
    book = FareBook.load()
    rows = [p.to_dict() | {"profile": applied} for p, applied in main]
    alt = [p.to_dict() | {"profile": applied} for p, applied in extra]
    if spec.zones:
        info(f"{spec.zones} zone(s), {spec.network} price list, profile {chosen}")
    app.printer.items(
        rows,
        PRODUCTS,
        kind="products",
        extra={
            **describe(spec),
            "profile": chosen,
            "alsoConsider": alt,
            "card": book.card,
            "priceListDate": book.retrieved_at,
            "source": book.source,
        },
    )


@group.command("list")
@click.option("--area", type=click.Choice(["urban", "extraurban", "ferrobus"]), default=None)
@click.option("--network", type=click.Choice(URBAN_NETWORKS), default=None)
@click.option("--zones", "zone_count", type=click.IntRange(1, 10), default=None)
@click.option("--kind", default=None, help="single, carnet10, monthly, annual, day, ...")
@pass_app
def list_products(
    app: AppContext, area: str | None, network: str | None, zone_count: int | None, kind: str | None
) -> None:
    """The whole price list, filtered."""
    book = FareBook.load()
    rows = [
        p.to_dict()
        for p in book.products
        if (area is None or p.area == area)
        and (network is None or p.network == network)
        and (zone_count is None or p.zones == zone_count)
        and (kind is None or p.kind == kind)
    ]
    app.printer.items(
        rows,
        PRODUCTS,
        kind="products",
        extra={"count": len(rows), "priceListDate": book.retrieved_at, "source": book.source},
    )


@group.command("compare")
@trip_options
@click.option(
    "--rides-per-month",
    type=click.IntRange(min=1),
    default=None,
    help="Total rides in a month (a return trip is 2).",
)
@click.option(
    "--days-per-week",
    type=click.FloatRange(0.1, 7),
    default=5,
    show_default=True,
    help="Days a week you travel.",
)
@click.option(
    "--rides-per-day",
    type=click.IntRange(1, 20),
    default=2,
    show_default=True,
    help="Rides on a travel day.",
)
@pass_app
def compare_cmd(
    app: AppContext,
    origin: str | None,
    destination: str | None,
    zone_count: int | None,
    urban: str | None,
    basin: str | None,
    profile: str | None,
    rides_per_month: int | None,
    days_per_week: float,
    rides_per_day: int,
) -> None:
    """Which is cheaper for your usage: single tickets, carnets, monthly or annual pass?"""
    chosen = profile or app.config.fare_profile
    spec = resolve_trip(
        app, origin=origin, destination=destination, zone_count=zone_count, urban=urban, basin=basin
    )
    main, extra = products_for(app, spec, chosen)
    rides = monthly_rides(rides_per_month, days_per_week, rides_per_day)
    travel_days = rides / rides_per_day
    result = compare([*main, *extra], rides, travel_days=travel_days)
    book = FareBook.load()
    cheapest = result["cheapest"]
    if cheapest:
        info(f"cheapest: {cheapest['name']} at {cheapest['monthlyCost']:.2f} EUR/month")
    app.printer.items(
        result["options"],
        OPTIONS,
        kind="options",
        extra={
            **describe(spec),
            "profile": chosen,
            "ridesPerMonth": result["ridesPerMonth"],
            "travelDaysPerMonth": round(travel_days, 1),
            "cheapest": cheapest,
            "breakEvenRidesPerMonth": result.get("breakEvenRidesPerMonth"),
            "priceListDate": book.retrieved_at,
            "source": book.source,
        },
    )
