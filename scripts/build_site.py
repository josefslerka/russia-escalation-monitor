#!/usr/bin/env python3
"""Build a static, source-linked archive; never recalculate a forecast."""
from __future__ import annotations

import argparse
from datetime import date, datetime
from html import escape
import json
import math
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "russia-escalation"
REPORT_NAME = re.compile(r"\d{4}-\d{2}-\d{2}-\d{4}\.md")
PRAGUE = ZoneInfo("Europe/Prague")
REPOSITORY = "https://github.com/josefslerka/russia-escalation-monitor"
TRENDS = {"baseline": "výchozí stav", "flat": "beze změny", "up": "růst", "down": "pokles"}
CONFIDENCE = {"low": "nízká", "medium-low": "střední až nižší", "medium": "střední", "medium-high": "střední až vyšší", "high": "vysoká"}
LABELS = {
    "additional_qualitative_conventional_escalation_ukraine": "Další kvalitativní eskalace na Ukrajině",
    "significant_hybrid_proxy_operation_eu": "Významná hybridní / proxy operace v EU",
    "physical_sabotage_proxy_attempt_eu": "Fyzický sabotážní / proxy pokus v EU",
    "limited_deliberate_nato_test": "Omezený záměrný test NATO",
    "baltic_limited_test": "Omezený test v Pobaltí",
    "larger_conventional_attack_on_nato": "Větší konvenční útok na NATO",
    "open_russia_nato_war": "Otevřená válka Rusko–NATO",
    "significant_russian_mobilization": "Významná nucená ruská mobilizace",
    "belarus_direct_entry_into_war": "Přímý vstup Běloruska do války",
    "nuclear_posture_change": "Neobvyklá změna jaderné pohotovosti",
    "nuclear_demonstration": "Jaderná demonstrace",
    "nuclear_use": "Použití jaderné zbraně",
    "significant_russian_linked_hybrid_operation_czechia": "Významná hybridní / proxy operace v Česku",
}
SECTION_NAMES = {
    "Probability dashboard": "Pravděpodobnosti",
    "What changed": "Co se změnilo",
    "Strongest evidence for escalation": "Důkazy pro eskalaci",
    "Evidence against escalation": "Důkazy proti eskalaci",
    "Western Decision Pressure Index": "Tlak na západní rozhodování",
    "Russian Pressure Effort": "Ruské nátlakové úsilí",
    "Context-manipulation watch": "Manipulace kontextem",
    "24–72h watchlist": "Co sledovat dál",
    "Key unknowns": "Klíčové neznámé",
    "Bottom line": "Závěr",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def percent(value: float) -> str:
    return f"{value * 100:g}".replace(".", ",") + " %"


def day(value: str) -> str:
    dt = date.fromisoformat(value)
    return f"{dt.day}. {dt.month}. {dt.year}"


def timestamp(value: str) -> str:
    dt = datetime.fromisoformat(value).astimezone(PRAGUE)
    return f"{dt.day}. {dt.month}. {dt.year}, {dt:%H:%M} {dt.tzname()}"


def public_text(text: str) -> str:
    # Historical reports used clickable local paths. Their web copies use relative links.
    # The archived author path differs from ROOT on GitHub's Linux runner.
    text = re.sub(
        r"/(?:Users|home)/[^<>\n\"']*?/\.?russia-escalation/reports/(\d{4}-\d{2}-\d{2}-\d{4}\.md)",
        r"\1", text,
    )
    for folder in ("russia-escalation", ".russia-escalation"):
        text = text.replace(f"{ROOT}/{folder}/reports/", "")
    return text.replace(str(ROOT), ".")


def validate():
    state = read_json(DATA / "state.json")
    cutoff = datetime.fromisoformat(state["assessment_time"])
    if cutoff.tzinfo is None:
        raise ValueError("assessment_time must include a time zone")
    report = DATA / state["last_report"]
    if report.parent.resolve() != (DATA / "reports").resolve() or not REPORT_NAME.fullmatch(report.name):
        raise ValueError("last_report must name a timestamped report inside reports/")
    if not report.is_file():
        raise ValueError("The report referenced by state.json does not exist")
    if cutoff.astimezone(PRAGUE).strftime("%Y-%m-%d-%H%M.md") != report.name:
        raise ValueError("Report filename and assessment_time disagree")
    if state["overall_level"] not in {"GREEN", "YELLOW", "ORANGE", "RED"}:
        raise ValueError("Unknown overall warning level")
    if state["overall_trend"] not in TRENDS:
        raise ValueError("Unknown overall trend")
    for key, hypothesis in state["hypotheses"].items():
        p, bounds = hypothesis["p"], hypothesis["range"]
        if not (0 <= bounds[0] <= p <= bounds[1] <= 1):
            raise ValueError(f"Invalid probability or uncertainty range: {key}")
        date.fromisoformat(hypothesis["horizon"])
    wdpi = state["wdpi"]
    inputs = [wdpi[k] for k in ("resource_dilution", "domestic_pain", "self_deterrence")]
    if not all(0 <= number <= 100 for number in inputs):
        raise ValueError("WDPI input out of range")
    total = math.floor(sum(w * n for w, n in zip((.35, .35, .30), inputs)) + .5)
    if total != wdpi["total"] or not wdpi.get("formula"):
        raise ValueError("WDPI does not match its documented weighted formula")
    if state["rpe"].get("scored") and not all(state["rpe"].get(k) for k in ("components", "formula")):
        raise ValueError("Scored RPE requires components and a formula")
    evidence = [json.loads(line) for line in (DATA / "evidence.jsonl").read_text().splitlines() if line.strip()]
    identifiers = [item["id"] for item in evidence]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate evidence IDs")
    if not set(state.get("new_evidence_ids", [])).issubset(identifiers):
        raise ValueError("New evidence IDs are missing from evidence.jsonl")
    read_json(DATA / "watchlist.json")
    reports = sorted((DATA / "reports").glob("*.md"), reverse=True)
    if not reports or any(not REPORT_NAME.fullmatch(p.name) for p in reports):
        raise ValueError("Unexpected report filename")
    if reports[0] != report:
        raise ValueError("state.json does not point to the latest timestamped report")
    return state, evidence, reports


def badge(level: str) -> str:
    return f'<span class="badge {escape(level.lower())}">{escape(level)}</span>'


def page(title: str, content: str, prefix: str = ".", active: str = "") -> str:
    navigation = "".join(
        f'<a href="{prefix}/{path}"' + (' aria-current="page"' if active == label else "") + f'>{label}</a>'
        for path, label in (("index.html", "Přehled"), ("archive.html", "Archiv"), ("methodology.html", "Metodika"))
    )
    return f'''<!doctype html>
<html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · Monitor eskalace</title><meta name="description" content="Průběžná OSINT předpověď ruské eskalace. Pravděpodobnosti, podklady, nejistoty a archiv hodnocení.">
<meta name="color-scheme" content="light"><meta name="referrer" content="strict-origin-when-cross-origin">
<link rel="stylesheet" href="{prefix}/assets/site.css"><script src="{prefix}/assets/site.js" defer></script></head>
<body><a class="skip" href="#main">Přejít na obsah</a><header class="masthead"><div class="shell">
<a class="brand" href="{prefix}/index.html"><span aria-hidden="true">◉</span> MONITOR ESKALACE</a><nav class="nav" aria-label="Hlavní navigace">{navigation}</nav></div></header>
<main id="main" class="shell">{content}</main><footer class="footer"><div class="shell">
<p>Analytický projekt Josefa Šlerky s podporou AI. Pracuje s veřejnými zdroji a úsudkovými odhady; nejde o oficiální výstražný systém. Každé hodnocení platí k vlastní uzávěrce.</p>
<p><a href="{REPOSITORY}">GitHub a historie změn ↗</a><br><a href="{prefix}/data/state.json">Aktuální data JSON</a></p></div></footer></body></html>'''


def report_metadata(path: Path):
    text = public_text(path.read_text(encoding="utf-8"))
    level = re.search(r"\*\*(?:Celkově|Overall):\*\*\s*(GREEN|YELLOW|ORANGE|RED)", text)
    judgment = re.search(r"\*\*(?:Jednovětý závěr|One-line judgment):\*\*\s*(.+)", text)
    naive = datetime.strptime(path.stem, "%Y-%m-%d-%H%M")
    return {"id": path.stem, "time": naive.replace(tzinfo=PRAGUE).isoformat(),
            "level": level.group(1) if level else "", "judgment": judgment.group(1).strip() if judgment else "Otevřít úplné hodnocení", "text": text}


def render_markdown(source: str, known_reports: set[str], prefix: str = ".."):
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = md.parse(source)
    contents = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2":
            heading = tokens[i + 1].content
            identifier = f"section-{len(contents) + 1}"
            token.attrSet("id", identifier)
            contents.append((identifier, SECTION_NAMES.get(heading, heading)))
        for child in token.children or []:
            if child.type != "link_open":
                continue
            href = unquote(child.attrGet("href") or "")
            parsed = urlsplit(href)
            if parsed.scheme in ("https", "http"):
                child.attrSet("rel", "noopener noreferrer")
            elif Path(parsed.path).name in known_reports:
                child.attrSet("href", f"{prefix}/reports/{Path(parsed.path).stem}.html" + (f"#{parsed.fragment}" if parsed.fragment else ""))
            elif Path(parsed.path).name in ("state.json", "watchlist.json", "evidence.jsonl"):
                child.attrSet("href", f"{prefix}/data/{Path(parsed.path).name}")
            elif href.startswith("#"):
                pass
            else:
                child.attrs.pop("href", None)
                child.attrSet("title", "Odkaz není součástí veřejného archivu")
    html = md.renderer.render(tokens, md.options, {})
    html = html.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    toc = "".join(f'<a href="#{identifier}">{escape(label)}</a>' for identifier, label in contents)
    return html, toc


def archive_cards(reports):
    return '<div class="archive-list">' + "".join(
        f'<article class="archive-item" data-archive-item><time datetime="{r["time"]}">{day(r["time"][:10])}<br><small>{timestamp(r["time"]).split(", ")[1]}</small></time>'
        f'<a href="reports/{r["id"]}.html">{escape(r["judgment"])}</a>{badge(r["level"])}</article>'
        for r in reports
    ) + "</div>"


def dashboard(state, reports, evidence_count):
    rows = []
    for key, h in state["hypotheses"].items():
        if h.get("status", "active") != "active":
            continue
        label = LABELS.get(key.rsplit("_by_", 1)[0], key.replace("_", " "))
        delta = h.get("delta_pp")
        delta_text = "—" if delta is None else f"{delta:+g} p. b." if delta else "0 p. b."
        rows.append(f'''<tr><td class="scenario">{escape(label)}<details><summary>Definice a důvod odhadu</summary><p>{escape(h.get("event_definition", ""))}</p><p>{escape(h.get("change_basis", ""))}</p></details></td>
<td>{day(h["horizon"])}</td><td class="number">{percent(h['p'])}<span class="interval">{percent(h['range'][0])}–{percent(h['range'][1])}</span></td>
<td class="delta {escape(h['trend'])}">{escape(delta_text)}</td><td>{escape(CONFIDENCE.get(h['confidence'], h['confidence']))}</td></tr>''')
    wdpi = state["wdpi"]
    watch = "".join(f"<li>{escape(text)}</li>" for text in state.get("watch_24_72h", []))
    basis = escape(state["overall_level_basis"])
    latest = Path(state["last_report"]).stem
    return f'''<div class="hero"><div><p class="eyebrow">Hodnocení k <time datetime="{escape(state['assessment_time'])}">{timestamp(state['assessment_time'])}</time></p><h1>Rizika ruské eskalace</h1>
<p class="lede">{escape(state['one_line_judgment'])}</p><div class="actions"><a class="button" href="reports/{latest}.html">Číst aktuální zprávu →</a><a class="button secondary" href="archive.html">Procházet archiv</a></div></div>
<aside class="status-card" aria-label="Celkové hodnocení"><p class="status-label">Celkový stupeň varování</p>{badge(state['overall_level'])}<span class="trend">{escape(TRENDS[state['overall_trend']])}</span><p class="meta">Kvalitativní hodnocení. Význam stupně a podklady jsou vysvětleny ve zprávě.</p></aside></div>
<p class="freshness" data-assessment-time="{escape(state['assessment_time'])}" hidden></p>
<div class="data-strip"><span>Odhady do <strong>{day(state['forecast_horizon'])}</strong></span><span><strong>{len(reports)}</strong> zpráv v archivu · <strong>{evidence_count}</strong> záznamů evidence</span></div>
<section class="section"><div class="section-head"><h2>Aktuální pravděpodobnosti</h2><p>Odhad · pásmo nejistoty · změna vůči prioru</p></div>
<div class="table-wrap"><table><thead><tr><th scope="col">Událost</th><th scope="col">Do kdy</th><th scope="col">Odhad / pásmo</th><th scope="col">Změna</th><th scope="col">Důvěra</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p class="note">Odhady se vztahují k dalším událostem po uzávěrce. Události se mohou překrývat a jejich pravděpodobnosti se nesčítají do 100 %. Pásma vyjadřují úsudkovou nejistotu.</p></section>
<section class="section two-column"><div class="panel"><p class="eyebrow">WDPI</p><h2>Tlak na západní rozhodování</h2><p class="metric">{wdpi['total']}<small> / 100 · {escape(TRENDS[wdpi['trend']])}</small></p>
<div class="component"><span>Konkurence o zdroje · 35 %</span><strong>{wdpi['resource_dilution']}</strong></div><div class="component"><span>Domácí náklady · 35 %</span><strong>{wdpi['domestic_pain']}</strong></div><div class="component"><span>Sebeodstrašení · 30 %</span><strong>{wdpi['self_deterrence']}</strong></div>
<p class="formula">{escape(wdpi.get('derivation', wdpi['formula']))}</p><p>WDPI je index tlaku na rozhodování, nikoli pravděpodobnost války. Ruské nátlakové úsilí se hodnotí samostatně ve zprávě.</p></div>
<div class="panel"><p class="eyebrow">Celkové hodnocení</p><h2>Zdůvodnění stupně {escape(state['overall_level'])}</h2><p>{basis}</p><a href="reports/{latest}.html">Podklady pro i proti eskalaci →</a></div></section>
<section class="section"><h2>Co sledovat v dalších 24–72 hodinách</h2><div class="panel"><ul>{watch}</ul></div></section>
<section class="section"><div class="section-head"><h2>Poslední hodnocení</h2><a href="archive.html">Všech {len(reports)} zpráv →</a></div>{archive_cards(reports[:3])}</section>'''


def build():
    state, evidence, paths = validate()
    reports = [report_metadata(path) for path in paths]
    known_reports = {path.name for path in paths}
    files = {}
    files["index.html"] = page("Aktuální předpověď", dashboard(state, reports, len(evidence)), active="Přehled")
    files["archive.html"] = page("Archiv zpráv", f'''<div class="hero"><div><p class="eyebrow">{len(reports)} zpráv od {day(reports[-1]['time'][:10])}</p><h1>Archiv hodnocení</h1><p class="lede">Zprávy od nejnovější po nejstarší. Každá obsahuje tehdejší odhady, zdroje a zdůvodnění změn.</p></div></div>
<div class="archive-toolbar"><label for="archive-search" class="meta">Hledat v datu a shrnutí</label><input id="archive-search" data-archive-search type="search" placeholder="Například: mobilizace, 29. 9., NATO"><span class="meta" data-archive-count aria-live="polite">{len(reports)} zpráv</span></div>
<section class="section">{archive_cards(reports)}</section>''', active="Archiv")
    for i, report in enumerate(reports):
        html, toc = render_markdown(report["text"], known_reports)
        older = f'<a href="{reports[i + 1]["id"]}.html">← Starší hodnocení</a>' if i + 1 < len(reports) else "<span></span>"
        newer = f'<a href="{reports[i - 1]["id"]}.html">Novější hodnocení →</a>' if i > 0 else '<a href="../index.html">Aktuální přehled →</a>'
        notice = "Archivní hodnocení platné k uvedené uzávěrce. Zachovává tehdejší poznatky a metodiku; pozdější opravy a změny najdete v novějších zprávách. Starší souhrnná skóre bez reprodukovatelného modelu nepřebíráme do aktuálního přehledu." if i > 0 else "Aktuální uložené hodnocení. Datum uzávěrky označuje konec rešerše, ne okamžik otevření této stránky."
        contents = f'<div class="article-layout"><aside class="toc" aria-label="Obsah zprávy"><p class="eyebrow">Obsah zprávy</p>{toc}<a href="{report["id"]}.md">Stáhnout Markdown ↓</a></aside><article class="report"><div class="archive-notice">{notice}</div>{html}<nav class="report-nav" aria-label="Další zprávy">{older}{newer}</nav></article></div>'
        files[f'reports/{report["id"]}.html'] = page(timestamp(report["time"]), contents, "..", "Archiv")
        files[f'reports/{report["id"]}.md'] = report["text"]
    methodology, _ = render_markdown((ROOT / "site/methodology.md").read_text(), known_reports, ".")
    files["methodology.html"] = page("Metodika", f'<article class="method report">{methodology}</article>', active="Metodika")
    for name in ("state.json", "watchlist.json", "evidence.jsonl"):
        files[f"data/{name}"] = public_text((DATA / name).read_text())
    for snapshot in sorted((DATA / "snapshots").glob("*.json")):
        read_json(snapshot)
        files[f"data/snapshots/{snapshot.name}"] = public_text(snapshot.read_text())
    files["data/reports.json"] = json.dumps([{k: v for k, v in r.items() if k != "text"} for r in reports], ensure_ascii=False, indent=2) + "\n"
    files[".nojekyll"] = ""
    for asset in (ROOT / "site/assets").iterdir():
        if asset.is_file():
            files[f"assets/{asset.name}"] = asset.read_text()
    output = ROOT / "_site"
    for name, content in files.items():
        if re.search(r"/Users/|file://|/private/(?:tmp|var)/", content):
            raise ValueError(f"A local filesystem path would be published in {name}")
    for name, content in files.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(destination)
    print(f"Built {len(reports)} reports, {len(evidence)} evidence records, {len(files)} files in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate sources without generating files")
    options = parser.parse_args()
    if options.check:
        state, evidence, reports = validate()
        print(f"Valid: {state['assessment_time']}; {len(reports)} reports; {len(evidence)} evidence IDs")
    else:
        build()
