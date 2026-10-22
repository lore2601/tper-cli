"""Locations of config, cache and state files, and the local policy."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tper_cli.errors import PolicyError, ValidationError

APP_DIR = "tper-cli"
TRUE = {"1", "true", "yes", "on"}

CONFIG_TEMPLATE = """\
# tper-cli configuration. Every key is optional; environment variables override it.

[defaults]
# format = "auto"          # auto (table on a terminal, JSON otherwise) | json | ndjson | table
# fare_profile = "ordinary"  # ordinary | under27 | over65 | over70
# basin = "bologna"        # bologna | ferrara: price list used for extra-urban fares

[policy]
# read_only = false        # true blocks every action that sends data to TPER (claims)
"""

FARE_PROFILES = ("ordinary", "under27", "over65", "over70")
BASINS = ("bologna", "ferrara")


def _env_path(env: Mapping[str, str], var: str, xdg_var: str, fallback: str) -> Path:
    if env.get(var):
        return Path(env[var]).expanduser()
    base = env.get(xdg_var)
    root = Path(base).expanduser() if base else Path.home() / fallback
    return root / APP_DIR


def config_dir(env: Mapping[str, str] | None = None) -> Path:
    return _env_path(env or os.environ, "TPER_CONFIG_DIR", "XDG_CONFIG_HOME", ".config")


def cache_dir(env: Mapping[str, str] | None = None) -> Path:
    return _env_path(env or os.environ, "TPER_CACHE_DIR", "XDG_CACHE_HOME", ".cache")


def state_dir(env: Mapping[str, str] | None = None) -> Path:
    return _env_path(env or os.environ, "TPER_STATE_DIR", "XDG_STATE_HOME", ".local/state")


def config_path(env: Mapping[str, str] | None = None) -> Path:
    env = env or os.environ
    if env.get("TPER_CONFIG"):
        return Path(env["TPER_CONFIG"]).expanduser()
    return config_dir(env) / "config.toml"


def profile_path(env: Mapping[str, str] | None = None) -> Path:
    env = env or os.environ
    if env.get("TPER_PROFILE_FILE"):
        return Path(env["TPER_PROFILE_FILE"]).expanduser()
    return config_dir(env) / "profile.toml"


@dataclass(frozen=True)
class Policy:
    read_only: bool = False

    def require_writable(self, what: str = "this action") -> None:
        if self.read_only:
            raise PolicyError(
                f"Read-only mode is on: {what} is blocked",
                hint="Unset TPER_READ_ONLY or set policy.read_only = false in config.toml.",
                reason="readOnly",
            )


@dataclass
class Config:
    defaults: dict[str, Any] = field(default_factory=dict)
    policy: Policy = field(default_factory=Policy)
    path: Path | None = None

    @property
    def fare_profile(self) -> str:
        return str(self.defaults.get("fare_profile", "ordinary"))

    @property
    def basin(self) -> str | None:
        value = self.defaults.get("basin")
        return str(value) if value else None


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in TRUE


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = env or os.environ
    path = config_path(env)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            raise ValidationError(
                f"Cannot read {path}: {exc}", hint="Fix the file or run `tper config init --force`."
            ) from exc
    defaults = dict(data.get("defaults") or {})
    if env.get("TPER_FORMAT"):
        defaults["format"] = env["TPER_FORMAT"]
    if env.get("TPER_FARE_PROFILE"):
        defaults["fare_profile"] = env["TPER_FARE_PROFILE"]
    if env.get("TPER_BASIN"):
        defaults["basin"] = env["TPER_BASIN"]
    if str(defaults.get("fare_profile", "ordinary")) not in FARE_PROFILES:
        raise ValidationError(
            f"Invalid fare_profile {defaults['fare_profile']!r}",
            hint=f"Use one of {', '.join(FARE_PROFILES)}.",
        )
    if defaults.get("basin") and str(defaults["basin"]) not in BASINS:
        raise ValidationError(
            f"Invalid basin {defaults['basin']!r}", hint=f"Use one of {', '.join(BASINS)}."
        )
    policy_data = data.get("policy") or {}
    read_only = (
        _truthy(env["TPER_READ_ONLY"])
        if "TPER_READ_ONLY" in env
        else bool(policy_data.get("read_only", False))
    )
    return Config(defaults=defaults, policy=Policy(read_only=read_only), path=path)


def write_private(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` creating parents, with ``0600`` permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    path.chmod(0o600)
