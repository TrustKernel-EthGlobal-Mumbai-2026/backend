"""Local descriptive progress review of new live-source sessions only.

Standard library, no model/source clients, credentials or budget writes. Source
and semantic status remain separate from observable invocation/access facts.
"""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid
from urllib.parse import parse_qsl,urlencode,urlsplit,urlunsplit

ROOT=Path(__file__).resolve().parents[1]
VERSION='live-session-review-0.1'
LIVE_MODES={'live_native_market_sources','paid_live_native_sources','live_native','live'}
SECRET_QUERY={'api_key','apikey','key','token','access_token','signature','password','secret','crumb','sessionid','csrf','csrftoken'}
LIMITS=[
    'Actual live provider results may differ across concurrent arms; no identical evidence control is claimed.',
    'Known token/charge subtotals exclude unknown usage; retained reservations are not zero usage or an invoice.',
    'Raw source hashes, timestamps and exact input content do not establish publisher authenticity, attention or private reliance.',
    'Provider bar/publication time may be absent or ambiguous; a daily Close can be an incomplete bar rather than a current tick.',
    'Claims and report semantics remain provisional; no intelligence rank, causal uplift, suitability or automatic feedback.',
    'Active integrity checks establish the named common recorded prefix; closed traces require exact full index parity.',
]


def _utc():return datetime.now(timezone.utc).isoformat()
def _hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
def _text_hash(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _load(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8')),None
    except FileNotFoundError:return {},'not_written_yet'
    except (ValueError,OSError) as exc:return {},type(exc).__name__


def _money(value):
    if isinstance(value,bool) or value is None:return None
    try:parsed=Decimal(str(value))
    except (InvalidOperation,ValueError):return None
    return parsed if parsed.is_finite() and parsed>=0 else None


def _safe_url(value):
    try:
        parts=urlsplit(str(value))
        query=[(k,'[REDACTED]' if k.lower() in SECRET_QUERY else v) for k,v in parse_qsl(parts.query,keep_blank_values=True)]
        return urlunsplit((parts.scheme,parts.netloc.split('@')[-1],parts.path,urlencode(query),'')).strip()
    except ValueError:return '[INVALID_URL]'


def _actor(event):
    metadata=event.get('payload',{}).get('metadata',{}).get('metadata',{})
    checkpoint=metadata.get('langgraph_checkpoint_ns') or metadata.get('checkpoint_ns') or ''
    return checkpoint.split(':',1)[0] if checkpoint else None


def _messages(event):
    result=[]
    def walk(value,pointer):
        if isinstance(value,list):
            for i,item in enumerate(value):walk(item,pointer+'/'+str(i))
        elif isinstance(value,dict) and isinstance(value.get('content'),str):
            result.append({'pointer':pointer+'/content','role':value.get('type') or value.get('role'),
                           'name':value.get('name'),'content':value['content'],'tool_call_id':value.get('tool_call_id')})
    walk(event.get('payload',{}).get('messages',[]),'/payload/messages')
    return result


def _generation_texts(event):
    for bi,batch in enumerate(event.get('payload',{}).get('response',{}).get('generations',[])):
        for gi,generation in enumerate(batch):
            if isinstance(generation.get('text'),str) and generation['text']:
                yield generation['text'],f'/payload/response/generations/{bi}/{gi}/text',generation.get('message',{})


def read_trace(directory,closed=False):
    """Snapshot JSONL and RO index; active append/commit skew is explicit."""
    directory=Path(directory);raw_path=directory/'trace.jsonl';database=directory/'trace.sqlite'
    if not raw_path.exists():
        return [],{'status':'INCONCLUSIVE','reason':'TRACE_NOT_WRITTEN','closed':closed,'verified_events':0}
    raw=raw_path.read_bytes();lines=raw.splitlines(keepends=True);events=[];issues=[];tail=False;previous=None
    for i,line in enumerate(lines,1):
        if i==len(lines) and not line.endswith(b'\n'):
            tail=True
            if closed:issues.append('CLOSED_TRACE_HAS_UNCOMMITTED_TAIL')
            break
        try:event=json.loads(line)
        except (ValueError,UnicodeError):issues.append(f'INVALID_JSON_AT_LINE_{i}');break
        if not isinstance(event,dict):issues.append(f'NONOBJECT_EVENT_AT_LINE_{i}');break
        required={'seq','event_id','run_id','timestamp','kind','span_id','parent_id','payload','event_hash','previous_hash'}
        if not required<=event.keys() or not isinstance(event['payload'],dict):
            issues.append(f'EVENT_SCHEMA_MISSING_AT_{i}');break
        body=dict(event);saved=body.pop('event_hash',None)
        if event.get('seq')!=i or event.get('previous_hash')!=previous or saved!=_hash(body):
            issues.append(f'HASHCHAIN_OR_SEQUENCE_MISMATCH_AT_{i}');break
        if events and event.get('run_id')!=events[0].get('run_id'):
            issues.append(f'RUN_ID_CHANGED_AT_{i}');break
        events.append(event);previous=saved
    status='ERROR' if issues else ('PASS' if events else 'INCONCLUSIVE')
    integrity={'status':status,'closed':closed,'scope':'closed_full_trace' if closed else 'active_common_recorded_prefix',
        'raw_snapshot_sha256':hashlib.sha256(raw).hexdigest(),'raw_snapshot_bytes':len(raw),'verified_events':len(events),
        'partial_last_line':tail,'hashchain_status':'ERROR' if issues else 'PASS','issues':issues,
        'sqlite_status':'NOT_READ','sqlite_rows':None,'common_rows':0,'raw_minus_index':None}
    if not database.exists():
        integrity.update(sqlite_status='MISSING',status='ERROR' if closed else 'INCONCLUSIVE')
        return events,integrity
    try:
        with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
            db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            rows=db.execute('SELECT seq,event_id,run_id,timestamp,kind,span_id,parent_id,payload_json,event_hash FROM events ORDER BY seq').fetchall()
        actual=[(*row[:7],json.loads(row[7]),row[8]) for row in rows]
        expected=[(e['seq'],e['event_id'],e['run_id'],e['timestamp'],e['kind'],e['span_id'],e['parent_id'],e['payload'],e['event_hash']) for e in events]
        n=min(len(actual),len(expected));same=actual[:n]==expected[:n]
        integrity.update(sqlite_rows=len(actual),common_rows=n,raw_minus_index=len(expected)-len(actual))
        if not same:
            integrity.update(status='ERROR',sqlite_status='COMMON_PREFIX_MISMATCH')
        elif closed and len(actual)!=len(expected):
            integrity.update(status='ERROR',sqlite_status='CLOSED_COUNT_MISMATCH')
        elif not n and events:
            integrity.update(status='INCONCLUSIVE' if not closed else 'ERROR',sqlite_status='INDEX_PENDING')
        else:
            integrity['sqlite_status']='EXACT_PARITY' if len(actual)==len(expected) else 'ACTIVE_PREFIX_PARITY_WITH_LAG'
    except (sqlite3.Error,ValueError,OSError,KeyError) as exc:
        integrity.update(status='ERROR' if closed else 'INCONCLUSIVE',sqlite_status='READ_ERROR',sqlite_error_type=type(exc).__name__)
    return events,integrity


def _usage(events):
    known={};completed=[];no_usage=[]
    settlement_usage={}
    for event in events:
        if event['kind']=='budget.settled':
            p=event['payload'];u=p.get('usage');identity=p.get('response_id')
            if identity and isinstance(u,dict) and type(u.get('input_tokens')) is int and type(u.get('output_tokens')) is int and min(u['input_tokens'],u['output_tokens'])>=0:
                settlement_usage[identity]={'input_tokens':u['input_tokens'],'output_tokens':u['output_tokens'],
                    'identity_source':'budget_settlement_response_id','event_seq':event['seq']}
    for event in events:
        if event['kind']!='llm.end':continue
        completed.append(event['span_id']);found={};observed_ids=set()
        # Never search llm.start prompts: copied earlier usage would be recounted.
        def walk(value):
            if isinstance(value,dict):
                usage=value.get('usage_metadata');identity=value.get('response_metadata',{}).get('id') or value.get('id')
                if isinstance(identity,str):observed_ids.add(identity)
                if isinstance(usage,dict):
                    inputs,outputs=usage.get('input_tokens'),usage.get('output_tokens')
                    if type(inputs) is int and type(outputs) is int and inputs>=0 and outputs>=0:
                        found[identity or 'span:'+str(event['span_id'])]={'input_tokens':inputs,'output_tokens':outputs,
                            'identity_source':'response_id' if identity else 'span_fallback','event_seq':event['seq']}
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        walk(event.get('payload',{}).get('response',{}))
        for identity in observed_ids:
            if identity not in found and identity in settlement_usage:found[identity]=settlement_usage[identity]
        if not found:no_usage.append({'span_id':event['span_id'],'event_seq':event['seq']})
        for identity,usage in found.items():
            if identity not in known:known[identity]=usage
    return {'usage_calls':len(known),'completed_events_without_usage':no_usage,
        'input_tokens':sum(x['input_tokens'] for x in known.values()) if known else None,
        'output_tokens':sum(x['output_tokens'] for x in known.values()) if known else None,
        'usage_complete_for_completed_events':not no_usage,'usage_records':[dict(response_id=k,**v) for k,v in known.items()]}


def _charges(events):
    reserved={};settled={};unknown=set();invalid=[]
    for event in events:
        payload=event['payload'];identity=payload.get('request_id')
        if event['kind']=='budget.reserved':
            if not identity:invalid.append({'seq':event['seq'],'reason':'reservation_without_request_id'});continue
            amount=_money(payload.get('reserved_usd'))
            if amount is None:invalid.append({'seq':event['seq'],'reason':'unknown_reservation_amount'})
            reserved[identity]=amount
        elif event['kind']=='budget.settled':
            if not identity:invalid.append({'seq':event['seq'],'reason':'settlement_without_request_id'});continue
            amount=_money(payload.get('charged_upper_usd'))
            if amount is None:invalid.append({'seq':event['seq'],'reason':'unknown_settlement_charge'})
            settled[identity]=amount
        elif event['kind']=='budget.usage_unknown' and identity:unknown.add(identity)
    pending={identity:value for identity,value in reserved.items() if identity not in settled}
    return {'request_ids':sorted(set(reserved)|set(settled)),'reserved_requests':len(reserved),'settled_requests':len(settled),
        'known_charged_upper_usd':float(sum((x for x in settled.values() if x is not None),Decimal(0))),
        'pending_request_ids':sorted(pending),'known_pending_reservation_usd':float(sum((x for x in pending.values() if x is not None),Decimal(0))),
        'pending_requests':len(pending),'usage_unknown_request_ids':sorted(unknown),'accounting_issues':invalid,
        'all_observed_reservations_settled':bool(reserved) and not pending and not invalid,
        'scope':'Observed trace requests only; pending holds retained, not treated as zero cost.'}


def budget_snapshot(path,session_request_ids):
    """Never constructs Budget or opens a source database for writing."""
    path=Path(path)
    result={'path':str(path),'status':'INCONCLUSIVE','session_request_ids':sorted(session_request_ids),
            'scope':'Read-only cumulative snapshot, including earlier charges and unknown holds.'}
    if not path.exists():result['reason']='BUDGET_DB_UNAVAILABLE';return result
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
            db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            balance=db.execute('SELECT reserved FROM budget WHERE id=1').fetchone()
            policy=db.execute('SELECT initial_limit,active_limit,hard_limit FROM budget_policy WHERE id=1').fetchone()
            requests=db.execute('SELECT id,reserved,charge,status,response_id FROM requests').fetchall()
        if balance is None or policy is None or _money(balance[0]) is None:raise ValueError('invalid_budget_snapshot')
        pending=[r for r in requests if r[3]!='settled'];settled=[r for r in requests if r[3]=='settled']
        pending_amounts=[_money(r[1]) for r in pending];charges=[_money(r[2]) for r in settled]
        local=[r for r in requests if r[0] in session_request_ids]
        result.update(status='PASS',committed_upper_plus_holds_usd=balance[0],initial_limit_usd=policy[0],
            active_limit_usd=policy[1],hard_limit_usd=policy[2],request_status_counts=dict(Counter(r[3] for r in requests)),
            pending_or_unknown_requests=len(pending),pending_or_unknown_reserved_usd=float(sum((x for x in pending_amounts if x is not None),Decimal(0))),
            known_settled_request_charges_usd=float(sum((x for x in charges if x is not None),Decimal(0))),
            amounts_complete=all(x is not None for x in pending_amounts+charges),
            session_requests=[{'request_id':r[0],'reserved_usd':r[1],'charged_upper_usd':r[2],
                               'status':r[3],'response_id':r[4]} for r in local],
            missing_session_request_ids=sorted(set(session_request_ids)-{r[0] for r in local}),
            older_unknown_holds_not_released=True)
    except (sqlite3.Error,ValueError,OSError) as exc:result.update(reason='BUDGET_SNAPSHOT_UNAVAILABLE',error_type=type(exc).__name__)
    return result


def _sources(events):
    starts=[e for e in events if e['kind']=='llm.start'];result=[]
    for event in events:
        if event['kind'] not in ('evidence.retrieved','source.tool.error'):continue
        p=event['payload'];content=p.get('content')
        if not isinstance(content,str):content=None
        item={'event_seq':event['seq'],'event_id':event['event_id'],'event_hash':event['event_hash'],
            'evidence_id':p.get('evidence_id'),'tool':p.get('tool'),'provider':p.get('provider'),
            'request':p.get('request'),'status':p.get('source_status') or ('ERROR' if event['kind']=='source.tool.error' else 'UNKNOWN'),
            'requested_at':p.get('requested_at'),'retrieved_at':p.get('retrieved_at'),
            'source_urls':[_safe_url(url) for url in p.get('source_urls',[])],
            'http_ids':p.get('http_ids',[]),'source_time_fields':p.get('source_time_fields',[]),
            'source_time_precision':'provider_declared_only' if p.get('source_time_fields') else 'UNKNOWN',
            'cache_status':p.get('cache_status','UNKNOWN'),'cache_files':p.get('cache_files',[]),
            'recorded_content_hash':p.get('content_hash'),'saved_content_sha256':_text_hash(content) if content is not None else None,
            'content':content,'error_type':p.get('error_type'),'input_exposures':[],
            'limits':['Saved/redacted string identity only; no private attention or independent source corroboration.',
                      'Absent provider time remains unknown; daily values may include an incomplete current bar.']}
        item['recorded_hash_matches_saved_content']=(p.get('content_hash')==item['saved_content_sha256']) if content is not None and p.get('content_hash') else None
        item['request_key']=_hash({'tool':item['tool'],'provider':item['provider'],'request':item['request']})
        if content:
            for start in starts:
                if start['seq']<=event['seq']:continue
                for message in _messages(start):
                    offset=message['content'].find(content)
                    if offset>=0:
                        item['input_exposures'].append({'input_seq':start['seq'],'input_event_id':start['event_id'],
                            'call_span_id':start['span_id'],'actor':_actor(start),'pointer':message['pointer'],
                            'role':message['role'],'tool_call_id':message['tool_call_id'],
                            'start':offset,'end':offset+len(content),'mode':'exact_saved_content_in_recorded_input',
                            'causal_reliance_established':False})
        result.append(item)
    return result


def _protocol(events,final,config):
    calls={e['span_id']:e for e in events if e['kind']=='llm.start'}
    report=final.get('market_report')
    candidates=[]
    for event in events:
        if event['kind']!='llm.end':continue
        start=calls.get(event['span_id'])
        if start is None or _actor(start)!='Market Analyst':continue
        checkpoint=start['payload'].get('metadata',{}).get('metadata',{}).get('langgraph_checkpoint_ns','')
        for text,pointer,message in _generation_texts(event):
            if report and text==report or not report and 'wrap_up' in checkpoint and not message.get('tool_calls'):
                candidates.append((event,start,text,pointer))
    result={'status':'INCONCLUSIVE','reason':'MARKET_REPORT_NOT_YET_SOURCE_LINKED','required_tool':'get_verified_market_snapshot',
            'max_tool_rounds':config.get('max_tool_rounds'),'finding_scope':'Observed original before-report invocation, not factual support.'}
    if len(candidates)!=1:return {**result,'candidate_origins':len(candidates)}
    end,start,text,pointer=candidates[0];messages=_messages(start);joined='\n'.join(m['content'] for m in messages)
    instructions=[]
    for message in messages:
        match=re.search(r'Before writing the final report,\s*call\s+get_verified_market_snapshot\b',message['content'])
        if match:instructions.append({'input_seq':start['seq'],'pointer':message['pointer'],'start':match.start(),'end':match.end(),'quote':match.group()})
    prefix=[e for e in events if e['seq']<end['seq']]
    complete=[e['seq'] for e in prefix]==list(range(1,end['seq']))
    inv=[e for e in prefix if e['kind']=='tool.start' and e['payload'].get('tool',{}).get('name')=='get_verified_market_snapshot']
    known=[e for e in inv if _actor(e)=='Market Analyst'];unassigned=[e for e in inv if _actor(e) is None]
    status='INCONCLUSIVE' if not instructions or not complete or unassigned else ('PASS' if known else 'FAIL')
    reason='OBLIGATION_OR_SCOPE_NOT_CAPTURED' if status=='INCONCLUSIVE' else ('REQUIRED_CALL_OBSERVED' if known else 'REQUIRED_CALL_OMITTED')
    source_results=[e['payload'] for e in prefix if e['kind']=='evidence.retrieved' and e['payload'].get('tool')=='get_verified_market_snapshot']
    fallback=[{'seq':e['seq'],'message':e['payload'].get('message','')[:800]} for e in prefix if e['kind']=='runtime.log' and re.search(r'fallback|tool rounds|no tools',e['payload'].get('message',''),re.I)]
    return {**result,'status':status,'reason':reason,'report_output_seq':end['seq'],'report_input_seq':start['seq'],
        'report_output_pointer':pointer,'report_text_sha256':_text_hash(text),'instruction_anchors':instructions,
        'invocation_seqs':[e['seq'] for e in known],'unassigned_invocation_seqs':[e['seq'] for e in unassigned],
        'source_result_statuses':[p.get('source_status','UNKNOWN') for p in source_results],
        'tool_rounds_spent_message_observed':bool(re.search(r'tool rounds (?:are )?spent|no tool rounds remain',joined,re.I)),
        'fallback_messages':fallback,'limits':['Called-but-unavailable is separate from missing invocation.',
            'Tool-round/fallback context is not a causal model-quality judgment; no corrective feedback is sent.']}


def _run(directory):
    manifest,manifest_error=_load(directory/'run_manifest.json')
    closed=manifest.get('status') in ('success','failed','stopped','stopped_or_failed') and bool(manifest.get('ended_at'))
    events,integrity=read_trace(directory,closed)
    context=(events[0].get('context') if events else None) or manifest.get('context',{})
    counts=Counter(e['kind'] for e in events)
    starts={e['span_id']:e for e in events if e['kind']=='llm.start'}
    ended={e['span_id'] for e in events if e['kind']=='llm.end'};errors={e['span_id'] for e in events if e['kind']=='llm.error'}
    pending=set(starts)-ended-errors
    usage=_usage(events);charges=_charges(events);sources=_sources(events)
    final,final_error=_load(directory/'final_state.json')
    status='success' if counts['run.end'] else ('failed' if counts['run.error'] or manifest.get('status')=='failed' else 'running')
    latencies=[]
    for event in events:
        if event['kind'] not in ('llm.end','llm.error') or event['span_id'] not in starts:continue
        start=starts[event['span_id']]
        try:duration=(datetime.fromisoformat(event['timestamp'])-datetime.fromisoformat(start['timestamp'])).total_seconds()
        except (ValueError,TypeError):duration=None
        latencies.append({'span_id':event['span_id'],'actor':_actor(start),'seconds':duration,'terminal_kind':event['kind']})
    paper=final.get('final_trade_decision') or next((e['payload'].get('decision','') for e in reversed(events) if e['kind']=='decision.paper'),'')
    rating=re.search(r'\*\*Rating\*\*:\s*(Buy|Overweight|Hold|Underweight|Sell)',paper,re.I) if isinstance(paper,str) else None
    row={'run_id':directory.name,'arm':context.get('arm'),'model':context.get('model'),'pair_id':context.get('pair_id'),
        'mode':context.get('mode'),'source_mode':context.get('source_mode'),'status':status,'manifest_status':manifest.get('status'),
        'trade_date':context.get('trade_date'),'context_at':context.get('context_at'),'context_timezone':context.get('context_timezone'),
        'manifest_read_issue':manifest_error,'closed':closed,'trace_integrity':integrity,
        'llm_started':counts['llm.start'],'llm_completed':counts['llm.end'],'llm_errors':counts['llm.error'],
        'pending_llm_spans':sorted(str(x) for x in pending),'pending_llm_count':len(pending),
        'unmatched_terminal_spans':sorted(str(x) for x in ended|errors if x not in starts),
        'tool_calls':counts['tool.start'],'tools':dict(Counter(e['payload'].get('tool',{}).get('name','UNKNOWN') for e in events if e['kind']=='tool.start')),
        'errors':counts['run.error']+counts['llm.error']+counts['tool.error'],
        'source_failures':sum(s['status'] in ('ERROR','SOURCE_UNAVAILABLE','MISSING_CREDENTIAL') for s in sources),
        'evidence_retrievals':sum(e['kind']=='evidence.retrieved' for e in events),
        'distinct_evidence_ids':sorted({s['evidence_id'] for s in sources if s['evidence_id']}),
        'source_statuses':dict(Counter(s['status'] for s in sources)),'sources':sources,
        'source_tool_pending_ids':sorted({e['payload'].get('evidence_id') for e in events if e['kind']=='source.tool.start' and e['payload'].get('evidence_id')}
            -{s['evidence_id'] for s in sources if s['evidence_id']}),
        'http_observations':[{'seq':e['seq'],'kind':e['kind'],'http_id':e['payload'].get('http_id'),
            'transport':e['payload'].get('transport'),'method':e['payload'].get('method'),
            'url':_safe_url(e['payload']['url']) if e['payload'].get('url') else None,
            'requested_at':e['payload'].get('requested_at'),'retrieved_at':e['payload'].get('retrieved_at'),
            'status':e['payload'].get('status'),'error_type':e['payload'].get('error_type'),
            'elapsed_seconds':e['payload'].get('elapsed_seconds'),'response_bytes':e['payload'].get('response_bytes'),
            'response_sha256':e['payload'].get('response_sha256'),'source_time_fields':e['payload'].get('source_time_fields',[]),
            'cache_status':e['payload'].get('cache_status','UNKNOWN')}
            for e in events if e['kind'] in ('source.http.start','source.http.end','source.http.error')],
        'http_statuses':dict(Counter(str(e['payload'].get('status','UNKNOWN')) for e in events if e['kind']=='source.http.end')),
        'source_http_errors':counts['source.http.error'],'source_http_pending':max(0,counts['source.http.start']-counts['source.http.end']-counts['source.http.error']),
        'runtime_fallback_messages':[{'seq':e['seq'],'logger':e['payload'].get('logger'),'message':e['payload'].get('message','')[:1000]}
            for e in events if e['kind']=='runtime.log' and re.search(r'fallback|tool rounds|no tools',e['payload'].get('message',''),re.I)],
        'protocol':_protocol(events,final,manifest.get('config',{})),
        'call_latencies':latencies,'paper_rating':rating[1] if rating else None,
        'raw_trace':str(directory/'trace.jsonl'),'usage':usage,**{k:usage[k] for k in ('usage_calls','input_tokens','output_tokens')},
        'charges':charges,'standard_cost_estimate_usd':None,'final_state_read_issue':final_error}
    packets=[]
    for field,text in final.items():
        if not isinstance(text,str) or not text or not (field.endswith('_report') or field in ('investment_plan','trader_investment_plan','final_trade_decision')):continue
        origins=[{'output_seq':e['seq'],'span_id':e['span_id'],'pointer':pointer} for e in events if e['kind']=='llm.end' for body,pointer,_ in _generation_texts(e) if body==text]
        packets.append({'run_id':directory.name,'arm':context.get('arm'),'pair_id':context.get('pair_id'),'field':field,'report':text,
            'source_artifact':str(directory/'final_state.json'),'json_pointer':'/'+field,'text_sha256':_text_hash(text),
            'exact_generation_origins':origins,'origin_status':'exact_text_match' if len(origins)==1 else 'unresolved_or_structured_render_not_reaudited',
            'review_status':'Provisional report input; no semantic truth/support label or complete claim extraction.',
            'source_observation_seqs':[s['event_seq'] for s in sources]})
    return row,packets


def _pairs(rows,experiment):
    groups=defaultdict(list)
    for row in rows:groups[row['pair_id']].append(row)
    for planned in experiment.get('pairs',[]):groups.setdefault(planned['pair_id'],[])
    pairs=[]
    for identity,group in groups.items():
        arms=[r['arm'] for r in group];shared=[]
        if len(group)==2 and set(arms)=={'sol','terra'}:
            a,b=group;left=defaultdict(list);right=defaultdict(list)
            for source in a['sources']:left[source['request_key']].append(source)
            for source in b['sources']:right[source['request_key']].append(source)
            for key in sorted(left.keys() & right.keys()):
                x={s['saved_content_sha256'] for s in left[key] if s['saved_content_sha256']}
                y={s['saved_content_sha256'] for s in right[key] if s['saved_content_sha256']}
                shared.append({'request_key':key,'tool':left[key][0]['tool'],'left_run':a['run_id'],'right_run':b['run_id'],
                    'left_statuses':[s['status'] for s in left[key]],'right_statuses':[s['status'] for s in right[key]],
                    'left_content_hashes':sorted(x),'right_content_hashes':sorted(y),'saved_content_equal':x==y if x and y else None,
                    'available_result_content_equal':x==y if x and y and all(s['status']=='AVAILABLE' for s in left[key]+right[key]) else None,
                    'left_retrieved_at':[s['retrieved_at'] for s in left[key]],'right_retrieved_at':[s['retrieved_at'] for s in right[key]]})
        pairs.append({'pair_id':identity,'arms':arms,'missing_arms':sorted({'sol','terra'}-set(arms)),
            'both_completed':len(group)==2 and set(arms)=={'sol','terra'} and all(r['status']=='success' and r['trace_integrity']['status']=='PASS' and r['closed'] for r in group),
            'identical_available_fixture':None,'consumed_evidence_equal':None,
            'shared_source_requests':shared,'differing_shared_source_requests':sum(s['saved_content_equal'] is False for s in shared),
            'limits':'Saved content comparisons are per matched request, not identical-source/consumption controls or model rankings.'})
    return pairs


def _atomic(path,value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(value,encoding='utf-8');temporary.replace(path)


def analyze_session(session):
    session=Path(session).resolve();experiment,error=_load(session/'experiment.json')
    mode=experiment.get('source_mode') or experiment.get('mode') or experiment.get('evidence_mode')
    if error or mode not in LIVE_MODES or (session/'fixture.json').exists() or experiment.get('fixture_hash'):
        raise ValueError('Review writes only explicitly marked new live-source sessions; historical/fixture paths refused')
    rows=[];packets=[]
    for directory in sorted(p for p in session.iterdir() if p.is_dir()):
        if not (directory/'trace.jsonl').exists():continue
        row,review=_run(directory);rows.append(row);packets.extend(review)
    requests={identity for row in rows for identity in row['charges']['request_ids']}
    budget_path=Path(experiment.get('budget_ledger') or experiment.get('budget_db') or ROOT/'runs/approved-budget.sqlite')
    snapshot=budget_snapshot(budget_path,requests)
    result={'schema_version':VERSION,'updated_at':_utc(),'session':str(session),'unit':'one model workflow at a paired checkpoint',
        'input_kind':'offline_review_test_stub' if experiment.get('review_test_stub') else 'live_source_recording',
        'source_mode':'live_native_market_sources','experiment_status':experiment.get('status'),'runs':rows,'pairs':_pairs(rows,experiment),
        'budget':snapshot,'session_known_charged_upper_usd':sum(r['charges']['known_charged_upper_usd'] for r in rows),
        'session_known_pending_reservation_usd':sum(r['charges']['known_pending_reservation_usd'] for r in rows),
        'session_unknown_usage_completed_events':sum(len(r['usage']['completed_events_without_usage']) for r in rows),
        'all_observed_trace_requests_settled':bool(rows) and all(r['charges']['all_observed_reservations_settled'] for r in rows),
        'total_estimated_standard_cost_usd':None,'limitations':list(LIMITS)}
    _atomic(session/'analysis.json',json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    _atomic(session/'review_packets.json',json.dumps(packets,indent=2,ensure_ascii=False)+'\n')
    lines=['# Live-source session review','',f'Updated {result["updated_at"]}. Local analysis only; no model calls or corrective feedback.','',
        '| Run | Status | LLM done/start/error/pending | Known tokens in/out | Trace upper charge | Retained trace holds | Required snapshot | Trace/index scope |',
        '|---|---|---|---|---:|---:|---|---|']
    for row in rows:
        lines.append(f'| {row["run_id"]} | {row["status"]} | {row["llm_completed"]}/{row["llm_started"]}/{row["llm_errors"]}/{row["pending_llm_count"]} | {row["input_tokens"]}/{row["output_tokens"]} | {row["charges"]["known_charged_upper_usd"]} | {row["charges"]["known_pending_reservation_usd"]} | {row["protocol"]["status"]} | {row["trace_integrity"]["status"]}: {row["trace_integrity"].get("scope")} |')
    lines += ['', '## Budget', '', 'Read-only cumulative ledger snapshot: '+json.dumps(snapshot,ensure_ascii=False), '',
              'No usage/charge field is invented when absent. Known subtotals and retained holds are separate from final cost.', '',
              '## Evidence and interpretation limits','']+['- '+line for line in LIMITS]
    lines += ['', 'analysis.json contains provider URLs/status/time/cache, saved content hashes and exact input exposures. review_packets.json preserves report text/source references with provisional semantic status.']
    _atomic(session/'analysis.md','\n'.join(lines)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--session',type=Path,required=True)
    args=parser.parse_args();result=analyze_session(args.session)
    print(json.dumps({'session':result['session'],'runs':len(result['runs']),
        'statuses':dict(Counter(r['status'] for r in result['runs'])),
        'known_charge_upper_usd':result['session_known_charged_upper_usd'],
        'pending_trace_reservations_usd':result['session_known_pending_reservation_usd']}))


if __name__=='__main__':main()
