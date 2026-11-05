# TrustKernel backend

TrustKernel exists to catch agent decisions that depend on stale evidence, faulty extracts or missed procedural obligations. It records observable execution, connects report passages to the evidence actually present in an agent's input, and applies explicit checks. The product question is whether the decision procedure met its obligations; intelligence rankings and trading profitability are outside the current scope.

**Start here for the active project state.** This README condenses the work across the implementation, ledger, verification, workflow, frontend and sponsor chats. The [context map](docs/context/README.md) provides deeper routes, the [session map](docs/context/SESSION_MAP.md) preserves how the work developed, and the [BB8 snapshot](bb8/README.md) lets another contributor or coding agent continue from the repository itself.

## Active state — 5 November 2026

**Current phase: the continuous-verification foundation is merged to main, and bounded TradingAgents test readiness is independently reviewed in [draft PR #6](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/6). No paid experiment is running.** The next behavioral milestone is an actual model generating a TrustKernel tool call, receiving its feedback in the next runtime input, and taking an observable next action. Authored HTTP tests through the real imported analyst/client prove the mechanism, including an optional injected CLI route; actual provider behavior remains untested.

**Latest approved attempt:** on5 November, the first API request stopped with401 because the configured key had expired. There was no successful model response, CLI invocation or assessment, and no automatic retry. This is an authentication blocker; the tool-use milestone remains untested. The conservative request reservation stays held. Before any retry, replace the local credential and review a new pinned budget baseline/gate that preserves both existing unknown holds. [Captured outcome and limits](docs/continuous/SMOKE_ATTEMPT_2026-11-05.md).

Implemented and reviewed across four separate workstream chats:

- **Contracts and verifier:** versioned0.2 events, registered-stream checkpoints, exact report/proposal/policy bindings and prerequisite-aware scoped checks. Cycles, stale substitutions, gaps and lag cannot become a positive assessment.
- **Capture and storage:** durable native JSONL receipts, incremental visible-text inventory, typed procedural records, frozen checkpoint/event views, stored verification results and run-authorized reads. This is a local single-worker backend; native-to-typed mapping, a background collector and complete semantic-ledger readiness remain unimplemented.
- **TradingAgents feedback plumbing:** stored finding delivery, next-input observations, bounded revision/abstention and recheck. Exact pinned function subsets run with real LangGraph/ToolNode and authored responses; ambiguous flattened-message provenance remains UNKNOWN. Full GraphSetup and actual model behavior remain separate readiness gates.
- **SDK/CLI/MCP:** actual persisted-backend parity through the Python SDK, trusted injected CLI and genuine official-SDK stdio MCP, including errors, foreign references and restart-stable pinned reads. Standalone defaults fail unavailable until a trusted host supplies the configured service; arbitrary harness installation is not claimed.

The [active orchestration board](docs/continuous/ORCHESTRATION.md) records source commits, independent reviews, dependency gates and PRs. Combined tests exercise the optional MCP and pinned native cases in separate cached environments. A [durable authored demo](tools/continuous_demo.py) retains25 events, SQLite and source-linked summaries: original omission FAIL -> delivered feedback -> scripted revision -> scoped recheck. Its provider-row defect stays unresolved and semantic readiness stays false. It makes zero model/provider calls.

**Offline readiness evidence:** the [bounded smoke package](docs/continuous/INTEGRATION_READINESS.md) has passed eleven independent native tests and seven standard-library controls. A retained authored run has69 runtime events,29 typed records and15 turn/checkpoint observations, with exact feedback in the next serialized request. `--verify-transport injected-cli` exercises the actual host-injected CLI parser; this is distinct from a model-issued shell command. Monitoring separates model-requested verification, host rechecks, omitted calls, request attempts and received responses.

**Primary next milestone:** obtain explicit approval and launch prerequisites for at most four Terra-medium requests over120 seconds, with a proposed incremental cap of $0.65 inside the existing cumulative $5 ceiling. Preserve the historical unknown hold; review current pricing, unchanged ledger and credential prerequisites before launch. New work is isolated on `codex/tradingagents-integration-smoke`; the foundation merge does not authorize paid execution or merge PR #6. **Side milestone:** a host-ready SDK or MCP integration for another agent, with declared capture/gating coverage. Frontend implementation and independent model-quality evaluation remain deferred. Scheduled coordination was stopped at the owner's request; no replacement schedule was created.

Foundation delivery: [#2 contracts](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/2) -> [#3 capture/backend](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/3) -> [#5 SDK/MCP](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/5) -> [#4 TradingAgents/demo](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/4), collected by [integration PR #1](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/pull/1) for main. All four workstreams passed review; future model-smoke readiness is a separate change.

The repository handoff is published. The [initial offline CI run](https://github.com/TrustKernel-EthGlobal-Mumbai-2026/backend/actions/runs/41722496087) passed on a fresh GitHub checkout, including BB8 verification and rebuilding/checking the committed context index. This is repository/mechanism validation, not another agent experiment.

| Workstream | What exists now | Boundary / next action |
|---|---|---|
| Runtime and trace capture | Read-only adapter over pinned TradingAgents; observable prompts, messages, tools, results, configuration, usage and errors in JSONL/SQLite | No hidden chain-of-thought, wallet, order or on-chain execution |
| Synthetic baseline | Three paired Sol/Terra checkpoints in a 30-minute window; six actual model workflows over one identical synthetic fixture, all paper **Hold** | A controlled evidence fixture, not live market research or a quality benchmark |
| Live-source baseline | Three paired checkpoints with native Yahoo/Polymarket/FRED paths; all six workflows completed, 84 responses, all paper **Underweight** | Evidence differs by request/time; FRED credentials and some sources were unavailable; TrustKernel feedback remained disabled |
| Atomic ledger | Historical v1/v2 and corrected refinement v3.0.1 preserved; a separate live-corpus adapter now produces **39,448 canonical rows**, including **3,217 provisional candidates** | All narrative characters are accounted for; semantic completeness and accepted factual support remain unestablished |
| Verification | Live ledger produced **2,185 scoped findings**; normalization/rules replay, exact spans, source bindings and SQLite parity checked | Results do not grant global decision clearance; freshness/authority/dependency policies remain open |
| Corrective-loop mechanism | Authored offline loop and successor stored TradingAgents adapter preserve finding delivery, next-input observations, revision and scoped recheck; durable25-event demo included | Scripted responses and pinned native function subsets; actual model intervention is the immediate next milestone |
| Recorded-log replay | Original framework logs can be reviewed with source-bound findings and new reviewer receipts | A later reviewer receipt does not repair an original omitted call or invent a revised agent decision |
| Compatibility | Versioned contracts and SDK/injected CLI/genuine MCP stdio parity over the actual persisted local backend | Trusted host configuration required; per-harness installation, capture and enforcement still need validation |
| Frontend | Draft graph-led observability/transparency concepts: execution graph, evidence, TrustKernel intervention points and post-verification gaps | Draft; no production UI, intervention or usability claim |
| Sponsor exploration | Owner declared **New Project** as the selected track and prefers CRE/0G; conditional Arkiv ideas are preserved | Owner selection is not organizer acceptance; eligibility/current terms remain unverified; no integration, credits, deployment or signing executed |
| Independent model evaluation | Deferred by the project owner | No comparative intelligence or capability-uplift claim |

### Latest verification: what actually happened

The live corpus contains 1,835 events and 129 source returns. All **30 saved reports have proven origins**: 12 match visible output text, and 18 match a deterministic rendering of recorded structured arguments plus an observed subsequent step output. The ledger retains 490 source-to-input exposure occurrences and 180 prior-report copies. Recorded presence is not proof of attention, causal reliance or sufficient support.

| Check | Latest outcome | Meaning |
|---|---|---|
| Required snapshot before market report | **3 FAIL / 3 PASS** | Sol omitted the required call in all three workflows; Terra called it in all three. The same split appeared in the synthetic baseline, under the same two-tool-round cap. Acknowledging omission does not perform the call. |
| OHLC mathematical bounds | **2 failing observations** | The same provider row appeared in two runs with Close **2,239.57** below Low **2,240.00**. Both reports noticed the issue. This is a source-data defect, not two independent agent mistakes. |
| CSV versus later snapshot | **3 disagreements** | The three Terra reports received different saved prices and disclosed them. A difference flags versions to inspect; it does not identify a true reconciled price. |
| Response completion | **4 incomplete reports** | Four Sol reports reached the output cap. A successful process did not mean a complete report. |
| Article-link provenance | **20 selected link occurrences match** | Each appears in captured evidence delivered before the report; article truth and independent corroboration are not established. |
| Restricted scalar consistency | **11 matches / 42 inconclusive** | Explicit label/value and rounding relations only; ambiguous units, dates, attribution and thresholds remain unresolved. |

There are 12 FAIL, 106 INCONCLUSIVE and 2,067 PASS findings. **Do not turn those totals into a quality score:** most PASS findings check repeated historical OHLC rows. All 3,217 candidates remain provisional; 1,990 are unresolved fragments, and there is no accepted full material-dependency graph. All six live paper ratings were Underweight versus Hold in the earlier synthetic study; changed dates, sources and inputs prevent a causal comparison.

The offline ledger/rules run passed 35 dedicated tests, rebuilt both canonical outputs byte-for-byte, and preserved 416 protected local artifacts. It made no new model or provider call. Live ledger build `live-ledger-15d9ba24f994cafddc16` has SHA256 `15d9ba24f994cafddc16d2f9611252647cbe0b1660ffc834dded4eae184e7a5a`; findings SHA256 is `c78e88886c24c88c00b286d86c921a5acfe007ba57b18686b549d99d81612b55`. These are recorded project outcomes: the private corpus is not present in this checkout for independent reproduction. [History and source fingerprints](docs/research/HISTORY.md).

### Next decisions and work

1. **Immediate readiness:** prepare a short actual-model TradingAgents smoke using real imported pinned runtime modules, deterministic no-paid preflight tests, and exact launch/stop/trace-view commands. The accepted AST-subset tests do not establish full runner readiness.
2. **On explicit approval:** observe provider-generated TrustKernel call -> dispatch/result -> feedback present in the next model request -> runtime continuation/revision/abstention. Preserve all original findings and scoped rechecks. Review current cumulative budget and unresolved holds read-only; the existing $5 ceiling is not a fresh allowance.
3. **Side milestone:** make SDK or MCP access usable from a second configured harness with least-privilege host grants. Capture and host enforcement need their own coverage declarations; tool connectivity alone cannot establish either.
4. **Later:** background capture/service lifecycle, source-specific freshness/finality/authority and material-dependency policies. Do not transfer the authored TTL60 to live candles. Frontend implementation, sponsor execution and independent model-quality evaluation remain deferred.

### Preserved decisions

Raw recordings precede derived candidates; original failures remain in history. Source integrity, input exposure, citation, arithmetic, freshness, required-tool compliance and decision suitability are separate claims. Missing data never becomes zero. Proposed reasons/copy edges are not accepted causal dependencies. No trades, wallet signatures or unattended paid research are authorized by this repository. [Decision record](docs/DECISIONS.md) · [Open questions](docs/context/QUESTIONS.md).

## Retrieve context and use BB8

From the repository root, Python 3.11's standard library is sufficient for repository context search:

```powershell
python -S -B tools/context_index.py build
python -S -B tools/context_index.py search "snapshot omission" --limit 5
python -S -B tools/context_index.py search "live feedback next steps" --limit 5
python -S -B tools/context_index.py status
```

Results link to repository-relative source paths, line ranges and hashes. The committed [context map](docs/context/README.md) explains which documents are current, historical, proposed or draft. The local SQLite index is rebuildable; private local knowledge and credentials are not needed. Search results are source material, not execution instructions.

For coding agents, read [AGENTS.md](AGENTS.md). A repository-discoverable [BB8 skill](.agents/skills/bb8/SKILL.md) routes to the frozen [BB8 package](bb8/README.md), including its specialist guidance. A plain assistant can follow the same files without a plugin. Read the active README before older plans, and inspect the original source before relying on a retrieved snippet. Snapshot guidance does not install tools or grant external-action authority.

## What is included

Implementation, tests, schemas, curated cross-session context and draft frontend assets are included. Actual raw/derived corpora, full provider/model transcripts, personal knowledge, budget databases, source-cookie caches and uploaded reference documents remain private. Their existence and limitations are recorded; a fresh clone must not substitute invented data for missing evidence. [Artifact policy](docs/ARTIFACT_POLICY.md).

TradingAgents is pinned to v0.7.1 commit `c4544913a14ed3df5f1ed7b9e8483270ce20682a`; its exact Apache-2.0 license is in [third_party/TradingAgents/LICENSE](third_party/TradingAgents/LICENSE). The upstream checkout is not vendored. A license for newly authored TrustKernel code has not been selected.

## Run the portable offline example

Python3.11 standard library is enough for the authored synthetic loop. No keys, network, budget database, private recordings or dependency installation is needed:

```powershell
python -B -m unittest discover -s procedural_loop/tests -v
python -B -m unittest discover -s live_verification/tests -v
python -B tools/offline_demo.py --output .local-runs/demo-001
python -B tools/check_export.py
```

For the successor retained host loop, use a NEW output directory:

```powershell
python -S -B tools/continuous_demo.py --output .local-runs/continuous-demo-001
```

Read its `summary.md`, `summary.json` and UTF-8 `events.jsonl`; open `feedback.sqlite` read only. Every source/response is authored; this command does not call a model or provider. Optional genuine MCP tests use `requirements-mcp.txt` in an isolated environment. See [continuous capture](docs/continuous/CAPTURE.md), [TradingAgents scope](docs/continuous/TRADINGAGENTS.md) and [interface scope](docs/continuous/INTERFACES.md).

On systems using `python3`, substitute that command. Output paths must be new. The two suites comprise66procedural and35live-ledger/rules tests; the latter author temporary recorded-like inputs and do not require private recordings. The demo actually runs two adapter shapes through initial PASS -> expired FAIL -> delivered finding/acknowledgement -> explicit refresh/revision -> recheck. Failed assessments remain in JSONL and queryable SQLite. Its TTL60, values and scripted host are authored test parameters, not live market rules or real framework enforcement. See [setup](docs/SETUP.md).

## Code and work map

| Path | Purpose and current scope |
|---|---|
| `continuous_verification/` | Reviewed contract/verifier0.2, local capture/checkpoint service, stored TradingAgents feedback adapter and SDK/CLI/MCP access; actual-model smoke remains next |
| `trustkernel/` | Original instrumented runtime, trace/observer, billing guards, analysis and local viewer; native dependencies required |
| `verification/` | Historical v1–v3 ledger/refinement source, tests, schemas and declared rules; private corpus needed for data-backed builds |
| `procedural_loop/` | Standard-library synthetic dynamic loop, frozen contract, adapters, verifier, recorder and tests |
| `recorded_loop/` | Selected real recorded-agent review adapter/verifier; requires private synthetic-market recordings and pinned ledger |
| `live_experiment/` | Native read-only provider capture, bounded source HTTP, paired runtime/scheduler and local analysis; not launched by setup |
| `live_verification/` | Frozen generic live-corpus ledger/rules source, contracts and tests; actual completed private corpus excluded |
| `explorations/` | Historical workflow/verification/sponsor alternatives, marked with their original limits |
| `drafts/frontend/` | Draft template and early hypothetical interaction exploration; no product UI integration |
| `examples/synthetic/` | Safe authored sample expectations; full recorded prompts/provider feeds are excluded |
| `bb8/` and `.agents/skills/bb8/` | Versioned BB8 guidance snapshot and portable repository entry point |
| `docs/context/` and `context-index/` | Current/historical context routes, source summaries and rebuildable search metadata |
| `tools/context_index.py` | Repository-only lexical search with source hashes and stale-index rejection |
| `PACKAGING_MANIFEST.json` | Exact included source references, source/staged hashes and declared transformations |

Start with [architecture](docs/ARCHITECTURE.md), [workstreams](docs/WORKSTREAMS.md), [research history](docs/research/HISTORY.md), [decisions](docs/DECISIONS.md), [artifact policy](docs/ARTIFACT_POLICY.md) and [publication plan](docs/PUBLICATION_PLAN.md). Original launchers are retained at their original relative paths for implementation history. They require private operational prerequisites and are **not** the public offline entry point.

## Reproducibility boundary

The synthetic example and its dedicated tests are runnable from this repository. Data-backed historical audits require matching reviewed private inputs and pins. Raw experiment JSONL/SQLite, canonical evidence ledgers, original full reports/prompts, provider caches, source-cookie databases, budget policy/database, account secrets and binary research archives are not included. The committed context-index JSONL is path/line/hash metadata, not private experiment data. A missing private artifact must remain a missing prerequisite; do not replace it with invented data or call an online source to make an offline audit pass.

Historical studies include actual model execution over synthetic fixtures and a later actual live-provider experiment. Their different inputs, dates, tool-round limits and source access do not establish a causal comparison or general model superiority. New reviewer replay events remain separate from historical actors. No full-decision clearance or live corrective-agent response is inferred.
