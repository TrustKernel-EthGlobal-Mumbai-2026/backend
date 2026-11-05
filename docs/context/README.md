# Context map

Current state lives in [the root README](../../README.md#active-state--5-november-2026). Read that before historical results. This map is for another person or agent picking up work without access to the original chats.

| Question | Read first | Implementation / evidence contract |
|---|---|---|
| Which parallel chat owns implementation and what is blocked? | [Active orchestration board](../continuous/ORCHESTRATION.md) | Four isolated branches, contract-first dependency gates and explicit acceptance evidence |
| What are we working on next: async capture, agent feedback and CLI/SDK/MCP? | [Continuous verification plan](../CONTINUOUS_VERIFICATION_PLAN.md) | Proposed successor contracts and replay-first milestones; not implemented |
| Why does this product exist? | README purpose and preserved decisions; [decision record](../DECISIONS.md) | [Architecture](../ARCHITECTURE.md) |
| What happened across the chats? | [Session/workstream map](SESSION_MAP.md) | [Dated history](../research/HISTORY.md), [source fingerprints](../research/SOURCE_INDEX.json) |
| What did the latest verification establish? | [Latest run](LATEST_RUN.md) | live_verification/LEDGER.md and RULES_POLICY.md |
| How are passages and decisions extracted? | verification/REFINED_README.md; live_verification/LEDGER.md | verification/processing.py, refine_rules.py; live_verification/ledger_corpus.py, ledger_extract.py |
| What does a verification PASS mean? | live_verification/RULES_POLICY.md | live_verification/rules.py and rules_checks.py |
| Is stale evidence detected and corrected in a real agent? | [Open questions](QUESTIONS.md); [latest run](LATEST_RUN.md) | procedural_loop/ synthetic mechanism; recorded_loop/ source replay; live feedback still open |
| How do sources reach a model? | live_experiment/SOURCES.md and ARM.md | trustkernel/observer.py; live_experiment/sources.py and source_http.py |
| Is this portable to arbitrary agents? | README compatibility row; explorations/evidence-workflows/ | procedural_loop/contracts.py and adapters.py are illustrative shapes, not universal adapters |
| What is the frontend direction? | drafts/frontend/ and [workstream map](../WORKSTREAMS.md) | Draft graph-led inspection only; backend verification remains separate |
| What is the sponsor strategy? | explorations/sponsor-fit/ | Historical proposals; no execution or verified current eligibility |
| How do I use BB8 here? | [BB8 snapshot](../../bb8/README.md), [AGENTS](../../AGENTS.md) | .agents/skills/bb8/SKILL.md; snapshot specialist guidance |
| What is intentionally absent? | [Artifact policy](../ARTIFACT_POLICY.md) | Private source packets, accounts, source caches and budget state are excluded |

Paths in the implementation column are relative to the repository root. Use the index rather than guessing the exact filename:

```text
python -S -B tools/context_index.py build
python -S -B tools/context_index.py search "snapshot omission" --limit 5
python -S -B tools/context_index.py search "semicolon corrected refinement" --limit 5
python -S -B tools/context_index.py search "real agent feedback missing" --limit 5
python -S -B tools/context_index.py check
```

The committed context-index catalog and chunk metadata supply relative paths, line ranges and hashes. The local FTS5 cache stores searchable source text and can be rebuilt without an account or model. Stale/corrupt/missing caches are rejected with a rebuild command; snippets must not silently outlive their source.

## Status vocabulary

**Current:** root README and these continuation documents. **Recorded:** dated research outcomes with scope and source fingerprints. **Provisional:** extracted candidates, proposed reasons/dependencies and undecided policies. **Draft:** frontend and unexecuted integrations. **Snapshot:** frozen BB8 guidance, not live host capability. **Private/not included:** evidence whose identity or outcome is summarized but whose original content is unavailable in a fresh clone.

There is no semantic search or truth oracle implied by this lexical index. A high search rank does not establish correctness, recency or authority. README is the current-state entry point; dated source results remain attached to their original experiments.
