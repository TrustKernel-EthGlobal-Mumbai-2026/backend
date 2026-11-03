"""Agent-neutral offline packet boundary. Validation never grants clearance.

The companion JSON schema owns structural shape. The small validator below
implements only the schema keywords used by that file; no third-party runtime.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = "procedural-loop-contract-0.1"
_SCHEMA = json.loads(Path(__file__).with_name("contract.schema.json").read_text(encoding="utf-8"))
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")


class ContractError(ValueError):
    def __init__(self, issues):
        self.issues = copy.deepcopy(issues)
        super().__init__("; ".join(f"{i['path']}: {i['code']} {i['message']}" for i in issues))


def _json_only(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_only(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_only(item)
        return
    raise ValueError("Only finite JSON values with string object keys are supported")


def canonical_json(value):
    """Exact JSON representation used locally; not a general RFC8785 claim."""
    _json_only(value)
    result = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    result.encode("utf-8")  # Reject unpaired surrogates before hashing/inspection.
    return result


def text_digest(text):
    if type(text) is not str:
        raise ValueError("text_digest requires a string")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest(value):
    return text_digest(canonical_json(value))


def parse_time(value):
    """None means UNKNOWN; invalid or timezone-naive clocks raise ValueError."""
    if value is None:
        return None
    if type(value) is not str or not _TIME.fullmatch(value):
        raise ValueError("Expected RFC3339 timestamp with seconds and explicit timezone")
    # RFC3339 -00:00 means offset unknown, so it cannot establish an instant.
    if value.endswith("-00:00"):
        raise ValueError("Unknown UTC offset -00:00 is not an observed instant; use null")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Timezone offset is outside RFC3339 bounds")
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)


def _issue(issues, path, code, message):
    issues.append({"path": path or "/", "code": code, "message": message})


def _path(path, key):
    return path + "/" + str(key).replace("~", "~0").replace("/", "~1")


def _shape(value, schema, path, issues):
    if "$ref" in schema:
        node = _SCHEMA
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        return _shape(value, node, path, issues)
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    tests = {"null": value is None, "object": type(value) is dict,
             "array": type(value) is list, "string": type(value) is str,
             "integer": type(value) is int, "boolean": type(value) is bool,
             "number": type(value) in (int, float)}
    if types and not any(tests[t] for t in types):
        _issue(issues, path, "TYPE", "Expected " + " or ".join(types))
        return
    if "const" in schema and value != schema["const"]:
        _issue(issues, path, "CONST", "Unsupported contract version")
    if "enum" in schema and value not in schema["enum"]:
        _issue(issues, path, "ENUM", "Value is outside the declared vocabulary")
    if type(value) is dict:
        for key in schema.get("required", []):
            if key not in value:
                _issue(issues, _path(path, key), "REQUIRED", "Required field is absent")
        for key, item in value.items():
            spec = schema.get("properties", {}).get(key)
            if spec is not None:
                _shape(item, spec, _path(path, key), issues)
            elif schema.get("additionalProperties") is False:
                _issue(issues, _path(path, key), "UNKNOWN_FIELD", "Unexpected field")
    if type(value) is list:
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", math.inf):
            _issue(issues, path, "LENGTH", "Array length is outside allowed bounds")
        if schema.get("uniqueItems") and len({canonical_json(x) for x in value}) != len(value):
            _issue(issues, path, "DUPLICATE", "Array members must be unique")
        for index, item in enumerate(value):
            _shape(item, schema.get("items", {}), _path(path, index), issues)
    if type(value) is str:
        if len(value) < schema.get("minLength", 0):
            _issue(issues, path, "LENGTH", "String is too short")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            _issue(issues, path, "PATTERN", "String does not match required format")
        if schema.get("format") == "date-time":
            try:
                parse_time(value)
            except ValueError as exc:
                _issue(issues, path, "TIMESTAMP", str(exc))
    if type(value) in (int, float) and value < schema.get("minimum", -math.inf):
        _issue(issues, path, "RANGE", "Number is below allowed minimum")


def _duplicates(items, key, path, issues):
    seen = set()
    for index, item in enumerate(items):
        identity = key(item)
        if identity in seen:
            _issue(issues, _path(path, index), "DUPLICATE_ID", "Identity repeats in packet")
        seen.add(identity)


def _span(span, text, path, issues):
    if span[1] < span[0] or (text is not None and span[1] > len(text)):
        _issue(issues, path, "SPAN_BOUNDS", "Expected half-open span within original content")


def _context_identity(packet):
    return {key: packet[key] for key in ("context", "evidence", "capabilities")}


def _immutability(previous, packet, issues):
    if previous["run_id"] != packet["run_id"]:
        _issue(issues, "/run_id", "PREVIOUS_RUN", "Previous packet belongs to a different run")
        return
    def unchanged(same_key, before, after, path):
        if same_key and digest(before) != digest(after):
            _issue(issues, path, "IMMUTABLE_IDENTITY", "Changed bytes require a new identity/revision")
    unchanged(previous["packet_id"] == packet["packet_id"], previous, packet, "/packet_id")
    for name, version in (("proposal", "revision"), ("policy", "version")):
        a, b = previous[name], packet[name]
        unchanged((a["id"], a[version]) == (b["id"], b[version]), a, b, "/" + name)
    a, b = previous["context"], packet["context"]
    unchanged((a["id"], a["revision"]) == (b["id"], b["revision"]),
              _context_identity(previous), _context_identity(packet), "/context")
    prior_ids = {e["id"]: e for e in previous["evidence"]}
    prior_versions = {(e["source_id"], e["source_version"]): e for e in previous["evidence"]}
    for index, evidence in enumerate(packet["evidence"]):
        path = f"/evidence/{index}"
        if evidence["id"] in prior_ids:
            unchanged(True, prior_ids[evidence["id"]], evidence, path)
        prior = prior_versions.get((evidence["source_id"], evidence["source_version"]))
        if prior is not None:
            fields = ("content_digest", "valid_at", "status")
            unchanged(True, {k: prior[k] for k in fields}, {k: evidence[k] for k in fields}, path)


def validate_packet(packet, previous=None):
    """Return structural/identity issues. Empty list is NOT procedural clearance.

    Unknown prerequisites (null clocks/dependencies, unknown capture), unavailable
    referenced evidence and faithful-extraction disagreements belong to verifier.
    """
    issues = []
    try:
        canonical_json(packet)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        _issue(issues, "/", "JSON", str(exc))
        return issues
    _shape(packet, _SCHEMA, "", issues)
    if issues:
        return issues
    run = packet["run_id"]
    _duplicates(packet["evidence"], lambda e: e["id"], "/evidence", issues)
    _duplicates(packet["capabilities"], lambda c: (c["name"], c["scope"]), "/capabilities", issues)
    _duplicates(packet["proposal"]["extracts"], lambda e: e["id"], "/proposal/extracts", issues)
    by_id = {e["id"]: e for e in packet["evidence"]}
    by_version = {}
    for index, evidence in enumerate(packet["evidence"]):
        path = f"/evidence/{index}"
        if evidence["run_id"] != run:
            _issue(issues, path + "/run_id", "RUN_SCOPE", "Evidence belongs to a different run")
        if text_digest(evidence["content"]) != evidence["content_digest"]:
            _issue(issues, path + "/content_digest", "DIGEST", "Original content digest mismatch")
        _span(evidence["pointer"]["span"], evidence["content"], path + "/pointer/span", issues)
        if evidence["id"] in evidence["supersedes"]:
            _issue(issues, path + "/supersedes", "SELF_REFERENCE", "Evidence cannot supersede itself")
        version = (evidence["source_id"], evidence["source_version"])
        fixed = {k: evidence[k] for k in ("content_digest", "valid_at", "status")}
        if version in by_version and by_version[version] != fixed:
            _issue(issues, path, "SOURCE_VERSION_CONFLICT", "One source version has conflicting original facts")
        by_version[version] = fixed
    if packet["proposal"]["run_id"] != run:
        _issue(issues, "/proposal/run_id", "RUN_SCOPE", "Proposal belongs to a different run")
    for index, capability in enumerate(packet["capabilities"]):
        if capability["scope"] != run:
            _issue(issues, f"/capabilities/{index}/scope", "RUN_SCOPE", "Capability scope must equal this run")
    for index, extract in enumerate(packet["proposal"]["extracts"]):
        source = by_id.get(extract["evidence_id"])
        _span(extract["span"], source["content"] if source else None,
              f"/proposal/extracts/{index}/span", issues)
    if previous is not None:
        prior_issues = validate_packet(previous)
        if prior_issues:
            _issue(issues, "/previous", "INVALID_PREVIOUS", "Cannot compare against an invalid previous packet")
        else:
            _immutability(previous, packet, issues)
    return issues


def require_valid_packet(packet, previous=None):
    issues = validate_packet(packet, previous)
    if issues:
        raise ContractError(issues)


def clearance_binding(packet):
    """Return inputs to verifier clearance issuance, never a clearance itself."""
    require_valid_packet(packet)
    return {"contract_version": SCHEMA_VERSION, "run_id": packet["run_id"],
            "packet_id": packet["packet_id"], "packet_digest": digest(packet),
            **{name + "_digest": digest(packet[name])
               for name in ("context", "proposal", "policy", "evidence", "capabilities")}}


def binding_matches(binding, packet):
    """Exact comparison only. A matching binding does not validate an issuer."""
    try:
        return type(binding) is dict and canonical_json(binding) == canonical_json(clearance_binding(packet))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return False
