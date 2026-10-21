"""Validate paired reports without translating or changing forecast data."""
from __future__ import annotations

from datetime import date
import re

from markdown_it import MarkdownIt


BILINGUAL_FROM = date(2026, 10, 22)
REPORT_NAME = re.compile(r"\d{4}-\d{2}-\d{2}-\d{4}\.md")
TRANSLATION_NAME = re.compile(r"\d{4}-\d{2}-\d{2}-\d{4}\.en\.md")
NUMBER = re.compile(r"[+−-]?\d+(?:[.,]\d+)?")
CONFIDENCE = {
    "nízká": "low", "střední až nižší": "medium-low", "střední": "medium",
    "střední až vyšší": "medium-high", "vysoká": "high",
}


def english_path(path):
    return path.with_name(path.stem + ".en.md")


def numbers(text):
    # A range dash is a separator, not a negative sign. Preserve signed deltas.
    return [float(n.replace(",", ".").replace("−", "-"))
            for n in NUMBER.findall(text.replace("–", " ").replace("—", " "))]


def report_parts(text):
    tokens = MarkdownIt("commonmark", {"html": False}).enable("table").parse(text)
    tables, headings, sources = [], [], set()
    table = row = None
    for token in tokens:
        if token.type == "heading_open":
            headings.append(token.tag)
        elif token.type == "table_open":
            table = []
        elif token.type == "tr_open":
            row = []
        elif token.type == "tr_close":
            table.append(row)
            row = None
        elif token.type == "table_close":
            tables.append(table)
            table = None
        elif token.type == "inline" and row is not None:
            row.append(token.content)
        for child in token.children or []:
            if child.type == "link_open":
                href = child.attrGet("href") or ""
                if href.startswith(("https://", "http://")):
                    sources.add(href)
    return tables, headings, sources


def validate_pair(czech, english, state=None):
    cs, en = czech.read_text(encoding="utf-8"), english.read_text(encoding="utf-8")
    cs_tables, cs_headings, cs_sources = report_parts(cs)
    en_tables, en_headings, en_sources = report_parts(en)
    label = czech.name
    if cs_sources != en_sources:
        raise ValueError(f"Translation source links differ: {label}")
    if cs_headings != en_headings or len(cs_headings) < 2:
        raise ValueError(f"Translation section structure differs: {label}")
    if not cs_tables or len(cs_tables) != len(en_tables):
        raise ValueError(f"Translation tables missing or mismatched: {label}")
    # Same row/column order, including WDPI tables; only prose is translated.
    for left, right in zip(cs_tables, en_tables):
        if len(left) != len(right):
            raise ValueError(f"Translation table rows differ: {label}")
        for a, b in zip(left[1:], right[1:]):
            if len(a) != len(b) or [numbers(x) for x in a[1:]] != [numbers(x) for x in b[1:]]:
                raise ValueError(f"Translation table numbers differ: {label}")
    for pattern in [r"\*\*(?:Celkově|Overall):\*\*\s*(GREEN|YELLOW|ORANGE|RED)",
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}"]:
        a, b = re.search(pattern, cs), re.search(pattern, en)
        if not a or not b or (a.groups() or (a.group(),)) != (b.groups() or (b.group(),)):
            raise ValueError(f"Translation level or assessment timestamp differs: {label}")
    if not re.search(r"\*\*One-line judgment:\*\*\s*\S", en):
        raise ValueError(f"English report needs One-line judgment: {label}")
    for a, b in zip(cs_tables[0][1:], en_tables[0][1:]):
        if len(a) != 7 or CONFIDENCE.get(a[6].strip(), a[6].strip()) != b[6].strip():
            raise ValueError(f"Translation dashboard confidence or columns differ: {label}")
    if state is None:
        return
    for text in (cs, en):
        first_time = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", text)
        if first_time.group() != state["assessment_time"] or state["forecast_window_end"] not in text:
            raise ValueError(f"Report must include exact assessment timestamp and horizon: {label}")
    rows = cs_tables[0][1:]
    active = [h for h in state["hypotheses"].values() if h.get("status", "active") == "active"]
    if len(rows) != len(active):
        raise ValueError(f"Report dashboard must contain every active hypothesis in state order: {label}")
    for row, h in zip(rows, active):
        expected = [[round(h["prior"] * 100, 8)] if h.get("prior") is not None else [],
                    [round(h["p"] * 100, 8)],
                    [h["delta_pp"]] if h.get("delta_pp") is not None else [],
                    [round(x * 100, 8) for x in h["range"]]]
        if row[1].strip() != h["horizon"] or [numbers(x) for x in row[2:6]] != expected:
            raise ValueError(f"Report dashboard differs from state: {label}")
        if CONFIDENCE.get(row[6].strip(), row[6].strip()) != h["confidence"]:
            raise ValueError(f"Report dashboard confidence differs from state: {label}")
    for text in (cs, en):
        score = re.search(r"\*\*WDPI:\s*(\d+)\s*/\s*100", text)
        level = re.search(r"\*\*(?:Celkově|Overall):\*\*\s*(GREEN|YELLOW|ORANGE|RED)", text)
        if not score or int(score.group(1)) != state["wdpi"]["total"] or level.group(1) != state["overall_level"]:
            raise ValueError(f"Report WDPI or warning level differs from state: {label}")


def validate_translations(reports, state, read_json):
    canonical = {p.name for p in reports}
    for path in reports[0].parent.glob("*.en.md"):
        if not TRANSLATION_NAME.fullmatch(path.name) or path.name.replace(".en.md", ".md") not in canonical:
            raise ValueError(f"Orphan or invalid report translation: {path.name}")
    for path in reports:
        translation = english_path(path)
        required = date.fromisoformat(path.name[:10]) >= BILINGUAL_FROM
        if required and not translation.is_file():
            raise ValueError(f"English report required from {BILINGUAL_FROM}: {path.name}")
        if translation.is_file():
            snapshot = path.parent.parent / "snapshots" / (path.stem + ".json")
            prior = state if path.name == reports[0].name else read_json(snapshot) if snapshot.exists() else None
            validate_pair(path, translation, prior)
