# Capture traces durably and project checkpointed atomic records incrementally

Lane B. Updated 5 November 2026. Status: QUEUED; implementation chat being created.

Branch: `codex/capture-ledger`, draft PR base: `codex/continuous-verification`.

Tail redacted captured JSONL into a new isolated journal and incremental projection. Preserve exact origin references and checkpoint watermarks; handle duplicates, gaps, partial lines and restarts. Demonstrate incremental/full replay parity at identical prefixes. Do not rebuild historical profiles or fetch sources.

Owned paths (new paths are proposed, not implemented): continuous_verification/capture.py, journal.py, projection.py and service.py; tests/test_continuous_capture.py and test_continuous_projection.py; docs/continuous/CAPTURE.md.

Dependency gate: Prepare replay/storage work now, then bind to lane A accepted event/checkpoint/result contracts. Do not freeze a competing schema.

Read ../ORCHESTRATION.md and ../../CONTINUOUS_VERIFICATION_PLAN.md before implementation. Update this file with actual changed files, commands, tests, blockers and next action. Keep machine-specific state and full chat transcripts out of the repository. No paid model/provider calls, original-budget mutation, live run, trading, signing or on-chain operation. Do not merge or modify another lane's files.
