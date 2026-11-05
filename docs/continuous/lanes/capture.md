# Capture traces durably and project checkpointed procedural records

Lane B. Updated 5 November 2026. Status: CALLABLE SERVICE MILESTONE; orchestrator
service review and C/D integration are next. Branch codex/capture-ledger, draft PR
#3 targeting codex/continuous-verification. No merge or paid run.

Accepted A dependency: e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2, integrated 29f038f,
continuous-verification-0.2. A's eight source/schema/example/test/doc dependency
files are imported byte-for-byte unchanged. Earlier 8eadcb1 was rejected and is
not the active contract. Central README/orchestration/CI are untouched.

Implemented owned files: continuous_verification/capture.py, journal.py,
projection.py, service.py; tests/test_continuous_capture.py and
 tests/test_continuous_projection.py; docs/continuous/CAPTURE.md and this lane doc.
The initial native storage milestone was 4105abd; hardening/facade proposal was
1f62562. This slice binds the accepted contract to real persisted typed events.

ServiceBackend provides host-only configure_run/install_policy/record_coverage/
project, read-authorized resolve_view(A_request)->{checkpoint,events,policy},
and D-compatible execute(operation,request). Principals/grants and stream
collector assignments come from trusted host configuration. register_run JSON
only activates configured streams; clients cannot grant coverage, service authority
or policy. Implemented operations: register_run, ingest_events, checkpoint, verify,
get_assessment, get_evidence, get_run_state, list_events. acknowledge_feedback
returns explicit UNSUPPORTED_OPERATION; captured lifecycle events remain separate.
Exact fields, signatures, safe error codes and limits are in [CAPTURE.md](../CAPTURE.md).

Native JSONL remains raw/visible-text inventory with ledger_ready=false. Typed
host tool-result/model-input/report records support scoped procedural checks;
atomic_semantic_ready remains false. No automatic native report/input-boundary
mapping, complete semantic-ledger claim or global decision clearance.

Checkpoints freeze registered stream set, requested vector, actual ingestion
view, projection state and collector coverage. Missing/lagged prefixes cannot
PASS; late evidence needs a new checkpoint revision and cannot repair old results.
Assessments/errors and identity revisions are immutable and persisted. Reads are
run-authorized, exact-span and pinned-cursor based. Crash recovery and replay use
only temporary authored inputs copied from A's public example.

Validation: 26 native storage/projection tests plus 23 typed stored-service tests
pass; accepted A's 29 tests also pass in this checkout (78 total). Final context
index/manifest/export/diff checks are run before publication; exact commands and
head are also retained in private coordination status. No optional native/MCP test
is counted as PASS and no historical corpus builder or provider was run.

Next: publish callable API commit, await orchestrator code/test review and C/D
integration. Orchestrator owns shared CI, README/current-state updates and generated
metadata conflict resolution. Frontend, independent evaluation and live execution
remain deferred. No sibling clone writes or cross-chat messages were performed.
