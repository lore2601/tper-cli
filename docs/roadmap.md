# Roadmap

Ideas for what comes next, in rough order of value for effort. Nothing here is promised: items
marked *to verify* depend on a data source that has not been checked yet. The shipped features
are in the [README](../README.md) and the [CHANGELOG](../CHANGELOG.md).

Ground rules that apply to every item (see [CONTRIBUTING.md](../CONTRIBUTING.md)): official and
polite sources only, no workarounds for blocked services, light dependencies (no browser
automation), JSON output with stable exit codes, and anything that sends data to TPER goes
through `--dry-run` / `--yes`.

## Next: route planning

`tper go FROM TO [--at 08:30 | --arrive-by 09:00]` answers "how do I get from A to B by bus".

- **Data.** TPER's static GTFS feeds for Bologna and Ferrara (`gommagtfsbo`, `gommagtfsfe` in the
  open data, CC BY 3.0 IT), cached like the other datasets. *To verify first:* that both files
  download, cover the current service days and do not expire soon (a third-party catalogue listed
  one Ferrara download as failing).
- **Algorithm.** RAPTOR or Connection Scan in pure Python, with walking transfers between nearby
  stops estimated from straight-line distance. No routing service and no Google Maps: it is paid,
  needs a key and forbids storing its data.
- **Places.** First stops and well-known places by name (the search we already have), then
  `--from LAT,LON` for agents, then addresses through OpenStreetMap Nominatim (free, one request
  per second, attribution required) or an open municipal geocoder, if one exists.
- **Output.** Legs with line, boarding and alighting stop, times and walking distance, as JSON and
  as a table.
- **Limits, stated up front.** Buses of Bologna and Ferrara only; scheduled times from the GTFS,
  not live delays. Later, Hello Bus can refresh the imminent departures. No GTFS for the
  Emilia-Romagna rail network has been found, so trains stay on the live boards.
- **Tests.** Compare results with trips known from the TPER site, and keep a trimmed GTFS in
  `tests/fixtures/`.

## High value, low effort

- **Favourites and shortcuts.** Store `home`, `work` and usual stops in `config.toml`, so that
  `tper next home` or `tper go work` are enough.
- **`tper watch`.** Poll a train or a stop and alert when the delay passes a threshold, the train
  is cancelled or the platform changes. Output as JSON lines so an agent or a script can react.
- **Bus plus train in one answer.** Combine the RFI boards with Hello Bus: "train X is 20
  minutes late, bus Y still gets you there in time".

## Medium

- **Strikes.** Dates, hours and guaranteed services in a structured form. *To verify:* whether
  the Ministry or the Commissione di garanzia expose an API or only web pages. The TPER feeds
  already carry the news.
- **Sharing and parking** (Corrente, sosta). News is already in the RSS feeds; availability of
  bikes or spaces needs an API that has not been found yet. *To verify.*
- **Complaint from the facts.** Draft the complaint text from a line, a time and the delay
  observed on the boards, for the user to review before sending.
- **Shell completions** (bash, zsh, fish) and compact output for `fzf` or a status bar.
- **MCP server.** Expose the same modules to clients that do not run shell commands.

## Quality and upkeep

- **Validate the complaint wizard.** Steps 2 and 3 are only tested against a simulation of the
  page. The first real complaint is a chance to confirm them and drop the "experimental" label.
- **Other Emilia-Romagna operators** (SETA, START Romagna, TEP). *To verify:* which data each
  publishes, as was done for TPER.
- **Local delay history.** Keep the boards a user has already read to show punctuality by train
  and time of day. Local only: RFI's terms forbid redistributing its content.
- **Sharper change detection.** Beyond the weekly contract tests, compare feed and page
  structures and say exactly what changed.

## Out of scope

- **Buying tickets or anything behind a login.** It needs an account, payment and bot
  protection.
- **ViaggiaTreno.** It answers `403` to every client that is not a browser, and this project does
  not work around access controls (see [data-sources.md](data-sources.md)).

## Suggesting something

Open a [feature request](https://github.com/lore2601/tper-cli/issues/new?template=feature_request.yml)
with the official source that would provide the data and a link to its terms.
