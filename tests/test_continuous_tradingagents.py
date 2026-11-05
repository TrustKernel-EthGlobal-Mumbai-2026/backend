"""Temporary authored inputs; accepted A/B offline, scripted native responses only."""
import ast
from collections import Counter
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from typing import Annotated
import unittest
from unittest.mock import patch

from continuous_verification import CONTRACT_VERSION, ContractError, canonical_json, digest, text_digest, verify, validate_event
from continuous_verification.tradingagents import (
    BoundaryError, FeedbackBoundary, HostEventCapture, Limits, UPSTREAM_COMMIT,
    make_verify_tool, make_trusted_model, observe_native_returns, TRUSTED_INSTRUCTION,
    make_stored_assessor, make_host_ingest,
    StoredFeedbackHost, validate_ingest_receipt,
    LocalServiceWorker,
)
from continuous_verification.service import Principal, ServiceBackend, ServiceError


def authored_packet(revision=0, *, snapshot=True, completion="COMPLETE", boundary="ASSEMBLED"):
    # This checkpoint/service declaration is a clearly authored test double.
    capture = HostEventCapture(run_id="authored-run", stream_id="host", producer_id="authored-host",
        redaction_profile="authored-public", redact=lambda s: s, emit=lambda e: None)
    for r in range(revision + 1):
        result = capture.tool_result(call_id=f"snapshot-{r}", tool_name="authored_snapshot",
            content="Authored provider defect Close=99 Low=100; no invented repair", status="SUCCESS")
        input_event = capture.model_input(messages=[dict(role="tool", content=result["content"])],
            report_id="market-report", report_revision=r,
            included_event_ids=[result["event_id"]] if snapshot else [], boundary=boundary)
        report = capture.report(content=f"Authored report revision {r}; provider defect remains",
            report_id="market-report", revision=r, input_event_id=input_event["event_id"],
            completion=completion, phase="CLOSED")
    count = len(capture.events)
    checkpoint = dict(contract_version=CONTRACT_VERSION, run_id="authored-run",
        checkpoint_id=f"authored-prefix-{revision}", revision=revision,
        established_by=dict(service_id="authored-service-double", basis="SERVICE_ESTABLISHED"), created_at=None,
        streams=[dict(stream_id="host", requested=count, ingested_through=count, projected_through=count,
                      gaps=[], capabilities=[dict(name=name, state="CAPTURED", basis_event_ids=[input_event["event_id"]])
                      for name in ("phase_boundaries", "report_completion", "model_input", "tool_lifecycle")])])
    policy = dict(contract_version=CONTRACT_VERSION, policy_id="authored-offline", version="1",
        required_tool="authored_snapshot", checks=[dict(check_id=check, on_fail="HOLD", on_inconclusive="RECHECK")
        for check in ("required_snapshot_before_market_report", "report_completion")])
    proposal = dict(proposal_id="paper-proposal", revision=revision, content="Authored paper Hold; no trade",
        content_digest=text_digest("Authored paper Hold; no trade"), report_event_id=report["event_id"],
        report_id="market-report", report_revision=revision, dependencies=None, dependency_completeness="UNKNOWN")
    request = dict(contract_version=CONTRACT_VERSION, run_id="authored-run", request_id=f"request-{revision}",
        proposal=proposal, checkpoint=dict(checkpoint_id=checkpoint["checkpoint_id"], revision=revision, digest=digest(checkpoint)),
        policy=dict(policy_id=policy["policy_id"], version=policy["version"], digest=digest(policy),
                    checks=[c["check_id"] for c in policy["checks"]]), checks=[c["check_id"] for c in policy["checks"]])
    return dict(request=request, checkpoint=checkpoint, events=deepcopy(capture.events), policy=policy)


def stored_fixture(path, *, worker=False):
    # Actual B storage with trusted authored grants; no agent supplies these.
    principal = Principal("authored-collector", frozenset({"configure", "collect", "verify", "read", "feedback"}),
                          frozenset({"authored-run"}))
    factory = lambda: ServiceBackend(path, principal=principal, service_id="authored-local-service")
    backend = LocalServiceWorker(factory) if worker else factory()
    try:
        backend.configure_run("authored-run", [dict(stream_id="host", collector_id=principal.actor_id,
            producer_id="authored-host", adapter_version="tradingagents-feedback-0.2", redaction_profile="authored-public")])
        backend.execute("register_run", dict(run_id="authored-run", registration_id="authored-registration"))
        policy = authored_packet()["policy"]
        backend.install_policy("authored-run", policy)
        host = StoredFeedbackHost(backend=backend, run_id="authored-run", stream_id="host", producer_id="authored-host",
            redaction_profile="authored-public", redact=lambda s: s, proposal_id="paper-proposal", policy=policy,
            limits=Limits(source_rounds=1, verify_calls=2, remediations=1))
        return backend, host
    except BaseException:
        backend.close()
        raise


def captured_coverage(backend, input_event, report):
    # Explicit scoped collector observations over this authored instrumented host.
    backend.record_coverage("authored-run", "host", [dict(name=name, state="CAPTURED", basis_event_ids=[basis])
        for name, basis in (("model_input", input_event["event_id"]), ("tool_lifecycle", input_event["event_id"]),
                            ("phase_boundaries", report["event_id"]), ("report_completion", report["event_id"]))])


def submit_stored_report(host, report, revision):
    return host.submit_report(report_event=report, proposal_content="Authored paper abstention; no trading",
        proposal_revision=revision, request_id=f"stored-request-{revision}", checkpoint_id="stored-prefix",
        checkpoint_revision=revision, streams=[dict(stream_id="host", requested=len(host.capture.events))])


class PersistedHostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "feedback.sqlite"
        self.backend, self.host = stored_fixture(self.path)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: self.backend.close())

    def initial_report(self):
        event = self.host.assemble_input([dict(type="human", content="Authored report request; no snapshot delivered")],
            report_id="market-report", report_revision=0)
        report = self.host.capture.report(content="Authored initial report; required snapshot omitted",
            report_id="market-report", revision=0, input_event_id=event["event_id"], completion="COMPLETE", phase="CLOSED")
        captured_coverage(self.backend, event, report)
        return event, report

    def test_persisted_delivery_revision_recheck_and_restart_preserve_failure(self):
        _, report0 = self.initial_report()
        request0 = submit_stored_report(self.host, report0, 0)
        payload0 = self.host.boundary.verify()
        failed = json.loads(payload0)
        self.assertEqual([f["outcome"] for f in failed["findings"]], ["FAIL", "PASS"])
        with self.assertRaisesRegex(BoundaryError, "newer revision"):
            self.host.record_revision(failed["assessment_id"], report0)
        self.host.observe_return(call_id="verify-0", tool_name="verify_proposal", content=payload0, status="SUCCESS")
        feedback_message = dict(type="tool", name="verify_proposal", tool_call_id="verify-0", content=payload0)
        self.host.assemble_input([feedback_message], report_id="market-report", report_revision=1)
        self.host.acknowledge(failed["assessment_id"], "Authored acknowledgement of omission")
        defect = self.host.boundary.source_round([lambda: "Authored provider defect Close=99 Low=100; no replacement price"])[0]
        self.host.observe_return(call_id="snapshot-1", tool_name="authored_snapshot", content=defect, status="SUCCESS")
        input1 = self.host.assemble_input([feedback_message, dict(type="tool", name="authored_snapshot",
            tool_call_id="snapshot-1", content=defect)], report_id="market-report", report_revision=1)
        report1 = self.host.capture.report(content="Authored abstention: provider defect remains unresolved",
            report_id="market-report", revision=1, input_event_id=input1["event_id"], completion="COMPLETE", phase="CLOSED")
        self.host.record_revision(failed["assessment_id"], report1)
        self.assertFalse(self.host.boundary.report_boundary_allowed(report1))
        captured_coverage(self.backend, input1, report1)
        request1 = submit_stored_report(self.host, report1, 1)
        rechecked = json.loads(self.host.boundary.verify(origin="host"))
        self.assertEqual([f["outcome"] for f in rechecked["findings"]], ["PASS", "PASS"])
        self.assertNotEqual(failed["binding"], rechecked["binding"])
        self.assertEqual(self.host.boundary.counts, dict(source_rounds=1, verify_calls=2, remediations=1))
        self.assertEqual(len(self.backend.resolve_view(request0)["events"]), 2)
        self.assertEqual(self.backend.resolve_view(request1), {k: self.host.boundary.packet[k] for k in ("checkpoint", "events", "policy")})
        kinds = [e["event_type"] for e in self.host.capture.events]
        for kind in ("feedback_delivery", "feedback_inclusion", "feedback_acknowledgement", "correction"):
            self.assertIn(kind, kinds)
        self.host.boundary.abstain("Scoped procedure passes; source defect and decision suitability remain unresolved")
        self.assertFalse(self.backend.execute("get_run_state", dict(run_id="authored-run"))["atomic_semantic_ready"])
        with self.assertRaises(ServiceError) as error:
            self.backend.execute("acknowledge_feedback", dict(run_id="authored-run"))
        self.assertEqual(error.exception.code, "UNSUPPORTED_OPERATION")
        principal = self.backend.principal
        self.backend.close()
        self.backend = ServiceBackend(self.path, principal=principal, service_id="authored-local-service")
        for result in (failed, rechecked):
            self.assertEqual(self.backend.execute("get_assessment", dict(run_id="authored-run", assessment_id=result["assessment_id"])), result)
        self.assertEqual(len(self.backend.resolve_view(request0)["events"]), 2)
        self.assertIn(defect, [e["content"] for e in self.backend.resolve_view(request1)["events"]])
        self.backend.audit()

    def test_actual_receipt_duplicate_retry_and_malformed_controls(self):
        capture = HostEventCapture(run_id="authored-run", stream_id="host", producer_id="authored-host",
            redaction_profile="authored-public", redact=lambda s: s, emit=lambda e: None)
        event = capture.tool_result(call_id="c", tool_name="authored_snapshot", content="Authored body", status="SUCCESS")
        self.backend.execute("ingest_events", dict(run_id="authored-run", batch_id="earlier-batch", events=[event]))
        ingest = make_host_ingest(self.backend, run_id="authored-run")
        receipt = ingest(event)
        self.assertEqual(receipt["events"][0]["status"], "DUPLICATE")
        self.assertEqual(ingest(event), receipt)
        mutations = []
        for field in ("run_id", "batch_id", "receipt_id"):
            changed = deepcopy(receipt)
            changed[field] = "wrong"
            mutations.append(changed)
        for field, value in (("event_id", "wrong"), ("receipt_position", True), ("status", "WRONG"), ("status", [])):
            changed = deepcopy(receipt)
            changed["events"][0][field] = value
            mutations.append(changed)
        changed = deepcopy(receipt)
        changed["streams"] = []
        mutations.append(changed)
        for changed in mutations:
            self.assertFalse(validate_ingest_receipt(changed, event))

    def test_invalid_reply_after_real_commit_does_not_advance_capture_and_exact_retry_recovers(self):
        backend = self.backend
        class CorruptReply:
            def execute(self, operation, request):
                response = backend.execute(operation, request)
                response["receipt_id"] = "wrong"
                return response
        self.host.capture.emit = make_host_ingest(CorruptReply(), run_id="authored-run")
        with self.assertRaisesRegex(BoundaryError, "receipt"):
            self.host.capture.tool_result(call_id="retry-call", tool_name="authored_snapshot", content="Authored exact body", status="SUCCESS")
        self.assertEqual(self.host.capture.events, [])
        self.assertEqual(self.backend.execute("get_run_state", dict(run_id="authored-run"))["raw_ingested_events"], 1)
        self.host.capture.emit = make_host_ingest(self.backend, run_id="authored-run")
        event = self.host.capture.tool_result(call_id="retry-call", tool_name="authored_snapshot", content="Authored exact body", status="SUCCESS")
        self.assertEqual(event["event_id"], "host:1")
        self.assertEqual(len(self.host.capture.events), 1)
        self.assertEqual(self.backend.execute("get_run_state", dict(run_id="authored-run"))["raw_ingested_events"], 1)

    def test_persisted_unready_prefix_stays_unresolved_without_source_calls(self):
        self.backend.project_on_ingest = False
        _, report = self.initial_report()
        request = submit_stored_report(self.host, report, 0)
        result = json.loads(self.host.boundary.verify())
        self.assertEqual(result["status"], "NOT_READY")
        self.assertTrue(all(f["outcome"] == "INCONCLUSIVE" for f in result["findings"]))
        self.host.boundary.abstain("Projection prerequisite not ready")
        self.backend.project("authored-run")
        self.assertEqual(self.backend.execute("verify", request), result)
        self.assertEqual(self.host.boundary.counts["source_rounds"], 0)


class BoundaryTests(unittest.TestCase):
    def same_return_capture(self, count=2):
        capture = HostEventCapture(run_id="authored-run", stream_id="host", producer_id="authored-host",
            redaction_profile="authored-public", redact=lambda s: s, emit=lambda e: None)
        for index in range(count):
            capture.tool_result(call_id=f"call-{index + 1}", tool_name="market_snapshot", content="SAME", status="SUCCESS")
        return capture

    def assess_captured_input(self, capture, input_event):
        # Explicit authored service view; no actual B coverage assertion.
        report = capture.report(content="Authored report", report_id="market-report", revision=0,
            input_event_id=input_event["event_id"], completion="COMPLETE", phase="CLOSED")
        packet = authored_packet()
        packet["events"] = deepcopy(capture.events)
        packet["policy"]["required_tool"] = "market_snapshot"
        packet["request"]["policy"]["digest"] = digest(packet["policy"])
        packet["request"]["proposal"]["report_event_id"] = report["event_id"]
        stream = packet["checkpoint"]["streams"][0]
        stream.update(requested=len(capture.events), ingested_through=len(capture.events), projected_through=len(capture.events))
        for capability in stream["capabilities"]:
            capability["basis_event_ids"] = [input_event["event_id"]]
        packet["request"]["checkpoint"]["digest"] = digest(packet["checkpoint"])
        return verify(**packet)

    def test_identical_flattened_returns_withhold_both_origins_and_assessment(self):
        capture = self.same_return_capture()
        messages = [dict(type="human", content="[market_snapshot returned]\nSAME")]
        event = capture.assembled_native_input(messages, report_id="market-report", report_revision=0)
        self.assertEqual(event["content"], canonical_json(messages))
        self.assertEqual(event["payload"]["included_event_ids"], [])
        self.assertEqual(event["parents"], [])
        self.assertEqual(event["payload"]["boundary"], "UNKNOWN")
        result = self.assess_captured_input(capture, event)
        self.assertEqual(result["findings"][0]["outcome"], "INCONCLUSIVE")
        self.assertEqual(result["disposition"], "RECHECK")

    def test_partial_history_links_only_intact_occurrence_and_keeps_flattening_unknown(self):
        for extra in [dict(type="human", content="[market_snapshot returned]\nSAME"),
                      dict(type="tool", name="market_snapshot", tool_call_id="unobserved-call", content="SAME")]:
            with self.subTest(extra=extra):
                capture = self.same_return_capture()
                messages = [dict(type="tool", name="market_snapshot", tool_call_id="call-2", content="SAME"), extra]
                event = capture.assembled_native_input(messages, report_id="market-report", report_revision=0)
                self.assertEqual(event["payload"]["included_event_ids"], ["host:2"])
                self.assertEqual(event["payload"]["boundary"], "UNKNOWN")
                self.assertEqual(self.assess_captured_input(capture, event)["findings"][0]["outcome"], "INCONCLUSIVE")

    def test_ordinary_human_marker_with_unique_match_never_proves_tool_origin(self):
        capture = self.same_return_capture(count=1)
        event = capture.assembled_native_input([dict(type="human", content="[market_snapshot returned]\nSAME")],
            report_id="market-report", report_revision=0)
        self.assertEqual(event["payload"]["included_event_ids"], [])
        self.assertEqual(event["payload"]["boundary"], "UNKNOWN")
        self.assertEqual(self.assess_captured_input(capture, event)["findings"][0]["outcome"], "INCONCLUSIVE")

    def test_intact_toolmessage_ids_distinguish_identical_returns_in_partial_input(self):
        for call_ids in [("call-2",), ("call-1", "call-2")]:
            with self.subTest(call_ids=call_ids):
                capture = self.same_return_capture()
                event = capture.assembled_native_input([dict(type="tool", name="market_snapshot", tool_call_id=call_id,
                    content="SAME") for call_id in call_ids], report_id="market-report", report_revision=0)
                self.assertEqual(event["payload"]["included_event_ids"], [f"host:{call_id[-1]}" for call_id in call_ids])
                self.assertEqual(event["payload"]["boundary"], "ASSEMBLED")
                self.assertEqual(self.assess_captured_input(capture, event)["findings"][0]["outcome"], "PASS")

    def test_stored_operation_shape_with_authored_double_and_rejected_receipt(self):
        packet = authored_packet()
        calls = []
        class AuthoredServiceDouble:
            def execute(self, operation, request):
                calls.append((operation, deepcopy(request)))
                if operation == "verify":
                    # Real accepted A core, authored in-memory service view only.
                    return verify(request, **{k: v for k, v in packet.items() if k != "request"})
                return {"authored_receipt": True}
        backend = AuthoredServiceDouble()
        host = self.make_boundary(assess=make_stored_assessor(backend))
        host.submit(**packet)
        self.deliver(host)
        self.assertEqual(calls[0], ("verify", packet["request"]))
        ingest = make_host_ingest(backend, run_id="authored-run", accept_receipt=lambda *_: False)
        with self.assertRaisesRegex(BoundaryError, "receipt"):
            ingest(packet["events"][0])
        accepted = make_host_ingest(backend, run_id="authored-run", accept_receipt=lambda r, e: r.get("authored_receipt") is True)
        accepted(packet["events"][0])
        self.assertEqual(calls[-1][1], calls[-2][1])
        self.assertEqual(set(calls[-1][1]), {"run_id", "batch_id", "events"})
        wrong_run = deepcopy(packet["events"][0])
        wrong_run["run_id"] = "other"
        with self.assertRaises(BoundaryError):
            accepted(wrong_run)

    def make_boundary(self, **kwargs):
        self.observations = []
        defaults = dict(run_id="authored-run", proposal_id="paper-proposal", assess=verify,
                        emit=lambda kind, data: self.observations.append((kind, data)))
        return FeedbackBoundary(**(defaults | kwargs))

    def deliver(self, host):
        payload = host.verify()
        call_id = f"verify-{host.counts['verify_calls']}"
        host.observe_tool_return(call_id, payload)
        host.observe_next_input("authored-next-input", [(call_id, payload)])
        return json.loads(payload)

    def report_event(self, packet):
        return next(e for e in packet["events"] if e["event_id"] == packet["request"]["proposal"]["report_event_id"])

    def test_accepted_binding_real_core_and_report_proposal_separation(self):
        packet = authored_packet()
        host = self.make_boundary(authorize=lambda *_: True)
        host.submit(**packet)
        result = self.deliver(host)
        self.assertEqual([f["outcome"] for f in result["findings"]], ["PASS", "PASS"])
        self.assertTrue(host.report_boundary_allowed(self.report_event(packet)))
        same_text_new_report = deepcopy(self.report_event(packet))
        same_text_new_report["event_id"] = "new-report-event"
        same_text_new_report["payload"]["revision"] += 1
        self.assertFalse(host.report_boundary_allowed(same_text_new_report))
        self.assertFalse(host.report_boundary_allowed(packet["request"]["proposal"]["content"]))
        self.assertEqual(result["scope"], "declared_checks_at_checkpoint")
        self.assertEqual(packet["request"]["proposal"]["dependency_completeness"], "UNKNOWN")
        host.packet["request"]["proposal"]["content"] += " changed downstream decision"
        host.packet["request"]["proposal"]["content_digest"] = text_digest(host.packet["request"]["proposal"]["content"])
        self.assertFalse(host.report_boundary_allowed(self.report_event(packet)))

    def test_delivery_input_ack_and_at_use_authorizer_are_distinct(self):
        packet = authored_packet()
        allowed = [True]
        host = self.make_boundary(authorize=lambda *_: allowed[0])
        host.submit(**packet)
        text = self.report_event(packet)
        self.assertFalse(host.report_boundary_allowed(text))  # Omitted verify.
        payload = host.verify()
        host.observe_tool_return("c", payload)
        host.acknowledge(host.feedback["assessment_id"], "Authored acknowledgement")
        self.assertFalse(host.report_boundary_allowed(text))
        host.observe_next_input("i", [("other", payload), ("c", "different")])
        self.assertFalse(host.report_boundary_allowed(text))
        host.observe_next_input("i2", [("c", payload)])
        self.assertTrue(host.report_boundary_allowed(text))
        self.assertFalse(host.report_boundary_allowed("Invented revised report Close=101"))
        allowed[0] = False
        self.assertFalse(host.report_boundary_allowed(text))

    def test_revision_rejects_old_result_and_identity_reuse(self):
        host = self.make_boundary()
        first = authored_packet()
        host.submit(**first)
        old_result = self.deliver(host)
        changed = deepcopy(first)
        changed["request"]["proposal"]["report_revision"] = 9
        with self.assertRaises(ContractError):
            host.submit(**changed)
        second = authored_packet(1)
        host.submit(**second)
        host.assess = lambda **_: old_result
        with self.assertRaisesRegex(BoundaryError, "Stale"):
            host.verify()
        self.assertEqual(host.proposals[0], first["request"]["proposal"])
        self.assertFalse(host.report_boundary_allowed(self.report_event(second)))

    def test_evidence_policy_checkpoint_bindings_and_malformed_result(self):
        original = authored_packet()
        old_result = verify(**original)
        for field in ("events", "checkpoint", "policy", "malformed"):
            with self.subTest(field=field):
                packet = deepcopy(original)
                if field == "events":
                    packet["events"][0]["content"] += " changed"
                    packet["events"][0]["content_digest"] = text_digest(packet["events"][0]["content"])
                elif field == "checkpoint":
                    packet["checkpoint"]["created_at"] = "2026-11-05T12:00:00Z"
                    packet["request"]["checkpoint"]["digest"] = digest(packet["checkpoint"])
                elif field == "policy":
                    packet["policy"]["version"] = "2"
                    packet["request"]["policy"].update(version="2", digest=digest(packet["policy"]))
                host = self.make_boundary(assess=lambda **_: {} if field == "malformed" else old_result)
                host.submit(**packet)
                with self.assertRaises((BoundaryError, ContractError)):
                    host.verify()

    def test_unknown_input_never_promoted_and_unready_gap_error_hold(self):
        packets = [authored_packet(boundary="UNKNOWN"), authored_packet(snapshot=False), authored_packet(completion="TRUNCATED")]
        lag, gap, cycle = authored_packet(), authored_packet(), authored_packet()
        lag["checkpoint"]["streams"][0]["projected_through"] = 1
        gap["checkpoint"]["streams"][0]["gaps"] = [[1, 1]]
        cycle["events"][0]["parents"] = [cycle["events"][-1]["event_id"]]
        for p in (lag, gap):
            p["request"]["checkpoint"]["digest"] = digest(p["checkpoint"])
        packets += [lag, gap, cycle]
        for packet in packets:
            with self.subTest(kind=packet["checkpoint"]["streams"][0]):
                host = self.make_boundary(authorize=lambda *_: True)
                host.submit(**packet)
                result = self.deliver(host)
                self.assertIn(result["disposition"], {"HOLD", "RECHECK"})
                self.assertFalse(host.report_boundary_allowed(self.report_event(packet)))

    def test_limits_timeout_failed_refresh_and_terminal_abstention(self):
        host = self.make_boundary(limits=Limits(1, 2, 1), authorize=lambda *_: True)
        host.submit(**authored_packet())
        self.deliver(host)
        def unavailable():
            raise TimeoutError("authored source failure")
        with self.assertRaises(TimeoutError):
            host.source_round([unavailable])
        self.assertEqual(host.counts, dict(source_rounds=1, verify_calls=1, remediations=0))
        with self.assertRaises(BoundaryError):
            host.source_round([])
        host.submit(**authored_packet(1))
        def timeout(**_):
            raise TimeoutError("authored backend failure")
        host.assess = timeout
        with self.assertRaises(TimeoutError):
            host.verify()
        with self.assertRaises(BoundaryError):
            host.verify()
        with self.assertRaises(BoundaryError):
            host.submit(**authored_packet(2))
        host.abstain("Provider defect cannot be corrected by inventing a price")
        self.assertFalse(host.report_boundary_allowed("any report"))

    def test_authored_omission_recheck_preserves_failure_and_defect(self):
        host = self.make_boundary()
        host.submit(**authored_packet(snapshot=False))
        first = self.deliver(host)
        self.assertEqual(first["findings"][0]["outcome"], "FAIL")
        host.acknowledge(first["assessment_id"], "Authored acknowledgement, no correction inferred")
        host.submit(**authored_packet(1))
        second = self.deliver(host)
        self.assertEqual(second["findings"][0]["outcome"], "PASS")
        self.assertNotEqual(first["binding"], second["binding"])
        self.assertIn("Close=99 Low=100", host.packet["events"][0]["content"])
        # PASS is only required-tool delivery, never validation of these prices.
        self.assertFalse(host.report_boundary_allowed(self.report_event(host.packet)))

    def test_capture_redaction_explicit_unknown_and_exact_causal_links(self):
        saved = []
        capture = HostEventCapture(run_id="authored", stream_id="host", producer_id="host",
            redaction_profile="authored-test", redact=lambda s: s.replace("PRIVATE", "[REDACTED]"), emit=saved.append)
        result = capture.tool_result(call_id="c", tool_name="snapshot", content="PRIVATE Close=99 Low=100", status="UNKNOWN")
        self.assertNotIn("PRIVATE", result["content"])
        self.assertEqual(result["content_digest"], text_digest(result["content"]))
        self.assertEqual(capture.tool_result(call_id="c", tool_name="snapshot", content="PRIVATE Close=99 Low=100", status="UNKNOWN"), result)
        with self.assertRaises(BoundaryError):
            capture.tool_result(call_id="c", tool_name="snapshot", content="Close=101", status="SUCCESS")
        input_event = capture.model_input(messages=[dict(role="tool", content=result["content"])], report_id="report",
            report_revision=0, included_event_ids=[result["event_id"]], boundary="UNKNOWN")
        report = capture.report(content="Authored report", report_id="report", revision=0,
            input_event_id=input_event["event_id"], completion="UNKNOWN", phase="UNKNOWN")
        self.assertEqual(input_event["payload"]["boundary"], "UNKNOWN")
        self.assertEqual(input_event["parents"], [result["event_id"]])
        self.assertEqual(report["parents"], [input_event["event_id"]])
        acknowledgement = capture.feedback(event_type="feedback_acknowledgement", assessment_id="authored-assessment",
            proposal_id="paper-proposal", proposal_revision=0, related_event_ids=[report["event_id"]],
            content="Authored acknowledgement; no correction inferred")
        self.assertEqual(acknowledgement["event_type"], "feedback_acknowledgement")
        for event in saved:
            validate_event(event)


class NativePinnedDispatchTests(unittest.TestCase):
    """Exact function ASTs with real LangGraph; no upstream package side effects.

    Source subset extraction is deliberate: importing the whole upstream package
    also loads provider and configuration modules. No source function is rewritten.
    This does not prove full GraphSetup integration or persistent restart resume.
    """

    @classmethod
    def setUpClass(cls):
        location = os.environ.get("TRUSTKERNEL_TRADINGAGENTS_UPSTREAM")
        if not location:
            raise unittest.SkipTest("Native integration NOT RUN: pinned source path not supplied")
        root = Path(location).resolve()
        pin = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        if pin != UPSTREAM_COMMIT:
            raise RuntimeError("Pinned source mismatch")
        try:
            from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
            from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
            from langchain_core.runnables import Runnable
            from langgraph.graph import END, START, StateGraph, MessagesState
            from langgraph.prebuilt import ToolNode
            from typing_extensions import TypedDict
        except ImportError as exc:
            raise unittest.SkipTest(f"Native integration NOT RUN: optional dependency missing: {exc.name}")
        import json
        namespace = dict(AIMessage=AIMessage, HumanMessage=HumanMessage, ToolMessage=ToolMessage,
                         ChatPromptTemplate=ChatPromptTemplate, MessagesPlaceholder=MessagesPlaceholder,
                         END=END, START=START, StateGraph=StateGraph, ToolNode=ToolNode,
                         MessagesState=MessagesState, TypedDict=TypedDict, Annotated=Annotated,
                         Counter=Counter, logger=logging.getLogger("authored-native-test"), json=json)
        subsets = {
            "tradingagents/agents/state.py": {"InvestDebateState", "RiskDebateState", "AgentState"},
            "tradingagents/agents/analysts/turn.py": {"WRAP_UP", "take_turn", "_as_text"},
            "tradingagents/graph/setup.py": {"_tools_or_done", "_analyst_graph"},
            "tradingagents/agents/analysts/market_analyst.py": {"create_market_analyst"},
        }
        for relative, names in subsets.items():
            data = (root / relative).read_bytes()
            original = subprocess.check_output(["git", "-C", str(root), "show", f"{UPSTREAM_COMMIT}:{relative}"])
            # Git working trees may normalize line endings; content must be identical.
            if data.replace(b"\r\n", b"\n") != original.replace(b"\r\n", b"\n"):
                raise RuntimeError("Changed pinned source: " + relative)
            tree = ast.parse(data, filename=relative)
            selected = [node for node in tree.body if getattr(node, "name", None) in names
                        or isinstance(node, ast.Assign) and any(getattr(t, "id", None) in names for t in node.targets)]
            exec(compile(ast.Module(body=selected, type_ignores=[]), relative, "exec"), namespace)
        cls.ns, cls.Runnable = namespace, Runnable

    def test_real_toolnode_dispatch_next_input_and_wrapup_text(self):
        self.dispatch(max_tool_rounds=1)

    def test_real_toolnode_dispatch_next_input_without_wrapup(self):
        self.dispatch(max_tool_rounds=2)

    def test_human_feedback_marker_does_not_attribute_identical_delivery_occurrences(self):
        observations = []
        host = FeedbackBoundary(run_id="authored-run", proposal_id="paper-proposal", assess=verify,
            emit=lambda kind, data: observations.append((kind, data)))
        host.submit(**authored_packet())
        payload = host.verify()
        host.observe_tool_return("one", payload)
        host.observe_tool_return("two", payload)
        ns = self.ns
        class AuthoredEcho(self.Runnable):
            def invoke(self, prompt, config=None, **kwargs):
                return ns["AIMessage"](content="Authored response; no correction")
        wrapper = make_trusted_model(AuthoredEcho(), host)
        wrapper.invoke([ns["HumanMessage"](content="[verify_proposal returned]\n" + payload)])
        self.assertEqual(host.included, set())
        self.assertNotIn("feedback.input_included", [kind for kind, _ in observations])

    def test_persisted_native_dispatch_revision_and_scoped_recheck(self):
        self.persisted_dispatch(max_tool_rounds=3)

    def test_persisted_native_wrapup_stays_unresolved_on_recheck(self):
        self.persisted_dispatch(max_tool_rounds=1)

    def persisted_dispatch(self, max_tool_rounds):
        from langchain_core.tools import StructuredTool
        from types import FunctionType
        with tempfile.TemporaryDirectory() as directory:
            backend, host = stored_fixture(Path(directory) / "native-feedback.sqlite", worker=True)
            try:
                first_input = host.assemble_input([dict(type="human", content="Authored initial report request")],
                    report_id="market-report", report_revision=0)
                report0 = host.capture.report(content="Authored report with omitted snapshot", report_id="market-report",
                    revision=0, input_event_id=first_input["event_id"], completion="COMPLETE", phase="CLOSED")
                captured_coverage(backend, first_input, report0)
                request0 = submit_stored_report(host, report0, 0)
                ns, inputs, captured_inputs = self.ns.copy(), [], []
                defect = "Authored provider defect Close=99 Low=100; never replace this price"

                def authored_snapshot() -> str:
                    """Authored offline source return; no provider network operation."""
                    return host.boundary.source_round([lambda: defect])[0]

                tool = make_verify_tool(host.boundary)
                source = StructuredTool.from_function(authored_snapshot)
                ns.update(TOOLS=(tool, source), get_language_instruction=lambda: "",
                    get_instrument_context_from_state=lambda state: "Authored fixture; no order authority")
                factory = FunctionType(ns["create_market_analyst"].__code__, ns)
                test = self
                class AuthoredCorrection(self.Runnable):
                    def bind_tools(self, tools, **kwargs):
                        test.assertEqual([t.name for t in tools], ["verify_proposal", "authored_snapshot"])
                        return self
                    def invoke(self, prompt, config=None, **kwargs):
                        messages = prompt.to_messages() if hasattr(prompt, "to_messages") else prompt
                        inputs.append(messages)
                        if len(inputs) == 1:
                            return ns["AIMessage"](content="", tool_calls=[dict(name="verify_proposal", args={},
                                id="native-verify-0", type="tool_call")])
                        original = next(iter(host.boundary.pending_returns.values()))
                        test.assertEqual(original["findings"][0]["outcome"], "FAIL")
                        test.assertIn(original["assessment_id"], "\n".join(str(m.content) for m in messages))
                        if len(inputs) == 2:
                            host.acknowledge(original["assessment_id"], "Authored acknowledgement of omitted call")
                            if max_tool_rounds > 1:
                                return ns["AIMessage"](content="", tool_calls=[dict(name="authored_snapshot", args={},
                                    id="native-snapshot-1", type="tool_call")])
                        if max_tool_rounds > 1:
                            test.assertIn(defect, "\n".join(str(m.content) for m in messages))
                        return ns["AIMessage"](content="AUTHORED abstention: source defect or missing source remains",
                            response_metadata=dict(finish_reason="stop"))

                def capture_input(messages):
                    event = host.assemble_input(messages, report_id="market-report", report_revision=1)
                    captured_inputs.append(event)
                    return event
                analyst = factory(make_trusted_model(AuthoredCorrection(), host.boundary, capture_input=capture_input))
                reports = []
                def observed_agent(state):
                    host.observe_native_returns(state["messages"], classify_status=lambda message:
                        "SUCCESS" if message.name == "authored_snapshot" else "UNKNOWN")
                    output = analyst(state)
                    if output["market_report"]:
                        # Explicit authored stop metadata, not nonempty-output inference.
                        test.assertEqual(output["messages"][0].response_metadata.get("finish_reason"), "stop")
                        reports.append(host.capture.report(content=output["market_report"], report_id="market-report",
                            revision=1, input_event_id=captured_inputs[-1]["event_id"], completion="COMPLETE", phase="CLOSED"))
                    return output
                spec = SimpleNamespace(key="market", agent_node="Market Analyst", report_key="market_report", tools=(tool, source))
                with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
                     patch("socket.create_connection", side_effect=AssertionError("Network forbidden")):
                    graph = ns["_analyst_graph"](spec, observed_agent, max_tool_rounds=max_tool_rounds)
                    result = graph.invoke(dict(messages=[], trade_date="2026-11-05"),
                        config=dict(recursion_limit=12, max_concurrency=1))
                report1 = reports[-1]
                self.assertEqual(result["market_report"], report1["content"])
                original = next(iter(host.boundary.pending_returns.values()))
                host.record_revision(original["assessment_id"], report1)
                captured_coverage(backend, captured_inputs[-1], report1)
                request1 = submit_stored_report(host, report1, 1)
                recheck = json.loads(host.boundary.verify(origin="host"))
                expected = "PASS" if max_tool_rounds > 1 else "INCONCLUSIVE"
                self.assertEqual([f["outcome"] for f in recheck["findings"]], [expected, "PASS"])
                self.assertEqual(captured_inputs[-1]["payload"]["boundary"], "ASSEMBLED" if max_tool_rounds > 1 else "UNKNOWN")
                self.assertNotEqual(original["binding"], recheck["binding"])
                self.assertEqual(backend.execute("get_assessment", dict(run_id="authored-run", assessment_id=original["assessment_id"])), original)
                self.assertEqual(len(backend.resolve_view(request0)["events"]), 2)
                self.assertEqual(host.boundary.counts, dict(source_rounds=1 if max_tool_rounds > 1 else 0, verify_calls=2, remediations=1))
                kinds = [event["event_type"] for event in backend.resolve_view(request1)["events"]]
                self.assertIn("feedback_delivery", kinds)
                self.assertEqual("feedback_inclusion" in kinds, max_tool_rounds > 1)
                if max_tool_rounds > 1:
                    self.assertIn(defect, [event["content"] for event in backend.resolve_view(request1)["events"]])
                host.boundary.abstain("Authored paper abstention; scoped procedure is not price/decision truth")
                self.assertFalse(backend.execute("get_run_state", dict(run_id="authored-run"))["atomic_semantic_ready"])
                backend.audit()
            finally:
                backend.close()

    def dispatch(self, max_tool_rounds):
        from langchain_core.tools import StructuredTool
        verify_core = verify
        ns = self.ns.copy()
        events, calls, inputs = [], [], []
        host = FeedbackBoundary(run_id="authored-run", proposal_id="paper-proposal",
            emit=lambda k, d: events.append((k, d)), assess=verify_core)
        packet = authored_packet(snapshot=False)
        host.submit(**packet)
        expected_assessment = verify_core(**packet)["assessment_id"]
        native_events, captured_inputs = [], []
        capture = HostEventCapture(run_id="authored-run", stream_id="native-host", producer_id="authored-native",
            redaction_profile="authored-public", redact=lambda s: s, emit=native_events.append)
        def capture_input(messages):
            event = capture.assembled_native_input(messages, report_id="market-report", report_revision=1)
            captured_inputs.append(event)
            return event

        def authored_source() -> str:
            """Return an authored defective row; never fetch a provider."""
            return "Authored row: Close=99 Low=100; do not invent a replacement"

        verify_tool = make_verify_tool(host)
        self.assertEqual(verify_tool.args, {})  # Agent cannot replace policy, proposal or checkpoint.
        source = StructuredTool.from_function(authored_source)
        ns.update(TOOLS=(source, verify_tool), get_language_instruction=lambda: "",
                  get_instrument_context_from_state=lambda state: "Authored instrument, no order authority")
        # Re-execute the exact factory AST so only its globals are injected.
        factory = ns["create_market_analyst"]
        from types import FunctionType
        factory = FunctionType(factory.__code__, ns)

        class AuthoredResponses(self.Runnable):
            def bind_tools(self, tools, **kwargs):
                calls.append([tool.name for tool in tools])
                return self

            def invoke(self, prompt, config=None, **kwargs):
                messages = prompt.to_messages() if hasattr(prompt, "to_messages") else prompt
                inputs.append(messages)
                self_outer.assertEqual(messages[0].content, TRUSTED_INSTRUCTION)
                if len(inputs) == 1:
                    return ns["AIMessage"](content="", tool_calls=[
                        dict(name="authored_source", args={}, id="source-call", type="tool_call"),
                        dict(name="verify_proposal", args={}, id="verify-call", type="tool_call")])
                # Observe native ToolMessages, or the exact pinned _as_text at cap.
                text = "\n".join(str(m.content) for m in messages)
                self_outer.assertIn(expected_assessment, text)
                self_outer.assertIn("Close=99 Low=100", text)
                return ns["AIMessage"](content="AUTHORED abstention: provider defect unresolved")

        self_outer = self
        spec = SimpleNamespace(key="market", agent_node="Market Analyst", report_key="market_report", tools=(source, verify_tool))
        # No model, provider client, source runner or upstream constructor runs.
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("Network forbidden")):
            # _analyst_graph uses its original globals: supply required real classes.
            analyst = factory(make_trusted_model(AuthoredResponses(), host, capture_input=capture_input))
            def observed_agent(state):
                observe_native_returns(host, state["messages"], capture=capture)
                output = analyst(state)
                if output["market_report"]:
                    capture.report(content=output["market_report"], report_id="market-report", revision=1,
                        input_event_id=captured_inputs[-1]["event_id"], completion="UNKNOWN", phase="CLOSED")
                return output
            graph = ns["_analyst_graph"](spec, observed_agent, max_tool_rounds=max_tool_rounds)
            result = graph.invoke(dict(messages=[], trade_date="2026-11-05"),
                                  config=dict(recursion_limit=8, max_concurrency=1))
        self.assertEqual(result, {"market_report": "AUTHORED abstention: provider defect unresolved"})
        self.assertEqual(len(inputs), 2)
        self.assertEqual(calls, [["authored_source", "verify_proposal"]] * max_tool_rounds)
        self.assertEqual(host.counts["verify_calls"], 1)
        self.assertEqual([e["event_type"] for e in native_events],
                         ["model_input", "tool_result", "tool_result", "model_input", "report"])
        actual_input, actual_report = captured_inputs[-1], native_events[-1]
        self.assertEqual(actual_input["payload"]["boundary"], "UNKNOWN" if max_tool_rounds == 1 else "ASSEMBLED")
        self.assertEqual(actual_input["payload"]["included_event_ids"],
                         [] if max_tool_rounds == 1 else [e["event_id"] for e in native_events if e["event_type"] == "tool_result"])
        self.assertEqual(actual_report["payload"]["input_event_id"], actual_input["event_id"])
        self.assertEqual(actual_report["parents"], [actual_input["event_id"]])
        self.assertEqual(actual_report["payload"]["completion"], "UNKNOWN")
        self.assertEqual([e["payload"]["status"] for e in native_events if e["event_type"] == "tool_result"],
                         ["UNKNOWN", "UNKNOWN"])
        self.assertIn("authored_snapshot", host.packet["policy"]["required_tool"])
        self.assertEqual(host.feedback["findings"][0]["outcome"], "FAIL")
        self.assertNotEqual(actual_report["event_id"], host.packet["request"]["proposal"]["report_event_id"])
        self.assertFalse(host.report_boundary_allowed(actual_report))
        self.assertEqual([k for k, _ in events if k.startswith("feedback.")],
                         ["feedback.prepared", "feedback.delivered"] + ([] if max_tool_rounds == 1 else ["feedback.input_included"]))


if __name__ == "__main__":
    unittest.main()
