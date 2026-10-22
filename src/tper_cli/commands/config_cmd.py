"""``tper config``: effective configuration and locations."""

from __future__ import annotations

import click

from tper_cli import config as cfg
from tper_cli.commands._common import pass_app
from tper_cli.context import AppContext
from tper_cli.errors import ValidationError


@click.group("config")
def group() -> None:
    """Show the effective configuration, or write a commented template."""


@group.command("show")
@pass_app
def show(app: AppContext) -> None:
    """Effective defaults, policy and file locations."""
    app.printer.item(
        {
            "configFile": str(cfg.config_path(app.env)),
            "configFileExists": cfg.config_path(app.env).is_file(),
            "defaults": {
                "format": app.config.defaults.get("format", "auto"),
                "fareProfile": app.config.fare_profile,
                "basin": app.config.basin,
            },
            "policy": {"readOnly": app.policy.read_only},
            "cacheDirectory": str(cfg.cache_dir(app.env)),
            "stateDirectory": str(cfg.state_dir(app.env)),
            "profileFile": str(cfg.profile_path(app.env)),
        }
    )


@group.command("init")
@click.option("--force", is_flag=True, help="Overwrite an existing file.")
@pass_app
def init(app: AppContext, force: bool) -> None:
    """Write a commented config.toml."""
    path = cfg.config_path(app.env)
    if path.exists() and not force:
        raise ValidationError(f"{path} already exists", hint="Use --force to overwrite it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cfg.CONFIG_TEMPLATE, encoding="utf-8")
    app.printer.item({"written": str(path)})
