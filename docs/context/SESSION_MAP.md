# Condensed cross-session history

This reconstructs the project context from the completed workstreams and parent-reviewed handoffs. It is a curated record, not a transcript or a claim that unavailable private artifacts are publicly reproducible. Dates refer to India time; runtime artifacts also preserve original UTC clocks.

## Purpose and scope decisions

The project owner defined TrustKernel around long-running agents taking decisions from stale evidence or faulty extracts. The desired assessment is procedural integrity. Intelligence ranking, profitability scoring and an independent quality benchmark were deferred. Agent compatibility should encompass a single command and explicit multi-agent systems through common observation/finding contracts.

The original planning documents proposed product, architecture, demo and sponsor directions. They were treated as design context, not permission to trade, spend or deploy. Later user decisions and measured implementation outcomes govern current state.

## 29–30 October: instrumented baseline

The baseline pinned TauricResearch/TradingAgents v0.7.1, preserved upstream code and added a read-only observer. User-visible console, JSONL and queryable SQLite record observable steps, input/output text, tool calls/results, model/configuration, usage and errors. The user authorized a bounded 30-minute paired experiment rather than a three-hour run, with a cumulative budget limit. Private budget/account state is retained outside this repository.

All six actual model workflows used the same synthetic ETH fixture and ended with paper Hold. Sol omitted the required verified snapshot in all three; Terra requested it in all three. Both acknowledged duplicated/unverified news and missing data. One failed request retained its unknown-cost reservation. These were actual agent executions over synthetic data; calling them a real-market baseline would be incorrect.

Code: trustkernel/; fixtures/; original study launcher. Recorded session identity: `20261030-010033-30min-597a75`. Summaries: docs/research/HISTORY.md and its source index.

## 30 October–1 November: atomic extraction and rule semantics

The atomic-ledger chat first delivered selected assertions and exact source/input links. The owner challenged partial extraction, so the work expanded to all visible originating report/discussion text, surface dispositions and explicit unresolved queues. Refinement then decomposed decision rationale into local statement, reason and condition candidates.

A real cross-semicolon condition-attachment defect was found after an earlier provisional build. The corrected frozen refinement3.0.1 introduced a local branch guard and preserved the rejected release as historical evidence. Accepted reference build: `refined-v3-99d181ef7ca54fea4ff1`, canonical SHA256 `950d60f56d835d08cb01fa4bd24d93153ce48ab211bcc1b2f630b35a815a3556`. Passing structural tests did not become semantic accuracy or accepted factual support.

The rules workstream separated source/numeric consistency, actual input exposure, before-report tool compliance, duplicated-source lineage, missingness versus zero, and conditional applicability. A single composite intelligence/grounding score was not adopted. Code/contracts: verification/; explorations/rules/.

## Parallel exploration: workflows, frontend and sponsors

Evidence-workflow exploration considered source-linked case files, replay and paired comparison. These remain alternatives rather than a universal production architecture. Frontend exploration converged on a graph-led observability layer so users can inspect execution, evidence, interventions and gaps under the surface. It remains a draft, provisionally approved, with no production UI integration.

Sponsor research preserved options and owner preferences including CRE/0G. The owner explicitly selected New Project rather than Continuity; that declaration does not establish organizer acceptance or partner eligibility. Current prize terms and concrete integration remained unresolved. No sponsor deployment, account-credit spending, wallet or signing operation occurred. Code/notes: explorations/; drafts/frontend/; docs/WORKSTREAMS.md.

## 2 November: first executable verification loop

The owner asked for one successful verification loop. The authored offline runtime demonstrated two adapter shapes: an initially eligible proposal passed; expired reuse failed; the host actually delivered the finding; the scripted agent acknowledged, refreshed and revised; recheck produced a version-bound clearance. Wrong-value and old-clearance controls were rejected. This is an executed mechanism demonstration with synthetic values and an authored60-second TTL, not a live agent experiment.

Code: procedural_loop/. Portable clone entry point: tools/offline_demo.py. The original protected execution used `verification-loop-20261102T175357Z-2a96a2e5` and passed66 dedicated tests.

## 2–3 November: verification on original framework logs

The owner requested applying the loop to real LangChain/TradingAgents logs. A source adapter reviewed selected original Sol/Terra reports from the synthetic-market baseline. The historical Sol omission stayed FAIL; Terra's required-call PASS did not establish complete procedure or factual support. A new local reviewer receipt retrieved original evidence and rechecked selected consistency. It did not invent historical delivery, fresh market data or a corrected original-agent decision.

Code: recorded_loop/. Recorded replay: `recorded-verification-20261102T182919Z-8ad6c261`. See recorded_loop/POLICY.md and SOURCE_ADAPTER.md for the selected scope.

## 3 November: live native-source run

After asking where the prices came from, the owner identified the synthetic-evidence limitation and authorized a new run under the same time and cumulative-budget constraint. A separate adapter preserved native Yahoo/Polymarket/FRED tool strings and schemas, capturing provenance out of band. It recorded optional source failures instead of inserting fixtures or forcing tool use.

Three concurrent Sol/Terra pairs completed in a 30-minute observation window, with84 successful responses and paper Underweight throughout. Sol's three snapshot omissions and Terra's three invocations persisted under the same two-round tool cap. Live price/source differences, a faulty provider row and missing sources were captured. TrustKernel feedback remained disabled. Different dates and evidence make the Hold/Underweight change descriptive, not causal.

Code: live_experiment/. Original session: `20261102T192912Z-live-30min-2f24b1`. See [latest-run evidence](LATEST_RUN.md).

## 4 November: live-corpus extraction, verification and handoff

The owner authorized running the atomic ledger and verification rules on those completed live logs. A separate live-corpus adapter reused frozen deterministic extraction primitives without rebuilding older profiles. The resulting ledger contains39,448 rows and3,217 provisional candidates. All30 report origins resolve, including18 exact structured-output render replays. The rules produce2,185 scoped findings; 12 FAIL findings refer to omissions, source bounds, observed version disagreement and report truncation.

The canonical ledger and findings rebuild byte-for-byte;35 dedicated tests and the parent source/artifact audit pass. All416 protected files remain unchanged. This is post-hoc observation/verification. A real agent's finding→hold→refresh→recheck loop remains the next product proof.

Code: live_verification/; rules policy; tools/inspect_live_ledger.py. Run identity: `live-verification-20261103T190006Z-85ac8aae`. [Latest findings and limits](LATEST_RUN.md).

The owner then requested one GitHub repository carrying the condensed active state, a reusable BB8 snapshot and indexed context for everyone. The public package includes implementation, tests, schemas and curated context; private runtime evidence, credentials, budgets and personal knowledge remain outside it. This README/context/BB8 layer is the continuation entry point, rather than access to the owner's local chats.

## 5 November: continuous capture and actual-agent feedback focus

The owner prioritized asynchronous log capture into the atomic ledger, verification on explicit agent calls, a TradingAgents experiment with trusted verification instructions and feedback, and CLI/SDK/MCP access across harnesses. The eventual frontend should expose that same event/graph/intervention history; implementing it now is out of scope.

The [continuous verification plan](../CONTINUOUS_VERIFICATION_PLAN.md) grounds this in the early private design documents and current code. It distinguishes asynchronous capture from checkpoint-consistent verification, common contracts from per-harness capture/enforcement, and voluntary tool use from a host-enforced gate. It proposes offline incremental replay first, a bounded separately approved actual-agent smoke loop next, and thin MCP plus a second harness afterward. This is proposed architecture and a continuation plan, not completed integration or approval for research spend. Prior findings remain historical.
