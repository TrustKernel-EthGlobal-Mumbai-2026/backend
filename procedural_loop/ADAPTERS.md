# Procedural loop fixture adapters

2 November 2026. Adapter owner plan and implementation contract. Status: adapter implementation and 17 dedicated tests complete against frozen `procedural-loop-contract-0.1`; parent owns actual runner/verifier integration and final acceptance. No competing canonical schema is introduced here.

## Scope and authored scenario

Two raw layouts encode semantically equivalent scheduled observations: a single command-shaped stream and a multi-agent observation/handoff/step stream. These are scripted offline test inputs, not an installed Claude integration or actual agent execution. Parent owns the runnable loop, persistence and final acceptance; this lane owns adapters.py, fixtures/, this document and tests/test_adapters.py. Standard library and existing .venv only. Historical records/releases/budgets remain untouched.

Fixtures use ETH-USD solely as a synthetic test entity. v1 is 2540 USD observed at 00:00:00Z. v2 is 2560 USD observed/scheduled at 00:01:00Z and declares v1 superseded. Authored freshness threshold is 60 seconds, with strict expiry at age >=60. Initial use is 00:00:30Z; stale reuse is 00:01:01Z; refresh request at 00:01:05Z can reveal v2. Parent accepted this timeline for the synthetic demonstration only. Evidence schedule is not the consumer's observed context: future fixture rows must not enter adapter output until an explicit eligible source read. Retrieval time is assigned to the actual scripted read, separate from source observed time.

No final successful finding or clearance is embedded in the fixture. The parent must deliver an assessment/finding, request refresh, obtain the newly visible observation and request a revised proposal/extract. A changed value or source-version mutation must be constructible for verifier tests. Review-only paper proposals cannot authorize trades or certify portfolio suitability.

## Shared contract and runtime API

The adapter imports `SCHEMA_VERSION`, `require_valid_packet`, `parse_time`, `text_digest` and `binding_matches` from the parent-routed frozen contract. Every packet validates structurally and against its preceding packet for immutable identities. Context/proposal revisions and packet/proposal IDs advance for changed submissions; previously delivered evidence remains byte-identical. Parent controls actions and persists returned raw/runtime events.

```python
from procedural_loop.adapters import (
    ReplaySession, INITIAL_AS_OF, EXPIRED_AS_OF, REFRESH_AS_OF, distorted_packet,
)

session = ReplaySession("single", run_id="parent-selected-run")  # or "multi"
initial = session.initial_packet()      # read v1 at t0, paper use at t+30
events = session.drain_events()         # parent records after every operation
expired = session.advance_to(EXPIRED_AS_OF)  # v1 reused, no source read
# Parent evaluates expired through the real local verifier, obtaining assessment.
ack = session.deliver_finding(assessment)
new_evidence = session.request_refresh(REFRESH_AS_OF)
revised = session.revised_packet()      # separate submission, not automatic success
```

`deliver_finding` requires a nonempty assessment identity, exact current packet binding, no clearance, at least one explicit non-PASS required finding and a machine-readable required response. It records actual delivery and a **scripted-host** acknowledgement. It checks data binding rather than authenticating an external verifier; parent supplies the real local assessment. `request_refresh` refuses missing delivery, time regression, duplicate refresh and unchanged source version. Re-reading v1 cannot reset its retrieval/valid time or unlock revision. `revised_packet` refuses until a successful explicit refresh. Refresh returns only evidence and does not compute an assessment or clearance.

`drain_events()` returns detached records with `event_id`, `kind`, `as_of`, `actor_id`, `causal_refs`, `mode=offline_scripted_fixture` and `payload`. Parent can wrap each as `recorder.emit(event['kind'], event, as_of=event['as_of'])`, optionally prefixing the outer kind with `adapter.`. No recorder or runtime output file is created by adapters. Source events include the original raw row, raw ID, fixture URI/pointer/hash and actual scripted read time. Multi-agent records explicitly link researcher observation, handoff, analyst extraction and planner proposal. Finding delivery links acknowledgement, refresh request and newly read source events. These are declared synthetic causal links, not inferred private reasoning.

`FixtureSource(shape, fixture_path=None).read(as_of)` is a read-only source selector; returned rows are detached and the complete physical fixture schedule never becomes consumer context automatically. No unobserved future v2 row enters a packet. Evidence pointer spans address decoded evidence content; raw fixture pointers locate the corresponding text object. Proposal extract spans are computed from the exact scalar token in that authored text. Packet policy declares the fixture's TTL and the five required capabilities: evidence_timestamps, source_versions, source_text, declared_dependencies, observed_prefix. CAPTURED means complete only within the authored fixture's bounded quote procedure. Unknown source clock stays null, missing completeness yields UNKNOWN, and malformed source identifiers/topology/structure cause input error. Unknown fields are never filled as observed facts.

`distorted_packet(packet, value="9999", source_version="wrong")` constructs an explicitly authored mutation with new packet/proposal/extract IDs while preserving immutable evidence and the original quote. Either argument can be supplied independently. It deliberately does not repair the wrong extract: the verifier must detect scalar/source-version disagreement. These are testing variants, not alternate historical ETH observations.

## Risk-based adapter checks

| Risk | Local verification |
|---|---|
| Future version leaks before observation boundary | Explicit reads immediately before/at boundary; context contains only observations actually read |
| Two shapes differ semantically | Compare normalized entity/value/unit/observed time/version/dependencies across both at matching actions |
| Command IDs or handoff causes are lost | Resolve raw IDs/pointers and check declared researcher/analyst/planner links |
| Missing/invalid source time or incomplete coverage silently passes | Negative fixture mutations preserve unknown or reject input; no inferred timestamp/completeness |
| Revision baked into final stream | Initial/stale proposal continue v1 until parent delivers finding, refreshes and explicitly requests revision |
| Value/version distortion is impossible to represent | Construct wrong scalar and mismatched version, preserving original source anchor |
| Mutable caller output contaminates later replay | Copy/immutable returned values and independent adapter instances |
| Historical or authored source bytes overwritten | Read-only fixture loads and deterministic identity; no writes from adapter |

## Now and next

Completed: two raw fixtures, read-only source selector, contract-backed ReplaySession, explicit finding/ack/refresh/revision transitions, value/version mutation helper and dedicated tests. Parent received fixture milestone and code-ready API. Test command:

```powershell
.\.venv\Scripts\python.exe -m unittest procedural_loop.tests.test_adapters -v
```

Seventeen tests pass. They cover scheduled observation boundary/no future leakage, shape equivalence, exact raw pointers/digests, actor topology and causal links, detached state, malformed/unknown clocks/coverage, no automatic source refresh, immutable old evidence, forbidden missing-predecessor transitions, old/unbound/cleared/PASS-only assessment rejection, same-version reread refusal, dynamic v2 revision and wrong-value/version mutation construction.

The local lifecycle tests use an explicitly authored blocked-assessment interface stub to exercise the adapter boundary. They do not establish that verifier checks ran or that a full persisted run succeeded. Parent must supply actual verifier output and independently execute/persist the loop. No model/Claude integration, live data, trade enforcement or broad dependency capture is implemented. Historical source/ledger/assessment/budget files and other owners' code were not modified. Any remaining shared-interface discrepancy must be routed through parent rather than patched into contracts/verifier here.
