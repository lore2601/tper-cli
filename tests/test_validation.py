from __future__ import annotations

from datetime import date

import pytest

from tper_cli import validation as v
from tper_cli.errors import ValidationError

TODAY = date(2026, 10, 22)


@pytest.mark.parametrize("value", ["4476", " 1 ", "999999"])
def test_stop_code_accepts_numbers(value: str) -> None:
    assert v.stop_code(value) == value.strip()


@pytest.mark.parametrize("value", ["", "abc", "12345678", "44 76", "4476; DROP", "-1"])
def test_stop_code_rejects_everything_else(value: str) -> None:
    with pytest.raises(ValidationError):
        v.stop_code(value)


def test_is_stop_code() -> None:
    assert v.is_stop_code("4476")
    assert not v.is_stop_code("lapidari")


@pytest.mark.parametrize(("value", "expected"), [("11", "11"), ("27a", "27A"), (" 101 ", "101")])
def test_line_code(value: str, expected: str) -> None:
    assert v.line_code(value) == expected


@pytest.mark.parametrize("value", ["", "11/3", "1234567", "a b"])
def test_line_code_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        v.line_code(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("18:30", "1830"), ("1830", "1830"), ("18.30", "1830"), ("9:05", "0905"), ("0:00", "0000")],
)
def test_hhmm(value: str, expected: str) -> None:
    assert v.hhmm(value) == expected


@pytest.mark.parametrize("value", ["25:00", "12:60", "noon", "", "1830pm"])
def test_hhmm_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        v.hhmm(value)


def test_zones_range() -> None:
    assert v.zones(3) == 3
    for bad in (0, 11, -1):
        with pytest.raises(ValidationError):
            v.zones(bad)


def test_coordinates() -> None:
    assert v.latitude(44.5) == 44.5
    assert v.longitude(11.3) == 11.3
    with pytest.raises(ValidationError):
        v.latitude(91)
    with pytest.raises(ValidationError):
        v.longitude(-181)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("today", date(2026, 10, 22)),
        ("yesterday", date(2026, 10, 21)),
        ("-7d", date(2026, 10, 15)),
        ("2026-09-01", date(2026, 9, 1)),
        ("01/09/2026", date(2026, 9, 1)),
    ],
)
def test_parse_date(value: str, expected: date) -> None:
    assert v.parse_date(value, TODAY) == expected


def test_parse_date_rejects_garbage() -> None:
    with pytest.raises(ValidationError):
        v.parse_date("next friday", TODAY)


def test_italian_date_refuses_the_future() -> None:
    assert v.italian_date("yesterday", TODAY) == "21/10/2026"
    with pytest.raises(ValidationError):
        v.italian_date("2026-12-01", TODAY)
    assert v.italian_date("2026-12-01", TODAY, allow_future=True) == "01/12/2026"


def test_tax_code_checks_format_and_check_character() -> None:
    assert v.tax_code("rosmra80a01h501q") == "ROSMRA80A01H501Q"
    with pytest.raises(ValidationError, match="check character"):
        v.tax_code("ROSMRA80A01H501A")
    with pytest.raises(ValidationError, match="format"):
        v.tax_code("ROSMRA80A01")


def test_email_postal_code_phone() -> None:
    assert v.email(" a@b.it ") == "a@b.it"
    assert v.postal_code("40128") == "40128"
    assert v.phone("+39 333 1234567") == "+39 333 1234567"
    for fn, bad in ((v.email, "nope"), (v.postal_code, "4012"), (v.phone, "abc")):
        with pytest.raises(ValidationError):
            fn(bad)
