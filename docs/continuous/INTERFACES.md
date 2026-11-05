# SDK, CLI and MCP over the reviewed local service

Updated 5 November 2026. Implemented and tested for **scoped local offline use**:
one operation set over the accepted A0.2 verifier and B persisted service, with
SDK, trusted in-process CLI injection and official MCP SDK subprocess stdio parity.
Standalone CLI/MCP still have no service factory and fail BACKEND_UNAVAILABLE for
a valid request. No harness configuration, daemon or native-trace converter exists.

## Accepted dependencies and scope

The orchestrator accepted A source `e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2`,
contract `continuous-verification-0.2`, from integration
`29f038f9bd8210cf3793f6a1d0db7acd51e113ff`. Exact reviewed A package/contracts/
verifier/schema/example/tests/contract-doc files were imported without edits.
B source `251b3b02c63e860020f94ce0b2962472eb0979fe` is accepted for scoped local
offline integration. Its capture/journal/projection/service, two test files and
CAPTURE.md were imported without edits. See [B's service contract](CAPTURE.md).
No merge or modification to another lane's implementation was performed.

The earlier rejected A causality candidate remains historical. Accepted A0.2
returns ERROR/CAUSALITY with no binding/PASS for that negative control. Its report
checks concern proposal.report_event_id + report_id + report_revision, not
downstream decision truth. Registered-stream completeness, authenticated collectors,
coverage declarations and actual model-input assembly remain host/service obligations.

D owns sdk.py, cli.py, mcp_server.py, test_continuous_interfaces.py and this document.
The modules create no policy defaults or independent verifier. Reverting the D
transport modules leaves B storage and historical artifacts intact.

## Trusted host wiring

`Client(backend, access).call(operation, request)` is the shared operation boundary.
The real backend is `ServiceBackend.execute(operation, request) -> dict`. B owns
operation DTO validation, durable mutations, stored-reference resolution and
nested-object authorization. D additionally validates accepted A requests/results
for verify and rejects mismatched run/request IDs and request/proposal/checkpoint/
policy digest bindings. D never invokes A's pure verifier instead of B.

```python
from continuous_verification.service import Principal, ServiceBackend
from continuous_verification.sdk import Client
from continuous_verification.cli import main as cli_main
from continuous_verification.mcp_server import build_server

# These variables are trusted operator configuration, never model arguments.
principal = Principal(actor_id, frozenset(permissions), frozenset(authorized_runs))
backend = ServiceBackend(operator_database_path, principal=principal,
                         service_id=operator_service_id)
sdk = Client.from_service(backend)
# Choose one owner/lifecycle at a time; always close the backend after use.
# sdk.call(operation, inline_request)
# cli_main(command_arguments, client=sdk)
# build_server(sdk).run(transport="stdio")
```

Client.from_service wraps an already configured reviewed B instance, binds its
actual ServiceError class and derives preliminary grants from its trusted Principal.
The host retains close responsibility. This code constructs no fixture-success
service and imports no model-selected module. A trusted operator must first configure the immutable run/stream registry
and install policy using B's configure permission. Assigned collectors establish
coverage through record_coverage. Those host methods, explicit projection and
resolve_view are not MCP tools or CLI operations. A client cannot supply a local
database/trace path, install policy, grant itself coverage or choose a collector.

Access permission/run sets default empty and are host-injected. They are a
preliminary allowlist, not authentication. B independently checks its Principal,
collector assignment and ownership of every referenced checkpoint, policy,
assessment, event and dependency. Broader SDK grants cannot bypass B's principal.
The local single-worker service is not a remotely authenticated deployment.

## Shared operations

Every request has an explicit run_id. Unexpected operation fields are rejected
by B. Permission names below match the accepted service.

| Operation | Permission | Exact input/result boundary |
|---|---|---|
| register_run | collect | {run_id,registration_id}; activates only trusted preconfigured registry |
| ingest_events | collect | {run_id,batch_id,events:[A]}; durable receipt/idempotent retry |
| checkpoint | collect | {run_id,checkpoint_id,revision,registry_revision:0,streams:[{stream_id,requested}]}; exact stored A checkpoint |
| verify | verify | Exact accepted A request; exact retained A result resolved from stored references |
| get_assessment | read | {run_id,assessment_id}; exact retained result |
| get_evidence | read | {run_id,event_id,span?}; retained event/provenance and bounded Unicode excerpt |
| get_run_state | read | {run_id}; actual watermarks/gaps/coverage; atomic_semantic_ready=false |
| list_events | read | {run_id,after_cursor:null|string,limit:1..100}; pinned snapshot, events, next_cursor, has_more |
| acknowledge_feedback | feedback | Explicit UNSUPPORTED_OPERATION; use separately captured lifecycle events |

No tool accepts arbitrary server-file reads. CLI alone accepts an operator-local
request file; its JSON is subject to the same operation schema. Native capture
paths remain trusted operator configuration, never a get_evidence fallback.

D preserves stable run/proposal/checkpoint/assessment/event IDs and treats cursors
as opaque. The first list_events request pins a persisted snapshot. Continuations
survive restart and exclude later appends. next_cursor=null and has_more=false
explicitly end the snapshot; a new null-cursor request observes a later view.
Foreign-run cursor is FORBIDDEN; invalid cursor is INVALID_CURSOR. No expiry or
compaction is implemented. D does not invent empty pages or rewrite bindings.

## Results, errors and execution boundaries

Invocation success is {"ok":true,"result":<unchanged backend object>}. Inside the
result, readiness, per-rule PASS/FAIL/INCONCLUSIVE, issues, policy disposition,
unknowns and bindings retain their independent meanings. A valid core ERROR,
NOT_READY, CAPTURE_GAP, HOLD or RECHECK remains a result, never clearance.

Transport/service failures are {"ok":false,"error":{"code":...,"message":...}}.
ServiceErrorAdapter is bound to actual B.ServiceError by trusted host code.
INVALID_REQUEST, FORBIDDEN, NOT_FOUND, CONFLICT, INVALID_CURSOR,
UNSUPPORTED_OPERATION and BACKEND_UNAVAILABLE map to fixed safe messages.
Unknown/unadapted exceptions become generic BACKEND_ERROR. Raw public_message,
service issues, paths and tracebacks are not echoed. Core result issues are
preserved; adding structured service-error issues requires a separate reviewed
extension. Invalid verify inputs use INVALID_REQUEST; malformed/foreign/stale
verify results use BACKEND_ERROR.

Requests/results must be finite string-keyed JSON within 1 MiB and 32 nested
levels. Duplicate JSON keys, nonfinite values, invalid Unicode and unsupported
Python objects are rejected. A transport/result failure does not establish that
a durable mutation rolled back; retry immutable operation/batch identities and
read retained state instead of creating new identities on an uncertain response.

```text
python -B -m continuous_verification.cli verify --request "proposal request.json"
python -B -m continuous_verification.cli list_events < event-request.json
```

Standalone commands have no configured backend and return BACKEND_UNAVAILABLE.
The tested integrated CLI boundary is cli.main(..., client=sdk), not an installed
shell command silently opening a service. Normal invocations emit one JSON object
on stdout and diagnostics on stderr. Exit 0 means a backend result, 2 means
argument/input validation failure, and 3 means service/authorization/execution
failure. Callers inspect JSON; FAIL or HOLD can accompany exit 0. --help is human
readable. Request filenames are opened literally; spawning callers should use
argument arrays with shell disabled. A leading-dash path can use --request=<path>.

## Official MCP SDK and capture limits

Optional dependency: **mcp>=1.28,<2**, checked at startup; tested version **1.30.0**.
This uses the documented v1 FastMCP API, not a homemade protocol. References:
[official v1 SDK documentation](https://py.sdk.modelcontextprotocol.io/v1/) and
[official stdio client example](https://github.com/modelcontextprotocol/python-sdk/blob/main/examples/snippets/clients/stdio_client.py),
checked 5 November 2026. Install optionally in an isolated environment.

```text
python -m pip install "mcp>=1.28,<2"
python -B -m continuous_verification.mcp_server
```

The standalone server exposes the same tools but has no backend. Trusted hosts
use build_server(sdk). Each tool has one inline request object. Stdout belongs
exclusively to SDK stdio protocol; diagnostics use stderr. Missing/unsupported
SDK exits 3 before serving. Structured application failures are returned inside
MCP content with ok=false; MCP isError=false alone does not mean success. There
are no resources, sampling/model calls, connector changes or dynamic imports.

No Claude Code/Desktop, Codex, Hermes, OpenClaw or TradingAgents harness was
installed or configured here. Their access routes remain candidates until tested
against the specific runtime. MCP sees its own requests, not a whole session,
hidden reasoning, later model-input inclusion or an enforced host action gate.
No complete semantic ledger or native-trace-to-typed mapping is inferred.

## Verification evidence

```text
python -B -m unittest discover -s tests -p test_continuous_interfaces.py -v
python -B -m unittest discover -s tests -p "test_continuous*.py" -q
```

Dedicated D suite: **22 tests**. Base Python3.11: **20 passed, 2 explicit skips**
for genuine MCP tests when the optional SDK is absent. Official mcp 1.30.0 isolated
environment: **22 passed**. All continuous suites total **100 tests**: A29 + B49 +
D22. The base environment passed 98 and explicitly skipped 2; the isolated
official-SDK environment passed all 100 with no skips. Optional SDK skips are
not counted as MCP PASS.

The older transport-double tests remain labeled and separate from
PersistedInterfaceTests and the genuine persisted MCP test. New integration tests
use the accepted public authored example, copied/mutated in memory, temporary
SQLite databases and temporary trusted host scripts. They do not use private
history, native source/model execution or account data.

| Risk/behavior | Observed test boundary |
|---|---|
| Exact persisted results across all transports | SDK + injected CLI + actual official ClientSession stdio over B, all nine operations including unsupported acknowledgement |
| Readiness/findings/errors flattened into success | Six persisted scenarios: PASS, FAIL, unknown coverage/INCONCLUSIVE, projection lag/NOT_READY, CAPTURE_GAP and causal-cycle ERROR with no binding/PASS |
| Foreign nested objects or stale references | Actual SDK/CLI and MCP deny foreign assessment/evidence/checkpoint/policy/report/dependency refs and stale stored digests |
| Model-controlled authority/files | Unexpected registry/coverage/checkpoint/path fields rejected; no configure/policy/coverage tools exposed |
| Collector/run grants bypassed | Actual B Principal and assigned collector enforce denial despite broader SDK grants |
| Cursor admits late evidence or fails after restart | Pinned cursor excludes later append through CLI and real MCP; a second MCP process resumes the same retained snapshot |
| Old failures disappear | Exact retained assessments survive reopen in all six scenarios |
| Missing service/dependency becomes a fake PASS | Standalone CLI/MCP fail unavailable; dependency absence explicitly skips genuine tests |

The 66 procedural-loop and 35 historical live-verification regression tests passed
at the initial transport milestone; those modules remain unchanged. Index,
packaging, export and diff checks are regenerated before publication. Central
README/orchestration/CI and generated-conflict integration remain orchestrator-owned.

The scoped local offline parity gate is complete. Remaining work is shared
launcher/service lifecycle and deployment configuration, specific harness coverage/
gates, native-to-typed host provenance where supported, and later frontend work.
No paid/provider call, original corpus/history rebuild, budget/unknown-hold change,
live experiment, trade, signature, on-chain action or independent quality evaluation.
