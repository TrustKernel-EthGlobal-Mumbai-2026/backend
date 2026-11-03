"""Native public source tools with out-of-band provenance; never model calls."""
from __future__ import annotations

import argparse
import copy
import functools
import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from .source_http import HTTP_EVIDENCE_ID, SOURCE_HOSTS, data_http, utc

ROOT = Path(__file__).resolve().parents[1]
VENDORS = {"core_stock_apis": "yfinance", "technical_indicators": "yfinance",
           "news_data": "yfinance", "macro_data": "fred", "prediction_markets": "polymarket"}
TOOL_VENDORS = {"get_stock_data": "yfinance", "get_indicators": "yfinance",
    "get_news": "yfinance", "get_global_news": "yfinance",
    "get_macro_indicators": "fred", "get_prediction_markets": "polymarket"}


def content_digest(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sanitize_text(value):
    """For runtime logs only, never applied to native model-visible results."""
    text = str(value)
    text = re.sub(r"(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)\bBearer\s+[^\s\"']+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(\b(?:crumb|api[_-]?key|token|sessionid|csrftoken|authorization|cookie)\b[\"']?\s*[:=]\s*)[\"']?[^\s\"'&,}]+", r"\1[REDACTED]", text)
    return text


def current_source_date():
    # Asia/Calcutta has UTC+05:30 and no seasonal offset; independent of host TZ.
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()


def classify(name, result):
    if name == "get_macro_indicators" and not os.environ.get("FRED_API_KEY"):
        return "MISSING_CREDENTIAL"
    if result.startswith("DATA_UNAVAILABLE:") or "currently unavailable (network error" in result:
        return "SOURCE_UNAVAILABLE"
    if result.startswith("NO_DATA_AVAILABLE:") or "No open prediction markets matched" in result or result.startswith("No news found"):
        return "NO_DATA"
    if result.startswith("Prediction-market odds are withheld"):
        return "HISTORICAL_UNAVAILABLE"
    if " unavailable for " in result and "not an absence" in result:
        return "COVERAGE_UNAVAILABLE"
    if "is not supported. Please choose from:" in result or result.startswith("FRED:"):
        return "INPUT_ERROR"
    if result.startswith("N/A:") or "No observations for " in result:
        return "NO_DATA"
    return "AVAILABLE"


def source_config(cfg):
    result = copy.deepcopy(cfg)
    configured = result.setdefault("data_vendors", {})
    for category, vendor in VENDORS.items():
        if configured.get(category, vendor) != vendor:
            raise ValueError("Only explicit inspected native source vendors allowed: " + category)
        configured[category] = vendor
    overrides = result.setdefault("tool_vendors", {})
    for method, vendor in overrides.items():
        if TOOL_VENDORS.get(method) != vendor:
            raise ValueError("Uninspected/paid/default tool vendor route rejected")
    return result


@contextmanager
def live_tools(trace, cfg):
    """Patch only tool execution, preserving original schema/description/string.

    Parent installs global safety first. Saved transport methods are delegated
    through, so source capture composes with the parent's CFFI permission guard.
    One context per fresh arm process; no historic or home cache is served.
    """
    from langchain_core.tools import StructuredTool
    from tradingagents.agents.analysts import market_analyst, news_analyst
    from tradingagents.graph import analyst_execution
    from tradingagents.dataflows.config import run_config
    from tradingagents.dataflows.vendors.yahoo import common, market, ohlcv, news
    import yfinance.cache

    effective = source_config(cfg)
    configured_cache = Path(effective.get("data_cache_dir") or ROOT / "live_experiment/cache").resolve()
    parent = Path(effective.get("source_cache_parent") or
                  (configured_cache if configured_cache.is_relative_to(ROOT) else ROOT / "live_experiment/cache"))
    parent.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(tempfile.mkdtemp(prefix="native-live-", dir=parent))
    effective["data_cache_dir"] = str(cache_dir / "ohlcv")
    # Propagate the same effective native configuration if parent's run_config
    # is nested inside this context. Nothing model-visible is added.
    cfg["data_cache_dir"] = effective["data_cache_dir"]
    cfg["data_vendors"] = copy.deepcopy(effective["data_vendors"])
    cfg["tool_vendors"] = copy.deepcopy(effective["tool_vendors"])
    yfinance.cache.set_cache_location(str(cache_dir / "yfinance"))
    retries = int(effective.get("source_max_retries", 1))
    if retries not in (0, 1):
        raise ValueError("Native source retry bound must be 0 or 1")
    original_retry = common.yf_retry
    @functools.wraps(original_retry)
    def bounded_retry(func, max_retries=3, base_delay=2.0):
        return original_retry(func, max_retries=min(max_retries, retries), base_delay=min(base_delay, 1.0))

    def emit(kind, payload):
        if trace is not None:
            trace.emit(kind, payload)

    with ExitStack() as stack:
        capture = stack.enter_context(data_http(trace, effective))
        stack.enter_context(run_config(effective))
        for module in (common, market, ohlcv, news):
            if hasattr(module, "yf_retry"):
                stack.enter_context(patch.object(module, "yf_retry", bounded_retry))
        replacements, native_functions = {}, {}
        for module in (market_analyst, news_analyst):
            wrapped_tools = []
            for original in module.TOOLS:
                native_functions[original.name] = original.func
                def serve(_original=original, **kwargs):
                    name = _original.name
                    evidence_id = "live-evidence:" + uuid.uuid4().hex
                    requested_at = utc()
                    files_before = {str(p): p.stat().st_mtime_ns for p in cache_dir.rglob("*.csv")}
                    emit("source.tool.start", {"evidence_id": evidence_id, "tool": name,
                        "request": kwargs, "requested_at": requested_at, "mode": "live_native_read_only"})
                    token = HTTP_EVIDENCE_ID.set(evidence_id)
                    try:
                        result = _original.func(**kwargs)
                    except Exception as exc:
                        emit("source.tool.error", {"evidence_id": evidence_id, "tool": name,
                            "request": kwargs, "requested_at": requested_at, "retrieved_at": utc(),
                            "error_type": type(exc).__name__, "mode": "live_native_read_only"})
                        raise
                    finally:
                        HTTP_EVIDENCE_ID.reset(token)
                    if not isinstance(result, str):
                        raise TypeError("Native tool result is not its documented string")
                    http_records = [record for record in capture.records if record.get("evidence_id") == evidence_id]
                    files_after = {str(p): p.stat().st_mtime_ns for p in cache_dir.rglob("*.csv")}
                    cache_hits = [path for path in files_after if files_before.get(path) == files_after[path]]
                    emit("evidence.retrieved", {"evidence_id": evidence_id,
                        "fixture_kind": None, "evidence_kind": "live_native_provider_result",
                        "tool": name, "request": kwargs, "requested_at": requested_at, "retrieved_at": utc(),
                        "provider": "yfinance" if name == "get_verified_market_snapshot" else TOOL_VENDORS.get(name),
                        "source_status": classify(name, result), "content": result,
                        "content_hash": content_digest(result),
                        "http_ids": [record["http_id"] for record in http_records],
                        "source_urls": [record["url"] for record in http_records],
                        "source_time_fields": [field for record in http_records for field in record["source_time_fields"]],
                        "cache_status": "network_observed" if http_records else ("native_session_cache" if cache_hits else "no_http_observed"),
                        "cache_files": [{"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                            for path in files_after],
                        "limitations": ["Native formatted string unchanged; timestamps only when supplied by provider.",
                            "Current-day daily bars may be incomplete and Close is not a certified final daily close.",
                            "HTTP absence may reflect native cache/NO_DATA; not proof of an external request."]})
                    return result
                wrapped_tools.append(StructuredTool.from_function(serve, name=original.name,
                    description=original.description, args_schema=original.args_schema))
            replacements[module] = tuple(wrapped_tools)
        specs = dict(analyst_execution.ANALYST_NODE_SPECS)
        specs["market"] = replace(specs["market"], tools=replacements[market_analyst])
        specs["news"] = replace(specs["news"], tools=replacements[news_analyst])
        for module in (market_analyst, news_analyst):
            stack.enter_context(patch.object(module, "TOOLS", replacements[module]))
        stack.enter_context(patch.object(analyst_execution, "ANALYST_NODE_SPECS", specs))
        metadata = {"mode": "live_native_read_only", "data_vendors": effective["data_vendors"],
            "tool_vendors": effective["tool_vendors"], "cache_dir": str(cache_dir),
            "source_hosts": sorted(SOURCE_HOSTS), "http_timeout": capture.timeout,
            "max_response_bytes": capture.max_bytes, "max_native_retries": retries}
        emit("source.session.start", metadata)
        yield metadata


class _ProbeTrace:
    def __init__(self):
        self.events = []
    def emit(self, kind, payload):
        self.events.append({"kind": kind, "payload": copy.deepcopy(payload)})


def data_preflight(cfg=None, trace=None, as_of_date=None):
    """Actual data-only native probes. Never construct a model or touch budget."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.agents.analysts import market_analyst, news_analyst
    effective = copy.deepcopy(DEFAULT_CONFIG if cfg is None else cfg)
    probe = trace if trace is not None else _ProbeTrace()
    today = datetime.fromisoformat(as_of_date or effective.get("source_as_of") or current_source_date()).date()
    effective.setdefault("source_cache_parent", str(ROOT / "live_experiment/cache"))
    date = today.isoformat()
    started = utc()
    results = {}
    with live_tools(probe, effective) as session:
        available = {tool.name: tool for module in (market_analyst, news_analyst) for tool in module.TOOLS}
        calls = [("get_stock_data", {"symbol": "ETH-USD", "start_date": (today - timedelta(days=10)).isoformat(), "end_date": date, "trade_date": date}),
                 ("get_verified_market_snapshot", {"symbol": "ETH-USD", "curr_date": date, "look_back_days": 5, "trade_date": date}),
                 ("get_news", {"ticker": "ETH-USD", "start_date": (today - timedelta(days=7)).isoformat(), "end_date": date, "trade_date": date}),
                 ("get_global_news", {"curr_date": date, "look_back_days": 7, "limit": 3, "trade_date": date}),
                 ("get_macro_indicators", {"indicator": "fed_funds_rate", "curr_date": date, "look_back_days": 365, "trade_date": date}),
                 ("get_prediction_markets", {"topic": "Ethereum", "limit": 3, "trade_date": date})]
        for name, args in calls:
            try:
                text = available[name].func(**args)
                status = classify(name, text)
                if name == "get_stock_data" and not ("Date" in text and "Close" in text):
                    status = "SOURCE_UNAVAILABLE"
                if name == "get_verified_market_snapshot" and not ("OHLCV" in text and "Close" in text):
                    status = "SOURCE_UNAVAILABLE"
                results[name] = {"status": status, "content_hash": content_digest(text),
                    "content_bytes": len(text.encode("utf-8")), "content": text}
            except Exception as exc:
                results[name] = {"status": "ERROR", "error_type": type(exc).__name__}
        # Probe the public live-only native route separately if UTC run date is
        # considered historical by upstream's local date.today() predicate.
        if results["get_prediction_markets"]["status"] == "HISTORICAL_UNAVAILABLE":
            try:
                text = available["get_prediction_markets"].func(topic="Ethereum", limit=3, trade_date="")
                results["get_prediction_markets_live_route_probe"] = {
                    "status": classify("get_prediction_markets", text), "as_of": None,
                    "scope": "provider reachability only; not data delivered under the UTC dated run",
                    "content_hash": content_digest(text), "content_bytes": len(text.encode("utf-8")), "content": text}
            except Exception as exc:
                results["get_prediction_markets_live_route_probe"] = {"status": "ERROR", "error_type": type(exc).__name__}
    core_ok = all(results[name]["status"] == "AVAILABLE" for name in ("get_stock_data", "get_verified_market_snapshot"))
    return {"status": "PASS" if core_ok else "BLOCKED_CORE_SOURCE", "core_ready": core_ok, "mode": "data_only_live_native_probe",
        "started_at": started, "ended_at": utc(), "as_of": date, "as_of_timezone": "Asia/Calcutta" if as_of_date is None else "caller_declared_date",
        "actual_utc_at_end": utc(), "local_date": current_source_date(),
        "native_host_local_date": datetime.now().date().isoformat(),
        "session": session, "providers": results, "model_calls": 0,
        "events": probe.events if isinstance(probe, _ProbeTrace) else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Optional new preflight JSON path; never overwrites")
    parser.add_argument("--as-of-date", help="Explicit native analysis date; defaults to current Asia/Calcutta date")
    args = parser.parse_args()
    report = data_preflight(as_of_date=args.as_of_date)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"status": report["status"], "as_of": report["as_of"],
        "providers": {name: {key: value for key, value in result.items() if key != "content"}
                      for name, result in report["providers"].items()}, "model_calls": 0}, indent=2))
