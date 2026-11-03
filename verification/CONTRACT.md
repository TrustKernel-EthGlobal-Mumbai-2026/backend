# Atomic ledger contract 1.1.0 — exploratory draft

Schema 1.1.0; normalization 1.1.0; selection/extraction rules 1.0.0. These versions identify a proposal, not ratified architecture. Compared with intermediate v1.0 builds, v1.1 adds exposure provenance and explicit JSON/wrap-up transformations, distinguishes envelope presence from established tool-call/result lineage, and scopes shared propositions by the actual fixture hash. Earlier pilot hashes/counts must not be combined with current IDs. This is a bounded local analysis of recorded synthetic data.

## Storage and return contract

`python -m verification.ledger build --profile pilot|full` reads only the frozen session and local selection rules, writes `verification/data/<profile>/ledger.jsonl`, rebuildable `ledger.sqlite`, coverage, manifest and generated BUILD.md. Each coherent build has an ID derived from the canonical data hash and implementation hashes; the manifest binds coverage counts and code to that build. `rebuild` consumes JSONL alone; `validate` resolves source files, checks bundle hashes and compares every SQLite row with JSONL. Canonical JSONL is sorted by table and ID, UTF-8 with LF line endings and one JSON object per row. Each row includes `table`, `schema_version`, `normalization_version`, `extraction_version`. SQLite contains typed columns, JSON-encoded composite values, primary/foreign keys, index metadata and views. It is a disposable index, never the source of truth. No runner imports, network or model inference.

## Grain

| Table | One row |
|---|---|
| artifacts | Immutable source file identified by project-relative path and SHA-256 bytes |
| runs | Recorded workflow, arm/model, pair, fixture and workflow config hash; session config hash remains separate |
| events | Every raw JSONL event, line/seq/event ID/hash, original payload preserved |
| evidence | Fixture tool item, scoped by fixture hash and item digest, with declared source/root/time and content status |
| availability | Run/evidence available in recorded evidence.available event |
| retrievals | Backend evidence.retrieved event; arguments retained; not proof of delivery |
| calls | Each llm.start attempt, matched end/error and actor from recorded checkpoint metadata |
| texts | Decoded original text at JSON pointer or explicit local report-format transformation; parent artifact/event and content hash |
| exposures | Exact evidence-content occurrence in one recorded input message, or exact prior report text, with lineage/mode and explicit transform; marker-only references stored separately as mentions |
| mentions | Literal evidence ID or recognized URI in report text, with exact span; references do not automatically support a claim |
| reports | Each nonempty designated final report field, its origin output/input call when provable, full text, selected coverage |
| propositions | Normalized candidate tuple: entity/predicate/value/unit/time/scope/modality/assumptions; semantic equivalence candidate or exact structured-value identity |
| assertions | One selected exact report span occurrence, actor/run/call/output time, candidate proposition and selection rule |
| links | Explicitly typed citation/dependency/support-candidate links with agent-asserted/extractor-proposed/verified status and limited meaning |
| checks | Reproducible typed result, method/version, subject, expected/observed, evidence/exposure pointers; separate from semantic judgments |

## Identity and exact provenance

Raw events retain UUIDs. Derived IDs use a table prefix plus SHA-256 of canonical JSON identity. Propositions never use a report occurrence ID as their identity; occurrences never collapse repeated text across actors, fields or runs. Nonidentical normalization is only proposed by explicit versioned selection rules. Recommendations carry run-specific scope because portfolios/context can differ. No unrestricted fuzzy merging.

Text offsets are zero-based inclusive/exclusive **Unicode code points in the decoded JSON string**, not UTF-8 bytes or raw JSON lexical offsets. Every assertion has original exact quote and a report text pointer. Raw events identify line/seq and JSON pointer; formatted structured reports must reproduce the entire saved report exactly before assigning their output/input call. Tool envelopes may require JSON parsing, or the recorded `[tool_name returned]` prefix followed by JSON parsing; both transforms preserve and resolve to the original input string. These finite transforms are explicit, not arbitrary execution. A source-presence check is not a factuality check.

## Evidence and links

Availability, backend retrieval, exact delivered content, report-text propagation and citation are independent facts. Exposures are tied to a specific model attempt and original input message. Validated envelope identity establishes content presence only. `decoded_tool_result_lineage` additionally requires tool-role message, matching tool-call ID, exact prior recorded tool-result content and a preceding equal evidence.retrieved payload in the same run. A valid copied envelope in human/assistant text remains `decoded_envelope_presence`, including legitimate upstream wrap-up messages; exact prior result copies are listed without inventing a tool role or ID. The envelope's digest is compared against the fixture; it conveys no source authority by itself. `exact_evidence_text_in_message` records identical text in prose without tool-origin lineage. A report repeating an evidence ID without the evidence content is a mention, not raw evidence delivery. Exact complete report embedding establishes report exposure, not all underlying evidence delivery. Absence of a full-content match means no exact delivery identified by this method; paraphrased/partial evidence remains unmeasured. No private reliance or causal reasoning inferred.

Declared root-source equality is recorded for E_NEWS/E_GLOBAL. Items without root_source_id have unknown independent-source identity; all share one synthetic fixture author, so CSV/snapshot agreement is not independent corroboration. NO_DATA means the tool explicitly reports missing series, not positive evidence of market conditions. Snapshot has mixed price content and missing indicators; status is PARTIAL. Evidence time is distinct from assertion/wall-clock time and synthetic as-of date.

Exact ID and recognized fixture URI citations are detected across full reports. Assertion-level citations are only linked when the marker shares the selected line; wider attachment is unresolved. Even a verified citation link means only that the marker appears, never verified support. Candidate evidence relations are extractor-proposed and awaiting independent adjudication. No guessed causal/dependency edges.

## Checks and extraction limits

Selection is deterministic lexical matching under a **worker-authored, provisional semantic rubric**. It is not an exhaustive semantic parser or independent gold annotation. Exact text/joins can pass while normalized meaning remains wrong. CSV Decimal/ordering checks are conditional on the candidate mapping and explicitly record this. Required snapshot compliance uses the recorded Market Analyst instruction plus preceding retrievals and remains separate from numeric support. Structured missing targets are absence observations, not numeric targets or forecasts. No composite score, model ranking, truth probability, contradiction rate or claim-recall percentage.

Coverage denominator is the complete saved report text and designated report fields, not an unknown count of all true atomic claims. Nonselected text and non-atomized fields remain queryable and are listed. Bull/bear/risk dialogue is preserved in events/input text but not atomized. Broader general-knowledge claims, conditional recommendations, inferred support and semantic equivalence remain provisional; independent evaluation is deferred. The read-only context query returns the enclosing paragraph, source pointer, candidate mapping, checks and per-attempt exposure separately. Reviewer supersession, alternative justification sets and reversible realignment are future design questions, not implemented features. There is no independent reference set.
