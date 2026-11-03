# Expanded processing and candidate contract 2.0.0 — exploratory

Schema/normalization/processing/extraction versions: 2.0.0. This release adds reusable passage accounting and provisional candidate extraction. It does not migrate, rewrite, or supersede the reproducible v1.1 pilot/full identities. The legacy selection file is retained only as a bounded regression example. Independent evaluation remains deferred.

## Corpus and denominators

1. Inventory every completed recorded model-output generation in the six-run corpus. A saved report is anchored in its final_state string and linked to its already verified output/input origin. A substantive non-report generation is anchored in its original generation text or visible text block. Empty generations containing only tool invocations are explicitly excluded from the narrative denominator; their output attempts remain inventoried. Errors remain in the parent trace inventory, never invented as text.
   The current corpus has one generation per completed event. Ingestion rejects unsupported multi-generation events, multiple visible-text blocks without a single generation text, unknown structured outputs without a report origin, or multiple saved reports mapped to one output. String-only visible message content has an explicit fallback pointer. These bounded format rules prevent silent narrative exclusion; none of the rejected formats occurs in this six-run corpus.
2. One **source occurrence** is one genuinely distinct originating output generation/representation, not every later state or input copy. The 30 saved report strings and accessible bull/bear/risk discussion outputs are in scope. All prose, conditional instructions, background explanations, questions, lists and tables inside them remain in scope. Distinct outputs with identical text retain distinct occurrences and share only an exact-text hash group, without semantic proposition merging.
3. Record complete exact-text **appearances** at raw pointers in same-run events and final_state, including origin/representation aliases, later model inputs, state snapshots and embedded outputs. Appearances are representations/occurrences, not extra authored sources or independent evidence. Partial/paraphrased copies are not exhaustively aligned; this is an explicit limitation. No cross-run/private-reasoning identity is inferred.
4. Processing denominator: the sum of Unicode code points in source occurrences, including whitespace. Exact-text-deduplicated character totals and physical appearance totals are separate denominators. The 30-report subtotal remains separately comparable to v1.1's 90,269 characters. A report reconstructed from structured output is one rendered source, not an extra source for every repeated structured argument field.

## Lossless segmentation and disposition

Each source is partitioned into adjacent nonoverlapping passages covering [0,len(text)) exactly. Markdown separators/whitespace are explicit passages. Sentence boundaries avoid decimal points and listed abbreviations. Semicolons can split independent clauses; conditional material is kept intact when splitting would risk losing condition scope. Compound or ambiguous clauses may remain a single **candidate statement envelope** with unresolved atomicity; they are never labeled fully atomic solely because segmentation ran.

Each passage has exactly one primary disposition plus overlapping tags:

- `candidate_assertion`: a reusable lexical rule identifies an assertive/structured statement candidate.
- `conditional_guidance_hypothesis`: conditions, epistemic possibility or recommendations; eligible for a candidate envelope that retains the whole condition.
- `question`: interrogative surface form; no answer is fabricated.
- `background_structural_material`: blank/formatting or nonassertive label. Background prose with a verb is still a candidate, tagged background when detected; it is not silently excluded.
- `unresolved_interpretation`: substantive content that the rules cannot safely normalize/classify, or a fragment needing context.
- `unprocessed_material`: a processing failure or unsupported input; retained exactly with a queue reason. A zero count only means the segmenter/classifier ran on every passage.

Overlapping tags preserve background, negation, uncertainty, conditions, recommendations, attributed allegations and possible compound structure. Primary dispositions are surface-rule proposals, not independently adjudicated semantics. Every substantive unresolved passage and each candidate with unresolved fields goes into a queryable queue. Structural headings with assertion-like content remain candidate eligible.

Candidate totals are separated into parent statement envelopes, surface-single-predication/structured-field candidates, and nested explicit numeric-field candidates. The latter retain a parent candidate and inherited full-passage condition/negation/modality cues. These rule-atomized candidates are not certified successful semantic atomization. Remaining statement envelopes and unresolved normalization counts must be reported separately; full passage accounting does not erase the extraction gap.

## Candidate and relationship contract

Every candidate statement envelope retains its exact source/passages/spans, enclosing paragraph, actor/run/stage/input/output sequence/time, method/version and provisional status. Surface subject/predicate/value are extracted only where a bounded rule can identify them; unknown fields remain null or explicitly unresolved. Units, dates/numeric expressions, negation/modality/uncertainty cues, conditions and assumption/reason wording preserve exact cue spans and do not imply correct scope resolution. Compound text is flagged; condition-bearing text is not converted to an unconditional fact.

Propositions and assertion occurrences remain separate tables. New propositions are **unmerged candidates scoped to their source occurrence**: no fuzzy equivalence, paraphrase merge or semantic identity inference. Exact text groups are separate from propositions. Legacy assertions remain visible in parent tables, clearly named as legacy selections; new candidate totals must not add legacy rows as if independently extracted claims.

Evidence links are lexical source references only: exact evidence IDs, known fixture URIs or unknown URI mentions, with text spans and attachment scope. They establish a mention, never factual support. Whole-source or paragraph references are not assigned to every clause. Explicit `because`/`if`/`assume` wording can be indexed as text-linked reason/condition/assumption spans with scope unresolved; it does not create causal or decision-dependency edges. Candidate extraction adds no factual-support verdicts. All v1.1 narrow deterministic checks remain parent observations under their original methods.

## Storage, validation and preservation

New commands live under `verification.expanded` and write only `verification/data/expanded-v2/`. Canonical JSONL contains unchanged v1.1 parent rows plus versioned new table rows, and SQLite is rebuildable from that JSONL. The manifest binds parent build/hash, code/contract hashes, corpus counts and coverage to a new build ID. Do not invoke the legacy build/tests to regenerate the historical parent while running this phase. Its released ZIP and profile hashes are preserved; new dedicated tests validate expansion without rebuilding v1.1.

Validation covers source hashes/pointers and rendered origins, lossless span round-trip, disjoint full character accounting, candidates inside passages, source actor/time/call joins, complete output-inventory disposition, appearance/origin deduplication, unfamiliar run IDs/wording, compound/conditional/negated cases, repeated text, stable builds, foreign keys and SQLite reconstruction. Denominators/exclusions and unprocessed/unresolved counts are exposed by run, actor and source type. **100% passage accounting is neither 100% semantic extraction nor verified truth.**

No new research, external inference, paid calls, credentials, budget changes, trades/signatures, UI work, new chats or subagents. Existing recordings only.
