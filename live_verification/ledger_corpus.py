"""Generic captured-live corpus ingestion. Reads explicit safe files only."""
from __future__ import annotations

import ast
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from .ledger import canonical, sha, resolve, walk_strings, occurrences

REPORT_ACTORS = {"market_report": "Market Analyst", "news_report": "News Analyst",
                 "investment_plan": "Research Manager", "trader_investment_plan": "Trader",
                 "final_trade_decision": "Portfolio Manager"}
STRUCTURED_FIELDS = {"ResearchPlan": "investment_plan", "TraderProposal": "trader_investment_plan",
                     "PortfolioDecision": "final_trade_decision"}


def render_structured(name, args):
    """Narrow native-shaped format replay; exact saved-byte equality is mandatory.

    Unsupported coercions/values abstain. We do not guess Pydantic coercions.
    """
    if not isinstance(args, dict):
        raise ValueError("Structured renderer requires recorded args object")
    if name == "ResearchPlan":
        if any(type(args.get(k)) is not str for k in ("recommendation", "rationale", "strategic_actions")):
            raise ValueError("Unsupported ResearchPlan args")
        return "\n".join(["**Recommendation**: " + args["recommendation"], "", "**Rationale**: " + args["rationale"],
                          "", "**Strategic Actions**: " + args["strategic_actions"]])
    if name == "TraderProposal":
        if type(args.get("action")) is not str or type(args.get("reasoning")) is not str:
            raise ValueError("Unsupported TraderProposal args")
        parts = ["**Action**: " + args["action"], "", "**Reasoning**: " + args["reasoning"]]
        for label, key in (("Entry Price", "entry_price"), ("Stop Loss", "stop_loss"), ("Position Sizing", "position_sizing")):
            value = args.get(key)
            if type(value) not in (str, int, float, type(None)):
                raise ValueError("Unsupported trader optional value")
            parts.extend(["", "**" + label + "**: " + str(value if value is not None and value != "" else "not provided")])
        return "\n".join(parts + ["", "FINAL TRANSACTION PROPOSAL: **" + args["action"].upper() + "**"])
    if name == "PortfolioDecision":
        if any(type(args.get(k)) is not str for k in ("rating", "executive_summary", "investment_thesis")):
            raise ValueError("Unsupported PortfolioDecision args")
        target = args.get("price_target")
        if type(target) not in (int, float, type(None)) or type(args.get("time_horizon")) not in (str, type(None)):
            raise ValueError("Unsupported price/time coercion; origin unresolved")
        return "\n".join(["**Rating**: " + args["rating"], "", "**Executive Summary**: " + args["executive_summary"],
                          "", "**Investment Thesis**: " + args["investment_thesis"], "",
                          "**Price Target**: " + str(target if target is not None else "not provided"), "",
                          "**Time Horizon**: " + (args.get("time_horizon") or "not provided")])
    raise ValueError("Unsupported structured rendering")


def inspect_trace(directory):
    directory = Path(directory)
    events = [json.loads(line) for line in (directory / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    previous = None
    seen = set()
    run_id = None
    for seq, event in enumerate(events, 1):
        body = {k: v for k, v in event.items() if k != "event_hash"}
        # Matches the producer's default json separators, not ledger canonical JSON.
        actual = sha(json.dumps(body, sort_keys=True, ensure_ascii=False))
        run_id = run_id or event["run_id"]
        if event["seq"] != seq or event["previous_hash"] != previous or actual != event["event_hash"]:
            raise ValueError("Original trace chain/sequence mismatch")
        if event["event_id"] in seen or event["run_id"] != run_id:
            raise ValueError("Original trace identity mismatch")
        seen.add(event["event_id"])
        previous = actual
    if not events:
        raise ValueError("Empty source trace")
    path = (directory / "trace.sqlite").resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Original trace SQLite corruption")
        indexed = db.execute("SELECT seq,event_id,run_id,timestamp,kind,span_id,parent_id,payload_json,event_hash FROM events ORDER BY seq").fetchall()
        expected = [(e["seq"], e["event_id"], e["run_id"], e["timestamp"], e["kind"], e["span_id"], e["parent_id"],
                     json.dumps(e["payload"], ensure_ascii=False), e["event_hash"]) for e in events]
        if indexed != expected:
            raise ValueError("Original JSONL/SQLite logical mismatch")
    return events


def _actor(event):
    metadata = event["payload"].get("metadata", {}).get("metadata", {})
    namespace = metadata.get("langgraph_checkpoint_ns", metadata.get("checkpoint_ns", ""))
    node = metadata.get("langgraph_node")
    return namespace.split(":", 1)[0] if node in ("agent", "wrap_up", "tools") and namespace else node or "UNKNOWN"


def _message_strings(messages, prefix):
    """Visible message content only. Full controls/args remain in raw event."""
    for batch_i, batch in enumerate(messages):
        if not isinstance(batch, list):
            continue
        for msg_i, message in enumerate(batch):
            if not isinstance(message, dict):
                continue
            pointer = f"{prefix}/{batch_i}/{msg_i}/content"
            content = message.get("content")
            if isinstance(content, str):
                yield pointer, content, message
            elif isinstance(content, list):
                for i, block in enumerate(content):
                    if isinstance(block, dict) and block.get("type") in ("text", "output_text") and isinstance(block.get("text"), str):
                        yield pointer + f"/{i}/text", block["text"], message


def _visible_output(message, pointer):
    content = message.get("content")
    if isinstance(content, str) and content:
        yield pointer + "/content", content
    elif isinstance(content, list):
        for i, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") in ("text", "output_text") and isinstance(block.get("text"), str) and block["text"]:
                yield pointer + f"/content/{i}/text", block["text"]


def _artifact(ledger, root, path, role, run_id=None, include_data=True):
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or "source-cache" in resolved.relative_to(root).parts:
        raise ValueError("Unsafe corpus artifact scope")
    raw = path.read_bytes()
    return ledger.add("artifacts", [path.relative_to(root).as_posix(), sha(raw)], run_id,
                      path=path.relative_to(root).as_posix(), sha256=sha(raw), role=role,
                      data=json.loads(raw.decode("utf-8")) if include_data else None)


def ingest(ledger, root):
    root = Path(root).resolve()
    if (root / "experiment.json").is_file():
        _artifact(ledger, root, root / "experiment.json", "session_manifest")
    traces = sorted(root.glob("*/trace.jsonl"))
    if not traces:
        raise ValueError("No captured live traces found")
    for trace_path in traces:
        ingest_run(ledger, root, trace_path.parent)


def ingest_run(ledger, root, directory):
    raw_events = inspect_trace(directory)
    run = raw_events[0]["run_id"]
    manifest = _artifact(ledger, root, directory / "run_manifest.json", "run_manifest", run)
    final = _artifact(ledger, root, directory / "final_state.json", "final_state", run)
    trace = _artifact(ledger, root, directory / "trace.jsonl", "raw_trace", run, False)
    _artifact(ledger, root, directory / "trace.sqlite", "raw_index", run, False)
    if manifest["data"].get("run_id") != run:
        raise ValueError("Run manifest identity mismatch")
    context = raw_events[0].get("context", {})
    if context.get("source_mode") != "live_native_market_sources":
        raise ValueError("Input is not a recorded live native-source run")
    ledger.add("runs", run, run, refs=[manifest["id"], trace["id"]], directory=directory.relative_to(root).as_posix(),
               context=context, manifest_artifact_id=manifest["id"], trace_artifact_id=trace["id"], event_count=len(raw_events))
    events = []
    for event in raw_events:
        events.append(ledger.add("events", [run, event["event_id"]], run, refs=[trace["id"]], seq=event["seq"],
                                 kind=event["kind"], timestamp=event["timestamp"], span_id=event["span_id"], parent_id=event["parent_id"],
                                 artifact_id=trace["id"], raw=event))
    calls, text_rows, narratives, source_rows = {}, [], [], []
    for event in events:
        if event["kind"] != "llm.start":
            continue
        end = [e for e in events if e["span_id"] == event["span_id"] and e["kind"] in ("llm.end", "llm.error")]
        if len(end) > 1:
            raise ValueError("Ambiguous model call endpoint")
        end = end[0] if end else None
        call = ledger.add("calls", [run, event["span_id"]], run, refs=[event["id"], end["id"] if end else None],
                          span_id=event["span_id"], actor=_actor(event["raw"]), start_event_id=event["id"],
                          end_event_id=end["id"] if end else None, input_seq=event["seq"], output_seq=end["seq"] if end else None,
                          status="completed" if end and end["kind"] == "llm.end" else "error" if end else "unfinished")
        calls[event["span_id"]] = call
        for pointer, text, message in _message_strings(event["raw"]["payload"].get("messages", []), "/payload/messages"):
            text_rows.append(ledger.add("texts", [event["id"], pointer], run, refs=[event["id"], trace["id"], call["id"]],
                                        text=text, sha256=sha(text), artifact_id=trace["id"], event_id=event["id"], pointer=pointer,
                                        transform=None, call_id=call["id"], actor=call["actor"], role="recorded_input",
                                        input_seq=event["seq"], output_seq=None,
                                        message_type=message.get("type"), message_name=message.get("name"), tool_call_id=message.get("tool_call_id")))
    state = final["data"]
    for event in events:
        if event["kind"] != "llm.end":
            continue
        call = calls.get(event["span_id"])
        if call is None:
            raise ValueError("Model end without start")
        for bi, batch in enumerate(event["raw"]["payload"]["response"].get("generations", [])):
            for gi, generation in enumerate(batch):
                pointer = f"/payload/response/generations/{bi}/{gi}/message"
                message = generation.get("message", {})
                output_texts = []
                for text_pointer, text in _visible_output(message, pointer):
                    row = ledger.add("texts", [event["id"], text_pointer], run, refs=[event["id"], call["id"], trace["id"]],
                                     text=text, sha256=sha(text), artifact_id=trace["id"], event_id=event["id"], pointer=text_pointer,
                                     transform=None, call_id=call["id"], actor=call["actor"], role="generated_narrative",
                                     input_seq=call["input_seq"], output_seq=event["seq"])
                    narratives.append(row)
                    output_texts.append(row["id"])
                for ti, tool in enumerate(message.get("tool_calls", [])):
                    field = STRUCTURED_FIELDS.get(tool.get("name"))
                    if not field or REPORT_ACTORS[field] != call["actor"] or not isinstance(state.get(field), str):
                        continue
                    try:
                        rendered = render_structured(tool["name"], tool.get("args"))
                    except (ValueError, KeyError, TypeError):
                        continue
                    if rendered != state[field]:
                        continue
                    next_input = min((c["input_seq"] for c in calls.values() if c["input_seq"] > event["seq"]), default=float("inf"))
                    observed = []
                    for step in events:
                        if step["kind"] == "step.end" and event["seq"] < step["seq"] < next_input:
                            value = step["raw"]["payload"].get("outputs")
                            if isinstance(value, dict) and value.get(field) == rendered:
                                observed.append(step)
                    if not observed:
                        continue
                    rendered_step = observed[0]
                    args_pointer = pointer + f"/tool_calls/{ti}/args"
                    transform = {"name": tool["name"], "version": "native-shaped-render-1", "method": "exact_replay_not_semantic_equivalence",
                                 "observed_event_id": rendered_step["id"], "observed_pointer": "/payload/outputs/" + field}
                    row = ledger.add("texts", [event["id"], args_pointer, transform], run,
                                     refs=[event["id"], call["id"], trace["id"], rendered_step["id"]], text=rendered, sha256=sha(rendered), artifact_id=trace["id"],
                                     event_id=event["id"], pointer=args_pointer, transform=transform, call_id=call["id"], actor=call["actor"],
                                     role="generated_narrative", input_seq=call["input_seq"], output_seq=event["seq"])
                    narratives.append(row)
                    output_texts.append(row["id"])
                md = message.get("response_metadata", {})
                tools = message.get("tool_calls", [])
                unknown_structure = any(t.get("name") in STRUCTURED_FIELDS for t in tools) and not output_texts
                disposition = "visible_narrative" if output_texts else "structured_origin_unresolved" if unknown_structure else "tool_invocation_only" if tools else "empty_visible_output"
                output = ledger.add("outputs", [event["id"], bi, gi], run, refs=[event["id"], call["id"], *output_texts],
                                    event_id=event["id"], call_id=call["id"], pointer=pointer, disposition=disposition, text_ids=output_texts,
                                    provider_status=md.get("status"), incomplete_details=md.get("incomplete_details"),
                                    finish_reason=generation.get("generation_info"), usage=message.get("usage_metadata"),
                                    tool_names=[t.get("name") for t in tools])
                if unknown_structure:
                    ledger.add("unresolved", [output["id"], "origin"], run, refs=[output["id"]], subject_id=output["id"],
                               reasons=["structured_args_not_proven_to_render_saved_report"], status="UNRESOLVED")
    reports = []
    for field, actor in REPORT_ACTORS.items():
        if not isinstance(state.get(field), str) or not state[field]:
            ledger.add("unresolved", [run, field, "missing_report"], run, refs=[final["id"]], subject_id=final["id"],
                       reasons=["saved_report_missing:" + field], status="UNRESOLVED")
            continue
        matches = [t for t in narratives if t["text"] == state[field] and t["actor"] == actor]
        origin = matches[0] if len(matches) == 1 else None
        if origin:
            text = origin
            method = "structured_render_replay_exact" if origin["transform"] else "exact_visible_output"
        else:
            text = ledger.add("texts", [final["id"], field], run, refs=[final["id"]], text=state[field], sha256=sha(state[field]),
                              artifact_id=final["id"], event_id=None, pointer="/" + field, transform=None, call_id=None,
                              actor=actor, role="saved_report_unresolved", input_seq=None, output_seq=None)
            method = "unresolved"
            ledger.add("unresolved", [text["id"], "origin"], run, refs=[text["id"]], subject_id=text["id"],
                       reasons=["no_unique_exact_generation_or_render_replay"], status="UNRESOLVED")
        report = ledger.add("reports", [run, field], run, refs=[text["id"], final["id"], text["call_id"]], field=field, text_id=text["id"],
                            call_id=text["call_id"], output_event_id=text["event_id"], origin_method=method,
                            origin_pointer=text["pointer"], origin_args=resolve(next(e["raw"] for e in events if e["id"] == text["event_id"]), text["pointer"]) if text["transform"] else None,
                            origin_status="PROVEN_TRANSFORM" if origin else "UNRESOLVED",
                            saved_artifact_id=final["id"], saved_pointer="/" + field)
        reports.append(report)
        if field == "final_trade_decision":
            decision = ledger.add("decisions", report["id"], run, refs=[report["id"], text["id"], text["call_id"], text["event_id"]],
                                  report_id=report["id"], text_id=text["id"], call_id=text["call_id"], event_id=text["event_id"],
                                  as_of=context.get("context_at"), scope="recorded_paper_decision_no_global_clearance")
            ledger.add("unresolved", [decision["id"], "support"], run, refs=[decision["id"]], subject_id=decision["id"],
                       reasons=["full_material_dependencies_unknown", "freshness_TTL_authority_unknown", "suitability_not_assessed"], status="UNRESOLVED")
    for event in events:
        if event["kind"] != "evidence.retrieved":
            continue
        p = event["raw"]["payload"]
        if not isinstance(p.get("content"), str) or p.get("content_hash") != sha(p["content"]):
            raise ValueError("Original source content hash mismatch")
        candidates = []
        for end in events:
            if end["kind"] != "tool.end" or end["seq"] <= event["seq"]:
                continue
            out = end["raw"]["payload"].get("output", {})
            if not isinstance(out, dict) or out.get("content") != p["content"] or out.get("name") != p["tool"]:
                continue
            start = next((s for s in events if s["kind"] == "tool.start" and s["span_id"] == end["span_id"]), None)
            if start is None or start["seq"] >= event["seq"]:
                continue
            try:
                requested = ast.literal_eval(start["raw"]["payload"].get("input", "{}"))
            except (ValueError, SyntaxError):
                continue
            if isinstance(requested, dict) and all(p.get("request", {}).get(k) == v for k, v in requested.items()):
                candidates.append((start, end, out.get("tool_call_id")))
        binding = min(candidates, key=lambda pair: pair[1]["seq"]) if candidates else None
        row = ledger.add("sources", [run, p["evidence_id"], event["id"]], run,
                         refs=[event["id"], trace["id"], binding[0]["id"] if binding else None, binding[1]["id"] if binding else None],
                         content=p["content"], sha256=sha(p["content"]), source_call_id=p["evidence_id"], tool=p["tool"], args=p.get("request", {}),
                         provider=p.get("provider"), source_status=p.get("source_status", "UNKNOWN"),
                         started_at=p.get("requested_at"), retrieved_at=p.get("retrieved_at"), event_id=event["id"], seq=event["seq"],
                         artifact_id=trace["id"], pointer="/payload/content", source_version=sha(p["content"]), version_status="content_identity_not_authority",
                         source_urls=p.get("source_urls", []), source_time_fields=p.get("source_time_fields", []), cache_status=p.get("cache_status"),
                         tool_start_event_id=binding[0]["id"] if binding else None, tool_end_event_id=binding[1]["id"] if binding else None,
                         tool_call_id=binding[2] if binding else None, lineage_status="observed_tool_interval_content_and_args" if binding else "UNRESOLVED",
                         limitations=p.get("limitations", []), http_ids=p.get("http_ids", []),
                         temporal_flags=["source_clocks_preserved", "daily_candle_finality_and_TTL_unresolved"])
        source_rows.append(row)
        if not binding:
            ledger.add("unresolved", [row["id"], "lineage"], run, refs=[row["id"]], subject_id=row["id"],
                       reasons=["source_to_tool_callback_lineage_unresolved"], status="UNRESOLVED")
    for input_text in text_rows:
        call = next(c for c in calls.values() if c["id"] == input_text["call_id"])
        for source in source_rows + narratives:
            source_seq = source.get("seq", source.get("output_seq"))
            if source_seq is None or source_seq >= call["input_seq"]:
                continue
            body = source.get("content", source.get("text"))
            for start, end in occurrences(input_text["text"], body):
                is_evidence = source["table"] == "sources"
                lineage = is_evidence and source["tool_call_id"] and input_text.get("message_type") == "tool" and input_text.get("tool_call_id") == source["tool_call_id"]
                mode = "tool_role_call_lineage" if lineage else "exact_source_text_presence" if is_evidence else "exact_prior_narrative_copy"
                exposure = ledger.add("exposures", [source["id"], input_text["id"], start], run,
                                      refs=[source["id"], input_text["id"], call["id"]], call_id=call["id"], text_id=input_text["id"],
                                      source_id=source["id"] if is_evidence else None, originating_text_id=None if is_evidence else source["id"],
                                      start=start, end=end, quote=body, mode=mode, pre_assertion=True,
                                      retrieval_seq=source_seq, input_seq=call["input_seq"], output_seq=call["output_seq"],
                                      support_status="presence_not_reliance_or_entailment")
                if not is_evidence:
                    ledger.add("relations", [exposure["id"], "copy"], run, refs=[source["id"], call["id"], exposure["id"]],
                               relation="observed_prior_narrative_copy", status="observed_copy", from_id=source["id"], to_id=call["id"],
                               witness={"exposure_id": exposure["id"], "not_a_semantic_dependency": True})
