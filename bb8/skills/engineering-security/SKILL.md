---
name: engineering-security
description: Threat-model or review authorized software for trust boundaries, abuse cases, vulnerable data flows, privilege errors, unsafe defaults, and practical mitigations. Use for security design and focused hardening. Do not use for unauthorized access, generic compliance claims, or ordinary code review without a material security question.
---

# Engineering Security

Read [the shared engineering principles](../../harness/references/engineering-principles.md).

## Workflow

1. Confirm authorized scope, assets, actors, data sensitivity, deployment context, and risk tolerance.
2. Map entry points, trust boundaries, identities, permissions, secrets, and sensitive data flows.
3. Enumerate plausible misuse and failure cases grounded in the actual system.
4. Validate suspected weaknesses against code, configuration, or reproducible behavior before calling them findings.
5. Prioritize by exploitability, impact, exposure, and detectability.
6. Propose minimal, defense-in-depth mitigations and a verification method.

## Output

Separate confirmed findings, plausible risks, and hardening opportunities. For each confirmed finding state the affected boundary, preconditions, impact, evidence, mitigation, and verification.

Never provide unsupported certainty or broaden testing beyond the user's authorized systems. Avoid destructive proof when a safer verification is sufficient.
