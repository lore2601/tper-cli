"""Fill and submit the TPER complaint wizard over plain HTTP.

https://solweb.tper.it/web/communications/complaints.aspx is an ASP.NET WebForms
wizard with three steps (personal data, communication data, summary). Each user
action is a form POST that carries the page state back, exactly what
:mod:`tper_cli.webforms` does, so no browser is involved.

The control names come from the form itself (they match the ids used by TPER's own
page). If TPER renames a control the session stops with ``formChanged`` instead of
guessing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from tper_cli.claim import telerik
from tper_cli.claim.model import Claim
from tper_cli.claim.profile import Profile
from tper_cli.errors import UpstreamError
from tper_cli.http import Http
from tper_cli.webforms import WebFormPage, load, submit

URL = "https://solweb.tper.it/web/communications/complaints.aspx"
SERVICE = "tper-claims"
PREFIX = "ctl00$ContentPlaceHolderMain$"
ID_PREFIX = "ctl00_ContentPlaceHolderMain_"
ERROR_CLASSES = ("error", "validation", "alert", "msg")


def ctrl(name: str) -> str:
    return PREFIX + name


def state_name(name: str) -> str:
    return f"{ID_PREFIX}{name}_ClientState"


def text_state(value: str) -> str:
    return json.dumps(
        {
            "enabled": True,
            "emptyMessage": "",
            "validationText": value,
            "valueAsString": value,
            "lastSetTextBoxValue": value,
        }
    )


def date_state(value: str) -> str:
    day, month, year = value.split("/")
    iso = f"{year}-{month}-{day}-00-00-00"
    return json.dumps(
        {
            "enabled": True,
            "emptyMessage": "",
            "validationText": iso,
            "valueAsString": iso,
            "minDateStr": "1900-01-01-00-00-00",
            "maxDateStr": "2099-12-31-00-00-00",
            "lastSetTextBoxValue": value,
        }
    )


def time_state(value: str) -> str:
    hour, minute = value.split(":")
    stamp = f"1900-01-01-{hour}-{minute}-00"
    return json.dumps(
        {
            "enabled": True,
            "emptyMessage": "",
            "validationText": stamp,
            "valueAsString": stamp,
            "minDateStr": "1900-01-01-00-00-00",
            "maxDateStr": "2099-12-31-00-00-00",
            "lastSetTextBoxValue": value,
        }
    )


@dataclass
class Wizard:
    """State of a conversation with the wizard."""

    http: Http
    page: WebFormPage
    filled: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------ field setters

    def _post(
        self, values: dict[str, str], *, button: str | None = None, target: str | None = None
    ) -> None:
        pair = None
        if button:
            node = self.page.root.by_id(f"{ID_PREFIX}{button}_input")
            if node is None or not node.get("name"):
                raise UpstreamError(
                    f"The complaint form has no {button} button",
                    service=SERVICE,
                    reason="formChanged",
                    hint="TPER changed the form. Please report it.",
                )
            pair = (node.get("name"), node.get("value", "Avanti"))
        self.filled.update(values)
        self.page = submit(self.http, self.page, values, button=pair, event_target=target)
        # Whatever the server did with the page, what we filled in stays filled in.
        self.page.fields.update(self.filled)

    def fill(self, values: dict[str, str]) -> None:
        self.filled.update(values)
        self.page.fields.update(values)

    def untick(self, name: str) -> None:
        self.filled.pop(ctrl(name), None)
        self.page.fields.pop(ctrl(name), None)

    def text(self, name: str, value: str, *, kind: str = "text") -> dict[str, str]:
        """Form fields for a text box (``text``) or a Telerik date / time picker."""
        if kind in {"date", "time"}:
            state = date_state(value) if kind == "date" else time_state(value)
            return {
                ctrl(name): state.split('"valueAsString": "')[1].split('"')[0],
                ctrl(f"{name}$dateInput"): value,
                state_name(f"{name}_dateInput"): state,
                state_name(name): "",
            }
        return {ctrl(name): value, state_name(name): text_state(value)}

    def choose(self, name: str, text: str) -> None:
        """Select an option of a combo / drop-down and let the form react (postback)."""
        combos = telerik.discover(self.page.markup, self.page.root)
        combo = telerik.require(combos, ctrl(name))
        choice = telerik.pick(combo, text)
        values = {
            combo.unique_id: choice.text,
            combo.client_state: telerik.state_for(combo, choice),
        }
        if combo.postback:
            self._post(values, target=combo.unique_id)
        else:
            self.fill(values)

    def radio(self, name: str, wanted: str) -> dict[str, str]:
        """Pick the radio of group ``name`` whose label starts with ``wanted`` (M / F)."""
        for node in self.page.root.find_all("input", where=lambda n: n.get("name") == ctrl(name)):
            label = self._label_for(node.get("id"))
            if label.upper().startswith(wanted.upper()):
                return {ctrl(name): node.get("value")}
        raise UpstreamError(
            f"No option starting with {wanted!r} in {name}", service=SERVICE, reason="formChanged"
        )

    def _label_for(self, element_id: str) -> str:
        label = self.page.root.find("label", where=lambda n: n.get("for") == element_id)
        return label.text().strip() if label is not None else ""

    def has(self, name: str) -> bool:
        """Is there a control called ``name``? Checkbox and radio ids lack the ``ctl00_`` prefix."""
        ids = {f"{ID_PREFIX}{name}", f"ContentPlaceHolderMain_{name}"}
        return (
            self.page.root.find(
                where=lambda n: n.get("id") in ids or n.get("name").startswith(ctrl(name))
            )
            is not None
        )

    # ------------------------------------------------------------ the wizard

    def personal_data(self, p: Profile) -> None:
        self.fill(
            self.text("txtCognome", p.surname)
            | self.text("txtNome", p.name)
            | self.radio("rbtlstSesso", p.gender)
            | self.text("txtDataNascita", p.birth_date, kind="date")
        )
        self.choose("cboNazioneNascita", p.birth_nation)
        self._optional_combo("cboComuneNascita", p.birth_municipality)
        self.fill(
            self.text("txtCodiceFiscale", p.tax_code)
            | self.text("txtIndirizzo", p.address)
            | self.text("txtNumeroCivico", p.house_number)
            | self.text("txtCap", p.postal_code)
        )
        self.choose("cboNazione", p.nation)
        self._optional_combo("cboProvincia", p.province)
        self._optional_combo("cboComune", p.municipality)
        self.fill(
            self.text("txtLocalita", p.locality)
            | self.text("txtEmail", p.email)
            | self.text("txtTelefonoCellulare", p.phone)
        )
        if p.contact_by_phone:
            self.fill({ctrl("chkModalitaRispostaTelefonica"): "on"})
        else:
            self.untick("chkModalitaRispostaTelefonica")
        self._post({}, button="btAvanti1")
        self._expect("ddlstTipoServizio", "personal data")

    def communication(self, c: Claim) -> None:
        for name, value in (
            ("ddlstTipoServizio", c.service),
            ("ddlstTipologiaComunicazione", c.kind),
            ("ddlstCategoriaComunicazione", c.category),
            ("ddlstBacinoAutomobilistico", c.basin),
            ("ddlstLineaAutomobilistica", c.line),
        ):
            self.choose(name, value)
        self.fill(
            self.text("txtDirezioneVeicolo", c.direction)
            | self.text("txtMatricolaVeicolo", c.vehicle)
            | self.text("txtMatricolaConducente", c.driver)
            | self.text("txtDataEvento", c.event_date, kind="date")
            | self.text("txtOraEvento", c.event_time, kind="time")
            | self.text("txtLuogoEvento", c.place)
            | self.text("txtTesto", c.text)
        )
        if c.compensation:
            self.fill({ctrl("chkRimborso"): "on"})
        else:
            self.untick("chkRimborso")
        self._post({}, button="btAvanti2")
        self._expect("chkConsensoPrivacy", "communication data")

    def confirm(self) -> list[str]:
        """Accept the privacy notice and send. Returns the confirmation text lines."""
        self.fill({ctrl("chkConsensoPrivacy"): "on"})
        self._post({}, button="btAvanti3")
        if self.page.root.by_id(f"{ID_PREFIX}btAvanti3_input") is not None:
            raise UpstreamError(
                "TPER did not accept the complaint: " + self._problems(),
                service=SERVICE,
                reason="notAccepted",
            )
        main = self.page.root.find(cls="c-page-title")
        body = self.page.root.find(where=lambda n: n.get("id", "").endswith("MainContent"))
        return [x for x in ((main.text() if main else ""), (body.text() if body else "")) if x]

    # ------------------------------------------------------------ helpers

    def _optional_combo(self, name: str, text: str) -> None:
        if self.has(name):
            self.choose(name, text)

    def _expect(self, control: str, step: str) -> None:
        if self.has(control):
            return
        raise UpstreamError(
            f"TPER did not accept the {step}: " + self._problems(),
            service=SERVICE,
            reason="stepRejected",
            hint="Check the profile and claim values, then retry.",
        )

    def _problems(self) -> str:
        found = [
            n.text()
            for n in self.page.root.find_all(
                where=lambda n: any(k in c.lower() for c in n.classes for k in ERROR_CLASSES)
            )
            if n.text()
        ]
        return "; ".join(dict.fromkeys(found))[:300] or "no message shown"


def open_form(http: Http) -> Wizard:
    return Wizard(http, load(http, URL, SERVICE))
