"""Failures that would leak outcomes, erase missed forecasts, or invent negative results."""
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
import monitor
import monitoring as m


class FixedForecastTests(unittest.TestCase):
    def setUp(self):
        self.bundle = m.load(build_site.DATA)
        self.bundle[f.ROUNDS] = []
        self.bundle[f.OUTCOMES] = []
        self.state = json.loads((build_site.DATA / 'snapshots/2026-10-30-0808.json').read_text())
        self.evidence = [json.loads(line) for line in (build_site.DATA / 'evidence.jsonl').read_text().splitlines() if line.strip()]
        self.protocol = self.bundle[f.PROTOCOL]
        self.start = f.instant(self.protocol['anchor'])
        self.issued = self.start - timedelta(hours=1)
        self.counter = 0

    def validate(self):
        m.validate(self.bundle, self.evidence, self.state)

    def test_origins_cli_outputs_original_registered_boundaries(self):
        with patch('sys.argv', ['monitor.py', 'origins']), \
                patch.object(monitor, 'context', return_value=(self.bundle, self.evidence, self.state)), \
                patch('builtins.print') as output:
            monitor.main()
        origins = json.loads(output.call_args.args[0])
        self.assertEqual(origins, f.legacy_origins(self.bundle, self.state))
        self.assertTrue(origins)
        self.assertTrue(all(f.instant(row['forecast_window_start']) < f.instant(self.state['assessment_time'])
                            for row in origins.values()))

    def check(self, at, sources, start, end, forecast_id=None, outcome='no_new_relevant'):
        self.counter += 1
        ident = 'TEST-fixed-check-' + str(self.counter)
        run_id = 'TEST-fixed-run-' + str(self.counter)
        self.bundle['monitoring-runs.jsonl'].append(dict(id=run_id,kind='backfill',started_at=(at-timedelta(hours=1)).isoformat(),finished_at=at.isoformat(),expected_tasks=[ident],note='TEST only'))
        self.bundle['coverage.jsonl'].append(dict(id=ident,run_id=run_id,task_id=ident,checked_at=at.isoformat(),source_ids=sources,
            urls=['https://example.com/TEST'],areas=['NATO'],domains=['incidents'],period_start=start,period_end=end,
            scope_type='forecast_audit' if forecast_id else 'news_scan',forecast_id=forecast_id,
            scope='TEST complete bounded archive search',limitations='TEST fixture',outcome=outcome,evidence_ids=[]))
        return ident

    def issue(self, q='eu-sabotage-disclosure-v1', days=7, p=.2):
        cutoff = self.issued-timedelta(minutes=1)
        cid = self.check(cutoff,['wire-reuters'],cutoff.date().isoformat(),cutoff.date().isoformat())
        raw = dict(question_id=q,horizon_days=days,window_number=0,p=p,source_cutoff=cutoff.isoformat(),
                   rationale='TEST researched judgment',alternative='TEST alternative',evidence_ids=[],check_ids=[cid],source_urls=['https://example.com/TEST'])
        issue = f.make_issue(self.protocol,raw,self.issued)
        self.bundle[f.ROUNDS].append(issue)
        return issue

    def outcome(self, forecast, result='no'):
        at = f.instant(forecast['settle_after']) + timedelta(hours=1)
        q = forecast['contract']
        sources = sorted({s for group in q['source_groups'] for s in group['source_ids']})
        check = self.check(at,sources,forecast['window_start'][:10],forecast['window_end'][:10],forecast['id'])
        row = dict(id='TEST-outcome-'+str(self.counter),forecast_id=forecast['id'],resolved_at=at.isoformat(),outcome=result,
                   evidence_ids=[],check_ids=[check],source_urls=['https://example.com/TEST'],rationale='TEST adjudication',supersedes=None,
                   open_claim_ids=[],coverage_basis='TEST checked full source panel and full time interval')
        if result == 'unknown':
            row['next_check_by'] = (at+timedelta(days=1)).isoformat()
        if result == 'yes':
            when = self.start+timedelta(days=2)
            ids = []
            for n in range(2):
                evidence = {**self.evidence[0], 'id':f'TEST-outcome-evidence-{self.counter}-{n}', 'source_tier':1,
                            'source_url':f'https://example.com/TEST/{self.counter}/{n}',
                            'event_time':when.isoformat(), 'publication_time':when.isoformat(),
                            'independent_source_line':f'TEST-independent-{n}'}
                self.evidence.append(evidence)
                ids.append(evidence['id'])
            case = copy.deepcopy(self.bundle['events.json']['events'][0])
            case.update(id='TEST-case-'+str(self.counter),kind='incident',case_status='closed',next_check_by=None,
                        links=[dict(evidence_id=i,line_id=f'TEST-line-{n}',claim='TEST',role='first_report',independence_basis='TEST independent') for n,i in enumerate(ids)])
            self.bundle['events.json']['events'].append(case)
            row.update(case_id=case['id'],evidence_ids=ids,event_time=when.isoformat(),publication_time=when.isoformat(),
                       qualifying_time_start=when.isoformat(),qualifying_time_end=when.isoformat(),
                       first_qualifying_publication=True,timing_basis=q['time_basis'],
                       criterion_evidence={key:ids for key in q['criteria']})
        self.bundle[f.OUTCOMES].append(row)
        return row

    def test_adjacent_windows_are_fixed_utc_intervals_even_across_dst(self):
        for days in (7,30):
            for number in (0,20,21,22):
                start,end=f.window(self.protocol,days,number)
                following,_=f.window(self.protocol,days,number+1)
                self.assertEqual(end,following)
                self.assertEqual((end-start).total_seconds(),days*86400)

    def test_late_or_backdated_issue_cannot_become_a_prospective_forecast(self):
        forecast=self.issue()
        forecast['issued_at']=forecast['window_start']
        with self.assertRaisesRegex(ValueError,'Issue must precede'):
            self.validate()

    def test_window_cannot_move_with_new_assessment(self):
        forecast=self.issue()
        forecast['window_start']=(self.start+timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'cannot roll'):
            self.validate()

    def test_source_cutoff_cannot_include_future_checks(self):
        forecast=self.issue()
        forecast['source_cutoff']=(self.issued-timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'checks after'):
            self.validate()

    def test_probability_rejects_nan_boolean_and_unexplained_missingness(self):
        forecast=self.issue()
        for value in (float('nan'),True,None):
            forecast['p']=value
            with self.assertRaisesRegex(ValueError,'Invalid probability'):
                self.validate()
        forecast['abstention_reason']='TEST data insufficient'
        self.validate()
        result=f.evaluate(self.bundle,self.start+timedelta(days=9))
        self.assertEqual(next(r for r in result['rows'] if r['id']==forecast['id'])['status'],'abstained')

    def test_thirty_days_cannot_be_lower_for_same_cutoff_and_nested_event(self):
        self.issue(days=7,p=.3)
        self.issue(days=30,p=.2)
        with self.assertRaisesRegex(ValueError,'below nested'):
            self.validate()

    def test_criteria_cannot_be_silently_redefined_after_issue(self):
        self.issue()
        self.protocol['questions'][0]['criteria']['material_attempt']='TEST changed threshold'
        with self.assertRaisesRegex(ValueError,'retain old version'):
            self.validate()

    def test_no_waits_for_horizon_and_reporting_delay(self):
        forecast=self.issue()
        r=self.outcome(forecast)
        r['resolved_at']=(f.instant(forecast['window_end'])+timedelta(hours=1)).isoformat()
        r['check_ids']=[]
        with self.assertRaisesRegex(ValueError,'plus reporting delay'):
            self.validate()

    def test_successful_no_scores_with_the_complete_denominator(self):
        forecast=self.issue(p=.2)
        r=self.outcome(forecast)
        self.validate()
        data=f.evaluate(self.bundle,f.instant(r['resolved_at']))
        short=next(s for s in data['summaries'] if s['horizon_days']==7)
        self.assertEqual(short['counts']['no'],1)
        self.assertAlmostEqual(short['brier'],.04)
        self.assertEqual(short['always_no_brier'],0)
        self.assertIsNone(short['skill_vs_always_no'])
        self.assertGreater(short['counts']['missed'],0)

    def test_partial_closure_never_becomes_a_negative_result(self):
        forecast=self.issue()
        r=self.outcome(forecast)
        check=next(c for c in self.bundle['coverage.jsonl'] if c['id']==r['check_ids'][0])
        check['outcome']='partial'
        with self.assertRaisesRegex(ValueError,'cannot establish no'):
            self.validate()

    def test_unrelated_check_or_incomplete_period_does_not_close_forecast(self):
        forecast=self.issue()
        r=self.outcome(forecast)
        check=next(c for c in self.bundle['coverage.jsonl'] if c['id']==r['check_ids'][0])
        check['forecast_id']='other'
        with self.assertRaisesRegex(ValueError,'dedicated window'):
            self.validate()
        check['forecast_id']=forecast['id']
        check['period_start']=(self.start+timedelta(days=1)).date().isoformat()
        with self.assertRaisesRegex(ValueError,'whole fixed window'):
            self.validate()

    def test_missing_required_source_group_cannot_establish_no(self):
        forecast=self.issue()
        r=self.outcome(forecast)
        check=next(c for c in self.bundle['coverage.jsonl'] if c['id']==r['check_ids'][0])
        check['source_ids']=['wire-reuters']
        with self.assertRaisesRegex(ValueError,'source group incompletely'):
            self.validate()

    def test_an_open_claim_blocks_no(self):
        forecast=self.issue()
        self.outcome(forecast)['open_claim_ids']=['TEST-unresolved-claim']
        with self.assertRaisesRegex(ValueError,'Unresolved claims'):
            self.validate()

    def test_unknown_preserves_missing_result_and_followup_deadline(self):
        forecast=self.issue()
        r=self.outcome(forecast,'unknown')
        self.validate()
        at=f.instant(r['resolved_at'])
        data=f.evaluate(self.bundle,at)
        self.assertIsNone(next(s for s in data['summaries'] if s['horizon_days']==7)['brier'])
        self.assertFalse(any(t.get('forecast_id')==forecast['id'] for t in f.tasks(self.bundle,at)))
        self.assertTrue(any(t.get('forecast_id')==forecast['id'] for t in f.tasks(self.bundle,f.instant(r['next_check_by']))))

    def test_yes_requires_evidence_for_every_criterion(self):
        forecast=self.issue()
        r=self.outcome(forecast,'yes')
        self.validate()
        r['criterion_evidence'].pop(next(iter(r['criterion_evidence'])))
        with self.assertRaisesRegex(ValueError,'Every frozen criterion'):
            self.validate()

    def test_occurrence_cannot_be_replaced_by_late_disclosure(self):
        forecast=self.issue(q='nato-armed-attack-v1')
        r=self.outcome(forecast,'yes')
        r['event_time']=(self.start-timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'differ from original'):
            self.validate()

    def test_uncertain_boundary_day_cannot_be_scored_by_guessing_an_hour(self):
        forecast=self.issue(q='nato-armed-attack-v1')
        r=self.outcome(forecast,'yes')
        r['event_time']=self.start.date().isoformat()
        r['qualifying_timezone']='UTC'
        lo,hi=f.timing_bounds(r['event_time'],'UTC')
        r.update(qualifying_time_start=lo.isoformat(),qualifying_time_end=hi.isoformat())
        with self.assertRaisesRegex(ValueError,'uncertainty crosses'):
            self.validate()

    def test_duplicate_primary_provenance_is_not_independent_confirmation(self):
        forecast=self.issue(q='nato-armed-attack-v1')
        r=self.outcome(forecast,'yes')
        for e in self.evidence:
            if e['id'] in r['evidence_ids']:e['independent_source_line']='TEST-same-line'
        with self.assertRaisesRegex(ValueError,'independent primary'):
            self.validate()

    def test_corrections_supersede_instead_of_adding_another_sample(self):
        forecast=self.issue()
        first=self.outcome(forecast)
        correction={**first,'id':'TEST-correction','resolved_at':(f.instant(first['resolved_at'])+timedelta(hours=2)).isoformat(),
                    'outcome':'unknown','next_check_by':(f.instant(first['resolved_at'])+timedelta(days=1)).isoformat(),'supersedes':first['id']}
        self.bundle[f.OUTCOMES].append(correction)
        self.validate()
        before=f.evaluate(self.bundle,f.instant(first['resolved_at']))
        after=f.evaluate(self.bundle,f.instant(correction['resolved_at']))
        self.assertEqual(next(s for s in before['summaries'] if s['horizon_days']==7)['scored'],1)
        self.assertEqual(next(s for s in after['summaries'] if s['horizon_days']==7)['scored'],0)

    def test_seven_and_thirty_day_results_are_never_pooled(self):
        short=self.issue(days=7,p=.2)
        long=self.issue(days=30,p=.4)
        self.outcome(short,'yes')
        r=self.outcome(long,'yes')
        # Same canonical event and qualifying timestamp may legitimately satisfy both horizons.
        a,b=self.bundle[f.OUTCOMES]
        b['case_id']=a['case_id'];b['evidence_ids']=a['evidence_ids'];b['criterion_evidence']=a['criterion_evidence']
        self.validate()
        data=f.evaluate(self.bundle,f.instant(r['resolved_at']))
        self.assertAlmostEqual(data['summaries'][0]['brier'],.64)
        self.assertAlmostEqual(data['summaries'][1]['brier'],.36)
        self.assertNotIn('brier',data)

    def test_diagnostic_subquestions_are_displayed_but_not_double_counted(self):
        forecast=self.issue(q='cze-sabotage-disclosure-v1')
        r=self.outcome(forecast)
        self.validate()
        data=f.evaluate(self.bundle,f.instant(r['resolved_at']))
        self.assertEqual(next(row for row in data['rows'] if row['id']==forecast['id'])['status'],'no')
        self.assertEqual(data['summaries'][0]['scored'],0)

    def test_legacy_boundaries_are_recovered_without_editing_old_records(self):
        origins=f.legacy_origins(self.bundle,self.state)
        self.state['assessment_time']='2026-11-01T10:00:00+01:00'
        with self.assertRaisesRegex(ValueError,'Legacy forecast window rolls'):
            f.validate_legacy_windows(self.bundle,self.state)
        for key,bounds in origins.items():self.state['hypotheses'][key].update(bounds)
        self.state['research_scope']['fixed_forecast_review']=f.assessment_scope(self.bundle,f.instant(self.state['assessment_time']))
        f.validate_legacy_windows(self.bundle,self.state)

    def test_atomic_writer_rejects_backdating_without_changing_the_log(self):
        forecast=self.issue()
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'russia-escalation'
            shutil.copytree(build_site.DATA,data)
            (data/f.ROUNDS).write_text('')
            (data/f.OUTCOMES).write_text('')
            (data/'state.json').write_text(json.dumps(self.state))
            before=(data/f.ROUNDS).read_bytes()
            forecast['issued_at']='2026-10-29T07:00:00+01:00'
            with patch.object(monitor,'DATA',data),self.assertRaisesRegex(ValueError,'no backdating'):
                monitor.append_records(f.ROUNDS,[forecast])
            self.assertEqual((data/f.ROUNDS).read_bytes(),before)

    def test_published_schedule_and_questions_cannot_be_rewritten(self):
        old=copy.deepcopy(self.protocol)
        changed=copy.deepcopy(old)
        changed['anchor']=(self.start+timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'schedule/policy'):
            f.preserve_protocol(old,changed,self.issued)
        changed=copy.deepcopy(old)
        changed['questions'][0]['definition']='TEST new meaning'
        with self.assertRaisesRegex(ValueError,'append-only'):
            f.preserve_protocol(old,changed,self.issued)

    def test_actual_clock_blocks_a_last_minute_backdate_after_window_start(self):
        forecast=self.issue()
        forecast['issued_at']=(self.start-timedelta(seconds=10)).isoformat()
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'russia-escalation';shutil.copytree(build_site.DATA,data)
            (data/f.ROUNDS).write_text('')
            (data/f.OUTCOMES).write_text('')
            (data/'state.json').write_text(json.dumps(self.state))
            with patch.object(monitor,'DATA',data),patch.object(monitor,'datetime') as clock:
                clock.now.return_value=self.start+timedelta(seconds=10)
                with self.assertRaisesRegex(ValueError,'Actual issuance deadline passed'):
                    monitor.append_records(f.ROUNDS,[forecast])
            self.assertEqual((data/f.ROUNDS).read_text(),'')

    def test_new_question_version_cannot_backfill_missed_slots(self):
        old=copy.deepcopy(self.protocol)
        q=copy.deepcopy(old['questions'][0]);q['id']='TEST-new-version'
        self.protocol['questions'].append(q)
        at=self.start+timedelta(days=8)
        with self.assertRaisesRegex(ValueError,'historical forecast slots'):
            f.preserve_protocol(old,self.protocol,at)
        q['active_from']=(self.start+timedelta(days=30)).isoformat()
        f.preserve_protocol(old,self.protocol,at)
        data=f.evaluate(self.bundle,at)
        self.assertFalse(any(r['question_id']==q['id'] for r in data['rows']))

    def test_retirement_keeps_already_planned_missing_results_visible(self):
        q=self.protocol['questions'][0]
        at=self.start+timedelta(days=8)
        old=copy.deepcopy(self.protocol)
        self.protocol['retirements'].append(dict(question_id=q['id'],effective_at=(at+timedelta(days=1)).isoformat(),reason='TEST prospectively retired'))
        f.preserve_protocol(old,self.protocol,at)
        rows=f.evaluate(self.bundle,at)['rows']
        self.assertTrue(any(r['question_id']==q['id'] and r['window_number']==0 and r['status']=='missed' for r in rows))
        self.protocol['retirements'][0]['effective_at']=(at-timedelta(days=2)).isoformat()
        with self.assertRaisesRegex(ValueError,'erase past planned'):
            f.preserve_protocol(old,self.protocol,at)

    def test_recorded_disclosure_date_must_agree_with_its_primary_publication(self):
        forecast=self.issue()
        r=self.outcome(forecast,'yes')
        changed=self.start+timedelta(days=3)
        r.update(publication_time=changed.isoformat(),qualifying_time_start=changed.isoformat(),qualifying_time_end=changed.isoformat())
        with self.assertRaisesRegex(ValueError,'not supported by the cited publication'):
            self.validate()

    def test_missing_denominator_cannot_be_omitted_from_assessment(self):
        origins=f.legacy_origins(self.bundle,self.state)
        self.state['assessment_time']='2026-11-10T10:00:00+01:00'
        for key,bounds in origins.items():self.state['hypotheses'][key].update(bounds)
        review=f.assessment_scope(self.bundle,f.instant(self.state['assessment_time']))
        self.assertTrue(review['missed_issue_ids'])
        self.state['research_scope']['fixed_forecast_review']=review
        review['missed_issue_ids']=[]
        with self.assertRaisesRegex(ValueError,'omits missed'):
            f.validate_legacy_windows(self.bundle,self.state)

    def test_page_and_counts_cannot_turn_empty_logs_into_zero_risk(self):
        at=self.issued
        data=f.evaluate(self.bundle,at)
        html=f.content(self.bundle,data)
        self.assertIn('Dosud nevydáno',html)
        self.assertTrue(all(s['brier'] is None and s['issued']==0 for s in data['summaries']))
        self.assertTrue(all(r['p'] is None for r in data['rows']))

    def test_completed_issuance_satisfies_its_research_task_without_inventing_a_check(self):
        forecast=self.issue()
        cid=forecast['check_ids'][0]
        check=next(c for c in self.bundle['coverage.jsonl'] if c['id']==cid)
        run=next(r for r in self.bundle['monitoring-runs.jsonl'] if r['id']==check['run_id'])
        task='forecast:issue:'+forecast['id']
        run['expected_tasks'].append(task)
        self.assertNotIn(task,m.completed_tasks(self.bundle,run['id'],self.issued-timedelta(seconds=1)))
        self.assertIn(task,m.completed_tasks(self.bundle,run['id'],self.issued))

    def test_next_bilingual_assessment_must_freeze_origins_and_expose_the_queue(self):
        # Disposable labelled reports test the real site validator, not a public assessment.
        # Keep this synthetic assessment newer than the copied live archive.
        latest=f.instant(json.loads((build_site.DATA / "state.json").read_text())["assessment_time"])
        at=max(self.start-timedelta(minutes=30),latest+timedelta(minutes=1))
        self.check(at-timedelta(minutes=1),['wire-reuters'],at.date().isoformat(),at.date().isoformat())
        run=self.bundle['monitoring-runs.jsonl'][-1]
        previous_time=self.state['assessment_time']
        previous_report=Path(self.state['last_report']).name
        next_name=at.astimezone(build_site.PRAGUE).strftime('%Y-%m-%d-%H%M.md')
        self.state.update(assessment_time=at.isoformat(),source_cutoff=at.isoformat(),last_report='reports/'+next_name)
        self.state['research_scope'].update(monitoring_run_id=run['id'],coverage_status='complete')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=root/'russia-escalation'
            shutil.copytree(build_site.DATA,data)
            for name in m.JSON_FILES:(data/name).write_text(json.dumps(self.bundle[name]))
            for name in m.LOG_FILES:(data/name).write_text(''.join(json.dumps(r)+'\n' for r in self.bundle[name]))
            for suffix in ('.md','.en.md'):
                original=build_site.DATA/'reports'/previous_report.removesuffix('.md')
                text=original.with_suffix(suffix).read_text().replace(previous_time,at.isoformat())
                target=data/'reports'/next_name.removesuffix('.md')
                target.with_suffix(suffix).write_text('<!-- TEST ONLY — not a new forecast -->\n'+text)
            def save(): (data/'state.json').write_text(json.dumps(self.state))
            save()
            with patch.object(build_site,'DATA',data):
                with self.assertRaisesRegex(ValueError,'Legacy forecast window rolls'):build_site.validate()
                for key,bounds in f.legacy_origins(self.bundle,self.state).items():self.state['hypotheses'][key].update(bounds)
                save()
                with self.assertRaisesRegex(ValueError,'must review fixed forecast tasks'):build_site.validate()
                self.state['research_scope']['fixed_forecast_review']=f.assessment_scope(self.bundle,at)
                save()
                build_site.validate()


if __name__ == '__main__':
    unittest.main()
