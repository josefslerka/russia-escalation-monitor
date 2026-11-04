"""Prospective fixed-window forecasts. No probability estimation or automatic outcomes."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import re
from zoneinfo import ZoneInfo

from signals import safe_url, temporal

PROTOCOL = 'forecast-protocol.json'
ROUNDS = 'forecast-rounds.jsonl'
OUTCOMES = 'forecast-outcomes.jsonl'
UTC = timezone.utc


def methods():
    # Lazy import keeps the legacy helpers reusable by the versioned methods module.
    import forecast_methods
    return forecast_methods


def instant(value):
    require(isinstance(value, str) and value, 'Forecast timestamp is missing')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'Forecast timestamp needs timezone')
    return result.astimezone(UTC)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def probability(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1


def latest(rows):
    return {r['forecast_id']: r for r in rows}


def question_map(protocol):
    return {q['id']: q for q in protocol['questions']}


def preserve_protocol(old, new, at):
    """Freeze published rules and past planned denominators, even before an issue exists."""
    variable = {'questions', 'retirements'}
    require({k:v for k,v in old.items() if k not in variable} == {k:v for k,v in new.items() if k not in variable}, 'Published forecast schedule/policy cannot change')
    for key in variable:
        require(new[key][:len(old[key])] == old[key], 'Published forecast definitions/retirements are append-only')
    for q in new['questions'][len(old['questions']):]:
        require(instant(q['active_from']) > at, 'New question cannot create or erase historical forecast slots')
    for r in new['retirements'][len(old['retirements']):]:
        require(instant(r['effective_at']) > at, 'Question retirement cannot erase past planned slots')


def window(protocol, days, number):
    start = instant(protocol['anchor']) + timedelta(days=days * number)
    return start, start + timedelta(days=days)


def identifier(question_id, days, start):
    return f'fixed-{question_id}-{days}d-{start.strftime("%Y%m%dT%H%M%SZ")}'


def slots(protocol, at):
    """All elapsed/active windows plus the next one: omissions never disappear."""
    if at < instant(protocol['introduced_at']):
        return
    epoch = instant(protocol['anchor'])
    retired = {r['question_id']:instant(r['effective_at']) for r in protocol['retirements']}
    for days in protocol['horizons_days']:
        current = max(0, int((at - epoch).total_seconds() // (days * 86400)))
        for number in range(current + 2):
            start, end = window(protocol, days, number)
            for q in protocol['questions']:
                if start < instant(q['active_from']) or q['id'] in retired and start >= retired[q['id']]:
                    continue
                yield {'id': identifier(q['id'], days, start), 'question_id': q['id'],
                       'horizon_days': days, 'window_number': number,
                       'window_start': start.isoformat(), 'window_end': end.isoformat(),
                       'issue_opens': (start - timedelta(hours=protocol['issue_lead_hours'])).isoformat(),
                       'settle_after': (end + timedelta(hours=q['settlement_delay_hours'])).isoformat()}


def make_issue(protocol, request, at):
    """Freeze a researched judgment before a predefined window; never scale an annual p."""
    allowed = {'question_id', 'horizon_days', 'window_number', 'p', 'source_cutoff',
               'rationale', 'alternative', 'evidence_ids', 'check_ids', 'source_urls', 'abstention_reason'}
    if protocol['id'] == 'fixed-v2':
        allowed |= {'estimation_passes','estimation_mode','external_influence_note','dependence_note','temporal_profile','related_question_note'}
    require(set(request) <= allowed, 'Unknown issue fields; timestamps/contracts are generated')
    q = question_map(protocol)[request['question_id']]
    start, end = window(protocol, request['horizon_days'], request['window_number'])
    result = {**deepcopy(request), 'id': identifier(q['id'], request['horizon_days'], start),
            'protocol': protocol['id'], 'issued_at': at.isoformat(),
            'window_start': start.isoformat(), 'window_end': end.isoformat(),
            'settle_after': (end + timedelta(hours=q['settlement_delay_hours'])).isoformat(),
            'contract': deepcopy(q), 'contract_hash': digest(q),
            'benchmarks': deepcopy(protocol['benchmarks'])}
    if protocol['id'] == 'fixed-v2':
        result['final_adjudication_by'] = (instant(result['settle_after']) + timedelta(days=q['adjudication_policy']['final_delay_days'])).isoformat()
        passes = result.get('estimation_passes', [])
        if result['p'] is None and passes and all(p.get('p') is None for p in passes):
            # An unfilled plan template is a valid abstention, not three raw estimates.
            result['estimation_passes'] = passes = []
        estimates = [p['p'] for p in passes]
        require(all(probability(p) for p in estimates), 'Raw estimates must be numeric; fill every pass or use an explicit abstention')
        result['estimate_spread'] = [min(estimates),max(estimates)] if estimates else []
    return result


def timing_bounds(raw, zone=None):
    """Preserve day precision; never manufacture an incident hour for a boundary day."""
    if isinstance(raw, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
        require(zone, 'Date-only outcome needs its source timezone')
        start = datetime.fromisoformat(raw).replace(tzinfo=ZoneInfo(zone))
        return start.astimezone(UTC), (start + timedelta(days=1) - timedelta(microseconds=1)).astimezone(UTC)
    value = instant(raw)
    return value, value


def validate(bundle, evidence):
    p = bundle[PROTOCOL]
    require(p['id'] == 'fixed-v1' and p['window_convention'] == '(start, end]', 'Unsupported forecast protocol')
    require(p['horizons_days'] == [7, 30], 'Window changes require a protocol migration')
    require(p['issue_lead_hours'] == 24 and p['maximum_source_age_hours'] == 48, 'Unknown issuance policy')
    require(p['benchmarks'] == {'constant_half': .5, 'always_no': 0.0}, 'Benchmark changes require a version')
    epoch, introduced = instant(p['anchor']), instant(p['introduced_at'])
    require(introduced < epoch and instant(p['enforce_after']) < epoch, 'Protocol must precede its first window')
    sources = {s['id'] for s in bundle['sources.json']['sources']}
    checks = {c['id']: c for c in bundle['coverage.jsonl']}
    evid = {e['id']: e for e in evidence}
    events = {e['id']: e for e in bundle['events.json']['events']}
    methods().validate_v2_protocol(bundle)
    all_protocols = methods().protocols(bundle)
    questions = {q['id']:q for protocol in all_protocols for q in protocol['questions']}
    protocol_by_question = {q['id']:protocol for protocol in all_protocols for q in protocol['questions']}
    require(len(questions) == sum(len(protocol['questions']) for protocol in all_protocols), 'Duplicate fixed question')
    for q in questions.values():
        require(q['label'] and q['definition'] and q['version'] >= 1, 'Incomplete fixed definition')
        require(instant(q['active_from']) >= epoch, 'Question activity precedes fixed protocol')
        require(q['criteria'] and q['exclusions'] and q['dependency_group'], 'Missing fixed criteria/exclusions')
        require(q['time_basis'] in {'publication', 'occurrence'} and q['settlement_delay_hours'] >= 72, 'Invalid outcome timing policy')
        require(type(q['primary_score']) is bool and q['minimum_primary_lines'] in {1, 2}, 'Invalid scoring/evidence policy')
        group_ids = set()
        for group in q['source_groups']:
            require(group['id'] not in group_ids, 'Duplicate closure source group')
            group_ids.add(group['id'])
            require(set(group['source_ids']) <= sources and len(group['source_ids']) == len(set(group['source_ids'])), 'Unknown/repeated forecast sources')
            require(0 < group['min_sources'] <= len(group['source_ids']), 'Invalid closure source threshold')
        require(bool(group_ids), 'Missing closure source groups')
    retired = {}
    for retirement in [r for protocol in all_protocols for r in protocol['retirements']]:
        qid = retirement['question_id']
        require(qid in questions and qid not in retired, 'Invalid/repeated question retirement')
        retired[qid] = instant(retirement['effective_at'])
        require(retired[qid] > instant(questions[qid]['active_from']) and retirement['reason'], 'Invalid retirement timing/reason')
    rounds = {f['id']: f for f in bundle[ROUNDS]}
    for f in rounds.values():
        require(f['question_id'] in questions, 'Unknown forecast question/protocol')
        p = protocol_by_question[f['question_id']]
        introduced = instant(p['introduced_at'])
        require(f['protocol'] == p['id'], 'Unknown forecast question/protocol')
        q = questions[f['question_id']]
        require(f['contract'] == q and f['contract_hash'] == digest(q), 'Issued contract differs from frozen definition; retain old version')
        require(type(f['window_number']) is int and f['window_number'] >= 0 and f['horizon_days'] in p['horizons_days'], 'Invalid fixed window number/horizon')
        start, end = window(p, f['horizon_days'], f['window_number'])
        require(start >= instant(q['active_from']) and (q['id'] not in retired or start < retired[q['id']]), 'Issued forecast removed from question schedule')
        require(instant(f['window_start']) == start and instant(f['window_end']) == end, 'Fixed window cannot roll or resize')
        require(f['id'] == identifier(q['id'], f['horizon_days'], start), 'Noncanonical fixed forecast ID')
        require(instant(f['settle_after']) == end + timedelta(hours=q['settlement_delay_hours']), 'Settlement deadline changed')
        issued, cutoff = instant(f['issued_at']), instant(f['source_cutoff'])
        successor = bundle.get(methods().V2)
        if p['id'] == 'fixed-v1' and successor and issued >= instant(successor['introduced_at']):
            require(start < instant(successor['transition'][str(f['horizon_days'])]), 'Retired issuance slot belongs to the new methodology')
        require(introduced <= issued < start and start - issued <= timedelta(hours=p['issue_lead_hours']), 'Issue must precede its fixed window, inside issuance period')
        require(cutoff <= issued and issued - cutoff <= timedelta(hours=p['maximum_source_age_hours']), 'Invalid/stale issue source cutoff')
        require((f['p'] is None and bool(f.get('abstention_reason'))) or probability(f['p']), 'Invalid probability; abstention requires reason')
        require(f['rationale'] and f['alternative'], 'Issue needs rationale and alternative explanation')
        require(f['benchmarks'] == p['benchmarks'], 'Frozen benchmark mismatch')
        require(isinstance(f['evidence_ids'], list) and set(f['evidence_ids']) <= set(evid), 'Unknown issue evidence')
        require(f['check_ids'] and len(f['check_ids']) == len(set(f['check_ids'])) and set(f['check_ids']) <= set(checks), 'Issue requires actual source checks')
        require(all(instant(checks[c]['checked_at']) <= cutoff for c in f['check_ids']), 'Issue uses checks after its source cutoff')
        require(max(instant(checks[c]['checked_at']) for c in f['check_ids']) >= issued - timedelta(hours=p['maximum_source_age_hours']), 'Issue relies only on stale checks')
        require(f['p'] is None or any(checks[c]['outcome'] != 'unavailable' for c in f['check_ids']), 'All sources unavailable: record abstention instead of a numeric forecast')
        require(f['source_urls'] and all(safe_url(u) for u in f['source_urls']), 'Issue source links missing')
        methods().validate_estimate(f, checks)
    # Same cutoff and nested event windows should not reverse their probabilities.
    paired = defaultdict(dict)
    for f in rounds.values():
        if f['p'] is not None:
            paired[(f['question_id'], f['window_start'], f['source_cutoff'])][f['horizon_days']] = f['p']
    for values in paired.values():
        require(not {7, 30} <= values.keys() or values[7] <= values[30], 'Thirty-day probability below nested seven-day probability at same cutoff')
    methods().validate_relations(list(rounds.values()))
    methods().validate_auxiliary(bundle, evidence)
    previous = {}
    previous_times = {}
    previous_definitive = {}
    for r in bundle[OUTCOMES]:
        require(r['forecast_id'] in rounds, 'Unknown fixed forecast outcome')
        f = rounds[r['forecast_id']]
        q = f['contract']
        at = instant(r['resolved_at'])
        require(at >= instant(f['issued_at']), 'Outcome precedes issuance')
        require(r.get('supersedes') == previous.get(f['id']), 'Outcome correction must name preceding decision')
        require(f['id'] not in previous_times or at >= previous_times[f['id']], 'Outcome corrections out of time order')
        previous[f['id']] = r['id']
        previous_times[f['id']] = at
        allowed_outcomes = {'yes','no','unknown'} | ({'void'} if f['protocol'] == 'fixed-v2' else set())
        require(r['outcome'] in allowed_outcomes and r['rationale'], 'Missing outcome/rationale')
        require(isinstance(r['evidence_ids'], list) and set(r['evidence_ids']) <= set(evid), 'Unknown outcome evidence')
        require(isinstance(r['check_ids'], list) and set(r['check_ids']) <= set(checks), 'Unknown outcome checks')
        require(all(instant(checks[c]['checked_at']) <= at for c in r['check_ids']), 'Outcome precedes its checks')
        require(r['source_urls'] and all(safe_url(u) for u in r['source_urls']), 'Outcome sources missing')
        if r['outcome'] == 'yes':
            require(r['case_id'] in events and r['evidence_ids'], 'Yes requires a canonical case and evidence')
            require(events[r['case_id']]['kind'] in {'incident','policy'}, 'Yes needs an event-level case, not a series or general assessment')
            require(set(r['evidence_ids']) & {l['evidence_id'] for l in events[r['case_id']]['links']}, 'Outcome evidence is not linked to its case')
            lo, hi = instant(r['qualifying_time_start']), instant(r['qualifying_time_end'])
            if f['protocol'] == 'fixed-v1':
                require(instant(f['window_start']) < lo <= hi <= instant(f['window_end']) and hi <= at, 'Qualifying time uncertainty crosses fixed window boundary')
            require(r.get('event_time') or r.get('event_time_note'), 'Preserve actual incident time or explain its absence')
            if q['time_basis'] == 'publication':
                require(r.get('publication_time') and r.get('first_qualifying_publication') is True, 'Disclosure outcome requires first qualifying publication')
                raw_time = r['publication_time']
                event_period = temporal(r.get('event_time'))
                if f['protocol'] == 'fixed-v1':
                    require(not event_period['start'] or event_period['start'] <= (hi + timedelta(hours=14)).date().isoformat(), 'Disclosure cannot attest a future physical incident')
            else:
                require(r.get('event_time') and r.get('timing_basis') == 'occurrence', 'Occurrence outcome cannot use disclosure date')
                raw_time = r['event_time']
            require((lo, hi) == timing_bounds(raw_time, r.get('qualifying_timezone')), 'Qualifying bounds differ from original event/publication time precision')
            if f['protocol'] == 'fixed-v2':
                methods().validate_v2_time(bundle,evidence,f,r,raw_time,lo,hi)
            answers = r['criterion_evidence']
            require(set(answers) == set(q['criteria']) and all(isinstance(v, list) and v and set(v) <= set(r['evidence_ids']) for v in answers.values()), 'Every frozen criterion needs evidence')
            if q['time_basis'] == 'publication':
                anchor_ids = answers['first_qualifying_publication']
                pub_date = temporal(r['publication_time'])['start']
                require(any(temporal(evid[i].get('publication_time'))['start'] == temporal(evid[i].get('publication_time'))['end'] == pub_date for i in anchor_ids), 'Disclosure date is not supported by the cited publication')
            primary = [evid[i] for i in r['evidence_ids'] if evid[i].get('source_tier') == 1]
            lines = {e.get('independent_source_line') or e.get('provenance_root') or e.get('source_url') for e in primary}
            require(len(lines) >= q['minimum_primary_lines'], 'Insufficient independent primary source lines')
        elif r['outcome'] == 'no':
            require(at >= instant(f['settle_after']), 'No requires closed horizon plus reporting delay')
            require(r.get('open_claim_ids') == [] and r.get('coverage_basis'), 'Unresolved claims/missing coverage cannot become no')
            covered = set()
            for cid in r['check_ids']:
                c = checks[cid]
                require(c['scope_type'] == 'forecast_audit' and c.get('forecast_id') == f['id'], 'No requires a dedicated window audit')
                require(c['outcome'] in {'no_new_relevant', 'relevant_found'}, 'Partial/unavailable checks cannot establish no')
                require(instant(c['checked_at']) >= instant(f['settle_after']), 'Closure source check predates reporting delay')
                require(c['period_start'] <= instant(f['window_start']).date().isoformat() and c['period_end'] >= instant(f['window_end']).date().isoformat(), 'Closure check does not cover whole fixed window')
                require('incidents' in c['domains'], 'Closure check lacks incident coverage')
                covered.update(c['source_ids'])
            require(r['check_ids'], 'No needs successful source checks')
            for group in q['source_groups']:
                require(len(covered & set(group['source_ids'])) >= group['min_sources'], 'Closure source group incompletely checked')
        elif r['outcome'] == 'unknown':
            require(instant(r['next_check_by']) > at, 'Unknown outcome needs a new check deadline')
        methods().validate_outcome(bundle,evidence,f,r,previous_definitive.get(f['id']))
        if r['outcome'] in {'yes','no'}:
            previous_definitive[f['id']] = r
    # A later derivative cannot manufacture another first publication of the same case.
    case_times = {}
    for r in latest(bundle[OUTCOMES]).values():
        if r['outcome'] != 'yes':
            continue
        key = (rounds[r['forecast_id']]['question_id'], r['case_id'])
        bounds = (instant(r['qualifying_time_start']), instant(r['qualifying_time_end']))
        require(key not in case_times or case_times[key] == bounds, 'Same case given a different qualifying time')
        case_times[key] = bounds


def legacy_origins(bundle, state):
    result = {}
    for key, h in state['hypotheses'].items():
        if h.get('status', 'active') != 'active':
            continue
        prior = [f for f in bundle['forecast-register.jsonl'] if f['eligible'] and f['question'] == key
                 and f['definition'] == h['event_definition'] and f.get('definition_version',1) == h.get('definition_version',1)
                 and ('resolution_criteria' not in h or f['resolution_criteria'] == h['resolution_criteria'])
                 and f['window_end'] == h.get('forecast_window_end', state['forecast_window_end'])]
        if prior:
            first = min(prior, key=lambda f: (instant(f['forecast_time']), f['id']))
            result[key] = {'forecast_window_start': first['window_start'], 'forecast_window_end': first['window_end']}
    return result


def validate_legacy_windows(bundle, state):
    if instant(state['assessment_time']) < instant(bundle[PROTOCOL]['enforce_after']):
        return
    for key, bounds in legacy_origins(bundle, state).items():
        h = state['hypotheses'][key]
        for boundary, expected in bounds.items():
            require(h.get(boundary, state.get(boundary)) == expected, 'Legacy forecast window rolls; use monitor.py origins before assessment')
    for key,h in state['hypotheses'].items():
        old = [r for r in bundle['forecast-register.jsonl'] if r['question'] == key]
        same = [r for r in old if r['definition'] == h['event_definition'] and r.get('definition_version',1) == h.get('definition_version',1)
                and ('resolution_criteria' not in h or r['resolution_criteria'] == h['resolution_criteria'])]
        if h.get('status','active') == 'active' and old and not same:
            require(h.get('definition_version',1) > max(r['definition_version'] for r in old) and h.get('definition_change_reason'), 'Changed legacy definition needs a new version and explanation')
            require(h.get('forecast_window_start',state['forecast_window_start']) == state['assessment_time'], 'New legacy definition needs an explicit new initial window')
    review = state.get('research_scope', {}).get('fixed_forecast_review')
    require(isinstance(review, dict) and review.get('reviewed_at'), 'New assessment must review fixed forecast tasks')
    require(instant(bundle[PROTOCOL]['introduced_at']) <= instant(review['reviewed_at']) <= instant(state['assessment_time']), 'Fixed forecast review outside assessment')
    expected = assessment_scope(bundle, instant(review['reviewed_at']))
    expected['reviewed_at'] = review['reviewed_at']
    require(review == expected, 'Fixed forecast review omits missed/pending outcomes')


def assessment_scope(bundle, at):
    """A reproducible queue snapshot for research_scope, not a claim of finished research."""
    data = evaluate(bundle, at)
    return {'reviewed_at': at.isoformat(),
            'missed_issue_ids': sorted(r['id'] for r in data['rows'] if r['status'] == 'missed'),
            'pending_outcome_ids': sorted(r['id'] for r in data['rows'] if r['status'] in {'awaiting_resolution', 'unknown', 'awaiting_final_resolution'}),
            'awaiting_issue_ids': sorted(r['id'] for r in data['rows'] if r['status'] == 'awaiting_issue')}


def tasks(bundle, at):
    rounds = {f['id']:f for f in bundle[ROUNDS] if instant(f['issued_at']) <= at}
    outcomes = latest([r for r in bundle[OUTCOMES] if instant(r['resolved_at']) <= at])
    result = []
    for slot in methods().planned_slots(bundle, at):
        if slot['id'] not in rounds and instant(slot['issue_opens']) <= at < instant(slot['window_start']):
            result.append({'id': 'forecast:issue:' + slot['id'], 'kind': 'forecast_issue', 'priority': 0, **{k:v for k,v in slot.items() if k != 'id'}})
    for f in rounds.values():
        outcome = outcomes.get(f['id'])
        deadline = outcome['next_check_by'] if outcome and outcome['outcome'] == 'unknown' else f['settle_after']
        final = f.get('final_adjudication_by')
        if final and instant(final) < instant(deadline):
            deadline = final
        if f['p'] is not None and (not outcome or outcome['outcome'] == 'unknown') and at >= instant(deadline):
            result.append({'id': 'forecast:resolve:' + f['id'], 'kind': 'forecast_resolution', 'priority': 0,
                           'forecast_id': f['id'], 'scheduled_for': deadline, 'window_end': f['window_end'],
                           'must_finalize': bool(final and at >= instant(final))})
        if f['protocol'] == 'fixed-v2' and f['p'] is not None and not any(r['forecast_id']==f['id'] and instant(r['recorded_at'])<=at for r in bundle.get(methods().BENCHMARKS,[])):
            result.append(dict(id='forecast:benchmark:'+f['id'],kind='forecast_benchmark',priority=1,forecast_id=f['id'],
                               instruction='Own estimate is frozen. Record a comparable pre-window quote or an explicit unsuccessful search; later quotes are context only.'))
    return result


def as_of(bundle, state):
    values = [state['assessment_time']] + [p['introduced_at'] for p in methods().protocols(bundle)]
    values += [f['issued_at'] for f in bundle[ROUNDS]] + [r['resolved_at'] for r in bundle[OUTCOMES]]
    values += [r['reviewed_at'] for r in bundle.get(methods().CANDIDATES,[])]
    values += [r['recorded_at'] for r in bundle.get(methods().BENCHMARKS,[])]
    return max(values, key=instant)


def evaluate(bundle, at):
    all_protocols = methods().protocols(bundle)
    questions = {q['id']:q for p in all_protocols for q in p['questions']}
    rounds, outcomes = {f['id']: f for f in bundle[ROUNDS]}, latest(bundle[OUTCOMES])
    rows = []
    for slot in methods().planned_slots(bundle, at):
        if instant(slot['issue_opens']) > at:
            continue
        f = rounds.get(slot['id'])
        outcome = outcomes.get(slot['id'])
        # As-of evaluation excludes information issued/adjudicated after the cutoff.
        if f and instant(f['issued_at']) > at:
            f = None
        if outcome and instant(outcome['resolved_at']) > at:
            outcome = next((r for r in reversed(bundle[OUTCOMES]) if r['forecast_id'] == slot['id'] and instant(r['resolved_at']) <= at), None)
        status = ('missed' if at >= instant(slot['window_start']) else 'awaiting_issue') if not f else (
            'abstained' if f['p'] is None else outcome['outcome'] if outcome else 'awaiting_resolution' if at >= instant(slot['settle_after']) else 'settling' if at >= instant(slot['window_end']) else 'open')
        if f and f.get('final_adjudication_by') and f['p'] is not None and status in {'unknown','awaiting_resolution'} and at >= instant(f['final_adjudication_by']):
            status = 'awaiting_final_resolution'
        y = int(status == 'yes') if status in {'yes', 'no'} and f and f['p'] is not None else None
        q = questions[slot['question_id']]
        rows.append({**slot, 'label': q['label'], 'primary_score': q['primary_score'],
                     'dependency_group': q['dependency_group'], 'status': status,
                     'p': f['p'] if f else None, 'issued_at': f['issued_at'] if f else None,
                     'final_adjudication_by': f.get('final_adjudication_by') if f else None,
                     'outcome': outcome, 'brier': (f['p'] - y)**2 if y is not None else None,
                     'always_no_brier': y**2 if y is not None else None, 'constant_half_brier': .25 if y is not None else None})
    cohort_ends = {}
    for r in rows:
        key=(r['protocol'],r['horizon_days'],r['window_start'])
        if r['primary_score']:
            cohort_ends[key]=max(cohort_ends.get(key,r['settle_after']),r['settle_after'],key=instant)
    for r in rows:
        key=(r['protocol'],r['horizon_days'],r['window_start'])
        r['cohort_ready_after']=cohort_ends.get(key,r['settle_after'])
    def summarize(selected, days):
        scored = [r for r in selected if r['brier'] is not None]
        counts = {status: sum(r['status'] == status for r in selected) for status in
                  ('yes','no','unknown','void','open','settling','awaiting_resolution','awaiting_final_resolution','awaiting_issue','missed','abstained')}
        brier = sum(r['brier'] for r in scored)/len(scored) if scored else None
        ref = sum(r['always_no_brier'] for r in scored)/len(scored) if scored else None
        return {'horizon_days': days, 'planned': len(selected), 'issued': sum(r['issued_at'] is not None for r in selected),
                          'scored': len(scored), 'counts': counts, 'brier': brier, 'always_no_brier': ref,
                          'constant_half_brier': .25 if scored else None,
                          'skill_vs_always_no': 1-brier/ref if ref and counts['yes'] and counts['no'] else None,
                          'interpretation': 'Descriptive scores; related questions and successive windows remain correlated. No calibration claim.',
                          **methods().score_diagnostics(selected,at)}
    visible_protocols=[p for p in all_protocols if instant(p['introduced_at'])<=at]
    summaries = [{**summarize([r for r in rows if r['protocol']==p['id'] and r['horizon_days']==days and r['primary_score']],days),'protocol':p['id']}
                 for p in visible_protocols for days in p['horizons_days']]
    by_question = [{**summarize([r for r in rows if r['question_id']==q['id'] and r['horizon_days']==days],days),
                    'question_id':q['id'],'label':q['label'],'primary_score':q['primary_score']}
                   for p in visible_protocols for q in p['questions'] for days in p['horizons_days']]
    return {'as_of': at.isoformat(), 'protocol': bundle[PROTOCOL]['id'], 'protocols':[p['id'] for p in visible_protocols],
            'methodology_updated_at':bundle.get(methods().V2,{}).get('introduced_at'),
            'coherence':methods().coherence([r for r in bundle[ROUNDS] if instant(r['issued_at'])<=at]),
            'related_forecasts':methods().related_comparisons(bundle,at),
            'external_comparisons':methods().benchmark_scores(bundle,rows,at),
            'corrections':[r for r in bundle[OUTCOMES] if instant(r['resolved_at'])<=at and r.get('correction_reason_class')],
            'rows': rows, 'summaries': summaries, 'by_question':by_question,
            'rule': 'Samostatně 7 a 30 dnů; první vydání před začátkem pevného okna. České a pobaltské podotázky jsou diagnostické a nevstupují do souhrnu. Nevydané, neznámé a nevyhodnocené otázky zůstávají viditelné.'}


def content(bundle, data):
    from forecast_pages import content as render
    return render(bundle, data)
