# Expose one verification backend through SDK, CLI and MCP

Lane D. Updated 5 November 2026. Status: TRANSPORT SLICE IMPLEMENTED;
real-backend integration BLOCKED on orchestrator acceptance and lane B service.

Branch: `codex/cli-sdk-mcp`, draft PR base: `codex/continuous-verification`.

Build thin schema-bound SDK, CLI and MCP wrappers with equivalent readiness, scoped findings, errors and read cursors. Test genuine MCP discovery using the official SDK when dependencies are available; label missing integration explicitly. Document harness capture and gating limits. Never substitute canned success for actual verification.

Owned paths (new paths are proposed, not implemented): continuous_verification/sdk.py, cli.py and mcp_server.py; tests/test_continuous_interfaces.py; docs/continuous/INTERFACES.md.

Dependency gate: Transport design and explicit test doubles can begin now; integrated parity requires lane A contracts and lane B service. Do not implement a second verifier or a homegrown MCP protocol.

## Published transport slice

Changed: `continuous_verification/sdk.py`, `cli.py`, `mcp_server.py`,
`tests/test_continuous_interfaces.py`, `docs/continuous/INTERFACES.md`, this lane
status and regenerated context/packaging metadata.

One shared operation dispatcher applies bounded finite JSON and explicit trusted
operation/run grants. CLI JSON errors/exit classes preserve scoped backend results.
Official FastMCP provides nine stdio tools with inline JSON, no server-path
argument, no sampling/model call. Standalone CLI/MCP default to unavailable
backend; no successful fixture assessment is offered in production invocation.

Commands/results:

- `py -3.11 -B -m unittest discover -s tests -p test_continuous_interfaces.py -v`:
  10 passed; 1 explicitly skipped (optional official MCP missing).
- Isolated test environment, same command with its Python, official `mcp 1.30.0`:
  11 passed, including actual subprocess stdio initialize/list/invoke for all
  nine tools with an authored backend and default unavailable backend.
- JSON CLI subprocess safely handles a temporary filename with spaces and shell
  metacharacters; no constructed shell command.
- Portable regression suites: 66 procedural-loop and 35 live-verification tests
  passed. Context index build/check, packaging manifest generation, export scan
  and `git diff --check` passed before publishing.

These are transport tests. The authored backend is explicitly labeled; mixed
NOT_READY/FAIL/HOLD results do not constitute a real assessment. Detailed risks,
acceptance checks, dependency/version declaration and candidate harness limits
are in [INTERFACES.md](../INTERFACES.md).

## Gate and next action

A's candidate has pure validation/verification functions; acceptance/pinned API
has not been relayed. B's inspected storage facade has no verify/checkpoint-success
operation yet. The provisional `Backend.execute(operation, request)` seam is
transport scaffolding, not a frozen competing DTO/service contract.

Orchestrator follow-up: A is explicitly NOT ACCEPTED while a reproduced causal
ordering/cycle defect is repaired. INTERFACES.md now includes an operation-by-
operation B input/result checklist and proposed safe error mapping. Those are
review requests, not accepted schemas or implemented B behavior.

Await orchestrator follow-up with accepted A/B references. Then bind domain
validation, stored checkpoint/policy/event resolution, scoped reads and cursor
semantics, and rerun parity over the actual service. No integrated parity or
harness capture/gate claim is made now. Needed shared work: service factory and
launchers, optional dependency registration, CI and current-state updates;
orchestrator owns those files. No other lane checkout has been modified.

Read ../ORCHESTRATION.md and ../../CONTINUOUS_VERIFICATION_PLAN.md before implementation. Update this file with actual changed files, commands, tests, blockers and next action. Keep machine-specific state and full chat transcripts out of the repository. No paid model/provider calls, original-budget mutation, live run, trading, signing or on-chain operation. Do not merge or modify another lane's files.
