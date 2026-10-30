#!/usr/bin/env python3
"""Issue and resolve researched fixed-window forecasts; never estimate p automatically."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import forecasting as f
import monitor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'evaluate'):
        p = sub.add_parser(name)
        p.add_argument('--at', help='Read-only timezone-aware historical/future view')
    for name in ('issue', 'resolve'):
        p = sub.add_parser(name)
        p.add_argument('--input', required=True, type=Path)
    args = parser.parse_args()
    bundle, _, _ = monitor.context()
    now = datetime.now(timezone.utc)
    if args.command in {'plan', 'evaluate'}:
        at = f.instant(args.at) if args.at else now
        data = f.evaluate(bundle, at)
        if args.command == 'plan':
            pending = [r for r in data['rows'] if r['status'] in {'awaiting_issue', 'missed', 'awaiting_resolution', 'unknown'}]
            templates = []
            for row in pending:
                if row['status'] == 'awaiting_issue':
                    templates.append(dict(question_id=row['question_id'], horizon_days=row['horizon_days'],
                                          window_number=row['window_number'], p=None, abstention_reason='',
                                          source_cutoff=None, rationale='', alternative='', evidence_ids=[], check_ids=[], source_urls=[]))
            data = {'as_of':at.isoformat(),'tasks':f.tasks(bundle,at),'pending':pending,'issue_templates':templates,
                    'assessment_scope':f.assessment_scope(bundle,at),
                    'instruction':'Fill researched probabilities and actual references. Null p needs an explicit abstention reason. This command performs no research or writes.'}
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    raw = json.loads(args.input.read_text())
    rows = raw if isinstance(raw, list) else [raw]
    if args.command == 'issue':
        rows = [f.make_issue(bundle[f.PROTOCOL], row, now) for row in rows]
        name = f.ROUNDS
    else:
        for row in rows:
            if {'id','resolved_at'} & row.keys():
                raise ValueError('Outcome ID/time are generated at actual adjudication')
        rows = [{**row, 'id':'fixed-outcome-'+uuid.uuid4().hex, 'resolved_at':now.isoformat()} for row in rows]
        name = f.OUTCOMES
    print(f'Appended {monitor.append_records(name, rows)} records to {name}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f'Fixed forecast stopped: {exc}') from exc
