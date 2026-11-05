"""Authored HTTP/data only. Never use a real source, model, key or budget."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import correction_sources as sources
from live_experiment.source_http import SourceNetworkError

CHART = "https://query2.finance.yahoo.com/v8/finance/chart/ETH-USD"


def authored_text(tool):
    if tool == "get_stock_data":
        return "# AUTHORED TEST OHLCV\nDate,Open,High,Low,Close,Volume\n2026-11-05,1,2,1,2,10\n"
    if tool == "get_indicators":
        return "## AUTHORED TEST indicator\n2026-11-05: 1.25\n"
    if tool == "get_verified_market_snapshot":
        return "## AUTHORED TEST snapshot\n- Latest trading row used: 2026-11-05\n| Close | 2.00 |\n"
    return "## AUTHORED TEST News\n### Authored article (source: test)\nNo real publication.\n"


def schemas():
    return {call["tool"]: dict(description="Authored test schema", args_schema={"type": "object"})
            for call in sources.make_plan("2026-11-05")["calls"]}


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def capture(self, override=None, *, tool_schemas=None):
        output = self.root / ("authored-" + str(len(list(self.root.iterdir()))))
        output.mkdir()
        plan = sources.make_plan("2026-11-05")
        trace = sources.CaptureTrace()
        writer = sources.Artifacts(output)
        def invoke(name, args):
            trace.emit("source.http.end", {"http_id": "authored-http-" + sources.request_key(name, args),
                "url": CHART, "status": 200, "retrieved_at": "2026-11-05T00:00:00+00:00"})
            return override(name, args) if override else authored_text(name)
        result = sources._record_bundle(output, plan, invoke, trace=trace, schemas=tool_schemas or schemas(),
            upstream_binding={"commit": sources.PIN, "scope": "AUTHORED TEST NO NATIVE EXECUTION"},
            artifacts=writer, clock=lambda: "2026-11-05T00:00:00+00:00")
        return result, sources.ReplayBundle(result["manifest_path"], expected_sha256=result["manifest_sha256"])

    def rewrite(self, result, mutate):
        path = Path(result["manifest_path"])
        value = json.loads(path.read_bytes())
        mutate(value)
        path.write_text(sources.canonical(value), encoding="utf-8")
        return path, sources.sha(path.read_bytes())

    def test_default_cli_preflight_performs_no_fetch_or_writes(self):
        with patch.object(sources, "capture_once", side_effect=AssertionError("capture forbidden")), \
             patch.object(sources.subprocess, "run", side_effect=AssertionError("subprocess forbidden")), \
             patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(sources.main(["--as-of", "2026-11-05"]), 0)
        value = json.loads(stdout.getvalue())
        self.assertEqual(value["status"], "PLAN_ONLY_NO_FETCH")
        self.assertEqual(value["network_calls"], 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_plan_bounded_catalog_order_and_no_paid_routes(self):
        plan = sources.make_plan("2026-11-05")
        self.assertEqual(len(plan["calls"]), 7)
        self.assertEqual([c["args"]["indicator"] for c in plan["calls"][1:4]], list(sources.INDICATORS))
        self.assertEqual(plan["calls"][4]["tool"], "get_verified_market_snapshot")
        self.assertEqual(plan["calls"][0]["args"]["start_date"], "2026-09-06")
        for bad in (29, 91, True):
            with self.assertRaises(sources.SourceBundleError):
                sources.make_plan("2026-11-05", bad)
        with self.assertRaises(ValueError):
            sources.make_plan("not-a-date")

    def test_live_arguments_accept_native_ranges_defaults_and_reject_unsafe_args(self):
        stock = dict(symbol="ETH-USD", trade_date="2026-11-05", start_date="2026-10-01", end_date="2026-11-04")
        self.assertEqual(sources._live_arguments("get_stock_data", stock, "2026-11-05"), stock)
        indicators = dict(symbol="ETH-USD", trade_date="2026-11-05", curr_date="2026-11-05", indicator="rsi, macd")
        self.assertEqual(sources._live_arguments("get_indicators", indicators, "2026-11-05")["look_back_days"], 30)
        for bad in (dict(stock, start_date="2020-01-01"), dict(stock, end_date="2026-11-06"), dict(stock, symbol="OTHER"), dict(stock, trade_date="")):
            with self.assertRaises(sources.SourceBundleError):
                sources._live_arguments("get_stock_data", bad, "2026-11-05")
        with self.assertRaises(sources.SourceBundleError):
            sources._live_arguments("get_indicators", dict(indicators, look_back_days=True), "2026-11-05")

    def test_exact_replay_native_string_status_refs_and_detached_metadata(self):
        result, bundle = self.capture()
        for offer in bundle.offers():
            served = bundle.resolve(offer["tool"], offer["args"])
            self.assertEqual(served["text"], authored_text(offer["tool"]))
            self.assertEqual(served["status"], "AVAILABLE")
            self.assertEqual(served["source_refs"][0]["manifest_sha256"], result["manifest_sha256"])
            self.assertEqual(served["text_origin"], "NATIVE_UNCHANGED")
            self.assertFalse(served["continuously_live"])
            served["coverage"]["requested"].clear()
            self.assertEqual(bundle.resolve(offer["tool"], offer["args"])["text"], authored_text(offer["tool"]))
        exposed = bundle.manifest
        exposed["as_of"] = "1900-01-01"
        self.assertEqual(bundle.manifest["as_of"], "2026-11-05")

    def test_wrong_args_dates_default_limits_combined_indicators_are_unavailable(self):
        _, bundle = self.capture()
        for call in bundle.offers():
            changed = copy.deepcopy(call["args"])
            changed.pop("trade_date")
            served = bundle.resolve(call["tool"], changed)
            self.assertEqual(served["status"], "UNAVAILABLE_ARGUMENTS")
            self.assertEqual(served["source_refs"], [])
            self.assertEqual(served["as_of_timezone"], "Asia/Calcutta")
            self.assertTrue(served["text"].startswith("DATA_UNAVAILABLE:"))
        indicator = copy.deepcopy(bundle.offers()[1])
        indicator["args"]["indicator"] = "rsi,macd"
        self.assertEqual(bundle.resolve(indicator["tool"], indicator["args"])["status"], "UNAVAILABLE_ARGUMENTS")

    def test_unavailable_native_text_never_becomes_available_snapshot(self):
        _, bundle = self.capture(lambda name, args: "DATA_UNAVAILABLE: authored failure" if name == "get_verified_market_snapshot" else authored_text(name))
        offer = bundle.offers()[4]
        served = bundle.resolve(offer["tool"], offer["args"])
        self.assertEqual(served["status"], "SOURCE_UNAVAILABLE")
        self.assertEqual(served["source_status"], "SOURCE_UNAVAILABLE")
        self.assertEqual(served["text"], "DATA_UNAVAILABLE: authored failure")
        self.assertFalse(bundle.manifest["core_ready"])

    def test_native_exception_news_gap_and_all_na_indicators_are_explicit(self):
        def invoke(name, args):
            if name == "get_verified_market_snapshot":
                raise RuntimeError("private diagnostic must not be retained")
            if name == "get_indicators":
                return "## Authored indicator\n2026-11-05: N/A\n"
            if name == "get_global_news":
                return "No global news found between authored dates"
            return authored_text(name)
        result, bundle = self.capture(invoke)
        self.assertEqual(bundle.offers()[4]["status"], "ERROR")
        self.assertEqual(bundle.offers()[1]["status"], "NO_DATA")
        self.assertEqual(bundle.offers()[5]["status"], "NO_DATA")
        self.assertNotIn("private diagnostic", Path(result["manifest_path"]).read_text())

    def test_secret_native_output_refused_without_mutating_it_into_evidence(self):
        _, bundle = self.capture(lambda name, args: "DATA_UNAVAILABLE: token=authored-secret" if name == "get_news" else authored_text(name))
        served = bundle.resolve("get_news", bundle.offers()[-1]["args"])
        self.assertEqual(served["status"], "SECRET_BEARING_NATIVE_OUTPUT_REFUSED")
        self.assertEqual(served["text_origin"], "UNAVAILABLE_SENTINEL")
        self.assertNotIn("authored-secret", sources.canonical(bundle.manifest))

    def test_oversize_native_model_exposure_is_not_silent_truncation(self):
        text = authored_text("get_news") + ("x" * sources.LIMITS["max_model_text_bytes"])
        _, bundle = self.capture(lambda name, args: text if name == "get_news" else authored_text(name))
        served = bundle.resolve("get_news", bundle.offers()[-1]["args"])
        self.assertEqual(served["status"], "MODEL_OUTPUT_TOO_LARGE")
        self.assertEqual(served["text_origin"], "UNAVAILABLE_SENTINEL")
        self.assertNotEqual(served["text"], text[:sources.LIMITS["max_model_text_bytes"]])

    def test_manifest_artifact_tampering_and_loaded_prefix_is_immutable(self):
        result, bundle = self.capture()
        offer = bundle.offers()[0]
        original = bundle.resolve(offer["tool"], offer["args"])
        content = bundle.manifest["entries"][0]["content"]
        path = Path(result["manifest_path"]).parent/content["path"]
        path.write_bytes(b"changed")
        self.assertEqual(bundle.resolve(offer["tool"], offer["args"]), original)
        with self.assertRaises(sources.SourceBundleError):
            sources.ReplayBundle(result["manifest_path"], expected_sha256=result["manifest_sha256"])
        result2, _ = self.capture()
        Path(result2["manifest_path"]).write_text("{}")
        with self.assertRaises(sources.SourceBundleError):
            sources.ReplayBundle(result2["manifest_path"], expected_sha256=result2["manifest_sha256"])

    def test_duplicate_missing_query_plan_schema_status_path_mutations_rejected(self):
        mutations = [lambda m: m["entries"].append(copy.deepcopy(m["entries"][0])),
                     lambda m: m["entries"].pop(),
                     lambda m: m["plan"].update(stock_days=90),
                     lambda m: m["schemas"]["get_news"].update(description="changed"),
                     lambda m: m["entries"][0].update(status="SOURCE_UNAVAILABLE"),
                     lambda m: m["entries"][0]["content"].update(path="../outside.txt"),
                     lambda m: m["entries"][0].update(as_of="1900-01-01")]
        for mutate in mutations:
            result, _ = self.capture()
            path, fingerprint = self.rewrite(result, mutate)
            with self.subTest(mutate=mutate), self.assertRaises(sources.SourceBundleError):
                sources.ReplayBundle(path, expected_sha256=fingerprint)

    def test_capture_never_overwrites_and_subprocess_deadline_retains_partial_only(self):
        with self.assertRaises(FileExistsError), patch.object(sources.subprocess, "run", side_effect=AssertionError("no launch")):
            sources.capture_once(self.root, self.root, sources.make_plan("2026-11-05"))
        target = self.root / "partial"
        with patch.object(sources.subprocess, "run", side_effect=subprocess.TimeoutExpired("authored", 90)):
            with self.assertRaisesRegex(sources.SourceBundleError, "deadline"):
                sources.capture_once(target, self.root, sources.make_plan("2026-11-05"))
        self.assertTrue((target/"plan.json").is_file())
        self.assertFalse((target/"manifest.json").exists())

    def test_actual_retained_bar_history_counts_exclude_future_and_disclose_gaps(self):
        raw = b"Date,Open,High,Low,Close,Volume\n2026-11-01,1,2,1,2,10\n2026-11-03,1,2,1,2,10\n2026-11-06,1,2,1,2,10\n"
        coverage = sources._bar_coverage(raw, "2026-11-05")
        self.assertEqual(coverage["rows"], 3)
        self.assertEqual(coverage["rows_on_or_before_asof"], 2)
        self.assertEqual(coverage["finite_close_rows_on_or_before_asof"], 2)
        self.assertIn("2026-11-02", coverage["missing_daily_dates"])
        self.assertFalse(coverage["at_least_200_real_close_rows"])

    def test_history_readiness_rejects_missing_invalid_duplicate_and_future_dates(self):
        invalid = b"Date,Close\n" + b",2\n"*200 + b"2026-02-30,2\n"*200 + b"not-a-date,2\n"*200
        coverage = sources._bar_coverage(invalid, "2026-11-05")
        self.assertFalse(coverage["at_least_200_real_close_rows"])
        self.assertEqual(coverage["invalid_date_rows"], 600)
        self.assertEqual(coverage["finite_close_rows_on_or_before_asof"], 0)
        duplicate = b"Date,Close\n" + b"2026-11-01,2\n"*200
        coverage = sources._bar_coverage(duplicate, "2026-11-05")
        self.assertFalse(coverage["at_least_200_real_close_rows"])
        self.assertEqual(coverage["finite_close_rows_on_or_before_asof"], 1)
        self.assertEqual(coverage["duplicate_valid_date_rows"], 199)
        future = b"Date,Close\n" + b"2026-11-06,2\n"*200
        coverage = sources._bar_coverage(future, "2026-11-05")
        self.assertFalse(coverage["at_least_200_real_close_rows"])
        self.assertEqual(coverage["future_dated_rows"], 200)
        self.assertEqual(coverage["rows_on_or_before_asof"], 0)
        valid = b"Date,Close\n" + b"".join(((sources.date(2026,11,5)-sources.timedelta(days=i)).isoformat()+",2\n").encode() for i in range(200))
        coverage = sources._bar_coverage(valid, "2026-11-05")
        self.assertTrue(coverage["at_least_200_real_close_rows"])
        self.assertEqual(coverage["finite_close_rows_on_or_before_asof"], 200)

    def test_data_only_child_denies_model_dns_local_socket_and_child_process(self):
        code = """
import json, socket, subprocess, sys
from tools.correction_sources import _data_only_socket_guard
_data_only_socket_guard()
denied = []
for host in ('api.openai.com', 'api.stlouisfed.org', 'gamma-api.polymarket.com'):
    try: socket.getaddrinfo(host, 443)
    except PermissionError: denied.append(host)
try:
    with socket.socket() as connection: connection.connect(('127.0.0.1',443))
except PermissionError: denied.append('local_socket')
try: subprocess.run([sys.executable,'-c','pass'])
except PermissionError: denied.append('child_process')
print(json.dumps(denied))
"""
        result = subprocess.run([sys.executable, "-S", "-B", "-c", code], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(len(json.loads(result.stdout)), 5)


class AuthoredHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.trace = sources.CaptureTrace()
        self.capture = sources.retaining_http_class(sources.Artifacts(self.root))(self.trace,
            {"source_http_timeout": 2, "source_max_response_bytes": 512, "source_max_http_requests": 3})

    @staticmethod
    def response(url, body, status=200, location=None):
        return SimpleNamespace(status_code=status, url=url, headers={"Location": location} if location else {},
                               iter_content=lambda size: iter([body[:8], body[8:]]), close=lambda: None)

    def test_reuses_guard_and_retains_exact_nonsecret_http_separately(self):
        body = b'{"chart":{"result":[{"meta":{"exchangeTimezoneName":"UTC","dataGranularity":"1d"}}]},"timestamp":[1,2]}'
        calls = []
        def authored(session, method, url, **kwargs):
            calls.append(kwargs)
            return self.response(url, body)
        result = self.capture.request("requests", authored, None, "GET", CHART, (), {"timeout": 999})
        self.assertEqual(result._content, body)
        record = self.trace.events[-1]["payload"]
        artifact = record["body_artifact"]
        self.assertEqual((self.root/artifact["path"]).read_bytes(), body)
        self.assertEqual(record["provider_metadata"]["dataGranularity"], "1d")
        self.assertEqual(calls[0]["timeout"], 2)
        self.assertTrue(calls[0]["verify"])
        self.assertFalse(calls[0]["allow_redirects"])

    def test_redacted_http_and_handshake_body_omitted_native_response_unchanged(self):
        body = b'{"access_token":"demo-secret","price":"authored"}'
        result = self.capture.request("requests", lambda session, method, url, **kw: self.response(url, body),
                                      None, "GET", CHART, (), {})
        self.assertEqual(result._content, body)
        record = self.trace.events[-1]["payload"]
        retained = (self.root/record["body_artifact"]["path"]).read_bytes()
        self.assertNotIn(b"demo-secret", retained)
        self.assertEqual(record["body_retention"], "REDACTED")
        self.capture.request("requests", lambda session, method, url, **kw: self.response(url, b"authored-crumb"),
                             None, "GET", "https://query1.finance.yahoo.com/v1/test/getcrumb", (), {})
        self.assertNotIn("body_artifact", self.trace.events[-1]["payload"])
        self.assertEqual(self.trace.events[-1]["payload"]["body_retention"], "HANDSHAKE_SECRET_BODY_OMITTED")

    def test_every_redirect_checked_and_oversized_body_not_saved(self):
        calls = []
        def authored(session, method, url, **kwargs):
            calls.append(url)
            return self.response(url, b"", 302, "https://api.openai.com/v1/responses")
        with self.assertRaises(SourceNetworkError):
            self.capture.request("requests", authored, None, "GET", CHART, (), {})
        self.assertEqual(calls, [CHART])
        with self.assertRaises(SourceNetworkError):
            self.capture.request("requests", lambda session, method, url, **kw: self.response(url, b"x"*600), None, "GET", CHART, (), {})

    def test_authored_curl_callback_preserves_body_and_refuses_wrong_destination(self):
        body = b'{"timestamp":[1,2]}'
        def authored(session, method, url, **kwargs):
            kwargs["content_callback"](body[:4])
            kwargs["content_callback"](body[4:])
            return self.response(url, b"")
        result = self.capture.request("curl_cffi", authored, None, "GET", CHART, (), {})
        self.assertEqual(result.content, body)
        self.assertEqual((self.root/self.trace.events[-1]["payload"]["body_artifact"]["path"]).read_bytes(), body)
        with self.assertRaises(SourceNetworkError), patch.object(sources.source_http, "SOURCE_HOSTS", sources.YAHOO_HOSTS):
            self.capture.request("curl_cffi", authored, None, "GET", "https://gamma-api.polymarket.com/public-search", (), {})


@unittest.skipUnless(os.environ.get("CORRECTION_SOURCES_TEST_UPSTREAM"),
                     "Optional pinned native dependency/schema test: set CORRECTION_SOURCES_TEST_UPSTREAM and use cached native environment")
class NativeSchemaTests(unittest.TestCase):
    setUp = SourceTests.setUp
    capture = SourceTests.capture

    def test_real_native_cache_store_lookup_across_deleted_call_directories(self):
        import shutil
        import yfinance.cache as cache
        previous_cookie_object = None
        for index in (1, 2):
            call = self.root/f"real-cache-call-{index}"
            call.mkdir()
            private = call/"private-cache"
            sources.LiveSourceSession._cache_reset(private)
            cache.set_cache_location(str(private/"native"))
            try:
                timezone_cache = cache.get_tz_cache()
                timezone_cache.store("AUTHORED", "UTC")
                self.assertEqual(timezone_cache.lookup("AUTHORED"), "UTC")
                cookie_cache = cache.get_cookie_cache()
                self.assertIsNot(cookie_cache, previous_cookie_object)
                previous_cookie_object = cookie_cache
                # Only authored values in these new local test databases.
                cookie_cache.store("authored-test", {"fixture": index})
                self.assertEqual(cookie_cache.lookup("authored-test")["cookie"], {"fixture": index})
                isin_cache = cache.get_isin_cache()
                isin_cache.store("AUTHORED", "ETH-USD")
                self.assertEqual(isin_cache.lookup("AUTHORED"), "ETH-USD")
                for manager in (cache._TzDBManager, cache._CookieDBManager, cache._ISINDBManager):
                    self.assertTrue(Path(manager.get_location()).resolve().is_relative_to(private))
            finally:
                sources.LiveSourceSession._cache_reset(private, close_only=True)
                if private.exists():
                    shutil.rmtree(private)
            self.assertFalse(private.exists())
            self.assertIsNone(cache._CookieCacheManager._Cookie_cache)
            self.assertNotIn("_cookie_cache", vars(cache._CookieCacheManager))

    def test_native_cache_reset_refuses_missing_real_field_without_creating_alias(self):
        import yfinance.cache as cache
        manager = cache._CookieCacheManager
        original = manager._Cookie_cache
        delattr(manager, "_Cookie_cache")
        try:
            with self.assertRaisesRegex(sources.SourceBundleError, "manager contract"):
                sources.LiveSourceSession._cache_reset(self.root/"missing-field"/"private-cache")
            self.assertNotIn("_cookie_cache", vars(manager))
        finally:
            manager._Cookie_cache = original
    def test_actual_pinned_schema_and_description_are_preserved_without_native_execution(self):
        from tools.tradingagents_integration import checked_upstream, real_runtime
        upstream = checked_upstream(os.environ["CORRECTION_SOURCES_TEST_UPSTREAM"])
        with real_runtime(upstream):
            from tradingagents.agents.analysts import market_analyst, news_analyst
            originals = tuple(tool for module in (market_analyst, news_analyst) for tool in module.TOOLS)
            allowed = {call["tool"] for call in sources.make_plan("2026-11-05")["calls"]}
            actual = {tool.name: dict(description=tool.description, args_schema=tool.args_schema.model_json_schema())
                      for tool in originals if tool.name in allowed}
            _, bundle = self.capture(tool_schemas=actual)
            observed = []
            bound = bundle.bind_tools(originals, lambda *args: observed.append(args))
            self.assertEqual(len(bound), 5)
            for tool in bound:
                original = next(item for item in originals if item.name == tool.name)
                self.assertIs(tool.args_schema, original.args_schema)
                self.assertEqual(tool.description, original.description)
            stock = next(tool for tool in bound if tool.name == "get_stock_data")
            args = bundle.offers()[0]["args"]
            self.assertEqual(stock.func(**args), authored_text("get_stock_data"))
            self.assertEqual(observed[0][2]["status"], "AVAILABLE")
            with patch.object(originals[0], "func", side_effect=AssertionError("never native")):
                self.assertTrue(stock.func(**args))
            originals_by_name = {tool.name: tool for tool in originals}
            description = originals_by_name["get_stock_data"].description
            with patch.object(originals_by_name["get_stock_data"], "description", description + " changed"):
                with self.assertRaises(sources.SourceBundleError):
                    bundle.bind_tools(originals, lambda *args: None)

    def test_thin_live_session_executes_each_call_with_fresh_cache_and_metadata(self):
        import requests
        from tools.tradingagents_integration import checked_upstream, real_runtime
        upstream = checked_upstream(os.environ["CORRECTION_SOURCES_TEST_UPSTREAM"])
        with real_runtime(upstream):
            from tradingagents.agents.analysts import market_analyst, news_analyst
            originals = tuple(tool for module in (market_analyst, news_analyst) for tool in module.TOOLS)
            stock = next(tool for tool in originals if tool.name == "get_stock_data")
            sent, observed, caches = [], [], []
            def authored_http(connection, method, url, **kwargs):
                response = requests.Response()
                response.url, response.status_code = url, 200
                text = "DATA_UNAVAILABLE: authored outage" if not sent else authored_text("get_stock_data")
                response._content, response._content_consumed = text.encode(), True
                sent.append(url)
                return response
            def authored_native(**arguments):
                from tradingagents.dataflows.config import get_config
                caches.append(get_config()["data_cache_dir"])
                data = Path(caches[-1])
                data.mkdir(parents=True, exist_ok=True)
                (data/"ETH-USD-YFin-data.csv").write_text("Date,Close\n2026-11-05,2\n")
                return requests.get(CHART).text
            with patch.object(requests.sessions.Session, "request", authored_http), patch.object(stock, "func", authored_native):
                with sources.live_source_session(self.root/"live-arm", as_of="2026-11-05", upstream=upstream,
                    original_tools=originals, on_result=lambda *args: observed.append(args)) as session:
                    self.assertEqual(sent, [])
                    wrapped = next(tool for tool in session.tools if tool.name == stock.name)
                    self.assertIs(wrapped.args_schema, stock.args_schema)
                    self.assertEqual(wrapped.description, stock.description)
                    arguments = dict(symbol="ETH-USD", trade_date="2026-11-05", start_date="2026-10-01", end_date="2026-11-05")
                    first = session.call("get_stock_data", arguments)
                    second = session.call("get_stock_data", arguments)
                    self.assertEqual(len(sent), 2)
                    self.assertNotEqual(caches[0], caches[1])
                    self.assertEqual(first["source_status"], "SOURCE_UNAVAILABLE")
                    self.assertEqual(second["source_status"], "AVAILABLE")
                    self.assertEqual(second["text"], authored_text("get_stock_data"))
                    self.assertEqual(second["mode"], "LIVE_NATIVE_PER_CALL")
                    self.assertEqual(second["retrieval_status"], "HTTP_OBSERVED")
                    self.assertEqual(len(second["fresh_bar_artifacts"]), 1)
                    self.assertTrue((Path(second["source_refs"][0]["artifact_root"])/second["fresh_bar_artifacts"][0]["artifact"]["path"]).is_file())
                    self.assertTrue(second["native_executed"])
                    self.assertEqual(len(observed), 2)
                    invalid = session.call("get_stock_data", dict(arguments, end_date="2026-11-06"))
                    self.assertFalse(invalid["native_executed"])
                    self.assertEqual(invalid["source_refs"], [])
                    self.assertEqual(len(sent), 2)
                receipts = list((self.root/"live-arm").glob("call-*/receipt.json"))
                self.assertEqual(len(receipts), 2)
                self.assertFalse(list((self.root/"live-arm").glob("call-*/private-cache")))


if __name__ == "__main__":
    unittest.main()
