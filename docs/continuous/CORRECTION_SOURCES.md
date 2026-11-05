# Live native sources and audit replay for the correction experiment

## Current user direction: LIVE fetch on every source invocation

The common pre-capture experiment plan below is superseded. It remains an audit
and offline replay utility only. The user selected fresh native reads when each
agent calls a source; timings, availability and evidence can differ across arms.
No real source fetch or model call has been performed by lane B.

Implemented live API candidate (independent root review pending):

```python
with live_source_session(new_arm_source_dir, as_of=run_date,
                         upstream=checked_native_checkout,
                         original_tools=original_native_tools,
                         on_result=host_source_observer, trace=runtime_trace) as session:
    native_schema_preserving_tools = session.tools
    # Model/ToolNode chooses actual calls; no proactive source call on enter.
    observation = session.call(tool_name, full_native_arguments)
```

`on_result(name, actual_arguments, result)` retains the previous metadata shape:
text/status/source_status/source_refs/http_refs/coverage/captured_at/as_of/
as_of_timezone, with mode LIVE_NATIVE_PER_CALL and explicit HTTP/cache observations.
The wrapped tool returns native text, while C records actual availability and
source refs. Each valid invocation executes the native function with its actual
validated arguments. There is no fixed-query unavailable/replay substitute for
a valid live request. Repeated identical arguments still execute again.

Proposed live bounds: fixed ETH-USD and trusted run date; stock ranges within
trailing90 days, native indicator1..3 names and lookback1..30, snapshot1..30rows,
news windows<=30days and limit<=5, no future dates. Native argument defaults are
honored inside these bounds. Fresh per-call caches and cleared known yfinance
response memoization prevent silently reusing old quote responses. Actual HTTP
presence remains observable; no HTTP means no new-network-retrieval claim.

C must install `live_experiment.safety.network_guard` with Yahoo-only source
hosts, equivalent file/SQLite write guards and its modelApiOnlyTransport.
It must **not** first install old trustkernel's API-only `child_guards`, since
audit hooks cannot be relaxed. Upstream git checks finish before guards. The B
context reuses existing `sources.live_tools`/`source_http.data_http` unchanged,
preserves original tool schemas, and never handles model credentials or budget.
Live calls are serialized because native cache/tool patching is process-global.
Root's420-second arm deadline is authoritative; proposed source limits are12
native calls,96HTTP requests,12HTTP per call,8sec/2MB per response,48MB retained,
16KB model text, and a30sec soft boundary before another HTTP request.

The remaining common-capture sections document the earlier audit-only utility;
they are **not** the selected paid experiment path. Root reviews the new immutable
live implementation/tests before any fetch. There is no identical-evidence claim.
`capture_once`/`ReplayBundle` are not prerequisites for this paid path.

The live result adds `native_executed`, `retrieval_status` (HTTP_OBSERVED versus
NO_HTTP_OBSERVED), `cache_status`, `fresh_per_call_cache`, `fresh_bar_artifacts`,
`requested_at` and `native_error_type`. Valid calls preserve the native text;
unavailable native strings keep unavailable source_status even when ToolNode
returns successfully. Invalid bounded arguments return NOT_FETCHED with no source
receipt and native_executed=false. Each executed call gets a unique source ref
and durable receipt.json; its relative content descriptor is qualified by
artifact_root. Callback signature is unchanged: `(name, args, result)`.

The wrapper uses the existing live_tools context for each native invocation,
with fresh disk cache and cleared inspected yfinance response memoization/cache
managers. It copies new CSV/HTTP artifacts before closing/removing only the new
private cache. If no HTTP was observed, the result makes no new-network-retrieval
claim. Context creation performs no source fetch. It does not run upstream git
subprocesses after C installs its guards: C supplies its already checked pinned
checkout, and receipts explicitly label HOST_CHECKED_BEFORE_GUARDS.

Current validation: **21 tests pass** in the cached native environment with no
skips; base Python has **19 passes and 2 explicit optional skips**. The new native
test uses authored HTTP only: repeated identical arguments cause two actual
wrapper/native invocations, two new cache paths, two HTTP receipts and independently
observed SOURCE_UNAVAILABLE/AVAILABLE results. It checks unchanged schema identity,
native strings, no fetch on entry, invalid future arguments without native execution
or source refs, and removal of each new private cache. Existing replay/date-metadata
tests remain for audits. No live provider or model request was performed by B.

The single integration dependency is C's guard selection: use the existing
live-capable network guard before source invocations, plus equivalent write/SQLite
guards and modelApiOnlyTransport. Installing old API-only child_guards first
cannot be repaired by this context. No new source broker or worker is required
for the selected live path. C passes session.tools into its existing ToolNode.

Status: implemented offline source API candidate, 5 November 2026; independent root review
required before fresh data capture or C binding. No model/source call by lane B.
Base `39e0e1c`, branch `codex/correction-live-sources`; this work does not extend
the stopped paired smoke or alter its history. Only the new source module, test
and this document are owned here. Shared README/CI/index/manifest remain untouched.

## API proposal for C and the orchestrator

```python
from tools.correction_sources import make_plan, capture_once, ReplayBundle
plan = make_plan(as_of="2026-11-05", stock_days=60)
# ROOT ONLY, after independent review, ONCE before both arms:
capture = capture_once(new_output_directory, pinned_upstream_path, plan)
bundle = ReplayBundle(capture["manifest_path"],
                      expected_sha256=capture["manifest_sha256"])
offers = bundle.offers()  # exact full native tool arguments and availability
result = bundle.resolve(tool_name, full_native_arguments)
tools = bundle.bind_tools(original_native_tools, on_result)
```

`on_result(name, arguments, result)` receives detached host metadata for the
actual query. Wrapped ToolNode calls receive **only** result.text, preserving the
native string. Original name, description and args_schema identity remain;
schema/description bytes must match the capture. This is a data-only acquisition
manifest, **not** a new verification/checkpoint schema or a model-correction claim.

`result` fields: text, status, source_status, source_refs, http_refs, coverage,
captured_at, as_of, as_of_timezone, mode=CAPTURED_REPLAY, continuously_live=false,
text_origin=NATIVE_UNCHANGED|UNAVAILABLE_SENTINEL, match=EXACT|NONE.
Source refs bind capture_id + manifest_sha256 + entry_id + native content file/hash.
HTTP refs retain request/retrieval clocks, redacted URL, response status/hash/size,
provider time/TZ fields and separately retained privacy-filtered body references.

C must count the required snapshot as SUCCESS **only** if result.status and
source_status are AVAILABLE. A successfully returned SOURCE_UNAVAILABLE/NO_DATA
string is not usable evidence. Source absence, invocation omission, report
completion and model-issued verify calls remain separate observations. This
adapter never calls verification or synthesizes a successful assessment.

## Advertised exact query catalog

The caller supplies an explicit ISO analysis date. The example date above is
only a command example, not an assertion about current source freshness.
All captured arguments include native injected symbol/ticker and trade_date.
Replay requires those full arguments after native graph-state injection. C can
advertise the corresponding non-injected arguments without changing native schemas.

| Order | Tool | Captured arguments in addition to injected date/instrument |
| --- | --- | --- |
| 1 | get_stock_data | start_date=as_of minus 60 calendar days, end_date=as_of (inclusive native formatter) |
| 2 | get_indicators, three separate queries | indicator=rsi, macd, close_200_sma; curr_date=as_of; look_back_days=10 |
| 3 | get_verified_market_snapshot | curr_date=as_of; look_back_days=10 recent rows |
| 4 optional | get_global_news | curr_date=as_of; look_back_days=7; limit=5 |
| 4 optional | get_news | ticker=ETH-USD; start_date=as_of minus 7 days; end_date=as_of |

Native argument defaults are not silently rewritten. Different dates, omitted
injected fields, different limits/indicators, comma-combined indicators, symbol
aliases and narrower/wider windows are unsupported queries. They return explicit
UNAVAILABLE_ARGUMENTS with an honest DATA_UNAVAILABLE sentinel and no wrong-query
source refs. There are **no covered transformations** in this candidate. C/root
must advertise the actual query catalog so the model need not guess cached dates.

Capture order follows stock -> indicators -> snapshot -> news. The adapter does
not silently enforce or invent model tool calls; C records the actual model order
and model-generated CLI verification after actual report boundaries. Both arms
must use the same approved manifest SHA256. Replayed evidence remains captured
at its original times; a second tool call is not a continuously live refresh.

## Manifest and limits

Candidate format `correction-source-capture-0.1`: capture ID/start/end UTC times,
analysis date/Asia-Calcutta basis, exact plan, immutable query-keyed entries,
native schema/description snapshots, upstream/source implementation bindings,
per-entry status/native text file/hash, exact query args, bar/news/indicator
coverage and precision, HTTP retrieval/provenance records and redacted body files.
`plan_sha256` and `schemas_sha256` bind the acquisition catalog and native tool
schemas. Loading rejects duplicate/missing entries, malformed/escaping artifact
paths, changed content/status/coverage, clock mismatches and changed implementation.
Read metadata is detached; loaded replay text is the previously verified immutable
byte snapshot. Reopening after disk mutation fails, rather than gaining new evidence.
Root validates the manifest byte hash before giving the same reference to both
arms. Content hashes establish byte identity, not source authority or truth.

The native v0.7.1 pin is c4544913a14ed3df5f1ed7b9e8483270ce20682a.
Existing `live_experiment.sources.live_tools` and `source_http.HttpCapture`
guard are reused unchanged. Only Yahoo read-only routes are enabled for this
capture; macro/FRED/Polymarket/model/provider fallbacks are not exposed.

Stock model text is 30..90 calendar days (60 default); native indicators use
fresh longer OHLCV history (the native loader retrieves five years). Native
stockstats may forward/back-fill price gaps; that policy remains explicit.
Snapshot uses fill_gaps=False. Native strings, numbers and defects are preserved,
not repaired. Current daily bars may be partial; source timezone/bar timestamps
and retrieval clocks are distinct from the analysis date. Snapshot is a native
function name, not independent certification of final prices.
Fresh cache CSVs are copied to bars/ with exact hashes. `fresh_bar_coverage`
records their actual row/date ranges, gaps and finite-close counts on/before as_of;
invalid/missing dates are excluded from the count, duplicate dates count once,
and future-only rows do not establish warmup history. Invalid, duplicate and
future row counts remain explicit, and completeness remains UNKNOWN.
`indicator_history_ready` explicitly states whether at least 200 distinct valid dated close rows
were retained. It is false without such an artifact and does not certify any
indicator method or source truth. The model receives the short native reports,
not the full five-year CSV. Root must review core_ready, indicator_history_ready
and every per-query status before considering the shared source set ready.

Proposed bounds: 7 tool queries, 24 HTTP requests, 8-second request timeout,
2 MB per HTTP body, 16 MB retained artifacts, 64 KB native string retention,
16 KB maximum model-visible native return, 90-second capture process deadline.
No silent truncation: oversized/unavailable strings have explicit status and
unavailable exposure. Raw HTTP is retained separately after named-field secret
redaction; handshake crumb/cookie bodies and headers are not persisted. Secret-
bearing native text is refused instead of silently rewritten. Capture uses a
new process/cache directory; no historical cache or cookie database is reused.
After the child exits, the parent deletes only its verified new private-cache
subdirectory, retaining copied CSV/body/text artifacts. Raw cookie databases are
never copied into the common bundle. Partial failed/timeout capture directories
remain explicit and have no valid complete manifest. No output is overwritten.

## Work sequence and verification boundary

Now: 19 offline tests pass in the cached native environment. Base Python runs
18 and explicitly skips the one optional native-schema test; that skip is not
native integration PASS. No provider HTTP or model request was performed. Authored
HTTP controls exercise the reused requests and curl guard, redirects/body limits,
exact nonsecret bytes, body redaction and handshake omission. Standard controls
exercise exact/missing/wrong arguments, unavailable snapshot strings, metadata,
schema/plan/content mutation, native errors/oversize/NA data, private output
refusal, fresh-output/deadline behavior and data-only socket/process denial.
The optional native test preserves actual pinned schemas/descriptions and proves
the wrapped tool returns authored text without executing its native source body.

Next: root independently reviews this immutable candidate. Later: root performs
one data-only capture; C binds the accepted common manifest
to its real report -> model-issued CLI verification -> correction -> recheck loop.
No paid smoke, model call, budget/key access, trade, signing, live-source fetch,
shared schema edit or SDK/MCP expansion is authorized to lane B.

## Commands and dependency boundaries

Default/offline (Python 3.11 standard library; no cache/key/budget access):

```powershell
py -3.11 -S -B tools/correction_sources.py --as-of 2026-11-05
py -3.11 -S -B -m unittest tests.test_correction_sources -v
```

Optional native-schema test requires the existing cached native Python environment
with requirements.lock.txt dependencies (including langchain-core/langgraph,
yfinance, stockstats, requests and curl_cffi) and the unchanged pinned checkout:

```powershell
$env:CORRECTION_SOURCES_TEST_UPSTREAM='<reviewed-path>/upstream/TradingAgents'
<native-python> -B -m unittest tests.test_correction_sources -v
```

No dependencies are installed by this module. Missing native dependencies remain
an explicit unavailable capture or optional test skip, not a substitute data path.
Do not use live_experiment.preflight: its historical budget-review behavior is
outside this source-only module. The new module neither imports nor constructs
Budget, nor opens a key or budget artifact.

**ROOT ONLY after independent review; performs fresh Yahoo data reads, no models:**

```powershell
<native-python> -B tools/correction_sources.py --mode capture --as-of 2026-11-05 --stock-days 60 --upstream '<reviewed-path>/upstream/TradingAgents' --output '<existing-parent>/<new-source-dir>'
```

The output parent must exist and the child directory must not. The parent
launches one shell-free child with the 90-second hard process timeout; the child
checks pin/origin/tracked integrity before installing its strict Yahoo-only
socket/process and existing HTTP/CFFI guards. Every redirect is checked. Python
model/FRED/Polymarket DNS, local sockets and child processes are denied; no model
client is constructed. The internal _worker mode is not a standalone capture API.

Capture returns manifest_path, manifest_sha256, status and core_ready. Inspect
without fetching, then share that **same** manifest/hash with both model arms:

```powershell
py -3.11 -S -B tools/correction_sources.py --mode inspect --manifest '<capture>/manifest.json' --expected-sha256 '<returned-manifest-sha256>'
```

Native availability and exact warmup history are **unverified until root's actual
capture**. Source/provider outages stay real gaps; there is no fallback to
invented prices/news, a historical corpus, an unrelated paid route or a fixture.
