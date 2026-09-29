#!/usr/bin/env python3
"""Check generated local links, source data fidelity and archive completeness."""
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from build_site import ROOT, DATA, validate


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.ids.add(attrs.get("id", ""))
        for attribute in ("href", "src"):
            if attrs.get(attribute):
                self.links.append(attrs[attribute])


def check():
    state, _, reports = validate()
    site = ROOT / "_site"
    problems = []
    parsed = {}
    for path in site.rglob("*.html"):
        parser = Links()
        parser.feed(path.read_text())
        parsed[path.resolve()] = parser
    for path, parser in parsed.items():
        for link in parser.links:
            parts = urlsplit(link)
            if parts.scheme or parts.netloc:
                continue
            target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if not target.is_relative_to(site.resolve()) or not target.exists():
                problems.append(f"{path.name}: missing local link {link}")
            elif parts.fragment and target in parsed and unquote(parts.fragment) not in parsed[target].ids:
                problems.append(f"{path.name}: missing anchor {link}")
    public_state = json.loads((site / "data/state.json").read_text())
    if public_state["hypotheses"] != state["hypotheses"]:
        problems.append("Published probabilities differ from state.json")
    index = json.loads((site / "data/reports.json").read_text())
    if {r["id"] for r in index} != {p.stem for p in reports}:
        problems.append("Archive index does not match the report history")
    for path in reports:
        if not (site / "reports" / (path.stem + ".html")).is_file():
            problems.append(f"Missing rendered report {path.name}")
    if problems:
        raise SystemExit("\n".join(problems))
    print(f"Checked {len(parsed)} HTML pages: local links, anchors, archive and probability fidelity OK")


if __name__ == "__main__":
    check()
