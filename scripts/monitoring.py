"""Auditable monitoring metadata. This module never changes a forecast or its history."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path

import forecasting
from signals import AREAS, TOPICS, STATUSES, safe_url, temporal

JSON_FILES = ('sources.json', 'events.json', 'indicators.json', 'metrics.json', forecasting.PROTOCOL)
LOG_FILES = ('coverage.jsonl', 'monitoring-runs.jsonl', 'case-reviews.jsonl',
             'indicator-observations.jsonl', 'metric-observations.jsonl',
             'wdpi-assessments.jsonl', 'forecast-register.jsonl', 'forecast-resolutions.jsonl', 'evidence-reviews.jsonl',
             forecasting.ROUNDS, forecasting.OUTCOMES)
FILES = JSON_FILES + LOG_FILES
DOMAINS = {'official_assessment': 'Oficiální hodnocení', 'incidents': 'Incidenty',
           'readiness': 'Připravenost', 'policy_effect': 'Politické a společenské účinky'}
OUTCOMES = {'relevant_found': 'Nalezen relevantní podklad', 'no_new_relevant': 'Bez nového podkladu v uvedeném rozsahu',
            'partial': 'Částečně zkontrolováno', 'unavailable': 'Zdroj nedostupný'}
STATES = {'checked': 'Zkontrolováno v plánu', 'partial': 'Částečné pokrytí',
          'unavailable': 'Nedostupné zdroje', 'not_checked': 'Bez strukturované kontroly', 'stale': 'Kontrola zastarala'}
ROLES = {'first_report', 'independent_corroboration', 'followup', 'attribution', 'refutation', 'correction', 'overlapping_claim'}
INVOLVEMENT = {'russian_caused', 'russian_amplified', 'russian_exploited', 'independent', 'unknown'}
ROLE_LABELS = {'first_report': 'První zpráva', 'independent_corroboration': 'Nezávislé potvrzení',
               'followup': 'Další vývoj', 'attribution': 'Atribuce', 'refutation': 'Vyvrácení',
               'correction': 'Oprava', 'overlapping_claim': 'Překryv tvrzení'}
STAGES = {'announced': 'Oznámeno', 'committed': 'Závazně přislíbeno', 'delivered': 'Dodáno',
          'paid': 'Zaplaceno', 'observed': 'Pozorováno', 'unknown': 'Neurčeno'}


def instant(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError(f'Timestamp needs timezone: {value}')
    return dt


def require(condition, message):
    if not condition:
        raise ValueError(message)


def index(items, label):
    result = {}
    for item in items:
        require(isinstance(item, dict) and isinstance(item.get('id'), str) and item['id'], f'Invalid {label} ID')
        require(item['id'] not in result, f'Duplicate {label} ID: {item["id"]}')
        result[item['id']] = item
    return result


def refs(values, allowed, label, empty=True):
    require(isinstance(values, list) and all(isinstance(v, str) for v in values), f'Invalid {label}')
    require(len(values) == len(set(values)) and set(values) <= set(allowed), f'Unknown or repeated {label}')
    require(empty or bool(values), f'Missing {label}')


def urls(values):
    require(isinstance(values, list) and bool(values) and all(safe_url(v) for v in values), 'Invalid/missing source URLs')


def load(data: Path):
    result = {}
    for name in JSON_FILES:
        result[name] = json.loads((data / name).read_text())
        require(result[name].get('schema_version') == 1, f'Unsupported schema: {name}')
    for name in LOG_FILES:
        result[name] = [json.loads(line) for line in (data / name).read_text().splitlines() if line.strip()]
        index(result[name], name)
    return result


def definition_hash(definition, criteria):
    return sha256(json.dumps([definition, criteria], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def completed_tasks(bundle, run_id, at):
    checks = {c['id']:c for c in bundle['coverage.jsonl'] if c['run_id'] == run_id and instant(c['checked_at']) <= at}
    completed = {c['task_id'] for c in checks.values() if c['outcome'] in {'relevant_found','no_new_relevant'}}
    for forecast in bundle[forecasting.ROUNDS]:
        if instant(forecast['issued_at']) <= at and set(forecast['check_ids']) & checks.keys():
            completed.add('forecast:issue:'+forecast['id'])
    for outcome in bundle[forecasting.OUTCOMES]:
        if instant(outcome['resolved_at']) <= at and set(outcome['check_ids']) & checks.keys():
            completed.add('forecast:resolve:'+outcome['forecast_id'])
    return completed


def validate(bundle, evidence, state):
    evidence_ids = {e['id'] for e in evidence}
    sources = index(bundle['sources.json']['sources'], 'source')
    countries = bundle['sources.json']['countries']
    for area, plan in countries.items():
        require(area in AREAS and AREAS[area]['kind'] == 'country', 'Invalid monitored country')
        refs(plan['source_ids'], sources, 'country sources', empty=False)
        require(0 <= plan['rotation_day'] <= 6 and plan['review_days'] > 0, 'Invalid country rotation')
    for source in sources.values():
        require(safe_url(source['url']) and source['name'], 'Invalid source URL/name')
        refs(source['areas'], AREAS, 'source areas', empty=False)
        refs(source['domains'], DOMAINS, 'source domains', empty=False)
        require(source['cadence_days'] in (1, 7, 30) and source['tier'] in range(1, 7), 'Invalid source cadence/tier')
    runs = index(bundle['monitoring-runs.jsonl'], 'run')
    for run in runs.values():
        require(instant(run['started_at']) <= instant(run['finished_at']), 'Reversed run interval')
        require(run['kind'] in {'daily', 'backfill', 'weekly', 'monthly'}, 'Invalid run kind')
        require(bool(run['expected_tasks']) and len(run['expected_tasks']) == len(set(run['expected_tasks'])), 'Invalid expected tasks')
    checks = index(bundle['coverage.jsonl'], 'coverage')
    for check in checks.values():
        refs(check['source_ids'], sources, 'checked sources', empty=False)
        refs(check['areas'], AREAS, 'checked areas', empty=False)
        refs(check['domains'], DOMAINS, 'checked domains', empty=False)
        refs(check['evidence_ids'], evidence_ids, 'checked evidence')
        urls(check['urls'])
        require(check['outcome'] in OUTCOMES, 'Invalid check outcome')
        require(check['scope_type'] in {'document_review', 'news_scan', 'country_audit', 'source_audit', 'forecast_audit'}, 'Invalid check scope')
        require(bool(check['scope']) and isinstance(check['limitations'], str), 'Check requires scope and limitations')
        require(check['run_id'] in runs, 'Unknown coverage run')
        run = runs[check['run_id']]
        require(check['task_id'] in run['expected_tasks'], 'Unexpected coverage task')
        checked = instant(check['checked_at'])
        require(instant(run['started_at']) <= checked <= instant(run['finished_at']), 'Check outside its run')
        start, end = temporal(check['period_start']), temporal(check['period_end'])
        require(start['start'] and end['end'] and start['start'] <= end['end'], 'Invalid coverage period')
        require(end['end'] <= checked.date().isoformat(), 'Coverage cannot include future research')
        if check['outcome'] == 'unavailable':
            require(not check['evidence_ids'], 'Unavailable fetch cannot supply evidence')
        if check['outcome'] == 'relevant_found':
            require(bool(check['evidence_ids']) or bool(check.get('observation_ids')), 'Relevant result needs evidence/observation')

    events = index(bundle['events.json']['events'], 'event')
    seen_links = set()
    for event in events.values():
        refs(event['areas'], AREAS, 'event areas', empty=False)
        require(event['kind'] in {'incident', 'assessment', 'policy', 'series'}, 'Invalid event kind')
        require(event['russian_involvement'] in INVOLVEMENT, 'Invalid Russian involvement')
        require(event['links'] and event['summary'] and event['attribution_basis'], 'Incomplete event')
        for link in event['links']:
            require(link['evidence_id'] in evidence_ids and link['role'] in ROLES, 'Invalid event evidence/role')
            require(link['line_id'] and link['claim'] and link['independence_basis'], 'Missing provenance reasoning')
            pair = (event['id'], link['evidence_id'])
            require(pair not in seen_links, 'Repeated event evidence link')
            seen_links.add(pair)
        if event.get('next_check_by'):
            instant(event['next_check_by'])
            require(event.get('next_action') and event.get('case_status') in {'open', 'monitoring', 'closed'}, 'Incomplete followup')
    latest = {}
    for review in bundle['case-reviews.jsonl']:
        require(review['event_id'] in events, 'Unknown case event')
        refs(review['check_ids'], checks, 'case checks', empty=False)
        require(review['outcome'] in OUTCOMES and review['case_status'] in {'open', 'monitoring', 'closed'}, 'Invalid case outcome')
        require(review['next_action'] and review['summary'], 'Incomplete case review')
        current = instant(review['checked_at'])
        event = events[review['event_id']]
        previous = latest.get(event['id'])
        original = previous['next_check_by'] if previous else event.get('next_check_by')
        require(original == review['scheduled_for'], 'Case review must preserve the preceding deadline')
        require(not previous or instant(previous['checked_at']) <= current, 'Case reviews out of order')
        require(instant(review['next_check_by']) > current, 'Case followup must be in future')
        require(all(instant(checks[c]['checked_at']) <= current for c in review['check_ids']), 'Case precedes source checks')
        failed = all(checks[c]['outcome'] == 'unavailable' for c in review['check_ids'])
        require(not failed or review['outcome'] == 'unavailable', 'Failed fetch cannot complete a case check')
        require(not (review['outcome'] in {'partial', 'unavailable'} and review['case_status'] == 'closed'), 'Incomplete check cannot close a case')
        latest[event['id']] = review

    indicators = index(bundle['indicators.json']['indicators'], 'indicator')
    for indicator in indicators.values():
        refs(indicator['source_ids'], sources, 'indicator sources', empty=False)
        require(indicator['expected_signature'] and indicator['alternative'] and indicator['baseline'], 'Incomplete indicator design')
        require(indicator['fresh_days'] > 0, 'Invalid indicator freshness')
    for observation in bundle['indicator-observations.jsonl']:
        require(observation['indicator_id'] in indicators, 'Unknown indicator')
        refs(observation['check_ids'], checks, 'indicator checks', empty=False)
        instant(observation['observed_at'])
        require(observation['result'] in {'present', 'absent', 'unknown'}, 'Invalid indicator observation')
        if observation['result'] == 'absent':
            require(observation.get('observability') == 'high' and observation.get('baseline_url') and safe_url(observation['baseline_url']), 'Absence requires observable signature and sourced baseline')
            require(all(checks[c]['outcome'] not in {'unavailable', 'partial'} for c in observation['check_ids']), 'Partial research is not negative evidence')
        require(observation['rationale'], 'Missing indicator rationale')
    metrics = index(bundle['metrics.json']['series'], 'metric')
    for metric in metrics.values():
        require(metric['unit'] and metric['definition'] and metric['method_version'], 'Incomplete metric')
        refs(metric['source_ids'], sources, 'metric sources', empty=False)
    observations = index(bundle['metric-observations.jsonl'], 'metric observation')
    for observation in observations.values():
        require(observation['series_id'] in metrics, 'Unknown metric series')
        metric = metrics[observation['series_id']]
        require(observation['method_version'] == metric['method_version'], 'Metric method mismatch; create a new series for a break')
        instant(observation['recorded_at'])
        require(temporal(observation['period'])['start'], 'Metric period must preserve known precision')
        urls(observation['source_urls'])
        require(observation['stage'] in {'announced', 'committed', 'delivered', 'paid', 'observed', 'unknown'}, 'Invalid metric stage')
        require(observation['russian_involvement'] in INVOLVEMENT and observation['causal_basis'], 'Metric needs causal qualification')
        value = observation['value']
        require(value is None or isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), 'Invalid metric value')
        if metric['unit'] == 'percent' and value is not None:
            require(0 <= value <= 100, 'Percentage out of range')
        if value is None:
            require(observation.get('missing_reason'), 'Missing value needs a reason, never zero-fill')
        if metric['kind'] == 'poll':
            require(all(observation.get(k) for k in ('question', 'sample_size', 'population', 'mode', 'fieldwork', 'comparability')), 'Poll requires design and fieldwork metadata')
    for check in checks.values():
        refs(check.get('observation_ids', []), observations, 'checked observations')
    rubric = bundle['metrics.json']['wdpi']
    require(rubric['weights'] == {'resource_dilution': .35, 'domestic_pain': .35, 'self_deterrence': .30}, 'WDPI weight change requires an explicit model migration')
    for score in bundle['wdpi-assessments.jsonl']:
        require(score['method_version'] == rubric['version'], 'Unknown WDPI method')
        instant(score['assessment_time'])
        require(set(score['components']) == set(rubric['weights']), 'WDPI cannot score missing components')
        for key, component in score['components'].items():
            require(str(component['score']) in rubric['anchors'][key], 'WDPI judgment must select a documented anchor')
            require(component['rationale'] and component['russian_involvement'] in INVOLVEMENT, 'WDPI rationale missing')
            refs(component['observation_ids'], observations, 'WDPI observations', empty=False)
        require(score['total'] == wdpi_total(score['components']), 'WDPI total does not match components')
    if state['wdpi'].get('method_version') == rubric['version']:
        scores = index(bundle['wdpi-assessments.jsonl'], 'WDPI assessment')
        require(state['wdpi'].get('assessment_id') in scores, 'New WDPI method requires an anchored assessment')
        score = scores[state['wdpi']['assessment_id']]
        require(score['assessment_time'] == state['assessment_time'], 'WDPI method switch requires a new dated assessment')
        require(all(state['wdpi'][k] == score['components'][k]['score'] for k in rubric['weights']) and state['wdpi']['total'] == score['total'], 'State WDPI differs from its anchored assessment')

    registrations = index(bundle['forecast-register.jsonl'], 'forecast registration')
    for forecast in registrations.values():
        require(forecast['definition_hash'] == definition_hash(forecast['definition'], forecast['resolution_criteria']), 'Frozen definition hash mismatch')
        start, end = instant(forecast['window_start']), instant(forecast['window_end'])
        require(start < end and 0 <= forecast['p'] <= 1, 'Invalid forecast window/probability')
        require(instant(forecast['forecast_time']) <= instant(forecast['registered_at']), 'Registration precedes forecast')
        require(forecast['cohort'] and forecast['exclusion_reason'] is not None, 'Missing evaluation cohort/qualification')
        if forecast['eligible']:
            require(instant(forecast['registered_at']) < end and not forecast['exclusion_reason'], 'Retrospective registration cannot be scored')
        require(Path(forecast['report']).name == forecast['report'] and forecast['report'].endswith('.md'), 'Unsafe registration report path')
    resolutions = index(bundle['forecast-resolutions.jsonl'], 'forecast resolution')
    last_resolution = {}
    for resolution in resolutions.values():
        require(resolution['forecast_id'] in registrations, 'Unknown resolved forecast')
        forecast = registrations[resolution['forecast_id']]
        resolved = instant(resolution['resolved_at'])
        require(resolved >= instant(forecast['registered_at']), 'Resolution before registration')
        require(resolution['outcome'] in {'yes', 'no', 'unknown'}, 'Invalid resolution outcome')
        refs(resolution['evidence_ids'], evidence_ids, 'resolution evidence')
        urls(resolution['source_urls'])
        require(resolution['rationale'], 'Resolution needs adjudication rationale')
        require(resolution.get('supersedes') == last_resolution.get(forecast['id']), 'Resolution corrections must name preceding adjudication')
        if resolution['outcome'] == 'yes':
            event = instant(resolution['event_time'])
            require(instant(forecast['window_start']) < event <= instant(forecast['window_end']) and event <= resolved, 'Resolved event outside forecast window')
            require(bool(resolution['evidence_ids']), 'Yes requires evidence')
        if resolution['outcome'] == 'no':
            require(resolved >= instant(forecast['window_end']) and resolution.get('coverage_basis'), 'No needs closed horizon and adequate observation coverage')
        last_resolution[forecast['id']] = resolution['id']
    for item in evidence:
        if item.get('intake_type') == 'retrospective_backfill':
            require(item.get('forecast_integration') in {'pending_review', 'reviewed_no_change', 'integrated'}, 'Backfill needs integration status')
            require(temporal(item.get('publication_time'))['start'], 'Backfill needs original publication time')
            instant(item['discovery_time'])
    for review in bundle['evidence-reviews.jsonl']:
        refs(review['evidence_ids'], evidence_ids, 'integration evidence', empty=False)
        require(review['decision'] in {'reviewed_no_change', 'integrated', 'excluded'}, 'Invalid integration decision')
        instant(review['reviewed_at'])
        require(review['rationale'] and review['report'], 'Integration requires a dated analytical report and rationale')
        require(Path(review['report']).name == review['report'] and review['report'].endswith('.md'), 'Unsafe integration report path')
    if instant(state['assessment_time']) > instant(bundle['sources.json']['created_at']):
        scope = state.get('research_scope', {})
        require(scope.get('monitoring_run_id') in runs, 'New assessment requires a structured monitoring run')
        run = runs[scope['monitoring_run_id']]
        require(instant(run['finished_at']) <= instant(state['assessment_time']), 'Assessment precedes its monitoring run')
        completed = completed_tasks(bundle, run['id'], instant(state['assessment_time']))
        status = 'complete' if set(run['expected_tasks']) <= completed else 'partial'
        require(scope.get('coverage_status') == status, 'Assessment coverage status must expose incomplete tasks')
    forecasting.validate(bundle, evidence)
    forecasting.validate_legacy_windows(bundle, state)
    return bundle


def validate_files(bundle, data):
    """Frozen values must come from an existing immutable assessment snapshot."""
    for forecast in bundle['forecast-register.jsonl']:
        report = data / 'reports' / forecast['report']
        require(report.is_file(), 'Registered forecast report is missing')
        snapshot = data / 'snapshots' / (report.stem + '.json')
        # During normal publication the just-completed state precedes its snapshot.
        current = json.loads((data / 'state.json').read_text())
        if snapshot.is_file():
            original = json.loads(snapshot.read_text())
        elif Path(current['last_report']).name == report.name:
            original = current
        else:
            require(not forecast['eligible'], 'Eligible forecast requires archived snapshot')
            continue
        hypothesis = original['hypotheses'].get(forecast['question'])
        require(hypothesis is not None, 'Registered question absent from original assessment')
        require(forecast['forecast_time'] == original['assessment_time'] and forecast['p'] == hypothesis['p'] and forecast['definition'] == hypothesis['event_definition'], 'Registered forecast differs from original assessment')
        for boundary in ('start', 'end'):
            key = 'forecast_window_' + boundary
            require(forecast['window_' + boundary] == hypothesis.get(key, original[key]), 'Registered window differs from original assessment')
    for review in bundle['evidence-reviews.jsonl']:
        require((data / 'reports' / review['report']).is_file(), 'Integration report does not exist')


def wdpi_total(components):
    # Integer arithmetic specifies half-up rounding at .5, consistently with the site.
    return (35 * components['resource_dilution']['score'] + 35 * components['domestic_pain']['score'] + 30 * components['self_deterrence']['score'] + 50) // 100


def evaluation(bundle):
    resolutions = {r['forecast_id']: r for r in bundle['forecast-resolutions.jsonl']}
    chosen = {}
    for forecast in sorted(bundle['forecast-register.jsonl'], key=lambda f: (f['forecast_time'], f['id'])):
        if forecast['eligible']:
            chosen.setdefault(forecast['cohort'], forecast['id'])
    rows, scores = [], []
    for forecast in bundle['forecast-register.jsonl']:
        resolution = resolutions.get(forecast['id'])
        scored = chosen.get(forecast['cohort']) == forecast['id'] and resolution and resolution['outcome'] in {'yes', 'no'}
        score = (forecast['p'] - (resolution['outcome'] == 'yes')) ** 2 if scored else None
        if score is not None:
            scores.append(score)
        rows.append({**forecast, 'resolution': resolution, 'brier': score,
                     'selected_for_cohort': chosen.get(forecast['cohort']) == forecast['id']})
    return {'rows': rows, 'scored_questions': len(scores), 'brier': sum(scores) / len(scores) if scores else None,
            'rule': 'První způsobilá registrace v každé kohortě otázka × verze definice × konec horizontu; přesné počáteční okno je zmrazené u registrace. Denní revize nejsou další vzorky. Překrývající se otázky nejsou nezávislé konflikty.'}


def due_tasks(bundle, watchlist, at):
    """Deterministic queue; creating a task is never counted as completing a check."""
    # An as-of queue must not be cleared by checks performed after that time.
    checks = [c for c in bundle['coverage.jsonl'] if instant(c['checked_at']) <= at]
    tasks = []
    for source in bundle['sources.json']['sources']:
        done = [c for c in checks if source['id'] in c['source_ids'] and c['scope_type'] == 'news_scan' and c['outcome'] in {'relevant_found', 'no_new_relevant'}]
        last = max((instant(c['checked_at']) for c in done), default=None)
        if last is None or at - last >= timedelta(days=source['cadence_days']):
            tasks.append({'id': 'source:' + source['id'], 'kind': 'source', 'url': source['url'], 'reason': 'never_checked' if last is None else 'due', 'priority': source['priority']})
    for area, plan in bundle['sources.json']['countries'].items():
        audits = [c for c in checks if area in c['areas'] and c['scope_type'] == 'country_audit' and c['outcome'] in {'relevant_found', 'no_new_relevant'}]
        last = max((instant(c['checked_at']) for c in audits), default=None)
        if at.weekday() == plan['rotation_day'] or last is not None and at - last >= timedelta(days=plan['review_days']):
            tasks.append({'id': 'country:' + area, 'kind': 'country_audit', 'priority': plan['priority']})
    monthly = [instant(c['checked_at']) for c in checks if c['scope_type'] == 'source_audit' and c['outcome'] in {'relevant_found', 'no_new_relevant'}]
    if not monthly or (at - max(monthly)).days >= 30:
        tasks.append({'id': 'monthly:coverage', 'kind': 'source_audit', 'priority': 1})
    reviews = {r['event_id']: r for r in bundle['case-reviews.jsonl'] if instant(r['checked_at']) <= at}
    for event in bundle['events.json']['events']:
        current = reviews.get(event['id'], event)
        if current.get('next_check_by') and current.get('case_status') != 'closed' and instant(current['next_check_by']) <= at:
            tasks.append({'id': 'case:' + event['id'], 'kind': 'case_review', 'scheduled_for': current['next_check_by'], 'priority': 0})
    for key, value in watchlist.items():
        if isinstance(value, dict) and value.get('next_check_by') and instant(value['next_check_by']) <= at:
            tasks.append({'id': 'watch:' + key, 'kind': 'legacy_watchlist', 'scheduled_for': value['next_check_by'], 'priority': 0})
    tasks.extend(forecasting.tasks(bundle, at))
    return sorted(tasks, key=lambda t: (t['priority'], t['id']))


def payload(bundle, evidence, state):
    checks = bundle['coverage.jsonl']
    times = [state['assessment_time']] + [c['checked_at'] for c in checks] + [r['finished_at'] for r in bundle['monitoring-runs.jsonl']]
    times += [forecasting.as_of(bundle, state)]
    as_of = max(times, key=instant)
    at = instant(as_of)
    countries = {}
    for area, plan in bundle['sources.json']['countries'].items():
        # A registry audit is not substantive research on every country it lists.
        attempts = sorted((c for c in checks if area in c['areas'] and c['scope_type'] not in {'source_audit', 'forecast_audit'}), key=lambda c: instant(c['checked_at']), reverse=True)
        successes = [c for c in attempts if c['outcome'] in {'relevant_found', 'no_new_relevant'}]
        recent = [c for c in successes if at - instant(c['checked_at']) <= timedelta(days=plan['review_days'])]
        recent_attempts = [c for c in attempts if at - instant(c['checked_at']) <= timedelta(days=plan['review_days'])]
        domains = set(d for c in recent for d in c['domains'])
        full = any(c['scope_type'] == 'country_audit' and c['outcome'] in {'relevant_found', 'no_new_relevant'} and set(c['domains']) == set(DOMAINS) for c in recent)
        status = ('not_checked' if not attempts else 'stale' if not recent_attempts else
                  'checked' if full else 'unavailable' if all(c['outcome'] == 'unavailable' for c in recent_attempts) else 'partial')
        if attempts and attempts[0]['outcome'] == 'unavailable' and status == 'checked':
            status = 'partial'
        countries[area] = {'label': AREAS[area]['label'], 'status': status, 'status_label': STATES[status],
                           'last_attempt': attempts[0]['checked_at'] if attempts else None,
                           'last_success': successes[0]['checked_at'] if successes else None,
                           'domains_checked': sorted(domains), 'domains_missing': sorted(set(DOMAINS) - domains),
                           'review_days': plan['review_days'], 'source_ids': plan['source_ids'],
                           'checks': attempts, 'priority': plan['priority']}
    links = defaultdict(list)
    for event in bundle['events.json']['events']:
        for link in event['links']:
            links[link['evidence_id']].append({**link, 'event_id': event['id'], 'event_title': event['title'], 'event_kind': event['kind']})
    groups = defaultdict(list)
    for e in evidence:
        if safe_url(e.get('source_url')):
            groups[e['source_url']].append(e['id'])
    # Same URL is only a review candidate. Dynamic feeds can carry unrelated events.
    candidates = [{'url': url, 'evidence_ids': ids} for url, ids in sorted(groups.items()) if len(ids) > 1 and any(i not in links for i in ids)]
    runs = []
    for run in bundle['monitoring-runs.jsonl']:
        completed = completed_tasks(bundle, run['id'], at)
        missing = sorted(set(run['expected_tasks']) - completed)
        runs.append({**run, 'status': 'partial' if missing else 'complete', 'incomplete_tasks': missing})
    reviewed = {i for r in bundle['evidence-reviews.jsonl'] for i in r['evidence_ids']}
    freshness = []
    for topic, (label, tags) in TOPICS.items():
        relevant = []
        for item in evidence:
            domains = item.get('domain') or []
            domains = [domains] if isinstance(domains, str) else domains
            published = temporal(item.get('publication_time'))
            if set(domains) & tags and published['start'] and published['start'] <= at.date().isoformat():
                relevant.append((published['start'], item))
        latest = max(relevant, key=lambda pair: pair[0]) if relevant else None
        freshness.append({'topic': topic, 'label': label, 'latest_publication': latest[0] if latest else None,
                          'evidence_id': latest[1]['id'] if latest else None,
                          'event_time': latest[1].get('event_time') if latest else None})
    return {'as_of': as_of, 'countries': countries, 'sources': bundle['sources.json']['sources'],
            'domains': DOMAINS, 'states': STATES, 'outcomes': OUTCOMES, 'roles': ROLE_LABELS, 'runs': runs,
            'evidence_links': dict(links), 'events': bundle['events.json']['events'],
            'case_reviews': bundle['case-reviews.jsonl'], 'unlinked_records': len(evidence) - len(links), 'domain_freshness': freshness,
            'duplicate_candidates': candidates,
            'pending_backfill': [e['id'] for e in evidence if e.get('intake_type') == 'retrospective_backfill' and e.get('forecast_integration') == 'pending_review' and e['id'] not in reviewed]}


def table(headers, rows):
    return '<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th scope="col">{escape(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def source_link(url, label='Zdroj'):
    return f'<a href="{escape(url, quote=True)}" rel="noopener noreferrer">{escape(label)} ↗</a>' if safe_url(url) else escape(label)


def coverage_content(data, state, bundle, watchlist):
    e = escape
    country_rows = []
    for area, value in sorted(data['countries'].items(), key=lambda pair: pair[1]['label']):
        details = ''.join(f'<li><strong>{e(c["checked_at"])} · {e(OUTCOMES[c["outcome"]])}</strong><br>{e(c["scope"])}<br>Období {e(c["period_start"])} – {e(c["period_end"])}<br>{e(c["limitations"])}<br>' + ' · '.join(source_link(u) for u in c['urls']) + '</li>' for c in value['checks'])
        sources = ' · '.join(source_link(s['url'], s['name']) for s in data['sources'] if s['id'] in value['source_ids'])
        country_rows.append([f'<a href="signals.html?mode=coverage&amp;area={area}">{e(value["label"])}</a>',
            f'<span class="coverage-state {value["status"]}">{e(value["status_label"])}</span>',
            e(value['last_attempt'] or 'Bez záznamu'),
            e(', '.join(DOMAINS[d] for d in value['domains_missing']) or 'Rozsah dle kontroly'),
            f'<details><summary>Zdroje a rozsah ({len(value["checks"])} kontrol)</summary><p>{sources}</p><ul>{details}</ul></details>'])
    scope_rows = [[e(c['domain']), e(state['assessment_time']), e(c['checks'])] for c in state.get('research_scope', {}).get('coverage', [])]
    freshness_rows = [[e(row['label']), e(row['latest_publication'] or 'Neznámé'), e(row['event_time'] or 'Neurčeno'), f'<a href="signals.html?record={e(row["evidence_id"], quote=True)}">Uložený podklad →</a>' if row['evidence_id'] else '—'] for row in data['domain_freshness']]
    source_rows = [[e(s['name']), e(', '.join(AREAS[a]['label'] for a in s['areas'])), e(', '.join(DOMAINS[d] for d in s['domains'])), f'{s["cadence_days"]} d', source_link(s['url'])] for s in data['sources']]
    tasks = due_tasks(bundle, watchlist, instant(data['as_of']))
    latest = data['runs'][-1] if data['runs'] else None
    status = 'Bez záznamu' if not latest else 'Částečný' if latest['status'] == 'partial' else 'Dokončený'
    return f'''<div class="hero"><div><p class="eyebrow">Kontrola pokrytí · {e(data['as_of'])}</p><h1>Pokrytí zdrojů a mezery rešerše</h1><p class="lede">Prázdná mapa může znamenat chybějící rešerši. Zde je vidět rozsah provedených kontrol, nedostupné zdroje a další práce.</p></div></div>
<div class="archive-notice"><strong>Poslední monitoring: {status}.</strong> {len(latest['incomplete_tasks']) if latest else 0} úkolů bez úplného výsledku. Rešerše předpovědi má vlastní uzávěrku {e(state['assessment_time'])}. Nový metadatový audit ji neposouvá. Retrospektivní podklady čekající na analytické začlenění: {len(data['pending_backfill'])}.</div>
<p><a href="signals.html?mode=coverage">Mapa pokrytí →</a> · <a href="quality.html">Události a vyhodnocování →</a> · <a href="society.html">Účinky a česká společnost →</a></p>
<section class="section"><h2>EU a NATO: {len(country_rows)} zemí</h2><p class="note">Datum je kontrola zdroje, ne datum poslední události. Úplné pokrytí vyžaduje výslovný audit všech čtyř oblastí. Chybějící strukturovaný záznam nepopírá starší rešerši ve zprávách.</p>{table(['Země', 'Pokrytí', 'Poslední pokus', 'Chybějící rozsah', 'Auditní stopa'], country_rows)}</section>
<section class="section"><h2>Rozsah posledního hodnocení</h2><p class="note">Převzato z původního research_scope. Nejde o nové kontroly zemí. Čas rešerše není časem posledního pozorování.</p>{table(['Doména', 'Uzávěrka rešerše', 'Rozsah a omezení'], scope_rows)}</section>
<section class="section"><h2>Stáří podkladů podle témat</h2><p class="note">Nejnovější zveřejnění v uložené evidenci, nikoli záruka aktuálnosti všech indikátorů. Čerstvý článek může popisovat starou událost. Nové datum dohledání neposouvá publikaci.</p>{table(['Téma', 'Poslední publikace', 'Původní údaj události', 'Podklad'], freshness_rows)}</section>
<section class="section"><h2>Pracovní fronta k datu auditu</h2><p>{len(tasks)} splatných nebo dosud neprovedených úkolů. Denně aktivní případy a prioritní zdroje; týdně rotující audity zemí; měsíčně mezery zdrojů.</p><details><summary>Zobrazit úkoly</summary><ul>{''.join('<li>' + e(t['id']) + (' · původně ' + e(t['scheduled_for']) if t.get('scheduled_for') else '') + '</li>' for t in tasks)}</ul></details></section>
<section class="section"><h2>Registr zdrojů</h2>{table(['Zdroj', 'Rozsah', 'Domény', 'Kontrola novinek', 'Odkaz'], source_rows)}</section>
<p><a href="data/monitoring.json">Odvozená data</a> · <a href="data/coverage.jsonl">Neměnný protokol kontrol</a> · <a href="data/sources.json">Registr a rotace</a></p>'''


def quality_content(data, bundle, state, labels=None):
    e = escape
    event_rows = []
    latest = {r['event_id']: r for r in data['case_reviews']}
    for event in data['events']:
        current = latest.get(event['id'], event)
        links = '<ul>' + ''.join(f'<li><a href="signals.html?record={e(link["evidence_id"], quote=True)}">{e(ROLE_LABELS[link["role"]])}</a> · {e(link["line_id"])}<br>{e(link["claim"])}<br>{e(link["independence_basis"])}</li>' for link in event['links']) + '</ul>'
        families = len({link['line_id'] for link in event['links']})
        event_rows.append([f'<span id="{e(event["id"], quote=True)}">{e(event["title"])}</span><p>{e(event["summary"])}</p>',
                           f'{len(event["links"])} / {families}<details><summary>Provenance</summary>{links}</details>',
                           e(event['attribution_basis']), e(current.get('next_check_by', 'Bez otevřeného případu')) + '<p>' + e(current.get('next_action', '')) + '</p>'])
    evaluation_data = evaluation(bundle)
    forecast_rows = []
    for forecast in evaluation_data['rows']:
        resolution = forecast['resolution']
        result = {'yes':'Ano','no':'Ne','unknown':'Neznámé'}[resolution['outcome']] if resolution else 'Dříve splněno — bez skórování' if forecast.get('legacy_outcome') == 'occurred' else 'Nevyhodnoceno'
        label = (labels or {}).get(forecast['question'].rsplit('_by_', 1)[0], forecast['definition'])
        forecast_rows.append([e(label), f'{forecast["p"] * 100:g} %', e(forecast['window_start']) + '<br>→ ' + e(forecast['window_end']),
                              e(result), f'{forecast["brier"]:.4f}' if forecast['brier'] is not None else '—',
                              e(forecast['exclusion_reason'] or ('První registrace kohorty' if forecast['selected_for_cohort'] else 'Další revize stejné kohorty')) + f'<details><summary>Zmrazená definice</summary><p>{e(forecast["definition"])}</p><p>{e(json.dumps(forecast["resolution_criteria"], ensure_ascii=False))}</p><a href="reports/{e(forecast["report"].removesuffix(".md"))}.html">Původní zpráva</a></details>'])
    indicator_rows = []
    obs = {o['indicator_id']: o for o in sorted(bundle['indicator-observations.jsonl'], key=lambda o: o['observed_at'])}
    for i in bundle['indicators.json']['indicators']:
        last = obs.get(i['id'])
        indicator_rows.append([e(i['label']), e(i['expected_signature']), e(i['baseline']) + '<p>' + e(i['alternative']) + '</p>',
                               e(last['observed_at'] + ' · ' + last['result'] if last else 'Bez strukturovaného pozorování')])
    score = f'{evaluation_data["brier"]:.4f}' if evaluation_data['brier'] is not None else 'Zatím nevyčíslujeme'
    return f'''<div class="hero"><div><p class="eyebrow">Kontrola kvality</p><h1>Události, důkazy a výsledky</h1><p class="lede">Více článků nemusí znamenat více událostí ani více nezávislých potvrzení.</p></div></div>
<div class="archive-notice">Ruční propojení: {len(data['events'])} událostí či hodnocení. {data['unlinked_records']} záznamů ještě nemá revidované přiřazení. Přehled není úplný počet útoků. Zdrojové rodiny se počítají uvnitř případu, nikoli jako potvrzení každého jeho tvrzení.</div>
<section class="section"><h2>Propojené případy</h2>{table(['Případ', 'Záznamy / zdrojové rodiny', 'Atribuce a nejistota', 'Další kontrola'], event_rows)}</section>
<section class="section"><h2>Kandidáti k prověření duplicit</h2><p>{len(data['duplicate_candidates'])} skupin se stejnou URL a dosud neúplnou revizí. Živý index nebo Telegram feed může obsahovat různé události; shoda URL není automatické sloučení.</p><details><summary>Otevřít seznam</summary><ul>{''.join('<li>' + source_link(c['url']) + ' · ' + e(', '.join(c['evidence_ids'])) + '</li>' for c in data['duplicate_candidates'])}</ul></details></section>
<section class="section"><h2>Očekávané a chybějící indikátory</h2><p class="note">Absenci lze vyhodnotit jen tam, kde měla být změna pozorovatelná a proběhla dostatečná kontrola. Chybějící měření znamená neznámý stav.</p>{table(['Indikátor', 'Očekávaný projev', 'Baseline a alternativa', 'Poslední pozorování'], indicator_rows)}</section>
<section class="section"><h2>Původní dlouhé prognózy</h2><p><a href="forecasts.html">Nové 7denní a 30denní prognózy s pevnými okny a úplným přehledem výsledků →</a></p><p><strong>Brier původního registru: {score}</strong> · {evaluation_data['scored_questions']} vyhodnocených otázek. Brier = průměr (p − výsledek)²; ano = 1, ne = 0. Neznámé výsledky se nepočítají.</p><p class="note">{e(evaluation_data['rule'])} Starší vydání používala posouvané počátky; jejich hodnoty se zpětně nemění. Nový protokol je vyhodnocován zvlášť. Malý vzorek nedokládá kalibraci. Dříve uzavřené otázky nejsou zpětně registrované úspěšné předpovědi.</p>{table(['Otázka', 'Odhad', 'Zmrazené okno', 'Výsledek', 'Brier', 'Způsobilost'], forecast_rows)}</section>
<p><a href="data/events.json">Registr událostí</a> · <a href="data/forecast-register.jsonl">Registr předpovědí</a> · <a href="data/forecast-resolutions.jsonl">Adjudikace</a> · <a href="coverage.html">Pokrytí zdrojů →</a></p>'''


def effects_content(bundle, state, as_of):
    e = escape
    rows = []
    at = instant(as_of)
    for series in bundle['metrics.json']['series']:
        observations = sorted((o for o in bundle['metric-observations.jsonl'] if o['series_id'] == series['id']), key=lambda o: (temporal(o['period'])['end'], o['recorded_at']), reverse=True)
        if observations:
            last = observations[0]
            age = (at.date() - datetime.fromisoformat(temporal(last['period'])['end']).date()).days
            stale = age > series['fresh_days']
            value = f'{last["value"]:g}' if last['value'] is not None else 'Neznámé'
            if series['unit'] == 'percent':
                value += ' %' if last['value'] is not None else ''
            elif last['value'] is not None:
                value += ' ' + {'faults':'poruch','hours':'hodin'}.get(series['unit'], series['unit'])
            design = ' · '.join(str(last[k]) for k in ('sample_size','population','mode') if k in last)
            detail = e(last.get('note', '')) + '<p>' + e(last.get('comparability', '')) + '</p><p>' + e(design) + '</p>'
            detail += '<p>' + e(last['causal_basis']) + '</p>' + ' · '.join(source_link(url) for url in last['source_urls'])
            if last.get('missing_reason'):
                detail += '<p>' + e(last['missing_reason']) + '</p>'
            status = last.get('status', 'unknown')
            rows.append([e(series['label']), e(value), e(last['period']) + ('<br><strong>Starší měření</strong>' if stale else ''), e(STAGES[last['stage']]) + ' · ' + e(STATUSES.get(status, status)), f'<details><summary>Význam, metodika a zdroje</summary><p>{e(series["definition"])}</p>{detail}</details>'])
        else:
            rows.append([e(series['label']), 'Dosud nezměřeno', '—', 'Neznámý stav', e(series['definition'])])
    rubric = bundle['metrics.json']['wdpi']
    applied = state['wdpi'].get('method_version') == rubric['version']
    method_note = 'Hodnocení používá kotvy anchored-v2; historické hodnoty před zlomem nejsou přímo srovnatelné.' if applied else 'Hodnocení používá dosavadní metodu. Nové kotvy anchored-v2 nebyly na tento prior aplikovány.'
    anchor_rows = [[e(key), '<br>'.join(f'<strong>{score}</strong> — {e(label)}' for score,label in anchors.items())] for key,anchors in rubric['anchors'].items()]
    history = '<ul>' + ''.join('<li>' + e(o['series_id']) + ' · ' + e(o['period']) + ' · ' + e(str(o['value'])) + ' · ' + e(o['stage']) + '</li>' for o in bundle['metric-observations.jsonl']) + '</ul>'
    return f'''<div class="hero"><div><p class="eyebrow">Účinky a společnost · stav evidence {e(as_of)}</p><h1>Účinky nátlaku a česká společnost</h1><p class="lede">Sledujeme realizovanou podporu, provozní náklady, důvěru a chování veřejnosti. U nezměřených veličin zůstává neznámý stav.</p></div></div>
<section class="section"><h2>Pozorované účinky a česká odolnost</h2><p class="note">Číselný souhrn české odolnosti zatím nemá obhajitelný model. Jediný starší průzkum nepředpovídá reakci společnosti na přímý konflikt.</p>{table(['Ukazatel', 'Poslední hodnota', 'Období pozorování', 'Fáze a doložení', 'Podklady'], rows)}<details><summary>Celá uložená řada pozorování</summary>{history}</details></section>
<section class="section"><h2>WDPI: zachovaná historie a nová pravidla</h2><div class="archive-notice">Poslední hodnocení {e(state['assessment_time'])}: WDPI {state['wdpi']['total']}/100, komponenty {state['wdpi']['resource_dilution']}/{state['wdpi']['domestic_pain']}/{state['wdpi']['self_deterrence']}. {e(method_note)}</div><p>{e(rubric['break_note'])}</p><p>{e(rubric['selection_rule'])} {e(rubric['missing_policy'])}</p><p class="formula">{e(rubric['formula'])}; váhy 35 % / 35 % / 30 %.</p><details><summary>Zobrazit kotvy komponent</summary>{table(['Komponenta', 'Doložená úroveň'], anchor_rows)}</details><p class="note">Ruská účast se ukládá samostatně: způsobeno / zesíleno / využito Ruskem / nezávislé / neznámé. Obecná deklarace podpory není platba a popularita narativu není prokázaný politický účinek.</p></section>
<p><a href="data/metrics.json">Definice ukazatelů a kotvy</a> · <a href="data/metric-observations.jsonl">Pozorování</a> · <a href="data/wdpi-assessments.jsonl">Nová hodnocení WDPI</a></p>'''
