"""A local record of submitted complaints, to avoid filing the same one twice."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class Ledger:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "claims.jsonl"

    def _rows(self) -> list[dict[str, object]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows: list[dict[str, object]] = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def find(self, fingerprint: str) -> dict[str, object] | None:
        return next((r for r in self._rows() if r.get("fingerprint") == fingerprint), None)

    def add(self, fingerprint: str, when: datetime, line: str, event_date: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "fingerprint": fingerprint,
            "submittedAt": when.isoformat(timespec="seconds"),
            "line": line,
            "eventDate": event_date,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        self.path.chmod(0o600)

    def all(self) -> list[dict[str, object]]:
        return self._rows()
