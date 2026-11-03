# Live-source session review

3 November 2026. Callable API: `from live_experiment.review import analyze_session`; `analyze_session(session_path) -> dict`. This is standard-library local analysis and does not call model/data services, import an arm/client, inspect credentials, change a budget, send corrective feedback or rank models.

## Scope and writes

The input is the parent's new live session directory. experiment.json must explicitly name a recognized live mode (`live_native` or the routed `paid_live_native_sources`/`live_native_market_sources`). Fixture files/hashes and old unmarked session modes are refused before output writes. Direct child runs are discovered by trace.jsonl; source caches or unrelated subdirectories are not treated as runs.

Only new session analysis.json, analysis.md and review_packets.json are atomically updated, using private temporary names. Trace/index/manifest/final-state inputs are read-only. Historical packages and analyses are never rebuilt. The cumulative budget database is opened with SQLite `mode=ro`, `query_only=ON` and a consistent read transaction. Missing databases remain missing. Parent owns launch, scheduler, STOP/deadline enforcement and paid requests.

## Result contract

The result retains viewer-compatible runs/pairs and exposes schema_version, updated_at, session, input_kind, source_mode, experiment_status, budget and known session charge/hold/unknown-usage subtotals. It has no aggregate quality or intelligence score and no standard-price estimate based on hardcoded rates.

Each run contains run/model/arm/pair and UTC trade/context metadata; status/manifest/closed state; trace_integrity; started/completed/error/pending call counts and latency; usage and charges; source observations and HTTP records; required-snapshot protocol; paper rating if observed; raw file paths and read/coverage limitations. Review packets retain full report text, file/JSON pointer, saved text hash and exact raw-generation origins when provable. Structured report rendering is left unresolved rather than silently assigning an origin. All report semantics/claims remain provisional.

## Trace and index integrity

Raw event hashes are recomputed with the preserved Trace.digest representation (sorted JSON keys, ensure_ascii=False, original default separators). Sequence, run identity and previous_hash must match. Only verified complete lines enter analysis. A trailing unfinished line is excluded from the active snapshot and marked explicitly.

The read-only SQLite snapshot is compared on its shared prefix with JSONL across every stored event column and decoded payload. Active writer lag/ahead is allowed only when the complete common prefix is identical, with row counts and direction recorded. A mismatch inside that prefix is ERROR. Zero committed index rows with nonempty raw data is INCONCLUSIVE. Active integrity PASS is explicitly scoped to the named recorded common prefix; it is not final whole-file parity.

After run_manifest has terminal status and ended_at, exact counts and full parity are required. A truncated tail, count mismatch, hashchain defect or index mismatch is ERROR. Using finalized manifest closure avoids a false failure in the short interval between raw run.end append and its SQLite commit. A temporarily incomplete manifest is recorded as unreadable/pending rather than invented.

## Source evidence and exposure

The actual routed evidence.retrieved payload is consumed: tool/request/provider, exact native result, UTF-8 hash, statuses, requested/retrieved times, source URLs, HTTP IDs/provider time fields, cache observations/files. Source.tool.error and source.http.start/end/error remain visible, including pending source calls. URL credentials/crumb/token query fields are independently redacted in derived URLs; no environment/credential values are read by the analyzer.

AVAILABLE, SOURCE_UNAVAILABLE, MISSING_CREDENTIAL, NO_DATA, WITHHELD, ERROR and UNKNOWN are distinct. An absent timestamp remains UNKNOWN. Provider-declared time fields are retained without claiming they identify a final daily bar or a current tick. HTTP absence can reflect native cache or NO_DATA and does not prove an external request. All HTTP observations remain separately visible, including source failures without a completed tool result.

Saved content hash is independently computed from persisted text. The original recorded source hash is also retained: persistence redaction can change saved text, so a disagreement is exposed without confusing it with a failed event hashchain. Source timestamps, content/cache and HTTP status are observational metadata, not publisher-authenticity or market-truth guarantees.

Exact full saved source strings are matched only in subsequent recorded llm.start input messages. Exposure records name actual input event/call/actor, message role and code-point half-open span. A content match establishes recorded presence; it does not prove attention, causal reliance, trusted tool lineage or complete semantic consumption. Partial/paraphrased/truncated handoffs remain unmeasured.

Matched cross-arm requests are compared using tool/provider/arguments and saved content hashes/status/time. Differing content is reported. `identical_available_fixture` and `consumed_evidence_equal` are null: no frozen/identical source control is claimed. A separate available-result agreement field is unknown for errors, missing credentials, withheld or no-data results; matching error text is not corroborating data. Missing arms/incomplete pairs are explicit.

## Calls and cost accounting

Usage is collected only from completed response records, never from prior outputs copied into new prompts. Provider response IDs deduplicate aliases; when missing, the fallback is explicitly the call span. A matching budget settlement response ID can recover usage with that provenance. Completed calls without usage, pending spans and errored spans remain separate; absent token counts are null, not zero. Reported output-token totals include whatever provider usage reports, without claiming access to hidden reasoning text.

Trace budget.reserved/settled/usage_unknown events identify observed session request reservations, conservative upper charges and retained holds. Only recorded charged_upper_usd is used; no inferred invoice or newly assumed pricing. Unknown reservation/settlement values are accounting issues. Known subtotals are labeled as such; pending reservations are not released.

The read-only cumulative database snapshot separately shows committed upper charges plus holds, initial/active/hard ceiling, request statuses and earlier pending/unknown reservations. Session matching uses trace request IDs only; requests not yet present in a concurrent trace cannot be silently assigned to it. Database and trace snapshots may momentarily differ. No reconciliation, settlement, reset, credit or allowance extension is performed by review.

## Required snapshot protocol

The market report must link to its actual model output/input attempt. During progress, an exact Market Analyst wrap-up output can supply that origin; final saved report equality is preferred when available. The before-report obligation is taken from the actual recorded prompt, not the mere presence of a tool name/schema. Its bounded verified prefix is examined for Market Analyst snapshot invocation before the report.

Run-wide fallback wording/log records are also retained separately from the market-report prefix. A later Research Manager fallback or model error therefore does not masquerade as a missing market tool. The wording is an observable log fact, not proof of a particular unrecorded control-flow cause.

An observed invocation is PASS for that protocol even if its source result failed or was unavailable; result statuses are shown separately. A captured obligation, complete source prefix and missing invocation produce FAIL. Missing/ambiguous report origin, obligation or actor scope remain INCONCLUSIVE. Spent-tool-round acknowledgement, configured round limit and actual fallback log messages are context, not automatic excuses, added failures or causal/model-quality claims. No invocation is forced and no finding is fed back to agents.

## Offline checks and commands

```powershell
# Desktop TrustKernel; local doubles only, no paid/provider calls
.\.venv\Scripts\python.exe -B -X utf8 -m unittest live_experiment.tests.test_review -v
# Parent-created explicitly live session only
.\.venv\Scripts\python.exe -B -X utf8 -m live_experiment.review --session <new-live-session-directory>
```

The review tests create disposable JSONL/SQLite/manifest/final-state and budget doubles, marked offline_test_stub. They cover live result success, provider failure versus omission, missing timestamps, WITHHELD/NO_DATA/missing credential, differing concurrent content, missing usage and retained holds, settlement recovery, active partial/lag, common-prefix corruption, closed trace failures, pending/error calls, missing budget, incomplete pair, input preservation and historical write refusal. These validate mechanism behavior, not real source availability or semantic quality. Source probes and the approved paid window belong to the responsible source/parent lanes.
