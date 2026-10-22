"""Validation of every user-supplied argument.

Arguments are untrusted (agents generate them), so each one is checked here
before it reaches a URL, a form field or the filesystem.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from tper_cli.errors import ValidationError

STOP_RE = re.compile(r"^\d{1,6}$")
LINE_RE = re.compile(r"^[0-9A-Za-z]{1,6}$")
TIME_RE = re.compile(r"^(\d{1,2})[:.]?(\d{2})$")
ZONE_CODE_RE = re.compile(r"^\d{3}$")
TAX_CODE_RE = re.compile(r"^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
POSTAL_CODE_RE = re.compile(r"^\d{5}$")
PHONE_RE = re.compile(r"^\+?[0-9 ]{6,16}$")
DATE_IT_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
PERIOD_DAYS_RE = re.compile(r"^-(\d{1,3})d$")


def stop_code(value: str) -> str:
    value = str(value).strip()
    if not STOP_RE.match(value):
        raise ValidationError(
            f"Invalid stop code {value!r}",
            hint="Stop codes are numbers such as 4476. Find one with `tper bus stops search NAME`.",
        )
    return value


def is_stop_code(value: str) -> bool:
    return bool(STOP_RE.match(str(value).strip()))


def line_code(value: str) -> str:
    value = str(value).strip().upper()
    if not LINE_RE.match(value):
        raise ValidationError(
            f"Invalid line {value!r}", hint="Lines look like 11, 27A or 101 (letters and digits)."
        )
    return value


def hhmm(value: str) -> str:
    """Normalise ``18:30``, ``18.30`` or ``1830`` to ``1830``."""
    match = TIME_RE.match(str(value).strip())
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise ValidationError(
            f"Invalid time {value!r}", hint="Use 24-hour time such as 18:30 or 1830."
        )
    return f"{int(match.group(1)):02d}{match.group(2)}"


def zones(value: int) -> int:
    if not 1 <= int(value) <= 10:
        raise ValidationError(
            f"Invalid number of zones: {value}", hint="Extra-urban fares go from 1 to 10 zones."
        )
    return int(value)


def latitude(value: float) -> float:
    if not -90 <= value <= 90:
        raise ValidationError(f"Invalid latitude {value}")
    return value


def longitude(value: float) -> float:
    if not -180 <= value <= 180:
        raise ValidationError(f"Invalid longitude {value}")
    return value


def parse_date(value: str, today: date) -> date:
    """``today``, ``yesterday``, ``-7d``, ``YYYY-MM-DD`` or ``DD/MM/YYYY``."""
    text = str(value).strip().lower()
    if text == "today":
        return today
    if text == "yesterday":
        return today - timedelta(days=1)
    rel = PERIOD_DAYS_RE.match(text)
    if rel:
        return today - timedelta(days=int(rel.group(1)))
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError(
        f"Invalid date {value!r}", hint="Use today, yesterday, -7d, YYYY-MM-DD or DD/MM/YYYY."
    )


def italian_date(value: str, today: date, *, allow_future: bool = False) -> str:
    """Validate and return ``DD/MM/YYYY`` (the format of the TPER forms)."""
    parsed = parse_date(value, today)
    if not allow_future and parsed > today:
        raise ValidationError(f"The date {parsed.isoformat()} is in the future")
    return parsed.strftime("%d/%m/%Y")


def tax_code(value: str) -> str:
    """Validate an Italian *codice fiscale* (format and check character)."""
    code = str(value).strip().upper()
    if not TAX_CODE_RE.match(code):
        raise ValidationError("Invalid codice fiscale format")
    odd = {
        **dict(zip("0123456789", (1, 0, 5, 7, 9, 13, 15, 17, 19, 21), strict=True)),
        **dict(
            zip(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                (
                    1,
                    0,
                    5,
                    7,
                    9,
                    13,
                    15,
                    17,
                    19,
                    21,
                    2,
                    4,
                    18,
                    20,
                    11,
                    3,
                    6,
                    8,
                    12,
                    14,
                    16,
                    10,
                    22,
                    25,
                    24,
                    23,
                ),
                strict=True,
            )
        ),
    }
    even = {c: i for i, c in enumerate("0123456789")} | {
        c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    }
    total = sum(odd[c] if i % 2 == 0 else even[c] for i, c in enumerate(code[:15]))
    if code[15] != chr(ord("A") + total % 26):
        raise ValidationError("Invalid codice fiscale: the check character does not match")
    return code


def email(value: str) -> str:
    value = str(value).strip()
    if not EMAIL_RE.match(value):
        raise ValidationError(f"Invalid email address {value!r}")
    return value


def postal_code(value: str) -> str:
    value = str(value).strip()
    if not POSTAL_CODE_RE.match(value):
        raise ValidationError(f"Invalid CAP {value!r}", hint="Use 5 digits, e.g. 40128.")
    return value


def phone(value: str) -> str:
    value = str(value).strip()
    if not PHONE_RE.match(value):
        raise ValidationError(f"Invalid phone number {value!r}")
    return value
