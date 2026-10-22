"""Fare book: tickets and passes from the official price list, and cost comparison.

Prices come from ``data/tariffs.json``, a snapshot of
https://www.tper.it/biglietti-abbonamenti/tariffe built by ``tools/build_tariffs.py``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from tper_cli.errors import SetupError, ValidationError

URBAN_ZONES = {"500": "bologna", "510": "imola", "600": "ferrara"}

KIND_LABELS = {
    "single": "Single ticket",
    "single_onboard": "Single ticket bought on board (coins / driver)",
    "carnet10": "10-ride carnet",
    "day": "Day ticket",
    "ecoticket": "Ecoticket (20 days)",
    "monthly": "Monthly pass (personal)",
    "monthly_anonymous": "Monthly pass (transferable)",
    "annual": "Annual pass (personal)",
    "annual_anonymous": "Annual pass (transferable)",
    "ferrobus_monthly": "Ferrobus monthly pass (bus + Trenitalia Tper trains)",
}
PROFILE_LABELS = {
    "ordinary": "ordinary",
    "under27": "under 27",
    "over65": "over 65",
    "over70": "over 70",
}
PASS_KINDS = {"monthly", "monthly_anonymous", "annual", "annual_anonymous", "ferrobus_monthly"}


@dataclass(frozen=True)
class Product:
    id: str
    area: str
    network: str
    kind: str
    profile: str
    zones: int | None
    rides: int | None
    validity_minutes: int | None
    price: float | None
    note: str | None
    order: int

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "name": self.label,
            "price": self.price,
            "profile": self.profile,
        }
        if self.zones:
            data["zones"] = self.zones
        if self.rides and self.rides > 1:
            data["rides"] = self.rides
            if self.price is not None:
                data["pricePerRide"] = round(self.price / self.rides, 2)
        if self.validity_minutes:
            data["validityMinutes"] = self.validity_minutes
        if self.note:
            data["note"] = self.note
        return data


class FareBook:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.source: str = raw["source"]
        self.retrieved_at: str = raw["retrievedAt"]
        self.card: dict[str, Any] = raw["card"]
        self.products = [
            Product(
                id=p["id"],
                area=p["area"],
                network=p["network"],
                kind=p["kind"],
                profile=p["profile"],
                zones=p["zones"],
                rides=p["rides"],
                validity_minutes=p["validityMinutes"],
                price=p["price"],
                note=p.get("note"),
                order=p["order"],
            )
            for p in raw["products"]
        ]

    @classmethod
    def load(cls) -> FareBook:
        return _load()

    def select(
        self,
        *,
        area: str,
        network: str,
        profile: str = "ordinary",
        zones: int | None = None,
    ) -> list[tuple[Product, str]]:
        """Products for one area/network (and zone count), best-fitting profile each.

        Returns ``(product, profile_applied)``. If there is no price for ``profile`` the
        ordinary one is used, so ``profile_applied`` tells which one the price is for.
        """
        group = [
            p
            for p in self.products
            if p.area == area and p.network == network and (zones is None or p.zones == zones)
        ]
        by_kind: dict[str, list[Product]] = {}
        for p in sorted(group, key=lambda x: x.order):
            by_kind.setdefault(p.kind, []).append(p)
        chosen: list[tuple[Product, str]] = []
        for options in by_kind.values():
            exact = next((p for p in options if p.profile == profile and p.price is not None), None)
            fallback = next((p for p in options if p.profile == "ordinary"), None)
            if exact is not None:
                chosen.append((exact, profile))
            elif fallback is not None:
                chosen.append((fallback, "ordinary"))
        return chosen

    def networks(self, area: str) -> list[str]:
        return sorted({p.network for p in self.products if p.area == area})


@cache
def _load() -> FareBook:
    try:
        text = resources.files("tper_cli.data").joinpath("tariffs.json").read_text("utf-8")
    except (OSError, ModuleNotFoundError) as exc:  # pragma: no cover - packaging error
        raise SetupError("The bundled fare table is missing", reason="faresMissing") from exc
    return FareBook(json.loads(text))


def monthly_rides(rides_per_month: int | None, days_per_week: float, rides_per_day: int) -> float:
    if rides_per_month is not None:
        return float(rides_per_month)
    return days_per_week * rides_per_day * 52 / 12


def compare(
    options: Iterable[tuple[Product, str]],
    rides: float,
    *,
    travel_days: float | None = None,
) -> dict[str, Any]:
    """Monthly cost of each way of paying for ``rides`` rides a month, cheapest first."""
    if rides <= 0:
        raise ValidationError("Rides per month must be positive")
    rows: list[dict[str, Any]] = []
    single_price: float | None = None
    for product, applied in options:
        if product.price is None:
            continue
        cost: float | None = None
        how = ""
        if product.kind == "single":
            single_price = product.price
            cost, how = rides * product.price, f"{rides:.1f} rides x {product.price:.2f}"
        elif product.kind == "carnet10" and product.rides:
            per_ride = product.price / product.rides
            cost, how = rides * per_ride, f"{rides:.1f} rides x {per_ride:.2f} (carnet average)"
        elif product.kind == "day" and travel_days:
            cost, how = travel_days * product.price, f"{travel_days:.1f} days x {product.price:.2f}"
        elif product.kind == "ecoticket" and travel_days and product.rides:
            per_day = product.price / product.rides
            cost, how = travel_days * per_day, f"{travel_days:.1f} days x {per_day:.2f}"
        elif product.kind in {"monthly", "monthly_anonymous", "ferrobus_monthly"}:
            cost, how = product.price, "flat monthly price"
        elif product.kind in {"annual", "annual_anonymous"}:
            cost, how = product.price / 12, f"{product.price:.2f} / 12 months"
        if cost is None:
            continue
        rows.append(
            {
                "product": product.id,
                "kind": product.kind,
                "name": product.label,
                "profile": applied,
                "monthlyCost": round(cost, 2),
                "how": how,
                "upfront": product.price if product.kind in PASS_KINDS or product.rides else None,
            }
        )
    rows.sort(key=lambda r: (r["monthlyCost"], r["kind"]))
    result: dict[str, Any] = {
        "ridesPerMonth": round(rides, 1),
        "options": rows,
        "cheapest": rows[0] if rows else None,
    }
    monthly = [
        r
        for r in rows
        if r["kind"] in {"monthly", "monthly_anonymous"} and single_price is not None
    ]
    if monthly and single_price:
        best = min(monthly, key=lambda r: r["monthlyCost"])
        result["breakEvenRidesPerMonth"] = math.ceil(best["monthlyCost"] / single_price)
    return result
