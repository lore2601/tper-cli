"""Build or verify ``src/tper_cli/data/tariffs.json`` from the official TPER fares page.

    python tools/build_tariffs.py            # fetch the page and rewrite the JSON
    python tools/build_tariffs.py --check    # fetch the page, exit 1 if the JSON is stale
    python tools/build_tariffs.py --from-text tests/fixtures/tariffe.txt

The page is parsed with a small state machine over its visible text lines. Parsing is
deliberately strict: if the page layout changes, the sanity checks fail loudly instead of
producing wrong prices.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

URL = "https://www.tper.it/biglietti-abbonamenti/tariffe"
OUT = Path(__file__).resolve().parent.parent / "src" / "tper_cli" / "data" / "tariffs.json"
USER_AGENT = "Mozilla/5.0 (compatible; tper-cli-tools; +https://github.com/lore2601/tper-cli)"

PRICE = re.compile(r"^(\d+(?:,\d+)?)€$")
ZONES_ROW = re.compile(r"^(\d+) zon[ae]$")
SINGLE_ROW = re.compile(r"^(\d+) zon[ae] validità (\d+) minuti$")
URBAN_PRODUCT = re.compile(
    r"^(Biglietto ordinario|Carnet da 10 viaggi \(CityPass\)|Giornaliero|Ecoticket|"
    r"Mensile Impersonale|Mensile Personale|Annuale Impersonale|Annuale Personale)\s+"
    r"(?:da )?(\d+(?:,\d+)?)€"
)
REDUCED = re.compile(
    r"(inferiore ai 27|superiore ai (65|70)) anni\.\s*Il costo dell'abbonamento "
    r"[a-z ]*?ridotto(?: anziani)? è di (\d+(?:,\d+)?)€"
)
ONBOARD = re.compile(r"acquistato a bordo è di (\d+(?:,\d+)?)€")
URBAN_KINDS = {
    "Biglietto ordinario": ("single", 1),
    "Carnet da 10 viaggi (CityPass)": ("carnet10", 10),
    "Giornaliero": ("day", None),
    "Ecoticket": ("ecoticket", 20),
    "Mensile Impersonale": ("monthly_anonymous", None),
    "Mensile Personale": ("monthly", None),
    "Annuale Impersonale": ("annual_anonymous", None),
    "Annuale Personale": ("annual", None),
}
TABLE_KINDS = {"Mensile Personale": "monthly", "Annuale Personale": "annual"}
CITIES = {"Bologna": "bologna", "Ferrara": "ferrara", "Imola": "imola"}
BASINS = {"Bacino di Bologna": "bologna", "Bacino di Ferrara": "ferrara"}


def money(text: str) -> float:
    return float(text.replace(",", "."))


def flatten(markup: str) -> list[str]:
    """Visible text of the page body, one block per line."""
    start = markup.find("<main")
    markup = markup[start:] if start >= 0 else markup
    end = markup.find("Contatti Via di Saliceto")
    markup = markup[:end] if end >= 0 else markup
    markup = re.sub(r"(?s)<(script|style).*?</\1>", "", markup)
    markup = re.sub(r"</(p|div|li|h\d|tr|td|th)>|<br\s*/?>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


def profile_of(header: str) -> str:
    h = header.lower()
    if "under 27" in h:
        return "under27"
    if "over 70" in h:
        return "over70"
    if "over 65" in h:
        return "over65"
    return "ordinary"


def product(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "area": None,
        "network": None,
        "kind": None,
        "profile": "ordinary",
        "zones": None,
        "rides": None,
        "validityMinutes": None,
        "price": None,
    }
    base.update(kw)
    return base


def parse(lines: list[str]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    area: str | None = None
    network: str | None = None
    kind: str | None = None  # extra-urban sub-section kind
    table_kind: str | None = None
    columns: list[str] = []
    current: dict[str, object] | None = None  # last urban product, for reduced prices
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "Area Urbana":
            area, network, kind, table_kind = "urban", None, None, None
        elif line == "Area Extraurbana":
            area, network, kind, table_kind = "extraurban", None, None, None
        elif line == "Servizio Ferroviario":
            area, network, kind, table_kind = "rail", None, None, None
        elif area == "urban" and line in CITIES:
            network, current = CITIES[line], None
        elif area == "extraurban" and line in BASINS:
            network, kind, table_kind, current = BASINS[line], None, None, None
        elif area == "urban" and network:
            m = URBAN_PRODUCT.match(line)
            if m:
                k, rides = URBAN_KINDS[m.group(1)]
                price = money(m.group(2))
                if k == "carnet10":
                    price = round(price * 10, 2)
                current = product(
                    area="urban",
                    network=network,
                    kind=k,
                    rides=rides,
                    price=price,
                    validityMinutes=75 if network == "bologna" and k == "single" else None,
                )
                out.append(current)
            else:
                ob = ONBOARD.search(line)
                if ob and current and current["kind"] == "single":
                    out.append({**current, "kind": "single_onboard", "price": money(ob.group(1))})
                red = REDUCED.search(line)
                if red and current:
                    profile = "under27" if "27" in red.group(1) else f"over{red.group(2)}"
                    out.append({**current, "profile": profile, "price": money(red.group(3))})
        elif area == "extraurban" and network:
            if line.startswith("Acquistati a terra"):
                kind, table_kind = "single", None
            elif line.startswith("Acquistati a bordo"):
                kind, table_kind = "single_onboard", None
            elif line.startswith("Carnet da 10 corse"):
                kind, table_kind = "carnet10", None
            elif line in TABLE_KINDS:
                kind, table_kind, columns = None, TABLE_KINDS[line], []
            elif table_kind and line == "numero zone":
                columns = []
                j = i + 1
                while j < len(lines) and not ZONES_ROW.match(lines[j]):
                    columns.append(profile_of(lines[j]))
                    j += 1
                i = j - 1
            elif kind and (m := SINGLE_ROW.match(line)) and i + 1 < len(lines):
                p = PRICE.match(lines[i + 1])
                if p:
                    out.append(
                        product(
                            area="extraurban",
                            network=network,
                            kind=kind,
                            zones=int(m.group(1)),
                            rides=10 if kind == "carnet10" else 1,
                            validityMinutes=int(m.group(2)),
                            price=money(p.group(1)),
                        )
                    )
            elif table_kind and (m := ZONES_ROW.match(line)):
                j = i + 1
                prices: list[float] = []
                while j < len(lines) and (p := PRICE.match(lines[j])):
                    prices.append(money(p.group(1)))
                    j += 1
                profiles = columns or ["ordinary", "under27"]
                for profile, price in zip(profiles, prices, strict=False):
                    out.append(
                        product(
                            area="extraurban",
                            network=network,
                            kind=table_kind,
                            profile=profile,
                            zones=int(m.group(1)),
                            price=price,
                        )
                    )
                i = j - 1
        elif area == "rail" and line == "Abbonamenti mensili Ferrobus":
            j = i + 1
            while j < len(lines) - 1:
                m = ZONES_ROW.match(lines[j])
                if m and (p := PRICE.match(lines[j + 1])):
                    out.append(
                        product(
                            area="ferrobus",
                            network="bologna",
                            kind="ferrobus_monthly",
                            zones=int(m.group(1)),
                            price=money(p.group(1)),
                        )
                    )
                    j += 2
                elif (
                    ZONES_ROW.match(lines[j - 0]) is None and out and out[-1]["area"] == "ferrobus"
                ):
                    break
                else:
                    j += 1
            i = j
        i += 1
    return out


def clean(products: list[dict[str, object]]) -> list[dict[str, object]]:
    """Null prices that contradict their own table (a reduced price above the ordinary one)."""
    ordinary = {
        (p["area"], p["network"], p["kind"], p["zones"]): p["price"]
        for p in products
        if p["profile"] == "ordinary"
    }
    for p in products:
        if p["profile"] == "ordinary":
            continue
        base = ordinary.get((p["area"], p["network"], p["kind"], p["zones"]))
        if isinstance(base, float) and isinstance(p["price"], float) and p["price"] > base:
            p["note"] = (
                f"tper.it publishes {p['price']:g} EUR, higher than the ordinary price: "
                "treated as a typo, verify at a TPER point."
            )
            p["price"] = None
    for n, p in enumerate(products):
        p["id"] = "-".join(
            str(x)
            for x in (
                p["area"],
                p["network"],
                p["kind"],
                p["profile"],
                f"{p['zones']}z" if p["zones"] else None,
            )
            if x
        )
        p.setdefault("note", None)
        p["order"] = n
    return products


def sanity(products: list[dict[str, object]]) -> None:
    def count(**kw: object) -> int:
        return sum(all(p[k] == v for k, v in kw.items()) for p in products)

    problems = []
    for net in ("bologna", "ferrara"):
        for kind in ("single", "single_onboard", "carnet10"):
            if count(area="extraurban", network=net, kind=kind) != 10:
                problems.append(f"{net} {kind}: expected 10 zone rows")
        for kind in ("monthly", "annual"):
            if count(area="extraurban", network=net, kind=kind, profile="ordinary") != 10:
                problems.append(f"{net} {kind}: expected 10 ordinary rows")
    for net in ("bologna", "ferrara", "imola"):
        for kind in ("single", "carnet10"):
            if count(area="urban", network=net, kind=kind) != 1:
                problems.append(f"urban {net} {kind} missing")
    if count(area="ferrobus") != 10:
        problems.append("ferrobus: expected 10 rows")
    if problems:
        raise SystemExit("Fares page layout changed:\n  " + "\n  ".join(problems))


def build(lines: list[str], retrieved: str) -> dict[str, object]:
    products = clean(parse(lines))
    sanity(products)
    return {
        "schemaVersion": 1,
        "source": URL,
        "retrievedAt": retrieved,
        "currency": "EUR",
        "card": {"name": "Mi Muovo", "price": 5.0, "validityYears": 5},
        "products": products,
    }


def fetch() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--check", action="store_true", help="exit 1 when the JSON differs from the page"
    )
    ap.add_argument("--from-text", type=Path, help="parse an already flattened text file")
    args = ap.parse_args()
    lines = (
        args.from_text.read_text(encoding="utf-8").splitlines()
        if args.from_text
        else flatten(fetch())
    )
    lines = [ln.strip() for ln in lines if ln.strip()]
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
    data = build(lines, str(existing.get("retrievedAt", date.today().isoformat())))
    if args.check:
        if data["products"] != existing.get("products"):
            old = {p["id"]: p["price"] for p in existing.get("products", [])}
            new = {p["id"]: p["price"] for p in data["products"]}  # type: ignore[attr-defined]
            for key in sorted(set(old) | set(new)):
                if old.get(key) != new.get(key):
                    print(f"{key}: {old.get(key)} -> {new.get(key)}")
            print("tariffs.json is out of date: run `python tools/build_tariffs.py`.")
            return 1
        print(f"tariffs.json matches {URL} ({len(existing['products'])} products)")
        return 0
    data["retrievedAt"] = date.today().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(data['products'])} products)")  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    sys.exit(main())
