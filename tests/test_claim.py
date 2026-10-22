from __future__ import annotations

import json
import stat
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import pytest
import responses

from tper_cli.claim import form, telerik
from tper_cli.claim.ledger import Ledger
from tper_cli.claim.model import Claim
from tper_cli.claim.profile import Profile, load, mask, save
from tper_cli.errors import NotFoundError, SetupError, UpstreamError, ValidationError
from tper_cli.htmlutil import parse_html
from tper_cli.http import Http

from .conftest import fixture_text

TODAY = date(2026, 10, 22)


def profile(**over: Any) -> Profile:
    data: dict[str, Any] = {
        "surname": "ROSSI", "name": "MARIO", "gender": "m", "birth_date": "01/01/1980",
        "birth_nation": "ITALIA", "birth_municipality": "ROMA", "tax_code": "ROSMRA80A01H501Q",
        "address": "VIA ESEMPIO", "house_number": "1", "postal_code": "40100", "nation": "ITALIA",
        "province": "BOLOGNA", "municipality": "BOLOGNA", "locality": "", "email": "m.rossi@example.com",
        "phone": "", "contact_by_phone": False,
    }  # fmt: skip
    data.update(over)
    return Profile(**data)


def claim(**over: Any) -> Claim:
    data: dict[str, Any] = {
        "service": "Servizio bus", "kind": "Servizio", "category": "Corsa non effettuata",
        "basin": "Bologna", "line": "20", "direction": "Pilastro", "vehicle": "", "driver": "",
        "event_date": "yesterday", "event_time": "9:11", "place": "fermata 4476",
        "text": "La corsa delle 9:11 non e' passata e ho aspettato 40 minuti.",
    }  # fmt: skip
    data.update(over)
    return Claim(**data)


# ------------------------------------------------------------------------ profile


def test_profile_validates_and_normalises() -> None:
    p = profile().validate(TODAY)
    assert p.gender == "M" and p.tax_code == "ROSMRA80A01H501Q"


@pytest.mark.parametrize(
    "over",
    [
        {"tax_code": "ROSMRA80A01H501A"}, {"email": "nope"}, {"postal_code": "1"},
        {"gender": "X"}, {"surname": ""}, {"birth_date": "2999-01-01"},
        {"contact_by_phone": True, "phone": ""},
    ],
)  # fmt: skip
def test_profile_rejects_bad_data(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        profile(**over).validate(TODAY)


def test_profile_round_trip_is_private_and_masked(tmp_path: Path) -> None:
    path = tmp_path / "cfg" / "profile.toml"
    save(profile(address='VIA "STRANA" \\ 1').validate(TODAY), path)
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    loaded = load(path, TODAY)
    assert loaded.address == 'VIA "STRANA" \\ 1'
    shown = json.dumps(loaded.masked())
    assert "ROSSI" not in shown and "ROSMRA" not in shown and "example.com" in shown
    assert loaded.masked()["email"] == "m***@example.com"


def test_missing_profile_is_a_setup_error(tmp_path: Path) -> None:
    with pytest.raises(SetupError) as err:
        load(tmp_path / "none.toml", TODAY)
    assert err.value.reason == "profileMissing"


def test_broken_profile_is_explained(tmp_path: Path) -> None:
    path = tmp_path / "p.toml"
    path.write_text("[profile]\nsurname = 'X'\n", encoding="utf-8")
    with pytest.raises(ValidationError) as err:
        load(path, TODAY)
    assert err.value.reason == "profileInvalid"


def test_mask() -> None:
    assert mask("") == "" and mask("abc") == "a**" and mask("a@b.it") == "a***@b.it"


# ------------------------------------------------------------------------ claim


def test_claim_validates_dates_times_and_text() -> None:
    ok = claim().validate(TODAY)
    assert (ok.event_date, ok.event_time) == ("21/10/2026", "09:11")
    for over in ({"event_date": "tomorrow"}, {"event_date": "2030-01-01"}, {"event_time": "25:00"},
                 {"text": "troppo corto"}, {"text": "x" * 3001}, {"line": ""}):  # fmt: skip
        with pytest.raises(ValidationError):
            claim(**over).validate(TODAY)


def test_fingerprint_depends_on_the_content() -> None:
    a = claim().validate(TODAY)
    assert a.fingerprint() == claim().validate(TODAY).fingerprint()
    assert a.fingerprint() != claim(line="21").validate(TODAY).fingerprint()
    assert set(a.summary()) >= {"service", "category", "date", "time", "text"}


def test_ledger(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "state")
    assert ledger.find("abc") is None and ledger.all() == []
    ledger.add("abc", datetime(2026, 10, 22, 19, 0), "20", "21/10/2026")
    assert ledger.find("abc")["line"] == "20"  # type: ignore[index]
    (tmp_path / "state" / "claims.jsonl").write_text("not json\n[1]\n", encoding="utf-8")
    assert ledger.all() == []


# ------------------------------------------------------------------------ telerik


def test_telerik_discovers_the_options_of_the_real_form() -> None:
    markup = fixture_text("claim_step1.html")
    combos = telerik.discover(markup, parse_html(markup))
    country = telerik.require(combos, form.ctrl("cboNazioneNascita"))
    italy = telerik.pick(country, "italia")
    assert italy.text.upper() == "ITALIA" and italy.value
    assert country.postback is True
    state = json.loads(telerik.state_for(country, italy))
    assert state["text"].upper() == "ITALIA" and state["value"] == italy.value


def test_telerik_unknown_option_lists_alternatives() -> None:
    markup = fixture_text("claim_step1.html")
    combos = telerik.discover(markup, parse_html(markup))
    with pytest.raises(NotFoundError) as err:
        telerik.pick(combos[form.ctrl("cboNazione")], "Atlantide")
    assert err.value.to_dict()["error"]["options"]


def test_telerik_dropdown_state_uses_selected_fields() -> None:
    combo = telerik.Combo(
        "u", "RadDropDownList", "u_ClientState", [telerik.Choice("A", "1", 0)], False
    )
    state = json.loads(telerik.state_for(combo, combo.choices[0]))
    assert (state["selectedIndex"], state["selectedText"], state["selectedValue"]) == (0, "A", "1")


def test_missing_control_is_reported_as_a_changed_form() -> None:
    with pytest.raises(UpstreamError) as err:
        telerik.require({}, "ctl00$x")
    assert err.value.reason == "formChanged"


# ------------------------------------------------------------------------ wizard on the real step 1


@pytest.fixture
def wizard(rsps: responses.RequestsMock) -> form.Wizard:
    rsps.add(responses.GET, form.URL, body=fixture_text("claim_step1.html"))
    return form.open_form(Http())


def test_every_control_of_step_one_exists_on_the_real_form(wizard: form.Wizard) -> None:
    """The names this module writes must exist in the page TPER really serves."""
    for name in ("txtCognome", "txtNome", "txtDataNascita", "cboNazioneNascita", "txtIndirizzo",
                 "txtNumeroCivico", "txtCap", "cboNazione", "txtLocalita", "txtEmail",
                 "txtTelefonoCellulare", "btAvanti1"):  # fmt: skip
        assert wizard.has(name), name
    assert wizard.radio("rbtlstSesso", "M")
    assert wizard.radio("rbtlstSesso", "F") != wizard.radio("rbtlstSesso", "M")


def test_text_fields_carry_both_the_value_and_the_client_state(wizard: form.Wizard) -> None:
    fields = wizard.text("txtCognome", "ROSSI")
    assert fields[form.ctrl("txtCognome")] == "ROSSI"
    assert json.loads(fields[form.state_name("txtCognome")])["valueAsString"] == "ROSSI"
    date_fields = wizard.text("txtDataNascita", "01/02/1980", kind="date")
    assert date_fields[form.ctrl("txtDataNascita")] == "1980-02-01-00-00-00"
    assert date_fields[form.ctrl("txtDataNascita$dateInput")] == "01/02/1980"
    time_fields = wizard.text("txtOraEvento", "09:11", kind="time")
    assert time_fields[form.ctrl("txtOraEvento")].endswith("09-11-00")


def test_choosing_a_country_posts_back_like_a_browser(
    wizard: form.Wizard, rsps: responses.RequestsMock
) -> None:
    seen: dict[str, str] = {}

    def respond(request: Any) -> tuple[int, dict[str, str], str]:
        seen.update(dict(parse_qsl(request.body, keep_blank_values=True)))
        return 200, {}, fixture_text("claim_step1.html")

    rsps.add_callback(responses.POST, form.URL, callback=respond)
    wizard.choose("cboNazioneNascita", "ITALIA")
    assert seen["__EVENTTARGET"] == form.ctrl("cboNazioneNascita")
    assert seen[form.ctrl("cboNazioneNascita")].upper() == "ITALIA"
    assert "__VIEWSTATE" in seen
    with pytest.raises(NotFoundError):
        wizard.choose("cboNazioneNascita", "Atlantide")


def test_a_rejected_step_reports_what_the_page_says(
    wizard: form.Wizard, rsps: responses.RequestsMock
) -> None:
    body = fixture_text("claim_step1.html").replace(
        "</form>", '<span class="field-error">Codice fiscale non valido</span></form>'
    )
    rsps.add(responses.POST, form.URL, body=body)
    wizard._post({}, button="btAvanti1")
    with pytest.raises(UpstreamError) as err:
        wizard._expect("ddlstTipoServizio", "personal data")
    assert err.value.reason == "stepRejected" and "Codice fiscale" in err.value.message


def test_a_missing_button_is_reported(wizard: form.Wizard) -> None:
    with pytest.raises(UpstreamError) as err:
        wizard._post({}, button="btDoesNotExist")
    assert err.value.reason == "formChanged"
