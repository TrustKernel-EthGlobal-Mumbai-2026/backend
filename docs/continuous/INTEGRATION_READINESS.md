# Actual-model TradingAgents smoke readiness

Status: IN PROGRESS, NO PAID EXECUTION, 5 November 2026.
PR4 is frozen at 7e53d01930b9a7468b8404036ff0a99d5550c044 for orchestrator merges.
This slice lives on codex/tradingagents-integration-smoke; reconcile with main
after merge confirmation before opening a separate draft PR. A/B/D bytes stay fixed.

Immediate target: a provider-generated voluntary verify_proposal call in real
TradingAgents dispatch, result delivery, exact next runtime input containing it,
and a visible next action/revision/abstention. Earlier authored demos and AST
subsets are mechanism evidence, not that actual-model outcome.

## Inspected gap and selected seam

Actual cached imports of tradingagents.agents.analysts.market_analyst and
tradingagents.graph.setup succeeded at the exact pinned v0.7.1 commit
c4544913a14ed3df5f1ed7b9e8483270ce20682a with network/subprocess blocked.
The package __init__ normally discovers .env files. This harness disables that
discovery process-locally; no credential file is read. It will use real imported
market factory, take_turn, _analyst_graph and ToolNode, not AST extraction.
Full GraphSetup is outside this bounded one-analyst smoke: it adds debate,
structured manager calls and a larger inference scope. No full-graph readiness.

Reuse original pin/origin guard, fixture_tools, Trace/Observer and network/Budget
guards; C StoredFeedbackHost supplies actual persisted checkpoints/results.
Native source schemas are replaced process-locally with explicitly authored
frozen returns; original source bodies never run. The verification definition is
added to both offered tools and dispatch tuple. Provider tool_choice remains
auto; no host-inserted AI tool calls can satisfy the paid success criteria.

## Planned boundaries / unresolved launch gates

Default preflight: no model/provider call, no Budget construction, no budget-file
open/reservation/reconciliation, credential environment-name presence only.
Original Budget.__init__ writes SQLite schema/rows, so it cannot be used as a
read-only preflight. The existing cumulative $5 is not a fresh allowance.
Current ledger/headroom, unknown holds, active ceiling, credentials and account
model access remain unchecked; no chat subscription implies API access.

Proposed single model: existing gpt-6.1-sol configuration, medium effort, default
tier, four calls, 1024 output tokens/request, no retry, 25-second request timeout,
120-second parent-enforced wall cap, 40k-byte input cap. Source rounds=1,
verify calls=2 and report/proposal remediation=1 are distinct allowances. Original
graph tool cap counts all tool-bearing turns; wrap-up provenance remains UNKNOWN.
Proposed incremental ceiling $1.30 must fit unchanged cumulative/active headroom;
original conservative reservation/pricing must be reviewed before approval.

Future paid mode must require NEW explicit approval tied to profile/source/fixture
digests, read-only cumulative-budget validation with no unknown holds, existing
policy/path binding, credential presence and a current model/pricing review. Only
after those gates may original Budget/Observer reserve/settle a paid request.
No approval is generated or execution launched by this readiness task.

Machine-readable proofs will distinguish deterministic plumbing from actual
provider tool generation, dispatch, result, exact next-input inclusion and next
action. Omitted call, failure, output cap, unknown completion, ambiguous wrap-up,
deadline or exhausted allowance is a retained outcome, not fabricated PASS.

Official OpenAI documentation supports discretionary auto tool choice and the
multi-step call/result conversation; it does not prove account model access:
[function calling](https://developers.openai.com/api/docs/guides/function-calling),
[selected model](https://developers.openai.com/api/docs/models/gpt-6.1-sol).
Implementation and opt-in launch/view commands will be completed on this branch.
