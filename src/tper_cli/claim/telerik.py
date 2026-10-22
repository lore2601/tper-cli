"""Reading and driving Telerik RadComboBox / RadDropDownList controls without a browser.

These controls render their options in the HTML and describe them (values, auto-postback)
in a ``$create(Telerik.Web.UI.Rad…, {json})`` call. The selected item travels back to the
server in the control's ``ClientState`` hidden field.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from tper_cli import search
from tper_cli.errors import NotFoundError, UpstreamError
from tper_cli.htmlutil import Node

_CREATE = re.compile(r"\$create\(Telerik\.Web\.UI\.(RadComboBox|RadDropDownList),\s*(\{)")
SERVICE = "tper-claims"


@dataclass(frozen=True)
class Choice:
    text: str
    value: str
    index: int


@dataclass(frozen=True)
class Combo:
    unique_id: str
    kind: str
    client_state: str
    choices: list[Choice]
    postback: bool


def discover(markup: str, root: Node) -> dict[str, Combo]:
    """Every combo / drop-down on the page, keyed by its unique id (``ctl00$...``)."""
    decoder = json.JSONDecoder()
    found: dict[str, Combo] = {}
    for match in _CREATE.finditer(markup):
        try:
            config, _ = decoder.raw_decode(markup, match.start(2))
        except ValueError:  # pragma: no cover - malformed script
            continue
        unique = config.get("_uniqueId")
        if not unique:
            continue
        element_id = unique.replace("$", "_")
        drop = root.by_id(f"{element_id}_DropDown")
        labels = [li.text() for li in drop.find_all("li")] if drop is not None else []
        data = config.get("itemData") or []
        choices = [
            Choice(
                text=labels[i] if i < len(labels) else "", value=str(d.get("value", "")), index=i
            )
            for i, d in enumerate(data)
            if i < len(labels)
        ]
        found[unique] = Combo(
            unique_id=unique,
            kind=match.group(1),
            client_state=config.get("clientStateFieldID") or f"{element_id}_ClientState",
            choices=choices,
            postback="_postBackReference" in config,
        )
    return found


def pick(combo: Combo, text: str) -> Choice:
    """The option whose label equals ``text`` (case- and accent-insensitive)."""
    wanted = search.normalize(text)
    for choice in combo.choices:
        if choice.text and search.normalize(choice.text) == wanted:
            return choice
    options = [c.text for c in combo.choices if c.text][:12]
    raise NotFoundError(
        f"{text!r} is not one of the options offered by the form",
        hint="Options include: " + "; ".join(options),
        reason="optionNotFound",
        details={"options": options},
    )


def state_for(combo: Combo, choice: Choice) -> str:
    base = {"enabled": True, "logEntries": [], "checkedIndices": []}
    if combo.kind == "RadDropDownList":
        base |= {
            "selectedIndex": choice.index,
            "selectedText": choice.text,
            "selectedValue": choice.value,
        }
    else:
        base |= {"value": choice.value, "text": choice.text, "checkedItemsTextOverflows": False}
    return json.dumps(base)


def require(combos: dict[str, Combo], unique_id: str) -> Combo:
    combo = combos.get(unique_id)
    if combo is None:
        raise UpstreamError(
            f"The complaint form no longer has the control {unique_id}",
            service=SERVICE,
            reason="formChanged",
            hint="TPER changed the form. Please report it.",
        )
    return combo
