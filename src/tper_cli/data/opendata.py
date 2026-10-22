"""TPER open data: discovery of the current versions, download and local cache.

Datasets are published at https://solweb.tper.it/web/tools/open-data/open-data.aspx
under the Creative Commons Attribution 3.0 Italy licence. They are downloaded on
first use into the cache directory and refreshed when TPER publishes a new version.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tper_cli.errors import NetworkError, SetupError, TperError, UpstreamError
from tper_cli.http import Http

BASE = "https://solweb.tper.it/web/tools/open-data"
PAGE_URL = f"{BASE}/open-data.aspx"
DOWNLOAD_URL = f"{BASE}/open-data-download.aspx"
LICENSE = "Creative Commons Attribuzione 3.0 Italia"
LICENSE_URL = "https://creativecommons.org/licenses/by/3.0/it/"
ATTRIBUTION = "Dati: Tper S.p.A., open data (CC BY 3.0 IT)"

DATASETS = {
    "fermate": "Bus stops",
    "linee": "Bus lines",
    "lineefermate": "Stops served by each bus line",
    "zone": "Fare zones",
    "localitazone": "Locality to fare zone",
    "rivendite": "Ticket retailers",
    "stazioniferroviarie": "Railway stations",
    "lineeferroviarie": "Railway lines",
}
_VERSION_RE = re.compile(r"filename=(\w+)&(?:amp;)?version=(\d+)")
SERVICE = "tper-open-data"


class OpenDataStore:
    """Local, versioned cache of the TPER open data tables."""

    def __init__(
        self,
        http: Http,
        cache: Path,
        now: Callable[[], datetime],
        *,
        ttl: timedelta = timedelta(days=7),
        warn: Callable[[str], None] | None = None,
    ) -> None:
        self.http = http
        self.dir = cache / "opendata"
        self.now = now
        self.ttl = ttl
        self.warn = warn or (lambda message: sys.stderr.write(message + "\n"))
        self._tables: dict[str, list[dict[str, str]]] = {}

    # ------------------------------------------------------------------ manifest

    @property
    def manifest_path(self) -> Path:
        return self.dir / "manifest.json"

    def _manifest(self) -> dict[str, Any]:
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"checkedAt": None, "datasets": {}}
        return data if isinstance(data, dict) else {"checkedAt": None, "datasets": {}}

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        tmp.replace(self.manifest_path)

    def _fresh(self, manifest: dict[str, Any]) -> bool:
        checked = manifest.get("checkedAt")
        if not isinstance(checked, str):
            return False
        try:
            return self.now() - datetime.fromisoformat(checked) < self.ttl
        except ValueError:
            return False

    def _file(self, name: str, version: str) -> Path:
        return self.dir / f"{name}_{version}.csv"

    # ------------------------------------------------------------------ network

    def discover(self) -> dict[str, str]:
        """Current version of every published dataset."""
        html = self.http.get(PAGE_URL, service=SERVICE).text
        versions = dict(_VERSION_RE.findall(html))
        if not versions:
            raise UpstreamError(
                "The open data page did not list any dataset",
                service=SERVICE,
                hint="TPER may have changed the page. Please report it.",
                reason="unexpectedResponse",
            )
        return versions

    def _download(self, name: str, version: str) -> bytes:
        params = {
            "source": "solweb.tper.it",
            "filename": name,
            "version": version,
            "format": "csv",
        }
        body = self.http.get(DOWNLOAD_URL, service=SERVICE, params=params).content
        if body.lstrip()[:1] == b"<":
            raise UpstreamError(
                f"Dataset {name} {version} came back as HTML instead of CSV",
                service=SERVICE,
                reason="unexpectedResponse",
            )
        return body

    def update(self, names: list[str] | None = None, *, force: bool = False) -> dict[str, str]:
        """Download the datasets whose published version differs from the cached one."""
        wanted = names or list(DATASETS)
        versions = self.discover()
        manifest = self._manifest()
        datasets = dict(manifest.get("datasets") or {})
        for name in wanted:
            version = versions.get(name)
            if version is None:
                raise UpstreamError(
                    f"TPER no longer publishes the dataset {name!r}",
                    service=SERVICE,
                    reason="unexpectedResponse",
                )
            target = self._file(name, version)
            current = datasets.get(name) or {}
            if force or current.get("version") != version or not target.is_file():
                self.dir.mkdir(parents=True, exist_ok=True)
                target.write_bytes(self._download(name, version))
                for old in self.dir.glob(f"{name}_*.csv"):
                    if old != target:
                        old.unlink()
                datasets[name] = {"version": version, "fetchedAt": self.now().isoformat()}
                self._tables.pop(name, None)
        self._save_manifest({"checkedAt": self.now().isoformat(), "datasets": datasets})
        return {n: versions[n] for n in wanted}

    # ------------------------------------------------------------------ reading

    def _cached_path(self, name: str) -> Path | None:
        entry = (self._manifest().get("datasets") or {}).get(name)
        if not entry:
            return None
        path = self._file(name, str(entry["version"]))
        return path if path.is_file() else None

    def cached(self, name: str) -> list[dict[str, str]] | None:
        """The table if it is already on disk, without any network access."""
        if name in self._tables:
            return self._tables[name]
        path = self._cached_path(name)
        if path is None:
            return None
        self._tables[name] = parse_csv(path.read_bytes())
        return self._tables[name]

    def table(self, name: str) -> list[dict[str, str]]:
        """The table, downloading or refreshing it when needed."""
        if name not in DATASETS:
            raise SetupError(f"Unknown dataset {name!r}", reason="unknownDataset")
        have = self.cached(name)
        if have is not None and self._fresh(self._manifest()):
            return have
        try:
            self.update([name])
        except (NetworkError, UpstreamError) as exc:
            if have is None:
                raise self._unavailable(name, exc) from exc
            self.warn(f"warning: could not refresh {name} ({exc.message}); using cached data")
            return have
        loaded = self.cached(name)
        if loaded is None:  # pragma: no cover - update() always writes the file
            raise self._unavailable(name, None)
        return loaded

    @staticmethod
    def _unavailable(name: str, cause: TperError | None) -> SetupError:
        return SetupError(
            f"Open data {name!r} is not cached and could not be downloaded"
            + (f": {cause.message}" if cause else ""),
            hint="Connect to the internet and run `tper data update`.",
            reason="openDataUnavailable",
        )

    def status(self) -> list[dict[str, object]]:
        manifest = self._manifest()
        datasets = manifest.get("datasets") or {}
        rows: list[dict[str, object]] = []
        for name, description in DATASETS.items():
            entry = datasets.get(name) if isinstance(datasets, dict) else None
            rows.append(
                {
                    "dataset": name,
                    "description": description,
                    "version": entry.get("version") if entry else None,
                    "fetchedAt": entry.get("fetchedAt") if entry else None,
                    "cached": self._cached_path(name) is not None,
                }
            )
        return rows

    def clear(self) -> int:
        removed = 0
        if self.dir.is_dir():
            for path in self.dir.iterdir():
                path.unlink()
                removed += 1
        self._tables.clear()
        return removed


def decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")  # pragma: no cover - latin-1 never fails


def parse_csv(raw: bytes) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(decode(raw)), delimiter=";")
    return [
        {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
        for row in reader
    ]
