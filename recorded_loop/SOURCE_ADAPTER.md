# Recorded framework source adapter

2 November 2026. Frozen consumer interface `recorded-source-packet-0.1`. Scope: two selected actual TradingAgents/LangChain Market Analyst reports, over the unchanged synthetic fixture; all-six-run source integrity uses parent-owned `audit.py`. No new model execution, source correction, market version or historical agent feedback is manufactured.

## API

```python
from recorded_loop.source_adapter import (
    SUPPORTED_RUNS, build_case, validate_case_sources, retrieve_for_review,
    audit_sources, canonical_json, digest, SourceIntegrityError,
)
packet = build_case("sol-0530a9827c2c")  # or terra-2f66dbe7f15d
witness = validate_case_sources(packet) # PASS dict, or SourceIntegrityError
receipt = retrieve_for_review(packet, "E_SNAPSHOT")
```

All functions are local and read-only. No runtime output is written by the adapter. Parent persists packets, receipts, assessments and new reviewer events. `audit_sources()` delegates unchanged to parent's six-trace hashchain/full logical SQLite parity audit. `build_case()` uses that audit plus source-file hashes and selected exact anchors. Recorded source-file digests/sizes are also checked against artifact rows read from the pinned canonical ledger, without importing any legacy builder. Unsupported run IDs fail rather than pretending selected-claim coverage across all six runs.

`retrieve_for_review(packet, evidence_key, *, reviewed_at=None)` defaults to the actual new UTC review timestamp. Optional explicit timezone-bearing timestamp exists for reproducible local tests/replays and must be later than the original report output. Every call obtains a new UUID receipt ID; receipt digest binds the full returned payload. Original packet is untouched. It is retrieval of the original local frozen artifact into a NEW reviewer context, not a historical tool invocation, updated source version, current-price fetch, original agent correction or retroactive procedural clearance.

## Packet shape

| Field | Frozen contents |
|---|---|
| schema_version, packet_id | `recorded-source-packet-0.1`; deterministic content-derived `recorded-case:` identity |
| layer, run_id | `original_recorded_execution`; selected original run ID |
| source | session_id, model, fixture_id, fixture_digest, fixture_origin, upstream_commit, trustkernel_feedback |
| source_files | List of `{path,sha256,bytes}` for raw JSONL/SQLite, final state, run manifest, fixture, pinned refined ledger, v0.2 pin/mapping files |
| ledger_pin | build_id, canonical_sha256, versions; pinned corrected refined-v3/950d60... |
| report | `{field:'market_report',text,anchor}`; full original report remains available |
| claim | `{kind,quote,anchor,mapping}`; kind scalar_close or relational_close |
| instruction | `{required_tool,text,anchor}` for original before-final-report snapshot instruction |
| call_context | `{actor,input_event,output_event,span_id,messages}`; complete original raw start/end events; messages preserve ordered `{pointer,role,content}` |
| prefix | `{seq_start,seq_end_inclusive,events,tool_invocations,retrievals,audit}`; complete raw dense prefix before selected report output |
| evidence | Dict keyed by all seven fixture evidence IDs; repository presence is distinct from historical retrieval/input exposure |
| coverage, limits | Explicit source/claim/capture/semantic limits, feedback disabled and original response unobserved |

`tool_invocations` entries are `{seq,event_id,span_id,tool,arguments,actor,raw_ref}`. `retrievals` are `{seq,event_id,evidence_key,content_digest,raw_ref}`. `raw_ref` retains path/hash/event_seq/event_id/event_hash. Tool invocation and evidence retrieval remain separate events. Actual recorded checkpoint namespace determines actor; unknown attribution is not inferred from prose. Normalized views are checked against the original raw prefix, so deleting a normalized invocation cannot manufacture absence.

An evidence entry has `{key,content,content_digest,anchor,source_version:null,snapshot_identity,valid_date,date_precision,declared_observed_at,observed_time_precision,access}`. Content digest uses this module's canonical JSON string representation. `snapshot_identity` combines recorded fixture digest and content digest; it is NOT an observed source version. Date-only daily OHLCV remains date precision; `declared_observed_at` preserves the fixture's supplied timestamp and is labeled `declared_fixture_second_not_market_attestation`. No TTL60 from the earlier authored scenario applies. `access={available_in_repository,retrieval_event_seqs,input_exposures}`. Missing exact/decoded matches mean not identified by these methods, not proof that no partial/paraphrased content existed.

An input exposure is `{anchor,message_pointer,message_role,mode,lineage}`. Role is the actual recorded role. These selected wrap-up inputs contain prefixed tool-return envelopes as **human** messages; decoding them never upgrades their role to tool or proves direct tool-message lineage. Prior recorded retrievals and decoded input presence are exposed as separate facts. `mode=decoded_envelope_presence` with `lineage=recorded_wrap_up_decoded_envelope_presence` describes decoded matches. Literal matches outside an envelope use `exact_input_content` / `recorded_wrap_up_content_presence` only when exact literal characters exist.

## Anchors and decoding

Every exact string anchor is `{path,sha256,json_pointer,event_seq,event_id,event_hash,start,end,quote,transform}`. Paths are project-relative; JSONL pointers address the selected event. Event fields are null for standalone JSON files. Coordinates are zero-based half-open Python Unicode code points. Raw text has `transform=null`.

For decoded envelopes, `anchor.json_pointer` remains the EXACT ORIGINAL message container pointer. `transform={name,prefix,json_pointer,container_sha256,coordinates}` names `json_parse` or `tool_return_prefix_then_json_parse`, retains the exact removed prefix, uses decoded pointer `/evidence/content`, hashes the entire original container string as UTF-8 SHA-256 and declares `coordinates='decoded_unicode_code_points'`. The anchor's quote/start/end then address the decoded evidence content, not escaped raw JSON characters. Source path/hash/event identities still bind the original artifact. Validator reconstructs the transform and original container hash before checking spans. Neither quote matching nor envelope decoding establishes source independence or private reliance.

## Selected actual cases and mapping

Sol0 report originates from input67/output69; complete prefix is1..68. Its selected original sentence is `[1939,2053)`: “The final session reaches a higher high but closes below both its opening price and the preceding session’s close.” Mapping is explicitly authored `lt_open_and_previous_close`, with no fabricated scalar Sol close claim. The comparator can check source CSV Close2540 < Open2550 and Close2540 < previous Close2550 under that declared mapping. This does not certify every interpretive clause or all agent dependencies.

Terra0 originates from input73/output75; prefix1..74. Numeric quote `2,540` is `[346,351)`. Mapping carries entity ETH-USD, date2026-10-28, unitUSD, fieldClose, value2540 and operator equals. The contextual scalar mapping was accepted by the human; this does not make all derived support or interpretation independently validated. Both mappings are scoped to synthetic fixture consistency.

Both original final inputs carry decoded E_PRICE. Sol has no original required snapshot invocation/retrieval/exposure; Terra has snapshot retrieval event63 and decoded snapshot presence. Original feedback was disabled. Sol's before-report omission remains a historical FAIL even after a new reviewer retrieves E_SNAPSHOT. Full-agent dependency completeness, source-version evolution, live freshness and Hold suitability remain unknown/unestablished.

## New reviewer retrieval receipt

Receipt fields are `{receipt_id,layer:'new_reviewer_retrieval',retrieved_at,actor:'local_reviewer_replay',source_packet_id,source_run_id,evidence_key,content,content_digest,source_anchor,source_version:null,snapshot_identity,source_origin,original_history_modified:false,historical_tool_invocation_created:false,source_observed_at,limits,receipt_digest}`. `source_anchor` points to original fixture content with transform null. It does not claim that the historical model saw the new reviewer's retrieval. No assessment/final-clearance is generated by this adapter; parent/rules own review findings and readiness scope.

## Plan and validation

Completed: source packet/API, explicit decoding/provenance contract, pinned canonical artifact validation, source-defense checks and 14 dedicated tests. Command from Desktop TrustKernel:

```powershell
.\.venv\Scripts\python.exe -m unittest recorded_loop.tests.test_source_adapter -v
```

Final local result: 14 tests passed (4.163 seconds). They cover selected actual calls/spans, Sol/Terra protocol difference, all-six source audit through parent helper, source hash and missing manifest entries, raw prefix omission, normalized tool suppression, wrong call/time/role, span/instruction mutation, forged input exposure/transform, source-version/precision and original-response fabrication, new immutable-history receipt separation, backdating, deterministic packets and detached returns. Test receipts are local reviewer-interface checks, not real original feedback or source corrections. No historical input bytes, prior first-loop implementation or other lane files were modified by this lane.

Final packet identities remain Sol `recorded-case:5367bc909ac446b755c2d760317c95dbb660b199583938eef4219c622c29e4d8` and Terra `recorded-case:b9d1c24d5140796d2e4c5745888bc59bd5831fbf60623a7aba2ada610cb44d1b`. Derive them from the built packets rather than hardcoding consumer assumptions. Parent owns persisted reviewer loop, integration tests and completion announcement. No end-to-end completion is claimed by source packet construction.
