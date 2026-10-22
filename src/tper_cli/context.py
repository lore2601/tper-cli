"""Shared state for commands: clock, HTTP, open data, services and the write guard."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from typing import Any
from zoneinfo import ZoneInfo

import click

from tper_cli import config as cfg
from tper_cli.claim.ledger import Ledger
from tper_cli.config import Config, Policy
from tper_cli.data.catalog import Catalog
from tper_cli.data.opendata import OpenDataStore
from tper_cli.errors import ConfirmationRequired
from tper_cli.hellobus import HelloBus
from tper_cli.http import Http
from tper_cli.infomobility import Infomobility
from tper_cli.news import NewsFeeds
from tper_cli.output import Printer
from tper_cli.rfi import Rfi
from tper_cli.zones import ZoneCalculator

ROME = ZoneInfo("Europe/Rome")


def rome_now() -> datetime:
    return datetime.now(ROME)


@dataclass
class AppContext:
    config: Config
    printer: Printer
    raw: bool = False
    debug: bool = False
    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    clock: Callable[[], datetime] = rome_now
    http: Http = field(default_factory=Http)

    @property
    def policy(self) -> Policy:
        return self.config.policy

    def now(self) -> datetime:
        return self.clock()

    @cached_property
    def store(self) -> OpenDataStore:
        return OpenDataStore(self.http, cfg.cache_dir(self.env), self.now)

    @cached_property
    def catalog(self) -> Catalog:
        return Catalog(self.store)

    @cached_property
    def hellobus(self) -> HelloBus:
        return HelloBus(self.http)

    @cached_property
    def zones(self) -> ZoneCalculator:
        return ZoneCalculator(self.http, self.catalog, cfg.cache_dir(self.env), self.now)

    @cached_property
    def news(self) -> NewsFeeds:
        return NewsFeeds(self.http)

    @cached_property
    def infomobility(self) -> Infomobility:
        return Infomobility(self.http)

    @cached_property
    def rfi(self) -> Rfi:
        return Rfi(self.http, cfg.cache_dir(self.env), self.now)

    @cached_property
    def ledger(self) -> Ledger:
        return Ledger(cfg.state_dir(self.env))

    # ------------------------------------------------------------------ writes

    def guard_write(
        self, *, action: str, request: dict[str, Any], yes: bool, dry_run: bool, summary: str
    ) -> bool:
        """Apply read-only mode, ``--dry-run`` and confirmation. True means: go ahead."""
        self.policy.require_writable(action)
        if dry_run:
            self.printer.item({"dryRun": True, "action": action, "request": request})
            return False
        confirm(summary, yes=yes, action=action)
        return True


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


def confirm(summary: str, *, yes: bool, action: str) -> None:
    if yes:
        return
    if _interactive():
        click.echo(summary, err=True)
        if not click.confirm("Send it to TPER?", default=False, err=True):
            raise ConfirmationRequired("Cancelled by user", reason="cancelled")
        return
    raise ConfirmationRequired(
        f"{action} needs confirmation",
        hint="Review the action (use --dry-run to preview it), then re-run with --yes.",
        details={"action": action},
    )
