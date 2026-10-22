from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tper_cli.errors import ValidationError
from tper_cli.fares import FareBook, compare, monthly_rides

ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "tariffe.txt"


def load_tool():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "build_tariffs", ROOT / "tools" / "build_tariffs.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_tariffs"] = module
    spec.loader.exec_module(module)
    return module


def test_shipped_table_matches_the_parser_output() -> None:
    """tariffs.json is exactly what tools/build_tariffs.py produces from the saved page."""
    tool = load_tool()
    lines = [ln.strip() for ln in FIXTURE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    built = tool.build(lines, "x")["products"]
    shipped = json.loads((ROOT / "src/tper_cli/data/tariffs.json").read_text(encoding="utf-8"))
    assert built == shipped["products"]


def test_parser_refuses_a_page_with_a_different_layout() -> None:
    tool = load_tool()
    with pytest.raises(SystemExit, match="layout changed"):
        tool.build(["Area Urbana", "Bologna", "Biglietto ordinario 2,3€"], "x")


def test_clean_nulls_a_reduced_price_above_the_ordinary_one() -> None:
    tool = load_tool()
    base = {"area": "extraurban", "network": "bologna", "kind": "annual", "zones": 8, "rides": None,
            "validityMinutes": None}  # fmt: skip
    products = [
        {**base, "profile": "ordinary", "price": 660.0},
        {**base, "profile": "over70", "price": 665.0},
    ]
    cleaned = tool.clean(products)
    assert cleaned[1]["price"] is None
    assert "typo" in cleaned[1]["note"]


def test_flatten_extracts_visible_text() -> None:
    tool = load_tool()
    lines = tool.flatten(
        "<html><main><p>Uno</p><div>Due &amp; tre<br>quattro</div><script>x</script>"
    )
    assert lines == ["Uno", "Due & tre", "quattro"]


def test_every_extraurban_group_is_complete() -> None:
    book = FareBook.load()
    for network in ("bologna", "ferrara"):
        for zones in range(1, 11):
            kinds = {
                p.kind for p, _ in book.select(area="extraurban", network=network, zones=zones)
            }
            assert {"single", "single_onboard", "carnet10", "monthly", "annual"} <= kinds, (
                network,
                zones,
            )


def test_prices_grow_with_the_number_of_zones() -> None:
    book = FareBook.load()
    for network in ("bologna", "ferrara"):
        for kind in ("single", "single_onboard", "carnet10", "monthly", "annual"):
            prices = [
                next(
                    p.price
                    for p, _ in book.select(area="extraurban", network=network, zones=z)
                    if p.kind == kind
                )
                for z in range(1, 11)
            ]
            assert prices == sorted(prices), (network, kind)


def test_select_prefers_the_profile_and_falls_back_to_ordinary() -> None:
    book = FareBook.load()
    chosen = {
        p.kind: (p.price, applied)
        for p, applied in book.select(area="urban", network="bologna", profile="under27")
    }
    assert chosen["annual"] == (230.0, "under27")
    assert chosen["single"] == (2.3, "ordinary")  # no reduced single ticket
    over70 = {
        p.kind: applied
        for p, applied in book.select(area="urban", network="bologna", profile="over70")
    }
    assert over70["annual"] == "over70"


def test_a_distrusted_price_is_never_offered_as_a_reduced_one() -> None:
    book = FareBook.load()
    picked = {
        p.kind: (p.price, applied)
        for p, applied in book.select(
            area="extraurban", network="bologna", profile="over70", zones=8
        )
    }
    assert picked["annual"] == (660.0, "ordinary")


def test_product_to_dict_shows_price_per_ride() -> None:
    book = FareBook.load()
    carnet = next(
        p for p, _ in book.select(area="urban", network="bologna") if p.kind == "carnet10"
    )
    data = carnet.to_dict()
    assert data["rides"] == 10 and data["pricePerRide"] == 1.9


def test_monthly_rides() -> None:
    assert monthly_rides(30, 5, 2) == 30
    assert monthly_rides(None, 5, 2) == pytest.approx(43.33, abs=0.01)


def options(
    area: str = "urban",
    network: str = "bologna",
    profile: str = "ordinary",
    zones: int | None = None,
):  # type: ignore[no-untyped-def]
    return FareBook.load().select(area=area, network=network, profile=profile, zones=zones)


def test_compare_picks_singles_for_rare_trips_and_a_pass_for_commuters() -> None:
    rare = compare(options(), 4, travel_days=4)
    assert rare["cheapest"]["kind"] in {"single", "carnet10"}
    commuter = compare(options(), 44, travel_days=22)
    assert commuter["cheapest"]["kind"] in {"annual", "annual_anonymous", "monthly_anonymous"}
    assert [o["monthlyCost"] for o in commuter["options"]] == sorted(
        o["monthlyCost"] for o in commuter["options"]
    )


def test_compare_break_even() -> None:
    result = compare(options(), 30, travel_days=15)
    assert result["breakEvenRidesPerMonth"] == 17  # 39 EUR monthly / 2.30 EUR single


def test_compare_needs_positive_rides() -> None:
    with pytest.raises(ValidationError):
        compare(options(), 0)


def test_compare_skips_day_tickets_without_travel_days() -> None:
    kinds = {o["kind"] for o in compare(options(), 10)["options"]}
    assert "day" not in kinds and "ecoticket" not in kinds
