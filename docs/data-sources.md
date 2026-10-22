# Data sources, terms and what is not included

`tper` talks to a short list of hosts (the allowlist is in [`http.py`](../src/tper_cli/http.py)): `tper.it`, `solweb.tper.it`, `hellobuswsweb.tper.it`, `trenitalia.com`, and TPER's static file host. Every request carries an honest User-Agent (`Mozilla/5.0 (compatible; tper-cli/x.y; +https://github.com/lore2601/tper-cli)`), uses timeouts and a few retries, and is made on your behalf from your own computer. There is no scraping farm, no proxy and no attempt to look like a browser.

| Source | Used for | How it is read | Terms |
|---|---|---|---|
| **Hello Bus** `hellobuswsweb.tper.it/web-services/hellobus.asmx` | `bus arrivals`, `bus stops get --retailer` | `QueryHellobus`, `QueryResale` over HTTP GET | TPER publishes the service definition. |
| **Open data** `solweb.tper.it/web/tools/open-data` | stops, lines, zones, localities, retailers, rail stations and lines | CSV downloads, cached by version | **CC BY 3.0 IT**; [legal notes](https://solweb.tper.it/web/tools/open-data/open-data-legal.aspx): attribute Tper S.p.A.; the Tper logo is a registered trademark and is not used here. |
| **Price list** `tper.it/biglietti-abbonamenti/tariffe` | `fare quote`, `fare list`, `fare compare` | Snapshot in `src/tper_cli/data/tariffs.json`, built by `tools/build_tariffs.py` | Public information; the snapshot is dated and checked weekly. |
| **Zone calculator** `solweb.tper.it/web/tools/zone-calculator.aspx` | `fare zones`, trips in `fare quote/compare` | Plain HTTP form post, like a browser; results cached 30 days | Public tool of TPER. It needs a browser-shaped User-Agent, which is why ours starts with `Mozilla/5.0`. |
| **RSS feeds** `tper.it/…/rss.xml` | `news` | RSS 2.0 | TPER offers them on its [feed page](https://www.tper.it/content/feed-rss). The feeds reuse one `guid` for every item, so the link identifies an item. |
| **RFI live boards** `www.rfi.it/it/stazioni.html`, `iechub.rfi.it/ArriviPartenze/ArrivalsDepartures/Monitor` | `rail board`, `rail train`, `rail stations --rfi` | The list of station names and each station page (to find its `placeId`) are read from rfi.it, then the board is a plain HTTP GET; names, ids and boards are cached (names and ids 30 days, boards only for the length of the command) | Public pages; neither host has a `robots.txt`. RFI's [terms](https://www.rfi.it/it/misc/termini-e-condizioni.html) forbid reproducing or distributing the content without consent and allow saving extracts for personal, non-commercial use: results are shown to the person who asked and never republished. The RFI and FS logos are not used. |
| **Notizie Infomobilità** `trenitalia.com/…/notizie-infomobilita.app.html` | `rail alerts` | HTML page; `robots.txt` has `Disallow:` (nothing) | Public page. Trenitalia's site terms forbid redistributing contents without consent: results are shown to you, not republished. |
| **Complaint form** `solweb.tper.it/web/communications/complaints.aspx` | `claim file`, `claim check` | The same WebForms POSTs a browser makes | It is your own complaint, sent by you. |

## Attribution

Anything derived from the open data carries `"source": "Dati: Tper S.p.A., open data (CC BY 3.0 IT)"`. If you redistribute that data, keep the attribution.

## What is not included, and why

- **Train GPS positions and ViaggiaTreno.** Trenitalia's ViaggiaTreno web service replies `HTTP 403 Access Denied` (an Akamai bot filter) to every client that is not a web browser, even for `robots.txt`, and its legal notes reportedly forbid copying its content without written consent. A CLI could only work by pretending to be a browser from a residential IP. That is the kind of workaround this project will not do. Live station boards (RFI) give the delay, platform and next stops of each train instead, which is what you need to decide when to leave.
- **Trains that are not on an RFI board.** Some FER services appear on the boards of the RFI stations where they call (for example at Bologna Centrale), but a service that stays entirely on FER's own network is on no board, and TPER publishes no real-time feed for it.
- **Buying tickets.** It needs an account, payment and bot protection. `tper` shows what to buy and where; it does not sell.
- **Trenitalia fares and booking (Le Frecce).** They use a private mobile API and block data-centre addresses.
- **Other operators** (SETA, TEP, START Romagna, Trenord). Not covered by TPER's data.
- **Any login-based service** (area riservata, MiMuovo card balance). Personal accounts are out of scope.

## Keeping up with changes

TPER and Trenitalia change pages without notice. Two safety nets exist:

- `tests/live/` holds contract tests against the real services (`uv run pytest -m live`). The weekly [`upstream` workflow](../.github/workflows/upstream.yml) runs them and opens an issue when one fails.
- `python tools/build_tariffs.py --check` compares the bundled price list with tper.it and exits `1` on any difference. When the prices change, run `python tools/build_tariffs.py`, review the diff and commit it. The parser refuses to produce a table if the page layout changes, rather than guessing.
