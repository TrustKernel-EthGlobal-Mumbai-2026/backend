# Expose one verification backend through SDK, CLI and MCP

Lane D. Updated 5 November 2026. Status: ACCEPTED A0.2 VALIDATION BOUND;
persisted-core parity BLOCKED on reviewed B operation/service interfaces.

Branch: `codex/cli-sdk-mcp`, draft PR base: `codex/continuous-verification`.

## Scope and changed files

Owned: `continuous_verification/sdk.py`, `cli.py`, `mcp_server.py`,
`tests/test_continuous_interfaces.py`, `docs/continuous/INTERFACES.md`, this lane
doc and regenerated context/packaging metadata. Shared README/orchestration/CI
and other lane checkouts remain untouched.

The orchestrator accepted A source `e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2`,
contract `continuous-verification-0.2`, for SCOPED OFFLINE integration. Exact A
package/contracts/verifier/schema/example/tests/contract-doc dependencies were
imported from integration commit `29f038f9bd8210cf3793f6a1d0db7acd51e113ff`
without changes. No A implementation was edited. The earlier candidate rejection
for causality is historical; accepted A0.2 is no longer a dependency blocker.

## Implemented behavior

One shared dispatcher applies bounded finite JSON and explicit trusted
collect/read/verify/feedback permissions plus run scope. For verify it calls
accepted A request/result validators and rejects mismatched run/request or
request/proposal/checkpoint/policy digest bindings. Other operations still need
B-owned DTO validation. A host-injected ServiceErrorAdapter prepares B's proposed
typed exception seam using allowlisted codes and fixed public messages; its tests
are authored doubles, not a reviewed B import. Valid readiness, scoped findings, issues and disposition
remain structured results; process/transport success is not rule PASS.

CLI emits JSON errors and uses literal local request filenames; MCP takes inline
JSON and uses official FastMCP stdio, with no server-path resolution or sampling.
The optional dependency is `mcp>=1.28,<2`. Standalone invocation still returns
BACKEND_UNAVAILABLE for a valid request. No service factory, fixture-success
mode, independent verifier or replacement policy/checkpoint schema was invented.

## Commands and evidence

- `py -3.11 -B -m unittest discover -s tests -p test_continuous_interfaces.py -v`:
  15 passed; 1 explicitly skipped because optional MCP is absent.
- Isolated environment with official `mcp 1.30.0`, same interface suite:
  16 passed, including real subprocess stdio initialize/list/invoke for all nine
  operations and verify-schema rejection through the actual protocol.
- Imported accepted A suites: 10 contract + 19 verifier tests passed.
- Original transport milestone also passed 66 procedural-loop + 35
  live-verification regression tests; those unaffected historical modules have
  not been edited in this follow-up.
- Context index build/check, packaging generation, export scan and staged diff
  checks are required before each publication. Imported A files match the exact
  integration commit (empty source comparison after staging).

All new inputs are authored examples copied/mutated in memory or temporary host
files. Verify tests use accepted pure-core result fixtures, including PASS, FAIL,
NOT_READY, CAPTURE_GAP and causal-cycle ERROR with no binding/PASS. Other operation
results are explicitly generic transport doubles. These tests do not invoke a
persisted B service and do not establish actual core/transport parity.

## Remaining gate and next action

B's last inspected implemented CaptureService has storage operations only; its
newer ServiceBackend/Principal/DTO proposal is documented but unreviewed. Await a reviewed
stored-reference Backend.execute facade, trusted actor/service configuration,
B-owned DTO validators, typed safe errors, assessment/evidence access checks,
feedback acknowledgements and stable cursor semantics. The per-operation input/
result checklist and proposed error mapping are in [INTERFACES.md](../INTERFACES.md).
SDK run grants do not replace B's authorization of every referenced object.

Await orchestrator-reviewed B commit/API references, bind the real backend and
then test persisted SDK/CLI/MCP parity. Needed shared work remains service factory/
launchers, optional dependency declaration, CI, current-state updates and generated
metadata conflict resolution. No paid/provider calls, private corpus/history
rebuild, budget/unknown-hold changes, live experiment, trading, signatures or
on-chain operations; frontend and independent evaluation remain deferred.
