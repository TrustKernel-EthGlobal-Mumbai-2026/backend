---
name: engineering-review
description: Review code, diffs, or technical changes for concrete correctness, security, reliability, performance, and maintainability defects. Use for pull-request review, change audits, and pre-merge risk assessment. Do not use for general style commentary, implementation planning, or redesign without an actual change to inspect.
---

# Engineering Review

Read [the shared engineering principles](../../harness/references/engineering-principles.md).

## Workflow

1. Establish the intended behavior, scope, base state, and verification already performed.
2. Inspect the actual change and relevant surrounding code, callers, tests, and contracts.
3. Trace data, state, errors, authorization, concurrency, and lifecycle across boundaries.
4. Look for behavior regressions, invalid assumptions, edge cases, missing migrations, and tests that cannot detect the failure.
5. Report only actionable findings supported by the code.

## Finding standard

Each finding should identify the defect, triggering conditions, concrete impact, exact location, and a viable correction direction. Prioritize by impact and likelihood.

Lead with findings. If there are none, say so and note material residual uncertainties. Avoid praise, style preferences, broad refactors, or speculative concerns without a plausible failure path.
