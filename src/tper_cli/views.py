"""Table columns for each kind of result."""

from __future__ import annotations

from tper_cli.output import Column, col


def day(key: str) -> Column:
    """A date column showing only YYYY-MM-DD of an ISO timestamp."""
    return Column("date", lambda item: str(item.get(key) or "")[:10])


ARRIVALS: list[Column] = [
    col("line", "line"),
    col("type", "type"),
    col("time", "time"),
    col("in min", "minutes"),
    col("bus", "bus"),
    col("wheelchair", "wheelchair"),
]
STOPS: list[Column] = [
    col("code", "code"),
    col("name", "name", 34),
    col("address", "address", 34),
    col("municipality", "municipality", 20),
    col("zone", "zone"),
]
NEAR: list[Column] = [col("m", "distanceMeters"), *STOPS]
LINES: list[Column] = [col("line", "line")]
STATIONS: list[Column] = [
    col("code", "code"),
    col("name", "name", 34),
    col("municipality", "municipality", 24),
    col("address", "address", 34),
    col("zone", "zone"),
]
RAIL_LINES: list[Column] = [
    col("code", "code"),
    col("abbr", "abbreviation"),
    col("name", "name", 50),
]
NOTICES: list[Column] = [
    day("published"),
    col("kind", "kind"),
    col("regions", "regions", 24),
    col("title", "title", 90),
]
NEWS: list[Column] = [
    day("published"),
    col("category", "category"),
    col("title", "title", 90),
]
PLACES: list[Column] = [
    col("name", "name", 40),
    col("zone", "zone"),
    col("zone name", "zoneName", 30),
]
PRODUCTS: list[Column] = [
    col("kind", "kind"),
    col("name", "name", 52),
    col("zones", "zones"),
    col("profile", "profile"),
    col("price €", "price"),
    col("per ride", "pricePerRide"),
]
OPTIONS: list[Column] = [
    col("option", "name", 52),
    col("profile", "profile"),
    col("€ / month", "monthlyCost"),
    col("how", "how", 44),
]
DATASETS: list[Column] = [
    col("dataset", "dataset"),
    col("version", "version"),
    col("cached", "cached"),
    col("fetched", "fetchedAt", 25),
    col("description", "description", 40),
]
CLAIMS: list[Column] = [
    col("submitted", "submittedAt"),
    col("line", "line"),
    col("event date", "eventDate"),
    col("id", "fingerprint"),
]
