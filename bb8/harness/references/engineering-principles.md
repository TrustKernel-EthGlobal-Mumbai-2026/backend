# BB8 Engineering Principles

Apply these as decision criteria, not slogans.

## Separation by reason to change

Separate responsibilities when they change for different reasons, have different owners, require different scaling or security boundaries, or benefit from independent testing and deployment. Do not split code merely to create more layers.

Keep policy separate from mechanism, domain logic from transport and persistence, orchestration from computation, reads from writes when their needs materially differ, and reversible choices from irreversible commitments.

## Boundaries

A good boundary has a clear purpose, explicit inputs and outputs, owned state, constrained side effects, failure semantics, and tests at the contract. Minimize knowledge that crosses it.

Prefer high cohesion within a component and low, explicit coupling between components. Treat temporal coupling, shared mutable state, hidden globals, and cross-layer data leakage as design smells.

## Simplicity and changeability

Choose the simplest design that meets current requirements and preserves likely change paths. Avoid speculative abstractions. Duplicate small amounts of code when the supposed abstraction would couple unrelated concepts.

## Correctness and observability

Make invariants explicit. Validate at boundaries. Design idempotency, retries, concurrency, timeouts, and partial failure intentionally. Provide enough structured telemetry to distinguish expected variation from defects without exposing secrets.

## Security and privacy

Use least privilege, minimize retained data, treat external input as untrusted, keep secrets out of code and logs, and make authorization checks close to protected actions. Security boundaries should align with ownership and data boundaries where practical.

## Delivery

Prefer small vertical slices with observable outcomes. Keep migrations reversible or staged. Pair changes with proportionate tests and rollback or recovery paths. Document consequential decisions and rejected alternatives.

## Review questions

- What responsibility and reason to change does each component own?
- Which assumptions cross a boundary?
- Where can partial failure leave inconsistent state?
- What becomes difficult to test, replace, or observe?
- Which choice is hard to reverse?
- Is complexity paying for a real requirement?
