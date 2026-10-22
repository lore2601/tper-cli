"""Root command group, global options and the error-handling entry point."""

from __future__ import annotations

import os
import sys
import traceback
from collections.abc import Sequence

import click

from tper_cli import __version__
from tper_cli.config import load_config
from tper_cli.context import AppContext, rome_now
from tper_cli.errors import ExitCode, TperError, ValidationError
from tper_cli.output import FORMATS, Printer, print_error

_state = {"format": "auto", "debug": False}

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"], "max_content_width": 100}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(FORMATS),
    default=None,
    help="Output format. 'auto' = table on a terminal, JSON otherwise.  [env: TPER_FORMAT]",
)
@click.option(
    "--fields",
    default=None,
    metavar="LIST",
    help="Comma-separated fields to keep, dotted paths allowed (e.g. line,time).",
)
@click.option("--raw", is_flag=True, help="Return less processed data where supported.")
@click.option("--debug", is_flag=True, help="Show tracebacks for unexpected errors.")
@click.version_option(__version__, "-V", "--version", prog_name="tper")
@click.pass_context
def cli(ctx: click.Context, fmt: str | None, fields: str | None, raw: bool, debug: bool) -> None:
    """tper: TPER public transport (Bologna, Ferrara) for humans and AI agents.

    \b
    Output is JSON when stdout is not a terminal. Errors are JSON objects on
    stderr. Exit codes: 0 ok, 1 service or network error, 2 setup needed
    (open data, profile), 3 invalid input, 4 blocked by policy or missing --yes,
    5 internal error.

    \b
    Try:  tper bus arrivals 4476
          tper bus stops search "stazione centrale"
          tper fare quote --from Bologna --to "San Giovanni in Persiceto"
          tper news --category bologna
    """
    _state["debug"] = debug
    env = dict(os.environ)
    config = load_config(env)
    chosen = fmt or env.get("TPER_FORMAT") or str(config.defaults.get("format", "auto"))
    if chosen not in FORMATS:
        raise ValidationError(f"Invalid format {chosen!r}", hint=f"Use one of {', '.join(FORMATS)}")
    _state["format"] = chosen
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else []
    ctx.obj = AppContext(
        config=config,
        printer=Printer(chosen, field_list),
        raw=raw,
        debug=debug,
        env=env,
        clock=lambda: rome_now(),  # looked up at call time so tests can freeze it
    )


def _register() -> None:
    from tper_cli.commands import (
        bus,
        claim,
        config_cmd,
        data_cmd,
        doctor,
        fare,
        news,
        rail,
        schema,
    )

    for module in (bus, rail, fare, news, claim, data_cmd, config_cmd, doctor, schema):
        cli.add_command(module.group)


_register()


def run(argv: Sequence[str] | None = None) -> int:
    """Invoke the CLI and translate every failure into an exit code."""
    try:
        result = cli.main(
            args=list(argv) if argv is not None else None, prog_name="tper", standalone_mode=False
        )
        return int(result) if isinstance(result, int) else int(ExitCode.OK)
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    except click.exceptions.Abort:
        print_error(
            {"error": {"exitCode": 130, "reason": "aborted", "message": "Aborted"}},
            str(_state["format"]),
        )
        return 130
    except click.UsageError as exc:
        no_args = getattr(click.exceptions, "NoArgsIsHelpError", None)
        if no_args is not None and isinstance(exc, no_args):
            exc.show()
            return int(ExitCode.OK)
        if sys.stderr.isatty():
            exc.show()
        else:
            err = ValidationError(exc.format_message(), hint="Run the command with --help.")
            print_error(err.to_dict(), "json")
        return int(ExitCode.VALIDATION)
    except TperError as exc:
        print_error(exc.to_dict(), str(_state["format"]))
        return int(exc.exit_code)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        if _state["debug"]:
            traceback.print_exc()
        payload = {
            "error": {
                "exitCode": int(ExitCode.INTERNAL),
                "reason": "internal",
                "message": f"{type(exc).__name__}: {exc}",
                "hint": "Re-run with --debug for a traceback and report it as a bug.",
            }
        }
        print_error(payload, str(_state["format"]))
        return int(ExitCode.INTERNAL)
