# Wire TradingAgents proposals to verification feedback and bounded recheck

Lane C. Updated 5 November 2026. Status: OFFLINE MILESTONE; WAITING FOR A/B.

Branch: `codex/tradingagents-feedback`, draft PR base: `codex/continuous-verification`.
Early inspection/offline slice published in `b079882`; tested milestone follows.

Implemented owned paths: `continuous_verification/tradingagents.py`,
`continuous_verification/prompts/tradingagents.md`,
`tests/test_continuous_tradingagents.py`, `docs/continuous/TRADINGAGENTS.md`.
This lane doc and rebuildable context-index/packaging metadata also change.

The pin and clean upstream state were verified read-only. Exact pinned analyst
factory/dispatch/turn functions were tested in an isolated AST-loaded namespace
with real LangGraph, authored responses/tools and no upstream package import.
Normal ToolMessage and wrap-up text paths both return findings into next input.
No actual-model response or full graph integration is claimed.

Verification:

- Standard-library suite: 8 generic tests PASS; optional native class SKIP.
- Cached native environment and pinned-source path: 10 tests PASS, including
  2 native dispatch cases. No dependencies installed.
- Command: `python -B -m unittest discover -s tests -p test_continuous_tradingagents.py -v`.
  Native execution requires the exact pinned path in
  `TRUSTKERNEL_TRADINGAGENTS_UPSTREAM`; use `-S` for the generic-only suite.
- Context index build/check, manifest refresh, export and diff checks run before
  publishing. Tests use authored inputs; no historical corpus/profile rebuild.

See [implementation, pinned seams and limits](../TRADINGAGENTS.md).
The trusted instruction/tool, proposal/checkpoint callback, independent counters,
finding delivery/input observations, revisions/recheck and abstention are local
plumbing. A/B callbacks and at-use authorizers remain explicitly labeled doubles.
The original subgraph shares a tool-round cap and is not yet replaced or gated.

Blocking next slice: orchestrator relay of A's accepted request/result constructors,
binding/readiness/disposition and issuer/policy semantics, plus B's proposal
registration, flush/barrier checkpoint and actual verify backend. Next action:
bind those accepted contracts, then splice the named report boundary and test
offline. Work stops at that gate; no behavioral experiment will be launched.

A candidate `verify(request, *, checkpoint, events, policy) -> dict` is under
orchestrator review, not accepted or used here. Local proposal IDs refer only to
the named market-report revision; map to accepted `report_event_id`, report text,
completion boundary and actual model-input event IDs. Later paper decisions are
separate artifacts and cannot inherit report clearance. Input-attempt observations
include ordered visible-message fingerprints; exact retained input/spans and
checkpoint references must come from B. No agent-controlled policy/coverage.

Orchestrator follow-ups: central README/orchestration state, CI registration and
generated metadata conflict handling. No central files or sibling clones edited.
No paid model/provider calls, budget mutation, live run, trading, signing, on-chain
operation or merge. Frontend and independent quality evaluation remain deferred.
