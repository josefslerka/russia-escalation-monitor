"""Guard against invented dates, narrowed geography and lost evidence in the map."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import build_site
import publish_update
from signals import geography, payload, temporal, safe_url


class SignalChecks(unittest.TestCase):
    def test_monthly_precision_is_retained(self):
        value = temporal('2026-09')
        self.assertEqual((value['start'], value['end'], value['precision']), ('2026-09-01', '2026-09-30', 'month'))

    def test_interval_is_not_replaced_by_discovery_day(self):
        value = temporal('2026-09-14/2026-09-16')
        self.assertEqual((value['start'], value['end']), ('2026-09-14', '2026-09-16'))

    def test_unknown_and_disputed_dates_are_not_guessed(self):
        for raw in [None, 'unknown_crash_time_discovered_2026-10-21',
                    'on_or_before_2026-10-20', '2026-10-13 nebo dříve; přesné datum neurčeno',
                    'planned_2026-10-29_disputed_2026-10-27', 'historical_campaign_and_august2026_contacts']:
            self.assertIsNone(temporal(raw)['start'], raw)

    def test_planned_future_interval_is_labelled(self):
        value = temporal('planned_2026-10-24/2026-12-04')
        self.assertTrue(value['planned'])
        self.assertEqual(value['end'], '2026-12-04')

    def test_timezone_conversion_uses_prague_day(self):
        self.assertEqual(temporal('2026-10-23T23:30:00Z')['start'], '2026-10-24')

    def test_publication_note_does_not_become_a_false_interval(self):
        value = temporal('2026-09-25 (FAZ specificity; initial ARD suspicion 2026-09-03)')
        self.assertEqual((value['start'], value['end']), ('2026-09-25', '2026-09-25'))

    def test_unsafe_source_urls_are_not_links(self):
        for value in ['javascript:alert(1)', 'data:text/html,x', '/Users/private/file', 'https://host/\nattack']:
            self.assertIsNone(safe_url(value))

    def test_annotations_cannot_reference_other_records_or_invent_area_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'geography.json'
            for entries in [{'other': {'areas': ['POL']}}, {'a': {'areas': ['MADEUP']}}]:
                path.write_text(json.dumps({'schema_version': 1, 'entries': entries}))
                with self.assertRaises(ValueError):
                    geography(path, [{'id': 'a'}])

    def test_missing_annotation_stays_unknown(self):
        state = {'assessment_time': '2026-10-27T10:31:36+01:00', 'last_report': 'reports/2026-10-27-1031.md'}
        result = payload(state, [{'id': 'new', 'summary': 'NATO warning from a Polish speaker'}], {'entries': {}})
        self.assertEqual(result['records'][0]['areas'], [])
        self.assertEqual(result['unannotated_count'], 1)

    def test_daily_publication_accepts_only_the_named_geography_sidecar(self):
        self.assertTrue(publish_update.ALLOWED.fullmatch('russia-escalation/geography.json'))
        for path in ['russia-escalation/private-geography.json', 'russia-escalation/data/signals.json', 'experiments/geography.json']:
            self.assertFalse(publish_update.ALLOWED.fullmatch(path))

    def test_real_ledger_is_complete_and_general_warning_stays_general(self):
        state, evidence, _ = build_site.validate()
        result = payload(state, evidence, geography(build_site.DATA / 'geography.json', evidence))
        self.assertEqual(len(result['records']), len(evidence))
        self.assertEqual({record['id'] for record in result['records']}, {record['id'] for record in evidence})
        warning = next(record for record in result['records'] if record['id'] == 'evt-20260806-us-intel-nato-test')
        self.assertEqual(warning['areas'], ['NATO'])
        attribution = next(record for record in result['records'] if record['id'] == 'evt-20261026-sri-carfil-attribution')
        self.assertEqual(attribution['times']['event']['start'], '2026-09-14')
        self.assertEqual(attribution['times']['publication']['start'], '2026-10-26')
        self.assertEqual(set(attribution['areas']), {'ROU', 'DEU', 'POL'})

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the browser filter unit checks')
    def test_browser_filter_semantics(self):
        result = subprocess.run(['node', '--test', str(Path(__file__).with_name('test_signals_core.cjs'))], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
