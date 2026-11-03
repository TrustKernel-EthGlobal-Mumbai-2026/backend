"""Origin-first inventory of visible generated text; no external inference."""
import json
from collections import Counter, defaultdict
from . import ledger as parent

VERSION='2.0.0'


def inventory(rows, root=parent.ROOT):
    by=defaultdict(dict)
    for row in rows:
        by[row['table']][row['id']]=row
    calls={c['end_event_id']:c for c in by['calls'].values() if c['end_event_id']}
    report_events={r['output_event_id']:r for r in by['reports'].values()}
    if len(report_events)!=len(by['reports']):raise ValueError('Unsupported: multiple saved report fields from one output event')
    sources=[]; outputs=[]
    for event in sorted(by['events'].values(),key=lambda e:(e['run_id'],e['seq'])):
        if event['kind']!='llm.end':continue
        call=calls[event['id']]
        start=by['events'][call['start_event_id']]
        stage=start['raw']['payload'].get('metadata',{}).get('metadata',{}).get('langgraph_node','recorded_stage_unavailable')
        if sum(len(b) for b in event['raw']['payload']['response'].get('generations',[]))!=1:
            raise ValueError('Unsupported multi-generation output; do not silently exclude narrative')
        for i,batch in enumerate(event['raw']['payload']['response'].get('generations',[])):
            for j,generation in enumerate(batch):
                pointer=f'/payload/response/generations/{i}/{j}'
                report=report_events.get(event['id']) if (i,j)==(0,0) else None
                text=generation.get('text') or ''
                method='raw_generation_text'; anchor_pointer=pointer+'/text'; transform=None
                aid=event['artifact_id']; anchor_event=event['id']; source_type='discussion'
                report_id=None
                if report:
                    saved=by['texts'][report['text_id']]
                    text=saved['text'];aid=saved['artifact_id'];anchor_pointer=saved['pointer'];anchor_event=None
                    method=report['origin_method'];source_type=report['field'];report_id=report['id']
                elif not text:
                    blocks=generation.get('message',{}).get('content',[])
                    visible=[(k,b['text']) for k,b in enumerate(blocks) if isinstance(b,dict) and b.get('type') in ('text','output_text') and isinstance(b.get('text'),str)] if isinstance(blocks,list) else []
                    if len(visible)==1:
                        k,text=visible[0];anchor_pointer=pointer+f'/message/content/{k}/text';method='visible_text_block'
                    elif len(visible)>1:raise ValueError('Unsupported multi-visible-text-block output; inventory requires an explicit representation contract')
                    elif isinstance(blocks,str) and blocks:
                        text=blocks;anchor_pointer=pointer+'/message/content';method='visible_message_string'
                source_id=None
                if text:
                    source_id=parent.ident('sources_v2',[event['run_id'],event['id'],pointer,source_type])
                    sources.append(dict(id=source_id,run_id=event['run_id'],actor=call['actor'],stage=stage,source_type=source_type,
                                        report_id=report_id,call_id=call['id'],output_event_id=event['id'],anchor_event_id=anchor_event,
                                        artifact_id=aid,pointer=anchor_pointer,text=text,sha256=parent.sha(text),content_group=parent.sha(text),
                                        origin_method=method,origin_pointer=report['origin_pointer'] if report else anchor_pointer,
                                        input_seq=start['seq'],output_seq=event['seq'],asserted_at=event['timestamp']))
                    disposition='originating_narrative'
                else:
                    tool_calls=generation.get('message',{}).get('tool_calls',[])
                    known_tools={e['tool'] for e in by['evidence'].values()}
                    if any(c.get('name') not in known_tools for c in tool_calls):
                        raise ValueError('Unsupported structured output without report origin; do not classify as tool-only')
                    disposition='tool_invocation_only' if tool_calls else 'empty_visible_output'
                outputs.append(dict(id=parent.ident('outputs_v2',[event['id'],i,j]),run_id=event['run_id'],actor=call['actor'],event_id=event['id'],
                                    pointer=pointer,source_id=source_id,disposition=disposition,
                                    details={'tool_names':[t.get('name') for t in generation.get('message',{}).get('tool_calls',[])],
                                             'exclusion':'No narrative visible text; raw generation remains in parent event.' if not text else None}))
    return sources,outputs,by


def appearances(sources, by, root=parent.ROOT):
    by_run=defaultdict(list)
    for source in sources:by_run[source['run_id']].append(source)
    found=[]
    def scan(run,aid,event,pointer,text,kind):
        for source in by_run[run]:
            for left,right in parent.matches(text,source['text']):
                if aid==source['artifact_id'] and (event['id'] if event else None)==source['anchor_event_id'] and pointer==source['pointer'] and left==0:
                    mode='source_anchor'
                elif event and event['id']==source['output_event_id']:mode='same_output_representation'
                elif event and event['kind']=='llm.start':mode='recorded_input_copy'
                elif event and event['kind']=='llm.end':mode='other_output_embedding'
                elif event:mode='recorded_state_or_step_copy'
                else:mode='final_state_copy'
                found.append(dict(id=parent.ident('appearances_v2',[source['id'],aid,event['id'] if event else None,pointer,left]),
                                  source_id=source['id'],run_id=run,artifact_id=aid,event_id=event['id'] if event else None,pointer=pointer,
                                  start=left,end=right,appearance_type=mode,container_kind=kind))
    for event in by['events'].values():
        for pointer,text in parent.walk_strings(event['raw']['payload'],'/payload'):
            if '/encrypted_content' in pointer or '/summary/' in pointer:continue
            scan(event['run_id'],event['artifact_id'],event,pointer,text,event['kind'])
    for artifact in by['artifacts'].values():
        if artifact['path'].endswith('/final_state.json'):
            run=artifact['path'].split('/')[-2]
            state=json.loads((root/artifact['path']).read_text(encoding='utf-8'))
            for pointer,text in parent.walk_strings(state):scan(run,artifact['id'],None,pointer,text,'final_state')
    return found


def summary(sources, outputs, copies):
    groups={s['content_group']:s['text'] for s in sources}
    return dict(source_occurrences=len(sources),source_characters=sum(len(s['text']) for s in sources),
                unique_exact_texts=len(groups),unique_exact_text_characters=sum(len(t) for t in groups.values()),
                report_sources=sum(s['report_id'] is not None for s in sources),
                report_characters=sum(len(s['text']) for s in sources if s['report_id']),
                output_generations=len(outputs),output_dispositions=dict(Counter(o['disposition'] for o in outputs)),
                appearances=len(copies),appearance_types=dict(Counter(a['appearance_type'] for a in copies)),
                source_type_counts=dict(Counter(s['source_type'] for s in sources)),actor_counts=dict(Counter(s['actor'] for s in sources)),
                exclusions=['Tool invocation-only/empty output generations have no narrative text denominator; preserved in output inventory.',
                            'Copied input/state representations are appearances, not additional authored sources.',
                            'Partial/paraphrased copy alignment and inaccessible/private reasoning are excluded.'])
