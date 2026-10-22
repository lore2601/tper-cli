"""``tper data``: the local copy of the TPER open data."""

from __future__ import annotations

import click

from tper_cli.commands._common import pass_app
from tper_cli.context import AppContext
from tper_cli.data.opendata import ATTRIBUTION, DATASETS, LICENSE, LICENSE_URL, PAGE_URL
from tper_cli.views import DATASETS as DATASET_COLUMNS


@click.group("data")
def group() -> None:
    """Manage the cached TPER open data (downloaded on first use)."""


@group.command("status")
@pass_app
def status(app: AppContext) -> None:
    """Which datasets are cached, and which version."""
    rows = app.store.status()
    app.printer.items(
        rows,
        DATASET_COLUMNS,
        kind="datasets",
        extra={
            "directory": str(app.store.dir),
            "license": LICENSE,
            "licenseUrl": LICENSE_URL,
            "attribution": ATTRIBUTION,
            "source": PAGE_URL,
        },
    )


@group.command("update")
@click.option("--force", is_flag=True, help="Download again even if the version is current.")
@click.argument("names", nargs=-1, type=click.Choice(sorted(DATASETS)))
@pass_app
def update(app: AppContext, force: bool, names: tuple[str, ...]) -> None:
    """Download new versions of the open data (all datasets, or only NAMES)."""
    versions = app.store.update(list(names) or None, force=force)
    app.printer.item({"updated": versions, "directory": str(app.store.dir)})


@group.command("clear")
@pass_app
def clear(app: AppContext) -> None:
    """Delete the cached open data."""
    app.printer.item({"removedFiles": app.store.clear(), "directory": str(app.store.dir)})
