# Supervised local asynchronous capture

Candidate on `codex/async-capture-portability`, based on merged foundation
`b365415f072eaf9d9b475662f56c7c7c441c6fc9`. Local only: no push, PR, merge,
daemon installation, automation, network, model, source or budget operation.
Owned files are `continuous_verification/async_capture.py`,
`tests/test_async_capture.py` and this document. Shared README/CI/index/manifest
updates belong to the orchestrator. Historical source branches remain preserved.

## Two explicit modes, one owner

`AsyncTraceCapture` can poll a supplied, already-reviewed/redacted native Trace v1
JSONL into the existing durable journal and visible-text projection. A growing
producer file is observed by a background thread; callers need not invoke poll.
This inventories externally recorded messages, prompts and tool returns. It does
not extract hidden reasoning or automatically turn arbitrary logs into semantic
claims, assembled model inputs, report boundaries or complete dependencies.

The same worker can accept **explicit A0.2 typed host-event batches** through the
existing ServiceBackend operations. It does not infer those events from native
inventory. Trusted host configuration, collectors, coverage, policies, nested
ownership checks, typed checkpoints and the verifier remain the accepted backend's
responsibility. With no trace path, the worker provides typed-host dispatch only.

The worker constructs ServiceBackend and its SQLite connection **inside one owner
thread**. Native receipts, source offsets, projection and typed requests are all
processed there, against the same existing SQLite authority. No event broker,
new event/checkpoint schema, second database authority or network service exists.
Do not open a concurrent direct backend writer against this database; use this
facade. Process-local ownership refuses a second worker for the same journal.
Cross-process ownership/leases are not implemented.

## Concrete API for D

```python
from continuous_verification.async_capture import AsyncTraceCapture
from continuous_verification.service import Principal

worker = AsyncTraceCapture(
    new_journal_path,
    source_id="explicit-native-source-generation", trace_path=reviewed_trace_path,
    principal=trusted_host_principal, service_id="local-reviewed-service",
    poll_interval=0.1, batch_lines=32, queue_size=16, project_on_poll=True,
)
with worker:                         # start; supervised stop on exit
    worker.configure_run(run_id, trusted_stream_assignments)
    worker.install_policy(run_id, accepted_policy)
    worker.execute("register_run", registration_request)
    committed = worker.submit("ingest_events", accepted_typed_batch)
    receipt = committed.result(timeout=2)
    worker.record_coverage(run_id, stream_id, trusted_observations)
    checkpoint = worker.execute("checkpoint", accepted_checkpoint_request)
    assessment = worker.execute("verify", accepted_A_request)
    exact_view = worker.resolve_view(accepted_A_request)
    native = worker.snapshot(include_rows=True)
```

Omit both source_id and trace_path for typed-host-only mode. `principal=None`
provides no typed operation/configuration grants. The principal and file paths
are trusted host construction inputs, never model request grants. Existing
ServiceBackend operation DTOs and results are unchanged. `submit(operation,
request)` returns a concurrent.futures.Future; `execute(operation, request,
timeout=2)` is the synchronous Backend protocol seam for the existing SDK.
Host-only `configure_run`, `install_policy`, `record_coverage` and `resolve_view`
retain their existing signatures plus optional timeout=2. All run on the owner.
No extra model tool grants collector authority or modifies policy.

`start(timeout=5)` returns self. `stop(timeout=5)` wakes and joins the owner,
closes SQLite on that thread, and returns final consistent metadata. A new object
restarts the same retained store; do not restart a stopped object. The thread is
non-daemon and must be supervised. Source faults latch while commands and reads
remain available. Unexpected worker failure exposes lifecycle=FAILED. After stop,
snapshot returns cached final metadata; request inventory rows while running.
Future callbacks must not block waiting on the same owner thread.

## Bounds, durability and timeouts

Each poll reads at most batch_lines complete receipts (32 default, maximum1000),
using the existing tailer's post-commit hook. The hook stops the batch **after**
durable commit; it never advances a cursor before commit or changes the historical
tailer. Partial final lines remain unacknowledged. Native source size defaults to
64MiB and line size to1MiB; bounds are configurable within explicit maxima.
Source identity, truncation, rewriting, hashes, immutable identities, retries and
gap handling remain the existing journal/tailer mechanisms. Source faults are
observable and sticky; no automatic gap clearance is introduced.

The bounded control queue defaults to16 commands (maximum256), each finite JSON
of at most1MiB. QUEUE_FULL means the command was not accepted. A submitted future
is **not** a durable acknowledgement: its result is supplied only after the real
backend operation returns from commit. A timeout can cancel an unstarted command.
If already running, COMMAND_TIMEOUT explicitly reports completion unknown; retry
the same immutable request/batch identity. Existing receipts preserve idempotency.
stop can leave unexecuted queued commands with NOT_RUNNING; it does not fabricate
acknowledgements. STOP_TIMEOUT means the old thread still owns SQLite and must be
joined before replacement. AsyncCaptureError has code/message; service exceptions
retain their existing ServiceError codes. No exception is converted into PASS.

`barrier(timeout=2, project=True)` performs **one bounded native poll** and a
projection update, returning state. It is not an unbounded file drain, an A
checkpoint or proof of a completed producer session. Repeatedly growing sources
cannot monopolize the worker indefinitely between commands. `snapshot(timeout=2,
include_rows=False)` returns durable line/byte/prefix-hash, journal and projection
positions, stream watermarks/gap ranges, unread bytes, fault code and poll state.
Requested rows are native visible inventory only, bounded to100 rows/1MiB; an
oversized response is explicitly omitted, never silently truncated as complete.

## Preserve frozen typed verification semantics

Native partial lines, unread bytes, gaps, source faults and projection lag make
native inventory NOT_READY. Native ledger_ready remains false and atomic_status
UNAVAILABLE in every outcome. native_to_typed_mapping is UNKNOWN_NOT_ASSERTED.
This is separate from accepted typed-host prerequisite readiness.

`execute(checkpoint/verify)` delegates unchanged to the accepted ServiceBackend.
Typed requested-stream watermarks, coverage and gaps determine its own
NOT_READY/CAPTURE_GAP/INCONCLUSIVE results. Latest native file state does **not**
globally override an existing typed checkpoint, assessment, cursor or idempotent
request, because no native-to-typed causal binding has been implemented. A retained
assessment remains identical after a late partial line or source fault. A host
may inspect a native barrier as its separate workflow action; this does not
silently alter core policy or imply captured semantic coverage. Late typed events
require a new checkpoint revision; they do not repair an old frozen view.

## Offline proof and remaining gaps

```powershell
py -3.11 -S -B -m unittest tests.test_async_capture -v
py -3.11 -S -B -m unittest discover -s tests -p 'test_continuous*.py' -q
```

Thirteen dedicated tests pass, all using authored temporary inputs: a growing
producer log updates inventory asynchronously; typed ingestion futures and SDK
verification share one owner/authority; source partial lines and projection lag
remain observable; native gaps and source faults never become complete semantic
inventory; typed gaps yield CAPTURE_GAP with no PASS; late native faults leave
retained typed results unchanged. Controls cover duplicate receipts, queue bounds,
cancelled/unknown completion, owner exclusion, actual subprocess exits before and
after commit, restart recovery, source rotation/truncation and source/line limits.
Root independently ran the reviewed13-test snapshot. Existing continuous suite:
115 pass,3 explicit optional dependency skips; skips are not integration PASS.

No generic native-to-typed converter, hidden reasoning access, exhaustive capture,
complete atomic semantic ledger, daemon, network authentication, installation or
arbitrary-harness compatibility is claimed. D's reviewed harness binding remains
separate. Missing host observations remain unknown; MCP calls alone cannot prove
whole-session capture. No private corpus build/history replacement, credentials,
budget/hold mutation or experiment execution is part of this slice.
