# Contributing

Thanks for helping improve `tper`!

## Development setup

```bash
git clone git@github.com:lore2601/tper-cli.git
cd tper-cli
uv sync                     # creates .venv with runtime + dev dependencies
uv run tper --help
uv run pre-commit install   # optional: uvx pre-commit install
```

## Checks (same as CI)

```bash
uv run ruff format src tests tools
uv run ruff check src tests tools
uv run mypy
uv run pytest --cov
```

Unit tests never touch the network: HTTP is mocked with
[`responses`](https://github.com/getsentry/responses). The tests in `tests/live/` do talk to the
real services and are excluded by default; run them with `uv run pytest -m live` before and
after touching a parser.

## Design guidelines

- **stdout is data only.** Diagnostics go to stderr. Every failure raises a `TperError`
  subclass, which maps to a documented exit code.
- **Official, polite sources only.** Every request goes through `Http` (honest User-Agent,
  timeouts, host allowlist). A new host needs a line in `docs/data-sources.md` saying why it is
  allowed and under which terms. If a service blocks polite clients, it stays out: do not add
  browser impersonation, proxies or other workarounds.
- **Anything that sends data to TPER goes through `AppContext.guard_write`**: policy,
  `--dry-run` and confirmation.
- **Validate every argument** (stops, lines, times, places, dates) with `tper_cli.validation`
  before it reaches a URL or a form. Treat arguments as untrusted, because agents generate them.
- **Parsers fail loudly.** If a page or feed is not what the parser expects, raise
  `UpstreamError(reason="unexpectedResponse")` instead of returning something plausible. Keep a
  trimmed real sample in `tests/fixtures/` and add the check to `tests/live/`.
- **Keep dependencies light.** `click`, `requests`, `defusedxml`. No browser automation, no
  HTML parsing library: `htmlutil.py` is enough for what is parsed.
- **Keep default output compact.** Add detail behind `--full` / `--raw`.
- Update `README.md`, `docs/`, `skills/tper/SKILL.md` and `CHANGELOG.md` (Unreleased) for
  user-facing changes.

## When prices change

`python tools/build_tariffs.py --check` compares `src/tper_cli/data/tariffs.json` with
tper.it. If it reports a difference, run `python tools/build_tariffs.py`, read the diff, run
the tests and commit. The tool refuses to write anything if the page layout changed.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`,
`ci:`, `refactor:`, `test:`, `deps:`).

## Releasing (maintainers)

1. Update `__version__` in `src/tper_cli/__init__.py`, the versions in `.claude-plugin/*.json`,
   and move the `Unreleased` notes in `CHANGELOG.md` under the new version.
2. Commit, then tag and push: `git tag v0.2.0 && git push origin v0.2.0`.
3. The **Release** workflow tests, builds, attests and creates the GitHub release.

### Enabling PyPI publishing (one-time)

1. On PyPI, add a *pending trusted publisher*: project `tper-cli`, owner `lore2601`,
   repository `tper-cli`, workflow `release.yml`, environment `pypi`.
2. In GitHub → Settings → Environments, create the environment `pypi`. Optionally require
   reviewers.
3. In GitHub → Settings → Variables → Actions, add `PYPI_PUBLISH` = `true`.
