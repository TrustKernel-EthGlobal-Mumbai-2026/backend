# TradingAgents feedback adapter

Lane C, 5 November 2026. Offline milestone tested; waiting for accepted A/B APIs.
No model/provider execution or historical recording changes.

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

## Plan and dependency gate

Now: trusted instruction and native tool definition; local host state preserving
proposal revisions, opaque service checkpoints and separately counted allowances.
Authored tests cover exact pinned dispatch/next-input return and stale bindings.
Next: bind lane A's accepted request/result contract and lane B's immutable
checkpoint/verify service, then splice a named report boundary into the graph.
Later: separately approved actual-model smoke. No behavioral claim follows from
scripted responses, including a scripted correction.

## Implemented local slice

`continuous_verification/tradingagents.py` supplies:

- A trusted system-instruction wrapper and a real LangChain `verify_proposal`
  tool with no model-controlled checkpoint, policy or proposal arguments.
- Append-preserving local proposal revisions and SHA256 text bindings, an opaque
  host checkpoint callback and normalized feedback callback. These callbacks are
  provisional integration seams, not service contract definitions or a verifier.
- Separate source-round, verify-call and remediation counters. Failed attempts
  spend allowances; a refresh invalidates prior advice and its checkpoint.
- Separate finding preparation, observed ToolMessage delivery, exact next-input
  inclusion, explicit acknowledgement, revision and terminal abstention events.
  `make_trusted_model` records attempted invocation, not provider acceptance or
  attention. `observe_native_returns` must run on analyst reentry before wrap-up
  flattens its ToolMessages. No acknowledgement is inferred from inclusion.
- An optional host report-boundary predicate requiring current text, revision,
  checkpoint, policy, readiness, advice, observed input inclusion and an explicit
  at-use host authorizer. Default behavior cannot authorize release. The final
  graph report must be checked using its actual text; arbitrary model output is
  never covered by an earlier submitted proposal. This predicate has not yet
  been installed in a complete TradingAgents graph.

The native tests execute **exact AST-extracted pinned functions**, verified
against their git blobs, using real installed LangGraph `StateGraph`/`ToolNode`,
the market analyst factory, `take_turn`, `_as_text` and `AgentState`. They inject
authored tools, static context and a deterministic Runnable response double into
an isolated namespace. They neither import the full upstream package (which
loads provider/configuration modules) nor mutate it. Both ordinary ToolMessage
return and capped wrap-up text deliver the findings into the next assembled
request, with trusted instructions present. Socket connection paths are blocked
during execution. The report output remains an authored abstention.

This is subgraph plumbing evidence, not a full GraphSetup run, actual-model
correction, persistent restart/resume or source-budget enforcement in the original
subgraph. That subgraph still counts every tool-bearing turn together. Its native
fixture's source callback returns authored text directly; it does not exercise
the local host's source-round counter. Separate host accounting is tested in the
generic suite; graph splicing awaits the accepted contracts/backend.

## Verification and risk coverage

| Risk | Offline evidence |
|---|---|
| Omitted voluntary verify; ignored/unincluded feedback | No report authorization; no fabricated call |
| Stale revision, run, policy, prefix, digest, final report text | Binding controls reject use |
| Projection unready, gap, error, HOLD or RECHECK | Report predicate remains false |
| Timeout, failed refresh, exhausted allowances | Spent attempts retained; stale advice invalidated |
| Invented correction of provider defect | Authored failure retained; abstention/recheck stays separate |
| Tool tuple mismatch or capped return lost | Exact native dispatch tests with matching offered/dispatched tuples |
| Missing optional framework/source | Explicit native SKIP, never native PASS |

Portable command: `python -S -B -m unittest discover -s tests -p test_continuous_tradingagents.py -v`.
Result: **8 generic tests PASS; native class SKIP** without the optional pin/deps.

Native command: set `TRUSTKERNEL_TRADINGAGENTS_UPSTREAM` to a reviewed read-only
checkout of the exact pin, then run the same command **without `-S`** using an
environment with the cached framework dependencies. Result on the inspected
environment: **10 tests PASS (8 generic + 2 native)**, with LangChain Core 1.7.1,
LangGraph 1.2.18, LangGraph Prebuilt 1.1.1 and Python 3.11. No installation needed.
Backend results, policies and authorizers in these tests are explicit doubles;
the authored ADVISE result in a recheck is not actual backend verification.

The adapter must not create a duplicate verifier or finalize a competing wire
schema. Until accepted contracts arrive, all backend responses are explicitly
labeled provisional test doubles. Required API details: proposal registration
and digest identity; host flush/barrier and checkpoint ID/vector; verify request
constructor and response binding/readiness/disposition; policy/issuer validation;
capture of proposal, feedback delivery and actual next-input inclusion.

Orchestrator clarification: A's reviewed candidate has the shape
`verify(request, *, checkpoint, events, policy) -> dict`, but is **not accepted**
and is not called by this lane. B's stored-reference facade is also pending.
The current local `proposal_id` names a **market-report artifact/revision**.
It must map to A's `report_event_id`, its exact report text/digest, the completed
report boundary, and the actual report-input event IDs/prefix. A later Trader or
Portfolio Manager paper decision needs its own artifact/binding and scope; report
advice cannot clear that decision. No agent argument declares policy or coverage.

Local observations needing translation into accepted stored events:

- `proposal.submitted`: report ID, immutable revision, exact text and digest;
  `proposal.bound`: corresponding registered checkpoint and policy binding.
- `verification.requested`: host/voluntary origin and complete local binding;
  translate to A's report reference, never a guessed latest report.
- `feedback.prepared`, `feedback.delivered`, `feedback.input_included`: assessment,
  actual call ID, returned payload and next-input ID remain distinct observations.
- `model.input_attempted`: local input ID and ordered SHA256 fingerprints of each
  actual visible message's canonical JSON envelope, plus trusted-instruction flag.
  B's privacy-filtered capture must retain exact input events/spans and map these
  IDs to service references; a local digest is not capture completeness or proof
  of provider acceptance. No hidden reasoning is accessed.
- `feedback.acknowledged`, later report revisions and `proposal.abstained` retain
  separate actor observations. No success follows from an acknowledgement.

Next action is **stopped at this dependency gate**. The orchestrator must relay
accepted A commit/API references and B service/checkpoint references before C
implements the translation bridge and report-boundary splice. Central README,
orchestration status and CI registration need orchestrator updates; C has not
modified them. Lane-generated context/packaging metadata is regenerated for
publication; the orchestrator resolves generated conflicts during integration.

Tests use newly authored inputs, never private recordings. Native tests must
report SKIP when optional dependencies or the pinned source are absent; generic
tests cannot stand in for native integration. Frontend, CLI/MCP, policy evaluation,
live TTLs and source authority remain outside this lane.
