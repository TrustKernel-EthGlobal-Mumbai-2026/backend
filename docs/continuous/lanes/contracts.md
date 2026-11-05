# Define continuous-verification contracts and scoped assessment semantics

Lane A. Updated 5 November 2026. Status: QUEUED; implementation chat being created.

Branch: `codex/contracts-checkpoints`, draft PR base: `codex/continuous-verification`.

Define versioned observable events, per-stream checkpoints, request/result bindings and prerequisite-aware outcomes. Add deterministic validation and named required-call/report-completion checks with malformed, gapped, unready and stale-binding controls. Persistence, transports and agent execution belong to the other lanes.

Owned paths (new paths are proposed, not implemented): continuous_verification/__init__.py, contracts.py, verifier.py and schemas/; tests/test_continuous_contracts.py and test_continuous_verifier.py; docs/continuous/CONTRACT.md.

Dependency gate: Publish a candidate API and contract commit for orchestrator review. Other lanes depend on the accepted contract.

Read ../ORCHESTRATION.md and ../../CONTINUOUS_VERIFICATION_PLAN.md before implementation. Update this file with actual changed files, commands, tests, blockers and next action. Keep machine-specific state and full chat transcripts out of the repository. No paid model/provider calls, original-budget mutation, live run, trading, signing or on-chain operation. Do not merge or modify another lane's files.
