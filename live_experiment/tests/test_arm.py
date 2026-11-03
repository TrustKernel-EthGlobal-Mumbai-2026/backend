"""Live arm tests use temporary ledgers, stub graph/source/client, no paid calls."""
import contextlib
import copy
import hashlib
import io
import json
import logging
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from live_experiment import arm
from trustkernel.trace import Trace, Observer, digest, plain, utc


class ArmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "runs").mkdir()
        (self.root / "budget_policy.json").write_text(json.dumps({
            "initial_limit_usd": 3, "hard_limit_usd": 5, "auto_extend_once": True}), encoding="utf-8")
        self.ledger = self.root / "runs/approved-budget.sqlite"
        with contextlib.closing(sqlite3.connect(self.ledger)) as db, db:
            db.executescript("""
                CREATE TABLE budget (id INTEGER PRIMARY KEY, reserved REAL);
                INSERT INTO budget VALUES (1,1.8376825);
                CREATE TABLE budget_policy (id INTEGER PRIMARY KEY, initial_limit REAL, active_limit REAL, hard_limit REAL);
                INSERT INTO budget_policy VALUES (1,3,3,5);
                CREATE TABLE requests (id TEXT PRIMARY KEY, reserved REAL, charge REAL, status TEXT, response_id TEXT);
                INSERT INTO requests VALUES ('prior-unknown',0.16024,NULL,'in_flight_or_unknown',NULL);
            """)
        self.args = SimpleNamespace(arm="sol", model="gpt-6.1-sol", output=str(self.root / "runs/session"),
                                    pair_id="pair-0", deadline=time.time()+500, approve_paid=True,
                                    budget_db=str(self.ledger), budget=5.0)
        self.enterContext(patch.object(arm, "ROOT", self.root))
        self.enterContext(patch.dict(os.environ, {"OPENAI_API_KEY": "offline-test-placeholder"}))

    def bytes_hash(self):
        return hashlib.sha256(self.ledger.read_bytes()).hexdigest()

    def events(self):
        directory = next(Path(self.args.output).glob("sol-*"))
        return directory, [json.loads(line) for line in (directory / "trace.jsonl").read_text(encoding="utf-8").splitlines()]

    def runtime(self, failure=None, final=None, runtime_log=None):
        order = []
        model_calls, budget_calls, graph_calls = [], [], []
        cfgs, states = [], []
        class FakeBudget:
            def __init__(self, *args, **kwargs):
                budget_calls.append((args, kwargs))
            def before(self, messages, metadata):
                order.append("reserve-before-model")
            def settle(self, response, metadata):
                order.append("settle-after-model")
        def model(**kwargs):
            model_calls.append(kwargs)
            return object()
        @contextlib.contextmanager
        def live_tools(trace, cfg):
            order.append("live_tools")
            cfgs.append(copy.deepcopy(cfg))
            trace.emit("source.test_stub", {"status": "test-only", "native_result": "no provider invoked"})
            yield
        @contextlib.contextmanager
        def run_config(cfg):
            order.append("run_config")
            yield
        class Graph:
            def invoke(self, state, config):
                graph_calls.append(config)
                states.append(state)
                observer = config["callbacks"][0]
                observer.on_chat_model_start({}, [["stub prompt"]], run_id="stub-span")
                if runtime_log:
                    logging.warning(runtime_log)
                if failure:
                    raise failure
                observer.on_llm_end({}, run_id="stub-span")
                return {"final_trade_decision": "Decision: Hold for paper review"} if final is None else final
        class Workflow:
            def compile(self):
                return Graph()
        class Setup:
            def __init__(self, *args, **kwargs):
                order.append(("setup", args, kwargs))
            def setup_graph(self, analysts):
                order.append(("analysts", analysts))
                return Workflow()
        class Propagator:
            def create_initial_state(self, ticker, date, **kwargs):
                return {"ticker": ticker, "trade_date": date, **kwargs}
        rt = SimpleNamespace(Trace=Trace, Observer=Observer, digest=digest, plain=plain, utc=utc,
                             Budget=FakeBudget, DEFAULT_CONFIG={"data_vendors": {"news_data": "openai"}},
                             run_config=run_config, GraphSetup=Setup, Propagator=Propagator,
                             ConditionalLogic=lambda *x: x, NormalizedChatOpenAI=model,
                             live_tools=live_tools, network_guard=lambda trace=None: order.append("network_guard"))
        return rt, SimpleNamespace(order=order, models=model_calls, budgets=budget_calls,
                                   configs=cfgs, states=states, graphs=graph_calls)

    def run_stub(self, **runtime_kwargs):
        rt, captured = self.runtime(**runtime_kwargs)
        client = Mock()
        with patch.object(arm, "upstream_check") as pinned, patch.object(arm, "_load_runtime", return_value=rt), \
                patch.object(arm.importlib.metadata, "distributions", return_value=[]), \
                patch.object(arm.httpx, "Client", return_value=client) as make_client, \
                patch.object(arm, "ApiOnlyTransport", return_value=object()), \
                contextlib.redirect_stdout(io.StringIO()):
            result = arm.run(self.args)
        pinned.assert_called_once()
        client.close.assert_called_once()
        self.assertFalse(make_client.call_args.kwargs["trust_env"])
        return result, captured

    def test_paid_gate_is_read_only_and_retains_prior_unknown(self):
        before = self.bytes_hash()
        self.assertEqual(arm.validate_args(self.args)["hard_limit_usd"], 5)
        self.assertEqual(self.bytes_hash(), before)
        with contextlib.closing(sqlite3.connect(self.ledger)) as db, db:
            self.assertEqual(db.execute("SELECT reserved,charge,status FROM requests").fetchone(),
                             (0.16024, None, "in_flight_or_unknown"))

    def test_approval_invalid_budget_deadline_and_model_deny_before_runtime(self):
        mutations = [{"approve_paid": False}, {"budget": 6}, {"budget": float("nan")},
                     {"deadline": 0}, {"deadline": float("inf")}, {"model": "gpt-6.1-terra"},
                     {"budget_db": str(self.root / "new-allowance.sqlite")}]
        for changes in mutations:
            args = copy.copy(self.args)
            args.__dict__.update(changes)
            with self.subTest(changes=changes), patch.object(arm, "_load_runtime") as loader:
                with self.assertRaises((PermissionError, ValueError)):
                    arm.run(args)
                loader.assert_not_called()
        self.assertFalse((self.root / "new-allowance.sqlite").exists())

    def test_stop_and_missing_process_key_do_not_create_run(self):
        (self.root / "STOP").touch()
        with self.assertRaises(PermissionError):
            arm.run(self.args)
        (self.root / "STOP").unlink()
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(PermissionError):
            arm.run(self.args)
        self.assertFalse(Path(self.args.output).exists())

    def test_saved_policy_or_ledger_change_cannot_reset_or_expand_allowance(self):
        (self.root / "budget_policy.json").write_text(json.dumps({
            "initial_limit_usd": 3, "hard_limit_usd": 6, "auto_extend_once": True}), encoding="utf-8")
        with self.assertRaises(PermissionError):
            arm.validate_args(self.args)
        (self.root / "budget_policy.json").write_text(json.dumps({
            "initial_limit_usd": 3, "hard_limit_usd": 5, "auto_extend_once": True}), encoding="utf-8")
        with contextlib.closing(sqlite3.connect(self.ledger)) as db, db:
            db.execute("UPDATE budget_policy SET hard_limit=6 WHERE id=1")
        before = self.bytes_hash()
        with self.assertRaises(PermissionError):
            arm.validate_args(self.args)
        self.assertEqual(before, self.bytes_hash())

    def test_native_config_isolation_explicit_vendors_no_default_mutation(self):
        defaults = {"data_vendors": {"core_stock_apis": "openai", "news_data": "openai"},
                    "tool_vendors": {"get_news": "openai"}, "data_cache_dir": "old-cache",
                    "checkpoint_enabled": True, "max_tool_rounds": 99, "deep_think_llm": "other"}
        before = copy.deepcopy(defaults)
        first = arm.native_config(defaults, self.root / "one", "gpt-6.1-sol")
        second = arm.native_config(defaults, self.root / "two", "gpt-6.1-terra")
        self.assertEqual(defaults, before)
        self.assertNotEqual(first["data_cache_dir"], second["data_cache_dir"])
        self.assertTrue(Path(first["data_cache_dir"]).is_relative_to(self.root / "one"))
        self.assertEqual(first["data_vendors"]["news_data"], "yfinance")
        self.assertEqual(first["data_vendors"]["macro_data"], "fred")
        self.assertEqual(first["data_vendors"]["prediction_markets"], "polymarket")
        self.assertEqual(first["tool_vendors"], {})
        self.assertFalse(first["checkpoint_enabled"])
        self.assertEqual(first["max_tool_rounds"], 2)
        self.assertEqual(first["llm_max_retries"], 0)

    def test_stub_success_wires_budget_and_unmodified_graph_limits(self):
        before = self.bytes_hash()
        old_handlers, old_level = logging.getLogger().handlers[:], logging.getLogger().level
        result, calls = self.run_stub()
        self.assertEqual(result, 0)
        self.assertEqual(before, self.bytes_hash())
        self.assertEqual(logging.getLogger().handlers, old_handlers)
        self.assertEqual(logging.getLogger().level, old_level)
        self.assertEqual(calls.order[:3], ["network_guard", "live_tools", "run_config"])
        self.assertLess(calls.order.index("reserve-before-model"), calls.order.index("settle-after-model"))
        self.assertEqual(calls.models[0]["reasoning_effort"], "medium")
        self.assertEqual(calls.models[0]["max_tokens"], 2048)
        self.assertEqual(calls.models[0]["max_retries"], 0)
        self.assertTrue(calls.models[0]["use_responses_api"])
        self.assertFalse(calls.models[0]["store"])
        args, kwargs = calls.budgets[0]
        self.assertEqual(args[:4], (self.args.budget_db, 5.0, "gpt-6.1-sol", self.args.deadline))
        self.assertEqual(args[6], 24)
        self.assertEqual(kwargs["initial_limit"], 3)
        self.assertIn(("analysts", ["market", "news"]), calls.order)
        setup = next(item for item in calls.order if isinstance(item, tuple) and item[0] == "setup")
        self.assertIs(setup[1][0], setup[1][1])
        self.assertEqual(setup[1][2], (1, 1))
        self.assertEqual(setup[2], {"max_tool_rounds": 2})
        self.assertEqual(calls.graphs[0]["max_concurrency"], 1)

    def test_live_metadata_current_context_no_fixture_artifact(self):
        _, calls = self.run_stub()
        directory, events = self.events()
        manifest = json.loads((directory / "run_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(manifest["context"]["source_mode"], "live_native_market_sources")
        self.assertEqual(manifest["context"]["inference"], "paid-openai")
        self.assertEqual(calls.states[0]["ticker"], "ETH-USD")
        self.assertEqual(calls.states[0]["trade_date"], manifest["context"]["local_date"])
        self.assertEqual(manifest["context"]["local_date"], manifest["context"]["local_context_at"][:10])
        self.assertEqual(manifest["context"]["utc_date"], manifest["context"]["context_at"][:10])
        self.assertEqual(manifest["context"]["context_timezone"], "UTC")
        self.assertNotIn("synthetic", calls.states[0]["instrument_context"].lower())
        self.assertNotIn("fixture_hash", manifest["context"])
        self.assertFalse((directory / "fixture.json").exists())
        self.assertEqual([e["kind"] for e in events].count("decision.paper"), 1)
        decision = next(e for e in events if e["kind"] == "decision.paper")
        self.assertFalse(decision["payload"]["execution_authority"])

    def test_native_local_date_is_distinct_from_utc_at_midnight_boundary(self):
        instant = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)
        india = timezone(timedelta(hours=5, minutes=30), "Asia/Calcutta")
        clocks = arm._clock_context(instant, india)
        self.assertEqual(clocks["utc_date"], "2026-11-02")
        self.assertEqual(clocks["local_date"], "2026-11-03")
        self.assertEqual(clocks["trade_date"], "2026-11-03")
        self.assertEqual(clocks["date_basis"], "current_local_date")
        self.assertEqual(clocks["local_timezone"], "Asia/Calcutta")
        self.assertEqual(datetime.fromisoformat(clocks["context_at"]),
                         datetime.fromisoformat(clocks["local_context_at"]))
        with patch.object(arm, "_clock_context", return_value=clocks):
            _, calls = self.run_stub()
        self.assertEqual(calls.states[0]["trade_date"], "2026-11-03")
        self.assertIn("Native current date 2026-11-03", calls.states[0]["instrument_context"])
        self.assertEqual(calls.graphs[0]["metadata"]["utc_date"], "2026-11-02")

    def test_native_runtime_log_and_failure_text_hide_credentials(self):
        log = "Yahoo crumb = 'crumb-private-value' Cookie: cookie-private-value"
        error = "https://provider.test?api_key=key-private-value&token=token-private-value"
        result, _ = self.run_stub(runtime_log=log, failure=RuntimeError(error))
        directory, events = self.events()
        self.assertEqual(result, 1)
        saved = (directory / "trace.jsonl").read_text(encoding="utf-8") + (directory / "run_manifest.json").read_text(encoding="utf-8")
        for secret in ("crumb-private-value", "cookie-private-value", "key-private-value", "token-private-value"):
            self.assertNotIn(secret, saved)
        self.assertIn("REDACTED", next(e["payload"]["message"] for e in events if e["kind"] == "runtime.log"))
        self.assertNotIn("other-crumb-secret", arm._runtime_text(RuntimeError("crumb: other-crumb-secret")))

    def test_graph_failure_is_traced_without_fallback_or_retry(self):
        result, calls = self.run_stub(failure=RuntimeError("Native source unavailable"))
        directory, events = self.events()
        self.assertEqual(result, 1)
        self.assertEqual(len(calls.models), 1)
        self.assertEqual(len(calls.graphs), 1)
        self.assertNotIn("decision.paper", [e["kind"] for e in events])
        self.assertNotIn("run.end", [e["kind"] for e in events])
        self.assertIn("run.error", [e["kind"] for e in events])
        manifest = json.loads((directory / "run_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "failed")
        self.assertFalse((directory / "fixture.json").exists())

    def test_empty_graph_result_cannot_claim_success(self):
        result, _ = self.run_stub(final={"market_report": "partial"})
        _, events = self.events()
        self.assertEqual(result, 1)
        self.assertIn("run.error", [e["kind"] for e in events])

    def test_pinned_upstream_failure_precedes_any_client(self):
        with patch.object(arm, "upstream_check", side_effect=ValueError("Unpinned source")), \
                patch.object(arm, "_load_runtime") as loader, self.assertRaises(ValueError):
            arm.run(self.args)
        loader.assert_not_called()
        self.assertFalse(Path(self.args.output).exists())

    def test_api_transport_denies_non_native_requests_before_io(self):
        denied = [("GET", "https://api.openai.com/v1/responses"),
                  ("POST", "https://api.openai.com/v1/chat/completions"),
                  ("POST", "http://api.openai.com/v1/responses"),
                  ("POST", "https://example.test/v1/responses"),
                  ("POST", "https://api.openai.com:444/v1/responses"),
                  ("POST", "https://api.openai.com/v1/responses?redirect=1"),
                  ("POST", "https://user:pass@api.openai.com/v1/responses")]
        with arm.ApiOnlyTransport(retries=0) as transport, \
                patch.object(httpx.HTTPTransport, "handle_request", return_value=httpx.Response(200)) as native:
            for method, url in denied:
                with self.subTest(url=url), self.assertRaises(PermissionError):
                    transport.handle_request(httpx.Request(method, url))
            native.assert_not_called()
            transport.handle_request(httpx.Request("POST", "https://api.openai.com/v1/responses"))
            native.assert_called_once()

    def test_normalized_model_payload_configuration_without_invoke(self):
        from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI
        llm = NormalizedChatOpenAI(model="gpt-6.1-sol", api_key="offline-test-placeholder",
                                  base_url=arm.CONFIG["endpoint"], use_responses_api=True,
                                  reasoning_effort="medium", max_tokens=2048, max_retries=0,
                                  store=False, service_tier="default", timeout=60)
        payload = llm._get_request_payload("No network: build payload only")
        self.assertEqual(payload["reasoning"]["effort"], "medium")
        self.assertEqual(payload["max_output_tokens"], 2048)
        self.assertFalse(payload["store"])
        self.assertEqual(payload["model"], "gpt-6.1-sol")

    def test_cli_has_required_parent_args_and_no_fixture_mode(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            arm.build_parser().parse_args(["--mode", "offline", "--fixture", "old.json"])
        self.assertNotIn("--fixture", arm.build_parser().format_help())
        self.assertIn("--approve-paid", arm.build_parser().format_help())


if __name__ == "__main__":
    unittest.main()
