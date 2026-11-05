# Wire TradingAgents proposals to verification feedback and bounded recheck

Lane C. Updated 5 November 2026. Status: QUEUED; implementation chat being created.

Branch: `codex/tradingagents-feedback`, draft PR base: `codex/continuous-verification`.

Inspect pinned framework tool dispatch and safe resume boundaries; add a trusted instruction/tool adapter with observable proposal, finding delivery, next-input inclusion, revision or abstention, and recheck. Use authored offline responses for plumbing tests. Do not represent scripted behavior as an actual-model result or launch a paid smoke test.

Owned paths (new paths are proposed, not implemented): continuous_verification/tradingagents.py and prompts/; tests/test_continuous_tradingagents.py; docs/continuous/TRADINGAGENTS.md.

Dependency gate: Inspection and authored host tests can begin now. Integrated dispatch depends on lane A verify API and lane B checkpoint backend.

Read ../ORCHESTRATION.md and ../../CONTINUOUS_VERIFICATION_PLAN.md before implementation. Update this file with actual changed files, commands, tests, blockers and next action. Keep machine-specific state and full chat transcripts out of the repository. No paid model/provider calls, original-budget mutation, live run, trading, signing or on-chain operation. Do not merge or modify another lane's files.
