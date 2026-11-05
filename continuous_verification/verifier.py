"""Pure deterministic named checks at an explicit observed prefix.

Service callers must authenticate collectors and establish checkpoint coverage.
This function cannot verify those external claims. It never emits global clearance.
"""
from .contracts import (
    CONTRACT_VERSION, ContractError, assessment_binding, digest, validate_request,
    validate_checkpoint, validate_event, validate_policy, _require,
)


def verify(request, *, checkpoint, events, policy):
    """Return a JSON result; malformed input becomes ERROR with structured issues.

    events is the exact service projection of every requested stream through its
    requested sequence, once each; late events must not be appended to this view.
    All inputs are read-only. No persistence, waits, I/O or wall clock involved.
    """
    result = {"contract_version": CONTRACT_VERSION, "assessment_id": "invalid-input",
              "run_id": "unknown", "request_id": "unknown", "status": "ERROR",
              "binding": None, "findings": [], "disposition": "HOLD", "issues": [],
              "scope": "declared_checks_at_checkpoint"}
    try:
        validate_request(request)
        result.update(run_id=request["run_id"], request_id=request["request_id"])
        validate_checkpoint(checkpoint)
        validate_policy(policy)
        _require(type(events) is list, "TYPE", "Events must be an ordered list")
        for event in events:
            validate_event(event)
        _require(checkpoint["run_id"] == request["run_id"] and all(e["run_id"] == request["run_id"] for e in events), "SCOPE", "Cross-run inputs")
        _require(request["checkpoint"] == {"checkpoint_id": checkpoint["checkpoint_id"], "revision": checkpoint["revision"], "digest": digest(checkpoint)}, "BINDING", "Checkpoint reference mismatch")
        _require(request["policy"] == {"policy_id": policy["policy_id"], "version": policy["version"], "digest": digest(policy), "checks": [c["check_id"] for c in policy["checks"]]}, "BINDING", "Policy reference mismatch")
        streams = {s["stream_id"]: s for s in checkpoint["streams"]}
        _require(bool(streams), "STREAMS", "No declared streams")
        ids, positions = set(), set()
        for event in events:
            _require(event["event_id"] not in ids, "DUPLICATE", "Event IDs are run-wide unique")
            pos = (event["stream_id"], event["sequence"])
            _require(pos not in positions, "SEQUENCE_CONFLICT", "Duplicate stream position")
            ids.add(event["event_id"])
            positions.add(pos)
            _require(event["stream_id"] in streams and event["sequence"] <= streams[event["stream_id"]]["requested"], "PREFIX", "Event outside requested prefix")
        result["binding"] = assessment_binding(request, checkpoint=checkpoint, events=events, policy=policy)
        gap = any(a <= s["requested"] for s in streams.values() for a, b in s["gaps"])
        ready = checkpoint["established_by"]["basis"] == "SERVICE_ESTABLISHED" and all(min(s["ingested_through"], s["projected_through"]) >= s["requested"] for s in streams.values())
        complete = all(sum(e["stream_id"] == s["stream_id"] for e in events) == s["requested"] for s in streams.values())
        if gap:
            result["status"] = "CAPTURE_GAP"
        elif not ready or not complete:
            result["status"] = "NOT_READY"
        else:
            result["status"] = "ASSESSED"
        by_id = {e["event_id"]: e for e in events}
        report = by_id.get(request["proposal"]["report_event_id"])
        rules = {r["check_id"]: r for r in policy["checks"]}
        for check in request["checks"]:
            outcome, reason, refs = "INCONCLUSIVE", "prefix_not_ready", []
            if result["status"] == "ASSESSED":
                outcome, reason, refs = _check(check, report, by_id, streams, policy)
            result["findings"].append({"check_id": check, "outcome": outcome, "reason": reason, "event_ids": refs})
        if result["status"] == "ASSESSED":
            dispositions = [rules[f["check_id"]]["on_fail" if f["outcome"] == "FAIL" else "on_inconclusive"] for f in result["findings"] if f["outcome"] != "PASS"]
            result["disposition"] = "HOLD" if "HOLD" in dispositions else "RECHECK" if "RECHECK" in dispositions else "ADVISE"
    except ContractError as exc:
        result.update(status="ERROR", disposition="HOLD", findings=[], issues=exc.issues, binding=None)
    result["assessment_id"] = "assessment-" + digest({k: v for k, v in result.items() if k != "assessment_id"})
    return result


def _captured(event, name, streams, by_id):
    stream = streams[event["stream_id"]]
    return any(c["name"] == name and c["state"] == "CAPTURED" and c["basis_event_ids"] and all(x in by_id for x in c["basis_event_ids"]) for c in stream["capabilities"])


def _check(check, report, by_id, streams, policy):
    if report is None or report["event_type"] != "report":
        return "INCONCLUSIVE", "report_unobserved", []
    refs = [report["event_id"]]
    p = report["payload"]
    if not _captured(report, "phase_boundaries", streams, by_id) or p["phase"] != "CLOSED":
        return "INCONCLUSIVE", "phase_not_closed_or_captured", refs
    if check == "report_completion":
        if not _captured(report, "report_completion", streams, by_id) or p["completion"] == "UNKNOWN":
            return "INCONCLUSIVE", "completion_unknown", refs
        return ("PASS", "report_complete", refs) if p["completion"] == "COMPLETE" else ("FAIL", "report_incomplete", refs)
    if p["report_type"] != "market":
        return "INCONCLUSIVE", "not_market_report", refs
    if p["completion"] != "COMPLETE" or not _captured(report, "report_completion", streams, by_id):
        return "INCONCLUSIVE", "market_report_not_complete", refs
    boundary = by_id.get(p["input_event_id"])
    if boundary is None or boundary["event_type"] != "model_input":
        return "INCONCLUSIVE", "input_boundary_unobserved", refs
    refs.append(boundary["event_id"])
    b = boundary["payload"]
    if (b["report_id"], b["report_revision"]) != (p["report_id"], p["revision"]) or b["boundary"] != "ASSEMBLED":
        return "INCONCLUSIVE", "input_boundary_mismatch", refs
    if not _captured(boundary, "model_input", streams, by_id) or not _captured(boundary, "tool_lifecycle", streams, by_id):
        return "INCONCLUSIVE", "input_or_tool_coverage_unknown", refs
    # Causality is explicit: report names the input and input names supplied events.
    # No ordering is inferred from timestamps or journal arrival across streams.
    if boundary["event_id"] not in report["parents"]:
        return "INCONCLUSIVE", "input_causality_unknown", refs
    if boundary["stream_id"] == report["stream_id"] and boundary["sequence"] >= report["sequence"]:
        return "INCONCLUSIVE", "input_order_conflict", refs
    supplied = [by_id.get(x) for x in b["included_event_ids"]]
    if any(e is None for e in supplied):
        return "INCONCLUSIVE", "input_evidence_missing", refs
    if any(e["stream_id"] == boundary["stream_id"] and e["sequence"] >= boundary["sequence"] for e in supplied):
        return "INCONCLUSIVE", "input_order_conflict", refs
    matches = [e for e in supplied if e["event_type"] == "tool_result" and e["payload"]["tool_name"] == policy["required_tool"]]
    if any(e["payload"]["status"] == "SUCCESS" for e in matches):
        return "PASS", "required_snapshot_in_report_input", refs + [e["event_id"] for e in matches]
    if any(e["payload"]["status"] == "UNKNOWN" for e in matches):
        return "INCONCLUSIVE", "tool_status_unknown", refs + [e["event_id"] for e in matches]
    return "FAIL", "required_snapshot_missing_or_failed", refs + [e["event_id"] for e in matches]
