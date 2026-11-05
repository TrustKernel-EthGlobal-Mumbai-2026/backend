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

Per-run native stream state reports highest observed and contiguous sequence.
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
the durable journal after restart. No late source matching is performed: model
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

Initial milestone: 18 tests pass. Controls cover partial Unicode lines, retries,
two identity collision forms, rollback/lost acknowledgement/restart, changed
files, missing/oversized/malformed inputs, sequence gaps/out-of-order arrivals,
source-chain mismatch, receipt corruption, multiple streams, projection lag,
fixed-prefix replay parity and no future evidence in earlier inputs.
Public event/checkpoint/verifier integration is **not run**, pending A acceptance.
There are no optional native/MCP integration dependencies in these tests and no
actual framework/model behavior claim.

Now: publish independent storage milestone and required interfaces. Next: finish
storage hardening while awaiting A, then bind public service/checkpoints only to
the accepted revision. Later: orchestrator integrates lanes and registers CI;
frontend, paid execution and independent quality evaluation remain deferred.
