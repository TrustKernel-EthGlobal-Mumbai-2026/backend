# Native live sources and preflight

3 November 2026. Source implementation for the authorized paired 30-minute live-source experiment. Previous recordings remain actual agent runs over synthetic evidence; these new tools call real external providers. This lane makes no model/API inference calls and never accesses the budget ledger. Parent alone launches the paid window.

## API and native behavior

```python
from live_experiment.sources import (
    live_tools, data_preflight, current_source_date, sanitize_text,
)
with live_tools(trace, cfg) as source_session:
    # Parent compiles/invokes original selected TradingAgents graph here.
    # Native names, descriptions, args_schema, injected state and string results persist.
    ...
report = data_preflight(cfg=None, trace=None, as_of_date=current_source_date())
assert report['core_ready']  # Parent gate; not a model call or source-world guarantee.
```

`current_source_date()` follows the user's Asia/Calcutta date. Parent graph state/preflight must consistently use that date; actual UTC retrieval clocks and provider bar/publication times remain distinct. Parent selected local date 2026-11-03 after a UTC-dated probe triggered native Polymarket's historical-withholding rule. `data_preflight` supports explicit caller date, returns `status=PASS|BLOCKED_CORE_SOURCE` and stable `core_ready:bool`. It never creates an LLM/Budget. CLI:

```powershell
.\.venv\Scripts\python.exe -m live_experiment.sources --as-of-date 2026-11-03 --output <new-preflight-json>
.\.venv\Scripts\python.exe -m unittest live_experiment.tests.test_sources -v
```

`live_tools(trace,cfg)` patches process-local market/news `TOOLS` and `ANALYST_NODE_SPECS` and restores them on exit. Every wrapper calls the original native `.func(**kwargs)` and returns the **exact native string**; genuine exceptions are observed and re-raised. No fixture serving, new JSON envelope, invented prices, hidden LLM data vendor or forced snapshot invocation. Existing Observer records actual tool callbacks and model inputs independently. Tool names/descriptions/args-schema objects remain original. `sanitize_text` is exclusively a runtime-log helper for crumb/key/userinfo/Bearer diagnostics, never applied to model-visible source text. Parent may use its own stricter diagnostic sanitizer.

## Native routes and vendor configuration

Pinned upstream is unchanged TradingAgents v0.7.1/c4544913a14ed3df5f1ed7b9e8483270ce20682a. Installed yfinance is1.7.0. Native functions inspected:

| Native agent tool | Native implementation |
|---|---|
| get_stock_data | dataflows.router -> vendors.yahoo.market.get_YFin_data_online |
| get_indicators | router -> yahoo.market.get_stock_stats_indicators_window / yahoo.ohlcv.load_ohlcv |
| get_verified_market_snapshot | agents.tools -> yahoo.snapshot.build_verified_market_snapshot -> yahoo.ohlcv.load_ohlcv(fill_gaps=False) |
| get_news / get_global_news | router -> yahoo.news.get_news_yfinance / get_global_news_yfinance |
| get_macro_indicators | router -> vendors.fred.get_macro_data |
| get_prediction_markets | router -> vendors.polymarket.get_prediction_markets |

`source_config` requires explicit core_stock_apis/technical_indicators/news_data=`yfinance`, macro_data=`fred`, prediction_markets=`polymarket`. Conflicting, `default`, paid or uninspected tool/category routes are rejected. Only selected market/news tools are exposed. No Alpha Vantage or model-backed data fallback is enabled. FRED uses only its native existing-process-key path; missing key yields native DATA_UNAVAILABLE and metadata MISSING_CREDENTIAL, not a fabricated series or a zero observation. No account/key creation.

## HTTP boundaries and capture

`source_http.data_http(trace,cfg)` owns provider method/path/redirect enforcement for **requests.Session.request and curl_cffi.requests.Session.request**. Curl native IO bypasses Python socket audit, so parent `network_guard()` alone is insufficient. Parent installs its Python DNS/socket443/subprocess guard before `live_tools`. Capture saves each transport method as found on entry and delegates through it; it does not bypass any preinstalled wrapper. No model transport is patched: native source HTTP to api.openai.com is denied.

| HTTPS host | Permitted native read operation |
|---|---|
| query1.finance.yahoo.com / query2.finance.yahoo.com | GET/HEAD `/v8/finance/chart/*`, `/v1/test/getcrumb`, `/v1/finance/search`, root reachability |
| fc.yahoo.com | GET/HEAD root, native Yahoo cookie bootstrap |
| finance.yahoo.com | POST `/xhr/ncp`, only queryRef latestNews/newsAll/pressRelease with serviceKey ncp_fin; native read-only Yahoo news query |
| gamma-api.polymarket.com | GET `/public-search` |
| api.stlouisfed.org | GET `/fred/series`, `/fred/series/observations` |

TLS verification is required; verify=False, userinfo URLs, nonHTTPS, non443 ports, general POST/account/subscription/order/consent endpoints and other hosts are denied. Automatic redirects are disabled; each next hop is checked before IO, with at most four followed redirects. Yahoo's consent-POST fallback is intentionally unavailable; if necessary for a provider response it becomes a disclosed source blocker rather than a new permitted action.

Default source timeouts are at most15s per HTTP operation, capped30s even if configured; response bytes default4,000,000 and hard cap8,000,000. Both requests decompressed iteration and curl write callbacks stop oversized responses and raise; truncated content is never returned as valid data. Native Yahoo retries are bounded to at most one retry (two attempts) with at most1s initial backoff. HTTP request count defaults160 per arm context. Parent's540s child/global deadline remains the final runtime bound. Unsupported streaming/custom transport callbacks fail explicitly. These transport/retry limits are observation/safety boundaries, not model-schema or source-value changes.

HTTP events `source.http.start/end/error` retain http_id, evidence_id, transport, method, scrubbed URL, request/retrieval UTC time, status when observed, latency, byte count, response SHA256, redirect index, cache status and provider-declared time fields when JSON supplies them. Yahoo crumbs/FRED keys/tokens are scrubbed from query strings; cookies/auth headers/raw credential response text and exception URLs are never logged. No source publication/bar timestamp is invented when absent. Time fields are identified by pointers in the provider response; a returned-body timestamp does not by itself establish that a particular formatted article used it. Chart epoch arrays retain first/last/count and provider timezone metadata when supplied.

`evidence.retrieved` is out-of-band: evidence_id, fixture_kind=null, evidence_kind=live_native_provider_result, tool/request, request/retrievalUTC, provider, source_status, exact native content/content_hash (UTF8SHA256), http_ids/source_urls/source_time_fields, cache_status/cache_files(path/hash), limitations. ContextVar evidence IDs prevent overlapping tool calls from claiming each other's HTTP records. HTTP network errors retain IDs/URLs/error metadata; native sentinels are recorded unchanged. Statuses AVAILABLE/NO_DATA/SOURCE_UNAVAILABLE/COVERAGE_UNAVAILABLE/HISTORICAL_UNAVAILABLE/MISSING_CREDENTIAL/INPUT_ERROR are narrow native-result markers, not factual support or model-quality verdicts.

## Cache and clocks

Each arm gets a unique new native-live-* cache under its supplied fresh run source-cache root (or an explicit source_cache_parent); implicit upstream home caches are not used. OHLCV cache and yfinance cookie/timezone/ISIN location are set there before fetching. Native cache CSVs are retained and hashed for provenance. Native current-day cache TTL remains900s, so the wrapper reports a cache hit rather than inventing a new network fetch. A cache-derived snapshot may have no HTTP IDs in its own tool call; source cache path/hash and earlier session fetch records preserve that distinction.

Production usage is one context in a fresh arm process. Native yfinance has process-global singleton/in-memory caches; this wrapper does not claim isolated state for arbitrary overlapping runs in one Python process. Parent launches separate fresh arm processes; scoped native dataflow config and new disk caches do not reset source history or alter evidence. Process-local source patches are not an OS firewall.

Daily OHLCV `Date` is not a current tick. Native get_stock_data removes timezone from its formatted index; provider chart timezone/epoch metadata remains captured out-of-band. A latest UTC-day row can be partial even when the user's local calendar has rolled to tomorrow. Native snapshot/indicator formatting and missing-value behavior are preserved; no current-day candle or final close is synthesized.

## Actual data-only probes and limits

First probe `preflight-public-20261103-1.json` used UTCdate2026-11-02 at actual UTC19:16. Core OHLCV/snapshot succeeded. Native Polymarket withheld odds because upstream uses local date.today(); this was identified as a clock/policy distinction, not provider data. That historical probe remains unchanged.

Final agreed-date probe `preflight-public-20261103-2.json` ran UTC2026-11-02 19:20:50.984888–19:20:54.609716 (India3November00:50:50–00:50:54), analysisdate2026-11-03, core_ready=true. Eleven provider HTTP responses observed, including actual Gamma GET/public-search200 (518,669bytes). Results:

| Tool | Native probe outcome |
|---|---|
| ETH-USD OHLCV | AVAILABLE766bytes, SHA2569163d06002e4a6ee886879861f450bd57610f0f051b7a33920172b747b8390aa |
| Native verified snapshot | AVAILABLE1248bytes, SHA2562521888f7896f0e8725b098f50fd5190b6b5f41dc6abc814983f925ec3989845; latest actual row2026-11-02 |
| ETH-tagged news | SOURCE_UNAVAILABLE234bytes: native quote-news endpoint404 and native search has no tagged ETH-USD article; no invented absence of all news |
| Global news | AVAILABLE765bytes via native Yahoo Search |
| FRED macro | MISSING_CREDENTIAL223bytes, native unavailable string unchanged |
| Polymarket | AVAILABLE533bytes via actual public Gamma endpoint |

These are live public source probes, not paid inference or a completed30-minute experiment. Native pandas deprecation warnings were observed; no source/schema/value rewrite was made to suppress them. No budget ledger, credentials outside the native existing FRED presence/path, model API, trade, wallet, signature or on-chain operation was used by this lane.

Thirteen dedicated offline source tests pass, covering exact native string/schema preservation/restoration, native exceptions, sentinel classification, explicit vendor chains, requests/curl wrapper composition, TLS/host/path/method restrictions, every-hop redirects, streaming response byte caps and credential/crumb log redaction. Parent independently runs complete integration/safety tests and gates the approved paid window on source/budget/model preflight. No paid launch is authorized to this lane.
