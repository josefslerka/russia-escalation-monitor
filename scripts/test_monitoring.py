"""Failure cases that could turn missing coverage into false certainty or corrupt history."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import build_site
import monitor
import monitoring as m
import publish_update
from signals import AREAS, temporal


class MonitoringChecks(unittest.TestCase):
    def setUp(self):
        self.bundle = m.load(build_site.DATA)
        self.state = json.loads((build_site.DATA / 'state.json').read_text())
        self.evidence = [json.loads(line) for line in (build_site.DATA / 'evidence.jsonl').read_text().splitlines()]

    def validate(self):
        return m.validate(self.bundle, self.evidence, self.state)

    def test_complete_eu_nato_plan_and_explicit_unknown_countries(self):
        self.validate()
        self.assertEqual(len(self.bundle['sources.json']['countries']), 36)
        self.assertTrue({'NLD','SWE','BEL','FIN','AUT','SVK','HUN','CAN','ISL','MLT','MKD','MNE','TUR'} <= AREAS.keys())
        # Test an explicitly unvisited country, regardless of future production runs.
        self.bundle['coverage.jsonl'] = [c for c in self.bundle['coverage.jsonl'] if 'MLT' not in c['areas']]
        data = m.payload(self.bundle, self.evidence, self.state)
        self.assertEqual(data['countries']['MLT']['status'], 'not_checked')
        self.assertIsNone(data['countries']['MLT']['last_attempt'])
        self.assertTrue({'NORTH_SEA','ARCTIC'} <= AREAS.keys())

    def test_selected_documents_do_not_claim_complete_country_coverage(self):
        self.bundle['coverage.jsonl'] = [c for c in self.bundle['coverage.jsonl'] if c['scope_type'] == 'document_review']
        data = m.payload(self.bundle, self.evidence, self.state)
        self.assertEqual(data['countries']['NLD']['status'], 'partial')
        self.assertIn('readiness', data['countries']['NLD']['domains_missing'])
        self.assertEqual(data['runs'][0]['status'], 'partial')

    def test_unavailable_fetch_cannot_generate_evidence(self):
        check = next(c for c in self.bundle['coverage.jsonl'] if c['outcome'] == 'unavailable')
        check['evidence_ids'] = [self.evidence[0]['id']]
        with self.assertRaisesRegex(ValueError, 'Unavailable'):
            self.validate()

    def test_actual_check_must_belong_to_a_run_and_have_a_valid_period(self):
        check = self.bundle['coverage.jsonl'][0]
        for key, bad in [('run_id','missing'),('period_start','unknown'),('period_end','2099-01-01')]:
            old = check[key]
            check[key] = bad
            with self.assertRaises(ValueError):
                self.validate()
            check[key] = old

    def test_geography_of_source_is_not_automatically_applied_to_new_evidence(self):
        data = m.payload(self.bundle, self.evidence, self.state)
        self.assertEqual(data['countries']['HUN']['status'], 'partial')
        self.assertFalse(any(e['id'].startswith('backfill-') and 'hun' in e['id'] for e in self.evidence))

    def test_bis_overlapping_claims_share_one_source_family(self):
        event = next(e for e in self.bundle['events.json']['events'] if e['id'] == 'case-bis-annual-2025')
        self.assertEqual(len(event['links']), 2)
        self.assertEqual(len({l['line_id'] for l in event['links']}), 1)
        self.assertEqual(event['links'][1]['role'], 'overlapping_claim')

    def test_event_cannot_reference_unknown_or_repeated_evidence(self):
        event = self.bundle['events.json']['events'][0]
        event['links'].append(copy.deepcopy(event['links'][0]))
        with self.assertRaisesRegex(ValueError, 'Repeated'):
            self.validate()
        event['links'][-1]['evidence_id'] = 'invented'
        with self.assertRaisesRegex(ValueError, 'Invalid event'):
            self.validate()

    def test_new_run_is_required_and_partial_work_cannot_be_labelled_complete(self):
        self.state['assessment_time'] = (max(m.instant(r['finished_at']) for r in self.bundle['monitoring-runs.jsonl']) + timedelta(hours=1)).isoformat()
        self.state.setdefault('research_scope', {}).pop('monitoring_run_id', None)
        with self.assertRaisesRegex(ValueError, 'structured monitoring run'):
            self.validate()
        self.state['research_scope']['monitoring_run_id'] = self.bundle['monitoring-runs.jsonl'][0]['id']
        self.state['research_scope']['coverage_status'] = 'complete'
        with self.assertRaisesRegex(ValueError, 'incomplete tasks'):
            self.validate()
        self.state['research_scope']['coverage_status'] = 'partial'
        self.validate()

    def test_unobserved_signature_is_not_negative_evidence(self):
        row = dict(id='test-absence',indicator_id='nato-readiness',check_ids=['check-fin-supo'],observed_at='2026-10-28T09:40:00+01:00',result='absent',rationale='TEST',observability='low')
        self.bundle['indicator-observations.jsonl'].append(row)
        with self.assertRaisesRegex(ValueError, 'Absence requires'):
            self.validate()
        row.update(observability='high',baseline_url='https://example.com/test-baseline')
        with self.assertRaisesRegex(ValueError, 'not negative evidence'):
            self.validate()

    def test_failed_case_review_preserves_deadline_and_cannot_close_case(self):
        event = next(e for e in self.bundle['events.json']['events'] if e.get('case_status') == 'open')
        previous = next((r for r in reversed(self.bundle['case-reviews.jsonl']) if r['event_id'] == event['id']), event)
        at = max([m.instant(self.state['assessment_time'])]
                 + [m.instant(r['checked_at']) for r in self.bundle['case-reviews.jsonl']]
                 + [m.instant(c['checked_at']) for c in self.bundle['coverage.jsonl']]) + timedelta(hours=1)
        review = dict(id='test-case',event_id=event['id'],check_ids=['check-fin-supo'],checked_at=at.isoformat(),scheduled_for=previous['next_check_by'],next_check_by=(at+timedelta(days=1)).isoformat(),next_action='TEST retry',summary='TEST unavailable',outcome='unavailable',case_status='closed')
        self.bundle['case-reviews.jsonl'].append(review)
        with self.assertRaisesRegex(ValueError, 'cannot close'):
            self.validate()
        review['case_status'] = 'open'
        self.validate()
        review['scheduled_for'] = '2026-10-28T07:00:00+01:00'
        with self.assertRaisesRegex(ValueError, 'preceding deadline'):
            self.validate()

    def test_document_review_does_not_clear_daily_news_scan(self):
        self.bundle['coverage.jsonl'] = [c for c in self.bundle['coverage.jsonl'] if c['scope_type'] == 'document_review']
        tasks = m.due_tasks(self.bundle, {}, m.instant('2026-10-28T10:00:00+01:00'))
        self.assertIn('source:nld-official', {t['id'] for t in tasks})
        self.assertIn('country:AUT', {t['id'] for t in tasks})
        self.assertIn('monthly:coverage', {t['id'] for t in tasks})

    def test_future_check_does_not_clear_as_of_queue(self):
        self.bundle['coverage.jsonl'] = [dict(source_ids=['nld-official'], scope_type='news_scan', outcome='no_new_relevant', checked_at='2026-10-28T11:00:00+01:00', areas=['NLD'])]
        tasks = m.due_tasks(self.bundle, {}, m.instant('2026-10-28T10:00:00+01:00'))
        self.assertIn('source:nld-official', {t['id'] for t in tasks})

    def test_source_audit_cannot_refresh_country_coverage(self):
        self.bundle['coverage.jsonl'] = [{**self.bundle['coverage.jsonl'][0], 'areas':['MLT'], 'scope_type':'source_audit', 'outcome':'relevant_found', 'checked_at':self.state['assessment_time'], 'domains':list(m.DOMAINS)}]
        country = m.payload(self.bundle, self.evidence, self.state)['countries']['MLT']
        self.assertEqual(country['status'], 'not_checked')
        self.assertIsNone(country['last_success'])
        self.assertEqual(set(country['domains_missing']), set(m.DOMAINS))

    def test_partial_check_does_not_refresh_last_success(self):
        self.bundle['coverage.jsonl'] = [{**self.bundle['coverage.jsonl'][0], 'areas':['MLT'], 'scope_type':'country_audit', 'outcome':'partial', 'checked_at':self.state['assessment_time'], 'domains':list(m.DOMAINS)}]
        country = m.payload(self.bundle, self.evidence, self.state)['countries']['MLT']
        self.assertEqual(country['status'], 'partial')
        self.assertIsNone(country['last_success'])
        self.assertEqual(set(country['domains_missing']), set(m.DOMAINS))

    def test_unknown_metric_without_optional_status_renders_missing_reason(self):
        series = next(s for s in self.bundle['metrics.json']['series'] if s['kind'] == 'operational')
        self.bundle['metric-observations.jsonl'] = [dict(id='test-unknown', series_id=series['id'], method_version=series['method_version'], recorded_at=self.state['assessment_time'], period=self.state['assessment_time'][:10], value=None, stage='unknown', source_urls=['https://example.com/test'], russian_involvement='unknown', causal_basis='TEST causal limit', missing_reason='TEST missing measurement')]
        html = m.effects_content(self.bundle, self.state, self.state['assessment_time'])
        self.assertIn('Neznámé', html)
        self.assertIn('TEST missing measurement', html)

    def test_year_only_dates_do_not_invent_a_day(self):
        self.assertEqual(temporal('2025'), dict(start='2025-01-01',end='2025-12-31',precision='year',planned=False,raw='2025'))

    def test_poll_requires_fieldwork_and_method(self):
        self.bundle['metric-observations.jsonl'][0].pop('fieldwork')
        with self.assertRaisesRegex(ValueError, 'Poll requires'):
            self.validate()

    def test_missing_metric_is_not_implicitly_zero(self):
        self.bundle['metric-observations.jsonl'][0]['value'] = None
        with self.assertRaisesRegex(ValueError, 'Missing value'):
            self.validate()

    def test_metric_method_break_requires_new_series(self):
        self.bundle['metric-observations.jsonl'][0]['method_version'] = 'different'
        with self.assertRaisesRegex(ValueError, 'method mismatch'):
            self.validate()

    def test_wdpi_requires_all_components_and_reproducible_rounding(self):
        self.assertEqual(m.wdpi_total({key:{'score':value} for key,value in zip(('resource_dilution','domestic_pain','self_deterrence'),(75,50,25))}),51)
        self.bundle['wdpi-assessments.jsonl'].append(dict(id='test-score',method_version='anchored-v2',assessment_time='2026-10-28T09:40:00+01:00',components={'resource_dilution':{'score':75}},total=26))
        with self.assertRaisesRegex(ValueError, 'missing components'):
            self.validate()

    def forecast(self):
        return next(f for f in self.bundle['forecast-register.jsonl'] if f['eligible'])

    def resolution(self, outcome='yes'):
        f = self.forecast()
        row = dict(id='test-resolution',forecast_id=f['id'],resolved_at='2027-01-02T10:00:00+01:00',outcome=outcome,event_time='2026-11-01T10:00:00+01:00',evidence_ids=[self.evidence[0]['id']],source_urls=['https://example.com/test'],rationale='TEST only',supersedes=None,coverage_basis='TEST reviewed horizon')
        self.bundle['forecast-resolutions.jsonl'].append(row)
        return row

    def test_frozen_definition_cannot_change_silently(self):
        self.forecast()['definition'] += ' changed'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.validate()

    def test_registration_values_must_match_archived_snapshot(self):
        self.forecast()['p'] = .987
        with self.assertRaisesRegex(ValueError, 'differs from original assessment'):
            m.validate_files(self.bundle, build_site.DATA)

    def test_new_wdpi_method_cannot_be_silently_applied_to_old_inputs(self):
        self.state['wdpi']['method_version'] = 'anchored-v2'
        with self.assertRaisesRegex(ValueError, 'anchored assessment'):
            self.validate()

    def test_no_cannot_be_resolved_before_horizon(self):
        self.resolution('no')['resolved_at'] = '2026-11-02T10:00:00+01:00'
        with self.assertRaisesRegex(ValueError, 'closed horizon'):
            self.validate()

    def test_yes_cannot_be_resolved_outside_frozen_window(self):
        self.resolution()['event_time'] = '2026-01-01T10:00:00+01:00'
        with self.assertRaisesRegex(ValueError, 'outside forecast window'):
            self.validate()

    def test_unknown_outcome_and_legacy_results_are_excluded(self):
        self.resolution('unknown')
        self.validate()
        result = m.evaluation(self.bundle)
        self.assertEqual(result['scored_questions'], 0)
        self.assertIsNone(result['brier'])

    def test_daily_revisions_do_not_inflate_brier_sample(self):
        first = self.forecast()
        self.resolution()
        duplicate = {**first, 'id':'test-later-forecast','p':.99,'forecast_time':'2026-10-29T07:00:00+01:00','registered_at':'2026-10-29T08:00:00+01:00'}
        self.bundle['forecast-register.jsonl'].append(duplicate)
        self.bundle['forecast-resolutions.jsonl'].append({**self.bundle['forecast-resolutions.jsonl'][0], 'id':'test-later-resolution','forecast_id':duplicate['id']})
        self.validate()
        result = m.evaluation(self.bundle)
        self.assertEqual(result['scored_questions'], 1)
        self.assertAlmostEqual(result['brier'], (first['p'] - 1) ** 2)

    def test_correction_must_link_previous_adjudication(self):
        first = self.resolution()
        self.bundle['forecast-resolutions.jsonl'].append({**first,'id':'test-corrected','outcome':'unknown'})
        with self.assertRaisesRegex(ValueError, 'preceding adjudication'):
            self.validate()
        self.bundle['forecast-resolutions.jsonl'][-1]['supersedes'] = first['id']
        self.validate()
        self.assertIsNone(m.evaluation(self.bundle)['brier'])

    def test_validation_failure_does_not_append_a_log(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / 'russia-escalation'
            shutil.copytree(build_site.DATA, data)
            before = (data / 'coverage.jsonl').read_bytes()
            bad = {**self.bundle['coverage.jsonl'][0], 'id':'test-bad','source_ids':['missing']}
            with patch.object(monitor, 'DATA', data), self.assertRaises(ValueError):
                monitor.append_records('coverage.jsonl', [bad])
            self.assertEqual((data / 'coverage.jsonl').read_bytes(), before)

    def test_publication_allowlist_remains_exact(self):
        for name in m.FILES:
            self.assertTrue(publish_update.ALLOWED.fullmatch('russia-escalation/' + name))
        for name in ('experiments/events.json','russia-escalation/private.json','russia-escalation/sources.json.bak','scripts/monitor.py'):
            self.assertFalse(publish_update.ALLOWED.fullmatch(name))

    def test_metadata_mode_rejects_changed_forecast(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder) / 'russia-escalation'
            shutil.copytree(build_site.DATA, data)
            path = data / 'state.json'
            path.write_text(path.read_text() + '\n')
            with patch.object(publish_update, 'DATA', data), self.assertRaisesRegex(ValueError, 'byte-for-byte'):
                publish_update.metadata_guard()

    def test_metadata_mode_does_not_snapshot_or_register(self):
        with patch.object(publish_update, 'validate', return_value=(self.state, [], [])), patch.object(publish_update, 'preserve_history'), patch.object(publish_update, 'metadata_guard'), patch.object(publish_update, 'snapshot') as snapshot, patch.object(publish_update, 'build'), patch('check_site.check'), patch.object(monitor, 'register_forecasts') as register:
            publish_update.prepare(metadata_only=True)
            snapshot.assert_not_called()
            register.assert_not_called()


if __name__ == '__main__':
    unittest.main()
