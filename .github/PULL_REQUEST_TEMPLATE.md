## Summary

<!-- What does this change and why? Link related issues (Fixes #123). -->

## Checklist

- [ ] Tests added or updated (`uv run pytest`)
- [ ] `uv run ruff format --check src tests tools && uv run ruff check src tests tools && uv run mypy` pass
- [ ] User-facing changes documented in `README.md` / `docs/` and `CHANGELOG.md` (Unreleased)
- [ ] Anything that sends data to TPER goes through `guard_write` (policy, `--dry-run`, `--yes`)
- [ ] New arguments are validated in `validation.py`
- [ ] New online sources are on the host allowlist (`http.py`) and documented in `docs/data-sources.md`
