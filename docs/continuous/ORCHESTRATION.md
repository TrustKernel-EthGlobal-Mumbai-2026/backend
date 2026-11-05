# Continuous verification: active orchestration

Updated: 5 November 2026. Status: A/B review gates accepted; C/D integrating the actual local backend.
Owner approved parallel work in separate chats, coordinated by the existing
orchestrator chat. This file is the repository's current coordination record.
The earlier [architecture proposal](../CONTINUOUS_VERIFICATION_PLAN.md) supplies
the rationale; it is not evidence that an implementation already exists.

## Objective and gates

Deliver one offline, checkpoint-bound capture -> ledger -> verification ->
feedback -> revision -> recheck integration, then prepare a separately approved
actual-model smoke run. Keep recorded private evidence, budgets and historical
implementations unchanged. No model/provider calls, trading, signatures,
on-chain writes or live experiment are authorized by these workstreams.

The orchestrator owns scope, contract acceptance, integration, PR descriptions,
README/current-state updates, generated indexes/manifests and final review.
Implementation lives in separate chats and isolated clones. Workstream owners
report changed files, commands, test evidence, assumptions, blockers and the next
dependency. They do not merge PRs or claim another lane's work is complete.

## Branch and dependency map

Integration branch: `codex/continuous-verification`, targeting `main`.
Draft [integration PR #1](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/1) contains the shared plan and current-state records. Initial plan commit `be4e17f926c0fb90e289b415a8e1e0ffc754cebd` passed GitHub offline CI. This is plan/package validation, not runtime implementation validation.
Each workstream branches from this integration branch and opens a draft PR back
to it. Retarget to main only after the integration plan is deliberately changed.
Do not auto-merge any branch. PR descriptions must distinguish implemented work
from remaining tasks; a draft scope commit is not implementation completion.

| ID | Workstream | Branch | Can start independently | Gate before integration |
|---|---|---|---|---|
| A | Contracts and scoped verifier | codex/contracts-checkpoints | Contract/schema design, validation and deterministic tests | Orchestrator accepts a versioned request/result/checkpoint API |
| B | Durable capture and incremental ledger | codex/capture-ledger | Existing-trace tailing, spool/replay analysis and crash/gap tests | A's accepted event/checkpoint contract; prefix/replay equivalence |
| C | TradingAgents feedback adapter | codex/tradingagents-feedback | Pinned graph inspection, trusted instruction/tool definitions and offline host tests | A's verify API and B's real checkpoint; instrumented dispatch/resume proof |
| D | SDK, CLI and MCP access | codex/cli-sdk-mcp | Transport discovery, interface parity tests and thin wrapper design | A's schemas and B's backend; no fabricated successful responses |

A is the critical path. B, C and D must not independently freeze competing
schemas. They may use explicitly provisional test doubles, but must name them
as such and bind to A before reporting an integrated result.

## Initial ownership boundaries

All paths are repository-relative and proposed new paths, not claims they exist.

- A: `continuous_verification/__init__.py`, `contracts.py`, `verifier.py`,
  `schemas/`; `tests/test_continuous_contracts.py`,
  `tests/test_continuous_verifier.py`; `docs/continuous/CONTRACT.md`.
- B: `continuous_verification/capture.py`, `journal.py`, `projection.py`,
  `service.py`; `tests/test_continuous_capture.py`,
  `tests/test_continuous_projection.py`; `docs/continuous/CAPTURE.md`.
- C: `continuous_verification/tradingagents.py`, `prompts/`;
  `tests/test_continuous_tradingagents.py`; `docs/continuous/TRADINGAGENTS.md`.
- D: `continuous_verification/sdk.py`, `cli.py`, `mcp_server.py`;
  `tests/test_continuous_interfaces.py`; `docs/continuous/INTERFACES.md`.
- Each lane owns its `docs/continuous/lanes/<lane>.md` status/handoff.
- Orchestrator: shared README/docs/context, this file, CI registration,
  packaging/index generation and shared integration tests when lanes converge.

Request a boundary change through the orchestrator rather than modifying another
lane's files. New tests should run offline with Python3.11; optional native
framework/MCP SDK tests must clearly declare dependencies and must never hide
missing integration behind a PASS. Do not implement a homegrown MCP protocol
server merely to avoid declaring the official SDK dependency.

## Acceptance sequence

1. A publishes a frozen candidate contract, examples and test evidence. The
   orchestrator reviews it and relays accepted commit/API references to B/C/D.
2. B proves durable receipt, idempotency, gap handling, explicit prefix readiness,
   restart recovery and deterministic incremental/full replay agreement.
3. C proves actual pinned framework dispatch/resume plumbing where the installed
   dependencies allow it. Authored model responses remain labeled scripted;
   tests do not demonstrate actual model behavior.
4. D proves equivalent SDK/CLI/MCP operations and transport-error semantics over
   the actual backend. MCP success alone does not prove whole-session capture.
5. Orchestrator reviews PRs, integrates accepted commits on the integration
   branch, regenerates shared metadata and runs cross-lane offline tests.
6. Prepare a concrete model-smoke preflight with explicit cost/time/tool caps,
   unchanged cumulative budget/unknown holds and an approval request. No launch
   until the owner approves it.

Policies start with named required-call/report-completion checks. Do not invent
live freshness TTL, source authority, complete dependencies or full-decision
clearance. Late evidence never silently enters an earlier model-input prefix.
Capture gaps and unready projections cannot produce clearance. Delivery,
model-input inclusion, acknowledgement, corrective action and recheck are separate
observations. Frontend implementation and independent quality ranking stay out
of scope; retain stable graph/event IDs and a cursor-based read contract.

## Active state

| Lane | State | Latest verified evidence | Next action |
|---|---|---|---|
| A | ACCEPTED FOR SCOPED OFFLINE INTEGRATION | [PR #2](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/2), corrected `e088970` / contract0.2: orchestrator independently reran all29 tests and original false-PASS control now rejects | B/C/D bind exact accepted API; A stays available for concrete integration defects |
| B | STORED SERVICE ACCEPTED FOR SCOPED LOCAL INTEGRATION | [PR #3](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/3), `251b3b0`: orchestrator independently reran78 tests (A29+B49); reviewed source imported here | C/D bind actual backend; B stays available for concrete integration defects; semantic readiness remains false |
| C | CAPTURE REPAIR ACCEPTED / SERVICE BINDING REQUESTED | [PR #4](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/4), corrected `9478a61`: orchestrator reran13 generic tests and original ambiguous-return negative control | Integrate actual B receipts/checkpoints/resolve_view and test bounded feedback/revision/recheck; native/actual-model scope remains explicit |
| D | TRANSPORT SLICE VERIFIED / BACKEND DEPENDENT | [PR #5](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/5), `c7e486f`: orchestrator independently verified16 tests with cached official MCP SDK; base run15 PASS/1 optional SDK SKIP | Accepted A dependency bytes exact; actual persisted B-core SDK/CLI/MCP parity remains untested |

The orchestrator updates states after actual chat snapshots and artifact review.
Public status deliberately omits private machine paths, account data and chat
transcripts. Exact local chat/checkout identifiers live in the orchestrator's
private coordination record. Pending or blocked work is never reported as PASS.

Every workstream PR started with a scope/status commit. Initial implementations
are now appearing, but completion is recorded only after actual code and test
evidence review. All four PRs target the integration branch, not main. None is merged.

First orchestrator review: immutable A candidate `8eadcb15da76873edd3d5e32c30065087516dc4a`
passes its seven committed tests. Setting the authored first tool event's parents
to the later report creates a same-stream future dependency and a cycle through
tool -> model input -> report -> tool, yet both procedural checks still PASS.
A received a bounded regression/repair request; no candidate contract has been
accepted or relayed as frozen at that first review. Other lanes continued independent work using
explicitly provisional interfaces. This is a development finding on authored
packets, not a defect asserted about historical market evidence.

Corrected review: source commit `e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2`
defines `continuous-verification-0.2`. All29 contract/verifier tests independently
pass from an isolated immutable snapshot. The original causal-cycle packet now
returns ERROR/CAUSALITY with no binding or positive findings. Cross-stream cycles,
unknown parents, lag/gaps and report ID/revision substitutions have dedicated
controls. The orchestrator accepts this API for named offline report-procedure
integration and imports the exact reviewed files, without merging PRs or main.
Collector/service authentication, complete registered streams, actual native
input exposure and any live policy remain backend/host obligations, not schema
guarantees. Proposal content is a separate downstream decision; these checks
assess the explicitly bound upstream report only.

Storage review: immutable B milestone `1f6256275d7ce5dcede610935dde23efcbe67f8c`
was inspected and all26 dedicated tests independently reran successfully. Tests
cover complete-line durable receipt, commit/ack crashes including actual abrupt
subprocess exit, identity conflicts, sequence gaps, file changes, exact text
spans, restart and incremental/full visible-inventory replay. This verifies that
storage slice only; it has no public checkpoint/verification backend and keeps
atomic semantic readiness unavailable. B's successor service implementation and
all cross-lane integration still require review.

Transport review: immutable D milestone `c7e486f19b005ffe8308ec12303bc8062d526938`
was inspected and independently rerun against the cached official MCP SDK, with
all16 tests passing. The dependency-free run passes15 and explicitly skips the
genuine MCP integration test. A dependency files match the accepted source bytes.
Tests cover real stdio tool discovery/invocation over an authored backend, absent
backend behavior, request/result validation, stale/foreign bindings, permissions,
JSON limits and safe errors. This accepts transport mechanics and validation,
not persisted B service parity or compatibility with every host installation.

Adapter review: immutable C milestone `7961d398fef693d33e4682188dcff5099e6922ff`
passes9 independently rerun generic tests; native tests are explicitly unexecuted
in this audit. A negative control records two successful same-name/same-content
tool calls, then gives the capture helper one flattened human message without a
call ID. The helper marks both distinct calls as included. This overstates exact
origin linkage; text equality cannot identify both call occurrences. C received
a bounded repair request to retain exact input while qualifying ambiguity or
using explicit host-observed transformation lineage. B was asked to expose the
exact frozen checkpoint/event/policy view for C's binding validation. No C capture
or full runtime integration acceptance is claimed yet.

Corrected C review: `9478a61dd8a84009bd53829c19399568c030382c` passes13 generic
tests and the original duplicate-return control independently. It withholds
flattened marker-to-call linkage, retains raw input, and marks uncertain input
boundary UNKNOWN. Ordinary human marker text also cannot establish call origin.
This bounded repair is accepted; no native framework run was exercised in that
independent audit. Exact transformed call lineage remains future work.

Callable B review: `251b3b02c63e860020f94ce0b2962472eb0979fe` passes78 tests
independently from immutable source, including the unchanged A29 suite and49 B
storage/service controls. Reviewed local backend supports trusted registry and
collector bindings, durable typed receipts, frozen checkpoints, installed policy
lookup, retained verification results, exact read-authorized resolve_view and
run-scoped pinned reads. Exact reviewed owned files are imported here. This
accepts a single-worker local procedural backend, not a background daemon, native
trace-to-typed conversion, remote authentication or complete semantic ledger.
The accepted commit/API was relayed to C/D; their actual-core integration tests
remain pending. No PR or main merge, model/provider call or budget change.

## Draft PR descriptions

Integration PR: **Build checkpoint-bound continuous verification across agent harnesses**.
The existing ledger verifies completed recordings. This series adds a successor
runtime for durable capture, explicit ledger checkpoints, scoped verification and
observable agent feedback, while preserving historical runs. It coordinates four
stacked implementation PRs. Initial changes are architecture/context/ownership
only; remaining implementation and validation gates are tracked above. No actual
agent correction, new paid run or frontend readiness is claimed by this PR.

A: **Define continuous-verification contracts and scoped assessment semantics**.
Define versioned observable events, per-stream checkpoints, request/result
bindings and prerequisite-aware outcomes. Add deterministic validation and named
required-call/report-completion checks, with malformed/gapped/unready/stale-binding
controls. This PR does not implement persistence, transports or agent execution.

B: **Capture traces durably and project checkpointed atomic records incrementally**.
Tail redacted recorded JSONL into a new isolated journal/projection, retain exact
origin references and checkpoint watermarks, and recover from duplicates, gaps,
partial lines and crashes. Compare incremental output with replay at identical
prefixes. This PR does not rebuild historical profiles or fetch market data.

C: **Wire TradingAgents proposals to verification feedback and bounded recheck**.
Add a trusted instruction/tool adapter and explicit proposal/checkpoint feedback
cycle over the pinned framework. Preserve original proposals, feedback delivery,
next-input inclusion, correction/abstention and rechecks. Test offline with
authored responses; distinguish those tests from actual-model behavior. Paid
smoke execution remains a later approval gate.

D: **Expose one verification backend through SDK, CLI and MCP**.
Add thin schema-bound access paths with consistent readiness, scoped findings,
errors and read cursors. Verify adapter parity and genuine tool discovery where
dependencies are present. Document per-harness capture/gating limits. No wrapper
may invent missing observations or return canned success as backend verification.
