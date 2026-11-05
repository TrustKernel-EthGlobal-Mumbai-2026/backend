# Define continuous-verification contracts and scoped assessment semantics

Lane A. Updated 5 November 2026. Status: CANDIDATE_API; acceptance pending.

Branch: `codex/contracts-checkpoints`, draft PR base: `codex/continuous-verification`.

Define versioned observable events, per-stream checkpoints, request/result bindings and prerequisite-aware outcomes. Add deterministic validation and named required-call/report-completion checks with malformed, gapped, unready and stale-binding controls. Persistence, transports and agent execution belong to the other lanes.

Owned paths (new paths are proposed, not implemented): continuous_verification/__init__.py, contracts.py, verifier.py and schemas/; tests/test_continuous_contracts.py and test_continuous_verifier.py; docs/continuous/CONTRACT.md.

Dependency gate: executable candidate API published for orchestrator review;
other lanes should use [the contract](../CONTRACT.md) and authored example packet.
Version: `continuous-verification-0.1`. Exact signatures are in that document.

Implemented: pure structural/integrity validators, immutable previous-object
controls, complete-input bindings, per-stream readiness and two named checks.
Changed owned files: package initializer, contracts, verifier, schema/example,
contract document and dedicated contract tests. No persistence or transport.

Validation: `py -3.11 -S -B -m unittest discover -s tests -p
test_continuous_contracts.py -v` passed 7 authored offline tests. This verifies
the candidate boundary, not other lanes or a real-agent experiment.

Next: complete negative verifier tests, review causal/input/coverage edge cases,
regenerate branch context/packaging metadata and publish the draft PR update.
Blockers: no implementation blocker; candidate acceptance is an integration gate.

Read ../ORCHESTRATION.md and ../../CONTINUOUS_VERIFICATION_PLAN.md before implementation. Update this file with actual changed files, commands, tests, blockers and next action. Keep machine-specific state and full chat transcripts out of the repository. No paid model/provider calls, original-budget mutation, live run, trading, signing or on-chain operation. Do not merge or modify another lane's files.
