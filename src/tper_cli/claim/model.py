"""A complaint, validated before anything is sent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from tper_cli import validation
from tper_cli.errors import ValidationError

MIN_TEXT = 20
MAX_TEXT = 3000


@dataclass
class Claim:
    service: str  # e.g. "Servizio bus"
    kind: str  # "Tipologia", e.g. "Servizio"
    category: str  # e.g. "Corsa non effettuata"
    basin: str  # e.g. "Bologna"
    line: str
    direction: str
    vehicle: str
    driver: str
    event_date: str  # DD/MM/YYYY
    event_time: str  # HH:MM
    place: str
    text: str
    compensation: bool = True

    def validate(self, today: date) -> Claim:
        for name in (
            "service",
            "kind",
            "category",
            "basin",
            "line",
            "event_date",
            "event_time",
            "place",
        ):
            if not str(getattr(self, name)).strip():
                raise ValidationError(f"The claim needs a value for {name!r}")
        self.event_date = validation.italian_date(self.event_date, today)
        stamp = validation.hhmm(self.event_time)
        self.event_time = f"{stamp[:2]}:{stamp[2:]}"
        self.text = self.text.strip()
        if not MIN_TEXT <= len(self.text) <= MAX_TEXT:
            raise ValidationError(
                f"The complaint text must be {MIN_TEXT}-{MAX_TEXT} characters "
                f"(got {len(self.text)})",
                hint="Describe what happened, when and where. Stay polite and factual.",
            )
        return self

    def fingerprint(self) -> str:
        import hashlib

        raw = "|".join(
            (
                self.service,
                self.category,
                self.basin,
                self.line,
                self.event_date,
                self.event_time,
                self.text,
            )
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def summary(self) -> dict[str, object]:
        return {
            "service": self.service,
            "kind": self.kind,
            "category": self.category,
            "basin": self.basin,
            "line": self.line,
            "direction": self.direction,
            "vehicle": self.vehicle,
            "driver": self.driver,
            "date": self.event_date,
            "time": self.event_time,
            "place": self.place,
            "compensation": self.compensation,
            "text": self.text,
        }
