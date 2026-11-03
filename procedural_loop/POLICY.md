# Offline procedural verifier policy

Implemented fixture policy for the first complete local verification loop, 2 November 2026. Shared interface: `procedural-loop-contract-0.1`, imported from procedural_loop.contracts. Verifier method version: `procedural-verifier-0.1`. This is an authored synthetic policy, not universal financial policy or general semantic verification.

## Scope and authority

The verifier checks one explicitly declared paper-proposal procedure over authored synthetic fixture evidence. It can establish source/version/extract consistency and temporal/protocol eligibility within the captured context. It does not establish real ETH conditions, Hold suitability, private attention/reliance, complete hidden dependencies or semantic accuracy. The host's hold/refresh response is a local simulation, not real framework enforcement or trade authorization.

Only procedural_loop/verifier.py, this policy and tests/test_verifier.py belong to this lane. Historic experiments, releases, budgets and contract-v0.2 artifacts remain unchanged. Standard-library Python and the existing virtual environment only. No model/API/network/research/spending/credential/trading/signature/on-chain/frontend work.

## Authored temporal policy

Evidence valid time, retrieval/recording time, source supersession knowledge and proposal decision as-of are separate fields. Fresh retrieval does not reset a source observation's validity or age. Required timestamp precision must be explicit and comparable; an absent needed time is INCONCLUSIVE, and malformed/naive/invalid timestamp binding is ERROR.

The implemented public boundary is half-open: `evidence.valid_at <= proposal.as_of < evidence.valid_at + policy.max_age_seconds`. At exactly expiry, eligibility fails. The shared contract permits a zero threshold; it yields no eligible instant. A nonnegative integer too large to compute an expiry returns a typed ERROR rather than an exception or clearance. Shared contract 0.1 has no valid_until field; the public verifier does not infer one. Its small internal interval helper also tests an explicit end for future compatibility, but adding a new public policy field currently makes policy scope INCONCLUSIVE. The max-age parameter is an authored fixture policy, never a universal financial TTL.

Parent has selected this explicit demonstration timeline: v1 value 2540 valid/observed at t0; first use t+30s; max age 60s, failing at age >=60s; expired reuse t+61s. V2 value 2560 is scheduled valid/observed at t+60s but must not enter the verifier's observed context until the parent actually refreshes at t+65s. A scheduled fixture version is not a delivered observation. Before refresh, staleness alone can block v1; the verifier must not use v2 as a hindsight supersession witness.

Use only evidence/changes available in the observed prefix at assessment as-of. Future evidence cannot validate an earlier decision, and later supersession knowledge must not invalidate a previously valid historical as-of assessment. A source revision already known to replace the cited revision at the current as-of makes the old revision ineligible under this fixture policy. If supersession scope/knowledge time is required but unknown, do not guess.

## Binding and extraction obligations

Resolve exact proposal, evidence, policy and context identities/revisions/digests. Source pointer/span coordinates use the contract's declared decoded-text coordinate system. The selected span must equal the recorded quote; the parsed value must equal the submitted extract under explicit entity/date/unit/field mappings. A correct number from the wrong revision does not pass source binding. Known contradictory versions are not silently reconciled.

Missing mappings, prerequisites, capture capabilities or declared dependency completeness are INCONCLUSIVE. Invalid digest/version/span/value bindings are ERROR or a narrowly typed extraction FAIL as the shared contract specifies. An absent protocol event can be a FAIL only under an explicitly complete bounded capture obligation; unknown capture cannot be treated as proof of omission. No blanket factual-support conclusion follows from these checks.

## Clearance and reassessment

Emit current clearance only if every required obligation is PASS. FAIL, ERROR, INCONCLUSIVE and any required NOT_APPLICABLE block clearance. Clearance must bind exact proposal/evidence/policy/context versions, their content and decision as-of. A different as-of, changed input or context revision requires reassessment. No reuse of a historical clearance to clear a new use.

Validation must check both binding and the current required-obligation outcome; a digest alone is not independent proof that checks ran or passed. This is deterministic local validation, not a cryptographic authorization system. Existing historical findings/clearances remain recorded; a new assessment does not overwrite them or label an earlier historical observation false.

Return a machine-readable required response for blocked proposals: refresh eligible fixture evidence and resubmit corrected proposal/extract/context, or supply missing capture/prerequisites. The verifier reports the required response; the parent runner must actually record finding delivery, host acknowledgement, refresh and reassessment. The verifier must not emit pretend acknowledgement or loop-completion events.

## Targeted acceptance tests

| Boundary | Required adversarial observation |
|---|---|
| Freshness | Just before expiry passes; exact expiry and later fail. |
| Clocks | New retrieval time cannot rescue old valid time; future valid/observed evidence cannot pass earlier as-of. |
| Known supersession | Known replacement blocks old version; future/unobserved replacement does not rewrite historical eligibility. |
| Extraction | Wrong quote/span/value/version/digest is detected, including a numerically identical value from the wrong source revision. |
| Capture and prerequisites | Unknown/incomplete capture, mapping or dependency coverage cannot produce clearance. |
| Binding | Changed proposal/evidence/policy/context/as-of rejects old clearance; unchanged exact inputs validate. |
| Clearance integrity | Altered result/clearance or a failed/inconclusive obligation cannot be made valid by an old clearance. |
| Reassessment | Refresh yields only a newly assessed clearance; the initial failing record remains distinct. |

## Frozen callable interface

`assess(packet) -> assessment` is deterministic and does not mutate the input or perform I/O. The assessment has `assessment_id`, `schema_version`, `verifier_version`, `packet_id`, `status`, `findings`, `required_response`, `clearance` (nullable), `binding` and `limits`. Each finding has an obligation/method/version, scalar top-level status, reason code, exact proposal/extract/source context, expected/observed, positive/negative source witnesses and limits. Assessment and finding identities hash their payloads. Logical assessment time is the explicit proposal as-of, not a guessed system clock; parent recording supplies runtime event chronology.

`required_response` contains `action`, `blocking_codes`, `evidence_ids` and `host_response_not_executed_by_verifier=true`. Action is `none`, `refresh_evidence_and_resubmit`, `supply_missing_prerequisites_and_resubmit` or `repair_invalid_packet_and_resubmit`. This response is a request only; no acknowledgement or refresh event is fabricated.

`validate_clearance(clearance, packet) -> bool` first checks the shared exact binding and then recomputes the assessment, comparing the whole expected clearance. A changed packet ID, proposal/revision/text/as-of, context/revision/events, evidence/version/pointer/content, capability declaration or policy invalidates old-clearance reuse. Every required finding must PASS. A forged digest alone cannot bypass a current failure. This is content validation within the local host, not issuer authentication.

The functions are stateless. The parent adapter/runner remains responsible for previous-packet immutability checks via `contracts.require_valid_packet(packet, previous=...)` and append-only recording. This verifier does not claim to know a prior version that is absent from its supplied context.

## Implemented narrow obligations

The supported policy ID is `synthetic-quote-freshness`, with exactly the shared base policy fields and the five required capture names `evidence_timestamps`, `source_versions`, `source_text`, `declared_dependencies`, `observed_prefix`. Unknown extra policy obligations or missing/unknown capture declarations remain INCONCLUSIVE rather than silently weakening checks. Required state is CAPTURED only within the declared fixture scope.

The fixture mapping is exactly one declared observation dependency and one `observed_quote` extract. It recognizes the complete source template `Synthetic ETH-USD quote: <scalar> USD at <RFC3339>. Authored test data.` and the authored REVIEW_ONLY paper-quote proposal. The amount span must be the actual amount field, the source substring must equal the extract quote, the Decimal amount must equal the extract value, source/dependency/extract versions must match, USD must be declared, and content's timestamp must equal valid_at. Unsupported mappings, NO_DATA and missing unit/dependency/capture/clock fields block clearance. Malformed packet/digest/bounds are ERROR; structurally valid wrong quote/value/version/unit are scoped FAIL. Decimal representation normalization is declared; quote/source spans themselves remain exact.

All supplied evidence must satisfy visible-prefix clock ordering `valid_at <= retrieved_at <= recorded_at <= context.observed_at <= proposal.as_of` and at least one evidence causal reference must occur in the declared context event refs. Proposal submission/capture refs must also be present. These are bounded declared-prefix checks, not independent verification of raw framework capture.

Freshness and known-supersession findings apply only to cited dependencies. Uncited immutable older history is not required to stay fresh. A delivered, visible same-source replacement can disqualify a cited old version; a future/unknown-clock replacement cannot be a supersession witness. Injected future evidence still blocks the overall packet's prefix eligibility. Cross-source replacement binding is ERROR. The complete required finding set, not a numeric score, determines clearance.

## Validation and handoff

Named test command from Desktop TrustKernel:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest procedural_loop.tests.test_verifier -v
```

The 26 targeted tests pass, including the parent-reported `max_age_seconds=10**30` overflow regression and a larger integer. The initial helper-only checkpoint had five tests; the final suite adds public assessment/clearance and adversarial input cases. Parent owns all integration tests, persistence and actual loop execution. No successful end-to-end loop is claimed here until that runner executes it and parent reports acceptance.
