# Portable wheel and configured local host

Updated 5 November 2026. Branch `codex/portable-sdk-mcp`, based on merged main
`b365415`. This is a new delivery lane; merged PR #5 and its history are unchanged.
The Python package contains the existing reviewed local backend and transport
modules, accepted JSON schemas/example and trusted instruction resource. It does
not install TradingAgents, configure an account, run a model or fetch sources.

## Build and install

Python 3.11 or newer and standard wheel build tools are required. The base package
has no runtime dependencies. Official MCP support is optional: `mcp>=1.28,<2`.

```text
python -m pip wheel --no-deps . --wheel-dir wheelhouse
python -m venv isolated-env
isolated-env/bin/python -m pip install "wheelhouse/trustkernel_continuous-0.1.1-py3-none-any.whl[mcp]"
```

On Windows use `isolated-env/Scripts/python.exe`; installed commands are beside
that interpreter. For offline builds, preinstall setuptools>=68 and wheel>=0.45
and add `--no-build-isolation`. For offline installation use `--no-index
--find-links <reviewed-wheelhouse>` with platform-compatible dependency wheels.
Only the TrustKernel wheel is platform-neutral; dependencies need their own
compatible wheels. No Docker, PyPI upload or public release is part of this work.

Version 0.1.1 adds the accepted async module and minimal shared-owner binding.
The wheel includes `continuous_verification` only, with `schemas/*.json` and
`prompts/*.md`. Historical corpora, repository tools/tests, caches, personal paths
and existing virtual environments are not package dependencies. A source checkout
or PYTHONPATH is unnecessary after installation. A distribution license has not
been selected by this packaging change.

## Existing service: no bootstrap or collector grant

An operator explicitly selects an existing local database, preferably an isolated
copy rather than an original research store, and a run allowlist. No initialization,
policy body, stream registry, collector identity or configure/collect grant is
required. [Authored profile example](../../examples/portable_host/existing-host.json):

```json
{
  "config_version": "trustkernel-host-1",
  "mode": "existing",
  "database": "copied-journal.sqlite",
  "service_id": "authored-service",
  "client_id": "authored-reader",
  "run_ids": ["authored-run"]
}
```

Database paths are absolute operator-selected local paths or relative to the
configuration file. Missing files, network/URL paths, symlink database files and
unrelated/unsupported database formats fail; the host does not create a missing
database in existing mode. The accepted B service audits/opens the selected store;
it is not an OS read-only SQLite connection because verification and cursors retain
new service records. Existing profiles cannot initialize or obtain collector_session.
The root's private-copy/harness test is separate; this lane never reads that data.

```text
trustkernel --config existing-host.json verify --request exact-retained-request.json
trustkernel --config existing-host.json get_assessment --request assessment-request.json
trustkernel-mcp --config existing-host.json
```

The verification body is the exact accepted A0.2 request, including immutable
proposal/report/checkpoint/policy bindings. It resolves existing stored references;
the host invents none. The configured CLI returns the same result as the SDK and
MCP. A retained FAIL/HOLD remains FAIL/HOLD. A bare successful invocation is never
decision clearance. Missing request references return explicit errors.

## Optional new empty host

[new-host.json](../../examples/portable_host/new-host.json) is an explicitly
authored operator example. Copy it into a new directory, review identities, run
registry and policy, then initialize intentionally:

```text
trustkernel --config new-host.json init
trustkernel --config new-host.json get_run_state --request run-state-request.json
```

New mode chooses a new direct child state directory beside its configuration.
Initialization never overwrites an existing directory. It configures/registers
the explicit streams and policy, seeds **zero observations**, and leaves coverage
UNKNOWN and semantic readiness false. It creates no successful assessment or
default evidence. Partial setup remains for operator inspection; it is never
deleted/reused automatically. The initialized state binds the exact configuration
digest; editing it does not silently grant a new identity/policy/stream set.

Run/stream configuration and policy installation belong to initialization's
trusted operator. For a new-mode host, separate trusted Python collector code may
use `collector_session(config_path)` to submit accepted A events, record actual
coverage observations and establish checkpoints. It has collect permission only,
no configure/read/verify grant. It is not a native trace mapper or background loop.
Only a reviewed host adapter may assert assembled-input/phase/completion coverage;
raw text presence or MCP connectivity cannot establish it.

## SDK and least-privilege MCP surface

```python
from continuous_verification.host import client_session

with client_session(operator_config_path) as sdk:
    response = sdk.call("verify", exact_request)
    # Inspect response.ok and the independent readiness/findings/disposition.
```

The trusted client principal always has **verify/read**, restricted to configured
runs. Model arguments cannot select a database/configuration, module loader,
policy installation, profile, collector grant or coverage assertion. SDK collect
and feedback mutations are denied. The configured MCP server advertises only:

- verify
- get_assessment
- get_evidence
- get_run_state
- list_events

Each tool takes one inline request object. There are no init/configure/ingest/
checkpoint/coverage tools. Unknown registry/path/authority fields are rejected by
the accepted operation schema; all nested stored references remain run-scoped.
MCP stdout is protocol only; startup/configuration diagnostics go to stderr.
Missing config fails, including an empty MCP stdout before serving. Structured
service errors use `ok=false`; MCP `isError=false` alone is not application success.
CLI exit 0 may accompany FAIL/HOLD/NOT_READY because it reports result delivery.

Host configuration and command/args are operator-owned startup inputs, not model
tool arguments. Give another harness the absolute installed `trustkernel-mcp`
executable and `args=["--config", "/absolute/operator-profile.json"]`. Use argument
arrays without a shell. This is a candidate command interface, not a claim of
tested installation in every agent. Root owns the installed-Codex harness check
and any per-invocation settings; this lane changes no global harness configuration.

## SQLite ownership and accepted shared runtime

All service creation, calls and close run on the existing C.LocalServiceWorker's
single owner thread. This is reuse of the reviewed host bridge, not another
collector or event schema. A client_session owns and closes its worker. Separate
collector_session and client_session examples are **sequential**, not concurrent
writers on one store. The configured standalone host is not a daemon or shared
network service and supplies no network authentication.

Accepted B source `4e46e2d9bd6b58756214f788f4724ef087691d9f` was imported by
cherry-pick without editing its async_capture.py, test_async_capture.py or
ASYNC_CAPTURE.md. Root independently reviewed its 13 tests and single-owner,
bounded-command and durable-future behavior before this binding.

For a new-mode initialized host, use one runtime for the producer and client:

```python
from continuous_verification.host import runtime_session

with runtime_session(operator_config_path) as runtime:
    receipt = runtime.collector.submit("ingest_events", accepted_batch).result(timeout=3)
    # A completed Future contains the actual durable B receipt, not enqueue success.
    state = runtime.client.call("get_run_state", {"run_id": allowed_run})
    result = runtime.client.call("verify", exact_checkpoint_bound_request)
```

One AsyncTraceCapture owns SQLite. Its trusted host Principal has collect/verify/
read, while the agent-facing Client Access is verify/read only. This is explicit
local delegation on the same owner, **not a separately authenticated agent** or
an OS/process sandbox. The trusted runtime object is not a model tool argument.
The runtime cannot install policy or configure runs; initialization remains
separate. Default typed coverage is UNKNOWN until actual trusted observations
are recorded. Capture/read success does not create semantic readiness.

Optional source_id and trace_path are trusted Python-only runtime_session keyword
arguments and must be supplied together. No CLI/MCP request selects a source path.
Native visible-text inventory is not automatically mapped into A events, assembled
input or coverage; ledger_ready remains false for that inventory. B's submit,
execute, snapshot, bounded barrier and stop semantics are preserved. A timeout
is not acknowledgement; use immutable request IDs and retained state when completion
is unknown. Context exit calls stop(), not close(). Do not open another worker
on this database concurrently; use runtime.client on this same owner. Existing-copy
client_session remains unchanged and independent for the root's harness test.

## Verification and review evidence

```text
python -B -m unittest discover -s tests -p test_portable_host.py -v
```

Six host tests cover shared-owner durable Future submission/restricted reads,
empty/UNKNOWN initialization, missing config/state, exact
persisted FAIL/HOLD, separated grants, foreign/profile injection rejection,
existing copied-store behavior and multi-threaded callers through the one owner.
An additional installed-wheel acceptance test is explicit: without artifact paths
it is **skipped/unexecuted**, not PASS. Supply `TRUSTKERNEL_TEST_WHEEL` and
`TRUSTKERNEL_TEST_WHEELHOUSE` to execute it. Both paths are test-runner/operator
configuration, not product tool arguments.

That test creates a clean venv outside the repository, installs the base wheel
without dependencies and imports it without MCP, then installs the MCP extra
offline. An external `python -I` script runs with no PYTHONPATH, loads packaged
schema/prompt resources, invokes the installed CLI and actual official SDK
ClientSession subprocess against `trustkernel-mcp`, and compares the real
persisted FAIL/HOLD. It verifies five-tool discovery, denied collector/foreign
references, path-field rejection, restart-stable pinned cursors after a later
append, missing-config stdout discipline and an unchanged original authored
store while operating on its copy. All data is authored and temporary.

Observed on this branch: all **7 portable tests passed** with the wheel/wheelhouse
supplied. Without those explicit artifacts, 6 host tests passed and the clean-
install test was explicitly skipped. Existing continuous regression suite: 118
tests, 117 passed and the optional native framework class explicitly skipped in
the official-MCP environment. No missing optional integration is counted as PASS.

Build/test dependencies were found in the local pip cache; the build does not
require an existing project venv at runtime. The acceptance result and exact wheel
hash are recorded in the private portable-sdk-mcp status. Official SDK and package
metadata references checked 5 November 2026:
[MCP v1 documentation](https://py.sdk.modelcontextprotocol.io/v1/),
[setuptools pyproject configuration](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)
and [package data](https://setuptools.pypa.io/en/stable/userguide/datafiles.html).

Root owns shared README/index/manifest and CI registration. No model/provider/
source fetch, sampling, original private database access, budget/unknown-hold
change, live research experiment, trading, signature, on-chain operation, global
connector setting, public release or merge is authorized by this packaging work.
