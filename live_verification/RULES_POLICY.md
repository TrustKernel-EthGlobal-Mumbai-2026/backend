# Scoped live-ledger rules 0.1

Only the new canonical live ledger is consumed. `assess_ledger(ledger_dir, dest)`
validates it and creates a new destination; an existing destination is refused.
The rules never load a budget client, fetch a source, call a model, modify a
recorded run, send feedback, or claim a repaired historical decision.

## Meaning of findings

Every finding has a deterministic content ID, method and policy versions,
status, scope, reason, expected/observed values, canonical source/candidate/span
references, coverage and limitations. The entire Unicode span and its parent
hash remain inspectable. The output summary has `clearance: null`.

- **PASS**: the named, bounded relation was observed. It is not assertion truth.
- **FAIL**: a captured obligation was omitted, an OHLC mathematical bound failed,
  saved matched versions disagreed, a displayed equation was false, or a bound
  provider response was marked incomplete. The finding names its subject.
- **INCONCLUSIVE**: a prerequisite, accepted policy or grammar mapping is missing.
  Failure to recognize an acknowledgement is inconclusive, not an invented rule.
- **ERROR**: invalid bindings are operational errors. Invalid canonical input is
  rejected before output creation with `ValueError`; it is not a factual FAIL.

`validate_ledger` verifies canonical hashes, spans, joins and SQLite parity.
The parent separately validates against the original source session. Canonical
integrity does not authenticate a publisher or establish semantic correctness.

## Rules and selection

`required_snapshot_invocation` follows the actual bound Market Analyst report
call. The obligation must appear in that call's recorded input. The complete
recorded event prefix and actual actor-bound tool invocation precede the report.
A called-but-unavailable source is invocation PASS; an omitted invocation with
complete prerequisites is FAIL. Missing report/actor/prompt/prefix is inconclusive.
Acknowledging omission does not retroactively perform the invocation.

`tool_round_fallback_context` retains the recorded original round cap, spent-round
wording and fallback logs independently. It neither exempts the obligation nor
establishes why a model chose its tools. No revised tool policy is simulated.

`recorded_source_availability` preserves AVAILABLE, SOURCE_UNAVAILABLE,
MISSING_CREDENTIAL, NO_DATA, WITHHELD, ERROR and unknown statuses. Availability
is distinct from invocation, freshness and authenticity. Missing return data
are not a zero or a fabricated observation.

`source_ohlc_bounds` parses dated CSV rows and the native snapshot OHLC table.
It checks `Low <= Open <= High`, `Low <= Close <= High` and `Low <= High` with
Decimal arithmetic. A FAIL belongs to the saved source row, not agent quality.
Repeated rows in different runs are separate observations of potentially the
same underlying provider row; finding counts are not independent-defect counts.
Non-numeric or unknown layouts remain inconclusive.

`within_run_csv_snapshot_agreement` compares explicitly identical symbol/date
OHLC rows from the CSV and snapshot within one run. A difference is a saved
version disagreement; no reconciled true price or authoritative supersession
is invented. Different retrieval clocks can explain variation but no cause is
proved. This does not make a report's truthful quotation of both values false.

`source_conflict_acknowledgement` selects a bound market report exposed to both
conflicting versions. It preserves full lines containing explicit discrepancy
wording and a CSV/snapshot/price label. PASS is lexical disclosure only, with
semantic resolution still inconclusive. No matched line is inconclusive, not an
invented failure or a guarantee of complete conflict analysis.

`missing_source_acknowledgement` selects exposed failed FRED/macro, ETH-news or
snapshot families and retains full report lines with family and missing-data
wording. PASS is lexical acknowledgement only, with negation/scope limitations.
Its absence is inconclusive. It does not prove exhaustive missing-data disclosure.

`exact_url_duplicate_lineage` counts literal saved-source URLs within each run.
It keeps occurrences separate from exact identities. Repeated URLs do not imply
independent corroboration; there is no failed deduplication obligation invented
from silence. URL syntax normalization, redirects, publisher identity and
syndicated-story identity are unassessed.

`citation_preinput_provenance` selects explicit Markdown report links. It requires
the exact URL in an AVAILABLE same-run source with canonical pre-assertion input
exposure in the originating report call. PASS establishes URL provenance only:
not article contents, actuality, relevance, entailment or private reliance.
Unresolved structured origins remain inconclusive.

`provider_response_completion` inspects provider status/finish metadata in the
bound output event. Incomplete/length is FAIL for completion only. Completed is
PASS for provider completion metadata, not analysis completeness. Unbound report
rendering or absent status remains inconclusive. Workflow success is irrelevant.

`selected_scalar_source_consistency` selects only explicit Open/High/Low/Close/
Volume/RSI/ATR label-number grammar in canonical candidate envelopes. It compares
with AVAILABLE native snapshot values exposed before the same call, using Decimal
ROUND_HALF_UP at the asserted precision. PASS means label and rounded-number
agreement only. It explicitly leaves semantic entity/date/attribution/negation/
conditional roles INCONCLUSIVE. Unmatched values are INCONCLUSIVE, never blanket
FAIL against a newer snapshot: a report may quote an older CSV as a discrepancy.
No thresholds, forecasts, sizing or general numerical assertions are certified.

`selected_subtraction_arithmetic` recognizes only explicit `a-b=c` or `c=a-b`
equations, including percent syntax. It retains the full candidate envelope and
checks exact displayed Decimal arithmetic. Settlement rules, identical time/
source, synchronized quotes and actual probability interpretation remain
INCONCLUSIVE even when the subtraction is correct. Textual hidden arithmetic
and general mathematical reasoning are not inferred. The scope is displayed
numeric coefficients only; unit interpretation is explicitly inconclusive. The
canonical passage context is retained when an extracted child is narrower.

`numerical_selection_coverage` records canonical candidate counts, unique
envelopes with digits, selected scalar slots/matches/unresolved slots and explicit
subtraction equations, unselected digit-bearing envelopes and canonical numeric
atom counts. Repeated scalar/equation spans in overlapping candidate envelopes
are selected once, with a deterministic narrowest-envelope choice. Selection is
deterministic grammar coverage, not semantic
recall, a random sample, independent adjudication or full numerical support.

`unresolved_semantic_and_time_limits` preserves unknown TTL, candle finality,
version authority, complete dependencies and suitability in every run. No old
synthetic 60-second TTL applies. Latest daily Close is not certified final or an
executable tick. Input presence and local proposed dependencies are not private
attention or accepted full-decision support.

`recorded_date_clock_context` retains run-local analysis/local/UTC clocks and
parsed source-row dates without declaring a one-day clock difference erroneous.
Missing provider time fields stay unknown. It introduces no TTL or finality rule.

## Outputs and validation

`findings.jsonl` is canonical sorted UTF-8 JSONL, keyed by deterministic finding
ID. `findings.sqlite` is rebuildable and queries rule/status/run plus full JSON.
`summary.json` binds the ledger canonical hash, findings hash and implementation/
policy files. `input-validation.json` preserves the ledger validator result;
`REPORT.md` gives counts, failures and limits. No wall-clock build time appears
in canonical findings. `validate_assessment(dest, ledger_dir)` checks IDs, ordering,
hashes, summary arithmetic, full SQLite logical parity and every emitted span/ref.
When a ledger directory is supplied, it also revalidates that ledger and replays
the assessment, rejecting even a rehashed verdict with a rebuilt index/summary.
Current implementation/policy hashes must match the saved binding.

Dedicated offline tests use disposable canonical-row doubles only. They are
mechanism checks, not observed live outcomes. Parent owns the actual integrated
build, original-corpus protection and final account of findings.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest live_verification.tests.test_rules -v
.\.venv\Scripts\python.exe -B -X utf8 -m live_verification.rules --ledger <new-ledger> --dest <new-findings>
```
