# Decision-rationale refinement layer 3.0.1 — corrected provisional build

Date: 1 November 2026. Existing recordings only. The accepted v1.1 and expanded-v2 releases, code/contracts/manifests and bundles remain unchanged. New output is data/refined-v3/. New dedicated tests must not invoke historical build/test setup.

Schema remains 3.0.0; normalization/extraction/rule registry are 3.0.1. The earlier provisional build refined-v3-3690dde6e7b737c3fbc2 was rejected after a real-sentence condition-attachment failure. Its original bundle is preserved as releases/REJECTED-refined-v3-3690dde6e7b737c3fbc2.zip for diagnosis, not as accepted output. This correction changes branch parsing and regenerated packet counts; it does not alter v1.1/v2 or establish independent semantic validity.

## Scope and hierarchy

Refine all six final decisions, six investment plans and six trader plans. Also refine same-run discussion outputs explicitly named by actor/role in those target texts, under declared alias rules. A named actor is an attribution candidate, not proof that all of that actor's statements are premises. Preserve all parent v2 envelopes; new sentence frames and children carry exact source spans plus overlapping parent passage/candidate IDs. A separately versioned scope registry records why each source was selected. Whole source, frame, clause child and proposition are distinct grains; no unique-fact or recall count.

An additional bounded structural-regression scope includes discussion texts whose legacy candidate has a punctuation-only value. This makes the observed discourse false-atom inspectable in the new layer without treating it as a decision premise. It is not an unrecorded scope expansion to factual verification.

## Rule order and interpretation

The machine registry in refinement_rules.json states precedence, version, declared assumptions and limitations. Rules are hand-authored. Their application is deterministic; semantic correctness is not established by that fact.

1. Preserve section labels as metadata. Strip only their exact prefix from semantic-body parsing; never use `Investment Thesis` or `Reasoning` as a semantic predicate. Rating/action/target/horizon scalar values are report declarations, not imperative instructions or inferred semantic predications.
2. Split visible text into sentence frames with exact offsets. Metadata/whitespace are retained separately. Full paragraph and parent context remain accessible. Abbreviations/decimal handling are explicit surface rules.
3. Guard discourse/administrative language (`Let me separate...`, etc.) and author-position statements. They are not promoted to market facts. Embedded assertions that cannot be separated safely remain queued.
4. Before reason/condition parsing, R035 partitions semicolon branches regardless of whether a branch fits the narrow viable() predication grammar. Typed condition/antecedent/consequent spans must stay within that branch. Full-frame cues remain visible context; their presence does not assign an IF in one branch to another. Cross-branch semantic scope stays unresolved. Index explicit positive and negated reason markers within branches. `because A—not because B` has distinct declared/rejected-reason children; preserve the full frame and negation context. A stated reason is an author's declaration, not a validated cause or sufficient premise.
5. Decompose only bounded independent clauses or explicit condition/consequent forms. Nested/alternative conditions retain all markers and full frame/paragraph guards; Boolean scope remains unresolved unless a very narrow grammar explicitly represents it. Do not inherit a missing subject by guesswork. Shared-predicate/subject or noun-list conjunctions abstain/queue.

Suffix parsing also abstains on a condition introduced after a colon, or an unsupported IF-comma-instruction form; it does not type the earlier advice as the consequent and absorb the later instruction into an antecedent. Ordinary supported suffix/only-if cases and local prefix cases remain available. Scope.attachment_start/end records the permitted local branch; condition_spans is a typed proposal, unlike inherited_frame_cues. Corpus validation rejects cross-semicolon typed attachments even when exact spans/full context round-trip.
6. Parse bounded surface subject/predicate/value slots only after those guards. Preserve local and inherited condition, negation, modality, uncertainty and attribution cues. Unknown coreference, valid time, units and semantic equivalence remain unresolved. Unsupported grammar produces an explicit queue record, not a forced fact.

Each application records rule IDs, exact input span, resulting fields/child IDs, inherited scope and unresolved reasons. All normalized fields resolve to exact source strings or explicitly labeled metadata. Section names/recorded actor/instrument context are never silently substituted for an unknown grammatical subject/predicate. New propositions are unmerged and source-occurrence scoped.

## Hand-authored interpretations

refinement_annotations.json is a separately versioned, worker-authored provisional annotation overlay. Exact-quote anchors are validated deterministically, but the proposed semantic relation is an interpretation, not a rule-discovered fact or independent label. Keep annotation IDs/author/status/version separate from rule applications. No annotation is accepted factual support or private causal reliance.

## Decision-to-source relation types

- `exact_origin`: source artifact/pointer and verified raw generation or versioned rendered structured output.
- `recorded_input_text_presence`: a complete exact source copy in a particular recorded call input. Preserve physical aliases and timing.
- `recorded_input_evidence_presence`: exact evidence text/envelope occurrence in a particular call, with its existing provenance mode. Upstream presence is not direct final-call delivery.
- `explicit_citation`: literal ID/URI at its actual source/passages, never section-wide clause support.
- `explicit_stated_reason`: author-declared/rejected reason wording with exact spans and full context.
- `proposed_semantic_premise`: separately authored provisional mapping, not accepted support.
- `conditional_numeric_check`: an existing typed synthetic-fixture comparison, conditional on its recorded candidate mapping. A check on a reachable market report is not automatically a check on the final decision.
- `accepted_factual_support`: reserved; extraction establishes none. Required-tool compliance remains a separate protocol observation.

Per-decision packets include origin, rationale/condition children, direct recorded inputs, complete-report handoff paths, direct versus upstream evidence occurrences, actual references, conditional checks, proposed mappings, literal matches/unmatched spans and gaps. Traverse only time-valid exact-copy handoffs; never attach every available/retrieved item to every decision.

Literal matching uses exact case-sensitive contiguous text, including a separately declared minimum-span overlap rule for partial copied wording. The packet states that rule's character/token thresholds. Matched/unmatched are lexical coverage diagnostics, not support, relevance, semantic recall or proof of no partial/paraphrased delivery. Unknown dependencies, sufficiency and unsupported paraphrases remain unestablished.

## Determinism and validation

Canonical JSON: UTF-8/LF, sorted object keys, compact separators, rows sorted by table/ID. Build identity binds data hash, accepted parent identity/hash, implementation/registry/annotation/contract hashes and runtime manifest (Python and relevant standard-library versions). Same inputs/rules/annotations/environment must reconstruct the same canonical rows. SQLite is a rebuildable index. Source corpus/parent rows are immutable inputs. Runtime drift is explicit; no external inference or stochastic extraction is used.

Tests exercise unfamiliar text/IDs, labels/discourse, positive/negated reasons, independent/unsupported compounds, nested/alternative conditions, attribution, full inherited scope, exact source and parent round-trip, provenance/time failures, historical preservation and deterministic reconstruction. These are contract/regression checks, not independent semantic accuracy labels. Report before/after structure by source type, unresolved reasons and parent/child grain; a lower queue count is not an optimization target.

No new runs, paid/external inference, credentials, budget changes, trades/signatures, frontend, independent evaluation or verification-policy ratification. Owner explanation must make every interpretive layer inspectable.
