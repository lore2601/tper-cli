"""``tper claim``: file a complaint (reclamo) with TPER through its official web form."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

from tper_cli import config as cfg
from tper_cli.claim import form
from tper_cli.claim import profile as profile_store
from tper_cli.claim.model import Claim
from tper_cli.claim.profile import Profile
from tper_cli.commands._common import pass_app, write_options
from tper_cli.context import AppContext
from tper_cli.errors import PolicyError, UpstreamError, ValidationError
from tper_cli.output import info
from tper_cli.views import CLAIMS

REQUIRED_CONTROLS = (
    "txtCognome",
    "txtNome",
    "txtDataNascita",
    "cboNazioneNascita",
    "txtIndirizzo",
    "txtNumeroCivico",
    "txtCap",
    "cboNazione",
    "txtEmail",
    "btAvanti1",
)


@click.group("claim")
def group() -> None:
    """Prepare and send a complaint to TPER (experimental).

    Complaints are sent with your personal data, from your own computer, through the same
    web form you would use in a browser. Be polite and factual.
    """


# ------------------------------------------------------------------------ profile


@group.group("profile")
def profile() -> None:
    """Your personal data, stored locally (mode 0600) and never printed."""


PROMPTS: tuple[tuple[str, str], ...] = (
    ("surname", "Surname"),
    ("name", "Name"),
    ("gender", "Gender (M/F)"),
    ("birth_date", "Birth date (DD/MM/YYYY)"),
    ("birth_nation", "Birth country (as in the TPER form, e.g. ITALIA)"),
    ("birth_municipality", "Birth municipality"),
    ("tax_code", "Codice fiscale"),
    ("address", "Address (street)"),
    ("house_number", "House number"),
    ("postal_code", "CAP"),
    ("nation", "Country of residence (e.g. ITALIA)"),
    ("province", "Province (e.g. BOLOGNA)"),
    ("municipality", "Municipality"),
    ("locality", "Locality / frazione (optional)"),
    ("email", "Email"),
    ("phone", "Mobile phone (optional)"),
)


@profile.command("init")
@click.option("--force", is_flag=True, help="Overwrite an existing profile.")
@pass_app
def profile_init(app: AppContext, force: bool) -> None:
    """Ask for your personal data and store it locally."""
    path = cfg.profile_path(app.env)
    if path.exists() and not force:
        raise ValidationError(
            f"{path} already exists", hint="Use --force to overwrite it.", reason="profileExists"
        )
    if not sys.stdin.isatty():
        raise ValidationError(
            "`claim profile init` is interactive",
            hint="Run it yourself in a terminal: your personal data is never typed by an agent.",
            reason="notInteractive",
        )
    answers: dict[str, Any] = {}
    optional = {"locality", "phone"}
    for key, label in PROMPTS:
        answers[key] = (
            click.prompt(label, default="", show_default=False)
            if key in optional
            else click.prompt(label)
        )
    answers["contact_by_phone"] = bool(answers["phone"]) and click.confirm(
        "Ask TPER to also contact you by phone?", default=False
    )
    saved = Profile(**answers).validate(app.now().date())
    profile_store.save(saved, path)
    app.printer.item({"saved": True, "path": str(path)})


@profile.command("show")
@pass_app
def profile_show(app: AppContext) -> None:
    """Which profile fields are set (values are masked)."""
    loaded = profile_store.load(cfg.profile_path(app.env), app.now().date())
    app.printer.item({"path": str(cfg.profile_path(app.env)), **loaded.masked()})


@profile.command("path")
@pass_app
def profile_path(app: AppContext) -> None:
    """Where the profile file lives."""
    path = cfg.profile_path(app.env)
    app.printer.item({"path": str(path), "exists": path.is_file()})


@profile.command("delete")
@click.option("-y", "--yes", is_flag=True, help="Do not ask for confirmation.")
@pass_app
def profile_delete(app: AppContext, yes: bool) -> None:
    """Delete the stored personal data."""
    path = cfg.profile_path(app.env)
    if path.is_file() and (yes or click.confirm(f"Delete {path}?", default=False, err=True)):
        path.unlink()
        app.printer.item({"deleted": True})
    else:
        app.printer.item({"deleted": False})


# ------------------------------------------------------------------------ claims


def _read_text(text: str | None, text_file: str | None) -> str:
    if text_file:
        return sys.stdin.read() if text_file == "-" else Path(text_file).read_text(encoding="utf-8")
    if text is None:
        raise ValidationError("Give the complaint text with --text or --text-file")
    return text


@group.command("file")
@click.option("--service", default="Servizio bus", show_default=True, help="Type of service.")
@click.option("--kind", default="Servizio", show_default=True, help="Type of communication.")
@click.option(
    "--category",
    required=True,
    help='e.g. "Corsa non effettuata", "Frequenza o orario non rispettato".',
)
@click.option("--basin", required=True, help="Bologna or Ferrara.")
@click.option("--line", required=True, help="Bus line, e.g. 20.")
@click.option("--direction", default="", help="Direction of the bus.")
@click.option("--vehicle", default="", help="Vehicle number, if known.")
@click.option("--driver", default="", help="Driver number, if known.")
@click.option(
    "--date",
    "event_date",
    required=True,
    metavar="DATE",
    help="When it happened: DD/MM/YYYY, yesterday, -2d ...",
)
@click.option("--time", "event_time", required=True, metavar="HH:MM", help="At what time.")
@click.option("--place", required=True, help='Where, e.g. "fermata 4476".')
@click.option("--text", default=None, help="The complaint, 20-3000 characters.")
@click.option("--text-file", default=None, help="Read the complaint from a file, or - for stdin.")
@click.option("--no-compensation", is_flag=True, help="Do not ask for an indemnity (indennizzo).")
@click.option(
    "--allow-duplicate", is_flag=True, help="Send even if the same complaint was filed before."
)
@write_options
@pass_app
def file_claim(
    app: AppContext,
    service: str,
    kind: str,
    category: str,
    basin: str,
    line: str,
    direction: str,
    vehicle: str,
    driver: str,
    event_date: str,
    event_time: str,
    place: str,
    text: str | None,
    text_file: str | None,
    no_compensation: bool,
    allow_duplicate: bool,
    dry_run: bool,
    yes: bool,
) -> None:
    """Send a complaint. Preview with --dry-run, then confirm (or pass --yes).

    The wizard options (service, category, basin, line) must match the labels shown by the
    TPER form; if one does not, the error lists the valid options. Agents: never invent a
    complaint, and only send what the user has approved word for word.
    """
    today = app.now().date()
    claim = Claim(
        service=service,
        kind=kind,
        category=category,
        basin=basin,
        line=line.strip().upper(),
        direction=direction,
        vehicle=vehicle,
        driver=driver,
        event_date=event_date,
        event_time=event_time,
        place=place,
        text=_read_text(text, text_file),
        compensation=not no_compensation,
    ).validate(today)
    owner = profile_store.load(cfg.profile_path(app.env), today)
    fingerprint = claim.fingerprint()
    earlier = app.ledger.find(fingerprint)
    if earlier and not allow_duplicate:
        raise PolicyError(
            f"This complaint was already sent on {earlier['submittedAt']}",
            hint="Use --allow-duplicate only if you really mean to send it again.",
            reason="duplicateClaim",
            details={"fingerprint": fingerprint},
        )
    request = {"claim": claim.summary(), "profile": owner.masked(), "fingerprint": fingerprint}
    summary = (
        f"Complaint about line {claim.line} on {claim.event_date} {claim.event_time}, "
        f"from {owner.name} {owner.surname}"
    )
    if not app.guard_write(
        action="send a complaint to TPER",
        request=request,
        yes=yes,
        dry_run=dry_run,
        summary=summary,
    ):
        return
    wizard = form.open_form(app.http)
    info("step 1/3: personal data")
    wizard.personal_data(owner)
    info("step 2/3: communication data")
    wizard.communication(claim)
    info("step 3/3: sending")
    confirmation = wizard.confirm()
    app.ledger.add(fingerprint, app.now(), claim.line, claim.event_date)
    app.printer.item({"submitted": True, "fingerprint": fingerprint, "confirmation": confirmation})


@group.command("history")
@pass_app
def history(app: AppContext) -> None:
    """Complaints sent from this computer (kept locally)."""
    rows = app.ledger.all()
    app.printer.items(rows, CLAIMS, kind="claims", extra={"count": len(rows)})


@group.command("check")
@pass_app
def check(app: AppContext) -> None:
    """Check that the TPER complaint form is reachable and still has the expected fields.

    Only reads the first page of the form: nothing is sent.
    """
    wizard = form.open_form(app.http)
    present = {name: wizard.has(name) for name in REQUIRED_CONTROLS}
    missing = [n for n, ok in present.items() if not ok]
    if missing:
        raise UpstreamError(
            "The complaint form no longer has: " + ", ".join(missing),
            service=form.SERVICE,
            reason="formChanged",
            hint="TPER changed the form. Please report it.",
        )
    app.printer.item({"url": form.URL, "ok": True, "missingControls": []})
