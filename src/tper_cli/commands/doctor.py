"""``tper doctor``: is everything the CLI depends on reachable and as expected?"""

from __future__ import annotations

from collections.abc import Callable

import click

from tper_cli import config as cfg
from tper_cli.claim import form
from tper_cli.commands._common import pass_app
from tper_cli.commands.claim import REQUIRED_CONTROLS
from tper_cli.context import AppContext
from tper_cli.data.opendata import PAGE_URL
from tper_cli.errors import TperError
from tper_cli.output import col
from tper_cli.webforms import load
from tper_cli.zones import SERVICE as ZONES_SERVICE
from tper_cli.zones import URL as ZONES_URL

COLUMNS = [col("check", "check"), col("ok", "ok"), col("detail", "detail", 80)]


def _run(name: str, fn: Callable[[], str]) -> dict[str, object]:
    try:
        return {"check": name, "ok": True, "detail": fn()}
    except TperError as exc:
        return {"check": name, "ok": False, "detail": exc.message}


@click.command("doctor")
@click.option("--offline", is_flag=True, help="Only check local files, do not touch the network.")
@pass_app
def group(app: AppContext, offline: bool) -> None:
    """Check the local setup and, unless --offline, every online service the CLI uses."""
    checks: list[dict[str, object]] = []

    def profile_check() -> str:
        path = cfg.profile_path(app.env)
        return f"profile found at {path}" if path.is_file() else "no complaint profile (optional)"

    checks.append(_run("local: complaint profile", profile_check))
    cached = [r["dataset"] for r in app.store.status() if r["cached"]]
    checks.append(
        {"check": "local: open data cache", "ok": True, "detail": f"{len(cached)} datasets cached"}
    )
    if not offline:
        checks.append(
            _run(
                "hellobus",
                lambda: f"{len(app.hellobus.arrivals('4476').arrivals)} arrivals at stop 4476",
            )
        )
        checks.append(_run("open data", lambda: f"{len(app.store.discover())} datasets published"))
        checks.append(_run("news feed", lambda: f"{len(app.news.fetch('front'))} items"))
        checks.append(_run("rail notices", lambda: f"{len(app.infomobility.notices())} notices"))
        checks.append(
            _run(
                "zone calculator",
                lambda: "form loaded" if load(app.http, ZONES_URL, ZONES_SERVICE) else "",
            )
        )

        def claim_form() -> str:
            wizard = form.open_form(app.http)
            missing = [n for n in REQUIRED_CONTROLS if not wizard.has(n)]
            if missing:
                raise TperError("missing controls: " + ", ".join(missing))
            return "complaint form has the expected fields"

        checks.append(_run("complaint form", claim_form))
    ok = all(bool(c["ok"]) for c in checks)
    app.printer.items(checks, COLUMNS, kind="checks", extra={"ok": ok, "openDataPage": PAGE_URL})
