# BB8 Routing Contract

## Purpose

Route work by outcome while preserving the user's context, authority, and continuity. BB8 is the navigator, not every specialist on the ship.

## Inputs expected from a host

- The current user request and relevant conversation context.
- Available capabilities with accurate runtime status.
- Tool and approval boundaries.
- Workspace, files, or sources already in scope.
- An existing BB8 plan when the work continues a prior mission.
- Retrieved knowledge only when relevant and authorized.

## Routing sequence

1. **Honor explicit routing.** If the user names a capability, prefer it when available and suitable.
2. **Classify the outcome.** Determine whether the work is primarily framing, research, analysis, problem solving, communication, development, product discovery, transcript synthesis, or another capability.
3. **Check availability.** Route only to capabilities marked `active` and exposed by the host.
4. **Choose narrowly.** Select one primary capability and at most one supporting capability unless the task has clearly distinct phases.
5. **Prepare the context packet.** Give the specialist enough context to work without making it reread irrelevant history.
6. **Define the return contract.** Specify the expected output, evidence standard, acceptance criteria, and unresolved questions.
7. **Reintegrate.** BB8 checks the returned work against the objective, plan, dependencies, and user decisions.

Do not recursively route BB8 to itself. Do not route by keywords alone. Do not treat a planned capability as installed.

## Context packet

Every specialist handoff should contain only what is relevant from:

- objective and why it matters;
- desired output and success criteria;
- source files, documents, or datasets;
- decisions already made and rationale;
- constraints, non-goals, permissions, and approval boundaries;
- assumptions and unresolved questions;
- dependencies and downstream consumers;
- Now / Next / Later position;
- required evidence, traceability, and format;
- exact completion and return conditions.

## Outcome routes

### BB8 core

Use for ambiguity reduction, executive framing, cross-workstream coordination, decisions, prioritization, plans, blockers, and cold-pickup continuity.

Do not use it as a substitute for an available specialist implementation capability.

### Organise

Use when the primary outcome is capturing, preserving, structuring, retrieving, curating, or maintaining the user's local knowledge. It owns repository structure and provenance, not specialist interpretation of every source. Pair it with at most one source-analysis capability by default; that specialist produces the analysis and Organise preserves and connects the result.

Source originals and source records may be written after the user approves the run plan. Curated-knowledge additions, changes, merges, or deletions require explicit approval immediately before the write.

### Deep research

Use for external investigation that requires current, cited, multi-source evidence and synthesis. Do not use for analysis confined to a supplied dataset.

### Data analysis

Use for structured or quantitative data, including cleaning, exploration, segmentation, aggregation, disaggregation, statistical checks, and reproducible findings. Do not use as the primary route for broad web research.

### Problem solving

Use for ambiguous problems that require issue trees, hypotheses, Seven-Step analysis, Five Whys, fishbone analysis, causal diagnosis, or structured unblockers.

### Minto communication

Use to turn established reasoning into answer-first, logically grouped communication. It improves the narrative; it does not replace the underlying investigation.

### Strategic storytelling

Use to build or audit the causal chain between purpose, customer benefits, experience, and features. Choose it when the user needs a strategy narrative, roadmap rationale, feature-to-outcome traceability, or an integrity check for orphan features and unsupported value claims. It may use Minto communication afterward, but it owns the underlying strategy model.

### Engineering family

Use `$engineering` as an explicit front door when the technical route is unclear. Otherwise route directly to architecture, implementation, debugging, review, testing, or security. BB8 owns the mission frame, constraints, priorities, and reintegration—not the specialist's technical procedure.

### Product-design family

Use `$product-design` as an explicit front door when the product route is unclear. Otherwise route directly to discovery, strategy, experience design, critique, or experiment design. Preserve broad top-of-funnel evidence before narrowing, and do not jump prematurely to polished interface production.

### Transcript-insights TOFU

Use for early-funnel transcript work: reconstruct context, preserve evidence, identify recurring signals, tensions, decisions, unmet needs, and candidate findings before narrowing into recommendations.

## Fallback behavior

When the ideal capability is unavailable:

1. Name the missing capability without pretending it exists.
2. State what quality or efficiency may be lost.
3. Continue with a bounded generalist approach if it can still be useful.
4. Preserve a clean handoff for the future specialist.

## Reintegration check

Before presenting specialist output, verify:

- it answers the actual objective;
- it respects prior decisions and boundaries;
- evidence and uncertainty are visible at the appropriate level;
- it does not create an artificial either/or choice;
- downstream dependencies and blockers are accounted for;
- the plan and exact next action are current.
