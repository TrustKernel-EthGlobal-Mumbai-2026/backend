# Proposed check contracts and ledger dependencies

Draft 0.1, 30 October 2026. Companion to `SEMANTICS.md`. Inputs refer to the captured draft atomic-ledger schema/normalization/extraction 1.0.0; artifact hashes in `notes/source-packet.json` pin the actual snapshot. No edits to that schema are made here. A field expressible in a free-form `details` object is not necessarily a stable interface.

## Common result envelope

One check invocation should bind a versioned method to immutable inputs and an explicit question. Provisional fields:

```json
{
  "check_id": "stable invocation identity",
  "check_type": "numeric_equal",
  "method_version": "declared version and optional code digest",
  "subject": {"assertion_id": "...", "proposition_revision": "..."},
  "context_id": "...",
  "scope": "frozen synthetic fixture, selected call or stated rationale",
  "input_refs": ["artifact hash + event/text pointer/span or row/column selector"],
  "normalization_ref": "worker candidate mapping and its version",
  "prerequisites": ["same entity, date and units; accepted scalar mapping"],
  "status": "PASS | FAIL | INCONCLUSIVE | NOT_APPLICABLE | ERROR",
  "expected": "typed value or relation",
  "observed": "typed value or relation",
  "reason_code": "specific, versioned reason",
  "positive_witness_refs": [],
  "negative_witness_refs": [],
  "assumption_refs": [],
  "recorded_at": "assessment creation time",
  "valid_for_context": "evidence/policy snapshot identity",
  "supersedes": null
}
```

No field above is a truth probability. Preserve expected versus observed rather than only a verdict. A failed prerequisite normally yields INCONCLUSIVE/NOT_APPLICABLE; it must not become semantic contradiction by default. Invalid source integrity should block dependent evidence checks and retain the integrity finding. Check execution exceptions produce ERROR. A later successful check supersedes the failed attempt for a selected view but must not erase it.

`check_id` must distinguish policy/evidence/normalization revisions. Repeating the same inputs/method may be idempotent; a new input hash is a new invocation context. Assessment candidates, accepted semantic mappings and deterministic observations need separate authorship/status fields. Exact reproduction does not upgrade a candidate semantic mapping to accepted truth.

## Check catalogue

| Contract | Required inputs and operation | Meaning of result | Cases and hard boundary |
|---|---|---|---|
| C01 Source integrity and span | Artifact SHA-256, JSON pointer, decoded text hash, offset unit, [start,end), quote, transformation chain. Recompute hash and resolve exact substring. | PASS proves quote/pointer equality under this transform. FAIL blocks source-dependent claims of reproducibility. | R01–R12; offset mutation. UTF-8 bytes, UTF-16 code units and Unicode code points are different coordinates. Duplicate text occurrences still need their own location. Hash consistency alone does not authenticate a real-world publisher or guarantee pre-capture completeness. |
| C02 Typed scalar equality or interval compatibility | Proposed claim tuple, date-specific row/column or snapshot field, decimal parser, field unit, rounding method. Confirm tuple compatibility before comparing. | PASS proves equality or interval relation for that normalized question. A distinct incompatible value can be a contrary witness only if mapping is accepted. | R01/R11; value 2541 counterfactual. Unit mismatch is not false numeric equality; it is an unsatisfied comparison precondition unless an explicit conversion exists. Missing values are not zero. |
| C03 Bounded derived numerical relation | Exact input rows, order/date window, expression, sign/denominator/scale/rounding, minimum sample requirement. Compute the declared expression. | PASS proves a relation on the selected finite sample. | R02/R03. High−low gives 70,80,90. Does not validate ATR or a durable trend. Day-on-day return and open-to-close return have different denominators. SMA3 can be computed if explicitly requested; it is not a returned SMA200. |
| C04 Recorded evidence exposure | Assertion's actual originating call; llm.start input event/hash; content pointer; original string; raw or decoded transform; evidence hash/identity. Resolve direct literal or recognized envelope content. | PASS/OBSERVED can establish full content delivery in the recorded input. INCONCLUSIVE means no supported match by the declared detector, not proof of total semantic absence. | R01/R05/R08. CSV JSON escapes defeat literal substring search. A full prior report establishes report exposure only. Evidence ID, URI or summary alone is not raw evidence delivery. Runtime logging boundaries remain a premise. |
| C05 Temporal and contextual admissibility | Claim valid interval, prompt as-of, source effective/observed/published/retrieved times with precision/timezone, actor input event order, freshness policy if any. Compare only compatible temporal questions. | PASS: evidence fits declared use. FAIL: an explicit rule is violated. INCONCLUSIVE for missing precision/policy. | Historical close stays historical; current reuse may be stale. `observed_at` date-end and prompt date-only cannot establish an exact same-day future leak. Event wall-clock and synthetic analysis date are different clocks. Later source availability cannot backfill earlier recorded context. |
| C06 Scope, modality and contradiction gate | Candidate proposition tuples, negation/modal operator, attribution source, quantifier, time/scope/unit compatibility; accepted incompatibility rule. | Numeric incompatibility may be deterministic after normalization; prose incompatibility remains proposed unless the mapping/rule is accepted. Different scopes/modalities can yield NOT_APPLICABLE or unresolved normalization. | R05 snapshot vs whole context; R07 allegation vs event; R08 News Analyst vs entire run. Rising highs and uncertain trend coexist. No automatic contradiction from different recommendations. |
| C07 Source lineage and independence obligation | Evidence/source/root IDs, derivation relations with provenance, claim-specific source roles, unknown-identity status, declared independence criterion. | Same known root can disqualify a requirement for distinct original reporting. Distinct roots do not prove statistical or organizational independence. Unknown roots remain unknown. | R06/R07. Different URIs, retrievals, hours or tools are not independent source counts. CSV and snapshot share fixture authorship despite different representations. No effective-sample-size calculation without a dependence model. |
| C08 Required-tool protocol | Exact instruction span/version, subject actor, obligation/trigger, tool availability interval, relevant calls/tool results, deadline/ordering and complete trace boundary. | PASS/FAIL concerns the explicit protocol. Separate invocation, successful retrieval and delivery obligations. On an unfinished/incomplete trace, absence is usually inconclusive. | R04; Sol had no preceding snapshot retrieval before completed market report. Unconditional “before final report” differs from “before exact numeric claims.” Tool-round limits explain context; they do not make unsupportedness or model blame automatic. |
| C09 Missingness and declared assumptions | Tool-result content/status/arguments, requested series and dates; assumption text/scope, proposed/accepted/disputed state, references, any explicit negation. | NO_DATA supports a missing-series observation only. An assumption can be recorded without being established. Conditional conclusions retain that condition. | R09/R10. No probability series ≠ zero probability. Three requested macro queries returning the same NO_DATA are three observations of tool behavior, not three sources about the world. User-provided portfolio limits still need applicability data. |
| C10 Justification viability and affected dependants | Accepted sufficient sets, typed members, inference rules/bridges, context eligibility states, change event and timing, known graph completeness. Re-evaluate conjunctions and alternatives. | A set can become invalid/pending while another survives. No surviving recorded set establishes loss of recorded justification, not the negation of the conclusion. | J1/J2 in SEMANTICS; common F or N defeats both. Candidate edges produce review candidates, not proven dependency failure. No pure circular self-support. New corpus members can defeat missingness/absence premises. |
| C11 Decision and prediction applicability | Decision objective, portfolio state, constraints, permitted alternatives, costs, horizon/resolution rule and timestamps; ex-ante evidence view separately. | Check specific policy conformance or outcome only when inputs exist; otherwise INCONCLUSIVE or NOT_APPLICABLE. | R10–R12. Hold does not mean a price forecast. Correct prices do not prove best allocation; an eventual bad outcome does not alone disprove the ex-ante rationale. |

The first five contracts can often use deterministic mechanisms after explicit selection. C06/C07/C09/C10 still contain semantic or acceptance premises even if their set comparisons are exact. C11 often lacks inputs. These are capabilities, not an automatic coverage promise.

## Atomic field dependencies and gaps in the captured draft

| Concern | Available in inspected 1.0.0 draft | Candidate additions or declared conventions needed |
|---|---|---|
| Exact reproducibility | artifacts.path/sha256; events.seq/hash/raw; texts.pointer/transform/text/hash; assertion spans/quote | Stable transform versions; raw-to-decoded mapping chain; method/code digests; explicit prerequisite failures and result supersession. Existing envelope decoder is useful, not a universal semantic-exposure detector. |
| Claim identity | propositions entity/predicate/value/unit/valid_time/scope/modality/assumptions/identity_status; occurrences in assertions | Claim revision/normalization acceptance and author; field-level volume units; attribution/quantifier structure if ambiguity cannot be represented in modality. Do not replace original text. |
| Assessment context | runs fixture/config hashes, calls IDs; checks method/result/details | Explicit named context/corpus ID, evidence cutoff and matching policy. Proposed support/opposition witnesses and search-completeness record. Details can prototype these without freezing columns. |
| Exposure/hand-off | calls, texts, exposures with evidence/report IDs, mode and offsets | Distinguish direct decoded evidence, report summary, marker and uncertain partial content. A trusted report-handoff policy, if chosen, must not manufacture raw-source exposure. |
| Time | assertions.asserted_at; evidence.observed_at; proposition.valid_time; raw event timestamp | Explicit temporal precision/timezone; valid-from/to and policy freshness where available; source publication, content-effective and recorded-change times if distinct. Unknown is a value state, not an invented default. |
| Lineage | evidence source_id/root_source_id/provider; availability and retrievals | Root relation status/basis, lineage revision, shared-dependency identity, claim-specific independence obligation. Do not silently create distinct independent roots for null IDs. |
| Justification sets | links assertion_id/evidence_id/report_id/relation/status/basis/mention_id; generic checks.details | General typed target (assertion/proposition revision/assumption/rule/context); justification set ID/member IDs and roles/polarity; conjunction vs alternative grouping; accepted sufficiency; guard/defeater conditions; graph completeness and change/supersession records. Current links cannot fully express assertion-to-assertion sufficient sets with their grouping. |
| Negative premises | Missing evidence status and original NO_DATA content | Separate source-returned missingness from “no item in corpus satisfies predicate”; the latter needs corpus/query/version/completeness and invalidation on membership changes. |
| Decisions | Run-scoped recommendation propositions; final report text | Explicit decision-policy version/authority and holdings/constraints/horizon data when supplied; conditional applicability state. No invented allocation or utility function. |

Options A, B and C all need the first three rows. B needs the structured context/eligibility/lineage/missingness distinctions. C needs sufficient-set grouping and change records. C11 is optional until a concrete policy question has actual inputs. Version bumps belong to the ledger owner/orchestrator after reconciliation; nothing here asks another lane to rewrite its work immediately.

## Invariants worth retaining across options

1. A finding names its question, corpus, mapping, method and witnesses. A PASS can be reproduced without guessing normalization.
2. Available, retrieved, delivered, cited, asserted reliance and independently established support are different relations.
3. Raw evidence, provisional mappings, accepted rules and decision policies have distinct revision histories.
4. Opposition is retained alongside support. Ambiguity, incomplete search and execution failure are distinct from contradiction.
5. No unsupported→false inference and no broken-premise→false-conclusion inference.
6. Alternative paths are sufficient only under explicit rules and assumptions; duplicates do not create independence.
7. Historical as-of assessments remain addressable after a current reassessment. No later evidence is silently placed in an earlier agent input.
8. A candidate dependency link is not a fact about private reliance. A missing edge is not proof of no dependency.

## Suggested reconciliation exercise

Take R01, R04, R05, R07 and R10. Express one result envelope for each under both repository-evidence and recorded-call views, marking unsupported prerequisites explicitly. For R01, add only the two hypothetical sufficient sets from the demonstration and a K0/K1 history. Compare resulting questions/outputs with the ledger pilot rather than expanding extraction or starting evaluation. This is the smallest useful interface exercise; it can stop with a design decision and needs no integrated judge.
