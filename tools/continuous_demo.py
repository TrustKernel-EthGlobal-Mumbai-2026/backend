"""Durable authored stdlib host demo. No model/provider, budget or private input."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuous_verification import canonical_json, digest
from continuous_verification.service import Principal, ServiceBackend
from continuous_verification.tradingagents import StoredFeedbackHost, Limits


def new_output(output, workspace_root):
    root = Path(workspace_root).resolve()
    candidate = Path(output)
    if not candidate.is_absolute():
        candidate = root / candidate
    # Refuse links/junctions before resolving or creating the destination.
    for parent in [candidate, *candidate.parents]:
        if parent.is_symlink() or (parent.exists() and bool(getattr(parent.lstat(), "st_file_attributes", 0) & 0x400)):
            raise ValueError("Linked output paths are not supported")
        if parent == root:
            break
    allowed = root / ".local-runs"
    target = candidate.resolve()
    if target == allowed or not target.is_relative_to(allowed):
        raise ValueError("Output must be a new child directory under this checkout's .local-runs")
    target.mkdir(parents=True, exist_ok=False)
    return target


def write_new(path, content):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def run(output, *, workspace_root=ROOT):
    target = new_output(output, workspace_root)
    run_id = "authored-continuous-demo"
    principal = Principal("authored-demo-collector", frozenset({"configure", "collect", "verify", "read"}), frozenset({run_id}))
    policy = dict(contract_version="continuous-verification-0.2", policy_id="authored-demo-procedure", version="1",
        required_tool="authored_snapshot", checks=[dict(check_id=name, on_fail="HOLD", on_inconclusive="RECHECK")
        for name in ("required_snapshot_before_market_report", "report_completion")])
    backend = ServiceBackend(target / "feedback.sqlite", principal=principal, service_id="authored-demo-local-service")
    try:
        backend.configure_run(run_id, [dict(stream_id="host", collector_id=principal.actor_id, producer_id="authored-demo-host",
            adapter_version="tradingagents-feedback-0.2", redaction_profile="authored-public")])
        backend.execute("register_run", dict(run_id=run_id, registration_id="authored-demo-registration"))
        backend.install_policy(run_id, policy)
        host = StoredFeedbackHost(backend=backend, run_id=run_id, stream_id="host", producer_id="authored-demo-host",
            redaction_profile="authored-public", redact=lambda text: text, proposal_id="authored-paper-proposal", policy=policy,
            limits=Limits(source_rounds=1, verify_calls=2, remediations=1))

        def coverage(input_event, report):
            # Explicit coverage of this small authored host, never a real session.
            backend.record_coverage(run_id, "host", [dict(name=name, state="CAPTURED", basis_event_ids=[basis])
                for name, basis in (("model_input", input_event["event_id"]), ("tool_lifecycle", input_event["event_id"]),
                    ("phase_boundaries", report["event_id"]), ("report_completion", report["event_id"]))])

        def submit(report, revision):
            return host.submit_report(report_event=report, proposal_content="AUTHORED paper abstention; no order authority",
                proposal_revision=revision, request_id=f"authored-request-{revision}", checkpoint_id="authored-prefix",
                checkpoint_revision=revision, streams=[dict(stream_id="host", requested=len(host.capture.events))])

        input0 = host.assemble_input([dict(type="human", content="AUTHORED initial host input; snapshot not yet called")],
            report_id="authored-market-report", report_revision=0)
        report0 = host.capture.report(content="AUTHORED initial report: required snapshot omitted; proposal held",
            report_id="authored-market-report", revision=0, input_event_id=input0["event_id"], completion="COMPLETE", phase="CLOSED")
        coverage(input0, report0)
        request0 = submit(report0, 0)
        payload0 = host.boundary.verify()
        original = json.loads(payload0)
        host.observe_return(call_id="authored-verify-0", tool_name="verify_proposal", content=payload0, status="SUCCESS")
        finding_message = dict(type="tool", name="verify_proposal", tool_call_id="authored-verify-0", content=payload0)
        next_input = host.assemble_input([finding_message], report_id="authored-market-report", report_revision=1)
        host.boundary.observe_next_input(next_input["event_id"], [("authored-verify-0", payload0)])
        host.acknowledge(original["assessment_id"], "AUTHORED host acknowledgement of omission; not real-agent behavior")
        defect = host.boundary.source_round([lambda: "AUTHORED snapshot fixture: Close=99 Low=100; provider-row defect UNRESOLVED"])[0]
        host.observe_return(call_id="authored-snapshot-1", tool_name="authored_snapshot", content=defect, status="SUCCESS")
        input1 = host.assemble_input([finding_message, dict(type="tool", name="authored_snapshot",
            tool_call_id="authored-snapshot-1", content=defect)], report_id="authored-market-report", report_revision=1)
        report1 = host.capture.report(content="AUTHORED revised report: snapshot received; abstain because provider-row defect remains",
            report_id="authored-market-report", revision=1, input_event_id=input1["event_id"], completion="COMPLETE", phase="CLOSED")
        host.record_revision(original["assessment_id"], report1)
        coverage(input1, report1)
        request1 = submit(report1, 1)
        recheck = json.loads(host.boundary.verify(origin="host"))
        host.boundary.abstain("AUTHORED paper abstention: procedure rechecked; price validity and decision suitability unresolved")

        stored_original = backend.execute("get_assessment", dict(run_id=run_id, assessment_id=original["assessment_id"]))
        old_view = backend.resolve_view(request0)
        new_view = backend.resolve_view(request1)
        state = backend.execute("get_run_state", dict(run_id=run_id))
        audit = backend.audit()
        events, cursor = [], None
        while True:
            page = backend.execute("list_events", dict(run_id=run_id, after_cursor=cursor, limit=100))
            events.extend(page["events"])
            if not page["has_more"]:
                break
            cursor = page["next_cursor"]
        original_outcomes = [f["outcome"] for f in original["findings"]]
        recheck_outcomes = [f["outcome"] for f in recheck["findings"]]
        expected = (original_outcomes == ["FAIL", "PASS"] and recheck_outcomes == ["PASS", "PASS"]
            and stored_original == original and len(old_view["events"]) == 2 and not state["atomic_semantic_ready"])
        summary = dict(status="COMPLETE" if expected else "UNEXPECTED_OUTCOME", run_id=run_id,
            scope="authored stdlib host demonstration; not native/model behavior", model_responses="AUTHORED host text; no model process ran",
            sources="AUTHORED snapshot fixture only; no provider request", completion="AUTHORED host status, not provider metadata",
            model_calls=0, provider_calls=0, trade_execution=False, private_inputs_used=False,
            original=original, recheck=recheck, original_preserved=stored_original == original,
            requests=[request0, request1], checkpoint_event_counts=[len(old_view["events"]), len(new_view["events"])],
            feedback_events=[dict(event_id=e["event_id"], event_type=e["event_type"], payload=e["payload"])
                for e in events if e["event_type"].startswith("feedback_") or e["event_type"] == "correction"],
            allowances=host.boundary.counts, provider_defect=dict(status="UNRESOLVED", content=defect),
            state=state, audit=audit, event_count=len(events), event_digest=digest(events),
            artifacts=dict(database="feedback.sqlite", events="events.jsonl", summary="summary.md"),
            limits=["Scoped recheck verifies required-tool delivery and report completion only.",
                "No price/source authority, dependency sufficiency, actual-model correction or global clearance.",
                "Authored next-input assembly was not sent to a model; acknowledgement is scripted.",
                "SQLite is persistent; graph/process resume and a full semantic ledger are not demonstrated."])
    finally:
        backend.close()
    write_new(target / "events.jsonl", "".join(canonical_json(e) + "\n" for e in events))
    write_new(target / "summary.json", json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    write_new(target / "summary.md", f"""# Authored continuous-verification host demo

Status: {summary['status']}. Standard library only; **not native/model behavior**.
Every source and response is authored. No model/provider call or trading occurred.

- Original omission: {', '.join(original_outcomes)}; disposition {original['disposition']}.
- Finding delivery, authored next-input assembly, acknowledgement and report revision are separate retained events.
- New report/proposal revision and exact checkpoint recheck: {', '.join(recheck_outcomes)}; scope {recheck['scope']}.
- Original assessment preserved: {summary['original_preserved']}; frozen old prefix has {len(old_view['events'])} events.
- Source/verify/remediation used: {host.boundary.counts}.
- Provider defect remains **UNRESOLVED**: Close=99 below Low=100. No replacement price was invented.
- Paper outcome: authored abstention. Procedural PASS does not verify prices or decision suitability.
- Full semantic readiness: {state['atomic_semantic_ready']}. No graph/process restart claim.

Read `summary.json` for exact requests/results, bindings and event references.
Read `events.jsonl` as UTF-8 JSON lines for the retained trace ({len(events)} events).
Open `feedback.sqlite` in a SQLite viewer **read only**. Inspect `cv_events` and
`cv_objects` (kind `assessment`) for exact stored evidence/results; `cv_batches`
retains durable receipts. Do not run historical/private-data launchers to view it.
""")
    return target, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="NEW directory under this checkout's .local-runs")
    args = parser.parse_args()
    try:
        target, summary = run(args.output)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Offline demo stopped ({type(exc).__name__}); no existing output is overwritten.\n")
    print(f"AUTHORED OFFLINE DEMO {summary['status']}: {target}")
    print(f"Read {target / 'summary.md'} and summary.json; trace is events.jsonl (UTF-8 JSON lines).")
    print("Open feedback.sqlite READ ONLY; inspect cv_events, cv_objects kind=assessment, and cv_batches receipts.")
    print("No native/model behavior, source truth, global decision clearance or semantic-ledger readiness is claimed.")
    return 0 if summary["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
