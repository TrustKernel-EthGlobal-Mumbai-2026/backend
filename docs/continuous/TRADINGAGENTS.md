# TradingAgents persisted feedback adapter

Lane C, 5 November 2026. **Persisted offline milestone tested; ready for review.**
Actual local B service is integrated; no paid model/provider execution, live policy,
full semantic-ledger readiness or actual-model corrective behavior is claimed.

| Accepted dependency | Provenance | Import treatment |
|---|---|---|
| A0.2 contracts/verifier | source e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2, integration 29f038f | Exact 8 files, unchanged; dependency commit 07e0a81 |
| B stored-reference service | 251b3b02c63e860020f94ce0b2962472eb0979fe | Exact capture/journal/projection/service, 2 tests and CAPTURE.md; dependency commit 91d39ba |
| C ambiguity repair | 9478a61dd8a84009bd53829c19399568c030382c | Orchestrator accepted scoped capture semantics after 13 generic tests and duplicate-return control; that audit did not exercise native tests |

Imported A/B documentation retains its source-time status wording; the above
orchestrator acceptance is the authority for this scoped offline integration.
No A/B-owned implementation was independently edited or merged by C.

## Pinned seams

Inspected the clean upstream v0.7.1 checkout at commit
`c4544913a14ed3df5f1ed7b9e8483270ce20682a` (read only).

- `tradingagents/agents/analysts/market_analyst.py:create_market_analyst`
  constructs a system prompt and calls `take_turn` with module-level `TOOLS`.
  Updating only the graph spec does not expose a new tool to the model.
- `agents/analysts/turn.py:take_turn` uses `llm.bind_tools(tools)` and returns an
  empty report during tool calls. On `WRAP_UP`, `_as_text` converts earlier calls
  and ToolMessages into text, and invokes an unbound model.
- `graph/setup.py:_analyst_graph` routes `agent -> tools -> agent/wrap_up` using
  actual `ToolNode`; every tool-bearing AI message consumes a round, including a
  newly added verification tool. Merely extending its tuple steals source rounds.
- The same function's output schema retains only the report. Parent `GraphSetup`
  joins analyst reports before research debate. Feedback injected after that join
  is not evidence the original analyst received it.
- Existing `trustkernel/runner.py` and `live_experiment/arm.py` construct
  `GraphSetup` directly, compile, then invoke with callbacks, recursion 50 and
  concurrency one. They avoid `TradingAgentsGraph`, memory and settlement.
  Those launchers remain unchanged; neither implements feedback or durable resume.
- Default `compile()` has no checkpointer. Continuing an analyst after a tool
  return is ordinary graph execution, not process-restart resume. Persistent
  resume needs an explicit checkpointer and is not claimed here.

## Implemented service binding

`FeedbackBoundary` uses accepted A requests/results and exact
`assessment_binding`/`binding_matches` over the request, paper proposal, checkpoint,
policy and ordered event view. A's paper proposal content/revision is distinct
from `report_event_id` + `report_id` + `report_revision`. New report references
require new proposal revisions. The optional report predicate requires the exact
retained report event identity and bytes and an explicit at-use authorizer.
Default authorization is disabled; report findings never clear decision truth.

`StoredFeedbackHost` now connects that controller to actual B persistence:

- `make_host_ingest` validates B's actual receipt run/batch/request digest, event
  ID, positive receipt position, ACCEPTED/DUPLICATE status and stream state.
  Stable content-bound batch IDs permit exact retry. Failed receipt validation
  does not advance the local capture sequence. A real commit followed by a
  corrupted reply is tested: exact retry recovers with one stored event.
- `submit_report` verifies the report equals B's retained event, establishes an
  explicit full registered-stream checkpoint vector, constructs the A request
  with independent report/proposal identities, then calls **B.resolve_view**.
  The exact immutable checkpoint/events/policy view is used for local binding
  checks. There is no latest-list reconstruction or service-owned state invention.
- `make_stored_assessor` forwards only `execute("verify", A_request)`; B resolves
  stored references and retains the exact result. No event view, policy body,
  principal or coverage assertion is supplied by model tool arguments.
- Actual observed verification returns create typed `feedback_delivery` events.
  Exact native ToolMessage references in an assembled input create separate
  `feedback_inclusion` events tied to delivery and input IDs. Explicit authored
  acknowledgement and observed newer report revisions create their own A events,
  bound to the original retained assessment/proposal revision. Reusing the old
  report as a correction is rejected. None means the finding was repaired.
- Local controller observations, including requested verification, separate
  allowance counters and terminal abstention, are retained as A `observation`
  records. Actual policy evaluation remains A/B-owned. Failed attempts spend
  allowance; source refresh invalidates the current view before executing.

The host caller authenticates B, configures every registered stream, installs
policy and supplies collector-only coverage with actual retained basis IDs. C
never promotes native inventory into coverage or lets the model configure it.
Per-event ingest is synchronous through B's durable receipt before capture
continues; this is not a durable host outbox or process-restart scheduler.

`LocalServiceWorker` owns creation, calls and closure of B's backend on one host
thread. Native LangGraph ToolNode dispatch uses worker threads, while B's SQLite
connection is bound to its creating thread. This in-process facade serializes
calls without changing B or disabling SQLite checks. It is not a standalone
server/transport. The tested host graph runs at max_concurrency=1; concurrent
proposal/controller mutation is outside this single-writer adapter's contract.

## Explicit capture and ambiguity

`HostEventCapture` emits validated A events, with privacy filtering before hashing:
actual tool returns, full retained visible-message envelopes at input assembly,
exact report outputs and separate feedback/correction observations. Null clocks
remain unknown. Phase/completion and source success require explicit host evidence;
nonempty output and ToolNode success do not imply COMPLETE/provider availability.

Only intact host-observed ToolMessages with matching call ID, tool name and
retained body establish call-specific input links. Flattened human marker text
establishes **no** call origin, even for a unique body/name match. Ambiguous,
unrecognized and unsupported representations preserve exact retained input but
encode boundary UNKNOWN and withhold uncertain links. A's required-snapshot check
then remains INCONCLUSIVE instead of false missing-tool FAIL/PASS. Proven intact
refs may remain in partial histories. No arbitrary candidate is chosen.

Native capped wrap-up therefore retains raw finding text and delivery but records
no call-specific feedback inclusion. Exact flattened linkage would require
explicit host-observed transformation lineage from pre-flattened occurrences and
output positions; it is not implemented. Historical native logs without an actual
assembly observation stay UNKNOWN. No hidden reasoning or provider acceptance
is inferred from an attempted request.

## What actually ran offline

All inputs and responses are newly authored, using temporary SQLite stores and
explicit trusted test-host grants/coverage. No private recording/profile was read.

| Path | Real components | Authored components | Observed result |
|---|---|---|---|
| Host driver loop | Accepted B journal/receipts/checkpoints/resolve_view/verify/read/reopen; A core | Initial report, source callback, next input, acknowledgement, revision and completion | Original [FAIL,PASS] retained; new report/proposal + checkpoint yields scoped [PASS,PASS]; terminal paper abstention |
| Pinned normal subgraph | Exact AST-loaded market analyst factory, _analyst_graph, take_turn, ToolNode, trusted model wrapper; real B on service worker | Deterministic Runnable, authored snapshot tool, stop metadata and trusted host checkpoint driver | Tool-dispatched finding delivered and included; source round; new report/input/proposal; host recheck [PASS,PASS] |
| Pinned capped wrap-up | Same exact pinned functions and persisted B | Deterministic authored abstaining response after cap | Finding text retained; linkage UNKNOWN; no feedback_inclusion; new report recheck [INCONCLUSIVE,PASS], RECHECK |
| Unready persisted prefix | Actual B projection lag and retained assessment | Explicit stop/abstention by test host | NOT_READY/INCONCLUSIVE remains unchanged after projection catches up; new checkpoint would be required |

Initial report revision0 is captured without the required snapshot and assessed
at checkpoint0. The original failed result is stored before any feedback or
refresh. In the normal path, a separately budgeted source callback returns the
unchanged authored defect `Close=99 Low=100`; it does not invent a corrected
price. The next actual input includes that return by call identity. Report1's
completion uses explicitly authored `finish_reason=stop` metadata; this is not a
claim about a real provider's completion signal. Proposal1 independently references
report1. A new immutable checkpoint/view is established and rechecked. The normal
procedure passes only required-tool delivery and report completion; OHLC validity,
price authority, suitability and dependency sufficiency remain unresolved. The
paper outcome explicitly abstains.

The native tests use **exact pinned AST functions**, checked against their git
blobs in an isolated namespace with authored tool tuples and static context. They
do not mutate or import the full upstream package or run complete GraphSetup,
debate, memory or settlement. The host driver captures initial reports, establishes
checkpoints/proposals/coverage and performs the final recheck outside the analyst
subgraph. Scripted responses are not evidence of actual agent behavior. The
original graph's round cap remains shared; separate host source/verify/remediation
allowances are exercised by the actual native callbacks (normal: 1/2/1; capped:
0/2/1) without claiming a replacement global graph scheduler.

The host loop closes/reopens B and retrieves byte-identical original/rechecked
assessments, plus the frozen old prefix excluding later events. This proves
persistence/read recovery, not durable graph/host-process continuation. Convenience
acknowledgement remains UNSUPPORTED_OPERATION; explicit lifecycle observations
are ingested through the assigned collector. get_run_state retains
`atomic_semantic_ready=false` and `native_trace_mapping=NOT_IMPLEMENTED`.

## Verification and continuation

| Check | Latest evidence |
|---|---|
| C stdlib generic + real persisted-host cases | 17 PASS |
| C pinned native plumbing/negative controls + 2 persisted subgraph paths | 5 PASS |
| Combined A29 + B49 + C22 in cached native environment | 100 PASS |
| Combined stdlib without native pin/deps | 95 PASS; native class explicitly SKIP |
| Actual duplicate receipt/exact retry, invalid receipt after commit | No duplicate logical event or local sequence advancement on invalid reply |
| Changed report/proposal/policy/prefix, ambiguous identical returns | Bound rejection or honest INCONCLUSIVE; original finding retained |
| Metadata/index/export | Regenerated and checked before publication |

Commands: `python -S -B -m unittest discover -s tests -p "test_continuous*.py"`.
Native: set `TRUSTKERNEL_TRADINGAGENTS_UPSTREAM` to the reviewed exact pin, use the
cached Python3.11 environment and omit `-S`. Cached versions: LangChain Core
1.7.1, LangGraph 1.2.18, Prebuilt 1.1.1. No dependency installation.

B is no longer a dependency blocker. Next: orchestrator reviews this persisted
milestone and integrates accepted owned changes/dependency imports; central
README/orchestration/CI and generated metadata conflicts remain orchestrator-owned.
Full GraphSetup/host restart continuation, semantic extraction, live policy,
actual-model smoke, frontend and independent quality evaluation remain deferred.
No model/provider call, budget/hold mutation, private rebuild, trade, signing,
on-chain operation or main merge occurred.

## Preserved review history

Early slices b079882/3b7916a used provisional local bindings; 7961d39 replaced them
with A0.2 but incorrectly credited two identical call returns from one flattened
human message. Its prior test success did not establish valid capture semantics.
The orchestrator requested changes. Repair 9478a61 removed all text-only origin
inference and was accepted for scoped capture semantics after independent code
review, 13 generic tests and the original duplicate-return control. That audit
explicitly did not run native tests; native evidence above is C's separate run.
The original failed review/commits and data defects remain preserved. Accepted
capture semantics do not grant general session completeness or decision clearance.
