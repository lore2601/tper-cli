"""End-to-end tests of the commands, with every service mocked."""

from __future__ import annotations

import json
import stat
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import responses

from tper_cli import __version__
from tper_cli.claim import form
from tper_cli.claim.profile import Profile, save
from tper_cli.commands import claim as claim_cmd
from tper_cli.zones import URL as ZONES_URL

from .conftest import HELLOBUS, RESALE, Result, fixture_text, hellobus_xml
from .test_zones import answer, calculator_page

Run = Callable[..., Result]
BASE = "https://www.tper.it"


@pytest.fixture
def bus(rsps: responses.RequestsMock) -> responses.RequestsMock:
    rsps.add(
        responses.GET,
        HELLOBUS,
        body=hellobus_xml(
            "TperHellobus: 11B DaSatellite 19:41 (Bus1638 CON PEDANA), 11B DaSatellite 19:53 (Bus5753)"
        ),
    )
    return rsps


# ------------------------------------------------------------------------ basics


def test_version_and_help(run: Run) -> None:
    assert run("--version").out.strip() == f"tper, version {__version__}"
    result = run("--help")
    assert result.code == 0 and "bus" in result.out and "claim" in result.out


def test_usage_errors_are_json_exit_3(run: Run) -> None:
    result = run("bus", "arrivals")
    assert result.code == 3
    assert result.error["reason"] == "invalidArgument"


def test_schema_lists_every_command(run: Run) -> None:
    schema = run("schema").json
    names = {c["command"] for c in schema["commands"]}
    assert {"tper bus arrivals", "tper fare quote", "tper claim file", "tper news"} <= names
    assert schema["exitCodes"]["policy"] == 4
    one = run("schema", "bus arrivals").json
    assert one["command"] == "tper bus arrivals"
    assert run("schema", "nope").code == 3


def test_config_show_and_init(run: Run, env: dict[str, str]) -> None:
    shown = run("config", "show").json
    assert shown["policy"]["readOnly"] is False and shown["defaults"]["fareProfile"] == "ordinary"
    assert run("config", "init").code == 0
    assert (Path(env["TPER_CONFIG_DIR"]) / "config.toml").is_file()
    assert run("config", "init").code == 3
    assert run("config", "init", "--force").code == 0


def test_bad_config_values_are_rejected(run: Run, env: dict[str, str]) -> None:
    path = Path(env["TPER_CONFIG_DIR"])
    path.mkdir(parents=True)
    (path / "config.toml").write_text('[defaults]\nfare_profile = "vip"\n', encoding="utf-8")
    result = run("config", "show")
    assert result.code == 3 and "fare_profile" in result.error["message"]


# ------------------------------------------------------------------------ bus


def test_bus_arrivals_live(run: Run, bus: responses.RequestsMock) -> None:
    result = run("bus", "arrivals", "4476", "-l", "11")
    assert result.code == 0
    data = result.json
    assert data["mode"] == "realtime" and data["stop"] == "4476"
    assert [a["minutes"] for a in data["arrivals"]] == [11, 23]  # frozen clock is 19:30
    assert data["arrivals"][0]["wheelchair"] is True
    assert "linea=11" in bus.calls[0].request.url


def test_bus_arrivals_scheduled_has_no_countdown(run: Run, rsps: responses.RequestsMock) -> None:
    rsps.add(
        responses.GET,
        HELLOBUS,
        body=hellobus_xml("TperHellobus: (x18:30) 11B Previsto 18:40 (Bus1)"),
    )
    data = run("bus", "arrivals", "4476", "--at", "18.30").json
    assert data["mode"] == "scheduled" and data["requestedTime"] == "18:30"
    assert data["arrivals"][0]["minutes"] is None
    assert "oraHHMM=1830" in rsps.calls[0].request.url


def test_after_midnight_the_countdown_wraps(run: Run, rsps: responses.RequestsMock) -> None:
    rsps.add(
        responses.GET, HELLOBUS, body=hellobus_xml("TperHellobus: 11B DaSatellite 00:10 (Bus1)")
    )
    assert run("bus", "arrivals", "4476").json["arrivals"][0]["minutes"] == 280


def test_no_more_runs_is_not_an_error(run: Run, rsps: responses.RequestsMock) -> None:
    rsps.add(
        responses.GET,
        HELLOBUS,
        body=hellobus_xml("TperHellobus: OGGI NESSUNA ALTRA CORSA DI 99 PER FERMATA 4476"),
    )
    result = run("bus", "arrivals", "4476", "-l", "99")
    assert result.code == 0 and result.json["arrivals"] == []
    assert "NESSUNA" in result.json["message"] and result.err == ""


def test_unknown_stop_exit_3(run: Run, rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, HELLOBUS, body=hellobus_xml("HellobusHelp: FERMATA 1 NON GESTITA"))
    result = run("bus", "arrivals", "1")
    assert (result.code, result.error["reason"]) == (3, "stopNotFound")


@pytest.mark.parametrize(
    "args", [["4476", "-l", "a/b"], ["4476", "--at", "25:99"], ["4476", "-l", "11;ls"]]
)
def test_hostile_or_bad_arguments_never_reach_the_network(
    run: Run, rsps: responses.RequestsMock, args: list[str]
) -> None:
    result = run("bus", "arrivals", *args)
    assert result.code == 3
    assert len(rsps.calls) == 0


def test_service_down_is_exit_1(run: Run, rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, HELLOBUS, status=500)
    result = run("bus", "arrivals", "4476")
    assert result.code == 1 and result.error["service"] == "hellobus"


def test_arrivals_by_unique_name(
    run: Run, mock_opendata: responses.RequestsMock, bus: responses.RequestsMock
) -> None:
    result = run("bus", "arrivals", "Lapidari Arcoveggio 74")
    assert result.code == 0 and result.json["stop"] == "4476"
    assert result.json["stopName"] == "LAPIDARI"


def test_arrivals_by_ambiguous_name_lists_candidates(
    run: Run, mock_opendata: responses.RequestsMock
) -> None:
    result = run("bus", "arrivals", "stazione centrale")
    assert (result.code, result.error["reason"]) == (3, "ambiguous")
    assert len(result.error["candidates"]) >= 2


def test_numeric_code_does_not_download_the_open_data(
    run: Run, bus: responses.RequestsMock
) -> None:
    run("bus", "arrivals", "4476")
    assert all("solweb" not in c.request.url for c in bus.calls)


def test_stop_name_shown_once_the_data_is_cached(
    run: Run, mock_opendata: responses.RequestsMock, bus: responses.RequestsMock
) -> None:
    run("bus", "stops", "search", "lapidari")
    assert run("bus", "arrivals", "4476").json["stopName"] == "LAPIDARI"


def test_stops_search_near_get(
    run: Run, mock_opendata: responses.RequestsMock, rsps: responses.RequestsMock
) -> None:
    found = run("bus", "stops", "search", "lapidri").json  # typo
    assert found["stops"][0]["name"] == "LAPIDARI" and "CC BY" in found["source"]
    assert run("bus", "stops", "search", "lapidari", "-m", "ferrara").json["stops"] == []
    near = run("bus", "stops", "near", "44.5364", "11.3502", "-r", "100").json
    assert near["stops"][0]["distanceMeters"] < 100
    assert run("bus", "stops", "near", "95", "11").code == 3
    rsps.add(
        responses.GET,
        RESALE,
        body=hellobus_xml("Rivendita a 260m da fermata 4476: TABACCHI X, VIA Y"),
    )
    stop = run("bus", "stops", "get", "4476", "--retailer").json
    assert stop["lines"] == ["11"] and stop["zoneName"] == "BOLOGNA"
    assert stop["nearestRetailer"]["distanceMeters"] == 260
    assert run("bus", "stops", "get", "123456").code == 3


def test_lines(run: Run, mock_opendata: responses.RequestsMock) -> None:
    assert {x["line"] for x in run("bus", "lines").json["lines"]} >= {"11", "20"}
    assert [x["line"] for x in run("bus", "lines", "-q", "9").json["lines"]] == ["90", "900"]
    stops = run("bus", "line", "11").json
    assert stops["line"] == "11" and stops["count"] >= 1
    assert run("bus", "line", "77777").code == 3


def test_table_output_on_request(run: Run, bus: responses.RequestsMock) -> None:
    out = run("-f", "table", "bus", "arrivals", "4476").out
    assert out.splitlines()[0].split() == ["LINE", "TYPE", "TIME", "IN", "MIN", "BUS", "WHEELCHAIR"]


def test_fields_trim_the_output(run: Run, bus: responses.RequestsMock) -> None:
    arrivals = run("--fields", "line,time", "bus", "arrivals", "4476").json["arrivals"]
    assert arrivals[0] == {"line": "11B", "time": "19:41"}


# ------------------------------------------------------------------------ rail & news


def test_rail_lines_and_stations(run: Run, mock_opendata: responses.RequestsMock) -> None:
    assert run("rail", "lines").json["count"] == 9
    stations = run("rail", "stations", "-q", "bologna centrale").json["stations"]
    assert stations[0]["name"] == "BOLOGNA CENTRALE"


def test_rail_alerts(run: Run, rsps: responses.RequestsMock) -> None:
    rsps.add(
        responses.GET,
        "https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.app.html",
        body=fixture_text("infomobility.html"),
    )
    er = run("rail", "alerts").json
    assert [n["title"] for n in er["notices"]] == ["INFOLAVORI EMILIA-ROMAGNA"]
    assert "body" not in er["notices"][0]
    full = run("rail", "alerts", "--full", "--region", "veneto").json["notices"]
    assert full[0]["regions"] == ["veneto"] and full[0]["body"]
    assert run("rail", "alerts", "--region", "all").json["count"] == 4
    assert run("rail", "alerts", "--national").json["count"] == 2


def test_news(run: Run, rsps: responses.RequestsMock) -> None:
    from tper_cli.news import FEEDS

    rsps.add(
        responses.GET,
        BASE + FEEDS["bologna"],
        body=(Path(__file__).parent / "fixtures/news_bologna.xml").read_bytes(),
    )
    data = run("news", "-c", "bologna", "-n", "2").json
    assert data["count"] == 2 and data["news"][0]["category"] == "bologna"
    assert run("news", "-c", "bologna", "--line", "449").json["count"] == 1
    assert run("news", "-c", "bologna", "--since", "2030-01-01").json["count"] == 0
    assert run("news", "--since", "never").code == 3


# ------------------------------------------------------------------------ live train boards


def mock_rfi(rsps: responses.RequestsMock) -> None:
    from tper_cli.rfi import MONITOR_URL, STATION_URL, STATIONS_URL

    rsps.add(responses.GET, STATIONS_URL, body=fixture_text("rfi_stations.html"))
    for slug, place in (("bologna-centrale", "683"), ("ferrara", "1309"), ("imola", "1487"),
                        ("modena", "1747"), ("parma", "1"), ("rimini", "2358")):  # fmt: skip
        rsps.add(responses.GET, STATION_URL.format(slug=slug),
                 body=fixture_text("rfi_station_page.html").replace("683", place))  # fmt: skip
    rsps.add(responses.GET, MONITOR_URL, body=fixture_text("rfi_board.html"))


def test_rail_board(run: Run, rsps: responses.RequestsMock) -> None:
    mock_rfi(rsps)
    data = run("rail", "board", "bologna centrale", "-n", "2").json
    assert data["station"] == "Bologna Centrale" and data["board"] == "departures"
    assert [t["train"] for t in data["trains"]] == ["8823", "17709"]
    assert data["trains"][1]["delayMinutes"] == 20 and data["updatedAt"].startswith(
        "2026-10-22T19:"
    )
    tper = run("rail", "board", "bologna centrale", "--carrier", "tper").json
    assert {t["carrier"] for t in tper["trains"]} == {"TRENITALIA TPER"}
    arrivals = run("rail", "board", "bologna centrale", "--arrivals").json
    assert arrivals["board"] == "arrivals" and "origin" in arrivals["trains"][0]
    assert run("rail", "board", "reggio").error["reason"] == "ambiguous"


def test_rail_train(run: Run, rsps: responses.RequestsMock) -> None:
    mock_rfi(rsps)
    found = run("rail", "train", "17709").json
    assert found["found"] is True and found["expectedTime"] == "20:06"
    assert (
        found["station"] == "Bologna Centrale"
        and found["stops"][0]["station"] == "BOLOGNA S.VITALE"
    )
    missing = run("rail", "train", "424242", "-s", "Ferrara").json
    assert missing["found"] is False and missing["searched"] == ["Ferrara"]
    assert run("rail", "train", "17709; ls").code == 3


def test_rail_stations_from_rfi(run: Run, rsps: responses.RequestsMock) -> None:
    mock_rfi(rsps)
    names = [s["name"] for s in run("rail", "stations", "--rfi", "-q", "reggio").json["stations"]]
    assert names[0].startswith("Reggio Emilia")


# ------------------------------------------------------------------------ fares


def test_fare_list_and_filters(run: Run) -> None:
    data = run("fare", "list", "--area", "urban", "--network", "ferrara", "--kind", "single").json
    assert [p["price"] for p in data["products"]] == [1.9]
    assert run("fare", "list", "--zones", "3", "--area", "extraurban").json["count"] > 5


def test_fare_quote_urban_profile(run: Run) -> None:
    data = run("fare", "quote", "--urban", "bologna", "-p", "under27").json
    by_kind = {p["kind"]: p for p in data["products"]}
    assert by_kind["annual"]["price"] == 230 and by_kind["annual"]["profile"] == "under27"
    assert by_kind["single"]["profile"] == "ordinary"
    assert data["card"]["price"] == 5.0 and data["priceListDate"]


def test_fare_quote_for_a_known_number_of_zones(run: Run) -> None:
    data = run("fare", "quote", "--zones", "4", "--basin", "ferrara").json
    assert {p["kind"]: p["price"] for p in data["products"]}["single"] == 4.5
    assert run("fare", "quote", "--zones", "4").code == 3  # basin missing
    assert run("fare", "quote", "--zones", "11").code == 3


def test_fare_quote_from_a_trip(
    run: Run, mock_opendata: responses.RequestsMock, rsps: responses.RequestsMock
) -> None:
    answer(rsps, {frozenset(("BOLOGNA", "SAN GIOVANNI IN PERSICETO")): "3"})
    data = run("fare", "quote", "--from", "Bologna", "--to", "San Giovanni in Persiceto").json
    assert data["zones"] == 3 and data["network"] == "bologna"
    assert data["trip"]["source"] == "calculator"
    assert any("inferred" in n for n in data["notes"])
    assert [p["id"] for p in data["alsoConsider"]] == [
        "ferrobus-bologna-ferrobus_monthly-ordinary-3z"
    ]


def test_fare_quote_inside_a_city_is_urban(
    run: Run, mock_opendata: responses.RequestsMock, rsps: responses.RequestsMock
) -> None:
    rsps.add(responses.GET, ZONES_URL, body=calculator_page())
    data = run("fare", "quote", "--from", "Bologna", "--to", "Bologna").json
    assert data["area"] == "urban" and data["network"] == "bologna"


def test_fare_quote_needs_a_clear_trip(run: Run) -> None:
    for args in ([], ["--from", "Bologna"], ["--zones", "3", "--urban", "bologna"]):
        assert run("fare", "quote", *args).code == 3


def test_fare_zones_and_places(
    run: Run, mock_opendata: responses.RequestsMock, rsps: responses.RequestsMock
) -> None:
    answer(rsps, {frozenset(("BOLOGNA", "FERRARA")): "5"})
    assert run("fare", "zones", "Bologna", "Ferrara").json["zones"] == 5
    assert run("fare", "places", "persiceto").json["places"][0]["zone"] == "553"
    fine = run("fare", "places", "corticella", "--localities").json["places"]
    assert fine[0]["zone"] == "504"
    assert run("fare", "zones", "Bologna", "Atlantide").code == 3


def test_fare_compare(run: Run) -> None:
    data = run("fare", "compare", "--urban", "bologna", "--days-per-week", "5").json
    assert data["cheapest"]["kind"] in {"annual", "annual_anonymous", "monthly_anonymous"}
    assert data["ridesPerMonth"] == pytest.approx(43.3)
    assert data["breakEvenRidesPerMonth"] == 17
    few = run(
        "fare", "compare", "--urban", "bologna", "--rides-per-month", "4", "--rides-per-day", "2"
    ).json
    assert few["cheapest"]["kind"] not in {"annual", "annual_anonymous", "monthly_anonymous"}


def test_default_profile_comes_from_the_config(
    run: Run, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TPER_FARE_PROFILE", "over70")
    data = run("fare", "quote", "--urban", "bologna").json
    assert data["profile"] == "over70"
    assert {p["kind"]: p["price"] for p in data["products"]}["annual"] == 200


# ------------------------------------------------------------------------ data


def test_data_status_update_clear(run: Run, mock_opendata: responses.RequestsMock) -> None:
    status = run("data", "status").json
    assert status["license"].startswith("Creative Commons") and not any(
        d["cached"] for d in status["datasets"]
    )
    updated = run("data", "update", "linee", "zone").json
    assert set(updated["updated"]) == {"linee", "zone"}
    assert [d["dataset"] for d in run("data", "status").json["datasets"] if d["cached"]] == [
        "linee",
        "zone",
    ]
    assert run("data", "clear").json["removedFiles"] >= 3
    assert run("data", "update", "bogus").code == 3


def test_open_data_unavailable_exit_2(run: Run, rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, "https://solweb.tper.it/web/tools/open-data/open-data.aspx", status=503)
    result = run("bus", "stops", "search", "lapidari")
    assert (result.code, result.error["reason"]) == (2, "openDataUnavailable")


# ------------------------------------------------------------------------ doctor


def test_doctor_offline(run: Run) -> None:
    data = run("doctor", "--offline").json
    assert data["ok"] is True and len(data["checks"]) == 2


def test_doctor_reports_each_service(
    run: Run, rsps: responses.RequestsMock, mock_opendata: responses.RequestsMock
) -> None:
    from tper_cli.news import FEEDS

    rsps.add(
        responses.GET, HELLOBUS, body=hellobus_xml("TperHellobus: 11B DaSatellite 19:41 (Bus1)")
    )
    rsps.add(responses.GET, BASE + FEEDS["front"], status=500)
    rsps.add(
        responses.GET,
        "https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.app.html",
        body=fixture_text("infomobility.html"),
    )
    rsps.add(responses.GET, ZONES_URL, body=calculator_page())
    rsps.add(responses.GET, form.URL, body=fixture_text("claim_step1.html"))
    mock_rfi(rsps)
    data = run("doctor").json
    status = {c["check"]: c["ok"] for c in data["checks"]}
    assert (
        status["hellobus"]
        and status["open data"]
        and status["rail notices"]
        and status["complaint form"]
    )
    assert status["news feed"] is False and data["ok"] is False


# ------------------------------------------------------------------------ claim

CLAIM_ARGS = [
    "claim", "file", "--category", "Corsa non effettuata", "--basin", "Bologna", "--line", "20",
    "--date", "yesterday", "--time", "9:11", "--place", "fermata 4476",
    "--text", "La corsa delle 9:11 non e' passata e ho aspettato 40 minuti.",
]  # fmt: skip


@pytest.fixture
def stored_profile(env: dict[str, str]) -> Path:
    from datetime import date

    from .test_claim import profile

    path = Path(env["TPER_CONFIG_DIR"]) / "profile.toml"
    save(profile().validate(date(2026, 10, 22)), path)
    return path


class FakeWizard:
    def __init__(self) -> None:
        self.steps: list[str] = []

    def personal_data(self, p: Profile) -> None:
        self.steps.append(f"personal:{p.surname}")

    def communication(self, c: Any) -> None:
        self.steps.append(f"communication:{c.line}")

    def confirm(self) -> list[str]:
        self.steps.append("confirm")
        return ["Reclamo inviato"]


@pytest.fixture
def wizard(monkeypatch: pytest.MonkeyPatch) -> FakeWizard:
    fake = FakeWizard()
    monkeypatch.setattr(claim_cmd.form, "open_form", lambda _http: fake)
    return fake


def test_claim_needs_a_profile(run: Run) -> None:
    result = run(*CLAIM_ARGS, "--dry-run")
    assert (result.code, result.error["reason"]) == (2, "profileMissing")


def test_claim_profile_commands(run: Run, stored_profile: Path) -> None:
    assert run("claim", "profile", "path").json["exists"] is True
    shown = run("claim", "profile", "show").json
    assert shown["surname"] == "R****" and "ROSSI" not in json.dumps(shown)
    if sys.platform != "win32":
        assert stat.S_IMODE(stored_profile.stat().st_mode) == 0o600
    assert run("claim", "profile", "delete", "--yes").json["deleted"] is True
    assert run("claim", "profile", "path").json["exists"] is False
    assert (
        run("claim", "profile", "init").code == 3
    )  # not interactive: an agent cannot type personal data


def test_claim_dry_run_sends_nothing_and_masks_personal_data(
    run: Run, stored_profile: Path, wizard: FakeWizard
) -> None:
    result = run(*CLAIM_ARGS, "--dry-run")
    assert result.code == 0 and wizard.steps == []
    assert result.json["dryRun"] is True
    assert "ROSSI" not in result.out and "ROSMRA" not in result.out
    assert result.json["request"]["claim"]["date"] == "21/10/2026"


def test_claim_needs_confirmation_when_not_interactive(
    run: Run, stored_profile: Path, wizard: FakeWizard
) -> None:
    result = run(*CLAIM_ARGS)
    assert (result.code, result.error["reason"]) == (4, "confirmationRequired")
    assert wizard.steps == []


def test_claim_is_sent_once(run: Run, stored_profile: Path, wizard: FakeWizard) -> None:
    sent = run(*CLAIM_ARGS, "--yes")
    assert sent.code == 0 and sent.json["submitted"] is True
    assert wizard.steps == ["personal:ROSSI", "communication:20", "confirm"]
    assert "ROSSI" not in sent.out
    again = run(*CLAIM_ARGS, "--yes")
    assert (again.code, again.error["reason"]) == (4, "duplicateClaim")
    assert run(*CLAIM_ARGS, "--yes", "--allow-duplicate").code == 0
    history = run("claim", "history").json
    assert history["count"] == 2 and history["claims"][0]["line"] == "20"


def test_claim_respects_read_only(
    run: Run, stored_profile: Path, wizard: FakeWizard, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TPER_READ_ONLY", "1")
    result = run(*CLAIM_ARGS, "--yes")
    assert (result.code, result.error["reason"]) == (4, "readOnly")
    assert wizard.steps == []


def test_claim_text_from_a_file(
    run: Run, stored_profile: Path, wizard: FakeWizard, tmp_path: Path
) -> None:
    text = tmp_path / "t.txt"
    text.write_text("Il bus non si e' fermato alla fermata indicata. " * 2, encoding="utf-8")
    args = [a for a in CLAIM_ARGS if not a.startswith("La corsa")]
    without_text = args[: args.index("--text")]
    assert run(*without_text, "--text-file", str(text), "--dry-run").code == 0
    assert run(*without_text, "--dry-run").code == 3  # no text at all


def test_claim_check(run: Run, rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, form.URL, body=fixture_text("claim_step1.html"))
    assert run("claim", "check").json["ok"] is True
    rsps.replace(
        responses.GET,
        form.URL,
        body="<html><form><input type='hidden' name='__VIEWSTATE' value='x'></form></html>",
    )
    result = run("claim", "check")
    assert (result.code, result.error["reason"]) == (1, "formChanged")


# ------------------------------------------------------------------------ failure modes


def test_internal_errors_are_json_exit_5(
    run: Run,
    bus: responses.RequestsMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(*_args: Any) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr("tper_cli.commands.bus.minutes_until", boom)
    result = run("bus", "arrivals", "4476")
    assert (result.code, result.error["reason"]) == (5, "internal")
    assert "RuntimeError: kaboom" in result.error["message"]
    debug = run("--debug", "bus", "arrivals", "4476")
    assert debug.code == 5 and "Traceback" in debug.err


def test_ctrl_c_and_abort(
    run: Run, bus: responses.RequestsMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    import click

    def interrupt(*_args: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("tper_cli.commands.bus.minutes_until", interrupt)
    assert run("bus", "arrivals", "4476").code == 130

    def abort(*_args: Any) -> None:
        raise click.Abort

    monkeypatch.setattr("tper_cli.commands.bus.minutes_until", abort)
    result = run("bus", "arrivals", "4476")
    assert (result.code, result.error["reason"]) == (130, "aborted")


def test_invalid_format_from_the_environment(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TPER_FORMAT", "yaml")
    assert run("config", "show").code == 3


def test_python_dash_m_works() -> None:
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "tper_cli", "--version"], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == f"tper, version {__version__}"
