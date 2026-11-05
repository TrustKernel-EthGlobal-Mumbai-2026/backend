"""Versioned JSON boundary. Validation checks shape/integrity, never authority.

The bundled schema is structural; cross-field invariants are checked here.
No issuer authentication, hidden registry, network or clock defaults are provided.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

CONTRACT_VERSION = "continuous-verification-0.2"
_SCHEMA = json.loads((Path(__file__).parent / "schemas/contract.schema.json").read_text("utf-8"))
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")


class ContractError(ValueError):
    def __init__(self, issues):
        self.issues = copy.deepcopy(issues)
        super().__init__("; ".join(f"{x['path']}: {x['code']}" for x in issues))


def canonical_json(value):
    """Canonical local JSON (not RFC8785); exact strings and array order matter."""
    def walk(v):
        if v is None or type(v) in (str, bool, int):
            return
        if type(v) is float and math.isfinite(v):
            return
        if type(v) is list:
            for x in v:
                walk(x)
            return
        if type(v) is dict and all(type(k) is str for k in v):
            for x in v.values():
                walk(x)
            return
        raise ValueError("Expected finite JSON with string keys")
    walk(value)
    result = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    result.encode("utf-8")
    return result


def text_digest(text):
    if type(text) is not str:
        raise ValueError("Expected text")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest(value):
    return text_digest(canonical_json(value))


def _issue(issues, path, code, message):
    issues.append({"path": path, "code": code, "message": message})


def _shape(value, spec, path, issues):
    if "$ref" in spec:
        spec = _SCHEMA["$defs"][spec["$ref"].split("/")[-1]]
    types = spec.get("type", [])
    types = [types] if isinstance(types, str) else types
    match = {"null": value is None, "object": type(value) is dict,
             "array": type(value) is list, "string": type(value) is str,
             "integer": type(value) is int, "boolean": type(value) is bool}
    if types and not any(match.get(t, False) for t in types):
        _issue(issues, path, "TYPE", str(types))
        return
    if "const" in spec and value != spec["const"]:
        _issue(issues, path, "CONST", "Unexpected version/value")
    if "enum" in spec and value not in spec["enum"]:
        _issue(issues, path, "ENUM", "Unknown value")
    if type(value) is dict:
        props = spec.get("properties", {})
        for k in spec.get("required", []):
            if k not in value:
                _issue(issues, path + "/" + k, "REQUIRED", "Missing key")
        for k, v in value.items():
            if k in props:
                _shape(v, props[k], path + "/" + k, issues)
            elif spec.get("additionalProperties") is False:
                _issue(issues, path + "/" + k, "KEY", "Unknown key")
    if type(value) is list:
        if len(value) < spec.get("minItems", 0) or len(value) > spec.get("maxItems", len(value)):
            _issue(issues, path, "LENGTH", "Wrong item count")
        if spec.get("uniqueItems") and len({canonical_json(x) for x in value}) != len(value):
            _issue(issues, path, "DUPLICATE", "Duplicate item")
        for i, v in enumerate(value):
            _shape(v, spec.get("items", {}), f"{path}/{i}", issues)
    if type(value) is str:
        if len(value) < spec.get("minLength", 0) or ("pattern" in spec and not re.fullmatch(spec["pattern"], value)):
            _issue(issues, path, "STRING", "Invalid string")
        if spec.get("format") == "date-time":
            try:
                if not _TIME.fullmatch(value) or value.endswith("-00:00"):
                    raise ValueError()
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                _issue(issues, path, "TIME", "Expected explicit RFC3339 instant")
    if type(value) is int and value < spec.get("minimum", value):
        _issue(issues, path, "RANGE", "Below minimum")


def _validate(value, name):
    issues = []
    try:
        canonical_json(value)
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError([{"path": "$", "code": "JSON", "message": "Invalid JSON value"}]) from None
    _shape(value, _SCHEMA["$defs"][name], "$", issues)
    if issues:
        raise ContractError(issues)


def _require(condition, code, message, path="$"):
    if not condition:
        raise ContractError([{"path": path, "code": code, "message": message}])


def _previous(value, previous, name, identity):
    if previous is None:
        return
    globals()["validate_" + name](previous)
    _require(value["run_id"] == previous["run_id"], "SCOPE", "Previous object belongs to another run")
    if all(value[k] == previous[k] for k in identity):
        _require(value == previous, "IMMUTABLE_IDENTITY", "Changed bytes require a new identity/revision")


def validate_event(event, *, previous=None):
    """Raise ContractError for malformed event; return None, without mutation."""
    _validate(event, "event")
    _validate(event["payload"], "payload_" + event["event_type"])
    _require(text_digest(event["content"]) == event["content_digest"], "DIGEST", "Content bytes mismatch")
    _require(event["event_id"] not in event["parents"], "CAUSALITY", "Event cannot parent itself")
    if event["origin"]["span"] is not None:
        a, b = event["origin"]["span"]
        _require(a <= b <= len(event["content"]), "SPAN", "Span outside retained content")
    _previous(event, previous, "event", ("event_id",))
    if previous is not None and event["stream_id"] == previous["stream_id"] and event["sequence"] == previous["sequence"]:
        _require(event == previous, "SEQUENCE_CONFLICT", "One event per stream sequence")
    if previous is not None and event["event_type"] == previous["event_type"] == "source":
        current, old = event["payload"], previous["payload"]
        if (current["source_id"], current["source_version"]) == (old["source_id"], old["source_version"]):
            _require(all(current[k] == old[k] for k in ("valid_at", "status")) and event["content_digest"] == previous["content_digest"], "IMMUTABLE_SOURCE_VERSION", "Source version bytes/status/valid time changed")


def validate_checkpoint(checkpoint, *, previous=None):
    _validate(checkpoint, "checkpoint")
    ids = [s["stream_id"] for s in checkpoint["streams"]]
    _require(len(set(ids)) == len(ids), "DUPLICATE", "Duplicate stream")
    for stream in checkpoint["streams"]:
        names = [c["name"] for c in stream["capabilities"]]
        _require(len(set(names)) == len(names), "DUPLICATE", "Duplicate capability")
        for gap in stream["gaps"]:
            _require(gap[0] <= gap[1], "GAP", "Reversed inclusive gap range")
    _previous(checkpoint, previous, "checkpoint", ("checkpoint_id", "revision"))


def validate_policy(policy, *, previous=None):
    _validate(policy, "policy")
    _require(len({x["check_id"] for x in policy["checks"]}) == len(policy["checks"]), "DUPLICATE", "Duplicate check")
    if previous is not None:
        validate_policy(previous)
        if (policy["policy_id"], policy["version"]) == (previous["policy_id"], previous["version"]):
            _require(policy == previous, "IMMUTABLE_IDENTITY", "Changed policy needs a new version")


def validate_request(request, *, previous=None):
    _validate(request, "request")
    _require(text_digest(request["proposal"]["content"]) == request["proposal"]["content_digest"], "DIGEST", "Proposal bytes mismatch")
    _require(set(request["checks"]) <= set(request["policy"]["checks"]), "CHECKS", "Request checks must be policy-bound")
    _previous(request, previous, "request", ("request_id",))
    if previous is not None and request["proposal"]["proposal_id"] == previous["proposal"]["proposal_id"] and request["proposal"]["revision"] == previous["proposal"]["revision"]:
        _require(request["proposal"] == previous["proposal"], "IMMUTABLE_IDENTITY", "Proposal changed without revision")


def validate_result(result):
    _validate(result, "result")
    if result["binding"] is not None:
        _validate(result["binding"], "binding")
        _require(result["binding"]["run_id"] == result["run_id"] and result["binding"]["request_id"] == result["request_id"], "SCOPE", "Result binding scope mismatch")
    _require(len({f["check_id"] for f in result["findings"]}) == len(result["findings"]), "DUPLICATE", "Duplicate finding")
    if result["status"] != "ASSESSED":
        _require(result["disposition"] == "HOLD" and all(f["outcome"] == "INCONCLUSIVE" for f in result["findings"]), "OUTCOME", "Unready/error results cannot pass checks")
    else:
        _require(result["binding"] is not None and bool(result["findings"]), "BINDING", "Assessment requires bound findings")
    _require((result["status"] == "ERROR") == bool(result["issues"]), "ISSUES", "Only errors carry issues")
    _require(result["assessment_id"] == "assessment-" + digest({k: v for k, v in result.items() if k != "assessment_id"}), "DIGEST", "Assessment identity mismatch")


def assessment_binding(request, *, checkpoint, events, policy):
    """Hash all inputs, including prefix state and coverage, without issuing clearance."""
    validate_request(request)
    validate_checkpoint(checkpoint)
    validate_policy(policy)
    _require(type(events) is list, "TYPE", "Events must be an ordered list")
    for event in events:
        validate_event(event)
    return {"contract_version": CONTRACT_VERSION, "run_id": request["run_id"],
            "request_id": request["request_id"], "request_digest": digest(request),
            "proposal_digest": digest(request["proposal"]), "checkpoint_digest": digest(checkpoint),
            "policy_digest": digest(policy), "evidence_digest": digest(events)}


def binding_matches(binding, request, *, checkpoint, events, policy):
    """Exact read-only match; does not authenticate an assessment issuer."""
    try:
        return binding == assessment_binding(request, checkpoint=checkpoint, events=events, policy=policy)
    except (ContractError, ValueError):
        return False
