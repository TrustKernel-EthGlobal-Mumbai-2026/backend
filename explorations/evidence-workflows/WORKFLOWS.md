# TrustKernel evidence inspection workflow alternatives

30 October 2026. Exploratory findings for the orchestrator. Sources and demonstration are local; no interface, schema or semantic adjudication policy is approved.

The next useful choice is how a reviewer answers one evidence question and preserves the answer. Three complementary entry points are worth exploring: an assertion case file, a recorded-context replay, and a paired comparison worksheet. Each can use CLI, queries, notebooks, reports or an eventual visual navigator. All need the same source and check distinctions; none requires a dashboard or an independent benchmark.

## User jobs and experience principles

The immediate human job is to follow an assertion to its exact source, reconstruct the recorded evidence delivered before it, understand the limited result of a check, and leave a correction or unresolved question without overwriting the past. The following roles are proposed needs, not findings from user interviews.

| Role and intent | Question at the point of work | Required information | Useful exit |
|---|---|---|---|
| Analyst inspecting a report | What exactly was asserted, and where? | Original report, selected span, surrounding sentence, actor, assertion occurrence, normalized candidate tuple | Source-linked case with uncertainty |
| Trace investigator | What did this particular attempt receive, and what happened next? | Ordered input messages and roles, tool observations, call identity, output/error, propagation of earlier reports | Reconstructed observable context, with gaps |
| Reviewer resolving a challenge | Does this check bear on this assertion under its stated scope? | Method/version, inputs, expected/observed values, mapping assumptions, opposing evidence, source lineage | Scoped assessment or reason it remains unresolved |
| Collaborator comparing runs | Which differences can actually be compared? | Pair/run/config/fixture identities, exposure differences, distinct assertions and alignment rationale | Descriptive comparison with unmatched items visible |
| Maintainer picking up a case | Why was a label changed? | Earlier assessment, reviewer/reason/time, source snapshot, supersession history | Continue or reopen without losing history |

Prioritize source reversibility, readable context, uncertainty and a clear stopping point before optimizing navigation speed. A short number-only selection such as `2,540` is a valid exact span but is not self-explanatory: display its surrounding sentence and candidate entity/date/unit/modality. Absence, error, unselected text and disagreement must remain visible. A selected excerpt must never silently become the entire evidence record.

## What the inspected packet actually establishes

Read the shared brief, root plans and ledger handoff; all four design DOCX sources; session experiment, analysis, review packets and fixture; all six manifests, traces and final states; current draft ledger contract and pilot; existing worked audit and 30-minute report. Older DOCX proposals for five-arm evaluation and dashboards are historical hypotheses. The latest instruction defers independent evaluation and avoids committing to UI.

The local demonstration `inspect_cases.py` reads those session sources and the draft pilot, writes `source_cases.json` only in this lane, and makes no network/model calls. It records hashes, exact pointers and selected passages. It is a bounded source navigator, not an extractor coverage study, semantic verifier, or hidden-reasoning reconstruction.

| Case | Verified observation and precise anchor | Implication for the experience |
|---|---|---|
| Terra price | `terra-2f66dbe7f15d/final_state.json`, `/market_report`, decoded Unicode span `[334,353)` is `close of **$2,540**`. Exact report equals trace event 75 `/payload/response/generations/0/0/text`. Event 73 `/payload/messages/0/13/content` contains full snapshot content at `[615,783)`. | Open assertion, raw report, recorded input and check inputs as separate objects. Presence establishes delivered context, not causal reliance. |
| Sol snapshot omission | Pair-0 Sol market report explicitly acknowledges the required snapshot was not retrieved; all three Sol traces have no snapshot retrieval. CSV content is nevertheless present in recorded Sol inputs. | Tool compliance and factual support need separate findings. Missing the snapshot cannot alone establish a fabricated price claim. |
| Duplicated news | E_NEWS and E_GLOBAL declare the same root `S_SYNTHETIC_A`. Pair-0 Terra news `[483,819)` explicitly calls the note unverified and the digest a repeat; Sol news `[186,552)` makes the same distinction. | Show allegation modality and root lineage. Two tool items are not two independent confirmations. |
| Local context boundary | The News Analyst describes a lack of price data; Market Analyst inputs contain the price fixture. The demonstration records each news output's matched input and delivered evidence types. | Inspect the relevant call before challenging an agent-local missing-data statement from run-wide evidence. Shared run identity does not establish shared context. |
| Incomplete raw exposure downstream | Pair-0 Terra Portfolio Manager input event 211 embeds the investment and trader plans. The pilot identifies these as exact prior-report exposures; full original fixture contents are not matched there. Partial/paraphrased transmission remains unmeasured. | Report transmission must not be upgraded into delivery of the original price snapshot. A repeated 2,540 figure downstream is a new occurrence requiring its own context. |
| Failed attempt and fallback | `terra-085765f41f69`: error event 166 precedes a new attempt at 169 with output 171. There are 14 starts and 13 ends in that run; six runs total 1,253 events, 79 starts and 78 ends. | A completed workflow must retain the failed attempt. Do not display error as empty output or merge retry inputs into the earlier attempt. Sequence alone does not establish why fallback occurred. |

These are synthetic records with evidence as-of 28 October 2026 and execution on 30 October India time. Preserve both evidence time and execution time. CSV/snapshot agreement is not independent corroboration: both came from one synthetic fixture author. Current packet has no source withdrawal or agent correction after a changed fixture; later correction flows below are proposals.

The first inspected draft pilot had 830 rows, 26 assertions and 24 candidate propositions across two runs, with 47 typed checks (canonical hash `447379c005491f45dc3d342208c9c53e66a4a90dffb959ace16a78c9cd28b709`). During local generator reruns, the pilot evolved. The actual final delivered `source_cases.json` captured 869 rows and canonical hash `11939dc082539db59c40662a2dea008860a537e0232461428f8e75e4803cf62c`, corresponding to build identity `pilot-22629c0450f2dcba6087` observed during compatibility review. The earlier report incorrectly retained the 830-row summary; this paragraph corrects that mismatch. Both of those earlier snapshots used schema/normalization/extraction `1.0.0`; matching version numbers alone do not establish build compatibility.

The delivered case packet is now preserved byte-for-byte, including its five minimal selected assertion records, exact IDs, source references, manifest and implementation hashes. The complete earlier case JSON was overwritten during the earlier reruns and is not available to reconstruct; `ledger-reference-history.json` preserves the initial textual observation separately. No historical IDs are silently rebound. A later current-ledger walkthrough must wait for a coherent ledger handoff and create a separate versioned case packet.

The compatibility validation subsequently observed build `pilot-c29a7c43db89e7bea4c8`, canonical hash `433a733113449e2581700585a6afeddeee8f5a12d966cab66fe453facf64c374`, schema/normalization `1.1.0` and extraction `1.0.0`. Raw validation passed for all 16 anchors and 22 source files while the retained ledger reference was explicitly `stale_referenced_build`, with current requery disabled and no IDs rebound. This is an observed compatibility transition, not a regeneration of the case packet. Later build state may change again.

Selected Terra market assertions have conditional fixture `MATCH` and recorded-context `OBSERVED` results. Neither label establishes unrestricted support. Market/news/final reports are only partly selected; investment/trader plans and dialogue are not atomized. Coverage of characters is not recall of all meaningful assertions.

### The same assertion through all three alternatives

All three alternatives below use the same pair-0 Terra Market Analyst assertion: ETH-USD close of 2,540 USD on 28 October, within the synthetic fixture, at report span `[334,353)`. The draft pilot's smaller numeric occurrence is `assertions:d02ce9f79709146ff2484575eccfe558423e6a8192ab1a7834fb2bb9b2212f85`; keep the contextual quote alongside it.

| User job on that assertion | A — Case file | B — Recorded-context replay | C — Comparison worksheet |
|---|---|---|---|
| Find original wording | Start from occurrence; show source paragraph and exact span | Start from output 75, then locate span in its report | Start from candidate close proposition; open Terra occurrence and source paragraph |
| Reconstruct what was delivered | Follow explicit case reference to input 73 | Move from output 75 to the same attempt's input 73; inspect ordered messages | Expand the Terra delivery cell to input 73; keep Sol's different context separate |
| Understand check scope | Separate cards/paragraphs for alignment, conditional equality, protocol and interpretation | Annotate the attempt with those separate results, preserving raw events | Separate result columns; unmatched Sol numeric occurrence remains empty with a reason |
| Follow later transmission | Add linked note that Portfolio Manager 211 has prior reports, with full raw delivery unmeasured | Move chronologically to 211 without carrying earlier raw evidence forward implicitly | Compare stages only under explicit alignment; downstream repetition is a distinct occurrence |
| Leave uncertainty | Record a scoped assessment and unresolved mapping questions | Record a source/context investigation and hand off to assessment | Record an alignment proposal with unmatched rows and extraction omissions |

No option treats the Terra arithmetic match as proof that the final Hold is optimal. No option treats Sol snapshot noncompliance as a contradiction of Terra's price. The separate recovered Terra call-error case is an investigation detour in all three: case attachment in A, error/new-attempt sequence in B, and workflow diagnostic beside the affected pair in C.

## Alternative A — Assertion case file

**Best initial fit:** a reviewer has a specific claim or challenge and wants a reviewable answer they can hand off. The same file could be returned by a CLI command or API, read as Markdown, or navigated visually later.

Storyboard using the existing Terra close:

1. Start from the quoted report passage or a ledger assertion occurrence. The case opens with run/actor/field, exact quote, surrounding paragraph and source hash. The candidate tuple says ETH-USD, close, 2540 USD, 28 October, synthetic observation. The reviewer can correct the tuple without editing the quote.
2. Follow the report pointer to generation text at event 75. Open event 73 separately to inspect ordered messages and the literal snapshot exposure. Show fixture availability, backend retrieval, exact input delivery and citation as independent facts; do not draw an implied support edge between them.
3. Open the conditional numerical comparison. Show the candidate mapping, CSV row/column, observed value, expected value, method/version and narrow result. The full worked audit used Decimal equality after manual normalization. The case can also show a protocol check; one does not override the other.
4. Reviewer records a scoped note: numerical equality within the synthetic fixture, no independent real-world verification, and no conclusion about the Hold decision. If the time/unit/entity mapping remains disputed, leave that mapping unresolved while retaining the arithmetic result.
5. Export a portable case containing source references, version IDs, selected context and explicit omissions. Resume by stable case/occurrence identity rather than search text alone.

Tradeoffs: easy to read and share; useful before a broad graph exists. Selecting one claim can hide neighboring qualifications and related assertions. Attach the enclosing paragraph and a path to the full report; show candidate links as candidates. File export can become stale, so include snapshot hashes and mark when later assessments exist. Large prompts should be opt-in attachments, with omission indicators; a shared export must state whether it contains full recorded input.

Dependencies: occurrence IDs, reversible proposition mapping, precise span convention, raw artifact/event/JSON pointers, exact report-origin method, call exposure, check method/version and assumptions. Durable reviewer notes and supersession records are proposed additions; the current checks table is not evidence of a human review log. A report with unresolved origin remains inspectable as a saved report; context reconstruction stops at that gap.

## Alternative B — Recorded-context replay

**Best fit:** an investigator asks why the record appears inconsistent or whether an execution error disappeared. Implementable as a CLI sequence listing plus selected JSON excerpts or an API traversal; a visual timeline is optional.

Storyboard using omission and fallback:

1. Start with the same Terra price at output 75. Select its Market Analyst attempt and input 73, then view the exact original messages containing the snapshot. Keep source alignment, conditional equality, protocol compliance and provisional interpretation separate. View chronological attempt IDs with input/end/error boundaries. Global event sequence establishes recording order; it does not prove causality or a dependency.
2. At Market Analyst final input, inspect the actual ordered messages. Sol receives the CSV and unavailable indicators, while the snapshot is absent from preceding retrievals. Contrast the later report's explicit acknowledgement. Show available-but-not-retrieved evidence separately from delivered content. Preserve tool arguments and results, including requests whose fixture returned only three candles.
3. Switch to News Analyst's final input. Its raw evidence set can differ from the Market Analyst's. A statement about missing price evidence must be read in the agent's scope, not challenged by a run-wide union.
4. Follow the original Terra run to Portfolio Manager input 211: prior reports are present, but full raw snapshot delivery is not identified. Then inspect Terra pair-2 error 166, attempt 169/output 171 as a separate recovered-error case. The failed attempt stays visible and the later output remains attached to its own input. The recorded structured/free-text fallback path is visible in the trace/review; do not infer an agent's private recovery reasoning.
5. Leave an investigation note pointing to the particular input/output/error and any unresolved context. Hand off to a claim case only when the investigator identifies an assertion worth reviewing.

Tradeoffs: exposes context mixing, missingness and retries well; can overwhelm someone who needs one factual answer. Default to a compact event index and let the investigator expand original messages without discarding roles or ordering. Summarized context must link back to exact text and identify omitted portions. A local absence of a complete-content match means the matcher found no full exact delivery; paraphrases/partial passages remain unmeasured.

Dependencies: call/attempt boundaries, actor attribution, original message order/roles, tool-call IDs, evidence retrieval and exact exposure, errors, report handoff exposure and unresolved attribution. Replay here means reading recorded events. It never re-executes tools, calls models or simulates what an agent would have said with different evidence.

## Alternative C — Paired comparison worksheet

**Best fit:** an analyst wants to compare two recorded workflows without turning text length or evidence counts into a quality ranking. Start as SQLite queries or a reproducible notebook producing a small report; expose the same rows through a read API if another client needs them.

Storyboard using pair 0:

1. Select the recorded pair. Show fixture/config identities, actual run IDs, completion/error status, evidence as-of date and fresh-state scope. Pair membership comes from manifests/session records; similar timestamps alone are insufficient.
2. Group report occurrences by candidate proposition keys only where entity, predicate, units, time, scope and modality plausibly agree. Keep each original assertion and an `unmatched` group. The Terra exact close can remain unmatched when Sol withholds exact numbers; no claim is manufactured to fill a comparison cell.
3. Compare acquisition and delivery side by side: snapshot retrieval differs; available fixture is equal. For duplicated news, show original passages and declared common root, alongside the fact that both describe an allegation. E_NEWS versus fixture-URI citation syntax is a presentation difference until resolved to source identity.
4. Inspect the same Hold label with its separate rationale and missing target/horizon fields. A missing target is neither zero nor a forecast. Maintain separate columns for source alignment, exposure, numeric check, compliance and unresolved interpretation. Never calculate a single winner from these rows.
5. Save an alignment proposal or correction with reasons and versions. The worksheet exports actual matched and unmatched rows plus extraction omissions. A later mapping change creates a new comparison version; it does not rewrite either run.

Tradeoffs: good for finding specific inspectable differences; tempting to imply semantic equivalence or pseudo-statistical quality. Candidate alignment must be reversible; repeated assertions must not become independent observations. Three checkpoint pairs on one unchanged synthetic fixture cannot establish model superiority or belief-update behavior. More tool calls and more words are diagnostics, not votes for quality.

Dependencies: pair and workflow identities, separate session/workflow config hashes, extraction snapshot identity, occurrence/proposition distinction, coverage/omissions, source-root lineage and typed check results. If alignment cannot be justified, compare the source passages without merging propositions. Notebook output needs recorded query, data hash and versions; an API must return these metadata with results rather than just a bare verdict.

## Shared review states and recovery

Treat workflow state separately from semantic result. A proposed review lifecycle is `unreviewed → inspecting → recorded`, with `needs_information`, `disputed`, `reopened` and `superseded` available. A recorded review can still conclude unresolved. These are proposals, not statuses already implemented by the ledger.

| Condition | Honest user-visible state | Recovery and preserved record |
|---|---|---|
| No selected assertions | Report available; extraction coverage incomplete | Inspect full report or propose a new span; do not mark claim-free |
| Source hash or span mismatch | Source resolution blocked | Retain old reference, show mismatch, locate intended snapshot; never silently relocate by fuzzy search |
| Derived ledger has changed or is missing | Raw anchors may validate; referenced ledger is stale or unavailable | Keep captured minimal records/IDs/hash; block joins to a different build, avoid rebinding, and version any later regeneration after coherent handoff |
| Missing call origin | Saved text available; originating input unresolved | Stop context reconstruction; attach explicit candidate attribution if later found |
| No full-content exposure match | Exact delivery not identified by this method | Inspect partial/paraphrased context manually; preserve uncertainty |
| Error or interrupted query | Failed attempt / incomplete read | Resume from captured source version and query; distinguish no rows from query failure |
| Competing source interpretations | Disputed mapping or assessment | Store both with reasons and scope; do not resolve by last write or reviewer count |
| Corrected extraction | Prior annotation superseded | New mapping cites old mapping and reason; preserve all original assertions and check results |
| Corrected reviewer assessment | Assessment superseded, underlying run unchanged | Append new assessment with author/time/reason and explicit predecessor |
| Later agent output differs | Separate assertion occurrence | Claim an agent revision only with justified temporal/context linkage; reviewer correction is not agent correction |
| Source withdrawn in a future packet | New source-status observation | Revisit affected justification sets when explicit dependencies exist; do not automatically flip every downstream conclusion |

For later invalidation, a decision may have an alternative sufficient justification. The workflow must expose the challenged dependency and any remaining justification set. Current extraction does not establish complete causal dependencies, so an impact list must identify whether its links are declared, proposed or checked, and report unknown downstream coverage.

CLI and report alternatives should work through keyboard navigation, plain text, explicit labels and JSON exports. Any later visual view needs text-equivalent paths and cannot rely on color for verdict or uncertainty. Empty results, loading and source-resolution errors need distinct messages. Existing redaction remains part of the evidence boundary: redacted or inaccessible content cannot be reconstructed; exports should preserve those gaps and reviewer identity scope. No collaboration permissions or multiuser review authority have been selected yet.

## Contract questions for reconciliation

1. Can a consumer fetch one occurrence with enclosing context and the exact raw origin or unresolved status? Current numeric spans can be minimal; consumers need a stable way to retrieve surrounding text without expanding the proposition itself.
2. Will checks expose the normalized candidate mapping and scoped conclusion separately from the arithmetic/exposure result? A source span passing integrity does not validate its semantic interpretation.
3. What object stores reviewer assessments, mapping corrections, disputes and supersession? Keep it separate from immutable agent assertions and reproducible checks; decide authority before making labels operational.
4. How should candidate equivalence, source identity and citation attachment be accepted or rejected? Candidate merges and same-line references must remain reversible. Shared fixture authorship limits independence even when roots are not declared equal.
5. What is the contract for evidence/claim revisions and alternative justifications? Do not infer a total dependency graph from report embedding or treat upstream challenges as automatic decision invalidation.
6. Does a portable case embed raw contexts or carry references requiring the original packet? The first is easier to review offline but duplicates large, potentially sensitive prompts; the second can fail on handoff. Either needs explicit completeness and hashes.

## Recommended next learning step

As a future learning option, use the existing packets for one short manual walkthrough of two case-file tasks: resolve the scope of Terra's 2,540 comparison, then investigate Sol's missing snapshot without conflating it with numerical falsity. Add the duplicated-news passage if the reviewer needs a semantic ambiguity case. Record where the reviewer needs an extra field, context jump or state. This would test the usability and completeness of the evidence contract; it is not an independent factual benchmark or scoring exercise. No human walkthrough is authorized or has occurred.

Begin with Alternative A as a portable Markdown/JSON case assembled from the existing pilot; use B to recover context and C for one pair comparison. This recommends a learning order, not final product architecture. No new inference or fault injection is necessary. An actual human walkthrough has not occurred; do not report simulated reviewer reactions as evidence.

Validate the retained packet from Desktop TrustKernel:

```powershell
.\.venv\Scripts\python.exe -X utf8 explorations/evidence-workflows/validate_cases.py
```

Read `source_cases.json` for machine-resolvable anchors and hashes, and `notes/PLAN.md` for scope and pickup state. The historical generator `inspect_cases.py` now refuses to overwrite an existing captured packet. It used standard-library reads, source equality assertions, conditional Decimal equality after manual mapping, and exact selected-span checks; it neither executed the ledger builder nor changed existing evidence or other lane's artifacts.

`validate_cases.py` resolves 16 selected exact source anchors and checks 22 raw source-file hashes independently of derived-ledger compatibility. It reports `compatible_exact_bytes`, `stale_referenced_build` or `unavailable` for the retained ledger reference, without joining historical IDs to new rows. Negative cases cover shortened spans, mismatched raw hashes, stale derived ledger and unavailable derived ledger; the last two preserve raw validation success and prohibit rebinding. Historical validation is retained in `validation-captured-build.json`; current results are in `validation.json`. Earlier reruns reproduced the same final navigation packet. This validation concerns selected source integrity and compatibility, not semantic mappings, complete extraction or model quality.
