# Offline capture storage milestone

Status: independent storage/replay milestone, 5 November 2026. Public contract
and verifier integration are blocked on orchestrator acceptance of lane A.
Historical trace writers, closed-corpus builders and accepted outputs are unchanged.

## Persistence and recovery

`continuous_verification.journal.Journal` owns a new, separate SQLite database.
It is the sole authority for new ingestion receipts and tail cursors: each
accepted line commits its event, exact raw receipt and source cursor in one
`BEGIN IMMEDIATE` transaction with WAL and `synchronous=FULL`. An acknowledgement
is returned after commit. A crash before commit rolls back all three; a crash
after commit before acknowledgement resumes at the committed cursor. Original
redacted JSONL remains the read-only source recording, not a second new write
authority. No independent JSONL/SQLite dual-write success is claimed.
The internal storage format is `native-receipt-journal-1`; an existing unrelated
SQLite file or unknown storage version is refused before changing its mode or
schema. This is a new storage format, not a migration of historical trace indexes.

Only explicitly supplied native Trace v1 JSONL is supported. Callers must supply
already reviewed/redacted files; this reader is not a redaction gateway. It does
not import the native LangChain callbacks, traverse corpora, read caches or make
provider/model calls. One local worker owns a tailer/projection instance. SQLite
serializes transactions across connections, but a multi-worker service lifecycle,
authentication, storage quotas and a background scheduler are not implemented.

Each source ID binds an absolute path, filesystem device/inode, committed byte
offset, line number and SHA256 of the consumed byte prefix. Every poll rehashes
that prefix in bounded chunks before reading more. Incomplete final lines remain
unacknowledged. Malformed complete lines, overlong lines (default 8 MiB), changed
prefixes, truncation, rotation and missing files halt capture and record an issue.
Rotation requires an explicit new source ID; this reader never guesses a skipped
generation or silently clears an old gap. These issues are conservatively sticky
and block all storage snapshots; recovery/clearance policy is not yet implemented.
An ordinary partial line is visible in the poll result, not a permanent fault.
Source mutations between polls are detected on the next poll; the reader cannot
prove that an upstream producer captured all activity. Filesystem durability
ultimately depends on the host honoring SQLite's flush requests.

Event IDs and `(run_id, seq)` each bind immutable normalized event content.
Identical transport retries create exact origin receipts without duplicate
projection effects. Changed content under either identity is rejected before
cursor advancement. Source line bytes, byte ranges, line numbers and raw hashes
remain recoverable from receipts. Native self-hashes use the original producer's
JSON serialization. Separate event and receipt hash chains protect retained
ingestion order; `audit()` revalidates chains, receipt/event bindings and cursor
prefixes. These hashes detect corruption, not publisher identity or authenticity.

Per-run native stream state reports highest observed and contiguous sequence,
inclusive missing ranges and known chain-mismatch positions.
Missing positions and native chain mismatches remain visible; out-of-order arrival
can fill a sequence gap only in a later journal view. A fixed earlier journal
position never gains that later event. A restarted producer must use a new run
identity in this native-only slice; A's explicit stream IDs are not yet bound.

## Projection and readiness boundary

`Projection.advance` appends event rows and a narrow visible-text inventory:
captured model prompts/messages, visible model generation text and string tool
returns. It preserves event IDs, exact JSON pointers, text hashes and Unicode
code-point half-open spans. Unknown shapes stay in the raw event, with no guessed
semantic extraction. Reasoning blocks are not included in the text inventory.
The raw recording still contains its original privacy-filtered envelope.

This is **not a complete atomic semantic ledger**. There are no accepted claims,
support edges, report origins, completion inference or material dependencies.
`storage_snapshot` always returns `atomic_status=UNAVAILABLE` and
`ledger_ready=False`, even when `capture_state=PREFIX_AVAILABLE`. Lag, prefix
mismatch, missing streams, gaps and source faults yield `NOT_READY` with no rows.
No verifier or successful checkpoint response is fabricated by the service.

Snapshots bind a fixed journal position plus optional per-run watermarks. An
already advanced projection cannot serve an older prefix; use a fresh `replay`
for that prefix. Projection state is a disposable in-memory cache, rebuilt from
the durable journal after restart. Advances query only the unprojected suffix;
each cache binds the journal's persisted identity and returns detached rows so
clients cannot mutate retained projection state. No late source matching is performed: model
input text comes only from the captured input envelope, never later evidence.
Array/list order remains captured order; canonical projection rows sort by table
and stable ID. Incremental and full replay have byte-identical canonical rows at
the same journal prefix and projection version. This proves the declared surface
projection, not semantic completeness or historical ledger parity.

## Independent API and dependency questions

The native storage API is internal to this milestone, not a competing public
continuous-verification contract:

```python
service = CaptureService(new_journal_path)
service.ingest_trace("explicit-source-generation", reviewed_redacted_jsonl)
service.project()
snapshot = service.storage_snapshot(service.journal.watermark(), {"run-id": 3})
service.close()
```

Lane A candidate `continuous-verification-0.1` at `8eadcb1` was inspected read-only;
acceptance remains pending. Required next interfaces/decisions:

1. Accept/pin `validate_event`, `validate_checkpoint`, `verify(request, *,
   checkpoint, events, policy)` and the exact schema revision. How should native
   `run_id/seq` map to run/stream/producer positions without asserting missing
   capabilities? Native envelopes must retain their receipt provenance.
2. Register service-owned streams and coverage separately from agent assertions.
   A's candidate requires exact events `1..requested`, gap ranges, ingested and
   projected watermarks, and `SERVICE_ESTABLISHED` authority. The storage facade
   does not yet provide these public checkpoints or authentication.
3. Agree how raw-observation availability differs from atomic extraction and
   named procedural-check readiness. Native raw ingestion cannot claim all
   candidate semantic event types; adapters must supply reviewed observations.
4. Bind exact model-input/report/tool relationships to C's actual captured input
   observations. Do not synthesize exposure or report completion from timestamps,
   lexical presence, tool invocation alone or MCP connectivity.

## Verification and continuation

Authored temporary inputs only, Python 3.11 standard library:

```powershell
py -3.11 -S -B -m unittest tests.test_continuous_capture tests.test_continuous_projection -v
```

Current milestone: 26 tests pass (initial publication had 18). Controls cover partial Unicode lines, retries,
two identity collision forms, rollback/lost acknowledgement/restart, changed
files, missing/oversized/malformed inputs, sequence gaps/out-of-order arrivals,
source-chain mismatch, receipt corruption, multiple streams, projection lag,
fixed-prefix replay parity and no future evidence in earlier inputs.
Hardening adds actual subprocess exits before/after commit, refusal of unrelated
SQLite files without mutation, direct retry/cursor immutability, event/cursor
corruption, detached reads, journal isolation and suffix-only incremental reads.
Public event/checkpoint/verifier integration is **not run**, pending A acceptance.
There are no optional native/MCP integration dependencies in these tests and no
actual framework/model behavior claim.

Now: publish independent storage milestone and required interfaces. Next: finish
storage hardening while awaiting A, then bind public service/checkpoints only to
the accepted revision. Later: orchestrator integrates lanes and registers CI;
frontend, paid execution and independent quality evaluation remain deferred.

## Proposed stored-reference facade for C/D (not implemented or accepted)

Read-only inspection of D's `INTERFACES.md` and `sdk.py` confirms its provisional
`Backend.execute(operation, request) -> dict` seam and nine operations. B proposes
the facade below after corrected A acceptance. These operation DTOs reference
A's types; they do not replace A's event, checkpoint, policy, request or result
schemas. A `8eadcb1` is **not accepted**: orchestrator reproduced a future-parent /
causal-cycle packet with two PASS findings and requested repair. A's sibling
working tree is evolving toward 0.2; that is not a reviewed commit to import.

Trusted host construction, outside any request JSON:

```python
backend = ServiceBackend(store, principal, collector_bindings, accepted_contract)
backend.install_policy(run_id, accepted_A_policy)  # operator/policy-owner only
backend.record_coverage(run_id, stream_id, observations)  # trusted collector only
result = backend.execute(operation, request)  # D's unchanged dispatch seam
```

`principal` binds service identity, actor identity, permitted runs, operation
grants and collector stream/adapter assignments. Construction must fail without
these grants. D's preliminary `Access` allowlist does not establish B's actor or
object authority. `install_policy` and `record_coverage` are operator/collector
methods, **not** extra model tools. No public request accepts a local path,
arbitrary policy body, service authority, capability assertion or ledger watermark.
Actual external authentication remains host integration work; a JSON actor name
is never authentication. C needs separate collector and verification principals.

Proposed exact operation fields (reject unlisted fields; all have `run_id`):

| Operation | Additional request fields | Durable backend result |
| --- | --- | --- |
| `register_run` | `registration_id`, `expected_revision` (null for new run), `streams` list of `{stream_id, producer_id, adapter_version, redaction_profile}` | `run_id`, `registry_revision`, registered `streams`, declared coverage limits; no capture-completeness claim |
| `ingest_events` | `batch_id`, `events` list of accepted A event envelopes | `run_id`, `batch_id`, `receipt_id`, `events` list of `{event_id, receipt_position, status}` with ACCEPTED/DUPLICATE, and per-stream durable ingest/gap state |
| `checkpoint` | `checkpoint_id`, `revision`, `registry_revision`, `streams` list of `{stream_id, requested}` | Exact stored A checkpoint object; B supplies actual ingest/projection/gap/coverage and establishment fields |
| `verify` | Exactly A's accepted request fields, unchanged | Exact validated A result, retained immutably with the resolved evidence view |
| `get_assessment` | `assessment_id` | Exact retained A result; never a fresh assessment |
| `get_evidence` | `event_id`, optional `span` `[start,end]` | `run_id`, `event_id`, retained A `event`, optional `excerpt` plus validated Unicode `span`; origin preserved, no filesystem resolution |
| `acknowledge_feedback` | `acknowledgement_id`, `assessment_id`, `proposal_id`, `proposal_revision`, `delivery_event_id`, optional `acknowledgement_event_id` | `run_id`, `acknowledgement_id`, `receipt_id`, exact bound references and `status=RECORDED`; no correction or model-inclusion claim |
| `get_run_state` | No extra fields initially | `run_id`, `registry_revision`, per-stream observed/contiguous/projected watermarks and gaps, current source/capture issues, raw/procedural/atomic readiness separately |
| `list_events` | `after_cursor` (null initially), `limit` (integer 1..100) | `run_id`, `snapshot_id`, ordered retained `events`, `next_cursor` (null at pinned end), `has_more` |

These fields are a **proposal for orchestrator/C/D agreement**, not currently
accepted DTOs or callable success paths. Until implemented, all nine operations
remain unavailable on the present `CaptureService`; it exposes only native
ingest/project/storage_snapshot/close. No empty successful substitute is provided.

Registration and references:

- New run registration starts revision 0. Later collector-authorized registry
  revisions may append stream assignments, never silently remove or change
  existing streams. A producer restart requires a new stream ID. Checkpoint
  creation requires the current registry revision and the entire registered
  stream set, including required idle/unknown streams. Freeze that registry
  revision with the checkpoint; never infer complete coverage from observed IDs.
- Coverage comes from trusted configured collector observations with retained
  basis event IDs, not from `register_run` or an agent's checkpoint JSON. Missing
  capabilities remain UNKNOWN/NOT_CAPTURED. Submitted producer checkpoint
  observations do not become SERVICE_ESTABLISHED checkpoints.
- Every nested event/report/proposal/checkpoint/policy/assessment/delivery/basis
  reference must resolve to the authorized run before reading or writing. Denied
  or foreign references return FORBIDDEN without object contents; missing objects
  in an already permitted run return NOT_FOUND. Source and proposal revisions
  retain immutable identity bindings across the complete stored history.
- Policy lookup is by accepted A identity/version/digest against operator-installed
  policy. Verify resolves stored checkpoint ID/revision/digest and proposal/report
  references; request JSON cannot replace checkpoint coverage or policy content.
- Receipt batches commit atomically before acknowledgement. Exact `batch_id` retries
  return the original receipt; changed payload under that batch ID or changed event
  identity rejects the whole batch with CONFLICT. A new batch carrying an identical
  event produces a duplicate receipt without a second logical event. Sequence gaps
  remain observable, not a successful complete-prefix assertion.

Prefix and cache semantics:

- A service checkpoint freezes both requested per-stream positions and the durable
  ingestion view/registry revision in one transaction. All events 1..requested
  must be resolved in that frozen view; record actual missing ranges and worker
  lag rather than substituting the newest view. A premature checkpoint remains
  unready; retry it by its immutable ID or create a new revision to include later
  arrivals. Late evidence never repairs an old checkpoint or assembled input.
- Use deterministic `(stream_id, sequence, event_id)` view ordering, subject to
  A acceptance, while treating explicit causal parents as the only causal claims.
  Pin contract/extractor versions, ordered event digest, exact checkpoint, policy
  and request/proposal revision in the stored assessment. Changed input requires
  a new assessment binding; a read never recalculates history.
- Distinguish durable raw observations, visible-text projection, the minimal
  procedural records required by the selected A checks, and atomic semantic
  extraction. A scoped procedural assessment may eventually run with its declared
  prerequisites; it must not set atomic `ledger_ready` merely because it passed.
- First `list_events` call pins a server-side ingestion high-watermark and stable
  ordering; pages exclude subsequent appends. Opaque cursors resolve persisted
  journal/run/snapshot/position bindings and survive process restart. They grant
  no access. A foreign-run cursor is FORBIDDEN; a missing, malformed or unsupported
  cursor is INVALID_CURSOR. Initial implementation retains cursors (no silent
  expiry). Start a new null-cursor read to observe later appends.
- Acknowledgement records the authenticated actor's receipt of named feedback,
  with assessment/proposal/revision/delivery bindings validated. It cannot assert
  delivery, next-input inclusion or correction without their own retained events.
  The optional acknowledgement event must be a reviewed A lifecycle event with
  matching bindings. Capability/acknowledgement claims never rewrite failures.

Typed service failures (proposed): `ServiceError.code`, `.public_message`, and
optional bounded `.issues` with safe schema paths/codes. Allowlisted codes are
INVALID_REQUEST, FORBIDDEN, NOT_FOUND, CONFLICT, INVALID_CURSOR,
UNSUPPORTED_OPERATION and BACKEND_UNAVAILABLE. B must not import D's SDK to raise
them. D translates these to `InterfaceError`; its current envelope supports only
code/message, so `.issues` need a separately agreed extension. Unexpected failures
stay generic BACKEND_ERROR with no private paths, payloads or traceback. Valid A
NOT_READY/CAPTURE_GAP/ERROR results and per-check FAIL/INCONCLUSIVE/HOLD remain
unchanged successful invocations; no exception mapping converts them to PASS.

After corrected A acceptance, B can implement in order: service registry and
typed errors; transactional accepted-event receipts; frozen checkpoints with
collector-owned coverage; stored policy/request resolution and retained A results;
authorized reads/cursors; bound feedback acknowledgement. Proposed tables would
be added to the same isolated authoritative journal, with an explicit storage
version/migration and authored crash/replay tests. Native receipts remain native
provenance; no mechanical conversion asserts missing semantic observations.
The orchestrator must first pin A's corrected commit and agree these B-owned DTOs,
principal construction, coverage basis and error mapping with C/D.
