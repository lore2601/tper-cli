# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-10-22

### Added

- `tper rail board STATION` and `tper rail train NUMBER`: live departures and arrivals of a
  station and single-train tracking (expected time, delay, platform, carrier, next stops) from
  RFI's live station boards, including Trenitalia Tper regional services. Stations are resolved
  by name; `rail stations --rfi` lists the names that have a board.
- `tper doctor` checks the RFI board, and a live contract test covers the board parser.

### Changed

- The README and docs no longer say that trains cannot be followed: they explain why the data
  comes from station boards and not from ViaggiaTreno.

## [0.1.0] - 2026-10-22

### Added

- `tper bus arrivals` for live (GPS) and timetable arrivals through TPER Hello Bus, with a
  countdown in minutes, stops by code or by unambiguous name, and `NESSUNA ALTRA CORSA`
  reported as a message.
- `tper bus stops search | near | get`, `bus lines`, `bus line` on the TPER open data
  (CC BY 3.0 IT): accent- and typo-tolerant search, lines per stop, fare zone, nearest ticket
  retailer.
- `tper rail lines | stations | alerts`: FER lines and stations, and Trenitalia's disruption
  and works notices by region.
- `tper news` from TPER's RSS feeds, merged and de-duplicated by link, filterable by line,
  category and date.
- `tper fare places | zones | quote | list | compare`: zone counts from TPER's official zone
  calculator (cached), the official price list for the Bologna, Ferrara and Imola urban
  networks and extra-urban zones 1 to 10 plus Ferrobus, reduced profiles (under 27, over 65,
  over 70), and a cost comparison with break-even point.
- `tper claim profile | file | history | check`: complaints through TPER's web form over plain
  HTTP, with a 0600 local profile, masked previews, mandatory confirmation, read-only mode and
  duplicate protection. Experimental.
- `tper data`, `tper doctor`, `tper config`, `tper schema`.
- JSON / NDJSON / table output, `--fields`, stable exit codes, JSON errors with hints.
- Agent skill (`skills/tper/SKILL.md`) and Claude Code plugin marketplace manifest.
- A weekly workflow that runs contract tests against the real services and compares the bundled
  price list with tper.it.

[Unreleased]: https://github.com/lore2601/tper-cli/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/lore2601/tper-cli/releases/tag/v0.2.0
[0.1.0]: https://github.com/lore2601/tper-cli/releases/tag/v0.1.0
