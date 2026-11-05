# Durable capture and stored-reference verification

Updated 5 November 2026. Lane B now implements an offline native storage slice
and a callable typed-host-event backend bound to accepted
`continuous-verification-0.2`. Historical writers/builders and private recordings
are unchanged. No provider/model execution or full semantic-ledger claim.

Accepted dependency provenance: A source commit
`e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2`, integrated as `29f038f`.
The accepted __init__, contracts, verifier, schema, example, two tests and
CONTRACT.md were imported byte-for-byte, with no edits. The earlier 0.1 candidate
`8eadcb1` was rejected for a causal-cycle/future-parent defect; it is historical,
not the current dependency. No PR or integration branch was merged by this lane.

## Concrete service API for C/D

All imports below come from `continuous_verification.service`. These signatures
are implemented; service acceptance/integration still requires orchestrator review.

```python
Principal(actor_id: str, permissions: frozenset[str], run_ids: frozenset[str])
ServiceBackend(journal_path, *, principal, service_id, project_on_ingest=True)
backend.configure_run(run_id, streams)
backend.install_policy(run_id, accepted_A_policy)
backend.record_coverage(run_id, stream_id, observations)
backend.project(run_id)
backend.resolve_view(accepted_A_request) -> {checkpoint, events, policy}
backend.execute(operation, request) -> dict
backend.audit() -> dict
backend.close()
ServiceError.code, ServiceError.public_message, ServiceError.issues
```

Principal construction and the local database path belong to the trusted host,
never model/tool request JSON. The host must authenticate its callers before
injecting a principal. This local grant enforcement is not network authentication.
`permissions` uses configure/collect/verify/read/feedback. Run scope is checked
for every host method and operation. D's preliminary Access check does not replace
B's principal and nested-object authorization. B imports no transport module.

`configure_run` requires configure permission. Its nonempty `streams` list uses
exact fields `{stream_id, collector_id, producer_id, adapter_version,
redaction_profile}`; the stream set and assignments are immutable in this slice.
Each configured collector ID must equal the trusted principal actor ID when it
ingests that stream. Checkpoint, registration and explicit projection require the
host actor assigned to every registered stream; a coordinator should be assigned
all streams it establishes. Native producer restart handling needs an explicitly
new run/configuration or preconfigured stream; dynamic registry revision is not
implemented. Registry revision is always integer 0, never agent-selected authority.

`install_policy` requires configure permission and stores an accepted A policy
under immutable identity/version. No transport operation installs policies.
`record_coverage` requires collect permission and the assigned stream collector.
Its observations are A capability objects `{name,state,basis_event_ids}`; captured
coverage needs retained same-run basis IDs. Missing capabilities remain UNKNOWN.
The declaration is a trusted collector assertion, not proof of uninstrumented
activity. Model request JSON cannot set coverage, collector assignment, service
identity, projected watermarks or SERVICE_ESTABLISHED state.

| Operation | Exact request fields | Backend result |
| --- | --- | --- |
| register_run | run_id, registration_id | Activates host-preconfigured streams; run_id, registry_revision, streams, coverage limit |
| ingest_events | run_id, batch_id, events (accepted A envelopes) | Durable receipt_id, per-event receipt_position and ACCEPTED/DUPLICATE status, stream ingest/gap state |
| checkpoint | run_id, checkpoint_id, revision, registry_revision, streams list of {stream_id,requested} | Exact service-established A checkpoint, stored immutably with its frozen event view |
| verify | Exact accepted A request unchanged | Exact validated, retained A result resolved from stored checkpoint/policy/events |
| get_assessment | run_id, assessment_id | Exact retained result, including errors and failed/unready findings |
| get_evidence | run_id, event_id, optional span [start,end] | Retained A event/origin and optional exact Unicode excerpt/span; no filesystem resolution |
| get_run_state | run_id | Actual raw/typed projection counts, per-stream watermarks/gaps, coverage, native mapping limit, atomic_semantic_ready=false |
| list_events | run_id, after_cursor (null initially), limit (integer 1..100) | Pinned snapshot_id, events, next_cursor (null at end), has_more |
| acknowledge_feedback | Not implemented | Explicit UNSUPPORTED_OPERATION; never an empty successful acknowledgement |

Unexpected fields are rejected. register_run does **not** accept streams,
expected_revision, collector IDs or capabilities from model JSON. This replaces
the earlier proposed mutable-registry DTO; no conflicting old proposal is active.
The optional execute hook keyword is trusted crash-test injection, not a tool arg.

ServiceError codes: INVALID_REQUEST, FORBIDDEN, NOT_FOUND, CONFLICT,
INVALID_CURSOR, UNSUPPORTED_OPERATION, BACKEND_UNAVAILABLE. Its message is bounded
public text; optional issues contain safe schema paths/codes only. D can translate
to InterfaceError(code, public_message); its current error envelope does not carry
structured issues. Unexpected exceptions must become generic BACKEND_ERROR at
the transport boundary, with no raw paths/tracebacks/request contents. A valid
NOT_READY/CAPTURE_GAP/ERROR/FAIL/INCONCLUSIVE/HOLD/RECHECK remains an unchanged result,
not a transport failure or PASS. Invocation success never means decision clearance.

`resolve_view` is a read-authorized host method, not an extra model tool. It
validates the accepted request and every stored reference, returning detached JSON
for exactly the immutable checkpoint/event order/installed policy used by verify.
C can call `assessment_binding(request, **view)` or
`binding_matches(result['binding'], request, **view)`. It never reconstructs from
the newest stream state, establishes coverage or changes policy. A retained
request's unresolved references remain unresolved in that frozen view even if
similarly named data subsequently arrives in another run.

## Persistence, views and procedural readiness

`Journal` creates a separate SQLite authority (`native-receipt-journal-1`).
Typed tables are an additive, version-bound `typed-service-0.2-1` namespace in that
same isolated database. Existing unrelated SQLite files are refused from their
header before SQLite can create sidecars; unknown storage versions are refused.
The database is local/single-worker. FULL synchronous WAL transactions commit
accepted native or typed events and their durable receipts together before return.
No independent dual-write authority is claimed. Original redacted JSONL stays a
read-only source; projections and exports are not a second write authority.

Typed event IDs are run-wide unique; `(run,stream,sequence)` also binds immutable
content. Duplicate event transport receipts have no second logical projection
row. A batch ID binds its entire request and original receipt; retry returns that
receipt, but still requires the assigned collector. Changed batch/event identities
reject the entire transaction. Source identity/version binds content, status and
valid time; report ID/revision, input ID, proposal ID/revision, request, policy,
checkpoint and assessment history cannot be overwritten. Separate native and typed
event/receipt/object hash chains detect corruption, not authenticity. Startup and explicit
audits replay retained bindings. No signatures or global approval are inferred.

Typed ingestion accepts already structured A observations from the trusted host:
tool-result, assembled model-input, report and other declared lifecycle records.
The procedural projection retains their exact content, origin pointers/spans,
parents and typed fields. Synchronous projection shares the receipt transaction
by default. `project_on_ingest=False` leaves observable projection lag until the
trusted host calls project(run_id). This is a narrow procedural record projection,
not full qualitative decomposition, accepted factual support or a complete atomic
semantic ledger. The backend always reports atomic_semantic_ready=false.

A checkpoint captures three distinct things: the immutable configured stream
registry (revision 0), every requested per-stream position, and the ingestion view
actually retained when it was established. It stores the exact event array and
its digest, ordered by `(stream_id,sequence,event_id)`, plus the durable ingestion
high-watermark. Every registered stream must be present, including idle/unknown
streams. Current highest-observed, contiguous-ingested and actually-projected
watermarks are different. Interior missing sequences become explicit gap ranges;
unobserved tails/worker lag remain NOT_READY. A checkpoint also freezes collector
coverage; later coverage/ingest/projection does not repair that checkpoint. Retry
returns the exact old checkpoint; a new revision captures a later view.

Verify validates A's request, resolves stored checkpoint identity/revision/digest,
resolves operator-installed policy identity/version/digest and uses only that
checkpoint's retained events. Every nested known event/checkpoint/policy/report/
assessment reference is scoped to the authorized run. Foreign references are
FORBIDDEN; missing permitted objects are NOT_FOUND; changed/stale identity bindings
are CONFLICT. Missing evidence in a frozen view stays a declared prerequisite gap.
Proposal and request revisions are immutable. Exact A results, including ERROR
with no binding, CAPTURE_GAP, NOT_READY, FAIL and INCONCLUSIVE, are retained; repeat
requests and get_assessment do not recompute them from later data.

Only the proposal's report_event_id + report_id + report_revision is checked by
A's scoped rules. A procedural PASS is not downstream decision truth, source
truth, complete dependencies or a host-enforced trading gate. Feedback lifecycle
events can be ingested explicitly; their assessment/proposal/revision bindings
must match retained requests. Acknowledgement, input inclusion and correction
remain separate observations. The convenience acknowledgement operation is not
implemented, and observations never rewrite the original assessment.

Reads use retained content and Unicode code-point half-open spans. list_events
first pins the durable typed-ingestion high-watermark in service-owned cursor
state. Subsequent pages exclude later appends; persisted opaque cursors survive
restart. They grant no access. Foreign-run cursor: FORBIDDEN; absent/malformed
cursor: INVALID_CURSOR. No expiry/compaction is implemented. Start a new null-cursor
read for a later view. The current run registry cannot silently replace the one
bound to an old checkpoint.

## Native trace storage remains a separate input stage

TraceTailer polls only an explicit already-reviewed/redacted native Trace v1
JSONL path. It is not a redaction gateway or background scheduler and makes no
model/provider call. Each source ID binds path, filesystem identity, line/byte
cursor and consumed-prefix SHA256. Every poll rehashes the consumed prefix in
bounded chunks. Incomplete final lines remain unacknowledged. Malformed complete
lines, overlong lines (8 MiB default), missing/rotated/truncated/rewritten files
halt capture and retain sticky source issues. Rotation needs a new explicit source
ID; faults are never silently cleared. Mutation between polls is detected next
poll; no claim is made about all upstream activity or host flush guarantees.

Native receipt/cursor/event commit is atomic; crash before commit rolls back and
crash after commit before acknowledgement safely resumes. Raw receipt bytes,
line numbers and byte spans remain exact. Native producer self-hashes use the
original serialization. Sequence gaps and native-chain mismatches stay observable.
Out-of-order arrivals fill only a later ingestion view, never an earlier prefix.

The native Projection is a detached, journal-bound, suffix-incremental visible-text
inventory of prompts/messages, visible generation text and string tool returns.
It preserves JSON pointers, hashes and Unicode spans. Unknown shapes remain raw;
reasoning blocks are not inventoried as accessible text. PREFIX_AVAILABLE means
captured surface rows only. Native storage_snapshot always returns
atomic_status=UNAVAILABLE and ledger_ready=false; lag, gaps, prefix mismatch and
sticky source issues give NOT_READY. A cache advanced past a prefix must use a
fresh replay for that older prefix. No later source is matched into an earlier input.

There is **no automatic native Trace -> typed assembled-input/report mapping**.
Native text inventory alone cannot justify A's model-input boundary, closed report,
completion or coverage. C's reviewed host adapter must provide those observations;
otherwise they remain UNKNOWN/INCONCLUSIVE. MCP connectivity cannot prove
whole-session capture, hidden reasoning or next-input inclusion.

## Verification and continuation

```powershell
py -3.11 -S -B -m unittest tests.test_continuous_capture tests.test_continuous_projection -v
py -3.11 -S -B -m unittest discover -s tests -p 'test_continuous*.py' -v
```

Current authored service controls cover real persisted scoped verification,
unknown coverage, frozen gaps/lag/late arrivals, registered idle streams, atomic
batch collisions/retries, immutable source/report/proposal identities, denied
collectors and foreign nested references, stale policy/checkpoint bindings,
actual subprocess crash before/after commit, restart-stable pinned pagination,
exact replay parity, retained causality errors and no semantic-ledger readiness.
Service fixtures copy the public authored A example into temporary inputs; they
are not historical trace conversion or actual model/framework behavior.

Native controls cover partial Unicode lines, file change, malformed inputs,
crashes/lost acknowledgement, hash/cursor corruption and incremental/full replay.
The lane doc records final test counts and publication checks. No optional native
framework or MCP integration is counted as PASS by this lane. No original private
corpus/history rebuild, budget mutation, paid call, frontend, trade or signature.

Next: orchestrator reviews this callable service and C/D bind their adapters/tests
against its actual persisted results. Shared CI/current README/orchestration and
generated integration conflicts remain orchestrator-owned. Dynamic registry,
network authentication, standalone service lifecycle, quotas, compaction and
complete semantic extraction are not implemented in this offline milestone.
