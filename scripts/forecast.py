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
    for name in ('plan', 'evaluate', 'coherence', 'long-review'):
        p = sub.add_parser(name)
        p.add_argument('--at', help='Read-only timezone-aware historical/future view')
    candidates=sub.add_parser('candidates')
    candidates.add_argument('--forecast-id',required=True)
    candidates.add_argument('--at')
    for name in ('issue', 'resolve', 'review-candidate', 'benchmark'):
        p = sub.add_parser(name)
        p.add_argument('--input', required=True, type=Path)
    args = parser.parse_args()
    bundle, evidence, state = monitor.context()
    now = datetime.now(timezone.utc)
    if args.command in {'candidates','coherence','long-review'}:
        at=f.instant(args.at) if args.at else now
        if args.command=='candidates':
            issue=next(r for r in bundle[f.ROUNDS] if r['id']==args.forecast_id)
            data=f.methods().candidate_status(bundle,evidence,issue,at)
        elif args.command=='long-review':data=f.methods().long_review(bundle,evidence,state,at)
        else:data=dict(temporal=f.methods().coherence([r for r in bundle[f.ROUNDS] if f.instant(r['issued_at'])<=at]),
                       related_questions=f.methods().related_comparisons(bundle,at))
        print(json.dumps(data,ensure_ascii=False,indent=2));return
    if args.command in {'plan', 'evaluate'}:
        at = f.instant(args.at) if args.at else now
        data = f.evaluate(bundle, at)
        if args.command == 'plan':
            pending = [r for r in data['rows'] if r['status'] in {'awaiting_issue', 'missed', 'awaiting_resolution', 'unknown', 'awaiting_final_resolution'}]
            templates = []
            for row in pending:
                if row['status'] == 'awaiting_issue':
                    template=dict(question_id=row['question_id'], horizon_days=row['horizon_days'],
                                          window_number=row['window_number'], p=None, abstention_reason='',
                                          source_cutoff=None, rationale='', alternative='', evidence_ids=[], check_ids=[], source_urls=[])
                    if row['protocol']=='fixed-v2':
                        template.update(estimation_mode='blind',dependence_note='',related_question_note='',temporal_profile=dict(shape='uncertain',rationale=''),
                                        estimation_passes=[dict(id='pass-'+a,approach=a,p=None,rationale='',completed_at=None,check_ids=[],
                                                               **({'base_rate':dict(status='unavailable',note='')} if a=='reference_class' else {}))
                                                           for a in ['reference_class','indicators','alternative_scenario']])
                    templates.append(template)
            data = {'as_of':at.isoformat(),'tasks':f.tasks(bundle,at),'pending':pending,'issue_templates':templates,
                    'related_question_context':f.methods().related_context(bundle,at),
                    'assessment_scope':f.assessment_scope(bundle,at),
                    'instruction':'Fill researched probabilities and actual references. Null p needs an explicit abstention reason. This command performs no research or writes.'}
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    raw = json.loads(args.input.read_text())
    rows = raw if isinstance(raw, list) else [raw]
    if args.command == 'issue':
        rows = [f.make_issue(f.methods().protocol_for(bundle,row['question_id']), row, now) for row in rows]
        name = f.ROUNDS
    elif args.command == 'resolve':
        for row in rows:
            if {'id','resolved_at'} & row.keys():
                raise ValueError('Outcome ID/time are generated at actual adjudication')
        rows = [{**row, 'id':'fixed-outcome-'+uuid.uuid4().hex, 'resolved_at':now.isoformat()} for row in rows]
        name = f.OUTCOMES
    elif args.command=='review-candidate':
        if any({'id','reviewed_at'} & row.keys() for row in rows):raise ValueError('Candidate review ID/time are generated at actual review')
        rows=[{**row,'id':'candidate-review-'+uuid.uuid4().hex,'reviewed_at':now.isoformat()} for row in rows]
        name=f.methods().CANDIDATES
    else:
        if any({'id','observed_at','recorded_at'} & row.keys() for row in rows):raise ValueError('Benchmark receipt times are generated after own issuance')
        rows=[{**row,'id':'benchmark-'+uuid.uuid4().hex,'observed_at':now.isoformat(),'recorded_at':now.isoformat()} for row in rows]
        name=f.methods().BENCHMARKS
    print(f'Appended {monitor.append_records(name, rows)} records to {name}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f'Fixed forecast stopped: {exc}') from exc
