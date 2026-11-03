# Procedural loop packet contract 0.1

Status: implemented, local synthetic fixture interface. This contract validates
packet structure and identity. An empty validation issue list does not certify
facts, complete dependency capture, decision quality or trading suitability.
The verifier owns findings, temporal policy and clearance issuance. The runner
owns append-only persistence and simulated host response. All historical
`verification/` sources/releases and existing budgets remain untouched.

## Public API

All imports are from `procedural_loop.contracts` using standard-library Python.

```python
SCHEMA_VERSION = "procedural-loop-contract-0.1"
canonical_json(value) -> str
digest(value) -> str
text_digest(text: str) -> str
parse_time(value: str | None) -> datetime | None
validate_packet(packet: dict, previous: dict | None = None) -> list[dict]
require_valid_packet(packet: dict, previous: dict | None = None) -> None
clearance_binding(packet: dict) -> dict
binding_matches(binding: dict, packet: dict) -> bool
```

`require_valid_packet` raises `ContractError` (a `ValueError`) with an `.issues`
list. Each issue has `path` (JSON Pointer), `code` and `message`. Validation and
binding functions do not mutate inputs. `clearance_binding` raises on invalid
input. `binding_matches` returns false on invalid input, missing or extra binding
keys, or any changed bound input. It does not authenticate a clearance issuer.

`contract.schema.json` specifies the entire packet shape. The runtime implements
the schema keywords that file uses, then checks content hashes, range bounds,
scope, uniqueness and optional previous-packet immutability. This is not a
general JSON Schema engine. Independent JSON Schema tools must also enforce
date-time format; runtime applies a stricter explicit-offset clock profile.

## Packet shape

Required top-level keys: `schema_version`, `packet_id`, `run_id`, `context`,
`capabilities`, `evidence`, `proposal`, `policy`. Objects are closed except policy,
whose extra JSON fields are allowed and bound by its digest.

| Object | Required fields |
| --- | --- |
| context | id, positive integer revision, observed_at, event_refs |
| capability | name, scope, state, detail |
| evidence | id, source_id, source_version, supersedes, valid_at, retrieved_at, recorded_at, content, content_digest, pointer, run_id, actor_id, call_id, causal_refs, status |
| pointer | uri, json_pointer, span |
| proposal | id, positive integer revision, as_of, created_at, run_id, actor_id, call_id, causal_refs, text, dependencies, dependency_completeness, extracts |
| dependency | evidence_id, source_version, status |
| extract | id, evidence_id, source_version, span, quote, field, value, unit |
| policy | id, version, nonnegative integer max_age_seconds, required_capabilities |

All IDs, versions, field names and reference IDs are nonempty strings. `value`
is a string to preserve authored decimal spelling; numeric interpretation belongs
to the verifier. `unit` may be null. `text`, `content`, `quote` and capability
`detail` may be empty. `event_refs`, `causal_refs`, `supersedes` and
`required_capabilities` are unique string lists. Dependencies are a unique list
of dependency objects or null. All other collection fields are lists.

Enums:

- capability state: CAPTURED / NOT_CAPTURED / UNKNOWN
- evidence status: AVAILABLE / NO_DATA
- dependency status: DECLARED / PROVISIONAL
- dependency_completeness: COMPLETE / PARTIAL / UNKNOWN

Capability `scope` must equal packet `run_id`; proposal and evidence must also
belong to that run. Actor/call/event IDs and causal references are opaque observed
identifiers. This boundary does not invent actor topology or assert causal
completeness. The fixture capability names agreed with the orchestrator are
`evidence_timestamps`, `source_versions`, `source_text`, `declared_dependencies`,
`observed_prefix`. Other names are structurally allowed; the policy/verifier
determines which are required. Capture declarations are adapter assertions.

## Clocks and observed context

All clock fields are RFC3339 strings with seconds and an explicit timezone or
null. Naive/date-only/malformed strings and the unknown offset `-00:00` are
invalid; null is the representation of an unknown instant. Offset conversion is
supported; strings are never silently rewritten or defaulted to wall time.

- evidence `valid_at`: instant the source observation describes
- `retrieved_at`: instant the adapter received this evidence occurrence
- `recorded_at`: instant it entered this adapter's observed record
- proposal `as_of`: intended decision-use instant
- proposal `created_at`: proposal production instant
- context `observed_at`: observed-prefix ceiling for this snapshot

The evidence list is exactly the observed prefix supplied by the adapter, not
future fixture versions. The verifier must check clocks/order against the
context and decision, and assess supersession only within that prefix. The
fixture uses half-open eligibility: age **>= max_age_seconds** is expired,
including equality at 60 seconds for its authored TTL60 policy. The contract
does not implement expiry. Refresh can reveal v2 measured at t+60 only when
retrieved/recorded at t+65; it is absent from the earlier t+61 snapshot.

## Original wording and spans

`content` retains the exact observed source string. `content_digest` is SHA256
of its exact UTF-8 bytes, without JSON wrapping or newline normalization.
`pointer.uri` and RFC6901 `json_pointer` retain the source location. The pointer
`span` selects an inspection span **in content**, not an external file byte
offset. Extract `span` selects original text in the referenced evidence content.
Every span is a half-open `[start,end]` pair of nonnegative integer Python
Unicode code-point indices; booleans are not integers. Reversed/out-of-range
spans are invalid. Empty spans are well-formed and left to the verifier.

For `ETH-USD Close = 2540 USD.` the full pointer span is `[0,25]`; the scalar
span is `[16,20]`, yielding exact quote `2540`. An extract additionally retains
its declared source_version, field `Close`, value `2540` and unit `USD`.
The checker can compare this wording and mapping against original content.
The contract deliberately accepts a different quote/value/source_version so
those faults can produce a typed verifier finding instead of a parse error.

## Unknown versus invalid

Unknown clocks, null dependencies, incomplete/unknown dependency completeness,
PROVISIONAL dependencies, missing capabilities and UNKNOWN/NOT_CAPTURED capability
states remain well-formed. Missing referenced evidence/superseded IDs remain
well-formed because an observed capture can be incomplete. They require verifier
INCONCLUSIVE or another explicit policy finding; shape validation never converts
them to PASS. NO_DATA is an observation status, not a zero market value.

Wrong JSON types, omitted required keys, misspelled closed-object keys, illegal
enums, digest mismatch, duplicate evidence/extract/capability identities,
cross-run scope and malformed spans/clocks are invalid contract input. A verifier
can wrap those issues in ERROR findings. Temporal inversions, future evidence,
supersession relevance and exact extract correspondence are verifier obligations.

## Immutable identities and clearance binding

Within a run, packet_id binds the whole packet; `(proposal.id,revision)` binds
the entire proposal; `(policy.id,version)` binds the entire policy;
`(context.id,revision)` binds the context plus complete evidence and capability
lists. Evidence id binds its occurrence including clocks and provenance.
`(source_id,source_version)` binds content_digest, valid_at and status; distinct
retrieval occurrences may retain that same source version with distinct IDs.
Changed inputs require new relevant identities/revisions, rather than overwrites.
Self-supersession is invalid. This boundary does not infer a global version order.

`validate_packet(current, previous=old)` checks these invariants against one
previous valid packet. Caller persistence must compare against retained history
to detect non-adjacent identity reuse; the module has no hidden global registry.
Different runs cannot be compared using `previous`.

`clearance_binding` returns exactly:

```text
contract_version, run_id, packet_id, packet_digest,
context_digest, proposal_digest, policy_digest, evidence_digest, capabilities_digest
```

Each component digest hashes the exact corresponding object/list. packet_digest
hashes the entire packet. Thus a changed as-of, proposal revision, dependency,
source text/version, policy, evidence order, context revision or capture declaration
cannot reuse its binding. A historical cleared packet remains a historical
record; a new use requires a current assessment and binding. The verifier alone
may issue clearance after all required checks pass; a binding can describe an
unknown or failed packet and is not itself permission or enforcement.

Canonical JSON sorts object keys, uses compact separators, retains Unicode and
rejects non-JSON values, non-string keys, NaN/infinity and unpaired surrogates.
No RFC8785 or cross-language numeric canonicalization claim is made. Ordered
arrays and distinct timestamp/string spellings are intentionally significant.
Both binding comparison and optional previous validation are read-only.

## Lane plan and validation

Now complete: interface frozen; all 16 dedicated contract tests pass (2026-11-02).
Next: verifier/adapters consume the frozen API; parent owns integration/replay.
Later: any broader capture/version semantics require an explicit successor.
No source migration, global claim extraction or historical rebuild is included.

| Risk | Contract test | Pass condition |
| --- | --- | --- |
| Unknown captured as success | Null/partial/provisional inputs | Remain valid without granting clearance |
| Faulty extraction hidden by parser | Wrong quote/value/version | Remain consumable for verifier findings |
| Malformed input crashes verifier | Type/clock/span/hash/key/scope mutations | Structured issues and ContractError |
| Stale clearance reused | Mutate each bound component | Exact binding comparison returns false |
| Source or decision bytes overwritten | Previous packet and same-packet conflicts | IMMUTABLE_IDENTITY or conflict issue |
| Host silently mutates packet | Deep-copy input assertions | No input bytes change |
| Unstable reproducibility | Object-key reorder and UTF8 distinction | Canonical digests stable; raw text distinct |

Dedicated command (does not run legacy rebuild tests):

```powershell
.venv\Scripts\python.exe -m unittest procedural_loop.tests.test_contract -v
```

Observed result: 16 tests passed in 0.022s. This verifies the packet boundary,
not an executed end-to-end loop; final integration is the orchestrator's lane.
