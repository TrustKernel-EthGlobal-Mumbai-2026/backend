# Continuous verification candidate contract 0.1

Status: executable candidate for orchestrator acceptance, 5 November 2026.
This successor does not change historical builders or the procedural-loop API.

## Public Python API

All imports below are available from `continuous_verification` on Python3.11,
standard library only. JSON dictionaries/lists are inputs and outputs. Inputs
are read-only; no network, clock default, persistence or transport is involved.

```python
CONTRACT_VERSION = "continuous-verification-0.1"
canonical_json(value) -> str
text_digest(text) -> str
digest(value) -> str
validate_event(event, *, previous=None) -> None
validate_checkpoint(checkpoint, *, previous=None) -> None
validate_policy(policy, *, previous=None) -> None
validate_request(request, *, previous=None) -> None
validate_result(result) -> None
assessment_binding(request, *, checkpoint, events, policy) -> dict
binding_matches(binding, request, *, checkpoint, events, policy) -> bool
verify(request, *, checkpoint, events, policy) -> dict
```

Validators raise `ContractError` with JSON `issues` (`path`, `code`, `message`).
Malformed input to `verify` returns `ERROR`, `HOLD`, issues and no binding.
`verify` accepts exactly the four keys in
[`schemas/example.json`](../../continuous_verification/schemas/example.json).
The example is authored, offline data, with unknown dependencies and clocks;
it is executable using `verify(**json.load(file))` and demonstrates two scoped
checks, not decision clearance. The authoritative structural definitions are
[`contract.schema.json`](../../continuous_verification/schemas/contract.schema.json)
under `$defs/event`, `checkpoint`, `policy`, `request`, `result`. Cross-field
hash, identity and span checks also require the Python validator.

## Integration responsibilities

B establishes checkpoints after durable ingest and projection, authenticates
collectors, registers the required stream set and supplies exactly every event
at positions 1 through `requested` in each declared stream. Sequence starts at
1; a restarted producer uses a new stream ID. Event IDs are run-wide unique;
stream position and event ID each bind one immutable event. Duplicate transport
receipts must be deduplicated by B before verification. The list order is part
of the evidence digest; B must preserve a deterministic view order.

Each stream records requested, contiguous ingested and projected watermarks,
inclusive unresolved gap ranges and capability observations. Capabilities name
`phase_boundaries`, `report_completion`, `model_input`, `tool_lifecycle` as needed,
with `CAPTURED`, `NOT_CAPTURED` or `UNKNOWN` plus basis event IDs. Basis references
must exist in the supplied prefix before a check can use the declaration.
These are collector/service assertions, never proof of uninstrumented activity.
Do not accept these assertions directly from an untrusted agent.

Checkpoint `established_by.basis=SERVICE_ESTABLISHED` is service-owned state.
`PRODUCER_REPORTED` remains valid but NOT_READY. A producer's
`checkpoint_observation` event is a request/observation, never that state.
The schema/digests cannot authenticate this distinction; the service must enforce
ownership. Requests after the prefix do not extend it. Checkpoint revisions bind
the complete vector and coverage. Late events require a new view and binding.

C captures exact retained report text, successful/error/unknown tool results,
and the actual assembled `model_input` event. Input payloads bind report ID and
revision and the event IDs actually included. The report names that input as a
parent and through `input_event_id`. Cross-stream causal claims are explicit
adapter observations; timestamps and ingestion order do not establish them.
`source` events retain source/version, valid/retrieved time and status separately;
their existence does not imply model exposure. A required tool result must be
included in the report input for the named snapshot check to PASS.

D forwards requests unchanged to the service; a policy reference binds the
entire policy digest and its available checks. Request `checks` selects a
nonempty subset. D must expose structured readiness, findings and issues rather
than turning process success into a successful assessment. The service obtains
the referenced checkpoint, policy and event view; clients do not authorize their
own policy/coverage by constructing valid JSON. Storage/transport signatures and
read cursors belong to B/D and are not frozen by this pure API.

## Outcomes and limits

`CAPTURE_GAP` means an explicit gap intersects the requested prefix. `NOT_READY`
means producer-only, lagging or incomplete projected state. Both return only
INCONCLUSIVE findings and HOLD. `ASSESSED` permits per-check
PASS/FAIL/INCONCLUSIVE. Missing report/input/coverage, unknown completion/tool
status, open phase or ambiguous causal boundary remain INCONCLUSIVE.

`report_completion` checks a captured closed report's COMPLETE versus
TRUNCATED/ERROR status. It does not infer semantic completeness from text.
`required_snapshot_before_market_report` checks a completed closed market report
with a captured assembled input and tool lifecycle: successful required tool
result included gives PASS; omission/error gives FAIL. The same tool result
outside the assembled input cannot satisfy this obligation. An incomplete
market report leaves the snapshot check INCONCLUSIVE; completion has its own FAIL.

Policy explicitly configures per-check FAIL/INCONCLUSIVE dispositions from
ADVISE/HOLD/RECHECK; HOLD dominates RECHECK dominates ADVISE. All passing selected
checks yield ADVISE, never global clearance. There is no TTL, source authority,
material-dependency completeness or global enforcement policy. Null dependencies
and UNKNOWN completeness are valid and remain declared unknown, even with PASS
procedural findings. The policy's treatment of findings is caller configuration,
not ratification of live trading policy.

Feedback delivery, next-input inclusion, acknowledgement and correction have
different event types with assessment/proposal/revision and related-event IDs.
One does not establish another or prove corrected behavior; a new assessment is
needed. No hidden reasoning claims are captured.

Exact UTF8 retained content hashes and Unicode code-point half-open spans apply
after the named redaction profile. Clocks may be null; other clocks require an
explicit RFC3339 timezone. Hashes bind bytes, not issuer identity, source truth
or authorization. Canonical JSON sorts keys, preserves array/string spelling,
rejects nonfinite values/non-JSON keys/unpaired surrogates and makes no RFC8785
cross-language numeric claim. Assessment IDs are deterministic content IDs.

Optional previous validation detects adjacent identity reuse. Service persistence
must enforce immutable run-wide history, proposal revision and policy/checkpoint
identity across all retained versions. Bindings include request/proposal,
checkpoint (coverage included), policy and entire ordered event view. Any changed
input needs a new binding. Host use additionally requires issuer authentication
and applicable explicit policy; `binding_matches` alone grants nothing.

## Remaining proposed decisions

Orchestrator acceptance of this candidate is pending. Service authentication,
complete registered stream coverage, host gate semantics and any live policy
remain separate decisions. This lane chooses no live freshness policy and
claims no model behavior, persistence, adapter integration or transport readiness.

Run dedicated tests with `py -3.11 -S -B -m unittest discover -s tests -p
test_continuous_contracts.py -v`. Negative verifier tests follow the candidate
milestone; the lane status records their actual results.
