"""Versioned forecasting methods; never rewrite an issued judgment or its contract."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
import re
from statistics import median

import forecasting as f
from signals import safe_url, temporal

V2 = 'forecast-protocol-v2.json'
POLICY = 'forecast-review-policy.json'
CANDIDATES = 'forecast-candidate-reviews.jsonl'
BENCHMARKS = 'forecast-benchmarks.jsonl'
EXTRA_JSON = (V2, POLICY)
EXTRA_LOGS = (CANDIDATES, BENCHMARKS)


def validate_new_evidence_labels(records):
    """Canonical new writes only; historical spellings stay in the immutable ledger."""
    statuses={'confirmed','reported','unverified_claim','analytical_inference','scenario'}
    signals={'intent','capability','opportunity','readiness','rhetoric/signalling','effect'}
    for row in records:
        f.require(row.get('status') in statuses, 'New evidence needs a canonical status label')
        types=row.get('signal_type')
        f.require(isinstance(types,list) and types and set(types)<=signals, 'New evidence needs canonical signal labels')


def protocols(bundle):
    return [bundle[f.PROTOCOL]] + ([bundle[V2]] if bundle.get(V2) else [])


def protocol_for(bundle, question_id):
    matches = [p for p in protocols(bundle) if question_id in f.question_map(p)]
    f.require(len(matches) == 1, 'Unknown or ambiguous protocol question')
    return matches[0]


def planned_slots(bundle, at):
    successor = bundle.get(V2)
    for p in protocols(bundle):
        for slot in f.slots(p, at):
            if (p['id'] == 'fixed-v1' and successor and at >= f.instant(successor['introduced_at'])
                    and f.instant(slot['window_start']) >= f.instant(successor['transition'][str(slot['horizon_days'])])):
                continue
            yield {**slot, 'protocol': p['id']}


def assigned_day_window(protocol, days, raw, zone):
    """A classification convention, not an invented occurrence/publication timestamp."""
    lo, inclusive_hi = f.timing_bounds(raw, zone)
    hi = inclusive_hi + timedelta(microseconds=1)
    epoch = f.instant(protocol['anchor'])
    length = days * 86400
    first = math.floor((lo - epoch).total_seconds() / length)
    last = math.floor((inclusive_hi - epoch).total_seconds() / length)
    choices = []
    for number in range(first, last + 1):
        start, end = f.window(protocol, days, number)
        overlap = max(0, (min(hi, end) - max(lo, start)).total_seconds())
        choices.append((overlap, number))
    return max(choices)[1]


def is_day(raw):
    return isinstance(raw, str) and bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw))


def validate_v2_protocol(bundle):
    if not bundle.get(V2):
        return
    p = bundle[V2]
    f.require(p['id'] == 'fixed-v2' and p['supersedes'] == 'fixed-v1', 'Unknown methodology successor')
    f.require(p['anchor'] == bundle[f.PROTOCOL]['anchor'] and p['horizons_days'] == [7, 30], 'Successor must retain the elapsed UTC schedule')
    introduced = f.instant(p['introduced_at'])
    f.require(introduced < f.instant(p['enforce_after']) < f.instant(p['active_from']), 'Invalid future methodology activation')
    f.require(p['window_convention'] == '(start, end]' and p['date_only_policy']['id'] == 'source-day-majority-v2', 'Unknown time assignment policy')
    old_ids = set(f.question_map(bundle[f.PROTOCOL]))
    f.require(not old_ids & set(f.question_map(p)), 'Changed definitions need new question IDs')
    for days in p['horizons_days']:
        transition = f.instant(p['transition'][str(days)])
        number = (transition - f.instant(p['anchor'])).total_seconds() / (days * 86400)
        f.require(number >= 1 and number.is_integer(), 'Transition must be an original window boundary')
        f.require(introduced < transition - timedelta(hours=p['issue_lead_hours']), 'Announce the transition before issuance opens')
    for q in p['questions']:
        f.require(q['version'] >= 2 and q['previous_question_id'] in old_ids, 'Missing predecessor question')
        f.require(f.instant(q['active_from']) >= f.instant(p['active_from']), 'Cannot activate successor questions in the past')
        f.require(q['timing_policy'] == p['date_only_policy'] and q['adjudication_policy'] == p['adjudication_policy'], 'Contract must freeze its time and adjudication rules')
        f.require(q['estimation_policy'] == p['estimation_policy'] and q['candidate_filter'], 'Missing estimation or candidate policy')
        f.require(q['adjudication_policy']['final_delay_days'] == 14, 'Unknown final adjudication delay')
        if q.get('subset_of'):
            f.require(q['subset_of'] in f.question_map(p), 'Unknown logical parent question')
    f.require(bundle.get(POLICY, {}).get('id') == 'evaluation-audit-v2', 'Successor needs a published review policy')


def validate_estimate(issue, checks):
    if issue['protocol'] != 'fixed-v2':
        return
    q = issue['contract']
    final = f.instant(issue['settle_after']) + timedelta(days=q['adjudication_policy']['final_delay_days'])
    f.require(f.instant(issue['final_adjudication_by']) == final, 'Final deadline differs from issued contract')
    profile = issue.get('temporal_profile', {})
    f.require(profile.get('shape') in {'constant', 'front_loaded', 'back_loaded', 'mixture', 'uncertain'} and profile.get('rationale'), 'V2 needs an explained temporal risk profile')
    f.require(issue.get('estimation_mode') in {'blind', 'informed'} and issue.get('dependence_note'), 'V2 must disclose estimation mode and dependence')
    f.require(issue.get('related_question_note'), 'V2 needs a related-question coherence explanation')
    f.require(issue['estimation_mode'] != 'informed' or issue.get('external_influence_note'), 'Informed estimate needs an influence note')
    if issue['p'] is None:
        return
    passes = issue.get('estimation_passes', [])
    policy = q['estimation_policy']
    f.require(policy['minimum_passes'] <= len(passes) <= policy['maximum_passes'], 'V2 needs three to five estimation passes')
    f.require(len({p['id'] for p in passes}) == len(passes), 'Repeated estimation pass')
    f.require(set(policy['required_approaches']) <= {p['approach'] for p in passes}, 'Missing reference-class, indicator or alternative-scenario pass')
    for p in passes:
        f.require(f.probability(p['p']) and p.get('rationale'), 'Invalid raw estimate')
        f.require(p.get('check_ids') and set(p['check_ids']) <= set(issue['check_ids']), 'Raw pass must cite actual issue checks')
        f.require(f.instant(p['completed_at']) <= f.instant(issue['source_cutoff']), 'Pass completed after source cutoff')
        f.require(all(f.instant(checks[c]['checked_at']) <= f.instant(p['completed_at']) for c in p['check_ids']), 'Pass precedes its source checks')
        if p['approach']=='reference_class':
            rate=p.get('base_rate',{})
            f.require(rate.get('status') in {'available','unavailable'} and rate.get('note'), 'Reference-class pass must disclose its base-rate evidence or its absence')
            if rate['status']=='available':
                f.require(type(rate.get('trials')) is int and type(rate.get('events')) is int and 0<=rate['events']<=rate['trials'] and rate['trials']>0 and rate.get('source_urls'), 'Invalid empirical reference-class count')
    f.require(abs(issue['p'] - median(p['p'] for p in passes)) < 1e-12, 'Issued probability must be the raw-pass median')
    f.require(issue['estimate_spread'] == [min(p['p'] for p in passes), max(p['p'] for p in passes)], 'Raw spread differs from passes')


def conservative_bounds(raw):
    """Candidate triage only: unknown timezone/date precision must not erase a case."""
    if not raw:
        return None
    try:
        at = f.instant(raw)
        return at, at
    except (ValueError, TypeError):
        period = temporal(raw)
        if not period['start']:
            return None
        lo = datetime.fromisoformat(period['start']).replace(tzinfo=timezone.utc) - timedelta(hours=14)
        hi = datetime.fromisoformat(period['end']).replace(tzinfo=timezone.utc) + timedelta(days=1, hours=14)
        return lo, hi


def available(evidence, at):
    try:
        return f.instant(evidence['discovery_time']) <= at
    except (KeyError, TypeError, ValueError):
        bounds = conservative_bounds(evidence.get('publication_time'))
        return bounds is not None and bounds[0] <= at


def candidate_universe(bundle, evidence, issue, at):
    q = issue['contract']
    config = q.get('candidate_filter') or bundle.get(POLICY, {}).get('legacy_candidate_filters', {}).get(q['id'])
    if not config:
        return {}
    start, end = f.instant(issue['window_start']), f.instant(issue['window_end'])
    known = {e['id']: e for e in evidence if available(e, at)}
    geo = bundle.get('_geography', {}).get('entries', {})
    result, linked = {}, set()
    def related(e, areas):
        domains = e.get('domain', [])
        domains = {domains} if isinstance(domains, str) else set(domains)
        text = ' '.join(str(e.get(k, '')) for k in ('title', 'summary')).casefold()
        topical = bool(domains & set(config['domains'])) or any(k.casefold() in text for k in config.get('keywords', []))
        geographic = not areas or bool(set(areas) & set(config['areas'])) or 'GLOBAL' in areas
        raw = e.get('publication_time') if q['time_basis'] == 'publication' else e.get('event_time')
        bounds = conservative_bounds(raw)
        overlaps = bounds is None or not (bounds[1] <= start or bounds[0] > end)
        return topical and geographic and overlaps
    for case in bundle['events.json']['events']:
        ids = [l['evidence_id'] for l in case['links'] if l['evidence_id'] in known]
        if case['kind'] not in {'incident', 'policy'}:
            continue
        linked.update(ids)
        relevant = [i for i in ids if related(known[i], geo.get(i, {}).get('areas', case.get('areas', [])))]
        if relevant:
            result[case['id']] = dict(id=case['id'],case_id=case['id'],title=case['title'],evidence_ids=relevant)
    for ident, e in known.items():
        if ident not in linked and related(e, geo.get(ident, {}).get('areas', e.get('areas', []))):
            key = 'evidence:' + ident
            result[key] = dict(id=key,case_id=None,title=e.get('summary', ident),evidence_ids=[ident])
    # Explicitly registered unresolved candidates cannot disappear after metadata reclassification.
    for review in bundle.get(CANDIDATES, []):
        if review['forecast_id'] == issue['id'] and f.instant(review['reviewed_at']) <= at:
            result.setdefault(review['candidate_id'], dict(id=review['candidate_id'],case_id=None,title=review['candidate_id'],evidence_ids=review['evidence_ids']))
    return result


def candidate_status(bundle, evidence, issue, at):
    candidates = candidate_universe(bundle, evidence, issue, at)
    reviews = {r['candidate_id']:r for r in bundle.get(CANDIDATES, [])
               if r['forecast_id'] == issue['id'] and f.instant(r['reviewed_at']) <= at}
    result=[]
    for key,candidate in sorted(candidates.items()):
        review=reviews.get(key)
        stale=bool(review and not set(candidate['evidence_ids'])<=set(review['evidence_ids']))
        if review and candidate.get('case_id'):
            stale=stale or any(r['event_id']==candidate['case_id'] and r['outcome']=='relevant_found'
                              and f.instant(review['reviewed_at'])<f.instant(r['checked_at'])<=at
                              for r in bundle['case-reviews.jsonl'])
        result.append({**candidate,'decision':review['decision'] if review and not stale else 'unresolved',
                       'review_id':review['id'] if review else None,'review_stale':stale})
    return result


def validate_auxiliary(bundle, evidence):
    issues = {r['id']:r for r in bundle[f.ROUNDS]}
    evid = {e['id']:e for e in evidence}
    checks = {c['id']:c for c in bundle['coverage.jsonl']}
    previous = {}
    for r in bundle.get(CANDIDATES, []):
        f.require(r['forecast_id'] in issues, 'Candidate review references unknown forecast')
        issue = issues[r['forecast_id']]
        at = f.instant(r['reviewed_at'])
        f.require(at >= f.instant(issue['issued_at']), 'Candidate review precedes issue')
        f.require(r['decision'] in {'unresolved','non_qualifying','qualifying'} and r.get('rationale'), 'Invalid candidate decision')
        f.require(r['evidence_ids'] and set(r['evidence_ids']) <= set(evid), 'Candidate decision needs evidence')
        f.require(r['check_ids'] and set(r['check_ids']) <= set(checks), 'Candidate decision needs actual checks')
        f.require(all(f.instant(checks[c]['checked_at']) <= at for c in r['check_ids']), 'Candidate decision precedes checks')
        f.require(all(available(evid[i], at) for i in r['evidence_ids']), 'Candidate decision uses later evidence')
        f.require(r.get('source_urls') and all(safe_url(u) for u in r['source_urls']), 'Candidate decision needs source URLs')
        known_ids = {e['id'] for e in bundle['events.json']['events']} | {'evidence:'+i for i in evid}
        f.require(r['candidate_id'] in known_ids, 'Unknown candidate ID')
        key = (r['forecast_id'], r['candidate_id'])
        f.require(r.get('supersedes') == previous.get(key), 'Candidate correction must reference preceding review')
        previous[key] = r['id']
        if r['decision'] == 'non_qualifying':
            allowed = set(issue['contract']['criteria']) | {'outside_window','outside_scope','not_new_disclosure'}
            f.require(r.get('failed_criteria') and set(r['failed_criteria']) <= allowed, 'Nonqualification needs a failed frozen criterion')
            if set(r['failed_criteria']) == {'outside_window'}:
                raw_key = 'publication_time' if issue['contract']['time_basis'] == 'publication' else 'event_time'
                start, end = f.instant(issue['window_start']), f.instant(issue['window_end'])
                for ident in r['evidence_ids']:
                    raw=evid[ident].get(raw_key)
                    assignment=r.get('date_assignments',{}).get(ident)
                    if issue['protocol']=='fixed-v2' and is_day(raw) and assignment:
                        zone=assignment.get('source_timezone')
                        number=assigned_day_window(protocol_for(bundle,issue['question_id']),issue['horizon_days'],raw,zone)
                        f.require(assignment==dict(policy='source-day-majority-v2',source_timezone=zone,window_number=number)
                                  and number!=issue['window_number'], 'Candidate day assignment does not exclude this window')
                    else:
                        b=conservative_bounds(raw)
                        f.require(b and (b[1] <= start or b[0] > end), 'Ambiguous boundary timing cannot be dismissed as outside the window')
    for r in bundle.get(BENCHMARKS, []):
        f.require(r['forecast_id'] in issues, 'Benchmark references unknown forecast')
        issue = issues[r['forecast_id']]
        observed, recorded = f.instant(r['observed_at']), f.instant(r['recorded_at'])
        f.require(f.instant(issue['issued_at']) <= observed <= recorded, 'External benchmark must follow own frozen issuance')
        f.require(r['status'] in {'matched','context_only','not_found'} and r.get('rationale') and r.get('provider'), 'Invalid benchmark search result/provider')
        f.require(r.get('source_urls') and all(safe_url(u) for u in r['source_urls']), 'Benchmark search needs URLs')
        if r['status'] == 'not_found':
            f.require(r.get('p') is None, 'Unmatched search is not a probability')
        else:
            f.require(f.probability(r.get('p')), 'Invalid benchmark probability')
        if r['status'] == 'matched':
            protocol = protocol_for(bundle, issue['question_id'])
            limit = timedelta(hours=protocol.get('benchmark_maximum_delay_hours',1))
            f.require(observed < f.instant(issue['window_start']) and observed-f.instant(issue['issued_at']) <= limit, 'Late external quote is context, not a contemporaneous benchmark')
            f.require(r.get('criteria_match') is True and r.get('definition_match'), 'Comparable benchmark needs explicit contract comparison')
            f.require(r.get('window_start') == issue['window_start'] and r.get('window_end') == issue['window_end'], 'External benchmark window differs')


def validate_outcome(bundle, evidence, issue, row, previous):
    at = f.instant(row['resolved_at'])
    policy = bundle.get(POLICY)
    active_guard = policy and at >= f.instant(policy['legacy_negative_guard_effective_at'])
    v2 = issue['protocol'] == 'fixed-v2'
    if v2:
        deadline = f.instant(issue['final_adjudication_by'])
        if row['outcome'] == 'unknown':
            f.require(at < deadline and f.instant(row['next_check_by']) <= deadline, 'Unknown cannot extend past the final adjudication deadline')
        if row['outcome'] == 'void':
            f.require(at >= deadline and row.get('void_reason_class') in issue['contract']['adjudication_policy']['void_reason_classes'], 'Void requires the final deadline and a reason class')
            f.require(row.get('check_ids') and row.get('coverage_basis'), 'Void must document attempted adjudication')
            checks={c['id']:c for c in bundle['coverage.jsonl']}
            f.require(any(checks[c]['scope_type']=='forecast_audit' and checks[c].get('forecast_id')==issue['id'] and f.instant(checks[c]['checked_at'])>=deadline for c in row['check_ids']), 'Void needs an actual final-deadline review')
    if row['outcome'] == 'no' and (active_guard or v2):
        candidates = candidate_status(bundle,evidence,issue,at)
        pending = sorted(c['id'] for c in candidates if c['decision'] != 'non_qualifying')
        f.require(row.get('open_claim_ids') == pending, 'Declared open claims differ from candidate/event evidence')
        f.require(not pending, 'Open or qualifying candidate blocks no')
        decisions = row.get('non_qualifying_evidence', {})
        checks = {c['id']:c for c in bundle['coverage.jsonl']}
        reviewed_evidence = set()
        for c in row['check_ids']:
            if checks[c]['outcome'] == 'relevant_found':
                reviewed_evidence.update(checks[c]['evidence_ids'])
        f.require(reviewed_evidence <= set(decisions), 'Relevant closure evidence needs explicit nonqualification')
        allowed = set(issue['contract']['criteria']) | {'outside_window','outside_scope','not_new_disclosure'}
        for ident, decision in decisions.items():
            f.require(ident in row['evidence_ids'] and decision.get('rationale') and decision.get('failed_criteria') and set(decision['failed_criteria']) <= allowed, 'Invalid closure evidence exclusion')
    if previous and previous['outcome'] in {'yes','no'} and row['outcome'] in {'yes','no'} and previous['outcome'] != row['outcome'] and (active_guard or v2):
        f.require(row.get('correction_reason_class') in policy['correction_classes'] and row.get('correction_note'), 'Definitive outcome flip needs a classified correction reason')


def validate_v2_time(bundle, evidence, issue, row, raw, lo, hi):
    protocol = protocol_for(bundle,issue['question_id'])
    if is_day(raw):
        zone = row.get('qualifying_timezone')
        number = assigned_day_window(protocol,issue['horizon_days'],raw,zone)
        f.require(row.get('date_assignment') == {'policy':'source-day-majority-v2','window_number':number,'source_timezone':zone}, 'Date-only decision must disclose its assignment convention')
        f.require(number == issue['window_number'] and hi <= f.instant(row['resolved_at']), 'Source day belongs to another window or is not complete')
    else:
        f.require(f.instant(issue['window_start']) < lo <= hi <= f.instant(issue['window_end']) and hi <= f.instant(row['resolved_at']), 'Precise event lies outside the window')
    publication=issue['contract']['time_basis']=='publication'
    evid = {e['id']:e for e in evidence}
    criterion='first_qualifying_publication' if publication else 'new_occurrence'
    field='publication_time' if publication else 'event_time'
    anchors = [evid[i] for i in row['criterion_evidence'][criterion]]
    precise = []
    for e in anchors:
        try: precise.append(f.instant(e.get(field)))
        except (ValueError, TypeError): pass
    f.require(not is_day(raw) or not precise, 'Cannot discard a known precise event/publication timestamp')
    if is_day(raw):
        f.require(any(e.get(field)==raw for e in anchors), 'Source date is not supported by its primary anchor')
    else:
        f.require(f.instant(raw) in precise, 'Precise time is not supported by its primary anchor')
    if publication:
        event_bounds = conservative_bounds(row.get('event_time'))
        f.require(not event_bounds or event_bounds[0] <= hi, 'Disclosure cannot attest a future incident')


def coherence(issues):
    warnings = []
    groups = defaultdict(dict)
    for issue in issues:
        if issue['p'] is not None:
            groups[(issue['protocol'],issue['question_id'],issue['window_start'],issue['source_cutoff'])][issue['horizon_days']] = issue
    for key, pair in groups.items():
        if {7,30} <= pair.keys():
            short, long = pair[7],pair[30]
            implied = 1-(1-short['p'])**(30/7)
            warnings.append(dict(kind='constant_hazard_diagnostic',question_id=key[1],p7=short['p'],p30=long['p'],constant_hazard_p30=implied,
                                 difference=long['p']-implied,requires_explanation=abs(long['p']-implied)>.15,
                                 explanation=long.get('temporal_profile',{}).get('rationale'),not_a_logical_contradiction=True))
    return warnings


def validate_relations(issues):
    lookup={(r['question_id'],r['horizon_days'],r['window_start'],r['source_cutoff']):r for r in issues if r['p'] is not None}
    for r in issues:
        parent=r['contract'].get('subset_of')
        if parent and r['p'] is not None:
            key=(parent,r['horizon_days'],r['window_start'],r['source_cutoff'])
            if key in lookup:
                f.require(r['p'] <= lookup[key]['p'], 'Subset probability exceeds its logical parent')
    for warning in coherence(issues):
        if warning['requires_explanation'] and warning['question_id'].endswith('-v2'):
            f.require(warning['explanation'], 'Temporal-profile diagnostic needs a written explanation')


RELATED = {
    'eu-sabotage-disclosure': ['significant_hybrid_proxy_operation_eu', 'physical_sabotage_proxy_attempt_eu'],
    'cze-sabotage-disclosure': ['significant_russian_linked_hybrid_operation_czechia'],
    'nato-armed-attack': ['limited_deliberate_nato_test', 'larger_conventional_attack_on_nato', 'open_russia_nato_war'],
    'baltic-armed-attack': ['baltic_limited_test'],
    'rus-mobilisation-order': ['significant_russian_mobilization'],
    'belarus-combat-entry': ['belarus_direct_entry_into_war'],
    'nuclear-demonstration': ['nuclear_demonstration'],
    'nuclear-use': ['nuclear_use'],
}


def related_context(bundle, at):
    """Show original long definitions available at the cutoff, without assuming subsets."""
    latest = {}
    for r in bundle['forecast-register.jsonl']:
        if f.instant(r['forecast_time']) <= at and f.instant(r['registered_at']) <= at:
            if r['question'] not in latest or f.instant(r['forecast_time']) > f.instant(latest[r['question']]['forecast_time']):
                latest[r['question']] = r
    return {stem: [r for k,r in latest.items() if k.split('_by_')[0] in keys] for stem,keys in RELATED.items()}


def related_comparisons(bundle, at):
    result=[]
    for issue in bundle[f.ROUNDS]:
        if f.instant(issue['issued_at']) > at:
            continue
        stem=issue['question_id'].rsplit('-v',1)[0]
        for long in related_context(bundle,f.instant(issue['source_cutoff'])).get(stem,[]):
            result.append(dict(forecast_id=issue['id'],question_id=issue['question_id'],p=issue['p'],
                               window_start=issue['window_start'],window_end=issue['window_end'],
                               long_forecast_id=long['id'],long_p=long['p'],long_definition=long['definition'],
                               long_window_start=long['window_start'],long_window_end=long['window_end'],
                               long_as_of=long['forecast_time'],explanation=issue.get('related_question_note'),
                               comparison_type='related_definitions_not_assumed_nested'))
    return result


def benchmark_scores(bundle, rows, at):
    """First eligible quote per provider/forecast; same matured resolved cases on both sides."""
    quotes={}
    for r in bundle.get(BENCHMARKS,[]):
        if r['status']=='matched' and f.instant(r['recorded_at'])<=at:
            key=(r['provider'],r['forecast_id'])
            if key not in quotes or f.instant(r['observed_at'])<f.instant(quotes[key]['observed_at']):
                quotes[key]=r
    groups=defaultdict(list)
    for row in rows:
        if not row['primary_score'] or row['brier'] is None or at<f.instant(row['cohort_ready_after']):
            continue
        for (provider,ident),quote in quotes.items():
            if ident==row['id']:
                y=int(row['status']=='yes')
                groups[(row['protocol'],row['horizon_days'],provider)].append((row,quote,(quote['p']-y)**2))
    return [dict(protocol=p,horizon_days=days,provider=provider,n=len(values),
                 own_brier=sum(row['brier'] for row,_,_ in values)/len(values),
                 external_brier=sum(loss for _,_,loss in values)/len(values),
                 forecast_ids=[row['id'] for row,_,_ in values],quote_ids=[q['id'] for _,q,_ in values])
            for (p,days,provider),values in sorted(groups.items())]


def score_diagnostics(selected, at):
    mature=[r for r in selected if at >= f.instant(r['cohort_ready_after'])]
    numeric=[r for r in mature if r['issued_at'] is not None and r['p'] is not None]
    definitive=[r for r in numeric if r['status'] in {'yes','no'}]
    unresolved=[r for r in numeric if r['status'] not in {'yes','no'}]
    abstained=[r for r in mature if r['status']=='abstained']
    observed=sum(r['brier'] for r in definitive)
    def mean(total,n):return total/n if n else None
    def scenario(choose):
        losses=[]; references=[]
        for r in numeric:
            if r['status'] in {'yes','no'}:y=int(r['status']=='yes')
            elif choose=='all_yes':y=1
            elif choose=='all_no':y=0
            elif choose=='best':y=int(r['p']>.5)
            else:y=int(r['p']<.5)
            losses.append((r['p']-y)**2);references.append(y*y)
        return dict(n=len(numeric),brier=mean(sum(losses),len(losses)),always_no_brier=mean(sum(references),len(references)))
    scenarios={k:scenario(k) for k in ['best','worst','all_yes','all_no']}
    n=len(numeric)+len(abstained)
    abstention={k:mean((v['brier'] or 0)*len(numeric)+.25*len(abstained),n) for k,v in scenarios.items()}
    return dict(matured_planned=len(mature),matured_numeric=len(numeric),matured_resolved=len(definitive),matured_unresolved=len(unresolved),
                matured_brier=mean(observed,len(definitive)),matured_always_no_brier=mean(sum(r['always_no_brier'] for r in definitive),len(definitive)),
                resolution_fraction=mean(len(definitive),len(numeric)),sensitivity=scenarios,
                abstention_sensitivity=dict(n=n,abstentions=len(abstained),assumed_probability=.5,brier=abstention),
                dependency_groups=len({r['dependency_group'] for r in selected if r['brier'] is not None}),
                distinct_windows=len({r['window_start'] for r in selected if r['brier'] is not None}),
                planned_dependency_groups=len({r['dependency_group'] for r in selected}),
                planned_distinct_windows=len({r['window_start'] for r in selected}),
                effective_sample_size=None,dependence_note='Počet skupin není počet prokázaně nezávislých pozorování. Efektivní velikost vzorku se neodhaduje.',
                sensitivity_note='Pouze dospělé kohorty; meze se počítají po jednotlivých nevyřešených odhadech. Jde o citlivost, ne dodatečně zjištěné výsledky. Chybějící vydání nejsou předpovědi nuly.')


def conditional_time_probability(prior, previous_as_of, now, end):
    previous_as_of,now,end=map(f.instant,(previous_as_of,now,end))
    f.require(f.probability(prior) and prior<1 and previous_as_of<=now<=end and previous_as_of<end, 'Invalid conditional survival model inputs')
    return 1-(1-prior)**((end-now).total_seconds()/(end-previous_as_of).total_seconds())


def long_review(bundle,evidence,state,at):
    """Candidates are leads to adjudicate against each original definition, never automatic yes."""
    mapping={'significant_hybrid_proxy_operation_eu':'eu-sabotage-disclosure','physical_sabotage_proxy_attempt_eu':'eu-sabotage-disclosure',
             'limited_deliberate_nato_test':'nato-armed-attack','baltic_limited_test':'baltic-armed-attack',
             'larger_conventional_attack_on_nato':'nato-armed-attack','open_russia_nato_war':'nato-armed-attack',
             'significant_russian_mobilization':'rus-mobilisation-order','belarus_direct_entry_into_war':'belarus-combat-entry',
             'nuclear_posture_change':'nuclear-demonstration','nuclear_demonstration':'nuclear-demonstration','nuclear_use':'nuclear-use',
             'significant_russian_linked_hybrid_operation_czechia':'cze-sabotage-disclosure'}
    result={}
    for key,h in state['hypotheses'].items():
        if h.get('status','active')!='active':continue
        stem=key.split('_by_')[0]
        filt=bundle.get(POLICY,{}).get('legacy_candidate_filters',{}).get(mapping.get(stem,'')+'-v1')
        if not filt:continue
        filt={k:list(v) for k,v in filt.items()}
        if 'hybrid' in stem:filt['domains']+=['cyber','hybrid_proxy_eu','eu_hybrid','czechia']
        proxy=dict(id='legacy:'+key,contract=dict(id='legacy:'+key,time_basis='occurrence',candidate_filter=filt),
                   window_start=h.get('forecast_window_start',state['forecast_window_start']),window_end=h.get('forecast_window_end',state['forecast_window_end']))
        candidates=candidate_universe(bundle,evidence,proxy,at)
        previous=[r for r in bundle['forecast-register.jsonl'] if r['question']==key and r['definition']==h['event_definition'] and f.instant(r['forecast_time'])<at]
        last=max(previous,key=lambda r:f.instant(r['forecast_time'])) if previous else None
        eligible=[r for r in previous if r['eligible']]
        first=min(eligible,key=lambda r:(f.instant(r['forecast_time']),r['id'])) if eligible else None
        result[key]=dict(definition=h['event_definition'],candidates=list(candidates.values()),
                         adjudication_forecast_id=first['id'] if first else None,
                         template=dict(prior_p=last['p'] if last else h['p'],previous_as_of=last['forecast_time'] if last else h.get('assessment_time'),
                                       as_of=at.isoformat(),time_model='not_applied',delta_time_pp=0,delta_evidence_pp=0,
                                       time_rationale='',evidence_rationale='',no_qualifying_event_confirmed=False,check_ids=[]),
                         candidate_audit=[dict(candidate_id=c['id'],decision='unresolved',rationale='',failed_criterion='',missing_evidence='',evidence_ids=c['evidence_ids']) for c in candidates.values()])
    return result


def validate_long_updates(bundle,evidence,state):
    policy=bundle.get(POLICY)
    if not policy or f.instant(state['assessment_time'])<f.instant(policy['long_update_effective_at']):return
    reviews=long_review(bundle,evidence,state,f.instant(state['assessment_time']))
    active={k.split('_by_')[0]:h for k,h in state['hypotheses'].items() if h.get('status','active')=='active'}
    war=active.get('open_russia_nato_war');attack=active.get('larger_conventional_attack_on_nato')
    if war and attack and war['p']>attack['p']:
        f.require(war.get('coherence_note'), 'War above larger-attack probability needs an explicit definition-based explanation')
    for key,h in state['hypotheses'].items():
        if h.get('status','active')!='active':continue
        d=h.get('revision_decomposition',{})
        f.require(d.get('time_model') in {'not_applied','constant_hazard_conditional_survival'} and d.get('time_rationale') and d.get('evidence_rationale'), 'Long revisions need time/evidence decomposition and rationales')
        f.require(d.get('prior_p')==h['prior'] and f.instant(d.get('as_of'))==f.instant(state['assessment_time']), 'Long decomposition differs from prior or assessment')
        if key in reviews:
            expected=reviews[key]['template']
            f.require(d['prior_p']==expected['prior_p'] and f.instant(d['previous_as_of'])==f.instant(expected['previous_as_of']), 'Long update must use the latest saved prior')
            audit=h.get('candidate_audit',[])
            required={c['id'] for c in reviews[key]['candidates']}
            f.require(required <= {c['candidate_id'] for c in audit}, 'Long forecast candidates require explicit review against the original definition')
            for c in audit:
                f.require(c['decision'] in {'unresolved','non_qualifying'} and c.get('rationale') and c.get('evidence_ids'), 'An active long forecast cannot ignore a qualifying candidate')
                detail='failed_criterion' if c['decision']=='non_qualifying' else 'missing_evidence'
                f.require(c.get(detail), 'Long candidate review must name its failed criterion or missing evidence')
                f.require(set(c['evidence_ids']) <= {e['id'] for e in evidence}, 'Unknown evidence in long candidate review')
        f.require(all(isinstance(d.get(k),(int,float)) and not isinstance(d[k],bool) and math.isfinite(d[k]) for k in ['delta_time_pp','delta_evidence_pp']), 'Invalid long probability components')
        f.require(abs(h['p']-(h['prior']+(d['delta_time_pp']+d['delta_evidence_pp'])/100))<1e-9, 'Time and evidence changes do not reproduce probability')
        if d['time_model']=='not_applied':f.require(d['delta_time_pp']==0, 'Unapplied time model has a nonzero delta')
        else:
            f.require(d.get('no_qualifying_event_confirmed') is True and d.get('check_ids'), 'Survival update needs an observable, checked absence')
            f.require(d.get('observability')=='high' and all(c['decision']=='non_qualifying' for c in h.get('candidate_audit',[])), 'Unresolved candidates or low observability preclude survival conditioning')
            checks={c['id']:c for c in bundle['coverage.jsonl']}
            f.require(set(d['check_ids'])<=set(checks) and all(checks[c]['outcome'] in {'relevant_found','no_new_relevant'} for c in d['check_ids']), 'Partial coverage cannot establish survival conditioning')
            f.require(all(f.instant(d['previous_as_of'])<=f.instant(checks[c]['checked_at'])<=f.instant(d['as_of']) for c in d['check_ids']), 'Survival conditioning needs current checks')
            value=conditional_time_probability(h['prior'],d['previous_as_of'],d['as_of'],h['forecast_window_end'])
            f.require(abs(d['delta_time_pp']-100*(value-h['prior']))<1e-8, 'Time component does not match declared hazard model')
