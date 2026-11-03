"""One approved live-source paper research arm; launched only by parent window.

Imports do not call models or data providers. Tests substitute runtime objects;
this module has no offline fixture mode and never falls back to synthetic data.
"""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import logging
import math
import os
import platform
import re
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx

from trustkernel.runner import COMMIT, MODELS, upstream_check, candidates

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MODE = "live_native_market_sources"
CONFIG = dict(analysts=["market", "news"], effort="medium", max_debate_rounds=1,
              max_risk_discuss_rounds=1, max_tool_rounds=2, max_output_tokens=2048,
              max_calls=24, max_input_bytes=50000, memory="disabled", trustkernel_feedback=False,
              ticker="ETH-USD", endpoint="https://api.openai.com/v1", service_tier="default",
              source_mode=SOURCE_MODE, date_basis="current_local_date")
VENDORS = dict(core_stock_apis="yfinance", technical_indicators="yfinance",
               fundamental_data="sec_edgar,yfinance", news_data="yfinance",
               macro_data="fred", prediction_markets="polymarket")


def _clock_context(instant=None, local_timezone=None):
    """One real instant, native host-local trade date, separate UTC/local clocks."""
    instant = instant if instant is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("Context instant must include a timezone")
    utc_at = instant.astimezone(timezone.utc)
    local_at = instant.astimezone(local_timezone)
    return dict(context_at=utc_at.isoformat(), context_timezone="UTC",
                local_context_at=local_at.isoformat(), local_timezone=str(local_at.tzinfo),
                utc_date=utc_at.date().isoformat(), local_date=local_at.date().isoformat(),
                trade_date=local_at.date().isoformat(), date_basis="current_local_date")


def _runtime_text(value):
    """Scrub native diagnostic strings before old Trace privacy filtering.

    Yahoo may log a crumb using arbitrary quoting. Omit that whole diagnostic
    message rather than guessing token boundaries; source results are untouched.
    """
    text = str(value)
    if re.search(r"\b(?:crumb|cookie|set-cookie)\b", text, re.I):
        return "[REDACTED native crumb/cookie diagnostic text]"
    return re.sub(r"(?i)(api[_-]?key|token|sessionid|csrf(?:token)?)=([^&\s\"']+)",
                  r"\1=[REDACTED]", text)


class ApiOnlyTransport(httpx.HTTPTransport):
    """The model client can POST only to the native Responses API."""
    def handle_request(self, request):
        if (request.method != "POST" or request.url.scheme != "https"
                or request.url.host != "api.openai.com" or request.url.port not in (None, 443)
                or request.url.path != "/v1/responses" or request.url.query
                or request.url.username or request.url.password):
            raise PermissionError("Only native OpenAI Responses POST requests are allowed")
        return super().handle_request(request)


def validate_args(args):
    """Read-only paid gate. Never initializes or reconciles a budget ledger."""
    if args.arm not in ("sol", "terra") or args.model != MODELS[0 if args.arm == "sol" else 1]:
        raise ValueError("Arm/model mismatch")
    if not args.approve_paid:
        raise PermissionError("Parent paid-window authorization flag is required")
    if not math.isfinite(args.budget) or args.budget != 5:
        raise PermissionError("Existing cumulative hard limit must remain $5")
    if not math.isfinite(args.deadline) or args.deadline <= time.time():
        raise PermissionError("A finite future parent deadline is required")
    if (ROOT / "STOP").exists():
        raise PermissionError("STOP file is present")
    if not args.budget_db or Path(args.budget_db).resolve() != (ROOT / "runs/approved-budget.sqlite").resolve():
        raise PermissionError("Only the existing cumulative budget ledger may be used")
    if not Path(args.budget_db).is_file():
        raise PermissionError("Existing cumulative budget ledger is missing; no new allowance is created")
    policy = json.loads((ROOT / "budget_policy.json").read_text(encoding="utf-8"))
    if (policy.get("initial_limit_usd"), policy.get("hard_limit_usd"), policy.get("auto_extend_once")) != (3, 5, True):
        raise PermissionError("Saved cumulative budget policy differs from the approved $3/$5 policy")
    with closing(sqlite3.connect(Path(args.budget_db).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        saved = db.execute("SELECT initial_limit,hard_limit FROM budget_policy WHERE id=1").fetchone()
        balance = db.execute("SELECT reserved FROM budget WHERE id=1").fetchone()
        if saved != (3, 5) or balance is None or not math.isfinite(balance[0]) or not 0 <= balance[0] <= 5:
            raise PermissionError("Existing cumulative budget state is invalid; no reset is allowed")
    if not os.environ.get("OPENAI_API_KEY"):
        raise PermissionError("OPENAI_API_KEY is missing from process environment")
    if not args.pair_id or not args.output:
        raise ValueError("Output directory and pair ID are required")
    return policy


def native_config(defaults, run_directory, model):
    """Freeze approved graph/vendor settings and isolate every cache per arm."""
    directory = Path(run_directory).resolve()
    cfg = copy.deepcopy(defaults)
    cfg.update(output_language="English", llm_provider="openai", deep_think_provider="openai",
               quick_think_provider="openai", deep_think_llm=model, quick_think_llm=model,
               backend_url=CONFIG["endpoint"], deep_think_backend_url=CONFIG["endpoint"],
               quick_think_backend_url=CONFIG["endpoint"], openai_reasoning_effort="medium",
               max_tokens=2048, llm_max_retries=0, max_debate_rounds=1, max_risk_discuss_rounds=1,
               max_tool_rounds=2, checkpoint_enabled=False, temperature=None,
               data_vendors=copy.deepcopy(VENDORS), tool_vendors={},
               data_cache_dir=str(directory / "source-cache"),
               results_dir=str(directory / "native-results"),
               memory_log_path=str(directory / "unused-memory.md"))
    return cfg


def _load_runtime():
    """Lazy loading permits paid-gate tests without loading provider modules."""
    from trustkernel.trace import Trace, Observer, digest, plain, utc
    from trustkernel.safety import Budget
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.dataflows.config import run_config
    from tradingagents.graph.setup import GraphSetup
    from tradingagents.graph.propagation import Propagator
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI
    from .sources import live_tools
    from .safety import network_guard
    return SimpleNamespace(Trace=Trace, Observer=Observer, digest=digest, plain=plain, utc=utc,
                           Budget=Budget, DEFAULT_CONFIG=DEFAULT_CONFIG, run_config=run_config,
                           GraphSetup=GraphSetup, Propagator=Propagator, ConditionalLogic=ConditionalLogic,
                           NormalizedChatOpenAI=NormalizedChatOpenAI, live_tools=live_tools,
                           network_guard=network_guard)


def run(args):
    """Run one parent-approved arm; return 0 on success, 1 on traced failure.

    Invalid preflight raises before Trace/client/Budget creation. Graph/provider
    failures are recorded; no retries, fallback model or synthetic evidence.
    """
    policy = validate_args(args)
    upstream_check()  # Git subprocess must finish before the child's network audit guard.
    rt = _load_runtime()
    clocks = _clock_context()
    trade_date = clocks["trade_date"]
    run_id = f"{args.arm}-{uuid.uuid4().hex[:12]}"
    metadata = dict(model=args.model, arm=args.arm, mode=SOURCE_MODE, source_mode=SOURCE_MODE,
                    inference="paid-openai", effort="medium", pair_id=args.pair_id,
                    upstream_commit=COMMIT, **clocks, execution_authority=False,
                    source_comparability="Live retrievals may differ across concurrent arms")
    trace = rt.Trace(Path(args.output) / run_id, run_id, metadata)
    cfg = native_config(rt.DEFAULT_CONFIG, trace.directory, args.model)
    manifest = dict(run_id=run_id, started_at=rt.utc(), status="running", context=metadata,
                    config=copy.deepcopy(CONFIG), native_config=copy.deepcopy(cfg),
                    config_hash=rt.digest(CONFIG), native_config_hash=rt.digest(cfg),
                    python=platform.python_version(),
                    packages={d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
                    adapter_hashes={str(p.relative_to(ROOT)): rt.digest(p.read_text(encoding="utf-8"))
                                    for folder in (ROOT / "trustkernel", ROOT / "live_experiment")
                                    for p in folder.glob("*.py")},
                    limitations=["Observable external artifacts only; hidden chain-of-thought unavailable",
                                 "Live source timing/content can differ across arms; no identical-evidence claim",
                                 "Native daily bars/snapshots are not guaranteed current ticks; inspect source clocks",
                                 "Missing data and provider errors remain explicit; no fabricated evidence",
                                 "Claim candidates are partial unverified labels, not complete semantic extraction",
                                 "Paper research only; no order, wallet, settlement or execution authority"])
    class LogHandler(logging.Handler):
        def emit(self, record):
            trace.emit("runtime.log", dict(logger=record.name, level=record.levelname,
                                           message=_runtime_text(record.getMessage())))
    logger = logging.getLogger()
    old_handlers, old_level = logger.handlers[:], logger.level
    logger.handlers, logger.level = [LogHandler()], logging.WARNING
    client = None
    success = False
    try:
        trace.artifact("run_manifest.json", manifest)
        trace.emit("run.start", manifest)
        # Guard is parent-owned; unlike the historical guard it permits only
        # approved native source hosts plus api.openai.com and blocks child exec.
        rt.network_guard(trace=trace)
        if time.time() >= args.deadline or (ROOT / "STOP").exists():
            raise PermissionError("Deadline or STOP file reached before client initialization")
        client = httpx.Client(transport=ApiOnlyTransport(retries=0), trust_env=False, timeout=60)
        llm = rt.NormalizedChatOpenAI(model=args.model, api_key=os.environ["OPENAI_API_KEY"],
                                     base_url=CONFIG["endpoint"], reasoning_effort="medium",
                                     use_responses_api=True, store=False, service_tier="default",
                                     max_tokens=2048, max_retries=0, timeout=60, http_client=client)
        budget = rt.Budget(args.budget_db, args.budget, args.model, args.deadline,
                           ROOT / "STOP", trace, CONFIG["max_calls"], initial_limit=policy["initial_limit_usd"])
        observer = rt.Observer(trace, budget.before, budget.settle)
        # Same upstream factories/prompts/tool schemas, no TradingAgentsGraph
        # constructor, persistent memory, identity resolution or forced tool use.
        with rt.live_tools(trace, cfg), rt.run_config(cfg):
            workflow = rt.GraphSetup(llm, llm, rt.ConditionalLogic(1, 1), max_tool_rounds=2).setup_graph(["market", "news"])
            graph = workflow.compile()
            state = rt.Propagator().create_initial_state(
                "ETH-USD", trade_date, asset_type="crypto",
                instrument_context=(f"Ethereum ETH-USD, USD quote. Native current date {trade_date} "
                                    f"({clocks['local_timezone']}). Live native market sources; "
                                    "paper research only, no order authority."))
            final = graph.invoke(state, config={"callbacks": [observer], "recursion_limit": 50,
                                               "max_concurrency": 1, "metadata": metadata})
        if not isinstance(final, dict) or not final.get("final_trade_decision"):
            raise ValueError("Graph returned no final paper decision")
        trace.artifact("final_state.json", rt.plain(final))
        extracted = candidates(final)
        trace.artifact("claim_candidates.json", extracted)
        trace.emit("decision.paper", dict(decision=final["final_trade_decision"], execution_authority=False))
        trace.emit("run.end", dict(status="success", claim_candidates=len(extracted)))
        manifest.update(status="success", ended_at=rt.utc())
        success = True
    except BaseException as exc:
        # Trace privacy filtering applies to exception strings and all artifacts.
        error = _runtime_text(exc)
        trace.emit("run.error", dict(error_type=type(exc).__name__, error=error))
        manifest.update(status="failed", ended_at=rt.utc(), error_type=type(exc).__name__, error=error)
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            try:
                trace.artifact("run_manifest.json", manifest)
            finally:
                trace.close()
                logger.handlers, logger.level = old_handlers, old_level
    return 0 if success else 1


def build_parser():
    parser = argparse.ArgumentParser(description="Parent-launched live-source paper arm; no fixture mode")
    parser.add_argument("--arm", choices=["sol", "terra"], required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--approve-paid", action="store_true")
    parser.add_argument("--budget-db", required=True)
    parser.add_argument("--budget", type=float, default=0)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ValueError, PermissionError, OSError, sqlite3.Error) as exc:
        # Avoid printing source args/URLs, native credentials or request payloads.
        parser.error(f"Live arm preflight refused ({type(exc).__name__}); verify approval, pinned upstream, deadline and cumulative policy")


if __name__ == "__main__":
    raise SystemExit(main())
