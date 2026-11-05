# Actual-model CLI feedback smoke — 5 November 2026

The owner authorized a retry and added GPT-6.1 Sol. Both real models demonstrated
the immediate integration milestone: model-generated verification call -> actual
injected CLI handler/result -> exact feedback in the next serialized request ->
visible provider continuation. Both later stopped at the source-round guard, so
the overall outcomes remain `STOPPED_NOT_PASS`.

| Observation | Terra medium | Sol medium |
|---|---|---|
| First request, IST |21:24:50 |21:26:50 |
| Turn1 |`verify_proposal` |`verify_proposal` |
| CLI result |Exit0, stored HOLD |Exit0, stored HOLD |
| Turn2 |Feedback present; `get_stock_data` |Feedback present; `get_stock_data` |
| Turn3 attempted action |`get_indicators` |`get_verified_market_snapshot` |
| Second source dispatch |Blocked by one-source-round guard |Blocked by same guard |
| Successful model responses |3 |3 |
| Input/output tokens |6,869 /256 |6,963 /204 |
| Conservative recorded charge |$0.0184525 |$0.036855 |

Source implementation was `5936caf`; indexed launch head was `fe636a3`. Runs used
the normally imported pinned TradingAgents market analyst/subgraph, medium effort,
automatic tool choice and the same frozen authored fixture. The initial complete
serialized request bodies match except for the model. Each arm allowed at most
four calls/120seconds with zero retries; they ran sequentially under the shared
cumulative $10 policy. No live source or trading operation was executed.

In both traces, event14 emits the model's verify call; event24 retains the actual
CLI-backed ToolNode return; event37 serializes the identical same-call feedback
into the next model request; event40 retains the provider's next action. The CLI
route is the real in-process parser with a trusted client, not an agent-issued OS
shell command. Each79-event runtime hashchain and exact SQLite parity passed
independent review, as did23 typed records, one stored assessment and monitor/raw
parity. Historical budget rows and both unknown holds remain unchanged. All six
new requests settled from captured usage; total conservative charge was
$0.0553075. This is project accounting, not a reconciled provider invoice.

The verified report was an explicitly authored omission seed. Required snapshot
FAIL plus seed report completion PASS produced HOLD; neither finding establishes
price truth or decision clearance. The prompts instructed verification; these
observations do not establish spontaneous tool use or a causal quality uplift.
Sol's later snapshot request was blocked, not executed/delivered evidence.

No corrected report or host recheck occurred. The result summary's `original=null`
reflects an unexecuted post-graph assignment; the CLI assessment itself is stored
and independently matches the delivered result. The minimal tool/feedback proof
must not be mistaken for a completed correction loop. This single authored case
does not support model superiority, full GraphSetup or arbitrary-harness claims.

Next: review the source-round allowance and final-report/resume boundary before
proposing another bounded corrected-report/recheck experiment. No additional paid
run, silent extension, automatic retry or replacement schedule is authorized.
Frontend and independent quality evaluation remain deferred. Private runtime
traces, model requests, approvals and budget evidence are excluded from export.
