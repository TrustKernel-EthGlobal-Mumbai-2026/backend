---
name: engineering-architecture
description: Design or evaluate software architecture, component boundaries, interfaces, data ownership, coupling, cohesion, and separation of concerns. Use for system design, refactoring boundaries, service decomposition, and consequential technical tradeoffs. Do not use for line-level implementation, isolated bugs, or routine code review.
---

# Engineering Architecture

Read [the shared engineering principles](../../harness/references/engineering-principles.md).

## Workflow

1. Establish functional goals, quality attributes, constraints, scale, lifecycle, and likely change vectors.
2. Model the current system and the forces creating the architecture decision.
3. Identify responsibilities, owned state, trust boundaries, and reasons to change.
4. Generate credible options, including a minimal-change option.
5. Compare options across complexity, coupling, operability, security, performance, migration risk, reversibility, and team ownership.
6. Define interfaces, invariants, failure behavior, data flow, and observability.
7. Produce a staged migration and identify decisions that should be recorded.

## Output

Provide the recommended boundary model only when asked to choose; otherwise present conditions favoring each option. Include a system view, tradeoff table, risks, migration path, and open decisions.

Reject layer creation that does not create a meaningful boundary. Do not claim "decoupling" when runtime, data, or release coupling remains hidden.
