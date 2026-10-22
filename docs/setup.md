# Setting up tper

`tper` needs no account, token or API key. Install it and run it.

```bash
pipx install git+https://github.com/lore2601/tper-cli
tper doctor
```

`tper doctor` calls every online service the CLI uses (Hello Bus, the open data index, the RSS feed, Trenitalia's notices page, the zone calculator and the complaint form) and tells you which one answers. `tper doctor --offline` only checks local files.

## The open data cache

Stops, lines, zones, retailers and rail stations come from TPER's open data. They are downloaded the first time a command needs them and stored in the cache directory (`~/.cache/tper-cli/opendata`, or `$XDG_CACHE_HOME/tper-cli`, or `TPER_CACHE_DIR`).

- The index page is checked at most once a week; a dataset is downloaded again only when TPER publishes a new version.
- If the network is down, the cached copy is used and a warning goes to stderr.
- `tper data status` shows versions and the licence, `tper data update [--force] [NAMES]` refreshes, `tper data clear` deletes the cache.
- A bus arrival by **stop code** (`tper bus arrivals 4476`) never triggers a download. It then shows the stop name only if the data is already cached.

Zone counts and the list of place names are cached for 30 days next to the open data.

## Optional: defaults

```bash
tper config init     # writes ~/.config/tper-cli/config.toml
```

```toml
[defaults]
fare_profile = "under27"   # ordinary | under27 | over65 | over70
basin = "bologna"          # price list used by `fare quote --zones N`

[policy]
read_only = false          # true blocks everything that sends data to TPER
```

Environment variables (`TPER_FARE_PROFILE`, `TPER_BASIN`, `TPER_READ_ONLY`, `TPER_FORMAT`) override the file.

## Optional: complaints

Filing a complaint needs your personal details, exactly as the TPER form asks for them. See [claims.md](claims.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| `openDataUnavailable` (exit 2) | The open data is not cached and TPER could not be reached. Connect and run `tper data update`. |
| `ambiguous` (exit 3) on a stop name | Several stops share the name (one per direction). Pick a code from `candidates`. |
| `placeNotFound` / `ambiguous` on a fare place | The zone calculator only knows municipality-level names. `tper fare places TEXT` lists them; or pass `--zones N`. |
| `stopNotFound` | Hello Bus does not manage that stop code. Find the right one with `tper bus stops search`. |
| `message: "OGGI NESSUNA ALTRA CORSA…"` | Not an error: no more runs of that line at that stop today. |
| `formChanged` (exit 1) | TPER changed a page this CLI reads. Run `tper doctor`, then please [open an issue](https://github.com/lore2601/tper-cli/issues). |
| `profileMissing` (exit 2) | Run `tper claim profile init` in a terminal. |
