# Notes for coding agents working on this repository

- Python 3.11+, package in `src/tper_cli`, CLI built with `click`, HTTP with `requests`. Runtime dependencies are only `click`, `requests` and `defusedxml`: do not add heavy ones (no browser automation, no HTML parsing library; `htmlutil.py` is enough).
- Layout:
  - `http.py`: the only place that talks to the network (honest User-Agent, retries, host allowlist).
  - `hellobus.py`: Hello Bus client and the parser of its text answers.
  - `data/opendata.py` (download, versioned cache) and `data/catalog.py` (typed views).
  - `webforms.py`, `zones.py`: ASP.NET WebForms sessions over HTTP and the zone calculator.
  - `fares.py` + `data/tariffs.json` (built by `tools/build_tariffs.py`): the price list and the comparison logic.
  - `news.py` (RSS), `infomobility.py` (Trenitalia notices), `rfi.py` (live station boards: names, `placeId`, board parser).
  - `claim/`: profile (0600), claim model, ledger, Telerik helpers and the wizard (`form.py`).
  - `commands/*`: one click group or command per module. `cli.py`: root command and error handling.
- Run `uv run ruff format src tests tools && uv run ruff check src tests tools && uv run mypy && uv run pytest` before finishing. Coverage must stay at or above 80%.
- Anything that sends data to TPER must call `app.guard_write(...)`. Validate every argument in `validation.py`, and add tests for rejected input.
- Never add network calls to unit tests. Mock them with `responses` (see `tests/conftest.py`). Real-service checks live in `tests/live/` behind `-m live`.
- When a parser reads a page or feed, keep a trimmed real sample in `tests/fixtures/`.
- Do not work around access controls: if a service answers 403 to a polite client, it stays out of scope (see `docs/data-sources.md`).
- Keep `skills/tper/SKILL.md`, `README.md` and `docs/` in sync with the command surface. Prices change: `python tools/build_tariffs.py` regenerates `tariffs.json`.
