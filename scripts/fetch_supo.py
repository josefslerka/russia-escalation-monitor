#!/usr/bin/env python3
"""Read Supo's Finnish news archive, falling back to its official RSS.

This read-only helper supplies dated source items and retrieval failures. It does
not create coverage receipts, evidence, or forecast outcomes.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

FINLAND = ZoneInfo('Europe/Helsinki')
SOURCES = Path(__file__).resolve().parents[1] / 'russia-escalation/sources.json'


def official_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'supo.fi', 'www.supo.fi'}:
        raise ValueError('Expected a public HTTPS URL on supo.fi')
    return url


def endpoints():
    source = next(s for s in json.loads(SOURCES.read_text())['sources'] if s['id'] == 'fin-official')
    urls = [source['url'], *source['fallback_urls']]
    if len(urls) != 2 or '/rss' not in urls[1]:
        raise ValueError('Supo needs its news archive followed by its official RSS')
    return [official_url(url) for url in urls]


class NewsArchive(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.current = None
        self.depth = 0
        self.title = False
        self.date_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if tag == 'div':
            if self.current is not None:
                self.depth += 1
            elif 'feed-item' in classes:
                self.current = dict(title='', url='', date='')
                self.depth = 1
        if self.current is None:
            return
        if tag == 'a' and not self.current['url']:
            self.current['url'] = attrs.get('href', '')
            self.title = True
        if tag == 'span':
            if self.date_depth:
                self.date_depth += 1
            elif 'date' in classes:
                self.date_depth = 1

    def handle_endtag(self, tag):
        if self.current is None:
            return
        if tag == 'a':
            self.title = False
        if tag == 'span' and self.date_depth:
            self.date_depth -= 1
        if tag == 'div':
            self.depth -= 1
            if not self.depth:
                self.items.append(self.current)
                self.current = None

    def handle_data(self, data):
        if self.current is not None:
            if self.title:
                self.current['title'] += data
            if self.date_depth:
                self.current['date'] += data


def parse_archive(body):
    parser = NewsArchive()
    parser.feed(body.decode('utf-8-sig'))
    parser.close()
    if parser.current is not None:
        raise ValueError('Truncated Supo news list')
    items = []
    for row in parser.items:
        match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2})\.(\d{2})', row['date'])
        if not match:
            raise ValueError('A Supo news item has no readable publication time')
        day, month, year, hour, minute = map(int, match.groups())
        items.append(dict(title=row['title'].strip(),
                          source_url=official_url(urljoin('https://supo.fi/uutiset', row['url'])),
                          publication_time=datetime(year, month, day, hour, minute, tzinfo=FINLAND).isoformat()))
    return validate_items(items)


def parse_rss(body):
    root = ET.fromstring(body)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('Response is not a Supo RSS feed')
    items = []
    for row in root.findall('./channel/item'):
        raw_time = row.findtext('pubDate')
        if not raw_time:
            raise ValueError('An RSS item has no publication time; cannot omit it')
        at = parsedate_to_datetime(raw_time)
        if at.tzinfo is None:
            raise ValueError('RSS publication time has no timezone')
        items.append(dict(title=(row.findtext('title') or '').strip(),
                          source_url=official_url(row.findtext('link') or ''),
                          publication_time=at.astimezone(FINLAND).isoformat()))
    return validate_items(items)


def validate_items(items):
    if not items or any(not row['title'] for row in items):
        raise ValueError('No readable Supo news items; an empty/challenge page is not a negative finding')
    times = [datetime.fromisoformat(row['publication_time']) for row in items]
    if times != sorted(times, reverse=True):
        raise ValueError('News list is not ordered newest first; review its range manually')
    return items


def fetch(url, timeout):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; RussiaEscalationMonitor/1.0)',
        'Cache-Control': 'no-cache',
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = official_url(response.geturl())
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}')
        body = response.read(4_000_001)
        if len(body) > 4_000_000:
            raise ValueError('Response exceeds the archive size limit')
        return body, final_url, response.status


def collect(start, end, timeout=20):
    if start > end or end > datetime.now(FINLAND).date():
        raise ValueError('Use an ordered publication-date range ending no later than today')
    attempts = []
    partial = None
    for url, parser in zip(endpoints(), [parse_archive, parse_rss]):
        attempt = dict(url=url, format='archive' if parser is parse_archive else 'rss')
        try:
            body, final_url, status = fetch(url, timeout)
            attempt.update(final_url=final_url, http_status=status)
            items = parser(body)
            oldest = date.fromisoformat(items[-1]['publication_time'][:10])
            attempt.update(status='available' if oldest < start else 'partial',
                           item_count=len(items), newest_publication=items[0]['publication_time'],
                           oldest_publication=items[-1]['publication_time'])
            selected = [row for row in items if start <= date.fromisoformat(row['publication_time'][:10]) <= end]
            result = dict(status=attempt['status'], selected_url=url, items=selected,
                          list_span=dict(oldest=items[-1]['publication_time'], newest=items[0]['publication_time']))
            if partial is None or oldest < date.fromisoformat(partial['list_span']['oldest'][:10]):
                partial = result
        except (ValueError, ET.ParseError, OSError, urllib.error.URLError) as exc:
            attempt.update(status='unavailable', error=str(exc))
            if isinstance(exc, urllib.error.HTTPError):
                attempt['http_status'] = exc.code
                exc.close()
        attempt['checked_at'] = datetime.now(timezone.utc).isoformat()
        attempts.append(attempt)
        if attempt['status'] == 'available':
            break
    result = partial or dict(status='unavailable', selected_url=None, items=[], list_span=None)
    return dict(source_id='fin-official', requested_period=dict(start=start.isoformat(), end=end.isoformat(),
                publication_timezone='Europe/Helsinki'), **result, attempts=attempts,
                limitations='Read-only retrieval of one institution. Archive and RSS are the same source line. '
                'Available means a dated list extends before the requested start day, not a completed forecast audit. '
                'Open relevant articles, apply the original exact forecast boundaries, and save actual checks separately. '
                'Partial/unavailable retrieval must never establish no. Publication and indexing lag remain possible.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, required=True, help='First publication date, YYYY-MM-DD')
    parser.add_argument('--end', type=date.fromisoformat, required=True, help='Last publication date, YYYY-MM-DD')
    parser.add_argument('--timeout', type=float, default=20, help='Timeout per route in seconds (default 20)')
    args = parser.parse_args()
    if not 0 < args.timeout <= 30:
        parser.error('--timeout must be between 0 and 30 seconds')
    try:
        result = collect(args.start, args.end, args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'available' else 1


if __name__ == '__main__':
    raise SystemExit(main())
