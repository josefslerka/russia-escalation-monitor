#!/usr/bin/env python3
"""Review due monitoring work, register forecasts, and append validated audit records."""
from __future__ import annotations

import argparse
from datetime import datetime
import fcntl
import json
from pathlib import Path
import tempfile

from build_site import DATA, PRAGUE
import monitoring
import forecasting


def context():
    state = json.loads((DATA / 'state.json').read_text())
    evidence = [json.loads(line) for line in (DATA / 'evidence.jsonl').read_text().splitlines() if line.strip()]
    bundle = monitoring.load(DATA)
    monitoring.validate(bundle, evidence, state)
    return bundle, evidence, state


def append_records(name, rows):
    """Validate the complete candidate before replacing any log; keep its exact prefix."""
    if name not in monitoring.LOG_FILES:
        raise ValueError('Only named append-only monitoring logs can be written')
    # A process lock outside the public data directory survives atomic log replacement.
    lock_path = DATA.parent / '.monitoring.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        bundle, evidence, state = context()
        known = {row['id']: row for row in bundle[name]}
        additions = []
        for row in rows:
            if row['id'] in known:
                if row != known[row['id']]:
                    raise ValueError('Existing ID has different contents; append an explicit correction')
                continue
            additions.append(row)
            known[row['id']] = row
        if name in {forecasting.ROUNDS, forecasting.OUTCOMES}:
            field = 'issued_at' if name == forecasting.ROUNDS else 'resolved_at'
            now = datetime.now(PRAGUE)
            if any(not 0 <= (now - forecasting.instant(row[field])).total_seconds() <= 300 for row in additions):
                raise ValueError('New forecast writes must use the actual current time; no backdating')
            if name == forecasting.ROUNDS and any(now >= forecasting.instant(row['window_start']) for row in additions):
                raise ValueError('Actual issuance deadline passed; no backdating into a closed window')
        bundle[name] += additions
        monitoring.validate(bundle, evidence, state)
        monitoring.validate_files(bundle, DATA)
        path = DATA / name
        old = path.read_text()
        if old and not old.endswith('\n'):
            raise ValueError('Log lacks a terminal newline; inspect before appending')
        content = old + ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in additions)
        with tempfile.NamedTemporaryFile('w', dir=DATA, prefix='.monitor-', delete=False, encoding='utf-8') as temporary:
            temporary.write(content)
            temp_path = Path(temporary.name)
        temp_path.replace(path)
        return len(additions)


def register_forecasts():
    bundle, _, state = context()
    now = datetime.now(PRAGUE).isoformat(timespec='seconds')
    rows = []
    for key, hypothesis in state['hypotheses'].items():
        if hypothesis.get('status', 'active') != 'active':
            continue
        # Idempotency also covers the initial manually reviewed registry migration.
        if any(f['question'] == key and f['forecast_time'] == state['assessment_time'] for f in bundle['forecast-register.jsonl']):
            continue
        prior = next((f for f in reversed(bundle['forecast-register.jsonl']) if f['question'] == key and f['definition'] == hypothesis['event_definition']), None)
        criteria = hypothesis.get('resolution_criteria') or (prior['resolution_criteria'] if prior else {'rule': 'Doložit přesnou definici v uloženém okně primární nebo silně nezávisle podloženou evidencí. Nedostatečná atribuce či pozorovatelnost znamená unknown, nikoli no.'})
        digest = monitoring.definition_hash(hypothesis['event_definition'], criteria)
        end = hypothesis.get('forecast_window_end', state['forecast_window_end'])
        eligible = monitoring.instant(now) < monitoring.instant(end)
        rows.append(dict(id='forecast-' + state['assessment_time'] + '-' + key, question=key,
            definition=hypothesis['event_definition'], definition_hash=digest,
            definition_version=hypothesis.get('definition_version', 1), resolution_criteria=criteria,
            p=hypothesis['p'], forecast_time=state['assessment_time'], registered_at=now,
            window_start=hypothesis.get('forecast_window_start', state['forecast_window_start']), window_end=end,
            report=Path(state['last_report']).name, cohort=key + '-' + digest[:12] + '-' + hypothesis['horizon'],
            eligible=eligible, exclusion_reason='' if eligible else 'Registrace po skončení horizontu.'))
    return append_records('forecast-register.jsonl', rows) if rows else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    due = sub.add_parser('due', help='Print pending tasks; this does not perform or log any checks')
    due.add_argument('--at', help='Timezone-aware date for a reproducible queue; default now')
    sub.add_parser('validate')
    sub.add_parser('register', help='Freeze current active forecast definitions and probabilities once')
    sub.add_parser('origins', help='Print the original fixed boundaries for the next long-horizon assessment')
    append = sub.add_parser('append', help='Append a JSON object or array after validating all references')
    append.add_argument('log', choices=monitoring.LOG_FILES)
    append.add_argument('--input', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'register':
        print(f'Registered {register_forecasts()} forecasts')
    elif args.command == 'append':
        rows = json.loads(args.input.read_text())
        print(f'Appended {append_records(args.log, rows if isinstance(rows, list) else [rows])} records')
    else:
        bundle, _, _ = context()
        if args.command == 'validate':
            print('Monitoring metadata and audit references valid')
        elif args.command == 'origins':
            print(json.dumps(forecasting.legacy_origins(bundle, state), ensure_ascii=False, indent=2))
        else:
            at = monitoring.instant(args.at) if args.at else datetime.now(PRAGUE)
            watchlist = json.loads((DATA / 'watchlist.json').read_text())
            print(json.dumps({'as_of': at.isoformat(), 'tasks': monitoring.due_tasks(bundle, watchlist, at)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f'Monitoring stopped: {exc}') from exc
