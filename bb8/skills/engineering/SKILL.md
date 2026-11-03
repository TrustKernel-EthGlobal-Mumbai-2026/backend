---
name: engineering
description: Explicit front door for the BB8 software-development skill family. Use when the user invokes engineering help but has not chosen architecture, implementation planning, debugging, code review, testing, or security. Route to the smallest appropriate engineering specialist and preserve the shared mission context. Do not use for non-technical strategy or product discovery.
---

# Engineering Router

Clarify the engineering outcome, constraints, repository scope, risk, and definition of done. Then route to one primary specialist:

- `$engineering-architecture` for system boundaries, interfaces, data ownership, separation of concerns, and tradeoffs.
- `$engineering-implementation` for an executable change plan, sequencing, migrations, and delivery slices.
- `$engineering-debugging` for failures, regressions, performance problems, and root-cause isolation.
- `$engineering-review` for reviewing code, diffs, designs, or changes for concrete defects.
- `$engineering-testing` for risk-based verification strategy and test design.
- `$engineering-security` for threat modeling, security review, and hardening.

Use at most one supporting specialist unless the work has distinct phases. Carry forward the objective, current evidence, constraints, permissions, affected files, acceptance criteria, and unresolved questions.

Do not perform a shallow pass across every specialist. Choose the route that most directly unlocks progress.
