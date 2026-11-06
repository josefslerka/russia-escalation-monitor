"""Exercise the morning CLI/publication workflow with TEST ONLY data and local Git.

No source is fetched and no public remote is configured. The clock is replaced
only inside these tests; production commands retain their real-time guards.
"""
from contextlib import ExitStack, redirect_stdout
import copy
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import bilingual
import build_site
import check_site
import forecast
import forecasting as f
import forecast_methods as fm
import monitor
import monitoring as m
import publish_update


class MorningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='forecast-morning-TEST-')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / 'checkout'
        self.root.mkdir()
        self.data = self.root / 'russia-escalation'
        shutil.copytree(build_site.DATA, self.data, ignore=shutil.ignore_patterns('audits', '.monitor-*'))
        shutil.copytree(build_site.ROOT / 'site', self.root / 'site')
        self.initial_state = json.loads((self.data / 'state.json').read_text())
        self.initial_rounds = (self.data / f.ROUNDS).read_bytes()
        self.original_protocol = (self.data / f.PROTOCOL).read_bytes()
        self.protected = {p.relative_to(self.data): p.read_bytes() for folder in ['reports', 'snapshots']
                          for p in (self.data / folder).iterdir() if p.is_file()}
        self.counter = 0
        self.now = f.instant(self.initial_state['assessment_time']) + timedelta(days=1)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()

        owner = self
        class TestClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return owner.now.astimezone(tz) if tz else owner.now.replace(tzinfo=None)

        stack = ExitStack()
        self.addCleanup(stack.close)
        for module in [build_site, check_site, publish_update]:
            stack.enter_context(patch.object(module, 'ROOT', self.root))
            stack.enter_context(patch.object(module, 'DATA', self.data))
        stack.enter_context(patch.object(monitor, 'DATA', self.data))
        for module in [monitor, forecast, publish_update]:
            stack.enter_context(patch.object(module, 'datetime', TestClock))

        # Exercise actual fetch/commit/push against a disposable local bare repo.
        # Even if the test patch fails, origin has no public/network destination.
        self.remote = Path(self.folder.name) / 'local-TEST-origin.git'
        self.git('init', '--bare', '--initial-branch=master', str(self.remote))
        self.git('init', '--initial-branch=master')
        self.git('config', 'user.name', 'Forecast TEST ONLY')
        self.git('config', 'user.email', 'forecast-test@example.invalid')
        self.git('add', '--', 'russia-escalation', 'site')
        self.git('commit', '-qm', 'TEST ONLY initial fixture')
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('push', '-q', 'origin', 'master')
        self.git('fetch', '-q', 'origin', 'master')
        real_git = publish_update.git
        def local_publication_git(*args, **kwargs):
            if args == ('remote', 'get-url', 'origin'):
                self.assertEqual(self.git(*args).stdout.strip(), str(self.remote))
                return subprocess.CompletedProcess(args, 0, sorted(publish_update.EXPECTED_REMOTES)[0] + '\n', '')
            return real_git(*args, **kwargs)
        stack.enter_context(patch.object(publish_update, 'git', local_publication_git))

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, text=True, capture_output=True, check=True)

    def cli(self, module, *args, payload=None):
        if payload is not None:
            self.counter += 1
            path = self.inputs / f'TEST-{self.counter}.json'
            path.write_text(json.dumps(payload, ensure_ascii=False))
            args = (*args, '--input', str(path))
        out = StringIO()
        with patch('sys.argv', [module.__name__ + '.py', *args]), redirect_stdout(out):
            module.main()
        value = out.getvalue()
        return json.loads(value) if value.lstrip().startswith(('{', '[')) else value

    def context(self):
        return monitor.context()

    def next_window_morning(self, days):
        bundle, _, _ = self.context()
        p = bundle[fm.V2]
        after = max(f.instant(self.initial_state['assessment_time']), f.instant(p['introduced_at']))
        number = max(1, int((after - f.instant(p['anchor'])).total_seconds() // (days * 86400)) + 1)
        start, _ = f.window(p, days, number)
        while any(r['protocol']=='fixed-v2' and r['horizon_days']==days and f.instant(r['window_start'])==start for r in bundle[f.ROUNDS]):
            number += 1
            start, _ = f.window(p, days, number)
        self.now = start - timedelta(hours=1)
        return start

    def record_check(self, source_ids=None, issue=None, outcome='no_new_relevant', full_plan=False):
        self.counter += 1
        ident = f'TEST-morning-check-{self.counter}'
        run_id = f'TEST-morning-run-{self.counter}'
        task = 'forecast:resolve:' + issue['id'] if issue else ident
        expected = [t['id'] for t in self.cli(monitor, 'due')['tasks']] if full_plan else []
        expected = list(dict.fromkeys([*expected, task]))
        run = dict(id=run_id, kind='daily', started_at=(self.now-timedelta(minutes=5)).isoformat(),
                   finished_at=self.now.isoformat(), expected_tasks=expected, note='TEST ONLY synthetic research')
        self.cli(monitor, 'append', 'monitoring-runs.jsonl', payload=run)
        if source_ids is None:
            source_ids = sorted({s for g in issue['contract']['source_groups'] for s in g['source_ids']}) if issue else ['wire-reuters']
        check = dict(id=ident, run_id=run_id, task_id=task, checked_at=self.now.isoformat(),
                     source_ids=source_ids, urls=['https://example.com/TEST-ONLY'], areas=['NATO'], domains=['incidents'],
                     period_start=issue['window_start'][:10] if issue else self.now.date().isoformat(),
                     period_end=issue['window_end'][:10] if issue else self.now.date().isoformat(),
                     scope_type='forecast_audit' if issue else 'news_scan', forecast_id=issue['id'] if issue else None,
                     scope='TEST ONLY bounded synthetic source panel', limitations='No real OSINT research',
                     outcome=outcome, evidence_ids=[])
        self.cli(monitor, 'append', 'coverage.jsonl', payload=check)
        self.last_run = run_id
        return ident

    def issue_v2(self, days):
        self.next_window_morning(days)
        plan = self.cli(forecast, 'plan')
        templates = [t for t in plan['issue_templates'] if t['horizon_days'] == days]
        self.assertEqual(len(templates), 9)
        self.assertTrue(all(t['question_id'].endswith('-v2') for t in templates))
        check = self.record_check(full_plan=True)
        self.now += timedelta(minutes=5)
        for row in templates:
            row.update(source_cutoff=self.now.isoformat(), rationale='TEST ONLY synthetic estimate',
                       alternative='TEST ONLY alternative', check_ids=[check], source_urls=['https://example.com/TEST-ONLY'],
                       estimation_mode='blind', dependence_note='TEST shared model/sources; no independence claim',
                       related_question_note='TEST definitions and horizons differ; no automatic conversion',
                       temporal_profile=dict(shape='uncertain', rationale='TEST no constant hazard assumption'))
            if row['question_id'].startswith('ukraine-grid-'):
                row.update(p=None, abstention_reason='TEST insufficient evidence: exercise the unfilled plan template')
                # Deliberately leave the plan's three p:null placeholders unchanged.
            else:
                row['p'] = .2
                for raw, value in zip(row['estimation_passes'], [.1, .2, .3]):
                    raw.update(p=value, rationale='TEST synthetic approach', completed_at=self.now.isoformat(), check_ids=[check])
                    if raw['approach'] == 'reference_class':
                        raw['base_rate'] = dict(status='unavailable', note='TEST no measured base-rate sample')
        malformed=copy.deepcopy(next(r for r in templates if r['p'] is not None))
        malformed['estimation_passes'][0]['p']=None
        before=(self.data/f.ROUNDS).read_bytes()
        with self.assertRaisesRegex(ValueError,'Raw estimates must be numeric'):
            self.cli(forecast,'issue',payload=malformed)
        self.assertEqual((self.data/f.ROUNDS).read_bytes(),before)
        self.cli(forecast, 'issue', payload=templates)
        bundle, _, _ = self.context()
        issues = [r for r in bundle[f.ROUNDS] if r['issued_at'] == self.now.astimezone(timezone.utc).isoformat()]
        self.assertEqual(len(issues), 9)
        abstention = next(r for r in issues if r['p'] is None)
        self.assertEqual(abstention['estimation_passes'], [])
        self.assertEqual(abstention['estimate_spread'], [])
        self.now += timedelta(minutes=1)
        self.cli(forecast, 'benchmark', payload=[dict(forecast_id=r['id'], provider='TEST searched panel', status='not_found', p=None,
                 rationale='TEST no exactly comparable question', source_urls=['https://example.com/TEST-ONLY']) for r in issues if r['p'] is not None])
        self.assertFalse(any(t['kind'] == 'forecast_benchmark' for t in self.cli(forecast, 'plan')['tasks']))
        return issues

    def outcome_request(self, issue, result='unknown'):
        bundle, _, _ = self.context()
        previous = f.latest(bundle[f.OUTCOMES]).get(issue['id'])
        row = dict(forecast_id=issue['id'], outcome=result, rationale='TEST ONLY synthetic adjudication', evidence_ids=[],
                   check_ids=[], source_urls=['https://example.com/TEST-ONLY'], supersedes=previous['id'] if previous else None)
        if result == 'unknown':
            row['next_check_by'] = (self.now+timedelta(days=1)).isoformat()
        return row

    def old_grid(self):
        return next(r for r in self.context()[0][f.ROUNDS] if r['protocol']=='fixed-v1'
                    and r['question_id']=='ukraine-grid-emergency-v1' and r['horizon_days']==7)

    def freeze_legacy_time_fixture(self, issue, at):
        """Only this historical-time test: discard later fixture decisions, never production data."""
        for name, field in [(f.OUTCOMES,'resolved_at'),(fm.CANDIDATES,'reviewed_at')]:
            path=self.data/name
            rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            rows=[r for r in rows if r['forecast_id']!=issue['id'] or f.instant(r[field])<=at]
            path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        state=json.loads((self.data/'state.json').read_text())
        reviewed=f.instant(state['research_scope']['fixed_forecast_review']['reviewed_at'])
        state['research_scope']['fixed_forecast_review']=f.assessment_scope(m.load(self.data),reviewed)
        (self.data/'state.json').write_text(json.dumps(state,ensure_ascii=False))

    def positive_fixture(self, issue, raw):
        bundle, _, _ = self.context()
        ids=[];new_evidence=[]
        for n in range(2):
            ident=f'TEST-positive-{self.counter}-{n}'
            item=dict(id=ident, event_time=raw, publication_time=raw, discovery_time=self.now.isoformat(),
                      source='TEST ONLY', source_url=f'https://example.com/TEST-ONLY/{ident}', source_tier=1,
                      provenance_root=ident, independent_source_line=ident, status='confirmed', signal_type=['readiness'],
                      domain=['nato'], direction='up', summary='TEST ONLY fictional event; never a public forecast',
                      alternative_explanation='Synthetic test data')
            new_evidence.append(item);ids.append(ident)
        with (self.data/'evidence.jsonl').open('a') as stream:
            stream.write(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in new_evidence))
        geo=json.loads((self.data/'geography.json').read_text())
        for ident in ids:geo['entries'][ident]=dict(areas=[],note='TEST synthetic geography unknown')
        (self.data/'geography.json').write_text(json.dumps(geo,ensure_ascii=False))
        case=dict(id=f'TEST-positive-case-{self.counter}',title='TEST ONLY fictional incident',kind='incident',areas=['NATO'],
                  russian_involvement='unknown',summary='TEST ONLY',attribution_basis='Synthetic primary-source lines',
                  links=[dict(evidence_id=i,line_id=i,claim='TEST ONLY',role='first_report',independence_basis='TEST separate lines') for i in ids])
        bundle['events.json']['events'].append(case)
        (self.data/'events.json').write_text(json.dumps(bundle['events.json'],ensure_ascii=False))
        row=self.outcome_request(issue,'yes')
        lo,hi=f.timing_bounds(raw,'Europe/Prague')
        row.update(case_id=case['id'],event_time=raw,publication_time=raw,first_qualifying_publication=True,
                   timing_basis=issue['contract']['time_basis'],qualifying_time_start=lo.isoformat(),qualifying_time_end=hi.isoformat(),
                   qualifying_timezone='Europe/Prague',evidence_ids=ids,criterion_evidence={k:ids for k in issue['contract']['criteria']})
        return row

    def save_assessment(self):
        self.now += timedelta(minutes=5)
        bundle,evidence,previous = self.context()
        state=copy.deepcopy(previous)
        stamp=self.now.astimezone(build_site.PRAGUE).isoformat(timespec='seconds')
        state.update(assessment_time=stamp,source_cutoff=stamp,previous_assessment=previous['assessment_time'],
                     last_report='reports/'+self.now.astimezone(build_site.PRAGUE).strftime('%Y-%m-%d-%H%M.md'),
                     one_line_judgment='TEST ONLY — not a real forecast',new_evidence_ids=[])
        review=fm.long_review(bundle,evidence,state,f.instant(stamp))
        origins=self.cli(monitor,'origins')
        for key,h in state['hypotheses'].items():
            if h.get('status','active')!='active':continue
            h.update(origins[key],prior=h['p'],delta_pp=0,trend='flat',coherence_note='TEST distinct original definitions')
            h['revision_decomposition']={**review[key]['template'], 'time_rationale':'TEST absence not established; no time model',
                                         'evidence_rationale':'TEST no evidence-driven probability change'}
            h['candidate_audit']=[{**c,'rationale':'TEST unresolved original criterion', 'missing_evidence':'TEST adequate attribution or timing not established'}
                                  for c in review[key]['candidate_audit']]
        run=next(r for r in bundle['monitoring-runs.jsonl'] if r['id']==self.last_run)
        completed=m.completed_tasks(bundle,run['id'],f.instant(stamp))
        state['research_scope']=dict(monitoring_run_id=run['id'],coverage_status='complete' if set(run['expected_tasks'])<=completed else 'partial',
                                     fixed_forecast_review=self.cli(forecast,'plan')['assessment_scope'])
        inverse={v:k for k,v in bilingual.CONFIDENCE.items()}
        for lang in ['cs','en']:
            rows=[]
            for key,h in state['hypotheses'].items():
                if h.get('status','active')!='active':continue
                confidence=h['confidence'] if lang=='en' else inverse[h['confidence']]
                rows.append(f'| {key} | {h["horizon"]} | {h["prior"]*100:g} | {h["p"]*100:g} | 0 | {h["range"][0]*100:g}–{h["range"][1]*100:g} | {confidence} |')
            text=f'''# TEST ONLY — {"not a real forecast" if lang=="en" else "nejde o skutečnou prognózu"}

**{"Overall" if lang=="en" else "Celkově"}:** {state['overall_level']}, flat
**{"One-line judgment" if lang=="en" else "Jednovětý závěr"}:** TEST ONLY synthetic workflow.
{stamp}
{state['forecast_window_end']}

## {"Probability dashboard" if lang=="en" else "Pravděpodobnosti"}

| Event | Horizon | Prior | Now | Delta | Range | Confidence |
|---|---|---:|---:|---:|---|---|
{chr(10).join(rows)}

## {"Research limitations" if lang=="en" else "Omezení rešerše"}

TEST ONLY. Synthetic evidence and estimates; no real research was performed.
[TEST source](https://example.com/TEST-ONLY)

**WDPI: {state['wdpi']['total']}/100**, flat
'''
            path=self.data/state['last_report']
            if lang=='en':path=bilingual.english_path(path)
            path.write_text(text,encoding='utf-8')
        path=self.data/'state.json'
        temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(state,ensure_ascii=False));temporary.replace(path)
        self.cli(monitor,'validate')
        return state

    def publish_locally(self):
        with redirect_stdout(StringIO()):publish_update.publish()
        self.assertEqual(self.git('rev-parse','HEAD').stdout,self.git('rev-parse','origin/master').stdout)
        self.assertEqual((self.data/f.PROTOCOL).read_bytes(),self.original_protocol)
        self.assertTrue((self.data/f.ROUNDS).read_bytes().startswith(self.initial_rounds))
        for rel,content in self.protected.items():self.assertEqual((self.data/rel).read_bytes(),content)
        self.assertEqual(json.loads((self.root/'_site/data/state.json').read_text()),json.loads((self.data/'state.json').read_text()))

    def test_next_daily_assessment_registers_publishes_and_repeats_without_duplicates(self):
        self.now=self.now.astimezone(build_site.PRAGUE).replace(hour=7,minute=0,second=0,microsecond=0)
        self.cli(monitor,'due');self.cli(forecast,'plan');self.cli(forecast,'coherence');self.cli(forecast,'long-review')
        self.record_check(full_plan=True)
        old=self.old_grid();self.cli(forecast,'resolve',payload=self.outcome_request(old))
        state=self.save_assessment()
        self.assertEqual(state['research_scope']['coverage_status'],'partial')
        self.publish_locally()
        head=self.git('rev-parse','HEAD').stdout
        self.publish_locally()
        self.assertEqual(self.git('rev-parse','HEAD').stdout,head)
        self.assertTrue((self.data/'snapshots'/Path(state['last_report']).with_suffix('.json').name).is_file())

    def test_weekly_numeric_and_abstained_issues_benchmarks_and_publication(self):
        issues=self.issue_v2(7)
        old=self.old_grid();self.cli(forecast,'resolve',payload=self.outcome_request(old))
        self.save_assessment();self.publish_locally()
        saved=json.loads((self.root/'_site/data/fixed-evaluation.json').read_text())
        self.assertEqual(len([r for r in saved['rows'] if r['id'] in {x['id'] for x in issues}]),9)
        self.assertEqual(next(r for r in saved['rows'] if r['id']==old['id'])['status'],'unknown')

    def test_monthly_numeric_and_abstained_issues_benchmarks_and_publication(self):
        self.issue_v2(30)
        self.save_assessment();self.publish_locally()

    def test_v1_cannot_borrow_new_grid_criteria_date_assignment_or_void(self):
        self.next_window_morning(7)
        old=self.old_grid()
        row=self.positive_fixture(old,(f.instant(old['window_start'])+timedelta(days=2)).isoformat())
        del row['criterion_evidence']['three_regions']
        before=(self.data/f.OUTCOMES).read_bytes()
        with self.assertRaisesRegex(ValueError,'Every frozen criterion'):self.cli(forecast,'resolve',payload=row)
        self.assertEqual((self.data/f.OUTCOMES).read_bytes(),before)
        boundary=f.instant(old['window_end']).astimezone(build_site.PRAGUE).date().isoformat()
        row=self.positive_fixture(old,boundary)
        row['date_assignment']=dict(policy='source-day-majority-v2',window_number=1,source_timezone='Europe/Prague')
        with self.assertRaisesRegex(ValueError,'crosses fixed window boundary'):self.cli(forecast,'resolve',payload=row)
        self.now=max(self.now,f.instant(old['settle_after'])+timedelta(days=20))
        self.cli(forecast,'resolve',payload=self.outcome_request(old))
        row=self.outcome_request(old,'void');row['void_reason_class']='timing_unresolved'
        with self.assertRaisesRegex(ValueError,'Missing outcome'):self.cli(forecast,'resolve',payload=row)

    def test_v2_yes_unknown_void_and_v1_unknown_survive_a_mixed_publication(self):
        issues=self.issue_v2(7)
        issue=next(r for r in issues if r['question_id']=='eu-sabotage-disclosure-v2')
        deadline=f.instant(issue['final_adjudication_by'])
        self.now=deadline-timedelta(days=1)
        row=self.outcome_request(issue)
        row['next_check_by']=(deadline+timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'past the final'):self.cli(forecast,'resolve',payload=row)
        row['next_check_by']=issue['final_adjudication_by']
        self.cli(forecast,'resolve',payload=row)
        self.now=deadline
        tasks=self.cli(forecast,'plan')['tasks']
        self.assertTrue(any(t.get('forecast_id')==issue['id'] and t.get('must_finalize') for t in tasks))
        check=self.record_check(issue=issue,outcome='unavailable')
        row=self.outcome_request(issue,'no')
        row.update(check_ids=[check],coverage_basis='TEST failed source retrieval',open_claim_ids=[])
        with self.assertRaisesRegex(ValueError,'Partial/unavailable'):self.cli(forecast,'resolve',payload=row)
        row.update(outcome='void',void_reason_class='source_unavailable')
        self.cli(forecast,'resolve',payload=row)
        old=self.old_grid()
        self.cli(forecast,'resolve',payload=self.outcome_request(old))
        nato=next(r for r in issues if r['question_id']=='nato-armed-attack-v2')
        raw=f.instant(nato['window_start']).astimezone(build_site.PRAGUE).date().isoformat()
        positive=self.positive_fixture(nato,raw)
        positive['date_assignment']=dict(policy='source-day-majority-v2',window_number=nato['window_number'],source_timezone='Europe/Prague')
        self.cli(forecast,'resolve',payload=positive)
        self.save_assessment();self.publish_locally()
        rows={r['id']:r for r in json.loads((self.root/'_site/data/fixed-evaluation.json').read_text())['rows']}
        self.assertEqual(rows[issue['id']]['status'],'void');self.assertIsNone(rows[issue['id']]['brier'])
        self.assertEqual(rows[old['id']]['status'],'unknown')
        self.assertEqual(rows[nato['id']]['status'],'yes');self.assertAlmostEqual(rows[nato['id']]['brier'],.64)

    def test_v1_negative_waits_for_original_delay_panel_and_candidate_reviews(self):
        old=self.old_grid()
        # This fixture deliberately models a negative outcome. Start this one
        # contract before any real adjudication so the scenario is independent
        # of the real grid result; the disposable copy alone is changed.
        self.freeze_legacy_time_fixture(old, f.instant(old['window_start']))
        self.now=max(f.instant(self.initial_state['assessment_time']),f.instant(old['settle_after']))+timedelta(days=10)
        self.cli(forecast,'resolve',payload=self.outcome_request(old))
        self.now=f.instant(old['settle_after'])-timedelta(hours=1)
        self.freeze_legacy_time_fixture(old,self.now)
        check=self.record_check(issue=old)
        row=self.outcome_request(old,'no')
        row.update(check_ids=[check],coverage_basis='TEST original complete panel',open_claim_ids=[])
        with self.assertRaisesRegex(ValueError,'closed horizon plus reporting delay'):self.cli(forecast,'resolve',payload=row)
        self.now=f.instant(old['settle_after'])+timedelta(days=1)
        check=self.record_check(source_ids=['wire-reuters'],issue=old)
        row.update(check_ids=[check])
        with self.assertRaisesRegex(ValueError,'source group incompletely checked'):self.cli(forecast,'resolve',payload=row)
        check=self.record_check(issue=old)
        row['check_ids']=[check]
        candidates=self.cli(forecast,'candidates','--forecast-id',old['id'])
        self.assertTrue(candidates)
        with self.assertRaisesRegex(ValueError,'open claims differ'):self.cli(forecast,'resolve',payload=row)
        for c in candidates:
            self.cli(forecast,'review-candidate',payload=dict(forecast_id=old['id'],candidate_id=c['id'],decision='non_qualifying',
                     rationale='TEST ONLY scenario: no three named regions',failed_criteria=['three_regions'],
                     evidence_ids=c['evidence_ids'],check_ids=[check],source_urls=['https://example.com/TEST-ONLY'],supersedes=c['review_id']))
        self.cli(forecast,'resolve',payload=row)
        result=next(r for r in self.cli(forecast,'evaluate')['rows'] if r['id']==old['id'])
        self.assertEqual(result['status'],'no');self.assertAlmostEqual(result['brier'],old['p']**2)


if __name__=='__main__':
    unittest.main()
