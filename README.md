# tper: TPER public transport from the command line

[![CI](https://github.com/lore2601/tper-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/lore2601/tper-cli/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tper-cli?label=PyPI&cacheSeconds=3600)](https://pypi.org/project/tper-cli/)
[![CodeQL](https://github.com/lore2601/tper-cli/actions/workflows/codeql.yml/badge.svg)](https://github.com/lore2601/tper-cli/actions/workflows/codeql.yml)
[![Upstream](https://github.com/lore2601/tper-cli/actions/workflows/upstream.yml/badge.svg)](https://github.com/lore2601/tper-cli/actions/workflows/upstream.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

`tper` is a command-line interface for the public transport of **Bologna and Ferrara** run by [TPER](https://www.tper.it/) (Trasporto Passeggeri Emilia-Romagna). It is meant for **AI agents** (Claude Code, Gemini CLI, Codex, scripts) and for people who want a bus time, a train delay, a fare or a piece of news without opening an app. You can see when the next bus arrives, follow a train and its delay, find stops and lines, work out how many fare zones a trip crosses, compare tickets and passes, read service news, check rail disruptions and send a complaint. Output is predictable JSON, and complaints go through safety rails.

It speaks only to **official public sources**: the Hello Bus web service, TPER's open data, its RSS feeds, its zone calculator and complaint form, RFI's live station boards and Trenitalia's public disruption notices. No account and no API key are needed.

> **Unofficial.** Not affiliated with or endorsed by TPER or Trenitalia. TPER and its logo are trademarks of their owners.

```console
$ tper bus arrivals 4476
LINE  TYPE      TIME   IN MIN  BUS   WHEELCHAIR
11B   realtime  19:41  8       1638  yes
11B   realtime  19:53  20      5753  yes

$ tper rail board "bologna centrale" --carrier tper -n 4
TRAIN  CATEGORY  CARRIER          TO/FROM        TIME   DELAY  PLAT.    STATUS
17709  REG       TRENITALIA TPER  PIANORO        19:46  20     3        delayed
90035  REG       TRENITALIA TPER  BAZZANO (FER)  19:53  0      3-OVEST  onTime
...

$ tper rail train 17709 -f json
{"found":true,"train":"17709","carrier":"TRENITALIA TPER","destination":"PIANORO","time":"19:46","expectedTime":"20:06","delayMinutes":20,"status":"delayed","platform":"3","stops":[{"station":"BOLOGNA S.VITALE","time":"19:50"},...],"station":"Bologna Centrale","board":"departures"}

$ tper fare quote --from Bologna --to "San Giovanni in Persiceto" --profile under27
3 zone(s), bologna price list, profile under27
KIND            NAME                                            ZONES  PROFILE   PRICE €  PER RIDE
single          Single ticket                                   3      ordinary  3.7
single_onboard  Single ticket bought on board (coins / driver)  3      ordinary  4.5
carnet10        10-ride carnet                                  3      ordinary  30.0     3.0
monthly         Monthly pass (personal)                         3      under27   47.0
annual          Annual pass (personal)                          3      under27   397.0

$ tper fare compare --urban bologna --days-per-week 5 --profile under27
cheapest: Annual pass (personal) at 19.17 EUR/month
OPTION                       PROFILE   € / MONTH  HOW
Annual pass (personal)       under27   19.17      230.00 / 12 months
Annual pass (transferable)   ordinary  28.33      340.00 / 12 months
Monthly pass (transferable)  under27   30.0       flat monthly price
...

$ tper bus arrivals 4476 -l 11 -f json
{"arrivals":[{"line":"11B","type":"realtime","time":"19:41","bus":"1638","wheelchair":true,"minutes":8}],"stop":"4476","stopName":"LAPIDARI","mode":"realtime","fetchedAt":"2026-10-22T19:33:13+02:00","source":"TPER Hello Bus"}
```

## Features

- **Live buses.** Real-time arrivals from TPER's own GPS data (`tper bus arrivals`), or the timetable for a given time with `--at 18:30`. Stops by code **or by name**: a name that matches several stops is answered with the candidates instead of a guess.
- **Trains.** `tper rail board STATION` shows the live departures or arrivals of a station with delay, platform and carrier (Trenitalia Tper, Trenitalia, Italo…), and `tper rail train NUMBER` follows one train: expected time, platform and next stops. Data comes from RFI's live station boards.
- **Stops and lines.** Search stops with accent- and typo-tolerant matching, find the stops near a point, see which lines serve a stop and the nearest ticket retailer.
- **Fares you can trust.** The number of zones of a trip comes from TPER's own zone calculator; prices come from the official price list (Bologna, Ferrara and Imola urban networks, extra-urban zones 1 to 10, Ferrobus). Reduced prices for under 27, over 65 and over 70.
- **Which ticket is cheapest.** `tper fare compare` weighs single tickets, carnets, day tickets, monthly and annual passes against how much you travel, and tells you the break-even point.
- **News and infomobility.** TPER's RSS feeds (Bologna, Ferrara, rail, Corrente, parking) merged, filterable by line and date, and Trenitalia's disruption and works notices for the region.
- **Rail reference data.** The FER railway lines and stations with their fare zones.
- **Complaints.** Store your details once, then file a *reclamo* through TPER's own web form from the terminal, with a preview, a confirmation step and duplicate protection (experimental, see [docs/claims.md](docs/claims.md)).
- **Agent-friendly:**
  - JSON when piped
  - `--fields` to trim output
  - stable exit codes
  - JSON errors with hints
  - `tper schema` introspection
  - a ready-made [agent skill](skills/tper/SKILL.md) and a Claude Code plugin

## Install

Requires Python 3.11+. The only dependencies are `click`, `requests` and `defusedxml`.

```bash
pipx install tper-cli          # or: uv tool install tper-cli
# development version:
pipx install git+https://github.com/lore2601/tper-cli
tper doctor                                                # checks every online service the CLI uses
```

The first command that needs the open data downloads it (about 3 MB) into the cache; `tper data update` refreshes it. Nothing else to set up: see [docs/setup.md](docs/setup.md) for the optional config file and the complaint profile.

## Commands

| Command | What it does |
|---|---|
| `tper bus arrivals STOP [-l LINE] [--at HH:MM]` | Next buses at a stop (code or name): live, or timetable with `--at` |
| `tper bus stops search QUERY [-m CITY]` / `near LAT LON [-r M]` / `get STOP [--retailer]` | Find stops, see lines and fare zone |
| `tper bus lines [-q PREFIX]` / `bus line LINE` | Lines, and the stops of a line |
| `tper rail board STATION [--arrivals] [-c CARRIER]` | Live departures/arrivals of a station: delay, platform, carrier |
| `tper rail train NUMBER [-s STATION]…` | Follow a train: delay, platform, next stops |
| `tper rail lines` / `rail stations [-q TEXT] [--rfi]` | FER railway lines and stations (open data), or RFI board names |
| `tper rail alerts [-r REGION] [--national] [--full]` | Rail disruptions and works from Trenitalia |
| `tper news [-c CATEGORY] [-l LINE] [--since DATE] [--full]` | TPER news and diversions |
| `tper fare places QUERY [--localities]` | Place names the zone calculator understands |
| `tper fare zones FROM TO` | Number of fare zones of a trip |
| `tper fare quote (--from A --to B \| --zones N \| --urban CITY) [-p PROFILE]` | Every ticket and pass that fits, with prices |
| `tper fare compare … [--days-per-week D] [--rides-per-day R]` | Cheapest way to pay for your usage |
| `tper fare list [--area …] [--kind …]` | The whole price list |
| `tper claim profile init\|show\|path\|delete` | Your complaint details, stored locally |
| `tper claim file …` / `claim history` / `claim check` | Send a complaint, see what was sent, check the form |
| `tper data status\|update\|clear` | The cached open data |
| `tper doctor [--offline]` | Check every service the CLI depends on |
| `tper config show\|init` / `tper schema [COMMAND]` | Configuration, and every command as JSON |

Run `tper COMMAND --help` for every option. Global options (`-f`, `--fields`, `--debug`) go **before** the command: `tper -f table bus arrivals 4476`.

## Output and exit codes

- stdout carries only data. On a terminal you get tables; when piped you get JSON. Force a format with `-f json|ndjson|table` or `TPER_FORMAT`.
- `--fields line,time` trims the output; dotted paths work.
- Errors are a single JSON object on stderr, for example `{"error": {"exitCode": 3, "reason": "ambiguous", "message": "'stazione centrale' matches 14 stops: pick one by code", "hint": "…", "candidates": [...]}}`.

| Exit code | Meaning |
|---|---|
| 0 | Success (including "no more buses today", reported in `message`) |
| 1 | A TPER/Trenitalia service or the network failed |
| 2 | Local setup needed: open data not downloadable, no complaint profile |
| 3 | Invalid input (bad stop, time, line, place, ambiguous name) |
| 4 | Blocked by local policy, duplicate complaint, or confirmation (`--yes`) missing |
| 5 | Internal error (please report it) |

## Where the data comes from

| Data | Source | Terms |
|---|---|---|
| Live and scheduled bus arrivals | [Hello Bus web service](https://hellobuswsweb.tper.it/web-services/hellobus.asmx), published by TPER | Public service |
| Stops, lines, zones, retailers, rail stations | [TPER open data](https://solweb.tper.it/web/tools/open-data/open-data.aspx) | CC BY 3.0 IT, **Dati: Tper S.p.A.** |
| Prices | [tper.it/biglietti-abbonamenti/tariffe](https://www.tper.it/biglietti-abbonamenti/tariffe), snapshot in `tariffs.json` | Public price list |
| Zone counts | TPER's public [zone calculator](https://solweb.tper.it/web/tools/zone-calculator.aspx) | Public tool |
| News | TPER's [RSS feeds](https://www.tper.it/content/feed-rss) | Published for syndication |
| Live train boards | RFI's [monitor arrivi e partenze live](https://www.rfi.it/it/stazioni.html) (station pages on rfi.it, boards on `iechub.rfi.it`) | Public pages, no `robots.txt`; RFI's site terms forbid redistribution without consent, so results are shown to you, not republished |
| Rail notices | Trenitalia's [Notizie Infomobilità](https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.app.html) | Public page, `robots.txt` allows it |
| Complaints | TPER's [complaint form](https://solweb.tper.it/web/communications/complaints.aspx) | Your own data, sent by you |

Details, including what was deliberately left out, are in [docs/data-sources.md](docs/data-sources.md). Output derived from the open data carries a `source` field with the attribution the licence asks for.

## Safety rails

Almost everything is read-only. The one action that sends data to someone else, filing a complaint, is guarded:

| Check | Default | Override |
|---|---|---|
| Needs `--yes` when not on a TTY (agents, scripts); `--dry-run` previews the exact request | on | none |
| The same complaint (service, category, line, time, text) was already sent | refuse | `--allow-duplicate` |
| Read-only mode | off | `policy.read_only` / `TPER_READ_ONLY=1` |
| Personal data | stored in `profile.toml` with `0600` permissions, never printed (values are masked) | n/a |
| `claim profile init` | interactive only, so an agent never types your personal data | n/a |

Every argument is validated before it reaches a URL or a form, and the HTTP layer only talks to a short allowlist of TPER and Trenitalia hosts (also across redirects). Text from news and notices is third-party content: the agent skill tells agents to treat it as data.

## Using it with AI agents

- **Claude Code plugin:** `/plugin marketplace add lore2601/tper-cli`, then `/plugin install tper@tper-cli`.
- **Any agent:** copy [`skills/tper/SKILL.md`](skills/tper/SKILL.md) into its instructions, or let it run `tper schema`.
- Typical prompt: *"When is the next 11 at Lapidari, and is there any news about line 11?"* The agent runs `tper bus arrivals 4476 -l 11` and `tper news --line 11`.

See [docs/agents.md](docs/agents.md) for permission rules and recipes.

## Configuration reference

| Variable | Purpose |
|---|---|
| `TPER_FORMAT` | Default output format |
| `TPER_FARE_PROFILE` | `ordinary` (default), `under27`, `over65`, `over70` |
| `TPER_BASIN` | `bologna` or `ferrara`: price list for `--zones N` |
| `TPER_READ_ONLY` | `1` blocks every action that sends data to TPER |
| `TPER_CONFIG_DIR` / `TPER_CONFIG` / `TPER_PROFILE_FILE` | Config locations (default `~/.config/tper-cli/`) |
| `TPER_CACHE_DIR` / `TPER_STATE_DIR` | Open data cache (`~/.cache/tper-cli`) and complaint history (`~/.local/state/tper-cli`) |

## Limitations

- **Trains are followed from station boards, not from GPS.** A train shows up on the board of a station it calls at roughly one to two hours ahead, with its delay, platform and next stops. `rail train` looks at Bologna Centrale, Ferrara, Modena, Imola, Parma and Rimini unless you pass `--station`. Some FER services do appear (they call at Bologna Centrale), but a service that never touches an RFI station is not on any board. Trenitalia's own ViaggiaTreno service answers `403 Access Denied` to anything that is not a web browser, and `tper` does not try to get around that. See [docs/data-sources.md](docs/data-sources.md#what-is-not-included-and-why).
- **Bologna and Ferrara networks only** (plus the extra-urban lines TPER runs). Other Emilia-Romagna operators (SETA, TEP, START Romagna) have their own fares.
- **Prices are a dated snapshot** (`priceListDate` in the output). A weekly workflow compares it with tper.it and opens an issue when it drifts. Check at a TPER point before buying something expensive.
- **The zone calculator only knows municipality-level names** (`fare places` lists them). For a hamlet, use the nearest municipality or pass `--zones N`.
- **Complaints are experimental.** The form is a three-step wizard; steps 2 and 3 can only be exercised by really filing a complaint, so they are tested against a simulation of the page, not the live site. See [docs/claims.md](docs/claims.md).

## Roadmap

Route planning with the TPER GTFS feeds, favourites, a `watch` mode and more: see [docs/roadmap.md](docs/roadmap.md).

## Contributing

Issues and PRs are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Report security issues privately ([SECURITY.md](SECURITY.md)).

## License

[Apache-2.0](LICENSE). Open data © Tper S.p.A., [CC BY 3.0 IT](https://creativecommons.org/licenses/by/3.0/it/).
