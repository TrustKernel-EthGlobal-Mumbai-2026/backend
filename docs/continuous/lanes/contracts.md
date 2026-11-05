# Define continuous-verification contracts and scoped assessment semantics

Lane A. Updated 5 November 2026. Status: ACCEPTED_SCOPED_OFFLINE.

Branch: `codex/contracts-checkpoints`, draft PR base: `codex/continuous-verification`.

Define versioned observable events, per-stream checkpoints, request/result bindings and prerequisite-aware outcomes. Add deterministic validation and named required-call/report-completion checks with malformed, gapped, unready and stale-binding controls. Persistence, transports and agent execution belong to the other lanes.

Owned paths: continuous_verification/__init__.py, contracts.py, verifier.py and schemas/; tests/test_continuous_contracts.py and test_continuous_verifier.py; docs/continuous/CONTRACT.md.

Dependency gate: corrected API accepted by the orchestrator for scoped offline integration;
other lanes should use [the contract](../CONTRACT.md) and authored example packet.
Version: `continuous-verification-0.2`. Exact signatures are in that document.

Implemented: pure structural/integrity validators, immutable previous-object
controls, complete-input bindings, per-stream readiness and two named checks.
Changed owned files: package initializer, contracts, verifier, schema/example,
contract document and dedicated contract/verifier tests. No persistence or transport.

Candidate milestone: commit `8eadcb1`, with exact API/example and 7 passing
contract tests. Final dedicated validation uses `py -3.11 -S -B -m unittest
discover -s tests -p "test_continuous*.py" -v`; 29 authored offline tests pass.
Controls cover omission, truncation, unknown capabilities, late input, per-stream
lag/gaps, stale binding, malformed/cross-run/duplicate events and feedback lifecycle.
Orchestrator review rejected candidate 0.1 for accepting a causal cycle. Candidate
0.2 rejects self/future parents and observable cross-stream cycles, makes missing
parents explicit readiness obligations, and binds report event/ID/revision. It
documents that the checked report is upstream of the separate paper proposal.
This verifies the candidate boundary, not other lanes or a real-agent experiment.

Publication checks: branch context index and packaging manifest regenerated;
index check, export/hash scan and Git whitespace diff checks must pass before push.
Central README, orchestration and CI remain orchestrator-owned.

Acceptance: source commit `e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2` was
independently reviewed by the orchestrator: all 29 tests passed from an immutable
snapshot, and the original cycle control returned ERROR/CAUSALITY with no binding
or PASS. Exact reviewed sources were placed on the integration branch at
`29f038f` without merging PRs or main. PR #2 remains draft.

Acceptance applies only to offline procedural checks of the bound report event,
report ID and revision. Downstream decision truth, collector authentication,
registered-stream completeness and actual input assembly remain service/host
obligations. The actual runtime milestone remains incomplete. No live policy or
paid execution is approved.

Next: remain available for concrete cross-lane integration regressions against
the accepted API. No schema or policy expansion is planned.
Blockers: none in lane A; runtime integration remains with the orchestrator/B/C/D.

Read ../ORCHESTRATION.md and ../../CONTINUOUS_VERIFICATION_PLAN.md before implementation. Update this file with actual changed files, commands, tests, blockers and next action. Keep machine-specific state and full chat transcripts out of the repository. No paid model/provider calls, original-budget mutation, live run, trading, signing or on-chain operation. Do not merge or modify another lane's files.
