"""Geographic annotations and a presentation-only view of the immutable ledger."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

PRAGUE = ZoneInfo('Europe/Prague')
COUNTRIES = {
    'ALB': 'Albánie', 'AUT': 'Rakousko', 'BEL': 'Belgie', 'CAN': 'Kanada',
    'HRV': 'Chorvatsko', 'CYP': 'Kypr', 'GRC': 'Řecko', 'HUN': 'Maďarsko',
    'ISL': 'Island', 'IRL': 'Irsko', 'LUX': 'Lucembursko', 'MLT': 'Malta',
    'MNE': 'Černá Hora', 'NLD': 'Nizozemsko', 'MKD': 'Severní Makedonie',
    'PRT': 'Portugalsko', 'SVK': 'Slovensko', 'SVN': 'Slovinsko', 'ESP': 'Španělsko',
    'SWE': 'Švédsko', 'TUR': 'Turecko',
    'BLR': 'Bělorusko', 'BGR': 'Bulharsko', 'CZE': 'Česko', 'DNK': 'Dánsko',
    'EST': 'Estonsko', 'FIN': 'Finsko', 'FRA': 'Francie', 'GEO': 'Gruzie',
    'IRN': 'Írán', 'ITA': 'Itálie', 'JPN': 'Japonsko', 'KOR': 'Korejská republika',
    'PRK': 'KLDR', 'LTU': 'Litva', 'LVA': 'Lotyšsko', 'DEU': 'Německo',
    'NOR': 'Norsko', 'POL': 'Polsko', 'ROU': 'Rumunsko', 'RUS': 'Rusko',
    'USA': 'Spojené státy', 'UKR': 'Ukrajina', 'GBR': 'Velká Británie',
}
REGIONS = {
    'NORTH_SEA': 'Severní moře', 'ARCTIC': 'Arktida',
    'BALTICS': 'Pobaltí', 'BALTIC_SEA': 'Baltské moře', 'BLACK_SEA': 'Černé moře',
    'EU': 'EU — nadregionální', 'EUROPE': 'Evropa — nadregionální',
    'NATO': 'NATO — nadregionální', 'GULF': 'Perský záliv', 'GLOBAL': 'Globální dosah',
}
AREAS = {**{key: {'label': label, 'kind': 'country'} for key, label in COUNTRIES.items()},
         **{key: {'label': label, 'kind': 'region'} for key, label in REGIONS.items()}}
TOPICS = {
    'baltic': ('Pobaltí a test NATO', {'baltic', 'baltic_limited_test', 'baltic_test', 'nato_baltic', 'limited_nato_test', 'nato_test', 'nato', 'nato_war', 'larger_nato_attack', 'larger_conventional_nato_attack', 'larger_conventional_attack', 'nato_readiness'}),
    'hybrid': ('Hybridní operace', {'hybrid', 'hybrid_eu', 'eu_hybrid', 'hybrid_proxy_eu', 'sabotage', 'sabotage_eu', 'physical_sabotage', 'physical_sabotage_eu', 'eu_physical_sabotage', 'cyber'}),
    'ukraine': ('Ukrajina', {'ukraine', 'ukraine_conventional', 'diplomacy', 'ukraine_support', 'ukraine_air_defence'}),
    'mobilization': ('Mobilizace', {'mobilization'}),
    'belarus': ('Bělorusko', {'belarus'}),
    'pressure': ('Tlak na Západ', {'wdpi', 'western_decision_pressure', 'western_pressure', 'western_response', 'russian_retaliation_opportunity'}),
    'nuclear': ('Jaderné zbraně a bezpečnost', {'nuclear', 'nuclear_safety', 'nuclear_posture', 'nuclear_signalling', 'znpp_nuclear_safety'}),
    'czechia': ('Česko', {'czechia'}),
    'context': ('Manipulace kontextem', {'context_manipulation', 'influence', 'context_integrity', 'data_quality', 'narrative'}),
}
STATUSES = {'confirmed': 'Potvrzeno', 'reported': 'Reportováno',
            'unverified_claim': 'Neověřené tvrzení', 'analytical_inference': 'Analytický závěr',
            'unknown': 'Neurčeno / oprava'}
DIRECTIONS = {'up': 'Pro eskalaci', 'down': 'Proti eskalaci',
              'neutral': 'Bez směrového dopadu', 'unknown': 'Směr neurčen'}


def geography(path: Path, evidence: list[dict]) -> dict:
    """Missing new annotations remain explicitly unknown; invalid ones fail validation."""
    if not path.is_file():
        return {'schema_version': 1, 'entries': {}, 'method': 'missing'}
    content = json.loads(path.read_text(encoding='utf-8'))
    if content.get('schema_version') != 1 or not isinstance(content.get('entries'), dict):
        raise ValueError('Invalid geography schema')
    ids = {item['id'] for item in evidence}
    if content['entries'].keys() - ids:
        raise ValueError('Geography references unknown evidence IDs')
    for identifier, annotation in content['entries'].items():
        areas = annotation.get('areas') if isinstance(annotation, dict) else None
        if not isinstance(areas, list) or any(not isinstance(area, str) or area not in AREAS for area in areas):
            raise ValueError(f'Unknown geographic area or invalid annotation: {identifier}')
        if len(set(areas)) != len(areas):
            raise ValueError(f'Duplicate geographic area: {identifier}')
        if not areas and not annotation.get('note'):
            raise ValueError(f'Unknown geography needs an explanatory note: {identifier}')
        if 'note' in annotation and not isinstance(annotation['note'], str):
            raise ValueError(f'Invalid geography note: {identifier}')
        if 'title' in annotation and (not isinstance(annotation['title'], str) or not annotation['title'].strip() or len(annotation['title']) > 220):
            raise ValueError(f'Invalid geography title: {identifier}')
    return content


def temporal(raw) -> dict:
    """Parse explicit ISO dates/intervals, never dates embedded in uncertain prose."""
    result = {'start': None, 'end': None, 'precision': 'unknown', 'planned': False,
              'raw': raw if isinstance(raw, str) else None}
    if not isinstance(raw, str) or not raw.strip():
        return result
    value = raw.strip()
    if value.startswith('planned_'):
        result['planned'] = True
        value = value[len('planned_'):]
    if 'disputed' in value:
        return result
    # Parenthetical provenance notes do not change the leading timestamp.
    value = re.sub(r'\s+\([^\n]*\)$', '', value)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}_morning', value):
        value = value.removesuffix('_morning')

    def endpoint(part):
        if re.fullmatch(r'\d{4}', part):
            year = int(part)
            return date(year, 1, 1), date(year, 12, 31), 'year'
        if re.fullmatch(r'\d{4}-\d{2}', part):
            year, month = map(int, part.split('-'))
            return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), 'month'
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', part):
            day = date.fromisoformat(part)
            return day, day, 'day'
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})', part):
            day = datetime.fromisoformat(part.replace('Z', '+00:00')).astimezone(PRAGUE).date()
            return day, day, 'day'
        raise ValueError('No explicit unambiguous date')

    try:
        parts = value.split('/')
        if len(parts) not in (1, 2):
            return result
        first, last = endpoint(parts[0]), endpoint(parts[-1])
        if last[1] < first[0]:
            return result
        result.update(start=first[0].isoformat(), end=last[1].isoformat(),
                      precision='year' if 'year' in (first[2], last[2]) else 'month' if 'month' in (first[2], last[2]) else 'day')
    except (ValueError, OverflowError):
        pass
    return result


def safe_url(value) -> str | None:
    if isinstance(value, str):
        try:
            parts = urlsplit(value)
            if parts.scheme in {'http', 'https'} and parts.netloc and not any(ord(c) < 32 for c in value):
                return value
        except ValueError:
            pass
    return None


def text(value) -> str:
    if value is None:
        return ''
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def payload(state: dict, evidence: list[dict], annotations: dict, monitoring: dict | None = None) -> dict:
    records = []
    for item in evidence:
        annotation = annotations['entries'].get(item['id'], {'areas': [], 'note': 'Geografie tohoto záznamu dosud nebyla anotována.'})
        domains = item.get('domain') or []
        if isinstance(domains, str):
            domains = [domains]
        status = text(item.get('status')).replace(' ', '_')
        if status not in STATUSES:
            status = 'unknown'
        direction = item.get('direction') if item.get('direction') in DIRECTIONS else 'unknown'
        scope = item.get('status_scope') or item.get('confirmed_scope') or item.get('confirmation_scope')
        source_urls = []
        for field in ('source_url', 'source_urls', 'corroboration_urls', 'supporting_urls'):
            values = item.get(field, [])
            if isinstance(values, str):
                values = [values]
            if isinstance(values, list):
                for value in values:
                    url = safe_url(value)
                    if url and url not in source_urls:
                        source_urls.append(url)
        summary = text(item.get('summary'))
        title = annotation.get('title') or (summary if len(summary) <= 130 else summary[:127].rsplit(' ', 1)[0] + '…')
        records.append({
            'id': item['id'], 'title': title, 'summary': summary,
            'source': text(item.get('source')), 'source_url': safe_url(item.get('source_url')),
            'source_urls': source_urls, 'status': status, 'status_raw': item.get('status'),
            'status_scope': text(scope), 'direction': direction, 'domains': domains,
            'topics': [key for key, (_, tags) in TOPICS.items() if set(domains) & tags],
            'signal_type': item.get('signal_type') or [],
            'alternative_explanation': text(item.get('alternative_explanation')),
            'independence_note': text(item.get('independence_note') or item.get('provenance_note')),
            'independent_source_line': text(item.get('independent_source_line')),
            'provenance_root': text(item.get('provenance_root')),
            'record_type': text(item.get('record_type')),
            'intake_type': item.get('intake_type'),
            'forecast_integration': item.get('forecast_integration'),
            'event_links': (monitoring or {}).get('evidence_links', {}).get(item['id'], []),
            'areas': annotation['areas'], 'geography_note': annotation.get('note', ''),
            'times': {key: temporal(item.get(field)) for key, field in (
                ('event', 'event_time'), ('publication', 'publication_time'), ('discovery', 'discovery_time'))},
        })
    cutoff = datetime.fromisoformat(state['assessment_time']).astimezone(PRAGUE).date()
    dates = [value for record in records for time in record['times'].values()
             for value in (time['start'], time['end']) if value]
    return {'schema_version': 2, 'assessment_time': state['assessment_time'],
            'monitoring': monitoring or {},
            'last_report': 'reports/' + Path(state['last_report']).stem + '.html',
            'total': len(records), 'areas': AREAS,
            'topics': {key: label for key, (label, _) in TOPICS.items()},
            'statuses': STATUSES, 'directions': DIRECTIONS,
            'default_from': (cutoff - timedelta(days=6)).isoformat(), 'default_to': cutoff.isoformat(),
            'minimum_date': min(dates + [cutoff.isoformat()]), 'maximum_date': max(dates + [cutoff.isoformat()]),
            'geography_reviewed_at': annotations.get('reviewed_at'),
            'unannotated_count': sum(item['id'] not in annotations['entries'] for item in evidence),
            'records': records}


def content(data: dict, cutoff_label: str, data_version: str = '') -> str:
    country_options = ''.join(f'<option value="{key}">{escape(label)}</option>' for key, label in sorted(COUNTRIES.items(), key=lambda pair: pair[1]))
    region_options = ''.join(f'<option value="{key}">{escape(label)}</option>' for key, label in REGIONS.items())
    topic_options = ''.join(f'<option value="{key}">{escape(label)}</option>' for key, label in data['topics'].items())
    status_options = ''.join(f'<option value="{key}">{escape(label)}</option>' for key, label in STATUSES.items())
    direction_options = ''.join(f'<option value="{key}">{escape(label)}</option>' for key, label in DIRECTIONS.items())
    recent = sorted(data['records'], key=lambda record: record['times']['discovery']['start'] or '', reverse=True)[:20]
    fallback = ''.join(f'<li><p><strong>{escape(record["title"])}</strong></p><p>{escape(record["summary"])}</p><p>{escape(record["source"])}' +
                       (f' · <a href="{escape(record["source_url"], quote=True)}" rel="noopener noreferrer">Zdroj ↗</a>' if record['source_url'] else '') + '</p></li>' for record in recent)
    return f'''<div class="signals-intro"><div><p class="eyebrow">Mapa a signály</p><h1>Mapa událostí a podkladů</h1><p class="meta">Úplná uložená evidence · {data['total']} záznamů · <a href="coverage.html">Rozsah kontrol a mezery →</a></p></div>
<p class="signals-cutoff">Uzávěrka rešerše<br><time datetime="{escape(data['assessment_time'])}">{escape(cutoff_label)}</time><br><a href="{escape(data['last_report'])}">Aktuální hodnocení →</a></p></div>
<p class="freshness" data-assessment-time="{escape(data['assessment_time'])}" hidden></p>
<div id="signals-app" class="signals-app" data-signals-source="data/signals.json?v={escape(data_version, quote=True)}" data-signals-map="assets/world-110m.geojson">
<p class="signals-loading" role="status">Načítání mapy a evidence…</p>
<div class="signals-controls" hidden>
<fieldset class="signals-basis signals-mode"><legend>Co mapa zobrazuje</legend><div class="signals-segment"><button type="button" data-mode="evidence" aria-pressed="true">Evidence</button><button type="button" data-mode="coverage" aria-pressed="false">Pokrytí zdrojů</button></div></fieldset>
<div class="signals-filters">
<label>Oblast<select name="area"><option value="all">Všechny oblasti</option><option value="baltics_all">Pobaltí společně</option><option value="unknown">Neurčená geografie</option><optgroup label="Země">{country_options}</optgroup><optgroup label="Regionální dosah">{region_options}</optgroup></select></label>
<label>Téma<select name="topic"><option value="all">Všechna témata</option>{topic_options}</select></label>
<label>Doložení<select name="status"><option value="all">Všechny stupně</option>{status_options}</select></label>
<label>Směr signálu<select name="direction"><option value="all">Všechny směry</option>{direction_options}</select></label>
</div>
<div class="signals-time-controls">
<label>Od<input type="date" name="from" value="{data['default_from']}" min="{data['minimum_date']}" max="{data['maximum_date']}"></label>
<label>Do<input type="date" name="to" value="{data['default_to']}" min="{data['minimum_date']}" max="{data['maximum_date']}"></label>
<fieldset class="signals-basis"><legend>Časový údaj</legend><div class="signals-segment"><button type="button" data-basis="publication" aria-pressed="true">Zveřejnění</button><button type="button" data-basis="event" aria-pressed="false">Událost / plán</button><button type="button" data-basis="discovery" aria-pressed="false">Zařazení do monitoru</button></div></fieldset>
<button type="button" class="signals-reset" data-reset>Zrušit filtry</button>
</div>
<label class="signals-undated"><input type="checkbox" name="undated"> Zahrnout záznamy bez určeného data <span data-undated-count></span></label>
</div>
<p class="signals-resultbar" aria-live="polite"><span data-results></span><span data-count-note>Počet záznamů ≠ počet útoků ani nezávislých potvrzení.</span></p>
<div class="signals-main" hidden>
<section class="signals-map-panel" aria-labelledby="signals-map-title"><div class="signals-panel-heading"><h2 id="signals-map-title">Územní vztah evidence</h2><div class="signals-segment" aria-label="Rozsah mapy"><button type="button" data-view="europe" aria-pressed="true">Evropa</button><button type="button" data-view="world" aria-pressed="false">Svět</button></div></div>
<svg class="signals-map" role="group" aria-label="Mapa přiřazení evidence k zemím"></svg>
<div class="coverage-legend" data-coverage-legend hidden><span class="coverage-state checked">Zkontrolováno v plánu</span><span class="coverage-state partial">Částečné</span><span class="coverage-state unavailable">Nedostupné</span><span class="coverage-state stale">Zastaralé</span><span class="coverage-state not_checked">Bez kontroly</span></div>
<p class="signals-map-summary" data-map-summary></p><p class="signals-map-note" data-map-note>Přiřazení k zemi neoznačuje přesné místo incidentu ani jeho původce. Jeden záznam může zahrnovat více zemí.</p></section>
<aside class="signals-detail" aria-label="Detail vybraného záznamu" data-detail></aside>
<section class="signals-timeline-panel" aria-labelledby="signals-time-title"><div class="signals-panel-heading"><h2 id="signals-time-title">Časová osa zveřejnění</h2><span class="meta" data-time-unit></span></div><svg class="signals-timeline" role="img" aria-label="Počty záznamů v čase podle směru signálu"></svg>
<div class="signals-legend"><span><i class="signals-swatch" data-direction="up"></i>Pro eskalaci</span><span><i class="signals-swatch" data-direction="down"></i>Proti eskalaci</span><span><i class="signals-swatch" data-direction="neutral"></i>Bez směrového dopadu</span><span><i class="signals-swatch" data-direction="unknown"></i>Směr neurčen</span></div><p class="signals-time-note" data-time-note></p></section>
<section class="signals-events" aria-labelledby="signals-list-title"><div class="signals-panel-heading"><h2 id="signals-list-title">Záznamy evidence</h2><span class="meta" data-order></span></div><div class="signals-event-list" data-event-list></div>
<nav class="signals-pagination" aria-label="Stránky evidence"><button type="button" data-previous>← Předchozí</button><span data-page></span><button type="button" data-next>Další →</button></nav></section>
</div></div>
<noscript><p class="note">Mapa a filtry vyžadují JavaScript. Níže je textový přehled; úplnou evidenci lze stáhnout.</p></noscript>
<details class="signals-fallback"><summary>Textový přehled posledních 20 zařazených záznamů</summary><ol>{fallback}</ol></details>
<div class="signals-data-links"><p><a href="data/evidence.jsonl">Úplná evidence JSONL</a> · <a href="data/geography.json">Geografické anotace JSON</a> · <a href="methodology.html">Metodika mapy</a></p><p>Mapový podklad: <a href="https://www.naturalearthdata.com/">Natural Earth</a> / <a href="https://github.com/d3-maps/atlas">d3-maps atlas</a>. Hranice jsou orientační.</p></div>'''
