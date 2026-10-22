"""The personal data a complaint needs, stored locally with ``0600`` permissions."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path

from tper_cli import validation
from tper_cli.config import write_private
from tper_cli.errors import SetupError, ValidationError


@dataclass
class Profile:
    surname: str
    name: str
    gender: str  # M | F
    birth_date: str  # DD/MM/YYYY
    birth_nation: str
    birth_municipality: str
    tax_code: str
    address: str
    house_number: str
    postal_code: str
    nation: str
    province: str
    municipality: str
    locality: str
    email: str
    phone: str
    contact_by_phone: bool = False

    def validate(self, today: date) -> Profile:
        for f in fields(self):
            if f.name in {"locality", "contact_by_phone", "phone"}:
                continue
            if not str(getattr(self, f.name)).strip():
                raise ValidationError(f"Profile field {f.name!r} is empty", reason="profileInvalid")
        self.gender = self.gender.strip().upper()[:1]
        if self.gender not in {"M", "F"}:
            raise ValidationError("gender must be M or F", reason="profileInvalid")
        self.birth_date = validation.italian_date(self.birth_date, today)
        self.tax_code = validation.tax_code(self.tax_code)
        self.email = validation.email(self.email)
        self.postal_code = validation.postal_code(self.postal_code)
        if self.phone:
            self.phone = validation.phone(self.phone)
        if self.contact_by_phone and not self.phone:
            raise ValidationError("contact_by_phone needs a phone number", reason="profileInvalid")
        return self

    def masked(self) -> dict[str, object]:
        """A view that is safe to print: shows which fields are set, never their values."""
        data = asdict(self)
        return {k: (v if isinstance(v, bool) else mask(str(v))) for k, v in data.items()}


def mask(value: str) -> str:
    if not value:
        return ""
    if "@" in value:
        local, _, domain = value.partition("@")
        return f"{local[:1]}***@{domain}"
    return value[:1] + "*" * min(len(value) - 1, 6)


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def save(profile: Profile, path: Path) -> None:
    lines = ["# tper-cli complaint profile. Personal data: keep this file private.", "[profile]"]
    lines += [f"{k} = {_toml_value(v)}" for k, v in asdict(profile).items()]
    write_private(path, "\n".join(lines) + "\n")


def load(path: Path, today: date) -> Profile:
    if not path.is_file():
        raise SetupError(
            "No complaint profile yet",
            hint="Run `tper claim profile init` once to store your personal data locally.",
            reason="profileMissing",
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8")).get("profile", {})
        names = {f.name for f in fields(Profile)}
        return Profile(**{k: v for k, v in data.items() if k in names}).validate(today)
    except (tomllib.TOMLDecodeError, TypeError) as exc:
        raise ValidationError(
            f"The profile file {path} is incomplete or malformed: {exc}",
            hint="Run `tper claim profile init --force`.",
            reason="profileInvalid",
        ) from exc
