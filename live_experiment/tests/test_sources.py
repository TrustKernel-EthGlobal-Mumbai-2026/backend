"""Offline source contracts/egress tests; no network, budget or model calls."""
import tempfile
import unittest
from unittest.mock import patch

import requests
from curl_cffi import requests as curl_requests

from live_experiment.source_http import SourceNetworkError, check_request, data_http, safe_url
from live_experiment.sources import _ProbeTrace, classify, live_tools, sanitize_text, source_config

CHART = "https://query2.finance.yahoo.com/v8/finance/chart/ETH-USD"


def requests_response(url, body=b'{"timestamp":[1,2]}', status=200, location=None):
    response = requests.Response()
    response.status_code = status
    response.url = url
    response._content = body
    response._content_consumed = True
    if location:
        response.headers["Location"] = location
    return response


class HttpBoundaryTests(unittest.TestCase):
    def test_reject_unapproved_host_method_port_and_tls(self):
        denied = [("GET", "https://api.openai.com/v1/responses"),
                  ("POST", CHART), ("GET", "http://query2.finance.yahoo.com/v8/finance/chart/ETH-USD"),
                  ("GET", "https://query2.finance.yahoo.com:444/v8/finance/chart/ETH-USD"),
                  ("POST", "https://finance.yahoo.com/ws/obi-integration/v1/subscriptions"),
                  ("POST", "https://consent.yahoo.com/v2/collectConsent")]
        for method, url in denied:
            with self.assertRaises(SourceNetworkError):
                check_request(method, url)
        with data_http():
            with self.assertRaises(SourceNetworkError):
                requests.get(CHART, verify=False)

    def test_requests_composes_with_preinstalled_guard_and_preserves_body(self):
        calls = []
        def prior_guard(session, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return requests_response(url)
        trace = _ProbeTrace()
        with patch.object(requests.sessions.Session, "request", prior_guard):
            with data_http(trace, {"source_http_timeout": 3}) as capture:
                response = requests.get(CHART, timeout=99)
                self.assertEqual(response.json(), {"timestamp": [1, 2]})
                self.assertEqual(capture.records[0]["status"], 200)
                self.assertEqual(capture.records[0]["source_time_fields"][0]["count"], 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2]["timeout"], 3)
        self.assertTrue(calls[0][2]["verify"])
        self.assertFalse(calls[0][2]["allow_redirects"])

    def test_curl_cffi_composes_and_rebuilds_exact_native_response_bytes(self):
        calls = []
        body = b'{"news":[{"pubDate":"2026-11-03T00:00:00Z"}]}'
        def prior_guard(session, method, url, **kwargs):
            calls.append((method, url))
            kwargs["content_callback"](body[:5])
            kwargs["content_callback"](body[5:])
            response = curl_requests.Response()
            response.url, response.status_code = url, 200
            return response
        with patch.object(curl_requests.Session, "request", prior_guard):
            with data_http() as capture:
                response = curl_requests.Session().get(CHART)
                self.assertEqual(response.content, body)
                self.assertEqual(response.json()["news"][0]["pubDate"], "2026-11-03T00:00:00Z")
                self.assertEqual(capture.records[0]["response_bytes"], len(body))
        self.assertEqual(calls, [("GET", CHART)])

    def test_redirect_to_unapproved_host_is_not_sent(self):
        calls = []
        def prior_guard(session, method, url, **kwargs):
            calls.append(url)
            return requests_response(url, b"", 302, "https://example.com/private")
        with patch.object(requests.sessions.Session, "request", prior_guard):
            with data_http():
                with self.assertRaises(SourceNetworkError):
                    requests.get(CHART)
        self.assertEqual(calls, [CHART])

    def test_requests_response_byte_limit_stops_before_tool_consumption(self):
        with patch.object(requests.sessions.Session, "request", lambda session, method, url, **kw: requests_response(url, b"x" * 40)):
            with data_http(cfg={"source_max_response_bytes": 10}) as capture:
                with self.assertRaises(SourceNetworkError):
                    requests.get(CHART)
                self.assertEqual(capture.records[0]["error_type"], "SourceNetworkError")

    def test_curl_response_byte_limit_stops_without_truncation_as_data(self):
        def prior_guard(session, method, url, **kwargs):
            kwargs["content_callback"](b"x" * 40)
            response = curl_requests.Response()
            response.url = url
            return response
        with patch.object(curl_requests.Session, "request", prior_guard):
            with data_http(cfg={"source_max_response_bytes": 10}):
                with self.assertRaises(SourceNetworkError):
                    curl_requests.Session().get(CHART)

    def test_url_capture_never_records_keys_crumb_or_userinfo(self):
        url = safe_url("https://user:password@api.stlouisfed.org/fred/series?api_key=secret&x=1", {"crumb": "othersecret"})
        for secret in ("user", "password", "secret", "othersecret"):
            self.assertNotIn(secret, url)
        self.assertIn("x=1", url)

    def test_only_inspected_yahoo_news_post_query_is_allowed(self):
        check_request("POST", "https://finance.yahoo.com/xhr/ncp?queryRef=latestNews&serviceKey=ncp_fin")
        with self.assertRaises(SourceNetworkError):
            check_request("POST", "https://finance.yahoo.com/xhr/ncp?queryRef=unknown&serviceKey=other")


class NativeToolTests(unittest.TestCase):
    def test_explicit_vendor_chains_no_default_paid_or_hidden_llm_fallback(self):
        cfg = source_config({})
        self.assertEqual(cfg["data_vendors"]["core_stock_apis"], "yfinance")
        for bad in ("default", "openai", "yfinance,alpha_vantage", "alpha_vantage"):
            with self.assertRaises(ValueError):
                source_config({"data_vendors": {"news_data": bad}})
        with self.assertRaises(ValueError):
            source_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})

    def test_native_string_schema_description_and_tool_specs_preserved(self):
        from tradingagents.agents.analysts import market_analyst
        from tradingagents.graph import analyst_execution
        original_tools = market_analyst.TOOLS
        original_specs = analyst_execution.ANALYST_NODE_SPECS
        original = next(tool for tool in original_tools if tool.name == "get_stock_data")
        native_string = "Native exact bytes as Unicode\nµ / no JSON observation wrapper"
        trace = _ProbeTrace()
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(original, "func", lambda **kwargs: native_string):
                with live_tools(trace, {"source_cache_parent": temp}) as session:
                    wrapped = next(tool for tool in market_analyst.TOOLS if tool.name == "get_stock_data")
                    self.assertEqual(wrapped.description, original.description)
                    self.assertIs(wrapped.args_schema, original.args_schema)
                    self.assertEqual(wrapped.func(symbol="ETH-USD", start_date="2026-11-01", end_date="2026-11-02"), native_string)
                    self.assertIn("native-live-", session["cache_dir"])
            self.assertIs(market_analyst.TOOLS, original_tools)
            self.assertIs(analyst_execution.ANALYST_NODE_SPECS, original_specs)
        evidence = next(event["payload"] for event in trace.events if event["kind"] == "evidence.retrieved")
        self.assertEqual(evidence["content"], native_string)
        self.assertEqual(evidence["evidence_kind"], "live_native_provider_result")
        self.assertIsNone(evidence["fixture_kind"])

    def test_native_errors_are_observed_then_reraised_without_fabricated_value(self):
        from tradingagents.agents.analysts import market_analyst
        original = market_analyst.TOOLS[0]
        trace = _ProbeTrace()
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(original, "func", side_effect=ValueError("native input failure")):
                with live_tools(trace, {"source_cache_parent": temp}):
                    with self.assertRaises(ValueError):
                        market_analyst.TOOLS[0].func(symbol="ETH-USD", start_date="bad", end_date="bad")
        self.assertTrue(any(event["kind"] == "source.tool.error" for event in trace.events))
        self.assertFalse(any(event["kind"] == "evidence.retrieved" for event in trace.events))

    def test_native_withholding_and_error_sentinels_are_not_data(self):
        self.assertEqual(classify("get_prediction_markets", "Prediction-market odds are withheld for date"), "HISTORICAL_UNAVAILABLE")
        self.assertEqual(classify("get_news", "DATA_UNAVAILABLE: native error"), "SOURCE_UNAVAILABLE")
        self.assertEqual(classify("get_news", "NO_DATA_AVAILABLE: no observations"), "NO_DATA")

    def test_runtime_log_sanitizer_scrubs_yahoo_crumb_and_keys(self):
        text = sanitize_text("GET https://user:pass@example.com/x?crumb=abcSECRET&api_key=keySECRET {'crumb': 'otherSECRET'} Bearer bearerSECRET")
        for value in ("abcSECRET", "keySECRET", "otherSECRET", "bearerSECRET", "user:pass"):
            self.assertNotIn(value, text)
        self.assertIn("[REDACTED]", text)


if __name__ == "__main__":
    unittest.main()
