# TradingAgents feedback lane

Updated 5 November 2026. **A0.2 INTEGRATED OFFLINE; WAITING FOR REVIEWED B SERVICE.**
Branch `codex/tradingagents-feedback`; draft PR base `codex/continuous-verification`.

Accepted A dependency source `e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2`, integration
`29f038f`. Exact contract/init/verifier/schema/example/tests/doc copied without
edits (staged comparison to integration has no diff). A is no longer a blocker.

Changed C files: `continuous_verification/tradingagents.py`, its trusted prompt,
`tests/test_continuous_tradingagents.py`, this status doc and
[TRADINGAGENTS.md](../TRADINGAGENTS.md). Context index/manifest regenerated for
publication. Historical early commits: `b079882`, `3b7916a`.

Removed provisional binding/result types. Submission/results now validate A0.2
request/proposal/report identities and exact checkpoint/event/policy bindings.
Downstream paper proposals remain separate from referenced market-report events;
report advice cannot clear a decision. Explicit capture emits actual retained
model_input/tool_result/report events and feedback observations. Historical traces
without an assembly boundary remain UNKNOWN. Native completion/source status is
not promoted from a successful framework return.

Verified: C9 generic tests use accepted A core; C2 pinned native dispatch tests
use authored Runnable responses and real ToolNode, capturing ordinary/wrap-up
inputs and new report events. Combined A+C: 40 PASS in cached native environment;
stdlib-only: 38 PASS, native class SKIP. No actual-model inference or real B
service test. Native tests continue an invocation; no durable restart resume.

Prepared B callbacks: stored-reference `execute("verify", A_request)` and host
`execute("ingest_events", {run_id,batch_id,events})` with mandatory receipt
validation. Tests use an explicit authored service double; no real-core service
parity claim. No agent-controlled principal, registry, policy or coverage.

Concrete B needs: reviewed service commit; durable receipt DTO/errors/retry IDs;
exact returned checkpoint and ordered assessment event view/policy (or reviewed
authenticated equivalent); registry metadata matching C producer/adapter/profile;
assigned-collector grants and actual input/completion/coverage basis; confirmation
that explicit acknowledgement events ingest while acknowledgement transport is
UNSUPPORTED. See full API mismatches and event mapping in TRADINGAGENTS.md.

Next: stop at B review gate, then bind real receipt/view callbacks and splice/test
the named report boundary. Orchestrator handles README/orchestration/CI/generated
conflicts. No model/provider calls, budget mutation, private rebuild, live policy,
experiment, trading, signing, on-chain operation or merge. No sibling clone edits.
