from __future__ import annotations

import pytest
import responses

from tper_cli.errors import NotFoundError, UpstreamError, ValidationError
from tper_cli.hellobus import HelloBus, parse_reply, unwrap
from tper_cli.http import Http

from .conftest import HELLOBUS, RESALE, hellobus_xml


def test_parses_live_arrivals() -> None:
    reply = parse_reply(
        "TperHellobus: 11B DaSatellite 19:33 (Bus5722 CON PEDANA), 11B DaSatellite 19:44 (Bus1638)"
    )
    assert [a.time for a in reply.arrivals] == ["19:33", "19:44"]
    first, second = reply.arrivals
    assert (first.line, first.kind, first.bus, first.wheelchair) == (
        "11B",
        "realtime",
        "5722",
        True,
    )
    assert second.wheelchair is None
    assert reply.message is None
    assert reply.unparsed == []


def test_parses_timetable_with_requested_time_and_missing_bus() -> None:
    reply = parse_reply(
        "TperHellobus: (x18:30) 11B Previsto 18:40 (Bus5697 CON PEDANA), 11B Previsto 18:54"
    )
    assert reply.requested_time == "18:30"
    assert [a.kind for a in reply.arrivals] == ["scheduled", "scheduled"]
    assert reply.arrivals[1].bus is None


def test_to_dict_only_has_known_fields() -> None:
    arrival = parse_reply("TperHellobus: 27A DaSatellite 07:05 (Bus9)").arrivals[0]
    assert arrival.to_dict() == {"line": "27A", "type": "realtime", "time": "07:05", "bus": "9"}


def test_no_more_runs_is_a_message_not_an_error() -> None:
    reply = parse_reply("TperHellobus: OGGI NESSUNA ALTRA CORSA DI 99 PER FERMATA 4476")
    assert reply.arrivals == []
    assert reply.message == "OGGI NESSUNA ALTRA CORSA DI 99 PER FERMATA 4476"
    assert reply.unparsed == []


def test_unknown_kind_is_kept_not_dropped() -> None:
    reply = parse_reply("TperHellobus: 11 Sospeso 10:00 (Bus1)")
    assert reply.arrivals[0].kind == "sospeso"


def test_part_of_the_answer_unreadable_is_reported() -> None:
    reply = parse_reply("TperHellobus: 11B DaSatellite 19:33 (Bus1), qualcosa di strano")
    assert len(reply.arrivals) == 1
    assert reply.unparsed == ["qualcosa di strano"]


def test_unknown_stop_is_not_found() -> None:
    with pytest.raises(NotFoundError) as err:
        parse_reply("HellobusHelp: FERMATA 999999 NON GESTITA, indicare FERMATA LINEA")
    assert err.value.reason == "stopNotFound"


def test_other_help_texts_are_validation_errors() -> None:
    with pytest.raises(ValidationError):
        parse_reply("HellobusHelp: indicare FERMATA LINEA o FERMATA LINEA ORA.")


def test_unexpected_text_is_an_upstream_error() -> None:
    with pytest.raises(UpstreamError):
        parse_reply("FORBIDDEN")


def test_unwrap_rejects_non_xml() -> None:
    with pytest.raises(UpstreamError):
        unwrap("<html>")
    assert unwrap(hellobus_xml("hello")) == "hello"


def test_client_sends_the_documented_parameters(rsps: responses.RequestsMock) -> None:
    rsps.add(
        responses.GET, HELLOBUS, body=hellobus_xml("TperHellobus: 11B DaSatellite 19:33 (Bus1)")
    )
    reply = HelloBus(Http()).arrivals("4476", "11", "1830")
    assert reply.arrivals[0].line == "11B"
    query = rsps.calls[0].request.url.split("?", 1)[1]
    assert query == "fermata=4476&linea=11&oraHHMM=1830"


def test_client_sends_empty_line_and_time_for_live_data(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, HELLOBUS, body=hellobus_xml("TperHellobus: 1 DaSatellite 10:00"))
    HelloBus(Http()).arrivals("1")
    assert rsps.calls[0].request.url.endswith("fermata=1&linea=&oraHHMM=")


def test_nearest_retailer(rsps: responses.RequestsMock) -> None:
    rsps.add(
        responses.GET,
        RESALE,
        body=hellobus_xml("Rivendita a 260m da fermata 4476: TABACCHERIA X, VIA Y 5, BOLOGNA"),
    )
    found = HelloBus(Http()).nearest_retailer("4476")
    assert found == {"distanceMeters": 260, "description": "TABACCHERIA X, VIA Y 5, BOLOGNA"}


def test_nearest_retailer_may_be_unknown(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, RESALE, body=hellobus_xml("Nessuna rivendita"))
    assert HelloBus(Http()).nearest_retailer("4476") is None
