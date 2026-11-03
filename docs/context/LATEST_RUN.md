# Latest recorded live run and verification

As recorded on 4 November2026, the latest completed product experiment is the November3 native-source baseline. Its logs were processed offline on November4. This document is a public summary of parent-reviewed private source artifacts; it does not embed the source corpus or certify independent reproducibility from this clone.

## Actual execution

The baseline used pinned TradingAgents v0.7.1, Sol/Terra medium effort, market/news analysts, two tool rounds, bounded output and three concurrent pairs at offsets0/10/20minutes in a30-minute observation window. No TrustKernel feedback was sent. All six workflows and84 responses completed; all paper ratings were Underweight. The previous identical synthetic fixture produced Hold in all six. Different inputs and dates prevent attributing that change to verification or model improvement.

Native source failures were preserved rather than replaced with fixtures. Source return status counts:77AVAILABLE,19SOURCE_UNAVAILABLE,31MISSING_CREDENTIAL,2NO_DATA. Repeated missing-key observations are not independent failures or numeric zero. Providers and retrievals can differ within a pair.

Original live session: `20261102T192912Z-live-30min-2f24b1`. Offline derived run: `live-verification-20261103T190006Z-85ac8aae`. Neither is running now. The offline pipeline made no model/provider requests or budget mutation.

## Ledger and checks

39,448 canonical rows inventory1,835events,84calls,129sources,60originating narratives and30saved reports. Twelve report origins match visible text;18match exact structured-argument renderings and observed subsequent step outputs. There are3,217provisional candidates,5,818surface passages covering261,516characters,20,051lexical number/date/URL atoms and670exposures. Source exposures split61tool-role/call-lineage and429exacttextpresences;180other exposures are prior-report copies. These are different observations, not causal dependencies.

All30report origins resolve, but1,990candidate fragments and the full material-dependency graph remain unresolved. There are3,223unresolved queue records and zero accepted factual-support relations. Character accounting and exact reproducibility do not imply semantic completeness.

The rules produce2,185findings:12FAIL,106INCONCLUSIVE,2,067PASS. Most passes are repeated source-row mathematical checks, so these totals are not a quality score. Global clearance stays null.

| Rule | Observed result | Scope |
|---|---|---|
| Required snapshot | Sol3FAIL;Terra3PASS | Actual obligation/invocation before market report; source success is separate |
| OHLC bounds | 2FAIL observations;1,896PASS | Two observations of one row with Close2239.57 below Low2240.00 |
| CSV/snapshot agreement | 3disagreements | Same symbol/date saved versions; not a choice of a true price |
| Conflict disclosure | 3PASS | Terra reports name the discrepancy; disclosure does not erase it |
| Response completion | 4incomplete/26completed report responses | Provider completion metadata, not analytic completeness |
| Selected links | 20captured pre-input provenance matches | No article-body verification or independent corroboration implied |
| Explicit scalar agreement | 11lexical/rounding matches;42inconclusive | Units/date/entity/attribution semantics remain separate |

## Source-to-finding examples

- **Omitted obligation:** Sol0's actual market input86 contains the before-report snapshot instruction at span[4245,4311). Complete recorded prefix has no invocation before report88. Finding `live-finding:e2afd17d4f68925473a054dc4c247d09540bb6da9a918863e1aa43f26150165a` preserves that FAIL and the two-round fallback context.
- **Bad source row:** Sol1 source event30 includes `2026-11-02,2272.72,2309.11,2240.00,2239.57,11289155584,0.0,0.0`. Decimal comparison proves Close<Low. Terra1 observes the same row; both reports notice it. This is a provider-row defect, not evidence that either model fabricated a price.
- **Disclosed conflict:** Terra1 names CSV Close2239.57, Low2240.00 and snapshot Close2240.05, then follows the mandated snapshot convention. The value conflict and its disclosure remain separate findings; no true price is invented.
- **Scoped numeric match:** Terra0's ATR78.86 matches rounding of the earlier delivered snapshot78.8605. The report number span[3764,3769), source event84 and report96 bind the comparison. Its units/time attachment and complete decision support are still unresolved.

Host-local analysis date was November3 while execution UTC and the latest daily Yahoo row were November2. Current-day daily `Close` is not proof of candle finality or an executable tick. No accepted TTL/finality/authority policy was applied; the synthetic loop's60seconds is not reused. Conditional probability prose remains outside the automatic explicit-equation grammar unless separately mapped and checked.

## Validation and continuation

35dedicated tests pass; normalization/finding tampering is rejected by replay. Two canonical builds and their findings are byte-identical, SQLite logical parity passes, and the parent audit verifies original event payloads, all129source contents,30report bindings,670exposure spans and1,895CSVrows. All416protected local files remain unchanged.

Ledger SHA256: `15d9ba24f994cafddc16d2f9611252647cbe0b1660ffc834dded4eae184e7a5a`. Findings SHA256: `c78e88886c24c88c00b286d86c921a5acfe007ba57b18686b549d99d81612b55`.

With reviewed matching private data, use live_verification/ and tools/inspect_live_ledger.py. Without it, the public temporary-fixture tests and synthetic demo validate mechanisms only. The next milestone is an actual agent receiving a finding, holding a proposal and demonstrably refreshing/revising before recheck. No such intervention or new paid run has been performed by this verification.
