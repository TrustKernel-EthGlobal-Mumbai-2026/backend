# Checkpointed report correction experiment

Candidate implementation on `codex/correction-experiment`, based on `39e0e1c`.
The old smoke, core, upstream and main are unchanged. Root owns shared metadata,
fresh source capture, operational reviews and paid launches. This lane performs
offline implementation and authored tests only. The B source API shape is known;
its immutable implementation must be accepted and bound before paid loading.

The user authorized seven minutes each for Terra and Sol, fresh read-only market
and news, and testing whether the model uses CLI checkpoint feedback procedurally.
There is no guarantee of a failed first report or a successful correction.

## Protocol and time

One invocation runs one arm, sequentially under root control. The supervised
parent records one start/deadline clock. The observation window ends 420 seconds
after that start, including setup. The supervisor permits five additional seconds
for closing/auditing artifacts only; inference is forbidden during that grace.
No model request starts without its full 30-second request allowance remaining.

| Phase | Slot or bound | Model/source allowance |
|---|---|---|
| Initial research and actual report revision 0 | By 180 seconds | At most 6 model requests, 5 distinct captured source queries |
| Model-requested CLI checkpoint 0 | At 180 seconds | 1 request from the remaining 5-call pool; host binds the actual report/checkpoint, then offers argument-free `verify_proposal` with auto choice |
| Finding feedback and actual revision 1 | By 330 seconds | Up to 2 source queries and a model report, retaining the final request for recheck |
| Model-requested CLI checkpoint 1 | At 350 seconds | Final request offers verification of the newly bound report/checkpoint |
| Completed-protocol observation | Until 420 seconds | No filler model/source calls |

Checkpoint waits and completed observation are declared scheduled waits, recorded
separately from measured model invocation durations, setup, and total observation
time. Offline tests simulate this schedule without a real seven-minute wait.
Paid mode uses real time. STOP, timeout, provider errors, new unknown usage,
exhausted bounds or missing required behavior can end early with a partial outcome.
This protocol does not claim continuous model reasoning or access hidden thoughts.

Only an actual model-generated `verify_proposal` call through native ToolNode
executes `continuous_verification.cli.main(["verify"], client=..., stdin/stdout=...)`.
The host creates and binds reports/checkpoints, grants and backend; the model
cannot supply these values. The CLI is an injected in-process parser/SDK route,
not an OS shell command or CLI transport subprocess. No host-only fallback counts
as agent CLI use. No report means no seed, proposal or verifier invocation.

## Source scope and context

The normal pinned TradingAgents market analyst and actual native ToolNode execute
with the original market/news schemas. This is a market analyst offered native
news access, not full GraphSetup or a separate news analyst evaluation.
Both arms replay the same root-captured, approved B manifest and exact native text.
Nothing fetches fresh sources inside the model process; replay is not continuously
live. Capture clocks, query/date/timezone, references, coverage, gaps and status
remain explicit in B's manifest and host trace.

The declared initial catalog is stock data (60 calendar days), RSI and MACD
(each one exact query, lookback 10), verified snapshot (10 rows), and ETH news
(7 days). One indicator plus stock, snapshot and news leaves room for a report;
the second indicator is optional. Global news and close_200_sma stay in the raw
bundle but are outside this model catalog. Correction may use the existing
history and one RSI plus one snapshot query. Duplicate queries within a phase
stop rather than imply new evidence. Dates/defaults are not silently rewritten.
Unsupported phase/query arguments stop explicitly; no fake source return is made.

Native ToolMessage success proves a string returned. The snapshot counts as
SUCCESS only when B's exact full-argument replay record has both status and
source_status AVAILABLE, joined to that intact model call ID. Unavailable,
NO_DATA, argument mismatch and invocation errors remain distinct source records;
model omission is a separate behavior. The existing policy checks only required
snapshot inclusion and report completion, never price truth, TTL or global quality.

Combined-envelope preflight serializes planned histories with actual captured
strings and declared maximum report/assessment/commentary padding through the
actual SDK and a local HTTP override. It measures both the 40,000-byte wire bound
and original Budget's 50,000-byte messages/metadata envelope. Research, full
feedback/correction and revised-report recheck shapes are checked. Oversize blocks
the arm before reservation. This estimate is a fitting gate, not model behavior.
Runtime independently checks every actual serialized envelope and stops on overflow.
Raw source artifacts remain outside the model context; nothing is silently
summarized or truncated. Report and assessment continuation limits are 4,096 UTF-8
bytes each, visible tool commentary 512 bytes, output at most 2,048 tokens/request.
An oversized actual report/assessment remains retained but cannot be used to force
a continuation through a smaller envelope.

## Immutable report, feedback and recheck

The first report comes from the actual model, with observed COMPLETE, TRUNCATED
or UNKNOWN completion and its own assembled-input reference. It is closed and
bound before offering verification. Truncated reports remain assessable so the
existing report_completion check can fail honestly. Verifier omission retains
the actual response and stops without manufacturing an assessment.

After the real CLI return, the next correction input includes the exact current
report, immutable finding packet, original intact verify/source ToolMessages,
and available source catalog. Actual SDK serialization must contain both that
feedback packet and the same call ID's exact CLI result. Typed delivery/inclusion
events and wire evidence record this; receipt or continuation does not establish
understanding or repair.

Revision 1 must be a new model-generated report with the same report ID, higher
revision and its own input reference. Only its new immutable checkpoint can be
rechecked, again upon a real model request. The original assessment remains
byte-identical in storage. Unchanged/noncompliant reports can fail again. Clean
initial named checks produce NO_CORRECTION_NEEDED and observation to window end;
no failure, correction or revision is fabricated. No model response after final
recheck is required or claimed.

## Money, approval and launch

Both models use medium effort, zero retries, concurrency 1, at most 11 requests
each. Historical conservative request reserves remain $0.16024 Terra and $0.32048
Sol: per-arm worst $1.76264/$3.52528, paired $5.28792. Rounded caps are $1.77/$3.53
($5.30 paired), within reported headroom $5.656075 under the cumulative $10 ceiling.
These are conservative bounds, not invoices or a new $10 allowance.

Original Budget reservation/settlement machinery is reused unchanged. A new
operator-reviewed closed ledger must bind initial/active/hard [3,10,10], exact
file hash, carried balance, all historical rows and both known $0.16024 unknown
holds by full tuple. Old smoke approvals cannot launch this milestone. New
approvals bind selected model/profile/cap, source manifest hash, accepted B
dependency, upstream pin, runtime versions, implementation, checkpoint policy,
operator baseline, one unused absolute output and expiry. Generated templates
are false. Only credential-name presence is checked by readiness; no secret search.

Root launches sequentially. The second arm requires a new explicit read-only
baseline including settled first-arm rows. A new unknown hold stops before arm
two. No hold is cleared, reconciled or released by this harness, and no ceiling
is raised. No scheduler or automatic retry is installed.

```powershell
# No paid call; ROOT supplies accepted source manifest and operator review paths.
python -B tools/correction_experiment.py --mode preflight --model gpt-6.1-terra --upstream "$env:TRUSTKERNEL_TRADINGAGENTS_UPSTREAM" --source-bundle "$env:CORRECTION_SOURCE_MANIFEST" --budget-review "$env:TRUSTKERNEL_BUDGET_REVIEW" --output .local-runs/correction-preflight-terra-001
# AUTHORED model HTTP responses, exact captured replay, simulated phase schedule:
python -B tools/correction_experiment.py --mode scripted --model gpt-6.1-sol --upstream "$env:TRUSTKERNEL_TRADINGAGENTS_UPSTREAM" --source-bundle "$env:CORRECTION_SOURCE_MANIFEST" --output .local-runs/correction-authored-sol-001
```

Root alone prepares the reviewed per-arm operator approval and invokes `--mode
paid --approval <matching-operator-artifact>` after all gates. Do not substitute
smoke outputs, an authored source bundle or stale budget metadata. Ctrl+C stops
the supervisor/child and retains unknown reservations; hard timeout also retains
partial files. Read result.json, envelope-preflight.json, phases-turns.jsonl,
runtime-trace/trace.jsonl and feedback.sqlite read-only. CLI request/envelope/exit,
model/source call IDs, source status/provenance and feedback next-wire references
remain inspectable. Failure is an outcome, never automatic permission to rerun.
