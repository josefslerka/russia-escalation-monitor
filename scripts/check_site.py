#!/usr/bin/env python3
"""Check generated local links, source data fidelity and archive completeness."""
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from build_site import ROOT, DATA, validate, public_text
from signals import geography, payload as signals_payload
from bilingual import english_path
import monitoring


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.lang = None
        self.anchors = []
        self.alternates = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.lang = attrs.get("lang")
        if tag == "a":
            self.anchors.append(attrs)
        if tag == "link" and attrs.get("rel") == "alternate":
            self.alternates[attrs.get("hreflang")] = attrs.get("href")
        self.ids.add(attrs.get("id", ""))
        for attribute in ("href", "src"):
            if attrs.get(attribute):
                self.links.append(attrs[attribute])


def check():
    state, evidence, reports = validate()
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
    signals = json.loads((site / "data/signals.json").read_text())
    annotations = geography(ROOT / "russia-escalation/geography.json", evidence)
    source_data = ROOT / 'russia-escalation'
    bundle = monitoring.load(source_data)
    monitor_data = monitoring.payload(bundle, evidence, state)
    if signals != json.loads(public_text(json.dumps(signals_payload(state, evidence, annotations, monitor_data), ensure_ascii=False))):
        problems.append("Map data differ from the complete ledger and geographic annotations")
    if json.loads((site / "data/geography.json").read_text()) != annotations:
        problems.append("Published geography differs from source annotations")
    if len(signals["records"]) != len(evidence) or {record["id"] for record in signals["records"]} != {record["id"] for record in evidence}:
        problems.append("Map lost or duplicated evidence records")
    if (site / "signals.html").resolve() not in parsed:
        problems.append("Map and signals page is missing")
    for name in monitoring.FILES:
        if (site / 'data' / name).read_text() != public_text((source_data / name).read_text()):
            problems.append(f'Monitoring source differs: {name}')
    for name, expected in [('monitoring.json', monitor_data), ('evaluation.json', monitoring.evaluation(bundle))]:
        if json.loads((site / 'data' / name).read_text()) != json.loads(public_text(json.dumps(expected, ensure_ascii=False))):
            problems.append(f'Derived monitoring data differ: {name}')
    for name in ('coverage.html', 'quality.html', 'society.html'):
        if (site / name).resolve() not in parsed:
            problems.append(f'Missing monitoring page: {name}')
    index = json.loads((site / "data/reports.json").read_text())
    if {r["id"] for r in index} != {p.stem for p in reports}:
        problems.append("Archive index does not match the report history")
    for path in reports:
        versions = {"cs": path}
        if english_path(path).is_file():
            versions["en"] = english_path(path)
        entry = next((r for r in index if r["id"] == path.stem), {})
        if set(entry.get("languages", {})) != set(versions):
            problems.append(f"Incorrect language availability: {path.name}")
        for lang, source in versions.items():
            html = site / "reports" / (source.stem + ".html")
            parser = parsed.get(html.resolve())
            if parser is None or parser.lang != lang:
                problems.append(f"Missing report or incorrect HTML language: {source.name}")
                continue
            download = site / "reports" / source.name
            if not download.is_file() or download.read_text() != public_text(source.read_text()):
                problems.append(f"Markdown download differs from its source: {source.name}")
            if len(versions) == 2:
                expected = {code: version.stem + ".html" for code, version in versions.items()}
                if parser.alternates != expected:
                    problems.append(f"Missing language alternates: {source.name}")
                for code, href in expected.items():
                    links = [a for a in parser.anchors if a.get("href") == href and a.get("hreflang") == code and a.get("lang") == code]
                    if len(links) != 1 or (links[0].get("aria-current") == "page") != (code == lang):
                        problems.append(f"Invalid language switch: {source.name} → {code}")
    if problems:
        raise SystemExit("\n".join(problems))
    print(f"Checked {len(parsed)} HTML pages: links, language switches, archive and probability fidelity OK")


if __name__ == "__main__":
    check()
