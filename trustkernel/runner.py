"""One bounded research arm; invoked by the experiment supervisor."""
import argparse
import importlib.metadata
import json
import logging
import os
import platform
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'c4544913a14ed3df5f1ed7b9e8483270ce20682a'
MODELS = ('gpt-6.1-sol', 'gpt-6.1-terra')
CONFIG = dict(analysts=['market', 'news'], effort='medium', max_debate_rounds=1,
              max_risk_discuss_rounds=1, max_tool_rounds=2, max_output_tokens=2048,
              max_calls=24, memory='disabled', trustkernel_feedback=False,
              ticker='ETH-USD', endpoint='https://api.openai.com/v1', service_tier='default')


def upstream_check():
    repo = ROOT / 'upstream/TradingAgents'
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    if git('rev-parse', 'HEAD') != COMMIT or git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Upstream revision or tracked source integrity changed')
    if git('remote', 'get-url', 'origin') != 'https://github.com/TauricResearch/TradingAgents.git':
        raise ValueError('Unexpected upstream origin')


def candidates(state):
    import re
    result = []
    for key, value in state.items():
        if not isinstance(value, str) or not value:
            continue
        for match in re.finditer(r'(Claim|Assumption|Hypothesis|Decision|Depends_on):\s*([^\n.]+)', value, re.I):
            result.append(dict(kind=match[1], text=match[2], source_field=key,
                               status='unverified_explicit_label_candidate', extraction='regex-v1',
                               source_character_start=match.start(), source_character_end=match.end()))
    return result


def run(args):
    upstream_check()
    fixture = json.loads(Path(args.fixture).read_text(encoding='utf-8'))
    if fixture['ticker'] != 'ETH-USD':
        raise ValueError('Only ETH-USD research fixtures allowed')
    from .trace import Observer, Trace, digest, plain, utc
    from .safety import Budget, network_guard
    from .replay import fixture_tools
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.dataflows.config import run_config
    from tradingagents.graph.setup import GraphSetup
    from tradingagents.graph.propagation import Propagator
    from tradingagents.graph.conditional_logic import ConditionalLogic

    run_id = f'{args.arm}-{uuid.uuid4().hex[:12]}'
    metadata = dict(model=args.model, arm=args.arm, mode=args.mode, effort='medium',
                    fixture_hash=digest(fixture), pair_id=args.pair_id, upstream_commit=COMMIT,
                    inference='scripted-test-double' if args.mode == 'offline' else 'paid-openai')
    trace = Trace(Path(args.output) / run_id, run_id, metadata)
    manifest = dict(run_id=run_id, started_at=utc(), status='running', context=metadata,
                    config=CONFIG, config_hash=digest(CONFIG), python=platform.python_version(),
                    packages={d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
                    adapter_hashes={str(p.relative_to(ROOT)): digest(p.read_text(encoding='utf-8'))
                                    for p in (ROOT / 'trustkernel').glob('*.py')},
                    limitations=['Observable external artifacts only; hidden chain-of-thought unavailable',
                                 'Synthetic frozen data; not live market evidence',
                                 'Claim extraction is partial and unverified; missing labels remain in raw outputs'])
    class LogHandler(logging.Handler):
        def emit(self, record):
            trace.emit('runtime.log', dict(logger=record.name, level=record.levelname, message=record.getMessage()))
    logger = logging.getLogger()
    old_handlers = logger.handlers[:]
    logger.handlers = [LogHandler()]
    logger.setLevel(logging.WARNING)
    success = False
    try:
        trace.artifact('run_manifest.json', manifest)
        trace.artifact('fixture.json', fixture)
        trace.emit('run.start', manifest)
        trace.emit('evidence.available', fixture)
        budget = None
        if args.mode == 'paid':
            if not args.approve_paid or not args.budget_db or args.budget <= 0:
                raise PermissionError('Paid inference requires explicit approval and positive budget')
            policy = json.loads((ROOT / 'budget_policy.json').read_text(encoding='utf-8'))
            if args.budget != policy['hard_limit_usd'] or Path(args.budget_db).resolve() != (ROOT / 'runs/approved-budget.sqlite').resolve():
                raise PermissionError('Paid runs must use the saved cumulative budget and ledger')
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise PermissionError('OPENAI_API_KEY not set; no credentials searched or copied')
            import httpx
            from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI
            class ApiOnlyTransport(httpx.HTTPTransport):
                def handle_request(self, request):
                    if request.url.scheme != 'https' or request.url.host != 'api.openai.com' or request.url.path != '/v1/responses':
                        raise PermissionError('Only OpenAI Responses API allowed')
                    return super().handle_request(request)
            client = httpx.Client(transport=ApiOnlyTransport(retries=0), trust_env=False, timeout=60)
            llm = NormalizedChatOpenAI(model=args.model, api_key=api_key, base_url=CONFIG['endpoint'],
                             reasoning_effort='medium', use_responses_api=True, store=False,
                             service_tier='default', max_tokens=2048, max_retries=0, timeout=60,
                             http_client=client)
            budget = Budget(args.budget_db, args.budget, args.model, args.deadline,
                            ROOT / 'STOP', trace, CONFIG['max_calls'], initial_limit=policy['initial_limit_usd'])
        else:
            from .scripted import ScriptedModel
            llm = ScriptedModel(model_name=f'scripted-for-{args.arm}')
        observer = Observer(trace, budget.before if budget else None, budget.settle if budget else None)
        cfg = {**DEFAULT_CONFIG, 'output_language': 'English'}
        # No TradingAgentsGraph constructor: excludes memory store, settlement,
        # identity lookup, provider auto-detection and all persistence side effects.
        network_guard(args.mode == 'paid')
        with fixture_tools(fixture, trace), run_config(cfg):
            workflow = GraphSetup(llm, llm, ConditionalLogic(1, 1), max_tool_rounds=2).setup_graph(['market', 'news'])
            graph = workflow.compile()
            state = Propagator().create_initial_state('ETH-USD', fixture['as_of'], asset_type='crypto',
                instrument_context='Ethereum ETH-USD, USD quote. Frozen synthetic research fixture; no order authority.')
            final = graph.invoke(state, config={'callbacks': [observer], 'recursion_limit': 50,
                                                'max_concurrency': 1, 'metadata': metadata})
        trace.artifact('final_state.json', plain(final))
        trace.artifact('claim_candidates.json', candidates(final))
        trace.emit('decision.paper', dict(decision=final.get('final_trade_decision'), execution_authority=False))
        trace.emit('run.end', dict(status='success', claim_candidates=len(candidates(final))))
        manifest.update(status='success', ended_at=utc())
        success = True
    except BaseException as exc:
        trace.emit('run.error', dict(error_type=type(exc).__name__, error=str(exc)))
        manifest.update(status='failed', ended_at=utc(), error_type=type(exc).__name__, error=str(exc))
    finally:
        trace.artifact('run_manifest.json', manifest)
        trace.close()
        logger.handlers = old_handlers
    from .report import summarize
    summarize(trace.directory)
    return 0 if success else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['offline', 'paid'], default='offline')
    p.add_argument('--arm', choices=['sol', 'terra'], required=True)
    p.add_argument('--model', choices=MODELS, required=True)
    p.add_argument('--fixture', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--pair-id', required=True)
    p.add_argument('--approve-paid', action='store_true')
    p.add_argument('--budget', type=float, default=0)
    p.add_argument('--budget-db')
    p.add_argument('--deadline', type=float, default=0)
    args = p.parse_args()
    if args.model != MODELS[0 if args.arm == 'sol' else 1]:
        p.error('Arm/model mismatch')
    raise SystemExit(run(args))


if __name__ == '__main__':
    main()
