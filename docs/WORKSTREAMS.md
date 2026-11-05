# Workstream accounting

Updated5November2026. Every lane is accounted for; inclusion is distinct from publication approval.

Active next-phase design: [continuous capture and feedback](CONTINUOUS_VERIFICATION_PLAN.md). The owner prioritized incremental ledger/checkpoint contracts, actual TradingAgents feedback and cross-harness tool access. Existing implementations below remain at their recorded scope; frontend implementation stays deferred. No runtime or paid experiment launched as part of the design update.

Current continuation: the scoped offline foundation is implemented/reviewed and delivered by PRs2/3/5/4 and integration PR1. Actual-model TradingAgents test readiness is the primary next gate; SDK/MCP host access is secondary. The initial design paragraph above describes the earlier proposal, not the present implementation status. See the root README and [active board](continuous/ORCHESTRATION.md).

| Workstream | Stage representation | Excluded or pending originals |
|---|---|---|
| Continuous-verification foundation | continuous_verification/, retained authored demo, scoped tests and optional MCP CI | Actual-model response, full GraphSetup, background collector/service and arbitrary-harness installation remain unproven |
| Baseline adapter/runtime | trustkernel source, tests, lock, upstream pin | Runtime logs, model prompts, budget/account state, installed environment |
| Atomic ledger v1–v3 | verification source/schemas/declared rules/API docs | Full canonical JSONL/SQLite, release ZIPs and machine-specific export script |
| Verification semantics/v0.2 | historical rules/contracts/mappings/test vectors and source | Full assessment bundles and raw anchors requiring private corpus |
| Evidence inspection workflows | three-alternative workflow notes and source-navigation code | Source-case raw packet and compatibility outputs kept in private archive |
| Synthetic procedural loop | source, authored fixtures, tests and portable new entry point | Original private-protection manifests; newly generated demo output stays local |
| Recorded framework replay | source adapter, policy, verifier and tests | Actual original recordings/pinned datasets; new review must not rewrite history |
| Live-provider experiment | source guard/adapters/runtime/review source and tests | Native raw provider responses/full reports/caches/cookies, private operational budget |
| Live-corpus ledger/rules | Frozen live_verification code/tests/contracts and root launcher, authorized by parent after actual integrated PASS | Actual live recording, full ledger/findings and private protected-before snapshot excluded |
| Frontend | draft authored template/spec and early illustrative HTML | Embedded real-data snapshots, renderer wrappers, screenshots and local browser QA files |
| Sponsor exploration | historical sponsor notes/source catalog with original date | No executed integration; account/credit/signing/deployment/eligibility unresolved |
| Product/architecture/demo references | curated purpose/history/decisions summaries | Original uploaded DOCX and extracted reference-document copies |
| Cross-chat orchestration | curated history, artifact policy and provenance map | Full chat transcripts, internal plans/approvals, raw parent reports/archives |

The original staging workspace retains the detailed per-file inventory and exclusion rationale. `PACKAGING_MANIFEST.json` is the repository's included-file map, with logical source references rather than private usernames/absolute paths. Original Git history remains in the private Desktop checkout. The owner supplied the empty public TrustKernel-EthGlobal-Mumbai-2026/backend repository on4November2026; this reviewed snapshot and its active README/context/BB8 layer form the clean public handoff, without publishing private installation history or evidence.
