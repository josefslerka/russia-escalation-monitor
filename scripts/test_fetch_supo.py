"""A blocked or truncated Supo archive must not masquerade as a negative audit."""
from datetime import date
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import fetch_supo as s

ARCHIVE = 'https://supo.fi/uutiset'
RSS = ARCHIVE + '/-/asset_publisher/yQeKxbecV9k4/rss'
START, END = date(2026, 10, 31), date(2026, 11, 7)


def rss_item(day, suffix):
    return (f'<item><title>TEST ONLY {suffix}</title><link>https://supo.fi/-/test-{suffix}</link>'
            f'<pubDate>{day}</pubDate></item>')


def rss(*items):
    return ('<rss version="2.0"><channel>' + ''.join(items) + '</channel></rss>').encode()


NEWS = rss(rss_item('Thu, 05 Nov 2026 12:00:00 GMT', 'new'),
           rss_item('Tue, 27 Oct 2026 12:47:00 GMT', 'old'))
OLD_HTML = b'''<div class="feed-item simple">
<h4 class="feed-item__heading"><a href="/-/test-old">TEST ONLY &amp; archive</a></h4>
<div class="meta"><span class="date"><span class="sr-only">Julkaisuajankohta:</span>27.10.2026 14.47</span></div>
</div>'''


class SupoRetrieval(unittest.TestCase):
    def collect(self, responses):
        with patch.object(s, 'endpoints', return_value=[ARCHIVE, RSS]), patch.object(s, 'fetch', side_effect=responses) as request:
            result = s.collect(START, END)
        return result, request

    def test_registry_uses_news_and_same_institution_rss(self):
        self.assertEqual(s.endpoints(), [ARCHIVE, RSS])

    def test_403_falls_back_to_rss_and_preserves_failure_and_real_dates(self):
        result, request = self.collect([HTTPError(ARCHIVE, 403, 'Forbidden', {}, None), (NEWS, RSS, 200)])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result['source_id'], 'fin-official')
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['selected_url'], RSS)
        self.assertEqual(result['attempts'][0]['http_status'], 403)
        self.assertEqual(result['attempts'][0]['status'], 'unavailable')
        self.assertEqual(result['items'], [dict(title='TEST ONLY new', source_url='https://supo.fi/-/test-new',
                                               publication_time='2026-11-05T14:00:00+02:00')])
        self.assertNotIn('outcome', result)

    def test_200_security_page_is_not_a_successful_empty_archive(self):
        result, _ = self.collect([(b'<html>Please wait: security validation</html>', ARCHIVE, 200),
                                  (NEWS, RSS, 200)])
        self.assertEqual(result['selected_url'], RSS)
        self.assertEqual(result['attempts'][0]['status'], 'unavailable')
        self.assertEqual(result['attempts'][0]['http_status'], 200)
        self.assertIn('empty/challenge', result['attempts'][0]['error'])

    def test_both_routes_blocked_remain_unavailable(self):
        result, _ = self.collect([URLError('TEST timeout'), URLError('TEST reset')])
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['selected_url'])
        self.assertIsNone(result['list_span'])
        self.assertEqual(result['items'], [])
        self.assertEqual(len(result['attempts']), 2)

    def test_successful_dated_archive_needs_no_repeated_blocked_route(self):
        result, request = self.collect([(OLD_HTML, ARCHIVE, 200)])
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['items'], [])
        self.assertEqual(result['list_span']['newest'], '2026-10-27T14:47:00+02:00')

    def test_archive_truncated_on_start_day_still_tries_longer_rss(self):
        limited = OLD_HTML.replace(b'27.10.2026 14.47', b'31.10.2026 14.47')
        result, _ = self.collect([(limited, ARCHIVE, 200), (NEWS, RSS, 200)])
        self.assertEqual(result['attempts'][0]['status'], 'partial')
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['selected_url'], RSS)

    def test_missing_older_history_cannot_be_complete(self):
        limited = OLD_HTML.replace(b'27.10.2026 14.47', b'5.11.2026 14.47')
        result, _ = self.collect([(limited, ARCHIVE, 200), URLError('TEST RSS blocked')])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(len(result['items']), 1)

    def test_undated_rss_item_is_not_silently_dropped(self):
        broken = NEWS.replace(b'<pubDate>Thu, 05 Nov 2026 12:00:00 GMT</pubDate>', b'')
        result, _ = self.collect([URLError('TEST blocked'), (broken, RSS, 200)])
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('cannot omit', result['attempts'][1]['error'])

    def test_empty_rss_and_broken_xml_are_unavailable(self):
        for body in [rss(), b'<rss><channel>']:
            with self.subTest(body=body):
                result, _ = self.collect([URLError('TEST blocked'), (body, RSS, 200)])
                self.assertEqual(result['status'], 'unavailable')

    def test_official_url_and_time_zone_are_required(self):
        for body in [NEWS.replace(b'https://supo.fi/-/test-new', b'https://example.org/foreign'),
                     NEWS.replace(b'12:00:00 GMT', b'12:00:00')]:
            with self.subTest(body=body):
                result, _ = self.collect([URLError('TEST blocked'), (body, RSS, 200)])
                self.assertEqual(result['status'], 'unavailable')

    def test_cli_reports_nonzero_for_incomplete_retrieval(self):
        with patch('sys.argv', ['fetch_supo.py', '--start', START.isoformat(), '--end', END.isoformat()]), \
             patch.object(s, 'collect', return_value={'status': 'unavailable', 'attempts': []}), \
             patch('sys.stdout', new_callable=io.StringIO) as stdout:
            self.assertEqual(s.main(), 1)
            self.assertEqual(json.loads(stdout.getvalue())['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
