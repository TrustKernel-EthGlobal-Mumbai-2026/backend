# TradingAgents feedback adapter

Lane C, 5 November 2026. Inspection complete; offline implementation in progress.
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

The adapter must not create a duplicate verifier or finalize a competing wire
schema. Until accepted contracts arrive, all backend responses are explicitly
labeled provisional test doubles. Required API details: proposal registration
and digest identity; host flush/barrier and checkpoint ID/vector; verify request
constructor and response binding/readiness/disposition; policy/issuer validation;
capture of proposal, feedback delivery and actual next-input inclusion.

Tests use newly authored inputs, never private recordings. Native tests must
report SKIP when optional dependencies or the pinned source are absent; generic
tests cannot stand in for native integration. Frontend, CLI/MCP, policy evaluation,
live TTLs and source authority remain outside this lane.
