# Expose one verification backend through SDK, CLI and MCP

Lane D. Updated 5 November 2026. Status: QUEUED; implementation chat being created.

Branch: `codex/cli-sdk-mcp`, draft PR base: `codex/continuous-verification`.

Build thin schema-bound SDK, CLI and MCP wrappers with equivalent readiness, scoped findings, errors and read cursors. Test genuine MCP discovery using the official SDK when dependencies are available; label missing integration explicitly. Document harness capture and gating limits. Never substitute canned success for actual verification.

Owned paths (new paths are proposed, not implemented): continuous_verification/sdk.py, cli.py and mcp_server.py; tests/test_continuous_interfaces.py; docs/continuous/INTERFACES.md.

Dependency gate: Transport design and explicit test doubles can begin now; integrated parity requires lane A contracts and lane B service. Do not implement a second verifier or a homegrown MCP protocol.

Read ../ORCHESTRATION.md and ../../CONTINUOUS_VERIFICATION_PLAN.md before implementation. Update this file with actual changed files, commands, tests, blockers and next action. Keep machine-specific state and full chat transcripts out of the repository. No paid model/provider calls, original-budget mutation, live run, trading, signing or on-chain operation. Do not merge or modify another lane's files.
