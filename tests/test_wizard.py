"""The complaint wizard against a small simulation of TPER's three-step WebForms page."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.parse import parse_qsl

import pytest
import responses

from tper_cli.claim import form
from tper_cli.errors import NotFoundError, UpstreamError
from tper_cli.http import Http

from .conftest import fixture_text
from .test_claim import claim, profile

TODAY = date(2026, 10, 22)
P = form.PREFIX


def dropdown(name: str, options: list[str]) -> str:
    unique = form.ctrl(name)
    element = unique.replace("$", "_")
    data = [{"selected": True}, *({"value": f"v{i}"} for i, _ in enumerate(options, 1))]
    config = {"_uniqueId": unique, "clientStateFieldID": f"{element}_ClientState", "itemData": data,
              "_postBackReference": "__doPostBack('x')"}  # fmt: skip
    items = "".join(f"<li>{o}</li>" for o in ["", *options])
    return (
        f'<div id="{element}"></div><div id="{element}_DropDown"><ul>{items}</ul></div>'
        f'<script>$create(Telerik.Web.UI.RadDropDownList, {json.dumps(config)}, null, null, $get("{element}"));</script>'
    )


def page(body: str, button: str | None = None) -> str:
    submit = (
        f'<input type="submit" id="ctl00_ContentPlaceHolderMain_{button}_input" '
        f'name="{P}{button}_input" value="Avanti">'
        if button
        else ""
    )
    return (
        '<html><body><form id="wfrmSite" method="post">'
        '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="VS">'
        f"{body}{submit}</form></body></html>"
    )


STEP2 = page(
    dropdown("ddlstTipoServizio", ["Servizio bus", "Servizio ferroviario"])
    + dropdown("ddlstTipologiaComunicazione", ["Servizio"])
    + dropdown("ddlstCategoriaComunicazione", ["Corsa non effettuata", "Altro"])
    + dropdown("ddlstBacinoAutomobilistico", ["Bologna", "Ferrara"])
    + dropdown("ddlstLineaAutomobilistica", ["19", "20"]),
    "btAvanti2",
)
STEP3 = page(f'<input type="checkbox" name="{P}chkConsensoPrivacy" id="x">', "btAvanti3")
DONE = page(
    '<span class="c-page-title">Reclamo inviato</span><div id="ctl00_MainContent">Protocollo 123</div>'
)


class Server:
    """Answers each POST like the wizard: stay on the page for postbacks, advance on buttons."""

    def __init__(self, *, reject_step: int | None = None) -> None:
        self.posts: list[dict[str, str]] = []
        self.reject_step = reject_step

    def __call__(self, request: Any) -> tuple[int, dict[str, str], str]:
        data = dict(parse_qsl(request.body, keep_blank_values=True))
        self.posts.append(data)
        if f"{P}btAvanti1_input" in data:
            return 200, {}, self._maybe_reject(1, STEP2, fixture_text("claim_step1.html"))
        if f"{P}btAvanti2_input" in data:
            return 200, {}, self._maybe_reject(2, STEP3, STEP2)
        if f"{P}btAvanti3_input" in data:
            return 200, {}, self._maybe_reject(3, DONE, STEP3)
        return 200, {}, self.current(data)

    def current(self, data: dict[str, str]) -> str:
        target = data.get("__EVENTTARGET", "")
        return STEP2 if "ddlst" in target or self.step2 else fixture_text("claim_step1.html")

    step2 = False

    def _maybe_reject(self, step: int, ok: str, bad: str) -> str:
        if step == self.reject_step:
            return bad.replace(
                "</form>", '<span class="validation-error">Dato non valido</span></form>'
            )
        if step == 1:
            self.step2 = True
        return ok


def start(rsps: responses.RequestsMock, server: Server) -> form.Wizard:
    rsps.add(responses.GET, form.URL, body=fixture_text("claim_step1.html"))
    rsps.add_callback(responses.POST, form.URL, callback=server)
    return form.open_form(Http())


def test_full_flow_sends_what_the_user_wrote(rsps: responses.RequestsMock) -> None:
    server = Server()
    wizard = start(rsps, server)
    owner = profile(phone="+39 333 1234567", contact_by_phone=True).validate(TODAY)
    wizard.personal_data(owner)
    wizard.communication(claim(vehicle="5722").validate(TODAY))
    confirmation = wizard.confirm()
    assert confirmation == ["Reclamo inviato", "Protocollo 123"]

    step1 = next(p for p in server.posts if f"{P}btAvanti1_input" in p)
    assert step1[f"{P}txtCognome"] == "ROSSI" and step1[f"{P}txtEmail"] == "m.rossi@example.com"
    assert step1[f"{P}txtCodiceFiscale"] == "ROSMRA80A01H501Q"
    assert step1[f"{P}txtDataNascita$dateInput"] == "01/01/1980"
    assert step1[f"{P}chkModalitaRispostaTelefonica"] == "on"
    assert step1["__VIEWSTATE"] == "VS" or step1["__VIEWSTATE"]
    step2 = next(p for p in server.posts if f"{P}btAvanti2_input" in p)
    assert step2[f"{P}txtMatricolaVeicolo"] == "5722"
    assert step2[f"{P}chkRimborso"] == "on"
    assert step2[f"{P}txtDataEvento$dateInput"] == "21/10/2026"
    assert (
        json.loads(step2["ctl00_ContentPlaceHolderMain_ddlstLineaAutomobilistica_ClientState"])[
            "selectedText"
        ]
        == "20"
    )
    step3 = server.posts[-1]
    assert step3[f"{P}chkConsensoPrivacy"] == "on"


def test_compensation_and_phone_can_be_declined(rsps: responses.RequestsMock) -> None:
    server = Server()
    wizard = start(rsps, server)
    wizard.personal_data(profile().validate(TODAY))
    step1 = next(p for p in server.posts if f"{P}btAvanti1_input" in p)
    assert f"{P}chkModalitaRispostaTelefonica" not in step1
    wizard.communication(claim(compensation=False).validate(TODAY))
    step2 = next(p for p in server.posts if f"{P}btAvanti2_input" in p)
    assert f"{P}chkRimborso" not in step2


@pytest.mark.parametrize("step", [1, 2, 3])
def test_a_rejected_step_stops_with_the_message_of_the_page(
    rsps: responses.RequestsMock, step: int
) -> None:
    wizard = start(rsps, Server(reject_step=step))
    steps = [
        lambda: wizard.personal_data(profile().validate(TODAY)),
        lambda: wizard.communication(claim().validate(TODAY)),
        wizard.confirm,
    ]
    for earlier in steps[: step - 1]:
        earlier()
    with pytest.raises(UpstreamError) as err:
        steps[step - 1]()
    assert "Dato non valido" in err.value.message


def test_an_option_the_form_does_not_offer_is_explained(rsps: responses.RequestsMock) -> None:
    wizard = start(rsps, Server())
    wizard.personal_data(profile().validate(TODAY))
    with pytest.raises(NotFoundError) as err:
        wizard.communication(claim(basin="Modena").validate(TODAY))
    assert "Bologna" in (err.value.hint or "")
