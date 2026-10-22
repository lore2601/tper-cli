"""Plain-HTTP sessions with the ASP.NET WebForms pages of solweb.tper.it.

A WebForms page keeps its state in hidden fields (``__VIEWSTATE`` and friends).
A browser sends them back with every action; so does this module, with ``requests``
only, no browser needed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from tper_cli.errors import UpstreamError
from tper_cli.htmlutil import Node, form_fields, parse_html
from tper_cli.http import Http


@dataclass
class WebFormPage:
    url: str
    service: str
    root: Node
    fields: dict[str, str]
    markup: str = ""

    @classmethod
    def parse(cls, url: str, service: str, markup: str) -> WebFormPage:
        root = parse_html(markup)
        fields = form_fields(root)
        if "__VIEWSTATE" not in fields:
            raise UpstreamError(
                f"{url} is not the expected form page",
                service=service,
                reason="unexpectedResponse",
                hint="TPER may have changed the page. Please report it.",
            )
        return cls(url, service, root, fields, markup)

    def text_of(self, element_id: str) -> str | None:
        node = self.root.by_id(element_id)
        return node.text() if node is not None else None


def load(http: Http, url: str, service: str) -> WebFormPage:
    return WebFormPage.parse(url, service, http.get(url, service=service).text)


def submit(
    http: Http,
    page: WebFormPage,
    values: dict[str, str],
    *,
    button: tuple[str, str] | None = None,
    event_target: str | None = None,
) -> WebFormPage:
    """POST the form back with ``values`` overriding the page defaults.

    ``button`` is the ``(name, value)`` of the submit control that was clicked, and
    ``event_target`` is the control that triggered an auto-postback.
    """
    data = dict(page.fields)
    data.update(values)
    if button:
        data[button[0]] = button[1]
    data["__EVENTTARGET"] = event_target or ""
    data["__EVENTARGUMENT"] = ""
    response = http.post(page.url, service=page.service, data=data)
    return WebFormPage.parse(page.url, page.service, response.text)


def combo(client_state_name: str, text: str) -> dict[str, str]:
    """Value of a Telerik RadComboBox: its ``ClientState`` carries the chosen text."""
    state = {
        "logEntries": [],
        "value": "",
        "text": text,
        "enabled": True,
        "checkedIndices": [],
        "checkedItemsTextOverflows": False,
    }
    return {client_state_name: json.dumps(state)}
