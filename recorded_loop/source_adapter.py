"""Read-only selected review packets from actual TradingAgents recordings.

Recorded agents used synthetic frozen market evidence. Reviewer retrieval is a
new local event, never a historical tool invocation or model correction.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "20261030-010033-30min-597a75"
SESSION = ROOT / "runs" / SESSION_ID
SCHEMA_VERSION = "recorded-source-packet-0.1"
SUPPORTED_RUNS = ("sol-0530a9827c2c", "terra-2f66dbe7f15d")
LEDGER_SHA = "950d60f56d835d08cb01fa4bd24d93153ce48ab211bcc1b2f630b35a815a3556"
LEDGER_BUILD = "refined-v3-99d181ef7ca54fea4ff1"
REQUIRED_TOOL = "get_verified_market_snapshot"
INSTRUCTION = ("Before writing the final report, call get_verified_market_snapshot for this ticker "
    "and the current date, and treat it as the source of truth for any exact OHLCV, price-level, "
    "or indicator-value claim.")
SOL_QUOTE = "The final session reaches a higher high but closes below both its opening price and the preceding session’s close."


class SourceIntegrityError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path):
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _path(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise SourceIntegrityError("Source path outside project")
    return path


def _file(path):
    return {"path": _relative(path), "sha256": _sha(path), "bytes": path.stat().st_size}


@lru_cache(maxsize=1)
def _recorded_artifact_pins():
    """Read pinned canonical artifact rows only; never invoke a ledger builder."""
    path = ROOT / "verification/data/refined-v3/ledger.jsonl"
    if _sha(path) != LEDGER_SHA:
        raise SourceIntegrityError("Pinned canonical ledger changed")
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("table") == "artifacts":
            pins[row["path"]] = {"sha256": row["sha256"], "bytes": row["bytes"]}
    return pins


def _anchor(path, pointer, text, start=0, end=None, event=None, transform=None):
    end = len(text) if end is None else end
    return {"path": _relative(path), "sha256": _sha(path), "json_pointer": pointer,
        "event_seq": event["seq"] if event else None,
        "event_id": event["event_id"] if event else None,
        "event_hash": event["event_hash"] if event else None,
        "start": start, "end": end, "quote": text[start:end], "transform": transform}


def _decode_envelope(container):
    prefix = ""
    body = container
    name = "json_parse"
    if container.startswith("[") and " returned]\n" in container:
        prefix, body = container.split("\n", 1)
        prefix += "\n"
        name = "tool_return_prefix_then_json_parse"
    try:
        decoded = json.loads(body)
        content = decoded["evidence"]["content"]
        if not isinstance(content, str):
            return None
    except (ValueError, KeyError, TypeError):
        return None
    return content, {"name": name, "prefix": prefix, "json_pointer": "/evidence/content",
        "container_sha256": hashlib.sha256(container.encode("utf-8")).hexdigest(),
        "coordinates": "decoded_unicode_code_points"}


def _exposures(trace_path, input_event, messages, content):
    found = []
    for message in messages:
        decoded = _decode_envelope(message["content"])
        if decoded is not None and decoded[0] == content:
            text, transform = decoded
            offset, mode = 0, "decoded_envelope_presence"
            lineage = "recorded_wrap_up_decoded_envelope_presence"
        else:
            text, transform = message["content"], None
            offset = text.find(content)
            if offset < 0:
                continue
            mode, lineage = "exact_input_content", "recorded_wrap_up_content_presence"
        found.append({"anchor": _anchor(trace_path, message["pointer"], text,
            offset, offset + len(content), input_event, transform),
            "message_pointer": message["pointer"], "message_role": message["role"],
            "mode": mode, "lineage": lineage})
    return found


def _prefix_views(trace_path, events):
    tools, retrievals = [], []
    for event in events:
        if event["kind"] == "tool.start":
            tools.append({"seq": event["seq"], "event_id": event["event_id"],
                "span_id": event["span_id"], "tool": event["payload"]["tool"]["name"],
                "arguments": event["payload"].get("metadata", {}).get("inputs"),
                "actor": _actor(event), "raw_ref": _event_ref(trace_path, event)})
        if event["kind"] == "evidence.retrieved":
            retrievals.append({"seq": event["seq"], "event_id": event["event_id"],
                "evidence_key": event["payload"]["evidence"]["evidence_id"],
                "content_digest": digest(event["payload"]["evidence"]["content"]),
                "raw_ref": _event_ref(trace_path, event)})
    return tools, retrievals


def _metadata(event):
    return event.get("payload", {}).get("metadata", {}).get("metadata", {})


def _actor(event):
    checkpoint = _metadata(event).get("checkpoint_ns")
    return checkpoint.split(":", 1)[0] if isinstance(checkpoint, str) else None


def _event_ref(path, event):
    return {"path": _relative(path), "sha256": _sha(path), "event_seq": event["seq"],
            "event_id": event["event_id"], "event_hash": event["event_hash"]}


def audit_sources():
    """Use parent-owned six-run hashchain/full logical SQLite audit unchanged."""
    from recorded_loop.audit import audit_sources as parent_audit
    return parent_audit()


def build_case(run_id):
    if run_id not in SUPPORTED_RUNS:
        raise SourceIntegrityError("Only the explicitly selected Sol0/Terra0 market cases are supported")
    ledger_path = ROOT / "verification/data/refined-v3/ledger.jsonl"
    if _sha(ledger_path) != LEDGER_SHA:
        raise SourceIntegrityError("Pinned refined ledger hash mismatch; no historic rebuild permitted")
    pin_path = ROOT / "explorations/rules/contract-v0.2/pin.json"
    pin = _load(pin_path)
    if pin["build_id"] != LEDGER_BUILD or pin["canonical_sha256"] != LEDGER_SHA:
        raise SourceIntegrityError("Historical v0.2 ledger pin mismatch")
    audit = audit_sources()
    run_audit = next(row for row in audit["runs"] if row["run_id"] == run_id)
    folder = SESSION / run_id
    trace_path = folder / "trace.jsonl"
    state_path, manifest_path = folder / "final_state.json", folder / "run_manifest.json"
    fixture_path = SESSION / "fixture.json"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    state, manifest, fixture = _load(state_path), _load(manifest_path), _load(fixture_path)
    text = state["market_report"]
    origins = [event for event in events if event["kind"] == "llm.end" and
        any(generation.get("text") == text for batch in event["payload"]["response"].get("generations", [])
            for generation in batch)]
    if len(origins) != 1:
        raise SourceIntegrityError("Saved report must have exactly one recorded originating call")
    output = origins[0]
    input_event = next(event for event in events if event["kind"] == "llm.start" and
                       event["span_id"] == output["span_id"])
    if _actor(input_event) != "Market Analyst":
        raise SourceIntegrityError("Selected report origin is not the recorded Market Analyst")
    messages = []
    for batch_idx, batch in enumerate(input_event["payload"]["messages"]):
        for index, message in enumerate(batch):
            if not isinstance(message.get("content"), str):
                raise SourceIntegrityError("Selected input contains unsupported non-string content")
            messages.append({"pointer": f"/payload/messages/{batch_idx}/{index}/content",
                "role": message.get("type") or message.get("role"), "content": message["content"]})
    system = next(message for message in messages if message["role"] == "system" and INSTRUCTION in message["content"])
    instruction_start = system["content"].index(INSTRUCTION)
    instruction = {"required_tool": REQUIRED_TOOL, "text": INSTRUCTION,
        "anchor": _anchor(trace_path, system["pointer"], system["content"], instruction_start,
            instruction_start + len(INSTRUCTION), input_event)}
    prefix_events = [event for event in events if event["seq"] < output["seq"]]
    tools, retrievals = _prefix_views(trace_path, prefix_events)
    evidence = {}
    for tool, item in fixture["tools"].items():
        content, key = item["content"], item["evidence_id"]
        exposures = _exposures(trace_path, input_event, messages, content)
        evidence[key] = {"key": key, "content": content, "content_digest": digest(content),
            "anchor": _anchor(fixture_path, f"/tools/{tool}/content", content),
            "source_version": None, "snapshot_identity": manifest["context"]["fixture_hash"] + ":" + digest(content),
            "valid_date": fixture["as_of"], "date_precision": "date",
            "declared_observed_at": item.get("observed_at"), "observed_time_precision": "declared_fixture_second_not_market_attestation",
            "access": {"available_in_repository": True,
                "retrieval_event_seqs": [row["seq"] for row in retrievals if row["evidence_key"] == key],
                "input_exposures": exposures}}
    scalar = run_id.startswith("terra")
    quote = "2,540" if scalar else SOL_QUOTE
    start = 346 if scalar else text.index(quote)
    if text[start:start + len(quote)] != quote:
        raise SourceIntegrityError("Selected original claim span changed")
    mapping = {"status": "human_accepted_context_mapping" if scalar else "authored_relational_mapping",
        "entity": "ETH-USD", "valid_date": "2026-10-28", "date_precision": "date", "unit": "USD",
        "evidence_key": "E_PRICE", "field": "Close", "value": "2540" if scalar else None,
        "operator": "equals" if scalar else "lt_open_and_previous_close",
        "scope": "synthetic_fixture_consistency_only",
        "assumptions": ["Report context attaches instrument/date/USD/price role; no private reliance or portfolio sufficiency inferred."]}
    mapping_path = ROOT / "explorations/rules/contract-v0.2/mappings.json"
    packet = {"schema_version": SCHEMA_VERSION, "layer": "original_recorded_execution", "run_id": run_id,
        "source": {"session_id": SESSION_ID, "model": manifest["context"]["model"],
            "fixture_id": fixture["fixture_id"], "fixture_digest": manifest["context"]["fixture_hash"],
            "fixture_origin": fixture["kind"], "upstream_commit": manifest["context"]["upstream_commit"],
            "trustkernel_feedback": manifest["config"]["trustkernel_feedback"]},
        "source_files": [_file(path) for path in [trace_path, folder / "trace.sqlite", state_path,
            manifest_path, fixture_path, ledger_path, pin_path, mapping_path]],
        "ledger_pin": {"build_id": LEDGER_BUILD, "canonical_sha256": LEDGER_SHA,
            "versions": pin["release_versions"]},
        "report": {"field": "market_report", "text": text, "anchor": _anchor(state_path, "/market_report", text)},
        "claim": {"kind": "scalar_close" if scalar else "relational_close", "quote": quote,
            "anchor": _anchor(state_path, "/market_report", text, start, start + len(quote)), "mapping": mapping},
        "instruction": instruction,
        "call_context": {"actor": "Market Analyst", "input_event": input_event, "output_event": output,
            "span_id": output["span_id"], "messages": messages},
        "prefix": {"seq_start": 1, "seq_end_inclusive": output["seq"] - 1,
            "events": prefix_events, "tool_invocations": tools, "retrievals": retrievals, "audit": run_audit},
        "evidence": evidence,
        "coverage": {"trace_integrity": "verified_hashchain_and_full_sqlite_parity",
            "tool_capture": "complete_recorded_prefix_before_selected_market_report",
            "dependency_completeness": "UNKNOWN", "original_feedback": "disabled_in_manifest",
            "original_agent_response_to_new_review": "UNOBSERVED", "source_versions": "UNKNOWN",
            "current_market_freshness": "NOT_ESTABLISHED"},
        "limits": ["Actual model execution over frozen synthetic evidence; not real ETH history.",
            "Only two selected report claims; all six trace audits do not establish semantic coverage.",
            "Exact wrap-up content presence is separate from direct tool-message lineage or private reliance.",
            "No evolving source versions, current-price TTL, historical feedback/remediation or Hold suitability is inferred."]}
    packet["packet_id"] = "recorded-case:" + digest(packet)
    validate_case_sources(packet)
    return packet


def _resolve(value, pointer):
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _anchors(value):
    if isinstance(value, dict):
        if {"path", "sha256", "json_pointer", "start", "end", "quote"} <= value.keys():
            yield value
        for child in value.values():
            yield from _anchors(child)
    elif isinstance(value, list):
        for child in value:
            yield from _anchors(child)


def validate_case_sources(packet):
    """Validate source fidelity, not numerical truth or historical compliance.

    Returns a PASS witness dict or raises SourceIntegrityError. No writes/imports
    of legacy builders. Semantic mapping values remain verifier inputs.
    """
    try:
        if packet["schema_version"] != SCHEMA_VERSION or packet["layer"] != "original_recorded_execution":
            raise SourceIntegrityError("Wrong packet schema/layer")
        if packet["run_id"] not in SUPPORTED_RUNS:
            raise SourceIntegrityError("Unsupported recorded run")
        folder = SESSION / packet["run_id"]
        required_paths = [folder / "trace.jsonl", folder / "trace.sqlite", folder / "final_state.json",
            folder / "run_manifest.json", SESSION / "fixture.json", ROOT / "verification/data/refined-v3/ledger.jsonl",
            ROOT / "explorations/rules/contract-v0.2/pin.json", ROOT / "explorations/rules/contract-v0.2/mappings.json"]
        if sorted(source["path"] for source in packet["source_files"]) != sorted(_relative(path) for path in required_paths):
            raise SourceIntegrityError("Required source manifest incomplete or duplicated")
        for source in packet["source_files"]:
            path = _path(source["path"])
            if _sha(path) != source["sha256"] or path.stat().st_size != source["bytes"]:
                raise SourceIntegrityError("Source file hash/size mismatch:" + source["path"])
            if source["path"].startswith("runs/" + SESSION_ID + "/"):
                pinned = _recorded_artifact_pins().get(source["path"])
                if pinned is None or source["sha256"] != pinned["sha256"] or source["bytes"] != pinned["bytes"]:
                    raise SourceIntegrityError("Recorded artifact differs from pinned canonical artifact row")
        trace_path = SESSION / packet["run_id"] / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        by_seq = {event["seq"]: event for event in events}
        for anchor in _anchors(packet):
            path = _path(anchor["path"])
            if _sha(path) != anchor["sha256"]:
                raise SourceIntegrityError("Anchor source hash mismatch")
            if anchor["event_seq"] is not None:
                if path != trace_path.resolve():
                    raise SourceIntegrityError("Cross-run event anchor")
                source = by_seq[anchor["event_seq"]]
                if source["event_id"] != anchor["event_id"] or source["event_hash"] != anchor["event_hash"]:
                    raise SourceIntegrityError("Anchor event identity mismatch")
            else:
                source = _load(path)
            text = _resolve(source, anchor["json_pointer"])
            transform = anchor.get("transform")
            if transform is not None:
                decoded = _decode_envelope(text)
                if decoded is None or decoded[1] != transform:
                    raise SourceIntegrityError("Decoded coordinate transform/container hash mismatch")
                text = decoded[0]
            if type(anchor["start"]) is not int or type(anchor["end"]) is not int or not 0 <= anchor["start"] <= anchor["end"] <= len(text):
                raise SourceIntegrityError("Invalid Unicode span")
            if text[anchor["start"]:anchor["end"]] != anchor["quote"]:
                raise SourceIntegrityError("Exact source span mismatch")
        context = packet["call_context"]
        original_input, original_output = context["input_event"], context["output_event"]
        if original_input != by_seq[original_input["seq"]] or original_output != by_seq[original_output["seq"]]:
            raise SourceIntegrityError("Recorded call identity/time/payload mismatch")
        if context["actor"] != "Market Analyst" or _actor(original_input) != context["actor"]:
            raise SourceIntegrityError("Recorded role mismatch")
        if original_input["kind"] != "llm.start" or original_output["kind"] != "llm.end" or original_input["span_id"] != original_output["span_id"] or context["span_id"] != original_output["span_id"]:
            raise SourceIntegrityError("Recorded call boundary mismatch")
        if original_input["seq"] >= original_output["seq"] or datetime.fromisoformat(original_input["timestamp"]) >= datetime.fromisoformat(original_output["timestamp"]):
            raise SourceIntegrityError("Recorded call temporal ordering mismatch")
        report = packet["report"]["text"]
        state_path = folder / "final_state.json"
        expected_report = _load(state_path)["market_report"]
        if packet["report"]["field"] != "market_report" or report != expected_report or packet["report"]["anchor"] != _anchor(state_path, "/market_report", expected_report):
            raise SourceIntegrityError("Selected saved market report changed")
        if original_output["payload"]["response"]["generations"][0][0]["text"] != report:
            raise SourceIntegrityError("Report does not equal actual originating generation")
        prefix = packet["prefix"]
        if prefix["seq_start"] != 1 or prefix["seq_end_inclusive"] != original_output["seq"] - 1 or prefix["events"] != events[:original_output["seq"] - 1]:
            raise SourceIntegrityError("Recorded prefix incomplete or altered")
        expected_tools, expected_retrievals = _prefix_views(trace_path, prefix["events"])
        if prefix["tool_invocations"] != expected_tools or prefix["retrievals"] != expected_retrievals:
            raise SourceIntegrityError("Normalized tool/retrieval prefix differs from original")
        expected_messages = [{"pointer": f"/payload/messages/{bi}/{mi}/content",
            "role": message.get("type") or message.get("role"), "content": message["content"]}
            for bi, batch in enumerate(original_input["payload"]["messages"])
            for mi, message in enumerate(batch)]
        if context["messages"] != expected_messages:
            raise SourceIntegrityError("Original input messages omitted or changed")
        for message in context["messages"]:
            if _resolve(original_input, message["pointer"]) != message["content"]:
                raise SourceIntegrityError("Input message content/pointer mismatch")
            parent_pointer = message["pointer"].rsplit("/", 1)[0]
            raw_message = _resolve(original_input, parent_pointer)
            if message["role"] != (raw_message.get("type") or raw_message.get("role")):
                raise SourceIntegrityError("Input message role mismatch")
        fixture = _load(SESSION / "fixture.json")
        manifest = _load(folder / "run_manifest.json")
        if packet["ledger_pin"]["build_id"] != LEDGER_BUILD or packet["ledger_pin"]["canonical_sha256"] != LEDGER_SHA:
            raise SourceIntegrityError("Required ledger pin changed")
        if _sha(ROOT / "verification/data/refined-v3/ledger.jsonl") != LEDGER_SHA:
            raise SourceIntegrityError("Pinned ledger source changed")
        expected_source = {"session_id": SESSION_ID, "model": manifest["context"]["model"],
            "fixture_id": fixture["fixture_id"], "fixture_digest": manifest["context"]["fixture_hash"],
            "fixture_origin": fixture["kind"], "upstream_commit": manifest["context"]["upstream_commit"],
            "trustkernel_feedback": manifest["config"]["trustkernel_feedback"]}
        if packet["source"] != expected_source:
            raise SourceIntegrityError("Recorded source/model/feedback metadata mismatch")
        expected_keys = {item["evidence_id"] for item in fixture["tools"].values()}
        if set(packet["evidence"]) != expected_keys:
            raise SourceIntegrityError("Repository evidence inventory altered")
        for tool, item in fixture["tools"].items():
            key, content = item["evidence_id"], item["content"]
            evidence = packet["evidence"][key]
            expected_anchor = _anchor(SESSION / "fixture.json", f"/tools/{tool}/content", content)
            expected_access = {"available_in_repository": True,
                "retrieval_event_seqs": [r["seq"] for r in expected_retrievals if r["evidence_key"] == key],
                "input_exposures": _exposures(trace_path, original_input, expected_messages, content)}
            if evidence["key"] != key or evidence["content"] != content or evidence["content_digest"] != digest(content) or evidence["anchor"] != expected_anchor or evidence["access"] != expected_access:
                raise SourceIntegrityError("Evidence content/access/provenance differs from recorded source")
            if evidence["source_version"] is not None or evidence["valid_date"] != fixture["as_of"] or evidence["declared_observed_at"] != item.get("observed_at"):
                raise SourceIntegrityError("Unknown source version or source time was fabricated")
            if evidence["snapshot_identity"] != manifest["context"]["fixture_hash"] + ":" + digest(content) or evidence["date_precision"] != "date" or evidence["observed_time_precision"] != "declared_fixture_second_not_market_attestation":
                raise SourceIntegrityError("Source identity or temporal precision changed")
        if packet["claim"]["quote"] != packet["claim"]["anchor"]["quote"]:
            raise SourceIntegrityError("Claim quote and exact anchor disagree")
        scalar = packet["run_id"].startswith("terra")
        expected_quote = "2,540" if scalar else SOL_QUOTE
        expected_start = 346 if scalar else expected_report.index(expected_quote)
        if packet["claim"]["kind"] != ("scalar_close" if scalar else "relational_close") or packet["claim"]["anchor"] != _anchor(state_path, "/market_report", expected_report, expected_start, expected_start + len(expected_quote)):
            raise SourceIntegrityError("Selected scalar/relational report anchor changed")
        if packet["instruction"]["required_tool"] != REQUIRED_TOOL or packet["instruction"]["text"] != INSTRUCTION or packet["instruction"]["anchor"]["quote"] != INSTRUCTION:
            raise SourceIntegrityError("Required original instruction changed")
        system = next(message for message in expected_messages if message["role"] == "system" and INSTRUCTION in message["content"])
        offset = system["content"].index(INSTRUCTION)
        if packet["instruction"]["anchor"] != _anchor(trace_path, system["pointer"], system["content"], offset, offset + len(INSTRUCTION), original_input):
            raise SourceIntegrityError("Instruction not anchored in original system input")
        expected_coverage = {"trace_integrity": "verified_hashchain_and_full_sqlite_parity",
            "tool_capture": "complete_recorded_prefix_before_selected_market_report",
            "dependency_completeness": "UNKNOWN", "original_feedback": "disabled_in_manifest",
            "original_agent_response_to_new_review": "UNOBSERVED", "source_versions": "UNKNOWN",
            "current_market_freshness": "NOT_ESTABLISHED"}
        if packet["coverage"] != expected_coverage:
            raise SourceIntegrityError("Source capture limits were changed or fabricated")
        return {"status": "PASS", "source_files": len(packet["source_files"]),
                "anchors": len(list(_anchors(packet))), "scope": "source fidelity only"}
    except SourceIntegrityError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise SourceIntegrityError("Malformed or unresolved recorded source binding") from exc


def retrieve_for_review(packet, evidence_key, *, reviewed_at=None):
    """New read-only reviewer receipt. Original actors/history are never changed."""
    validate_case_sources(packet)
    if evidence_key not in packet["evidence"]:
        raise SourceIntegrityError("Unknown selected repository evidence key")
    if reviewed_at is None:
        reviewed_at = datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None or reviewed_at.endswith("-00:00"):
            raise ValueError("Unknown review offset")
    except (ValueError, TypeError, AttributeError) as exc:
        raise SourceIntegrityError("Reviewer retrieval needs explicit current UTC offset") from exc
    if parsed <= datetime.fromisoformat(packet["call_context"]["output_event"]["timestamp"]):
        raise SourceIntegrityError("Reviewer receipt cannot be backdated into original execution")
    evidence = packet["evidence"][evidence_key]
    receipt = {"receipt_id": "review-retrieval:" + str(uuid.uuid4()),
        "layer": "new_reviewer_retrieval", "retrieved_at": reviewed_at,
        "actor": "local_reviewer_replay", "source_packet_id": packet["packet_id"],
        "source_run_id": packet["run_id"], "evidence_key": evidence_key,
        "content": evidence["content"], "content_digest": evidence["content_digest"],
        "source_anchor": copy.deepcopy(evidence["anchor"]), "source_version": None,
        "snapshot_identity": evidence["snapshot_identity"],
        "source_origin": packet["source"]["fixture_origin"],
        "original_history_modified": False, "historical_tool_invocation_created": False,
        "source_observed_at": evidence["declared_observed_at"],
        "limits": "Original frozen repository snapshot; no current market refresh, new version or agent response."}
    receipt["receipt_digest"] = digest(receipt)
    return receipt
