# Verification semantics and mathematical checks

Exploratory recommendation, 30 October 2026. No taxonomy, schema or integration is approved by this packet. Semantic mappings below are worker-authored proposals. The local checks establish specific equalities and graph behaviors under those mappings; they are not independent labels, a benchmark or a general truth score.

TrustKernel should preserve separate check findings and, if useful, derive a support summary for a declared evidence scope. A single mutable claim label cannot explain the existing examples without hiding important differences. For dependency changes, record which sufficient justification paths survive. Losing a path calls for reconsideration; it does not establish that the conclusion is false.

## What was inspected

Authority and scope: `explorations/BRIEF.md`, root `PLAN.md`, `ANALYSIS_PLAN.md`, and `verification/HANDOFF.md`. The parent's recent human turn authorizes parallel exploratory chats reporting to the orchestrator and defers independent evaluation. Current draft interfaces: `verification/CONTRACT.md`, `schema.json`, relevant exposure code, and pilot artifacts. The ledger contract inspected declares schema/normalization/extraction 1.0.0; captured hashes in `notes/source-packet.json` identify the exact versions used here. Do not assume later files with the same name or version have identical content.

Context: all four DOCX documents in `references/`, extracted as plain paragraphs into this lane's notes. They describe source-linked claims, revision, freshness and dependency concerns. Their older benchmark and three-hour implementation proposals do not override the brief. No DOCX layout, live sponsor requirement or cited external paper was investigated in this lane.

Evidence: frozen session `runs/20261030-010033-30min-597a75`, its fixture, experiment, analysis and review packet; existing worked numerical audit and final review in the original chat's outputs. Detailed new examples use pair 0, `sol-0530a9827c2c` and `terra-2f66dbe7f15d`. All six runs' trace/SQLite/manifest/final-state files were hashed as a source inventory; this is not a fresh full six-run semantic audit. Raw evidence was not edited.

The companion `notes/source-packet.json` contains twelve selected report spans R01–R12, enclosing paragraphs, decoded JSON pointers, zero-based Unicode code-point offsets [start,end), file hashes and, where directly matched, original output-event pointers. Full report headers supply additional candidate normalization context; a short numeric span alone is insufficient. It also records thirteen early input contexts and explicit evidence-decoding references. Final-decision examples use final-state pointers; the packet does not claim a direct full-text response match for their formatted output. The ledger's separate structured-rendering contract is relevant to that join. Captured pilot build identity is `pilot-22629c0450f2dcba6087`; its canonical hash and implementation-to-manifest comparisons are retained separately from the current draft interface snapshot. The captured current `ledger.py` hash differs from that pilot's declared implementation hash, while selections and contract match. This is expected to be possible during active exploration, not evidence of a defect. Current decoder capabilities cannot automatically be attributed to the earlier pilot. Our example checks use the frozen traces directly, without rebuilding or modifying the ledger.

## Existing examples that constrain the rules

| Ref | Recorded example | Mechanically established | Remaining interpretation |
|---|---|---|---|
| R01 | Terra market report, `close of **$2,540**`, [334,353), output 75, input 73 | Decimal equality to E_PRICE last row and snapshot; snapshot and CSV recoverable in input | Normalizing this phrase to ETH-USD close on 2026-10-28 within the synthetic fixture is a proposed mapping. Equality does not establish actual ETH price or internal source reliance. |
| R02 | Sol, daily highs and lows rise, [1554,1615), output 69, input 67 | Highs 2550<2580<2600; lows 2480<2500<2510 | A durable bullish trend requires an additional interpretation and adequate domain evidence. |
| R03 | Sol, daily high-to-low ranges widen, [2827,2886) | High−low gives 70,80,90 USD | This is not an ATR series. A volatility-regime conclusion is a separate inference. |
| R04 | Sol, required snapshot not retrieved, [871,971) | Instruction says to call it before final report; no preceding snapshot retrieval in the completed market trace prefix | This establishes a scoped protocol finding. Tool-round exhaustion is context for attribution, not proof of numerical falsity. CSV facts remain checkable. |
| R05 | Terra, snapshot provides no earlier volume series, [736,845) | E_SNAPSHOT includes latest volume only; input 73 also carries decoded E_PRICE with 10000,12000,15000 | Snapshot-only reading is supported; a claim that the whole input lacks earlier volumes would conflict with the CSV. Whether three volumes identify an unusual-volume baseline is another question. |
| R06 | Sol news, same root `S_SYNTHETIC_A`, [1111,1169) | Fixture declares the same root for E_NEWS and E_GLOBAL | This establishes declared common lineage, not comprehensive forensic verification of real publishing provenance. |
| R07 | Terra, alleged demand increase, [483,645), output 141, input 139 | E_NEWS explicitly says a note alleges increased demand | Supports that an allegation was supplied. Does not establish increased demand, or establish that demand did not increase. |
| R08 | Terra news, no price/volume supplied, [821,925) | No complete E_PRICE or E_SNAPSHOT exposure detected in its input 139, including recognized JSON envelopes; both exist in the run's fixture | Plausible actor-local absence versus apparent run-global inconsistency. Preserve the scope question instead of automatically labeling contradiction. No broad absence proof from one matching method. |
| R09 | Sol news, missing data is not zero probability, [3544,3603) | E_PREDICTION returns NO_DATA; no numeric probability is supplied | Missingness cannot be coerced to zero. Real-world event probability is unresolved. |
| R10 | Terra final decision, maintain exposure if limits fit, [97,219) | Exact conditional recommendation exists | Holdings, constraints and loss limits are unobserved here. Policy suitability is not implied by supported prices. |
| R11 | Terra, $2510/$2600 investigation points rather than validated stops, [358,459) | Levels equal last-row low/high | Their use as stop levels would require a method and policy; the report explicitly limits their role. |
| R12 | Sol final decision, Time Horizon not provided, [3133,3163) | Field records a missing horizon | It is not a numeric horizon, resolved prediction or failed forecast. |

The escaped-CSV case is important. Input messages contain a tool-result JSON envelope inside a string. Its `content` field represents CSV newlines using JSON escapes. Literal full-content substring search misses E_PRICE in both market inputs. Recognized-prefix JSON decoding recovers exactly the frozen content. The packet preserves that transformation and source message pointer. The inspected ledger code already supports a related decoding path; this is a demonstrated requirement, not a reported ledger defect. Even recovered content proves recorded delivery, not attention or private reasoning.

Volume units remain unspecified beyond the fixture's column label; do not silently treat Volume as USD, ETH or contracts. USD is the declared price quote. Strong quantity checks need unit information at the field level.

## Three meaningful formulations

| Option | What it preserves | Atomic data required | Cost and failure mode |
|---|---|---|---|
| A. Typed findings with an optional single support view | Independent facts plus a compact summary | Assertion and evidence references; method/version; scope; prerequisites; expected/observed; status/reason; normalization provenance | Smallest change. A summary must name precedence and scope; otherwise conflicts and incomplete searches disappear. It cannot by itself express alternative derivations. |
| B. Factored assessment record | Numerical relation, provenance, visibility, temporal eligibility, modality/scope, lineage, protocol, assumptions and policy as separate results; support/opposition witnesses remain distinct | A's fields plus assessment context, positive/negative witness IDs, searched corpus/completeness and assumption identities | More explicit query contract. Missing cells must mean unexamined/inconclusive, not failure. Dimensions are explanatory proposals, not independent probabilistic variables. |
| C. Factored findings with sufficient justification sets | B plus why support survives or fails after premise changes | B plus typed dependency target, justification ID/members, AND/OR semantics, inference/bridge rule, acceptance status, effective/recorded times, supersession and recalculation lineage | Best fit for invalidation exploration. Semantic sufficiency is costly and can be wrong. Full graphs can explode; begin with two hand-specified sets, not exhaustive extraction. |

Bounded recommendation: use A as a thin append-only check envelope, explore B's views on the twelve cases, and demonstrate C on explicit hypothetical sets. A and B are compatible storage/view choices. Do not implement C as an automatic propagation engine or require a new universal ontology before the ledger is useful. Keep UI choices independent of this experiment.

## A precise provisional state view

Let an assessment context K declare the proposition mapping, evidence corpus/snapshot, actor/call if relevant, admissibility rules, inference methods and evaluation time. A corpus may be the frozen repository, exact recorded call context, a trusted report handoff, or the agent's cited rationale. These answer different questions; none silently substitutes for another.

Let s mean at least one admissible sufficient witness supports p under K, and c mean at least one admissible sufficient witness supports a materially incompatible proposition under K. These are existence flags, not probabilities or confidence values.

| s | c | Derived view | Required qualification |
|---|---|---|---|
| true | false | Supported under K | Absence of an opposition witness is relative to the recorded search, not proof that no contradiction exists. |
| false | true | Contradicted under K | Show the contrary witness, compatible time/scope/modalities and accepted incompatibility rule. |
| true | true | Conflicting evidence; unresolved reconciliation | Preserve both witnesses. Do not choose by article count or let arbitrary ordering overwrite one. |
| false | false | Unsupported in the checked corpus, or unresolved | Unsupported is justified only when the bounded search and support obligation are declared complete. Otherwise unresolved with the missing prerequisite. |

“Unresolved” should carry a reason: unexamined, ambiguous normalization, incomplete evidence search, temporal ambiguity, uncertain source identity, competing witnesses, disputed assumption or unsupported inference rule. It is not merely a softer synonym for unsupported. A prediction with a future horizon may have ex-ante support while outcome is pending; these need separate records. A policy recommendation may be outside a factual-support check's domain.

Do not make STALE compete with SUPPORTED as one mutually exclusive state. A historical October 28 observation can remain correctly supported on October 30, while reuse as a current quote can fail a freshness policy. A missing valid-until time is unknown eligibility, not infinite freshness. No freshness threshold is selected here. Likewise, a noncompliant workflow can contain a correct numerical statement, and a provenance-valid statement can be semantically unsupported.

Deterministic results use PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE/ERROR relative to a specific check contract. These operational results are not claim-truth labels. FAIL of span integrity makes downstream checks unreliable; it does not contradict the quoted proposition. ERROR is a check execution failure; it must not be counted as unsupported. A failed model attempt and a successful fallback retain distinct call/input scopes: do not union their inputs into a fictional successful context.

Execution receipts, service/model provenance and database publication establish different facts from semantic support. A platform attesting that computation occurred or storing a digest cannot make its inputs true or its conclusion supported. These remain separate checks for any future sponsor extension; no adapter is selected here.

## Alternative justification sets and invalidation

For an explicit set of sufficient justifications J(p), support is an OR over sets of an AND over prerequisites:

`support(p,K) = exists j in J(p): rule_accepted(j,K) AND every member m of j is eligible and established under K`

Each set must include its bridge assumptions and normalization/inference method. A flat list of SUPPORTS edges does not tell us whether all premises are jointly necessary or any one is sufficient. Unknown or proposed members cannot silently count as established. A contradictory witness remains a separate signal even if a support path survives.

For R01, the local demonstration proposes, rather than extracts, these sets:

- J1 = {accepted common fixture context F, accepted normalization N, CSV last-row equality C}.
- J2 = {F, N, snapshot equality S}.

Removing S disables J2 while J1 still supports the scoped close. Removing F or N disables both. Losing every route means support is no longer established under these rules; it does not derive close≠2540. If a new admissible snapshot says 2541, preserve opposing evidence and the reconciliation question. Calling the two routes independent would be wrong: F is shared. If a policy makes the snapshot authoritative, that policy must be an explicit prerequisite/precedence rule and can change the result; provenance alone does not choose it.

For dynamic caches, invalidating one node should enqueue its reachable justification sets and dependants for recomputation. A set is affected even if the conclusion survives through another set. Pure positive propagation is monotone only while evidence is added without retractions, expiry, defeaters or policy changes. Current-context findings need recalculation when those change. Negative premises such as “no corroborating evidence in this bounded corpus” also depend on corpus membership; a new source can invalidate them without altering an old artifact.

Keep two questions distinct: “Is the proposition supported anywhere in the admissible corpus?” and “Does this agent's stated rationale still justify its conclusion?” A newly found CSV can salvage the first while a snapshot-dependent stated rationale remains broken. Never silently rewrite the agent's dependency record to make it look grounded. Candidate extractor links may nominate affected items for review; they cannot establish an actual reasoning dependency.

Historical states are append-only: at context K0 both routes may be established; at K1 a retraction or rule revision invalidates J2. Preserve the K0 assessment and create a K1 successor with its cause. A current reassessment of old evidence is a new view, not a replacement for what was visible at the original call. Store evidence effective time and the time the change became recorded separately. Unknown alternatives or graph incompleteness require a bounded conclusion: “no surviving recorded justification,” not “no possible justification.”

Cycles need a grounded base. A→B→A alone establishes neither. Restrict the first demonstration to acyclic, explicitly supplied sets, or use a least-supported fixed point with no ungrounded seeds. Edges can carry different obligations: evidential support, historical derivation, citation, protocol and decision policy must not all inherit the same invalidation meaning.

The Hold decision's scope in R10 illustrates why generic “taint” is too strong. A price-support path may disappear while a separate portfolio-risk policy still calls for review or no change. The logs do not establish that policy's actual holdings inputs. Record affected rationale, unknown applicability and any surviving policy path; do not declare Hold false or automatically prescribe another action.

## Determinism ends at the declared mapping

Arithmetic proves equalities, ordering and transformations on selected inputs. It cannot select the intended entity, predicate, horizon, modality or corpus from arbitrary prose without interpretive choices. Pairwise contradiction requires compatible entity/unit/time/scope plus incompatible values or predicates. “The note alleges demand rose,” “demand rose,” and “demand may rise if yields fall” are different claims. “Direction unresolved” and “rising highs in three candles” can coexist.

Approximate numeric claims need explicit rounding/tolerance conventions. A recorded rounded value denotes an interval under such a convention; overlapping intervals do not prove contradiction. A percentage move needs endpoints, denominator, sign, scale and rounding. Sample-volume increases do not prove unusual volume without a baseline. Three closes allow a declared three-point average, even though the fixture says its requested indicators are unavailable; “unavailable returned series” and “mathematically impossible to compute any indicator” are different propositions.

No composition of correct prices and matched citations proves an optimal decision. That requires decision objectives, position state, constraints, alternatives and a policy, plus later outcome evidence for outcome questions. Those are largely unavailable here. Numeric confidence or an aggregate reliability score would conceal these gaps; none is proposed.

## Smallest useful next step and decisions to resolve

Reconcile the check-envelope fields and twelve examples with the ledger owner, retaining semantic mappings as provisional. Exercise two sufficient justification sets against a copied local example and retain before/after contexts. This needs no new model run, no external research and no independent benchmark.

Open decisions for the orchestrator:

1. Which corpus does the first support view assess: recorded direct input, trusted handoff, cited rationale or repository evidence? Can several views coexist with explicit context IDs?
2. Does the snapshot instruction govern protocol only, or also factual precedence when sources disagree? The recorded instruction treats it as authoritative; the analytical view should expose that policy rather than silently assume universal authority.
3. What explicit completeness declaration permits an UNSUPPORTED label? Is an unresolved conflict a separate label or a reason attached to unresolved?
4. How are evidence-interpretation assumptions accepted, disputed and versioned without pretending independent adjudication has occurred?
5. What temporal precision/freshness rules apply to synthetic as-of dates, historical observations and later current-use claims?
6. How are sufficient sets and negative corpus-dependent premises represented without overclaiming extracted dependencies? Should candidate links only create review tasks until accepted?
7. Which decision-policy checks are meaningful before holdings, constraints and utility are available?

No approval is needed to review this packet. Integration, a judge engine, feedback, spending and new experiments remain outside this lane's authorized work.

## Reproduction and measured scope

From `${PRIVATE_SOURCE_ROOT}`:

```powershell
.\.venv\Scripts\python.exe explorations\rules\source_packet.py
.\.venv\Scripts\python.exe explorations\rules\local_demo.py
```

The scripts use the Python standard library, do not import the runner and write only `explorations/rules/notes/`. The demonstrated run passed 51 mechanism assertions: hashes/spans, arithmetic, recorded exposure distinctions, bounded snapshot acquisition, historical/current contexts and hand-authored dependency/interval counterexamples. One unasserted derived-numeric illustration is recorded separately. This is a check of these mechanisms on selected inputs; the count measures neither semantic accuracy nor coverage. `CHECK_CONTRACTS.md` gives proposed check boundaries; `test-vectors.json` distinguishes actual recorded observations from counterfactual mutations and policy questions.
