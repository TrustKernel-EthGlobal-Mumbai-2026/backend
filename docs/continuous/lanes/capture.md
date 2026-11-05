# Capture traces durably and project checkpointed atomic records incrementally

Lane B. Updated 5 November 2026. Status: STORAGE MILESTONE; public integration
blocked on orchestrator acceptance of lane A's candidate contract.

Branch: `codex/capture-ledger`, draft PR base: `codex/continuous-verification`.

Tail redacted captured JSONL into a new isolated journal and incremental projection. Preserve exact origin references and checkpoint watermarks; handle duplicates, gaps, partial lines and restarts. Demonstrate incremental/full replay parity at identical prefixes. Do not rebuild historical profiles or fetch sources.

Owned paths (new paths are proposed, not implemented): continuous_verification/capture.py, journal.py, projection.py and service.py; tests/test_continuous_capture.py and test_continuous_projection.py; docs/continuous/CAPTURE.md.

Dependency gate: Prepare replay/storage work now, then bind to lane A accepted event/checkpoint/result contracts. Do not freeze a competing schema.

Read ../ORCHESTRATION.md and ../../CONTINUOUS_VERIFICATION_PLAN.md before implementation. Update this file with actual changed files, commands, tests, blockers and next action. Keep machine-specific state and full chat transcripts out of the repository. No paid model/provider calls, original-budget mutation, live run, trading, signing or on-chain operation. Do not merge or modify another lane's files.

Implemented: native redacted JSONL tailing; transactional authoritative SQLite
receipts/cursors; identity collision rejection, hash-chain audit, partial-line and
source-change handling; per-native-run contiguous watermarks; visible-text
projection and fixed-prefix replay. This is raw/visible-text availability, **not**
a complete atomic ledger or integrated verifier. `ledger_ready` remains false.

Changed owned paths: the four modules and two tests listed above,
`docs/continuous/CAPTURE.md`, and this lane doc. Branch-local generated context
index/packaging metadata are refreshed before publication; orchestrator resolves
generated conflicts. Central README/orchestration/CI were not changed.

Validation: `py -3.11 -S -B -m unittest tests.test_continuous_capture
tests.test_continuous_projection -v` — 26 authored temporary-input tests pass,
including actual subprocess crashes before/after durable commit. Initial storage
milestone published at `4105abd`; hardening adds suffix reads, detached projection
rows, journal binding, explicit gap ranges and unrelated-database refusal.
No original corpus/history build, optional native integration or provider call.
Detailed boundaries and test risks: [CAPTURE.md](../CAPTURE.md).

Blocker: A's candidate `continuous-verification-0.1` (`8eadcb1`) is NOT ACCEPTED;
orchestrator requested future-parent/causal-cycle repairs. Need corrected accepted event/checkpoint/verifier schema revision,
native trace mapping, registered-stream/coverage ownership and extraction versus
procedural readiness agreement. These are recorded in CAPTURE.md; no competing
public event contract or fake successful verifier was created.

Read-only inspected D's INTERFACES.md and sdk.py. CAPTURE.md now proposes exact
nine-operation stored-reference DTOs, host-bound principal construction, registered
streams, collector-only coverage, immutable checkpoint/policy resolution, stable
paginated read semantics and B-owned typed errors. Proposal only: current service
does not implement these operations or claim atomic ledger readiness.

Next: await corrected accepted A commit and orchestrator/C/D agreement on the
facade before public service binding. Orchestrator needs to register the new suites in shared
CI and update central active-state documentation when the integration is ready.
