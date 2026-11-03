---
name: engineering-implementation
description: Turn an approved technical objective or design into an executable implementation plan with repository-grounded changes, vertical slices, migrations, verification, and rollback. Use before substantial coding or when sequencing matters. Do not use to decide unresolved product strategy or perform a post-hoc code review.
---

# Engineering Implementation

Read [the shared engineering principles](../../harness/references/engineering-principles.md).

## Workflow

1. Inspect the relevant repository, conventions, tests, and current change state.
2. Restate the desired behavior, non-goals, constraints, and acceptance criteria.
3. Map affected components, interfaces, data, callers, and operational dependencies.
4. Identify unresolved design choices before pretending implementation is mechanical.
5. Sequence small vertical slices that remain buildable and verifiable.
6. Include schema or data migration, compatibility, feature flags, telemetry, rollout, and rollback where relevant.
7. Define tests and observable completion signals for every material slice.

## Output

Produce a file- and component-aware plan with dependencies, risks, verification, and Now/Next/Later. When authorized to implement, execute the smallest safe slice and verify it before expanding.

Do not write plans that merely repeat ticket language. Do not invent files or APIs that have not been inspected.
