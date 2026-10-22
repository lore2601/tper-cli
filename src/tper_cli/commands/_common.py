"""Option decorators and helpers shared by command modules."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import click

from tper_cli import search, validation
from tper_cli.context import AppContext
from tper_cli.data.catalog import Stop
from tper_cli.errors import AmbiguousError, NotFoundError

F = TypeVar("F", bound=Callable[..., Any])

pass_app = click.make_pass_decorator(AppContext)


def write_options(fn: F) -> F:
    fn = click.option("--dry-run", is_flag=True, help="Print what would be sent and exit.")(fn)
    fn = click.option(
        "-y",
        "--yes",
        is_flag=True,
        help="Do not ask for confirmation (required when not on a TTY).",
    )(fn)
    return fn


def limit_option(default: int) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        return click.option(
            "-n",
            "--limit",
            type=click.IntRange(min=1),
            default=default,
            show_default=True,
            help="Maximum number of results.",
        )(fn)

    return decorator


def resolve_stop(app: AppContext, ref: str) -> tuple[str, Stop | None]:
    """A stop code, or a name that identifies exactly one stop.

    Returns the code and, when the open data is at hand, the stop itself. A numeric code
    never forces a download: the stop is only looked up if the table is already cached.
    """
    if validation.is_stop_code(ref):
        code = validation.stop_code(ref)
        return code, app.catalog.stop_if_cached(code)
    ranked = app.catalog.search_stops(ref)
    if not ranked:
        raise NotFoundError(
            f"No stop matches {ref!r}",
            hint="Try fewer words, or `tper bus stops near LAT LON`.",
            reason="stopNotFound",
        )
    top = ranked[0][0]
    best = [s for score, s in ranked if score >= top - 1e-9]
    exact = search.normalize(ref) == search.normalize(best[0].name)
    if len(best) == 1 and (exact or len(ranked) == 1 or top - ranked[1][0] >= 10):
        return best[0].code, best[0]
    raise AmbiguousError(
        f"{ref!r} matches {len(ranked)} stops: pick one by code",
        hint="Re-run with the stop code, e.g. `tper bus arrivals 4476`.",
        details={"candidates": [stop_view(s) for _, s in ranked[:8]]},
    )


def stop_view(stop: Stop) -> dict[str, object]:
    return {
        "code": stop.code,
        "name": stop.name,
        "address": stop.address,
        "municipality": stop.municipality,
        "zone": stop.zone,
    }
