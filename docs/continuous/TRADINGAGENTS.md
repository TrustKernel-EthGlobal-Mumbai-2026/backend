# TradingAgents feedback adapter

Lane C, 5 November 2026. **A0.2 integrated offline; awaiting reviewed B service.**
No model/provider execution, live policy approval or historical recording change.

Accepted dependency: source `e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2`, imported
from integration `29f038f`. A's `__init__`, contracts, verifier, schemas/example,
29 tests and contract doc are copied exactly without edits. Their source doc's
candidate wording is frozen; orchestrator acceptance governs this scoped offline
integration. No merge, central README, orchestration or CI edit occurred.

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

## Accepted-contract host behavior

`FeedbackBoundary.submit(request, *, checkpoint, events, policy)` now accepts A0.2
objects. `LocalBinding` and `LocalFeedback` are removed. The host validates A's
request/result and computes `assessment_binding` over the exact request, proposal,
checkpoint, policy and ordered event view. It validates result identity and full
binding, and checks it again at report-boundary use. No duplicate verifier exists:
offline tests call A's accepted `verify` core; service operation is still pending.

A's **paper proposal** and **market report** are separate artifacts. The request's
proposal content/revision names a downstream paper decision and independently
references `report_event_id`, `report_id`, `report_revision`. C binds all of them;
changing the report reference requires a new proposal revision. The optional
`report_boundary_allowed(actual_report_event)` predicate applies only to that
referenced event identity/revision and exact retained report bytes. It cannot authorize the proposal text or establish downstream
decision truth, price validity, source authority or dependency completeness.
Default authorization remains disabled. At-use issuer/invalidation policy is a
trusted host obligation, not something a digest authenticates.

Separate source-round, verify-call and remediation counters remain. Failure
spends allowances. A source round invalidates prior advice/view; subsequent
submission needs a fresh proposal revision and checkpoint. Finding preparation,
observed return, next-input inclusion, acknowledgement, correction and abstention
remain distinct observations. Original failed assessments and provider defects
are retained; a required-tool PASS does not repair invalid OHLC data.

The native `verify_proposal` tool has no arguments. It cannot select a policy,
coverage, checkpoint or proposal revision. `make_trusted_model` adds the trusted
instruction and observes actual assembled requests, including pinned wrap-up
text. Provider acceptance, attention and hidden reasoning remain unobserved.

## Explicit capture, not reconstructed completeness

`HostEventCapture` constructs validated A events only. It accepts trusted host
IDs/redaction/ingest callbacks, filters retained content before hashing, and emits:

- `tool_result`: actual call ID/name, retained body and explicit status. Native
  ToolNode success does not imply provider availability; absent a trusted
  source-specific classifier, native successful returns stay **UNKNOWN**, and
  native execution errors are ERROR.
- `model_input`: full retained canonical visible-message envelope at the actual
  input-assembly seam, report ID/revision and exact observed tool event references
  as both `included_event_ids` and parents. `assembled_native_input` is called
  only at this seam and matches observed returns in ordinary ToolMessages or
  the exact pinned wrap-up text. A historical log missing this observation must
  use UNKNOWN; the generic builder requires an explicit boundary argument.
- `report`: exact retained report text, independent report revision, actual input
  event ID/parent and explicit completion/phase. Nonempty output or graph exit
  cannot imply COMPLETE. Native tests capture CLOSED with completion UNKNOWN.
- Separate A `feedback_delivery`, `feedback_inclusion`,
  `feedback_acknowledgement` and `correction` events via an explicit host helper.
  Related event IDs and content carry observable links; no correction is inferred.

No helper asserts CAPTURED coverage, SERVICE_ESTABLISHED, registered-stream
completeness, authentication or durability. Null clocks remain unknown. B must
persist identities, assigned-collector metadata and retry/restart state. A failed
emit requires stopping/retrying the identical event; local memory is not a spool.

The native fixtures verify an already authored/captured report revision 0, then
observe the scripted analyst's new abstaining report revision 1. That new report
has its own actual assembled input and is **not** covered by the old assessment.
Tests retain actual A tool_result/model_input/report events for both normal and
capped paths. Exact AST subsets are checked against the pin's git blobs and use
real LangGraph StateGraph/ToolNode. They do not import the full upstream package,
run GraphSetup, call a provider or demonstrate actual-model behavior.

## Prepared B seam and remaining concrete needs

Orchestrator relayed B's early API, not yet reviewed service parity:
`ServiceBackend(..., principal=Principal(...))`, trusted `configure_run`,
`install_policy`, assigned-collector `record_coverage`/`project`, and
`execute(operation, request) -> dict` with `ServiceError`.

C prepares two callbacks without importing or inventing B's implementation:

- `make_stored_assessor(backend)` forwards **only** `execute("verify", A_request)`.
  The request is unchanged and the backend resolves stored references. Local
  events, policies, principals and coverage are not sent as agent authority.
  Errors propagate; there is no local-success fallback.
- `make_host_ingest(backend, run_id=..., accept_receipt=...)` sends
  `execute("ingest_events", {run_id,batch_id,events:[A_event]})`. Content-bound
  batch IDs are stable for exact retry; cross-run events fail. An explicit receipt
  validator must accept the actual B durable receipt before capture advances.
  The authored test service double validates this forwarding shape only.

Required from B's reviewed commit/API before real service integration:

1. Exact ingest success/duplicate receipt DTO and error semantics for the receipt
   validator, including ambiguous commit-before-ack failures and restart IDs.
2. Exact checkpoint return DTO and the pinned **ordered event view/policy** used
   by `verify`. C's A `binding_matches` needs the same checkpoint/events/policy,
   not a reconstructed latest list. Early `get_evidence` returns one event and
   `list_events` pins a journal snapshot; neither yet specifies an assessment-
   checkpoint view accessor or the verifier's deterministic ordering. Provide
   that accessor/order or a reviewed equivalent authenticated at-use binding API.
3. Host principal grants and registry configuration matching producer ID,
   stream ID, `adapter_version="tradingagents-feedback-0.2"`, redaction profile,
   plus collector-only coverage observations with real basis IDs.
4. Actual model-input capture basis, report phase/completion signals and flush/
   barrier sequence. The native trace without assembly cannot be upgraded.
5. `acknowledge_feedback` is initially UNSUPPORTED. Use assigned-collector A
   observation events only after B confirms that path; no transport fallback
   may claim successful acknowledgement or correction.

A is no longer a blocker. Next: consume B's reviewed service, bind receipt/view
callbacks, then splice the named report boundary and test an isolated real-service
checkpoint/feedback/recheck path. No experiment launches while waiting.

## Verification

All tests use temporary authored in-memory packets and explicit test-service
coverage/principal doubles; no private recordings or original profiles are read.

| Check | Latest evidence |
|---|---|
| Lane C generic offline controls | 9 PASS with real accepted A core |
| Native exact pinned dispatch, normal and wrap-up | 2 PASS with authored responses |
| Combined accepted A + C, cached native environment | 40 PASS = A29 + C11 |
| Combined stdlib-only without native pin/deps | 38 PASS; native class explicit SKIP |
| Old revision/view/policy/report substitution | Rejected; report/proposal separation tested |
| Missing assembly, unknown completion/source status | Remain UNKNOWN/INCONCLUSIVE, never promoted |
| Gap, lag, cycle, timeout, failed refresh, exhaustion | No named report release |
| B operation forwarding/receipt control | Authored service double only; real B NOT RUN |

Commands: `python -S -B -m unittest discover -s tests -p "test_continuous*.py" -v`.
Native: set `TRUSTKERNEL_TRADINGAGENTS_UPSTREAM` to the reviewed exact pin, use the
cached Python3.11 environment and omit `-S`. Cached versions: LangChain Core
1.7.1, LangGraph 1.2.18, Prebuilt 1.1.1. No dependency installation.

Historical lane milestones `b079882` and `3b7916a` used explicitly provisional
local bindings/doubles. This slice replaces those bindings; their earlier native
plumbing evidence remains historical. Separate host counters do not yet replace
the original subgraph's shared round cap. Durable restart/resume, full graph
splicing, actual B parity and actual-model corrective behavior remain unproven.
Frontend and independent quality evaluation remain deferred. Orchestrator owns
central README/orchestration/CI and generated integration-conflict resolution.
