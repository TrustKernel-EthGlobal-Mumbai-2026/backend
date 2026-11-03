"""No-inference preflight for native live sources and unchanged budget policy."""
import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4

from trustkernel.runner import ROOT,upstream_check
from .preservation import budget_snapshot


def run_preflight(directory=None):
    # Finish git subprocesses before installing irreversible child boundaries.
    upstream_check()
    from tradingagents.default_config import DEFAULT_CONFIG
    from .arm import native_config
    from .sources import data_preflight
    from .safety import network_guard
    now=datetime.now(timezone.utc)
    local_date=datetime.now().date().isoformat()
    directory=Path(directory) if directory else ROOT/'runs'/('live-preflight-'+now.strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6])
    directory.mkdir(parents=True,exist_ok=False)
    cfg=native_config(DEFAULT_CONFIG,directory,'gpt-6.1-sol')
    cfg['source_as_of']=local_date
    cfg['source_cache_parent']=str(directory/'source-cache')
    network_guard()
    report=data_preflight(cfg)
    report['requested_local_date']=local_date
    report['actual_utc_date']=now.date().isoformat()
    report['date_basis']='host_local_date_matches_pinned_native_current_date_predicate'
    report['budget_before']=budget_snapshot()
    report['model_calls']=0
    report['new_paid_requests']=0
    path=directory/'source-preflight.json'
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    public={'status':report['status'],'as_of':report['as_of'],'path':str(path),
        'providers':{name:{k:v for k,v in item.items() if k not in ('content','events')}
            for name,item in report['providers'].items()},
        'model_calls':0,'new_paid_requests':0,'preflight_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    print(json.dumps(public,indent=2),flush=True)
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',type=Path)
    args=parser.parse_args();path=run_preflight(args.output_directory)
    report=json.loads(path.read_text(encoding='utf-8'))
    raise SystemExit(0 if report['status']=='PASS' else 1)


if __name__=='__main__':main()
