"""Regression tests for the audit findings, using labelled disposable forecasts only."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import build_site
import forecasting as f
import forecast_methods as fm
import monitoring as m
import publish_update
import test_forecasting as legacy_tests


class MethodologyV2Tests(unittest.TestCase):
    def setUp(self):
        self.base=legacy_tests.FixedForecastTests('test_late_or_backdated_issue_cannot_become_a_prospective_forecast')
        self.base.setUp()
        self.bundle=self.base.bundle;self.evidence=self.base.evidence
        self.protocol=self.bundle[fm.V2]
        self.start=f.window(self.protocol,7,1)[0]
        self.base.start=self.start

    def validate(self):
        return m.validate(self.bundle,self.evidence,self.base.state)

    def issue(self,q='eu-sabotage-disclosure-v2',days=7,number=1,p=.2):
        start,_=f.window(self.protocol,days,number)
        at=start-timedelta(hours=1);cutoff=at-timedelta(minutes=1)
        cid=self.base.check(cutoff-timedelta(minutes=1),['wire-reuters'],cutoff.date().isoformat(),cutoff.date().isoformat())
        raw=dict(question_id=q,horizon_days=days,window_number=number,p=p,source_cutoff=cutoff.isoformat(),
                 rationale='TEST researched judgment',alternative='TEST alternative',evidence_ids=[],check_ids=[cid],source_urls=['https://example.com/TEST'],
                 estimation_mode='blind',dependence_note='TEST approaches share a model and source data; statistical independence is not claimed.',
                 related_question_note='TEST long definitions and periods differ; no mechanical conversion is claimed.',
                 temporal_profile=dict(shape='uncertain',rationale='TEST no constant hazard assumption'),estimation_passes=[])
        if p is None:raw['abstention_reason']='TEST insufficient evidence'
        else:
            for i,approach in enumerate(['reference_class','indicators','alternative_scenario']):
                value=max(0,min(1,p+(i-1)*.05))
                raw['estimation_passes'].append(dict(id='TEST-'+approach,approach=approach,p=value,rationale='TEST independent line of reasoning, not independent data',
                    completed_at=cutoff.isoformat(),check_ids=[cid],**({'base_rate':dict(status='unavailable',note='TEST no measured reference-class sample')} if i==0 else {})))
        issue=f.make_issue(self.protocol,raw,at)
        self.bundle[f.ROUNDS].append(issue)
        return issue

    def outcome(self,issue,result='no'):
        self.base.start=f.instant(issue['window_start'])
        return self.base.outcome(issue,result)

    def case(self,issue,day=1):
        when=f.instant(issue['window_start'])+timedelta(days=day)
        ident='TEST-new-case-evidence'
        e={**self.evidence[0], 'id':ident,'event_time':when.isoformat(),'publication_time':when.isoformat(),
           'discovery_time':when.isoformat(),'domain':['physical_sabotage'],'summary':'TEST sabotage claim',
           'source_url':'https://example.com/TEST/new-case','source_tier':1,'independent_source_line':'TEST-new-primary'}
        self.evidence.append(e)
        case=copy.deepcopy(self.bundle['events.json']['events'][0])
        case.update(id='TEST-open-case',title='TEST unresolved physical sabotage',kind='incident',areas=['POL'],case_status='open',
                    next_check_by=(when+timedelta(days=1)).isoformat(),next_action='TEST followup',
                    links=[dict(evidence_id=ident,line_id='TEST-new-primary',claim='TEST',role='first_report',independence_basis='TEST')])
        self.bundle['events.json']['events'].append(case)
        return case,e

    def date_outcome(self,issue,day,zone='Europe/Prague'):
        row=self.outcome(issue,'yes')
        raw_key='publication_time' if issue['contract']['time_basis']=='publication' else 'event_time'
        row[raw_key]=day;row['qualifying_timezone']=zone
        lo,hi=f.timing_bounds(day,zone)
        row.update(qualifying_time_start=lo.isoformat(),qualifying_time_end=hi.isoformat(),
                   date_assignment=dict(policy='source-day-majority-v2',window_number=fm.assigned_day_window(self.protocol,issue['horizon_days'],day,zone),source_timezone=zone))
        for e in self.evidence:
            if e['id'] in row['evidence_ids']:e[raw_key]=day
        if raw_key=='publication_time':
            row['event_time']=(lo-timedelta(days=2)).isoformat()
        return row

    def test_next_windows_use_v2_without_overlapping_or_replacing_v1(self):
        at=f.instant('2026-11-07T06:00:00Z')
        slots=list(fm.planned_slots(self.bundle,at))
        self.assertEqual({s['protocol'] for s in slots if s['window_start']=='2026-11-07T07:00:00+00:00'}, {'fixed-v2'})
        self.assertEqual(f.window(self.bundle[f.PROTOCOL],7,0)[1],f.window(self.protocol,7,1)[0])
        self.assertEqual(f.window(self.bundle[f.PROTOCOL],30,0)[1],f.window(self.protocol,30,1)[0])
        current=m.load(build_site.DATA)
        issued=copy.deepcopy(current[f.ROUNDS]);outcomes=copy.deepcopy(current[f.OUTCOMES])
        f.evaluate(current,f.instant(self.protocol['introduced_at']))
        self.assertEqual(current[f.ROUNDS],issued);self.assertEqual(current[f.OUTCOMES],outcomes)

    def test_historical_queue_is_unchanged_before_v2_announcement(self):
        current=m.load(build_site.DATA)
        old=json.loads((build_site.DATA/'state.json').read_text())
        expected=old['research_scope']['fixed_forecast_review']
        self.assertEqual(f.assessment_scope(current,f.instant(expected['reviewed_at'])),expected)

    def test_v2_boundary_day_qualifies_without_inventing_an_hour(self):
        issue=self.issue(q='nato-armed-attack-v2')
        row=self.date_outcome(issue,'2026-11-07')
        self.validate()
        self.assertLess(f.instant(row['qualifying_time_start']),f.instant(issue['window_start']))
        self.assertEqual(row['event_time'],'2026-11-07')

    def test_source_day_is_assigned_to_exactly_one_adjacent_window(self):
        for days,day in [(7,'2026-11-07'),(30,'2026-11-30')]:
            for zone in ['Europe/Prague','Europe/Kyiv','UTC','Asia/Karachi','Asia/Tokyo']:
                number=fm.assigned_day_window(self.protocol,days,day,zone)
                self.assertEqual(sum(n==number for n in [0,1,2]),1)
                self.assertEqual(number,0 if zone=='Asia/Tokyo' else 1)

    def test_exact_tie_goes_to_later_window(self):
        self.assertEqual(fm.assigned_day_window(self.protocol,7,'2026-11-07','Asia/Karachi'),1)

    def test_source_calendar_day_keeps_dst_uncertainty(self):
        lo,hi=f.timing_bounds('2027-03-28','Europe/Prague')
        self.assertEqual((hi-lo).total_seconds()+.000001,23*3600)
        number=fm.assigned_day_window(self.protocol,7,'2027-03-28','Europe/Prague')
        self.assertIsInstance(number,int)

    def test_wrong_day_assignment_cannot_be_used_to_score_yes(self):
        issue=self.issue(q='nato-armed-attack-v2')
        self.date_outcome(issue,'2026-11-14')
        with self.assertRaisesRegex(ValueError,'another window'):self.validate()

    def test_known_precise_publication_time_cannot_be_discarded(self):
        issue=self.issue()
        row=self.date_outcome(issue,'2026-11-07')
        anchor=next(e for e in self.evidence if e['id']==row['criterion_evidence']['first_qualifying_publication'][0])
        anchor['publication_time']='2026-11-07T06:00:00Z'
        with self.assertRaisesRegex(ValueError,'discard a known precise'):self.validate()

    def test_known_precise_occurrence_time_cannot_be_discarded(self):
        issue=self.issue(q='nato-armed-attack-v2')
        row=self.date_outcome(issue,'2026-11-07')
        anchor=next(e for e in self.evidence if e['id']==row['criterion_evidence']['new_occurrence'][0])
        anchor['event_time']='2026-11-07T06:00:00Z'
        with self.assertRaisesRegex(ValueError,'discard a known precise'):self.validate()

    def test_unknown_cannot_be_extended_beyond_issued_final_deadline(self):
        issue=self.issue();row=self.outcome(issue,'unknown')
        row['next_check_by']=(f.instant(issue['final_adjudication_by'])+timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'past the final'):self.validate()

    def test_void_is_terminal_but_not_a_negative_result(self):
        issue=self.issue();row=self.outcome(issue,'unknown')
        row.update(outcome='void',resolved_at=issue['final_adjudication_by'],void_reason_class='source_unavailable')
        at=f.instant(issue['final_adjudication_by'])
        row['check_ids']=[self.base.check(at,['wire-reuters'],issue['window_start'][:10],issue['window_end'][:10],forecast_id=issue['id'],outcome='unavailable')]
        self.validate()
        data=f.evaluate(self.bundle,f.instant(row['resolved_at']))
        s=next(s for s in data['summaries'] if s['protocol']=='fixed-v2' and s['horizon_days']==7)
        self.assertEqual(s['counts']['void'],1);self.assertEqual(s['scored'],0)
        self.assertEqual(s['matured_unresolved'],1)
        self.assertAlmostEqual(s['sensitivity']['worst']['brier'],.64)

    def test_void_cannot_be_used_to_avoid_an_early_difficult_outcome(self):
        issue=self.issue();row=self.outcome(issue,'unknown')
        row.update(outcome='void',void_reason_class='source_unavailable')
        with self.assertRaisesRegex(ValueError,'Void requires'):self.validate()

    def test_overdue_unknown_is_visible_and_final_review_is_queued(self):
        issue=self.issue();row=self.outcome(issue,'unknown')
        row['next_check_by']=issue['final_adjudication_by']
        at=f.instant(issue['final_adjudication_by'])+timedelta(days=1)
        self.validate()
        selected=next(r for r in f.evaluate(self.bundle,at)['rows'] if r['id']==issue['id'])
        self.assertEqual(selected['status'],'awaiting_final_resolution')
        self.assertTrue(any(t.get('forecast_id')==issue['id'] and t.get('must_finalize') for t in f.tasks(self.bundle,at)))

    def test_empty_declared_list_cannot_hide_an_open_case(self):
        issue=self.issue();case,_=self.case(issue)
        self.outcome(issue)
        self.bundle[fm.CANDIDATES]=[r for r in self.bundle[fm.CANDIDATES] if r['candidate_id']!=case['id']]
        with self.assertRaisesRegex(ValueError,'open claims differ'):self.validate()

    def test_generic_closed_case_still_needs_forecast_specific_screening(self):
        issue=self.issue();case,_=self.case(issue);case['case_status']='closed'
        self.outcome(issue)
        self.bundle[fm.CANDIDATES]=[r for r in self.bundle[fm.CANDIDATES] if r['candidate_id']!=case['id']]
        with self.assertRaisesRegex(ValueError,'open claims differ'):self.validate()

    def test_later_evidence_invalidates_a_stale_nonqualification(self):
        issue=self.issue();case,evidence=self.case(issue)
        row=self.outcome(issue)
        at=f.instant(row['resolved_at'])
        later={**evidence,'id':'TEST-later-case-evidence','discovery_time':(at+timedelta(minutes=1)).isoformat()}
        self.evidence.append(later)
        case['links'].append({**case['links'][0],'evidence_id':later['id']})
        row['resolved_at']=(at+timedelta(minutes=2)).isoformat()
        selected=next(c for c in fm.candidate_status(self.bundle,self.evidence,issue,f.instant(row['resolved_at'])) if c['id']==case['id'])
        self.assertTrue(selected['review_stale']);self.assertEqual(selected['decision'],'unresolved')
        with self.assertRaisesRegex(ValueError,'open claims differ'):self.validate()

    def test_boundary_ambiguity_cannot_be_cleared_as_outside_window(self):
        issue=self.issue();case,evidence=self.case(issue)
        evidence['publication_time']='2026-11-07'
        self.outcome(issue)
        review=next(r for r in self.bundle[fm.CANDIDATES] if r['candidate_id']==case['id'])
        review['failed_criteria']=['outside_window']
        with self.assertRaisesRegex(ValueError,'Ambiguous boundary'):self.validate()

    def test_relevant_closure_item_requires_explicit_nonqualification(self):
        issue=self.issue();row=self.outcome(issue)
        check=next(c for c in self.bundle['coverage.jsonl'] if c['id']==row['check_ids'][0])
        ident=self.evidence[0]['id'];check.update(outcome='relevant_found',evidence_ids=[ident]);row['evidence_ids']=[ident]
        with self.assertRaisesRegex(ValueError,'explicit nonqualification'):self.validate()
        row['non_qualifying_evidence']={ident:dict(failed_criteria=['outside_scope'],rationale='TEST old unrelated evidence')}
        self.validate()

    def test_median_and_raw_spread_are_enforced(self):
        issue=self.issue();issue['p']=.25
        with self.assertRaisesRegex(ValueError,'raw-pass median'):self.validate()
        issue['p']=.2;issue['estimate_spread']=[0,1]
        with self.assertRaisesRegex(ValueError,'Raw spread'):self.validate()

    def test_three_different_approaches_and_base_rate_note_are_required(self):
        issue=self.issue();issue['estimation_passes'].pop()
        with self.assertRaisesRegex(ValueError,'three to five'):self.validate()
        self.bundle[f.ROUNDS]=[];issue=self.issue();del issue['estimation_passes'][0]['base_rate']
        with self.assertRaisesRegex(ValueError,'base-rate evidence'):self.validate()

    def test_logical_subset_cannot_exceed_parent(self):
        self.issue(q='nato-armed-attack-v2',p=.1);self.issue(q='baltic-armed-attack-v2',p=.2)
        with self.assertRaisesRegex(ValueError,'logical parent'):self.validate()

    def test_constant_hazard_diagnostic_does_not_force_constant_hazard(self):
        # A valid pair with the same start, shown directly to the coherence diagnostic.
        a=self.issue(q='ukraine-grid-emergency-v2',p=.55)
        b=copy.deepcopy(a);b.update(horizon_days=30,p=.8)
        result=fm.coherence([a,b])[0]
        self.assertTrue(result['requires_explanation']);self.assertTrue(result['not_a_logical_contradiction'])
        fm.validate_relations([a,b])

    def test_early_yes_does_not_create_a_matured_headline(self):
        issue=self.issue();row=self.outcome(issue,'yes')
        self.validate()
        data=f.evaluate(self.bundle,f.instant(row['resolved_at']))
        s=next(s for s in data['summaries'] if s['protocol']=='fixed-v2' and s['horizon_days']==7)
        self.assertEqual(s['scored'],1);self.assertEqual(s['matured_resolved'],0)
        self.assertIsNotNone(s['brier']);self.assertIsNone(s['matured_brier'])

    def test_missing_outcome_bounds_are_per_contract_not_two_uniform_imputations(self):
        at=f.instant('2026-12-01T10:00:00Z')
        rows=[dict(protocol='TEST',horizon_days=7,window_start='2026-11-01T00:00:00Z',cohort_ready_after='2026-11-20T00:00:00Z',
                   dependency_group='TEST-dependent',status='unknown',issued_at='2026-10-31T00:00:00Z',p=p,brier=None,always_no_brier=None) for p in [.01,.8]]
        d=fm.score_diagnostics(rows,at)
        self.assertAlmostEqual(d['sensitivity']['worst']['brier'],.81005)
        self.assertGreater(d['sensitivity']['worst']['brier'],d['sensitivity']['all_yes']['brier'])
        self.assertGreater(d['sensitivity']['worst']['brier'],d['sensitivity']['all_no']['brier'])
        self.assertAlmostEqual(d['sensitivity']['best']['brier'],.02005)
        self.assertEqual(d['planned_dependency_groups'],1);self.assertEqual(d['dependency_groups'],0)
        self.assertIsNone(d['effective_sample_size'])

    def test_abstention_sensitivity_uses_half_without_rewriting_primary_score(self):
        issue=self.issue(p=None)
        at=f.instant(issue['settle_after'])+timedelta(days=20)
        self.validate()
        s=next(s for s in f.evaluate(self.bundle,at)['summaries'] if s['protocol']=='fixed-v2' and s['horizon_days']==7)
        self.assertIsNone(s['brier'])
        self.assertEqual(s['abstention_sensitivity']['abstentions'],1)
        self.assertAlmostEqual(s['abstention_sensitivity']['brier']['worst'],.25)

    def benchmark(self,issue,offset=10):
        at=f.instant(issue['issued_at'])+timedelta(minutes=offset)
        row=dict(id='TEST-market',forecast_id=issue['id'],observed_at=at.isoformat(),recorded_at=at.isoformat(),
                 status='matched',provider='TEST market',p=.3,criteria_match=True,definition_match='TEST exact criteria comparison',
                 window_start=issue['window_start'],window_end=issue['window_end'],rationale='TEST quote after own freeze',source_urls=['https://example.com/TEST/market'])
        self.bundle[fm.BENCHMARKS].append(row)
        return row

    def test_external_quote_follows_own_freeze_and_matches_exact_window(self):
        issue=self.issue();b=self.benchmark(issue)
        self.validate()
        self.assertEqual(f.as_of(self.bundle,self.base.state),b['recorded_at'])
        b['observed_at']=(f.instant(issue['issued_at'])-timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'follow own frozen'):self.validate()
        b['observed_at']=b['recorded_at'];b['window_end']=issue['window_start']
        with self.assertRaisesRegex(ValueError,'window differs'):self.validate()

    def test_late_or_differently_defined_market_is_context_only(self):
        issue=self.issue();b=self.benchmark(issue,offset=90)
        with self.assertRaisesRegex(ValueError,'Late external quote'):self.validate()
        b['status']='context_only';self.validate()

    def test_external_score_uses_same_matured_subset_and_first_quote(self):
        issue=self.issue();self.benchmark(issue)
        later=copy.deepcopy(self.bundle[fm.BENCHMARKS][0])
        later.update(id='TEST-later-quote',observed_at=(f.instant(later['observed_at'])+timedelta(minutes=5)).isoformat(),
                     recorded_at=(f.instant(later['recorded_at'])+timedelta(minutes=5)).isoformat(),p=.9)
        self.bundle[fm.BENCHMARKS].append(later)
        row=self.outcome(issue,'yes');self.validate()
        self.assertEqual(f.evaluate(self.bundle,f.instant(row['resolved_at']))['external_comparisons'],[])
        at=f.instant(issue['settle_after'])+timedelta(days=8)
        score=f.evaluate(self.bundle,at)['external_comparisons'][0]
        self.assertEqual(score['n'],1);self.assertAlmostEqual(score['own_brier'],.64)
        self.assertAlmostEqual(score['external_brier'],.49)

    def test_v2_date_only_exclusion_needs_source_day_assignment(self):
        issue=self.issue();case,evidence=self.case(issue)
        evidence['publication_time']='2026-11-07'
        self.outcome(issue)
        review=next(r for r in self.bundle[fm.CANDIDATES] if r['candidate_id']==case['id'])
        review['failed_criteria']=['outside_window']
        review['date_assignments']={evidence['id']:dict(policy='source-day-majority-v2',source_timezone='Asia/Tokyo',window_number=0)}
        self.validate()
        review['date_assignments'][evidence['id']]['source_timezone']='Europe/Prague'
        with self.assertRaisesRegex(ValueError,'does not exclude'):self.validate()

    def test_definitive_flip_requires_reason_and_uses_as_of_evidence(self):
        issue=self.issue();first=self.outcome(issue)
        second=self.outcome(issue,'yes')
        second.update(supersedes=first['id'],resolved_at=(f.instant(first['resolved_at'])+timedelta(hours=2)).isoformat())
        for e in self.evidence:
            if e['id'] in second['evidence_ids']:
                e['discovery_time']=(f.instant(first['resolved_at'])+timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'classified correction reason'):self.validate()
        second.update(correction_reason_class='new_evidence',correction_note='TEST primary source discovered after the first decision')
        self.validate()
        data=f.evaluate(self.bundle,f.instant(second['resolved_at']))
        self.assertEqual(len(data['corrections']),1)

    def new_long_state(self):
        state=json.loads((build_site.DATA/'state.json').read_text())
        state['assessment_time']='2026-11-05T07:30:00+01:00'
        review=fm.long_review(self.bundle,self.evidence,state,f.instant(state['assessment_time']))
        for key,r in review.items():
            h=state['hypotheses'][key];h['prior']=r['template']['prior_p']
            h['coherence_note']='TEST war can develop through sustained escalation from limited incidents; larger conventional attack is a different event.'
            h['revision_decomposition']={**r['template'],'time_rationale':'TEST absence not sufficiently observable for a hazard model','evidence_rationale':'TEST evidence does not justify a delta'}
            h['candidate_audit']=[{**c,'rationale':'TEST pending criterion evidence remains unresolved','missing_evidence':'TEST attribution or intent evidence remains missing'} for c in r['candidate_audit']]
        return state

    def test_future_long_revisions_require_decomposition_but_no_forced_decay(self):
        state=self.new_long_state()
        fm.validate_long_updates(self.bundle,self.evidence,state)
        key=next(k for k,h in state['hypotheses'].items() if h.get('status','active')=='active')
        del state['hypotheses'][key]['revision_decomposition']
        with self.assertRaisesRegex(ValueError,'time/evidence decomposition'):fm.validate_long_updates(self.bundle,self.evidence,state)

    def test_declared_time_and_evidence_components_must_reproduce_probability(self):
        state=self.new_long_state()
        h=next(h for h in state['hypotheses'].values() if h.get('status','active')=='active')
        h['revision_decomposition']['delta_evidence_pp']=3
        with self.assertRaisesRegex(ValueError,'do not reproduce'):fm.validate_long_updates(self.bundle,self.evidence,state)

    def test_conditional_survival_is_explicit_and_not_a_short_window_conversion(self):
        value=fm.conditional_time_probability(.4,'2026-10-28T07:05:38+01:00','2026-11-04T08:16:17+01:00','2026-12-31T23:59:59+01:00')
        self.assertGreater(value,.36);self.assertLess(value,.37)
        self.assertEqual(fm.conditional_time_probability(.4,'2026-10-28T07:05:38+01:00','2026-12-31T23:59:59+01:00','2026-12-31T23:59:59+01:00'),0)

    def test_long_candidates_must_be_explicitly_adjudicated(self):
        state=self.new_long_state()
        review=fm.long_review(self.bundle,self.evidence,state,f.instant(state['assessment_time']))
        key=next(k for k,r in review.items() if r['candidates'])
        state['hypotheses'][key]['candidate_audit']=[]
        with self.assertRaisesRegex(ValueError,'candidates require explicit'):fm.validate_long_updates(self.bundle,self.evidence,state)

    def test_public_page_explains_versions_missingness_and_no_independence_claim(self):
        issue=self.issue();data=f.evaluate(self.bundle,f.instant(issue['issued_at']))
        html=f.content(self.bundle,data)
        self.assertIn('fixed-v1',html);self.assertIn('fixed-v2',html)
        self.assertIn('Citlivost na nevyřešené',html);self.assertIn('Efektivní velikost vzorku',html)
        self.assertIn('Rozpětí není interval spolehlivosti',html)

    def test_publication_still_rejects_rewriting_old_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'data';shutil.copytree(build_site.DATA,data)
            path=data/f.OUTCOMES
            path.write_text('\n'.join(path.read_text().splitlines()[1:])+'\n')
            with patch.object(publish_update,'DATA',data),self.assertRaisesRegex(ValueError,'history changed'):
                publish_update.preserve_history()

    def test_v2_published_rules_cannot_be_revised_in_place(self):
        changed=copy.deepcopy(self.protocol)
        changed['date_only_policy']['tie_break']='earlier_window'
        with self.assertRaisesRegex(ValueError,'immutable|schedule'):
            f.preserve_protocol(self.protocol,changed,f.instant(self.protocol['introduced_at']))

    def test_only_new_evidence_uses_canonical_labels(self):
        row=dict(status='unverified_claim',signal_type=['rhetoric/signalling'])
        fm.validate_new_evidence_labels([row])
        row['status']='unverified claim'
        with self.assertRaisesRegex(ValueError,'canonical status'):fm.validate_new_evidence_labels([row])
        row['status']='reported';row['signal_type']=['rhetoric']
        with self.assertRaisesRegex(ValueError,'canonical signal'):fm.validate_new_evidence_labels([row])

    def test_long_definitive_correction_also_needs_a_reason(self):
        original=self.bundle['forecast-register.jsonl'][0]
        first=dict(id='TEST-long-yes',forecast_id=original['id'],outcome='yes',resolved_at='2026-11-05T10:00:00+01:00',
                   event_time=(f.instant(original['window_start'])+timedelta(days=1)).isoformat(),
                   evidence_ids=[self.evidence[0]['id']],source_urls=['https://example.com/TEST'],rationale='TEST long outcome',supersedes=None)
        second={**first,'id':'TEST-long-no','outcome':'no','resolved_at':'2027-01-02T10:00:00+01:00',
                'coverage_basis':'TEST bounded audit','supersedes':first['id']}
        self.bundle['forecast-resolutions.jsonl']=[first,second]
        with self.assertRaisesRegex(ValueError,'long outcome flip'):self.validate()
        second.update(correction_reason_class='source_correction',correction_note='TEST source retracted its attribution')
        self.validate()


if __name__=='__main__':unittest.main()
