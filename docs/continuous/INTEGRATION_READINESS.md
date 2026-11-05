# Actual-model TradingAgents integration-smoke readiness

Status: **test-readiness package prepared; PAID EXECUTION DISABLED pending NEW
explicit user approval and launch checks**. 5 November 2026.

Branch codex/tradingagents-integration-smoke is based on main
b365415f072eaf9d9b475662f56c7c7c441c6fc9 after the foundation merges. PR4 stayed
frozen at 7e53d01 and is now merged. This readiness work belongs in a new draft PR
against main; no A/B/D, original guard/instrumentation or upstream file is changed.

## Immediate milestone and exact integration scope

An actual provider model must voluntarily generate verify_proposal, actual native
dispatch must return a persisted scoped finding, a subsequent actual model request
must contain that exact return/call ID, and a later provider response must show a
visible next action/report. This actual-model milestone **has not run**. Earlier
AST-subset and authored demos do not establish it.

This runner uses normal imports from the installed pinned v0.7.1 checkout
c4544913a14ed3df5f1ed7b9e8483270ce20682a: market_analyst.create_market_analyst,
take_turn, graph.setup._analyst_graph and real LangGraph ToolNode. No AST extraction.
It also uses the imported NormalizedChatOpenAI client and its real Responses API
serialization/parser. Deterministic tests replace HTTP model I/O in-process using
httpx.MockTransport with explicitly AUTHORED responses, never an API call. Paid
mode uses that same client/runner with a restricted API-only transport.

The bounded imported analyst/subgraph is the declared test target. Full GraphSetup
adds researchers/managers/debate/structured calls and is not constructed by this
smoke; no full-graph readiness, memory, settlement or complete session coverage.
The initial report/checkpoint is an explicitly AUTHORED omission seed, not an
actual-model historical mistake. A model's later refusal/omission is an outcome.

Original safeguards reused unchanged: upstream_check (pin/origin/tracked integrity,
with optional git index locks disabled), fixture_tools (same native source schemas,
process-local frozen bodies), Trace/Observer callbacks, network_guard and future
Budget.before/settle. No dotenv discovery, source function body, provider fetch,
private corpus rebuild or source-tree write. Bytecode writes are disabled. The
child also confines file/SQLite writes to its new output; future approved paid
budget writes are a narrowly named exception. Original regex/key-field redaction
is reused without credential environment-value enumeration. Only key-name presence
is inspected in preflight; real credential values are not printed or searched.

## Startup commands (no paid call)

Use the existing cached Python3.11 environment with the native dependencies.
Set TRUSTKERNEL_TRADINGAGENTS_UPSTREAM to the reviewed upstream/TradingAgents path
and TRUSTKERNEL_BUDGET_REVIEW to the closed/read-only review JSON path. Commands
below use PowerShell environment syntax; activate the cached environment or use
its Python executable explicitly.
From the checkout run with NEW output directories:

```text
python -B tools/tradingagents_integration.py --output .local-runs/model-preflight-001 --budget-review "$env:TRUSTKERNEL_BUDGET_REVIEW"
python -B tools/tradingagents_integration.py --mode scripted --output .local-runs/model-ready-scripted-001 --budget-review "$env:TRUSTKERNEL_BUDGET_REVIEW"
```

Alternatively pass --upstream explicitly. The budget-review argument is an operator
review JSON artifact only, not the ledger; TRUSTKERNEL_BUDGET_REVIEW can supply its
path. No real budget database is opened in preflight/scripted mode. Without that
artifact, native plumbing may be ready but the package reports the review gate.
 There is no source-path/credential search
or dependency installation. Default mode is preflight: imports/provenance/fixture
and a false approval template only; no model client, Budget constructor, budget
file open, reservation or provider request. Scripted mode exercises the same real
client/import/graph/ToolNode/storage path with AUTHORED in-process HTTP responses.
It makes zero provider/network/model-inference calls. READY_FOR_APPROVAL means the
package can be reviewed for a proposed launch, never permission to spend.

Negative controls use --mode scripted --scenario omit|ignore|truncated. Omission
returns a nonzero process result and records no fabricated verifier invocation.
Truncation records partial progression and report-completion FAIL, never success.
Ignore can show visible continuation while the named missing-source check remains
FAIL; neither continuation nor acknowledgement means correction. Scenario controls
are unavailable in paid mode.

## Fixed proposed smoke profile

| Boundary | Configured limit / distinction |
|---|---|
| Model | Single existing gpt-6.1-terra; medium effort; default service tier |
| API | https://api.openai.com/v1/responses only; store=false; no live sources |
| Model calls/output | 4 calls maximum; 1024 total output tokens/request; 40k-byte wire/input cap |
| Requests/wall time | No retry; 25s request timeout; parent process kills child at 120s |
| Model tool choice | auto, parallel_tool_calls=false; one call per returned AI turn; a batch is stopped, not split |
| Native tool-bearing turns | 3, shared by source and verifier as in the pinned graph; forced wrap-up can lose call identity |
| Source/verification/remediation | 1 frozen-source dispatch round, 2 verification calls (initial voluntary + host recheck), 1 proposal/report remediation |
| Money proposal | Incremental ceiling $0.65, subject to unchanged cumulative/active headroom under the existing $5 hard ceiling; not a fresh $5 |

Source schemas remain the original market tuple. Frozen wrapper bodies replace
native source functions using original fixture_tools; one source function call per
AI turn is the bounded smoke's source round. Multiple source requests or source
before the currently bound verification can exhaust/invalidate the boundary and
stop the run. These are honest outcomes, not retries to force success. No tool is
host-forced with tool_choice=required, and no AI tool-call message is seeded into
the graph. Both prompt tool list and ToolNode tuple include verify_proposal.

## What remains to be checked/approved before any paid call

- NEW explicit user approval for this one output-bound smoke, exact profile,
  implementation/fixture digests and upstream pin. Generated approval-required.json
  has approved=false, no approval ID/expiry/output and incomplete confirmations.
  It cannot launch anything as generated. An operator artifact is a local execution
  guard; it is not proof of human authorization without the separate user approval.
- Credential-name presence and an acknowledgement that account/model availability
  is unprobed. The first separately approved bounded request may fail; no impossible
  positive account-access confirmation is required in advance. Preflight does not
  use subscription access as an API credential, inspect key values or probe access.
- Current pricing review: original upper_charge uses historical conservative
  reservations (Terra maximum 60k input/2048 output envelope; $0.16024 per
  request, four totaling $0.64096 under the proposed $0.65 incremental cap).
  Operator must confirm those legacy upper rates remain conservative
  before launch. No current invoice/price/account entitlement is inferred here.
- Existing operational-root budget_policy.json and runs/approved-budget.sqlite.
  This task does not open or mutate those real files. Future approved paid mode
  reads them read-only, requires the existing $5 hard identity/initial policy,
  active headroom for all remaining requests, and the unchanged **known original
  historical hold**. The reviewed closed ledger includes that $0.16024 hold in its
  reserved total; it must not be cleared or reconciled. The review fingerprint
  anchors the exact closed database before launch. The future read gate pins all
  historical row tuples, including the hold's actual identity/value/status, and
  preserves the existing carry balance rather than recomputing it from charges.
  Changed/removed/settled historical holds, modified historical rows/policy,
  unexpected new requests/unknowns, or a concurrent balance change refuse progress.
  Only this smoke's tracked reservations and settlements may add to the baseline.
  No replacement ledger, ceiling increase or fresh allowance is created.
- Only after those gates may original Budget be constructed and reserve/settle via
  the original callback Observer. The same read-only headroom/hold gate is checked
  before and after reservation, at the HTTP boundary, and after settlement.
  Original max_calls/deadline/STOP/input-envelope bounds
  remain active. Unknown usage/error/timeout reservations remain held. No automatic
  reservation release, budget reconciliation or retry is implemented.

The orchestrator's closed/read-only review reports reserved including historical
carry/hold $4.128377500000004, active/hard $5/$5, remaining about $0.8716225. Four
Terra reservations fit without releasing anything; four Sol reservations ($1.28192)
did not and that prototype is superseded. These are reviewed project-guard figures,
not a fresh allowance/current invoice or permission to launch. The original hold
remains reserved. A concurrent change after review invalidates the baseline; there
is no automatic rebaselining. The operator must coordinate a single launch; checks
can detect a racing writer and leave this run's new hold reserved on refusal.

No real budget files were read by this readiness task. Budget-gate tests use only
new authored temporary SQLite/policy files and prove read-only byte preservation.

## Future launch command — NOT AUTHORIZED NOW

After separate NEW user approval and the above operator checks, an operator must
prepare approval.json from the false template, preserving exact digests, recording
required pricing/hold-preservation confirmations, model_account_access=
'UNPROBED_CALL_MAY_FAIL_AND_RETAIN_HOLD', a unique approval_id, expiry within one hour and
launch_output='.local-runs/model-smoke-approved-001'. Only that new output can use
it; the new-output guard prevents reuse. Do not auto-create an approved artifact.

```text
python -B tools/tradingagents_integration.py --mode paid --output .local-runs/model-smoke-approved-001 --fixture .local-runs/model-ready-scripted-001/fixture.json --approval .local-runs/model-ready-scripted-001/approval.json --budget-review "$env:TRUSTKERNEL_BUDGET_REVIEW"
```

This command is a proposed future operator action; it has not been run. A paid
flag alone is rejected before any child/budget/model work. The profile/source/
fixture bindings or expiry changing requires a new review/approval. A failed
attempt does not permit automatic rerun: use a newly approved unused output and
preserve the known historical hold and separately review any new unknown hold first. No wider30min experiment is prepared.

## View / stop / proof and failure criteria

Read readiness.json and VIEW.md. Preflight stores import provenance (real module
paths/hashes), fixture.json, implementation/profile digests and approval-required.json.
Scripted/paid execution additionally retains runtime-trace/trace.jsonl and its
rebuildable SQLite through original redacted callbacks, plus feedback.sqlite via
accepted B. Open databases READ ONLY. Relevant B tables: cv_events, cv_objects
kind=assessment and cv_batches. No historical viewer/launch command is needed.

Trace join: model/SDK response with tool-call ID -> tool.start/tool.end -> typed
feedback_delivery -> exact ToolMessage input capture -> Responses function_call_output
with the same call ID/body in smoke.wire_request -> later smoke.model_output.
smoke.tools_offered retains trusted definitions and discretionary auto choice.
In scripted mode every wire/response origin is AUTHORED_HTTP_OVERRIDE and
provider_generated_verify=false. Only a separately approved real API response
can set that provider-origin proof. Inspect per-stage flags; process success alone
is not model correction or a positive scoped assessment.

Omitted/invalid call, absent delivery, no exact next request, no visible next
response, tool/input/output/call/time limits, unready capture, source error or
ambiguous wrap-up are retained outcomes. Wrap-up human text establishes no exact
call-specific provenance; it remains UNKNOWN. Report phase is captured at the
native report return; completion is COMPLETE only with observed completed/stop
metadata, TRUNCATED for output limits, otherwise UNKNOWN. The later host recheck
is separate from the voluntary initial call. Source price validity and full
semantic readiness remain unresolved even when procedural checks PASS.

Use Ctrl+C on the foreground supervisor to stop; it kills the child and writes
OPERATOR_STOP_NOT_PASS. The 120s hard timeout writes WALL_TIMEOUT_NOT_PASS.
Neither clears budget holds. Consult supervisor-stop.json or failure.json and the
partial trace. No failure path is reclassified as a successful experiment.

## Tests and independent-review handoff

```text
python -S -B -m unittest discover -s tests -p test_tradingagents_integration.py -v
python -B -m unittest discover -s tests -p test_tradingagents_integration.py -v
```

The stdlib suite has 5 controls; actual-import tests explicitly SKIP if pinned
source/framework dependencies are unavailable. Cached native execution has 8 tests,
including default no-paid imports, real NormalizedChatOpenAI HTTP serialization/
parsing and ToolNode feedback continuation, and omitted/ignored/truncated cases.
No optional integration is counted as PASS when missing. Source/approval expiry/
one-output bindings, paid-flag denial, read-only authored budget checks (known hold preserved; changed identity/value/state, new
unknown, insufficient headroom and concurrent balance rejected) and parent
wall/operator stops are separate controls. A/B/D and original runtime bytes stay
unchanged. Shared CI/README/orchestration updates remain orchestrator-owned.

Official documentation for discretionary tool choice and call/result sequencing:
[OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling).
The [selected-model page](https://developers.openai.com/api/docs/models/gpt-6.1-terra)
does not establish this account's access, key validity or approved budget.

Retained current candidate evidence: `.local-runs/terra-preflight-001` and
`.local-runs/terra-ready-001`. These consume only the supplied review JSON metadata,
not the real ledger. The deterministic artifact reports READY_FOR_APPROVAL with
execution_enabled=false, provider_generated_verify=false, exact feedback IDs in
requests 2/3 and visible next action. The old four-Sol-call prototype is superseded.

```powershell
Get-Content .local-runs/terra-ready-001/readiness.json
Get-Content .local-runs/terra-ready-001/VIEW.md
Get-Content .local-runs/terra-ready-001/runtime-trace/trace.jsonl
```
