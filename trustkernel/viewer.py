"""Loopback-only log viewer with escaped text; no external assets or commands."""
import argparse
import json
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .runner import ROOT
from .trace import rebuild

PAGE = '''<!doctype html><meta charset="utf-8"><title>TrustKernel trace viewer</title>
<style>body{font:15px system-ui;background:#101820;color:#e6edf3;margin:24px}select,input{padding:8px;margin:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#182733;padding:16px}button{padding:8px}</style>
<h1>TrustKernel observable traces</h1><p>Research only. Offline smoke contains scripted responses, not Sol/Terra inference. No hidden chain-of-thought.</p>
<label>Run <select id="run"></select></label><label>Event kind <input id="kind" placeholder="llm.start / tool.end / step.end"></label><button id="refresh">Refresh</button>
<p id="budget"></p><details open><summary>Latest experiment analysis (descriptive, no quality score)</summary><pre id="analysis"></pre></details><p id="status"></p><div id="events"></div><script>
async function refresh(){let b=await(await fetch('/api/budget')).json();document.querySelector('#budget').textContent='Cumulative budget: $'+b.reserved_usd.toFixed(4)+' committed upper bound + outstanding holds / $'+b.active_limit_usd.toFixed(2)+' active; initial $3, hard stop $5.';let a=await(await fetch('/api/analysis')).json();document.querySelector('#analysis').textContent=a.runs?a.runs.map(r=>r.run_id+' | '+r.status+' | calls '+r.llm_completed+'/'+r.llm_started+' | tools '+r.tool_calls+' | evidence '+r.distinct_evidence_ids.length+' | tokens '+r.input_tokens+'/'+r.output_tokens+' | paper '+(r.paper_rating||'pending')).join('\n')+'\n\nUpdated '+a.updated_at+'\n'+a.limitations.join('\n'):'No analysis snapshot yet.';let sel=document.querySelector('#run');let prior=sel.value;let runs=await(await fetch('/api/runs')).json();sel.replaceChildren(...runs.map(r=>{let o=document.createElement('option');o.value=r;o.textContent=r;return o}));if(runs.includes(prior))sel.value=prior;if(!sel.value)return;
let events=await(await fetch('/api/events?run='+encodeURIComponent(sel.value)+'&kind='+encodeURIComponent(document.querySelector('#kind').value))).json();document.querySelector('#status').textContent='Latest '+events.length+' events; full history remains in JSONL and SQLite. Refreshes every 3 seconds.';
document.querySelector('#events').replaceChildren(...events.map(e=>{let d=document.createElement('details');let s=document.createElement('summary');s.textContent='#'+e.seq+' '+e.timestamp+' '+e.kind;let p=document.createElement('pre');p.textContent=JSON.stringify(e,null,2);d.append(s,p);return d}));}
document.querySelector('#refresh').onclick=refresh;document.querySelector('#run').onchange=refresh;setInterval(refresh,3000);refresh();</script>'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--query', type=Path)
    p.add_argument('--kind', default='')
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--rebuild', type=Path)
    p.add_argument('--database', type=Path)
    args = p.parse_args()
    if args.rebuild:
        if not args.database:
            p.error('--database required')
        rebuild(args.rebuild, args.database)
        return
    def query(db_path, kind, limit):
        with closing(sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True)) as db:
            return [dict(seq=r[0], run_id=r[1], timestamp=r[2], kind=r[3], span_id=r[4], parent_id=r[5], payload=json.loads(r[6]))
                    for r in db.execute('SELECT seq,run_id,timestamp,kind,span_id,parent_id,payload_json FROM events WHERE (?="" OR kind=?) ORDER BY seq DESC LIMIT ?', (kind, kind, limit))]
    if args.query:
        print(json.dumps(query(args.query.resolve(), args.kind, args.limit), indent=2))
        return
    base = ROOT / 'runs'
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            params = parse_qs(url.query)
            if url.path == '/':
                body, mime = PAGE.encode(), 'text/html; charset=utf-8'
            elif url.path == '/api/runs':
                body, mime = json.dumps(sorted((str(p.parent.relative_to(base)).replace('\\', '/') for p in base.glob('*/*/trace.sqlite')),reverse=True)).encode(), 'application/json'
            elif url.path == '/api/analysis':
                paths=sorted(base.glob('*/analysis.json'))
                body,mime=(paths[-1].read_bytes() if paths else b'{}'),'application/json'
            elif url.path == '/api/budget':
                policy = json.loads((ROOT / 'budget_policy.json').read_text(encoding='utf-8'))
                status = dict(reserved_usd=0, active_limit_usd=policy['initial_limit_usd'], hard_limit_usd=policy['hard_limit_usd'])
                ledger = base / 'approved-budget.sqlite'
                if ledger.exists():
                    with closing(sqlite3.connect(f'file:{ledger.as_posix()}?mode=ro', uri=True)) as db:
                        status['reserved_usd'] = db.execute('SELECT reserved FROM budget WHERE id=1').fetchone()[0]
                        row = db.execute('SELECT active_limit FROM budget_policy WHERE id=1').fetchone()
                        if row:
                            status['active_limit_usd'] = row[0]
                body, mime = json.dumps(status).encode(), 'application/json'
            elif url.path == '/api/events':
                target = (base / params.get('run', [''])[0] / 'trace.sqlite').resolve()
                if not target.is_relative_to(base.resolve()) or not target.is_file():
                    self.send_error(404)
                    return
                body, mime = json.dumps(query(target, params.get('kind', [''])[0], 100)).encode(), 'application/json'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    print(f'TrustKernel log viewer: http://127.0.0.1:{args.port} (Ctrl+C to stop)', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
