---
name: engineering-testing
description: Design a risk-based software verification strategy across unit, contract, integration, end-to-end, property, performance, and operational tests. Use when deciding what to test, closing coverage gaps, or making a change safely verifiable. Do not use merely to maximize coverage metrics or duplicate implementation details in tests.
---

# Engineering Testing

Read [the shared engineering principles](../../harness/references/engineering-principles.md).

## Workflow

1. Identify user-visible outcomes, system invariants, failure modes, and highest-risk boundaries.
2. Map each risk to the cheapest test level that can detect it reliably.
3. Use unit tests for local logic, contract tests for boundary assumptions, integration tests for real component interaction, and end-to-end tests for a small number of critical journeys.
4. Add property, fuzz, concurrency, migration, performance, resilience, or security tests when the risk warrants them.
5. Define fixtures, observability, determinism, and failure diagnostics.
6. Remove redundant tests that add maintenance cost without distinct detection value.

## Output

Provide a risk-to-test matrix, priority order, fixtures or environments, and clear pass conditions.

Do not use coverage percentage as a proxy for confidence. Test behavior and contracts, not private implementation shape, unless that shape is itself an invariant.
