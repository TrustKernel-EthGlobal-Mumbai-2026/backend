---
name: engineering-debugging
description: Diagnose software failures, regressions, incorrect behavior, and performance problems through reproduction, evidence collection, hypothesis testing, root-cause isolation, and verified fixes. Use when something is broken or unexpectedly slow. Do not use for speculative architecture redesign without an observed failure.
---

# Engineering Debugging

Read [the shared engineering principles](../../harness/references/engineering-principles.md).

## Workflow

1. Define expected versus observed behavior, impact, frequency, environment, and last-known-good state.
2. Reproduce or obtain the closest reliable signal. Preserve the failing input and exact conditions.
3. Bound the fault across time, components, data, users, and environments.
4. Build competing hypotheses and rank them by explanatory power and test cost.
5. Add or inspect observability at boundaries; change one informative variable at a time.
6. Identify the root mechanism, contributing conditions, and why existing controls missed it.
7. Implement the smallest complete fix, add a regression check, and verify adjacent behavior.

## Contract-first rule for agent/tool regressions

When an agent stops before a downstream tool call, inspect the executable contract
before changing prompts, models, retries, or timeouts. In the first diagnostic pass:

1. Reconstruct the exact chain from completed user turn to model-selected tool,
   returned payload, next tool schema, and spoken claim.
2. Compare the producer's actual output fields with every required input of the
   next tool. Pay special attention to canonical IDs that may have been replaced
   by patient-facing labels or omitted during enrichment.
3. Execute the intended tool chain with the same fixture or persisted state. This
   distinguishes missing data from data that exists but is unreachable through
   the exposed contract.
4. Treat a downstream tool that was never requested as an orchestration or contract
   failure, not a service outage. Do not accept an assistant claim that retrieval
   failed unless a corresponding tool attempt is present in telemetry.
5. Fix the producer/consumer boundary, then add both a contract regression test and
   an evaluation negative control that reproduces the misleading spoken outcome.

Prompt reinforcement may support a complete contract, but it must not conceal a
missing field or become the primary repair for a deterministic interface defect.

## Output

State the symptom, reproduction, root cause, evidence, fix, verification, residual risk, and prevention opportunity.

Do not confuse correlation with cause. Do not "fix" by swallowing errors, weakening tests, increasing timeouts without mechanism, or deleting evidence.
