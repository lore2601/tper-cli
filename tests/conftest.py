"""Shared fixtures. Unit tests never touch the network: HTTP is mocked with ``responses``."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
import responses

from tper_cli import cli
from tper_cli.data import opendata
from tper_cli.http import Http

FIXTURES = Path(__file__).parent / "fixtures"
ROME = ZoneInfo("Europe/Rome")
NOW = datetime(2026, 10, 22, 19, 30, tzinfo=ROME)
HELLOBUS = "https://hellobuswsweb.tper.it/web-services/hellobus.asmx/QueryHellobus"
RESALE = "https://hellobuswsweb.tper.it/web-services/hellobus.asmx/QueryResale"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def hellobus_xml(text: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<string xmlns="https://hellobuswsweb.tper.it/web-services/hellobus.asmx">{text}</string>'
    )


@pytest.fixture
def rsps() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for key in list(__import__("os").environ):
        if key.startswith("TPER_"):
            monkeypatch.delenv(key)
    values = {
        "TPER_CONFIG_DIR": str(tmp_path / "config"),
        "TPER_CACHE_DIR": str(tmp_path / "cache"),
        "TPER_STATE_DIR": str(tmp_path / "state"),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> datetime:
    monkeypatch.setattr(cli, "rome_now", lambda: NOW)
    return NOW


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries must not slow the suite down."""
    original = Http.__init__

    def init(self: Http, **kwargs: Any) -> None:
        kwargs.setdefault("sleep", lambda _seconds: None)
        original(self, **kwargs)

    monkeypatch.setattr(Http, "__init__", init)


@dataclass
class Result:
    code: int
    out: str
    err: str

    @property
    def json(self) -> Any:
        return json.loads(self.out)

    @property
    def error(self) -> dict[str, Any]:
        return json.loads(self.err.strip().splitlines()[-1])["error"]


@pytest.fixture
def run(
    env: dict[str, str], frozen: datetime, capsys: pytest.CaptureFixture[str]
) -> Callable[..., Result]:
    def invoke(*args: str) -> Result:
        code = cli.run(list(args))
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return invoke


@pytest.fixture
def mock_opendata(rsps: responses.RequestsMock) -> responses.RequestsMock:
    """The open data index page and the (reduced) CSV downloads."""
    rsps.add(responses.GET, opendata.PAGE_URL, body=fixture_text("open-data.html"))

    def download(request: Any) -> tuple[int, dict[str, str], bytes]:
        name = parse_qs(urlparse(request.url).query)["filename"][0]
        path = FIXTURES / "opendata" / f"{name}.csv"
        if not path.is_file():
            return 200, {}, b"<html>not a csv</html>"
        return 200, {}, path.read_bytes()

    rsps.add_callback(
        responses.GET, re.compile(re.escape(opendata.DOWNLOAD_URL) + r".*"), callback=download
    )
    return rsps
