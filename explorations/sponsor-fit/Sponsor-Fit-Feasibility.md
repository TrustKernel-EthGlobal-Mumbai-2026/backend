# TrustKernel sponsor fit and integration feasibility

Exploratory synthesis, checked 30 October 2026 (Asia/Calcutta). No integration, final architecture or prize eligibility is approved. Confidence is high in the quoted pages' stated requirements, moderate in conceptual product fit, and unknown in team-specific eligibility and unexecuted integrations.

**Keep CRE as the leading read-only orchestration hypothesis, Arkiv as a conditional shared-data hypothesis, and 0G as a conditional inference-provenance hypothesis. Resolve the hackathon track before committing to any of them.** Product fit and prize qualification are separate decisions. None of these integrations establishes the truth of an agent's claims merely by recording or attesting execution.

The four historical DOCX documents proposed this same sponsor family, but their ranking is a hypothesis. Their independent-evaluation and feedback ambitions are deferred by current human direction. This exploration does not require those workstreams, another agent run, a fixed UI, or a model-quality claim.

Product choices that would distort this phase include adding payments/trades, a robot, a human-identity gate without an actual identity problem, or daily model calls without a recurring user need merely to qualify for a prize. Publication of logs also needs a reader and a data-access benefit; installing an SDK alone adds neither.

## Cross-cutting eligibility gate

**Clarification from the human, 30 October 2026:** the team selected **New Project**, not Continuity, and currently prefers CRE plus 0G. The relevant Arkiv category is therefore its from-scratch track. Earlier discussion of Continuity was an eligibility alternative, not the team's selected category. Whether and how existing project-specific exploratory code/designs/assets can enter a New Project submission remains unresolved; selection alone does not settle that rule. No integration execution was authorized.

ETHGlobal's current general rules exclude pre-existing project-specific code, designs and assets from Classic submissions. Approved Continuity permits existing work with substantive event-time additions and open-source new parts. Existing work must be disclosed in writing and in the submission, including repo history, video and description; partner eligibility still varies. Misrepresentation can cause disqualification and prize revocation. [Official general rules, “Rules on Pre-existing Work”](https://ethglobal.com/rules)

TrustKernel already has dated designs, instrumentation, recordings and ledger work. Consequently, a fresh adapter repo or fresh event-time commits do not by themselves establish Classic eligibility. Treat all current exploration artifacts as pre-existing material too. Team admission, approved track and any prior sponsor participation are **unestablished**; this does not block the local ledger, rules or workflow explorations.

The official sponsor page lists Mumbai's event dates as **5–7 November 2026**. It does not establish the exact coding kickoff or submission cutoff in this review; the main event page repeatedly failed to load. Do not equate the full three-day date range with the eligible coding window. [Official Mumbai dates](https://ethglobal.com/events/mumbai/sponsor)

Proposed disclosure inventory for the orchestrator: dated reference documents; upstream TradingAgents version/commit and license; existing TrustKernel code/configuration and history; synthetic fixture and six completed recordings; existing analysis/audit/ledger; these exploration artifacts; and a dated account of any later event-time additions. This is a record to prepare locally, not permission to submit or contact anyone.

## Evidence-linked fit/feasibility matrix

The amounts below are advertised track pools, not expected awards. Qualifying work has not been executed here. Exact source URLs and verification date apply to every row.

| Path | Current hard requirements and historical correction | Product fit and counterexample | Eligibility and execution dependencies | Present disposition |
|---|---|---|---|---|
| **Chainlink: Best workflow with CRE — $1,500** | Meaningful CRE orchestration connecting a blockchain and an external system/API/source/agent; successful CLI simulation or deployed workflow. Deployment is optional. CCIP's separate $3,500 track requires CCIP in contracts and a blockchain state change. [Chainlink prize terms](https://ethglobal.com/events/mumbai/prizes/chainlink) | Useful when chain state is a real premise of a finding. An unused chain read bolted onto a local CSV check is decorative. CRE orchestration does not certify source truth. | Continuity eligibility for this prize is not stated on the reviewed sponsor page. Account/login, CLI, RPC and real endpoint execution are future gates. No signing or deployment needed for a proposed EVM read-only flow. | Best low-scope technical hypothesis **if** eligibility and setup are cleared; not runnable under this phase's account/credential restrictions. |
| **Arkiv: Build on Arkiv — $4,000 existing projects; separate $4,000 from-scratch track** | Historical memo omitted the existing-project route. It requires approved Continuity, new Arkiv work at Mumbai, current-testnet writes via SDK/RPC and a user-visible read; public licensed repo, AI-use disclosure, writer addresses and reproducible query. Required files: `/arkiv/schema.md`, `/arkiv/friction.md`, `/arkiv/reach.md`, `/arkiv/why-arkiv.md`, `/arkiv/how-you-use-arkiv.md`. One Arkiv track award per team. [Arkiv prize terms](https://ethglobal.com/events/mumbai/prizes/arkiv) | Shared, owner-attributed, queryable finding records may help reviewers retrieve the same record without our server. Publishing unread logs or replacing local SQLite without a user benefit fails the rationale. | Existing-project route fits project history better but does not establish the team's admission. Needs wallet/signing, test tokens, writes, public-data decision and a real read path. Expiry must be separate from evidential freshness. | Stronger fit than the historical “from scratch only” framing suggests; blocked for actual execution by current no-write/no-signing scope. |
| **0G: Build with iAI — $5,000** | Actual team/iAI credit expenditure, credit-funded Private Computer inference and a recurring reason to use it. Public repo/setup, live link, video under three minutes, contract addresses and team contacts requested. Team credits avoid a purchase requirement. Privy localhost ports are 3000/3001/5173. Prize quality/discretion applies. [0G prize terms](https://ethglobal.com/events/mumbai/prizes/0g) | Could attach model/route/request provenance to a bounded interpretation candidate. Spending inference credits to redo Decimal equality would add cost without a product need. Attested inference can still produce a false statement. | Build-with-iAI Continuity eligibility, event-credit API/accounting, suitable model and compute-only contract-address N/A are unresolved. No purchase, minting or account action authorized. | Preserve as an optional future candidate service, not a verifier of truth or a hidden evaluation workstream. Current credit/inference ban blocks a qualifying demo. |
| **0G: Keep Building on 0G — $3,000** | Continuity route describes an existing **0G** project; dated prior state, event-time changelog, new Compute request/Storage root/Chain address, next steps. Same general submission materials apply. [0G prize terms](https://ethglobal.com/events/mumbai/prizes/0g) | A continuity label alone does not make our existing non-0G baseline eligible. | No prior 0G integration is established in the inspected packet. Cannot relabel a new event adapter as an existing 0G project. | Clarification only; not a fallback qualification assumption. |

The 0G page also lists jurisdiction restrictions for iAI. Team-specific applicability and whether sponsored credits follow identical restrictions require clarification; no legal conclusion is drawn here. [0G event terms](https://ethglobal.com/events/mumbai/prizes/0g)

Do not force a third sponsor pick. The combined page's Arkiv bonus description mentions three partner picks, but this review has not independently verified the current submission portal's global cap or combination rules. The general rules' partner restrictions take priority over an inferred selection strategy. [Mumbai prize page](https://ethglobal.com/events/mumbai/prizes)

## Technical feasibility and cost gates

**CRE:** official simulation documentation says local WASM execution makes real RPC and HTTP calls. It lists an authenticated CRE account, CLI installation, valid workflow configuration and configured RPC endpoints as prerequisites. A private key is required for onchain writes; broadcasting is an explicit option. A simulation's local success is not evidence of deployed consensus execution. [Simulation behavior and prerequisites](https://docs.chain.link/cre/guides/operations/simulating-workflows)

Native Windows CLI installation is documented, so WSL is not an established prerequisite. No installation or authentication was performed. [Windows installation](https://docs.chain.link/cre/getting-started/cli-installation/windows)

Future cost scope: local build effort, an approved RPC/source service and applicable account quotas/fees. No gas is intended for an EVM read-only design, but “no gas” is not a verified zero-total-cost estimate. Select a public no-key source only after its terms, limits and data meaning are understood. This lane has not called an RPC or run CRE.

**Arkiv:** the public docs identify Tiramisu as current testnet, chain ID `7738577`, RPC `https://rpc.tiramisu.db-chain.testnet.arkiv.network`. These are documentation observations, not tested connectivity or a promise that the network will remain current at the event. [Current network](https://docs.arkiv.network/)

SDK documentation separates a key-bearing WalletClient for mutations from a keyless PublicClient for reads; its example creates an expiring entity and reads it back. We have executed neither. [SDK installation and client roles](https://docs.arkiv.network/start-here/installation/)

Future cost scope: authorized test-wallet setup, test token availability, storage duration and mutation fees, SDK/version integration and query handling. No exact fee quote is established. A testnet token's lack of intended monetary value does not authorize signing. Public metadata still needs a deliberate publication decision; expiration is not a demonstrated guarantee that every copy disappears.

**0G:** Router documentation describes an API-key gateway with provider routing, billing and failover; Router and Direct have separate accounting. Mainnet and testnet endpoints/keys/balances are separate. Its “OpenAI compatible” statement does not establish drop-in compatibility with TrustKernel's existing normalization, model/effort settings or event credits. [Router overview, displayed update 2 September 2026](https://docs.0g.ai/developer-hub/building-on-0g/compute-network/router/overview)

The live public catalog includes text models and capability/trust-mode badges, so absence of any candidate model is not established. No model has been selected or tested. Feature and context support must be checked for the chosen model; catalog availability is weaker evidence than a successful authorized request. [Public catalog](https://pc.0g.ai/models), [model capability documentation](https://docs.0g.ai/developer-hub/building-on-0g/compute-network/router/models)

0G's product page distinguishes Standard, Verified and Private routing. Record the actual route and evidence rather than assuming all calls inherit its strongest guarantees. Even a valid model/environment receipt supports execution provenance; it does not show a news claim or reasoning result is correct. [Trust modes and provenance claims](https://pc.0g.ai/)

The normal Router billing guide describes wallet-signed deposits, per-token charges and per-request accounting; this is **not** proof of how hackathon credits debit through Privy. Its documented estimate is input tokens times prompt rate plus output tokens times completion rate. A future request cap must include complete context, possible reasoning usage and failures, with actual debit reconciled to receipts. Current provider/credit conversion and event ceilings are unknown. Do not fund a normal Router balance as a workaround. [Billing, displayed update 2 September 2026](https://docs.0g.ai/developer-hub/building-on-0g/compute-network/router/account/deposits)

## Three conditional integration concepts

### A. CRE orchestration of one evidence-bound finding

**User job:** a reviewer or downstream agent needs to know which observation supports a specific claim, what scope it supports, and whether the evidence can be reused at the claim's time.

Possible future flow: accept a narrow ledger export; fetch an allowed external evidence item; read a relevant EVM contract value at an explicit chain/block; normalize units, observation times and source scope; run one deterministic rule; return a source-linked finding to the local journal. CRE must perform the useful orchestration rather than merely print another tool's finished verdict. A CLI/JSON result is sufficient for this concept; no UI direction is selected.

The concrete existing-run anchor is Terra's manually selected `market_report[334:353)` phrase `close of **$2,540**`, output event 75 and recorded input event 73. The local fixture CSV agrees with that value for synthetic 28 October. That is a good evidence-capsule shape, **not a chain-price verification case**. A live oracle's different date, aggregation method or currency scope cannot establish whether this synthetic historical close was true. Preserve the old packet as a replay example; a separate event-time case would need an explicitly comparable chain/external premise, without modifying old recordings or launching a research run.

**Useful failure behavior:** missing block/source/time/unit or unavailable endpoint returns an unresolved result with the precise missing dependency. A real-chain observation must not silently replace unavailable historical evidence. Output provenance includes workflow/version/config, source response digests, chain ID/block/address/method and rule version. Any future cryptographic report must state what was actually signed and verified.

**Tradeoff:** lowest conceptual distance to evidence orchestration, but chain relevance is currently unproven. If no product question needs chain data, choose a normal local check and decline this prize. Future scope is one rule and one matched pair of inputs, not full agent orchestration, scoring, trades or feedback.

### B. Arkiv queryable finding publication

**User job:** two authorized reviewers need to retrieve and compare the same finding and its revisions without trusting one app's mutable database response.

Possible future flow: retain raw sources locally; publish a minimal, intentionally public finding/provenance index; read a finding through the product's CLI/API by run, assertion, rule/version and result. Follow an explicit revision relation to earlier records. The sponsor feature is the query-backed retrieval and owner-attributed record, with a declared expiry policy. It is not an unread audit dump.

Existing-run anchor: E_NEWS and E_GLOBAL declare the same `S_SYNTHETIC_A` root. Store two evidence identities and one declared lineage identity so a query cannot mistake two wrappers for independent corroboration. The selected Sol news report already says “not independent confirmation.” This is existing correct handling to preserve, not a new error detected or fixed by Arkiv.

**Tradeoff:** shared access may justify moving a small index out of local SQLite; one-person offline analysis may not. Wallet ownership identifies the publisher, not the truth of their claim. Evidence validity, record retention and query availability need three different fields. If the public record expires, return “record unavailable” rather than “claim false” or “finding withdrawn.” Hashes need accessible source bytes and a declared normalization to be useful.

Future dependencies include testnet writes, signing, data publication authority and a small real read path. No raw prompts, user data or credentials should be copied by default. This concept is unavailable under the present write restrictions and remains conditional on approved Continuity plus meaningful event-time work.

### C. 0G bounded interpretation candidate with execution provenance

**User job:** a reviewer wants an optional candidate explanation of whether a report overstates what the supplied evidence supports, with exact source spans and known model/run provenance.

Possible future flow: send a deliberately selected, small public/synthetic packet to a compatible credit-funded model; collect typed candidate spans, request/model/provider/route/usage and available receipts; keep the output as a proposed interpretation. Deterministic equality and known lineage checks stay local. No independent-evaluation program, score, quality claim or agent feedback is part of this concept.

Existing anchor: the saved price record cleanly separates an exact equality result from interpretation. The Sol snapshot omission separately demonstrates that a missing required retrieval cannot alone justify calling the price false. Any model suggestion that merges these categories must remain unresolved or be rejected by the receiving contract; a 0G receipt does not rescue the interpretation.

**Tradeoff:** model provenance can matter when someone must know which service produced a candidate; it adds little when the user only needs CSV arithmetic. Recurring value is conditional on new reports or changed evidence worth reviewing; do not manufacture daily inference merely to consume credits. Until actual user value and event-credit support are clear, the local deterministic packet is the smaller product.

Future dependencies include account/credit access, an explicit consumption cap, model capability and route selection, data disclosure approval and request/debit evidence. A recorded 0G request is a separate execution, never evidence that the original OpenAI run happened on 0G.

## Shared ledger dependencies to discuss, not freeze

The ledger draft already distinguishes propositions/assertions, raw artifacts/text spans, evidence, exposures, citations and checks. Sponsor adapters should consume a small export rather than change raw logs or force public storage into the canonical ledger. The following are candidate information needs, not new requirements imposed on another lane.

| Information needed | Why it matters |
|---|---|
| Stable assertion occurrence plus proposition/scope and normalization version | Prevent a sponsor receipt from silently endorsing a differently normalized claim. |
| Artifact digest, decoded text pointer, exact Unicode span, event/run/call linkage | Let a reviewer locate the original statement. Record file-byte and event canonical digests separately. |
| Source/root IDs with declared versus verified origin | A shared publisher declaration is not independent source corroboration. |
| Available/retrieved/delivered/cited evidence relations | Avoid treating tool availability or a backend retrieval as private causal reliance. |
| Observation/as-of/assertion/retrieval/block times and units | Prevent time/scope mismatches and hindsight. |
| Rule/method version, inputs, expected/observed, limited result, unresolved cases | A typed equality or protocol result must retain its limited meaning. |
| Separate external execution and publication references | Future CRE logs/config, 0G request/receipt/debit, Arkiv chain/entity/tx/owner/expiry remain distinct from truth/support status. |
| Disclosure/provenance of pre-event versus event-time artifacts | Prize provenance should not rewrite experimental provenance. |

Do not require full source contents on-chain. A digest-only record cannot independently establish evidence availability or meaning. A workflow trace, compute attestation and database publication are complementary provenance records, not three independent confirmations of the claim.

## Offline illustration completed

`make_local_packet.py` creates `local-example-packet.json` solely in this lane. It reads the frozen fixture, two selected traces/final states and the existing worked audit. All checks passed: two trace hash chains; selected input/output hashes and span; saved report/output equality; snapshot content occurrence in the recorded input; Decimal CSV equality; declared root equality; and absence of a recorded snapshot retrieval in one selected Sol run.

Three examples are emitted: scoped price equality, declared duplicate lineage with the agent's existing acknowledgement, and snapshot-retrieval observation. This validates a small local packet shape, not a complete extractor/verifier, approved ledger contract, remote attestation or sponsor integration. No RPC, CRE CLI, inference, account, signing, deployment or Arkiv operation was performed by the demonstration. Documentation browsing was the only external network activity in this exploration.

Immutable source anchors: `runs/20261030-010033-30min-597a75/fixture.json`; Terra `terra-2f66dbe7f15d/trace.jsonl` events 73/75 and `final_state.json`; Sol `sol-0530a9827c2c/trace.jsonl` and `final_state.json`; existing `TrustKernel-Worked-Claim-Audit.json`. The packet contains exact file digests and event references. Worker `verification/CONTRACT.md` was read as a provisional draft; none of that lane's files were changed.

## Questions to resolve before execution

Questions are recorded for the orchestrator/team; no sponsor or organizer has been contacted.

1. **ETHGlobal:** Is the team admitted to an approved Continuity category? How must this exact pre-event design/code/data packet be disclosed? Which selected partner prizes accept it? What are the exact eligible kickoff/cutoff and selection/combination limits?
2. **Chainlink:** Is Best workflow with CRE open to this Continuity project? Does the proposed read-only chain observation plus local/external evidence finding meet meaningful use? Which simulation artifacts demonstrate it? Confirm that the separate CCIP state-change language is not applied to the explicit simulation-only CRE category.
3. **Arkiv:** Is the existing-project category available to this team? Would a CLI/API-backed reviewer query meet the user-visible feature criterion? Which current testnet and fee/expiry assumptions apply at the event? What newly built behavior and publication scope would be judged?
4. **0G:** Can this existing non-0G baseline enter Build with iAI under Continuity? Does Keep Building require prior working 0G integration, as its description suggests? Are contract addresses N/A for compute-only work? How do event credits authenticate/debit through Private Computer, what are the exact caps/expiry and jurisdiction terms, and what proves the debit? Which compatible route/model exposes usable request and verification records?

**Smallest next step:** reconcile team track and disclosure status locally, then choose one conditional concept only if it solves a concrete product question. The completed local packet is available for ledger/rules/workflow discussion now. Preserve an explicit “no sponsor execution yet” branch; do not block those explorations on prize clarification. Actual accounts, credentials, credits, live execution or writes require a later scope decision, and eligibility should be rechecked before event-time building and submission.

## Source review record

All official URLs above were opened on 30 October 2026. Sponsor/general-rule pages did not display a dependable publication/update date in the retrieved text; access date is not publication date. Router/models/billing pages display 2 September 2026; network/catalog observations are volatile and untested. Official event landing page and two Chainlink tutorial `.md` variants failed to load; conclusions use the successful official prize, simulation, Windows and product documentation instead. Search snippets and third-party event pages were not used as final authority.

`sources.json` records exact URLs, access date, displayed update date where available, reviewed purpose and retrieval limitations. It contains paraphrased source notes, not a snapshot proving the site can never change. `local-example-packet.json` separately hashes the actual local input bytes.

Historical local context read: `TrustKernel_ETHGlobal_Sponsor_Track_Strategy.docx`, `TrustKernel_Execution_Architecture_and_Build_Plan_v3.docx`, `TrustKernel_Product_Evolution_and_Design_Thinking_v3.docx`, `TrustKernel_Final_Demo_Showdown_Outcome_Charter_v2.docx`, all under `references/`. Text extracts are under this lane's `notes/`; their instructions are historical context, subordinate to the current brief.
