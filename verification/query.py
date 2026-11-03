"""Read-only queries and source context for the exploratory atomic ledger."""
import argparse
import json
import sqlite3
from contextlib import closing

from .ledger import ROOT

QUERIES = {
    'summary': 'SELECT (SELECT COUNT(*) FROM runs) runs,(SELECT COUNT(*) FROM events) events,(SELECT COUNT(*) FROM calls) attempts,(SELECT COUNT(*) FROM assertions) selected_assertions,(SELECT COUNT(*) FROM propositions) candidate_propositions',
    'assertions': 'SELECT id,run_id,field,actor,quote,predicate,value,valid_time,scope,modality,annotation_status FROM assertion_details ORDER BY run_id,field,start,end',
    'evidence': 'SELECT * FROM evidence_stages ORDER BY run_id,evidence_key',
    'exposures': 'SELECT c.run_id,c.actor,x.mode,COUNT(*) occurrences FROM exposures x JOIN calls c ON c.id=x.call_id GROUP BY c.run_id,c.actor,x.mode ORDER BY c.run_id,c.actor,x.mode',
    'checks': 'SELECT category,method,result,COUNT(*) checks FROM checks GROUP BY category,method,result ORDER BY category,method,result',
    'origins': 'SELECT origin_method,COUNT(*) reports FROM reports GROUP BY origin_method',
    'unatomized': 'SELECT r.run_id,r.field,LENGTH(t.text) characters,r.origin_method FROM reports r JOIN texts t ON t.id=r.text_id WHERE NOT EXISTS(SELECT 1 FROM assertions a WHERE a.report_id=r.id) ORDER BY r.run_id,r.field',
    'lineage': 'SELECT evidence_key,source_id,root_source_id,provider,content_status FROM evidence ORDER BY evidence_key',
}


def assertion_context(db, assertion_id, include_input=False):
    def one(sql,values):
        row = db.execute(sql,values).fetchone()
        return dict(row) if row else None
    assertion = one('SELECT a.*,r.field FROM assertions a JOIN reports r ON r.id=a.report_id WHERE a.id=?',(assertion_id,))
    if assertion is None:
        raise ValueError('Unknown assertion ID for this build; do not remap stale IDs silently.')
    report = one('SELECT * FROM reports WHERE id=?',(assertion['report_id'],))
    proposition = one('SELECT * FROM propositions WHERE id=?',(assertion['proposition_id'],))
    for name in ('value','valid_time','assumptions'):
        proposition[name] = json.loads(proposition[name])
    text = one('SELECT t.*,a.path artifact_path FROM texts t JOIN artifacts a ON a.id=t.artifact_id WHERE t.id=?',(report['text_id'],))
    paragraph_start = text['text'].rfind('\n\n',0,assertion['start'])
    paragraph_start = 0 if paragraph_start<0 else paragraph_start+2
    paragraph_end = text['text'].find('\n\n',assertion['end'])
    paragraph_end = len(text['text']) if paragraph_end<0 else paragraph_end
    checks = [dict(r) for r in db.execute('SELECT category,method,result,details FROM checks WHERE subject_table=? AND subject_id=?',('assertions',assertion_id))]
    for check in checks:
        check['details'] = json.loads(check['details'])
    links = [dict(r) for r in db.execute('SELECT relation,status,basis,evidence_id,mention_id FROM links WHERE assertion_id=?',(assertion_id,))]
    exposures = [dict(r) for r in db.execute('SELECT x.mode,x.evidence_id,x.report_id,x.provenance,t.pointer,t.transform,t.event_id,t.role FROM exposures x JOIN texts t ON t.id=x.text_id WHERE x.call_id=?',(assertion['call_id'],))]
    for exposure in exposures:
        exposure['provenance'] = json.loads(exposure['provenance'])
    result = dict(assertion=assertion,candidate_proposition=proposition,paragraph=dict(start=paragraph_start,end=paragraph_end,text=text['text'][paragraph_start:paragraph_end]),
                  report_source=dict(artifact_path=text['artifact_path'],pointer=text['pointer'],sha256=text['sha256'],origin_method=report['origin_method'],
                                     output_event_id=report['output_event_id'],origin_pointer=report['origin_pointer']),
                  candidate_mapping_notice='Worker proposal; check matches do not independently validate this normalization.',checks=checks,links=links,exposures=exposures)
    if include_input and assertion['call_id']:
        raw = one('SELECT e.raw FROM calls c JOIN events e ON e.id=c.start_event_id WHERE c.id=?',(assertion['call_id'],))
        result['recorded_input_event'] = json.loads(raw['raw'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=['pilot','full'],default='full')
    parser.add_argument('--name',choices=[*QUERIES,'context'],default='summary')
    parser.add_argument('--assertion-id')
    parser.add_argument('--include-input',action='store_true')
    parser.add_argument('--limit',type=int,default=50)
    args = parser.parse_args()
    if args.limit<1 or args.limit>10000:
        parser.error('--limit must be 1..10000')
    destination = ROOT/'verification/data'/args.profile
    manifest = json.loads((destination/'manifest.json').read_text(encoding='utf-8'))
    with closing(sqlite3.connect((destination/'ledger.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        if args.name=='context':
            if not args.assertion_id:
                parser.error('context requires --assertion-id from this build')
            result = assertion_context(db,args.assertion_id,args.include_input)
        else:
            result = [dict(r) for r in db.execute(QUERIES[args.name]+' LIMIT ?',(args.limit,))]
    print(json.dumps(dict(build_id=manifest['build_id'],query=args.name,result=result),indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
