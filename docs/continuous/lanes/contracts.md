# Define continuous-verification contracts and scoped assessment semantics

Lane A. Updated 5 November 2026. Status: IMPLEMENTED_CANDIDATE; acceptance pending.

Branch: `codex/contracts-checkpoints`, draft PR base: `codex/continuous-verification`.

Define versioned observable events, per-stream checkpoints, request/result bindings and prerequisite-aware outcomes. Add deterministic validation and named required-call/report-completion checks with malformed, gapped, unready and stale-binding controls. Persistence, transports and agent execution belong to the other lanes.

Owned paths (new paths are proposed, not implemented): continuous_verification/__init__.py, contracts.py, verifier.py and schemas/; tests/test_continuous_contracts.py and test_continuous_verifier.py; docs/continuous/CONTRACT.md.

Dependency gate: executable candidate API published for orchestrator review;
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

Next: orchestrator review/acceptance and cross-lane integration against the exact
API. Persistence must enforce authority, registered streams and history-wide
immutable identities; no global clearance or paid execution is claimed.
Blockers: no implementation blocker; candidate acceptance is an integration gate.

Read ../ORCHESTRATION.md and ../../CONTINUOUS_VERIFICATION_PLAN.md before implementation. Update this file with actual changed files, commands, tests, blockers and next action. Keep machine-specific state and full chat transcripts out of the repository. No paid model/provider calls, original-budget mutation, live run, trading, signing or on-chain operation. Do not merge or modify another lane's files.
