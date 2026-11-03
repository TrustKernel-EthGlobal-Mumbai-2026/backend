# Recorded-source verification policy

2 November 2026. Implemented against source adapter `recorded-source-packet-0.1`. Verifier `recorded-source-verifier-0.1`; policy `recorded-historical-and-review-policy-0.1`. This lane owns verifier.py, this policy and tests/test_verifier.py. The parent owns persistent replay, recording, integration and final acceptance. Prior procedural_loop and contract-v0.2 code/packets remain frozen.

## Historical source scope

Inputs are actual recorded TradingAgents/LangChain executions over a frozen synthetic ETH fixture. Selected pair-0 cases are Sol's missing required snapshot invocation and actual closes-below-open/previous wording, plus Terra's compliant recorded snapshot call and exact close token. The contextual Terra instrument/date/unit/Close mapping was accepted by the human; that acceptance does not validate unrelated normalization or change old findings. Sol's finite-sample relation remains an explicit authored mapping, not an invented numeric price assertion.

Source integrity, exact claim extraction, numerical fixture consistency, particular-call exposure, before-report protocol, historical date alignment, intraday freshness, full-decision dependencies and suitability are different questions. A correct price does not excuse a missing required call. Matching content does not prove private reliance or attention. A synthetic fixture match does not establish real-world ETH conditions.

## Historical evidence and time

Bind the corrected ledger build/hash, original trace/report/fixture artifacts and exact selected Unicode half-open spans. Validate claim source/call/event identities, decoded tool-envelope content and version/pointer/hash references. Derive protocol observations from the actual bounded original event prefix, not a later reviewer receipt or a run-wide tool count. If source/capture prerequisites are incomplete, remain INCONCLUSIVE or ERROR rather than invent absence.

Daily fixture date, source observed_at, actual execution wall time and new review time must remain separate. The historical synthetic prompt as-of has no intraday precision, and no accepted intraday freshness threshold is supplied. Date alignment can be checked; intraday freshness remains INCONCLUSIVE. Do not apply TTL60 from the earlier authored evolving fixture or invent a new source version for an unchanged artifact.

The original omitted before-report snapshot invocation remains FAIL. Original feedback was disabled, and no historical receipt/acknowledgement, correction, new model response or new decision may be fabricated. Whole-decision material dependency completeness and portfolio suitability remain explicitly uncertified, even if selected numerical checks PASS.

## Local reviewer scope

The new parent-owned replay may deliver a finding to a local reviewer, record a reviewer acknowledgement, re-read the original snapshot artifact and request a recheck. These are new local actions with distinct identities/timestamps. The read demonstrates post-hoc artifact availability and selected-claim consistency, not a fresh market observation or original agent delivery.

`assess(packet)` (also `assess_original`) produces source-linked historical findings. `assess_review(packet, receipt)` validates the separately bound reviewer read and produces only narrowly scoped reviewer findings/readiness. It retains the historical assessment identity/protocol outcome and never issues global or historical procedure clearance based on a new read. Readiness binds the new receipt, packet/source hashes and reviewer context with explicit limits; a changed or mismatched receipt cannot retain the same readiness identity. No current-market TTL is invented for a read of an unchanged artifact.

## Test priorities

| Boundary | Targeted regression |
|---|---|
| Actual protocol | Sol original prefix FAIL versus Terra original compliant call; later read cannot turn Sol PASS |
| Extraction | Exact Terra token/context/date/unit and actual Sol relational wording; wrong source/span/value/version blocked |
| Exposure | Content is tied to original input call, preserving decoded-envelope versus direct-lineage distinctions |
| Temporal scope | Historical daily alignment versus absent intraday precision; no invented TTL/version progression |
| Replay identity | Receipt binds original packet/source hash and new reviewer identity/time; mutation or original-agent impersonation blocked |
| Decision scope | Missing full dependencies/portfolio inputs prevent certification; no false original-agent remediation |
| Preservation | Historical findings/packets stay unchanged; no writes to old sources or completed first loop |

No model/API/network/research/credential/budget/trading/on-chain/frontend actions. Use only existing standard-library runtime and named new tests; no historic builds/test discovery.

## Frozen APIs and result scope

`assess_original(packet)` / `assess(packet)` return `assessment_id`, `packet_id`, `layer=historical_source_assessment`, `scope=selected_original_recorded_call_checks_with_explicit_unknowns`, aggregate `status`, source-linked `findings`, `protocol_status` / `historical_protocol_status`, `required_response`, `clearance=null`, `policy_binding` and limits. Individual findings have scalar status, obligation/method/reason, expected/observed, original input/output sequences and exact source witnesses. IDs hash the full respective payload. Validation checks packet content identity and delegates original file/call/prefix/span/role fidelity to the frozen source adapter. It never executes old source builders.

Both selected numerical checks PASS in the actual source cases. Terra's accepted numeric occurrence is exactly report [346,351), within its original enclosing context. Sol's source anchor [1939,2053) is a full sentence for context, but the authored check covers only close<open and close<previous-close. `checked_subclaims` and `unassessed_subclaims` explicitly retain the higher-high wording as unassessed, and `source_sentence_fully_verified=false`. The same restriction applies to reviewer readiness; no whole-sentence PASS is implied.

Original required-invocation status is Sol FAIL (prefix 1–68 before output 69 has no snapshot invocation/retrieval) and Terra PASS (invocation 62/retrieval 63 before output 75). Own-call exposure checks preserve actual wrap-up human roles and decoded-envelope provenance; they do not relabel messages as tool output. Historical date alignment uses synthetic 2026-10-28, while actual wall-clock execution is retained separately. Intraday freshness, source-version authority, complete final-decision dependencies, suitability and response to new review remain INCONCLUSIVE. Thus original aggregate status is Sol FAIL and Terra INCONCLUSIVE, with no historical clearance for either.

`assess_review(packet, receipt)` returns `assessment_id`, packet/layer/scope, `review_scope`, `status`, `findings`, `review_ready`, nullable `readiness_binding`, `historical_assessment_id`, historical/original protocol status, `historical_clearance=null`, `clearance=null`, policy binding and limits. Review readiness requires all four local obligations PASS: newly identified receipt bound to exact original source; read-only original snapshot availability; dated snapshot/CSV OHLC consistency; and the selected scalar/partial relational consistency. It is not whole-procedure, full-sentence, current-market or trading clearance.

Receipt validation checks content digest, original case/run identity, evidence key E_SNAPSHOT, exact source anchor/snapshot identity, null source-version authority, new reviewer layer/actor/UUID, timestamp strictly after original output, and explicit no-history-change/no-historical-call-creation flags. Backdating, original-actor impersonation, altered source hashes, wrong cases and invented source versions are ERROR. A receipt is a local declared read record, not a cryptographically authenticated issuer. Parent replay events establish the actual new runtime action separately.

Readiness binds original packet/source-file digests, receipt ID/digest, original assessment identity and current verifier/policy file hashes. A different receipt creates a distinct assessment/binding; it does not overwrite old source findings. Missing/unsupported mapping prerequisites remain INCONCLUSIVE, malformed source bindings ERROR and known mapping/value inconsistency FAIL. Invalid packet nested contexts are normalized only for error reporting, never filled with invented observations.

## Tests and handoff

From Desktop TrustKernel:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest recorded_loop.tests.test_verifier -v
```

The final 19 named tests pass on actual source-backed Sol/Terra packets plus labeled mutations: original contrast, partial claim scope, own-call/role/decoding fidelity, no intraday TTL/version invention, original feedback/dependency limits, reviewer readiness without rewriting history, cross-case/evidence receipts, tampered/rehashed source bindings, original actor/backdating/version impersonation, wrong date/unit/value/occurrence/span, altered raw prefix/roles, null/list/primitive contexts, deterministic IDs, detached outputs and distinct receipt bindings. Parent owns the actual persistent replay and independent integration tests; this lane claims verified component behavior only until that replay is executed and reviewed.
