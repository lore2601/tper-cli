from __future__ import annotations

import pytest
import requests
import responses

from tper_cli.errors import NetworkError, UpstreamError
from tper_cli.http import USER_AGENT, Http, host_allowed

URL = "https://www.tper.it/x"


def test_user_agent_is_honest_and_browser_shaped() -> None:
    assert USER_AGENT.startswith("Mozilla/5.0 (compatible; tper-cli/")
    assert "github.com/lore2601/tper-cli" in USER_AGENT


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://www.tper.it/x", True),
        ("https://solweb.tper.it/a", True),
        ("https://hellobuswsweb.tper.it/a", True),
        ("https://www.trenitalia.com/a", True),
        ("https://evil.example.com/tper.it", False),
        ("https://tper.it.evil.com/", False),
        ("file:///etc/passwd", False),
    ],
)
def test_host_allowlist(url: str, allowed: bool) -> None:
    assert host_allowed(url) is allowed


def test_refuses_foreign_hosts(rsps: responses.RequestsMock) -> None:
    with pytest.raises(UpstreamError) as err:
        Http().get("https://example.com/", service="x")
    assert err.value.reason == "hostNotAllowed"
    assert len(rsps.calls) == 0


def test_refuses_redirect_to_a_foreign_host(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, URL, status=302, headers={"Location": "https://example.com/"})
    rsps.add(responses.GET, "https://example.com/", body="hi")
    with pytest.raises(UpstreamError) as err:
        Http().get(URL, service="x")
    assert err.value.reason == "hostNotAllowed"


def test_retries_server_errors_then_succeeds(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, URL, status=503)
    rsps.add(responses.GET, URL, status=502)
    rsps.add(responses.GET, URL, body="ok")
    assert Http().get(URL, service="x").text == "ok"
    assert len(rsps.calls) == 3


def test_gives_up_after_the_last_retry(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, URL, status=500)
    with pytest.raises(UpstreamError) as err:
        Http(retries=1).get(URL, service="svc")
    assert err.value.http_status == 500
    assert err.value.to_dict()["error"]["service"] == "svc"
    assert len(rsps.calls) == 2


def test_connection_errors_become_network_errors(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, URL, body=requests.ConnectionError("down"))
    with pytest.raises(NetworkError) as err:
        Http(retries=1).get(URL, service="svc")
    assert err.value.exit_code == 1


def test_403_is_not_retried_and_says_so(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.GET, URL, status=403)
    with pytest.raises(UpstreamError) as err:
        Http().get(URL, service="svc")
    assert len(rsps.calls) == 1
    assert "403" in (err.value.hint or "")


def test_post_sends_form_data(rsps: responses.RequestsMock) -> None:
    rsps.add(responses.POST, URL, body="done")
    assert Http().post(URL, service="x", data={"a": "1"}).text == "done"
    assert rsps.calls[0].request.body == "a=1"
