# Finding envelope 0.2.0

This lane implements scoped mechanical claim → evidence → check → finding packets against a fixed release. The implementation uses standard-library Python only and imports no verification engine. It writes only this version directory. This is a local implementation slice, not a judge engine, independent evaluation or accepted semantic-support layer.

## Envelope

Each finding carries `finding_contract_version`, `finding_id`, `case_id`, `check` (ID, type, method version, implementation digest), `subject` (exact occurrence and proposition revision refs with row hashes/row versions, source/run/actor/call/event identity, exact source pointer/span and enclosing context), `ledger_context` (release ID/hash/versions, registry and overlay version, named corpus/cutoff/search limits), `mapping` (author/version/status, exact gates and normalization premises), `required_prerequisites`, typed `expected`/`observed`, `result` (status and reason code), `positive_witnesses`, `negative_witnesses`, `assumptions`, `limits`, UTC `assessed_at`, explicit nullable `supersedes`, and `accepted_factual_support=false`.

`finding-envelope.schema.json` documents the syntactic contract. The local tests check required envelope fields, IDs/digests, result/prerequisite invariants and actual source anchors; they do not claim to be a full standards-compliant JSON Schema validator. Positive/negative witness polarity is relative to the named check question. A rejected author reason can be positive evidence for the structural fact that it was rejected; it is not an accepted negative fact about the world.

The protocol-omission wording is present in the saved market report but is not selected as an existing canonical assertion. That one finding explicitly uses a lane-authored exact source-span occurrence and a separately named provisional wording-only proposition revision. Its definition is embedded in the packet and points to the real canonical sources_v2 report. No canonical ledger row or accepted semantic relation is fabricated. All other selected claim subjects use existing assertion or clause records.

Result vocabulary is PASS / FAIL / INCONCLUSIVE / NOT_APPLICABLE / ERROR. PASS and FAIL require every declared prerequisite met. FAIL concerns the named mechanical/policy obligation, never an unqualified false-fact label. Missing mapping, missing scope/precision or incomplete support search yields INCONCLUSIVE. NOT_APPLICABLE means the operation is outside its declared domain. ERROR means invalid inputs or execution/provenance failure; it must not be counted as unsupported. Release-binding/source-integrity errors can fail the entire preflight rather than fabricate a claim finding without a trustworthy subject.

For the scalar slice, the `expected` value comes from the anchored claim token. `observed` comes from a uniquely selected dated CSV Close cell. Decimal comparison runs only under explicit entity/date/USD/field/corpus gates. Authored gates check exact selected context, not correctness of its semantic interpretation. A PASS means fixture consistency conditional on that provisional mapping. It establishes no real ETH price, source independence, optimum action or private reliance.

## Identity, compatibility and reproducibility

Release identity is pinned in pin.json. Canonical JSONL is authoritative; SQLite is opened with mode=ro and query_only and selected rows must match their canonical counterparts. Input file hashes and selected raw source hashes are checked before/after assessment. Unchanged historical row versions are preserved inside the newer release context. This code does not regenerate any source release.

Source coordinates are Unicode code points in a decoded string, zero-based [start,end). JSON-envelope decoding is an explicit transform with original event pointer and source hash; content comparison does not grant a trusted tool role. Exact source delivery is always tied to its specific recorded attempt. Summary/marker matches do not become raw evidence delivery. Final-decision structured-render origin is carried as a pinned ledger relation; a saved final-state source anchor is independently resolved. It is not presented as a new independent rendering audit.

The check ID binds case/method/mapping/context. Finding ID hashes the entire envelope including subject, values, witnesses, implementation digest, timestamp and supersedes. Reusing a timestamp and identical files produces identical bytes. Changed source/mapping/method/time creates a new assessment identity. Supersedes is explicit, never inferred by filename. Packet directories refuse changed-byte overwrites. Their manifest records all pinned input hashes, selected SQLite row IDs, implementation/mapping hashes and packet/report digests. Historical October packets are unchanged and must not be run to refresh this version.

## Commands for the first slice

From `${PRIVATE_SOURCE_ROOT}`:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 explorations\rules\contract-v0.2\test_findings.py -v
.\.venv\Scripts\python.exe -B -X utf8 explorations\rules\contract-v0.2\assessments\assessment-1a6f20fb7d465d56aaa2a19f\implementation.py --suite slice --assessed-at 2026-11-01T14:37:31Z
```

The explicit UTC assessment timestamp is fixed for this reproducibility example. Use a new actual assessment timestamp for a new invocation; reuse the printed timestamp to reconstruct that invocation. No historical test discovery or ledger build/rebuild/export commands are part of this contract.

The first-slice command deliberately uses its saved implementation; today's expanded reader has a different implementation hash and therefore emits new finding IDs. Final case-set commands and assessment identity are in RESULTS.md. Each reported assessment preserves executable source, pin and mapping snapshots. Earlier development packets are retained but are not the reported deliverables.

## Unresolved policies

Fixture consistency and recorded-call access remain distinct scopes. Snapshot invocation is a protocol obligation, with no silent universal truth precedence. Mapping authoring remains provisional and support-search completeness is not claimed. Explicit dates/event order can be checked; intraday precision/freshness may remain unknown. Root identity is a declared lineage fact, not a full independence model. Conditional actions need actual portfolio/policy prerequisites. Reason markers describe an author's statement, not accepted support or logical sufficiency. These defaults are exposed in packets and can be revised only with a new assessment/version; no source truth is overwritten.
