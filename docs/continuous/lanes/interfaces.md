# Expose one verification backend through SDK, CLI and MCP

Lane D. Updated 5 November 2026. Status: SCOPED LOCAL OFFLINE PARITY VERIFIED.
Branch: `codex/cli-sdk-mcp`; draft PR targets `codex/continuous-verification`.

## Implemented boundary

SDK Client.from_service wraps a trusted, already configured B ServiceBackend,
binds actual B.ServiceError and derives preliminary grants from its Principal.
The host retains service close responsibility. One dispatcher serves SDK, injected
cli.main and build_server(sdk). Official FastMCP stdio owns stdout; diagnostics
use stderr. Standalone CLI/MCP still return BACKEND_UNAVAILABLE for valid requests.
Database paths, profiles, policy installation, collector grants and coverage are
trusted host configuration; trusted setup methods are not exposed as tools.

All nine operation names are exercised, including B's explicit unsupported
acknowledge_feedback. Accepted A verify request/result validators and submitted
run/request/proposal/checkpoint/policy bindings are enforced. B validates other
DTOs and every nested stored-object/run reference. Findings, readiness, issues,
unknowns and policy disposition remain separate; invocation success is not PASS
or full decision clearance. No whole-session/hidden-reasoning claim is made.

## Accepted dependencies and owned changes

A source `e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2`, contract 0.2, imported exactly
from integration `29f038f9bd8210cf3793f6a1d0db7acd51e113ff`: package/contracts/
verifier/schema/example/two tests/CONTRACT.md. B source
`251b3b02c63e860020f94ce0b2962472eb0979fe`: capture.py, journal.py, projection.py,
service.py, test_continuous_capture.py, test_continuous_projection.py and CAPTURE.md
imported exactly. Neither owner's dependency implementation/tests/docs were edited.
No branch or PR was merged and no sibling checkout was written.

D-owned changes are sdk.py, cli.py, mcp_server.py, test_continuous_interfaces.py,
INTERFACES.md, this lane status and generated context/packaging metadata. Shared
README/orchestration/CI are unchanged; orchestrator handles shared current state,
CI registration and generated metadata conflicts.

## Verification evidence

- D dedicated suite: 22 tests. Official `mcp 1.30.0` isolated environment: all 22
  pass. Base Python3.11: 20 pass, 2 explicitly skipped for missing official MCP.
- `python -B -m unittest discover -s tests -p "test_continuous*.py" -q`:
  A29 + B49 + D22 = 100 tests. Official-SDK environment: 100 pass, no skips.
  Base environment: 98 pass, 2 explicit MCP skips.
- Actual accepted B SQLite service over temporary authored typed host data:
  SDK/injected-CLI/official ClientSession stdio parity across all operations.
  Six persisted scenarios: PASS, FAIL, unknown coverage/INCONCLUSIVE, lag/NOT_READY,
  CAPTURE_GAP and causal-cycle ERROR without binding/PASS. Results survive reopen.
- SDK/CLI and genuine MCP reject foreign nested event/assessment/checkpoint/policy/
  report/dependency references, stale digests, invalid/foreign cursors and
  model-issued coverage/path fields. B principal/assigned-collector denial holds
  despite broader SDK grants.
- Real MCP process appends a later event; a second MCP process resumes the same
  pinned snapshot cursor without the append. CLI restart parity also passes.
- Separate authored transport doubles remain labeled. No missing SDK integration
  is counted as PASS. Prior unchanged historical regression suites passed
  66 procedural-loop + 35 live-verification tests at the initial milestone.
- Exact dependency source comparisons, context build/check, packaging/export and
  staged diff checks are required before publication; generated metadata included.

Tests author only in-memory examples, temporary databases and trusted host scripts.
The integrated CLI boundary is trusted in-process injection, not a standalone
shell command opening a configured service. Official MCP stdio tests are genuine
protocol calls over the actual persisted core, not model/harness installation.

## Remaining scope and handoff

The reviewed local offline parity slice is complete. Detailed DTOs, permission and
safe error mapping, trusted host setup, read cursors and limitations are in
[INTERFACES.md](../INTERFACES.md). No dependency blocker remains for this slice.
Shared service lifecycle/launchers, per-harness installation and capture/gates,
native-to-typed host mapping and frontend remain separate work. Convenience
acknowledgement is intentionally unsupported; there is no daemon, network
authentication or complete semantic ledger. Report checks concern only the named
report event/ID/revision, not downstream decision truth.

No paid/provider calls, private corpus/history rebuild, budget/unknown-hold changes,
live experiment, trading, signatures or on-chain operations. Frontend and
independent quality evaluation remain deferred. PR stays draft; no merge.
