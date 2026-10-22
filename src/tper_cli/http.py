"""A small HTTP layer: honest User-Agent, timeouts, retries, host allowlist.

Every network call of the CLI goes through :class:`Http`, so politeness and
failure handling live in one place.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from urllib.parse import urlparse

import requests

from tper_cli import __version__
from tper_cli.errors import NetworkError, UpstreamError

USER_AGENT = (
    f"Mozilla/5.0 (compatible; tper-cli/{__version__}; +https://github.com/lore2601/tper-cli)"
)

# Hosts the CLI is allowed to talk to (and to be redirected to).
ALLOWED_HOSTS = (
    "tper.it",
    "solweb.tper.it",
    "hellobuswsweb.tper.it",
    "static.tper.it",
    "s3.eu-south-1.amazonaws.com",
    "trenitalia.com",
)
RETRY_STATUS = {429, 500, 502, 503, 504}


def host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


class Http:
    """``requests`` wrapper with retries and an allowlist."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        retries: int = 2,
        backoff: float = 0.6,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._sleep = sleep

    def request(
        self,
        method: str,
        url: str,
        *,
        service: str,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        retry: bool = True,
    ) -> requests.Response:
        if not host_allowed(url):
            raise UpstreamError(
                f"Refusing to contact {urlparse(url).hostname!r}",
                service=service,
                reason="hostNotAllowed",
            )
        attempts = (self.retries if retry else 0) + 1
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self.session.request(
                    method, url, params=params, data=data, timeout=self.timeout
                )
            except requests.RequestException as exc:
                last = exc
            else:
                if not host_allowed(response.url):
                    raise UpstreamError(
                        f"Redirected to a host that is not allowed: {response.url}",
                        service=service,
                        reason="hostNotAllowed",
                    )
                if response.status_code not in RETRY_STATUS or attempt == attempts - 1:
                    return self._check(response, service)
                last = None
            if attempt < attempts - 1:
                self._sleep(self.backoff * (2**attempt))
        raise NetworkError(
            f"Could not reach {service}: {last}",
            hint="Check your internet connection and retry.",
            details={"service": service},
        )

    def get(
        self, url: str, *, service: str, params: Mapping[str, str] | None = None
    ) -> requests.Response:
        return self.request("GET", url, service=service, params=params)

    def post(
        self, url: str, *, service: str, data: Mapping[str, str] | None = None
    ) -> requests.Response:
        return self.request("POST", url, service=service, data=data)

    @staticmethod
    def _check(response: requests.Response, service: str) -> requests.Response:
        if response.status_code >= 400:
            hint = "Retry later." if response.status_code >= 500 else None
            if response.status_code == 403:
                hint = "The service refused the request (HTTP 403). Do not retry in a loop."
            raise UpstreamError(
                f"{service} answered HTTP {response.status_code}",
                service=service,
                http_status=response.status_code,
                hint=hint,
            )
        return response
