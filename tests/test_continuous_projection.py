"""Prefix/replay tests over temporary authored trace inputs only."""
import tempfile
import unittest
import copy
import json
import subprocess
import sys
from pathlib import Path

from continuous_verification.capture import TraceTailer
from continuous_verification.journal import CaptureError, Journal, canonical
from continuous_verification.projection import Projection, replay
from continuous_verification.service import CaptureService, Principal, ServiceBackend, ServiceError
from continuous_verification.contracts import binding_matches, digest, text_digest
from continuous_verification.verifier import verify as core_verify
from tests.test_continuous_capture import event, line


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "trace.jsonl"
        self.journal = Journal(self.root / "journal.sqlite")
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.journal.close)

    def append(self, value):
        with self.path.open("ab") as stream:
            stream.write(line(value))
        TraceTailer(self.journal, "authored-source", self.path).poll()

    def test_incremental_full_replay_bytes_equal_at_each_prefix(self):
        projection, previous = Projection(), None
        for seq in range(1, 9):
            value = event(seq, previous, kind="llm.start" if seq % 2 else "tool.end",
                          payload={"prompts": ["Authored input μ"]} if seq % 2 else {"output": "Authored return"})
            previous = value["event_hash"]
            self.append(value)
            projection.advance(self.journal)
            self.assertEqual(canonical(projection.rows()), canonical(replay(self.journal, seq).rows()))
        for prefix in range(9):
            self.assertEqual(len([r for r in replay(self.journal, prefix).rows() if r["table"] == "events"]), prefix)

    def test_late_evidence_cannot_enter_earlier_input_or_prefix(self):
        one = event(kind="llm.start", payload={"prompts": ["Existing input"]})
        self.append(one)
        before = canonical(replay(self.journal, 1).rows())
        self.append(event(2, one["event_hash"], payload={"output": "Late evidence"}))
        self.assertEqual(before, canonical(replay(self.journal, 1).rows()))
        inputs = [row["text"] for row in replay(self.journal).rows() if row.get("role") == "model_input"]
        self.assertEqual(inputs, ["Existing input"])
        self.assertNotIn("Late evidence", before)

    def test_exact_json_pointer_unicode_span_and_no_reasoning_extraction(self):
        value = event(kind="llm.start", payload={"messages": [[{"content": [
            {"type": "text", "text": "μ😀 Price 42"}, {"type": "reasoning", "text": "inaccessible"}]}]]})
        self.append(value)
        row = next(row for row in replay(self.journal).rows() if row["table"] == "texts")
        target = value
        for part in row["pointer"][1:].split("/"):
            target = target[int(part)] if isinstance(target, list) else target[part]
        self.assertEqual(target[row["start"]:row["end"]], row["text"])
        self.assertEqual(row["end"], len("μ😀 Price 42"))

    def test_projection_lag_gap_and_never_semantic_ready(self):
        self.append(event(2, "missing"))
        p = Projection()
        state = p.snapshot(self.journal, required_position=1)
        self.assertEqual(state["capture_state"], "NOT_READY")
        p.advance(self.journal)
        state = p.snapshot(self.journal, required_position=1)
        self.assertIn("CAPTURE_GAP:authored", state["reasons"])
        self.assertFalse(state["ledger_ready"])
        self.assertEqual(state["rows"], [])

    def test_multiple_stream_watermarks_and_missing_stream(self):
        self.append(event(run="a"))
        # Separate file/source for a second native stream.
        path = self.root / "b.jsonl"
        path.write_bytes(line(event(run="b")))
        TraceTailer(self.journal, "b-source", path).poll()
        p = replay(self.journal)
        state = p.snapshot(self.journal, required_position=2, streams={"a": 1, "b": 1})
        self.assertEqual(state["capture_state"], "PREFIX_AVAILABLE")
        self.assertFalse(state["ledger_ready"])
        self.assertEqual(state["atomic_status"], "UNAVAILABLE")
        self.assertIn("CAPTURE_GAP:missing", p.snapshot(self.journal, required_position=2,
                                                      streams={"missing": 1})["reasons"])
        self.assertEqual({r["run_id"] for r in p.rows(streams={"a": 1})}, {"a"})

    def test_source_issue_sticky_after_new_source_identity(self):
        self.append(event())
        self.path.write_bytes(b"")
        with self.assertRaises(CaptureError):
            TraceTailer(self.journal, "authored-source", self.path).poll()
        self.assertIn("SOURCE_CAPTURE_ISSUE", replay(self.journal).snapshot(
            self.journal, required_position=1)["reasons"])

    def test_service_restart_rebuild_and_unavailable_prefix(self):
        path = self.root / "service.sqlite"
        self.path.write_bytes(line(event()))
        service = CaptureService(path)
        service.ingest_trace("s", self.path)
        self.assertEqual(service.storage_snapshot(1)["capture_state"], "NOT_READY")
        service.project()
        rows = service.storage_snapshot(1)["rows"]
        service.close()
        service = CaptureService(path)
        try:
            service.project()
            self.assertEqual(service.storage_snapshot(1)["rows"], rows)
            with self.assertRaises(CaptureError):
                service.storage_snapshot(2)
        finally:
            service.close()

    def test_projection_is_bound_to_journal_and_rows_are_detached(self):
        self.append(event())
        p = replay(self.journal)
        before = canonical(p.rows())
        rows = p.rows()
        rows[0]["event"]["payload"]["output"] = "client mutation"
        self.assertEqual(canonical(p.rows()), before)
        other = Journal(self.root / "other.sqlite")
        try:
            with self.assertRaisesRegex(CaptureError, "another journal"):
                p.advance(other, 1)
            with self.assertRaisesRegex(CaptureError, "another journal"):
                p.snapshot(other, required_position=0)
        finally:
            other.close()

    def test_invalid_watermarks_and_projection_rewind_rejected(self):
        self.append(event())
        p = replay(self.journal)
        for streams in ({"authored": True}, {"authored": -1}, {"": 1}, ["authored"]):
            with self.subTest(streams=streams), self.assertRaises(CaptureError):
                p.snapshot(self.journal, required_position=1, streams=streams)
        for target in (0, "1", True, 2):
            with self.subTest(target=target), self.assertRaises(CaptureError):
                p.advance(self.journal, target)

    def test_incremental_reader_requests_only_unprojected_suffix(self):
        one = event()
        self.append(one)
        p = replay(self.journal)
        self.append(event(2, one["event_hash"]))
        actual = self.journal.events
        calls = []
        def record(through=None, *, after=0):
            calls.append((through, after))
            return actual(through, after=after)
        self.journal.events = record
        p.advance(self.journal)
        self.assertEqual(calls, [(2, 1)])
        self.assertEqual(canonical(p.rows()), canonical(replay(self.journal).rows()))


class StoredServiceTests(unittest.TestCase):
    """Authored public A example over temporary stores, never historical mapping."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "typed.sqlite"
        self.example = json.loads((Path(__file__).resolve().parents[1] /
                                   "continuous_verification/schemas/example.json").read_text("utf-8"))
        self.run = self.example["request"]["run_id"]
        self.actor = Principal("collector", frozenset({"configure", "collect", "verify", "read", "feedback"}),
                               frozenset({self.run, "other-run"}))
        self.backend = ServiceBackend(self.path, principal=self.actor, service_id="authored-service")
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: self.backend.close())
        self.setup_run(self.run)

    def setup_run(self, run, *, streams=None):
        streams = streams or [dict(stream_id="host", collector_id="collector", producer_id="authored-host",
                                   adapter_version="fixture-1", redaction_profile="authored-public")]
        self.backend.configure_run(run, streams)
        self.backend.execute("register_run", dict(run_id=run, registration_id="registration-1"))
        self.backend.install_policy(run, self.example["policy"])

    def ingest(self, events=None, *, run=None, batch="batch-1", hook=None):
        return self.backend.execute("ingest_events", dict(run_id=run or self.run, batch_id=batch,
                                    events=self.example["events"] if events is None else events), hook=hook)

    def coverage(self, *, run=None, stream="host", basis="event-2"):
        capabilities = copy.deepcopy(self.example["checkpoint"]["streams"][0]["capabilities"])
        for item in capabilities:
            item["basis_event_ids"] = [basis]
        self.backend.record_coverage(run or self.run, stream, capabilities)

    def checkpoint(self, *, revision=0, requested=3, run=None, streams=None):
        return self.backend.execute("checkpoint", dict(run_id=run or self.run, checkpoint_id="checkpoint-1",
                                    revision=revision, registry_revision=0,
                                    streams=streams or [dict(stream_id="host", requested=requested)]))

    def request(self, checkpoint, *, request_id="request-1"):
        request = copy.deepcopy(self.example["request"])
        request.update(run_id=checkpoint["run_id"], request_id=request_id)
        request["checkpoint"] = {key: checkpoint[key] for key in ("checkpoint_id", "revision")}
        request["checkpoint"]["digest"] = digest(checkpoint)
        return request

    def assertCode(self, code, operation, request):
        with self.assertRaises(ServiceError) as raised:
            self.backend.execute(operation, request)
        self.assertEqual(raised.exception.code, code)
        self.assertNotIn(str(self.root), str(raised.exception))

    def test_real_stored_reference_verify_restart_and_full_replay_parity(self):
        receipt = self.ingest()
        self.assertEqual([item["status"] for item in receipt["events"]], ["ACCEPTED"] * 3)
        self.coverage()
        checkpoint = self.checkpoint()
        self.assertEqual(checkpoint, self.example["checkpoint"])
        request = self.request(checkpoint)
        result = self.backend.execute("verify", request)
        self.assertEqual([finding["outcome"] for finding in result["findings"]], ["PASS", "PASS"])
        self.assertEqual(result, core_verify(request, checkpoint=checkpoint,
                                           events=self.example["events"], policy=self.example["policy"]))
        self.assertEqual(result["scope"], "declared_checks_at_checkpoint")
        self.backend.close()
        self.backend = ServiceBackend(self.path, principal=self.actor, service_id="authored-service")
        self.assertEqual(self.backend.execute("verify", request), result)
        self.assertEqual(self.backend.execute("get_assessment", dict(run_id=self.run,
                         assessment_id=result["assessment_id"])), result)
        self.assertEqual(self.backend.audit(), {"typed_events": 3, "procedural_records": 3})
        self.assertFalse(self.backend.execute("get_run_state", dict(run_id=self.run))["atomic_semantic_ready"])

    def test_untrusted_stream_coverage_policy_and_authority_fields_rejected(self):
        for operation, request in (
            ("register_run", dict(run_id=self.run, registration_id="r", streams=[])),
            ("checkpoint", dict(run_id=self.run, checkpoint_id="c", revision=0, registry_revision=0,
                                streams=[dict(stream_id="host", requested=0)], established_by="SERVICE_ESTABLISHED")),
            ("verify", {**self.example["request"], "policy_body": self.example["policy"]})):
            self.assertCode("INVALID_REQUEST", operation, request)

    def test_unknown_coverage_remains_inconclusive(self):
        self.ingest()
        result = self.backend.execute("verify", self.request(self.checkpoint()))
        self.assertEqual(result["status"], "ASSESSED")
        self.assertEqual({finding["outcome"] for finding in result["findings"]}, {"INCONCLUSIVE"})

    def test_lag_gap_late_repair_does_not_mutate_old_checkpoint(self):
        events = self.example["events"]
        self.ingest([events[0], events[2]])
        old = self.checkpoint()
        self.assertEqual(old["streams"][0]["gaps"], [[2, 2]])
        request = self.request(old)
        result = self.backend.execute("verify", request)
        self.assertEqual(result["status"], "CAPTURE_GAP")
        self.ingest([events[1]], batch="late-2")
        self.coverage()
        self.assertEqual(self.checkpoint(), old)
        self.assertEqual(self.backend.execute("verify", request), result)
        new = self.checkpoint(revision=1)
        self.assertEqual(self.backend.execute("verify", self.request(new, request_id="new-request"))["status"], "ASSESSED")

    def test_projection_lag_is_frozen_and_requires_new_checkpoint_revision(self):
        self.backend.project_on_ingest = False
        self.ingest()
        self.coverage()
        old = self.checkpoint()
        self.assertEqual(old["streams"][0]["projected_through"], 0)
        self.assertEqual(self.backend.execute("verify", self.request(old))["status"], "NOT_READY")
        self.backend.project(self.run)
        self.assertEqual(self.checkpoint(), old)
        new = self.checkpoint(revision=1)
        self.assertEqual(self.backend.execute("verify", self.request(new, request_id="after-project"))["status"], "ASSESSED")

    def test_late_event_never_enters_frozen_prefix(self):
        self.ingest(self.example["events"][:1])
        old = self.checkpoint(requested=3)
        result = self.backend.execute("verify", self.request(old))
        self.assertEqual(result["status"], "NOT_READY")
        self.ingest(self.example["events"][1:], batch="late")
        self.coverage()
        self.assertEqual(self.backend.execute("verify", self.request(old)), result)
        saved = self.backend._load(self.run, "checkpoint", "checkpoint-1", 0)
        self.assertEqual(saved["events"], self.example["events"][:1])
        self.backend.audit()

    def test_registered_idle_stream_cannot_be_omitted(self):
        config = [dict(stream_id=stream, collector_id="collector", producer_id="authored-host",
                       adapter_version="fixture-1", redaction_profile="authored-public") for stream in ("host", "idle")]
        self.setup_run("other-run", streams=config)
        self.assertCode("INVALID_REQUEST", "checkpoint", dict(run_id="other-run", checkpoint_id="c", revision=0,
                        registry_revision=0, streams=[dict(stream_id="host", requested=0)]))
        cp = self.checkpoint(run="other-run", streams=[dict(stream_id="host", requested=0), dict(stream_id="idle", requested=1)])
        request = self.request(cp)
        # Report in another run must be rejected before it can become evidence.
        self.assertEqual(self.backend.execute("verify", request)["status"], "NOT_READY")

    def test_batch_duplicate_and_collision_are_atomic(self):
        first = self.ingest()
        self.assertEqual(self.ingest(), first)
        dup = self.ingest(batch="second-transport")
        self.assertEqual({item["status"] for item in dup["events"]}, {"DUPLICATE"})
        changed = copy.deepcopy(self.example["events"][0])
        changed["content"] = "Changed authored bytes"
        changed["content_digest"] = text_digest(changed["content"])
        changed["origin"]["span"] = [0, len(changed["content"])]
        with self.assertRaises(ServiceError) as raised:
            self.ingest([changed], batch="collision")
        self.assertEqual(raised.exception.code, "CONFLICT")
        fresh = copy.deepcopy(self.example["events"][0])
        fresh.update(event_id="new-4", sequence=4)
        with self.assertRaises(ServiceError):
            self.ingest([fresh, changed], batch="atomic-fail")
        self.assertEqual(self.backend.audit()["typed_events"], 3)

    def test_source_report_and_proposal_identity_history_is_immutable(self):
        self.ingest()
        self.coverage()
        cp = self.checkpoint()
        request = self.request(cp)
        self.backend.execute("verify", request)
        changed = copy.deepcopy(request)
        changed["request_id"] = "different-request"
        changed["proposal"]["content"] = "Changed proposal"
        changed["proposal"]["content_digest"] = text_digest(changed["proposal"]["content"])
        self.assertCode("CONFLICT", "verify", changed)
        report = copy.deepcopy(self.example["events"][2])
        report.update(event_id="report-copy", sequence=4)
        report["payload"]["completion"] = "TRUNCATED"
        with self.assertRaises(ServiceError) as raised:
            self.ingest([report], batch="report-change")
        self.assertEqual(raised.exception.code, "CONFLICT")
        source = copy.deepcopy(self.example["events"][0])
        source.update(event_id="source-4", sequence=4, event_type="source")
        source["payload"] = dict(source_id="s", source_version="v", valid_at=None, retrieved_at=None, status="OK")
        self.ingest([source], batch="source")
        changed_source = copy.deepcopy(source)
        changed_source.update(event_id="source-5", sequence=5)
        changed_source["payload"]["status"] = "NO_DATA"
        with self.assertRaises(ServiceError) as raised:
            self.ingest([changed_source], batch="source-change")
        self.assertEqual(raised.exception.code, "CONFLICT")

    def test_foreign_nested_refs_denied_and_safe_errors(self):
        self.ingest()
        self.coverage()
        result = self.backend.execute("verify", self.request(self.checkpoint()))
        self.setup_run("other-run")
        self.assertCode("FORBIDDEN", "get_evidence", dict(run_id="other-run", event_id="event-1"))
        self.assertCode("FORBIDDEN", "get_assessment", dict(run_id="other-run", assessment_id=result["assessment_id"]))
        cp = self.checkpoint(run="other-run", requested=0)
        request = self.request(cp)
        self.assertCode("FORBIDDEN", "verify", request)
        event = copy.deepcopy(self.example["events"][0])
        event.update(run_id="other-run", event_id="foreign-parent", parents=["event-1"])
        with self.assertRaises(ServiceError) as raised:
            self.ingest([event], run="other-run", batch="foreign")
        self.assertEqual(raised.exception.code, "FORBIDDEN")
        missing = self.request(self.checkpoint(), request_id="missing-then-foreign")
        missing["proposal"].update(proposal_id="missing-proposal", report_event_id="later-foreign")
        old_result = self.backend.execute("verify", missing)
        old_view = self.backend.resolve_view(missing)
        foreign = copy.deepcopy(self.example["events"][0])
        foreign.update(run_id="other-run", event_id="later-foreign")
        self.ingest([foreign], run="other-run", batch="late-foreign")
        self.assertEqual(self.backend.execute("verify", missing), old_result)
        self.assertEqual(self.backend.resolve_view(missing), old_view)

    def test_denied_actor_wrong_producer_and_policy_mutation(self):
        stranger = ServiceBackend(self.path, principal=Principal("stranger", frozenset({"collect"}), frozenset({self.run})),
                                  service_id="authored-service")
        try:
            with self.assertRaises(ServiceError) as raised:
                stranger.execute("ingest_events", dict(run_id=self.run, batch_id="bad", events=self.example["events"]))
            self.assertEqual(raised.exception.code, "FORBIDDEN")
        finally:
            stranger.close()
        changed = copy.deepcopy(self.example["events"][0])
        changed["producer"]["id"] = "unassigned"
        with self.assertRaises(ServiceError) as raised:
            self.ingest([changed])
        self.assertEqual(raised.exception.code, "FORBIDDEN")
        policy = copy.deepcopy(self.example["policy"])
        policy["required_tool"] = "different-tool"
        with self.assertRaises(ServiceError) as raised:
            self.backend.install_policy(self.run, policy)
        self.assertEqual(raised.exception.code, "CONFLICT")

    def test_stale_digest_and_checkpoint_identity_conflict(self):
        self.ingest()
        cp = self.checkpoint()
        request = self.request(cp)
        request["policy"]["digest"] = "0" * 64
        self.assertCode("CONFLICT", "verify", request)
        request = self.request(cp)
        request["checkpoint"]["revision"] = 1
        self.assertCode("CONFLICT", "verify", request)
        self.assertCode("CONFLICT", "checkpoint", dict(run_id=self.run, checkpoint_id="checkpoint-1", revision=0,
                        registry_revision=0, streams=[dict(stream_id="host", requested=2)]))

    def test_cursor_pins_prefix_survives_restart_and_rejects_foreign(self):
        self.ingest()
        page = self.backend.execute("list_events", dict(run_id=self.run, after_cursor=None, limit=1))
        extra = copy.deepcopy(self.example["events"][0])
        extra.update(event_id="late-4", sequence=4)
        self.ingest([extra], batch="late")
        self.backend.close()
        self.backend = ServiceBackend(self.path, principal=self.actor, service_id="authored-service")
        next_page = self.backend.execute("list_events", dict(run_id=self.run, after_cursor=page["next_cursor"], limit=100))
        self.assertEqual([event["event_id"] for event in next_page["events"]], ["event-2", "event-3"])
        self.assertFalse(next_page["has_more"])
        self.assertIsNone(next_page["next_cursor"])
        self.setup_run("other-run")
        self.assertCode("FORBIDDEN", "list_events", dict(run_id="other-run", after_cursor=page["next_cursor"], limit=10))
        self.assertCode("INVALID_CURSOR", "list_events", dict(run_id=self.run, after_cursor="missing", limit=10))

    def test_typed_process_crash_before_after_commit_and_retry(self):
        authored = self.root / "typed-events.json"
        authored.write_text(json.dumps(self.example["events"]), encoding="utf-8")
        script = """
import json, os, sys
from continuous_verification.service import Principal, ServiceBackend
p = Principal('collector', frozenset({'collect'}), frozenset({'authored-run'}))
b = ServiceBackend(sys.argv[1], principal=p, service_id='authored-service')
def crash(stage):
    if stage == sys.argv[3]: os._exit(31)
b.execute('ingest_events', dict(run_id='authored-run', batch_id='batch-1',
          events=json.load(open(sys.argv[2], encoding='utf-8'))), hook=crash)
"""
        for stage, count in (("before_commit", 0), ("after_commit", 3)):
            result = subprocess.run([sys.executable, "-S", "-B", "-c", script, str(self.path), str(authored), stage],
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 31, result.stderr.decode())
            self.assertEqual(self.backend.audit()["typed_events"], count)
        receipt = self.ingest()
        self.assertEqual(len(receipt["events"]), 3)
        self.assertEqual(self.backend.audit()["typed_events"], 3)

    def test_cycle_error_is_retained_without_binding_or_pass(self):
        events = copy.deepcopy(self.example["events"])
        events[0]["parents"] = ["event-3"]
        self.ingest(events)
        self.coverage()
        result = self.backend.execute("verify", self.request(self.checkpoint()))
        self.assertEqual(result["status"], "ERROR")
        self.assertIsNone(result["binding"])
        self.assertEqual(result["findings"], [])
        self.assertIn("CAUSALITY", {issue["code"] for issue in result["issues"]})
        self.assertEqual(self.backend.execute("get_assessment", dict(run_id=self.run,
                         assessment_id=result["assessment_id"])), result)

    def test_evidence_spans_readiness_and_unsupported_feedback(self):
        self.ingest()
        evidence = self.backend.execute("get_evidence", dict(run_id=self.run, event_id="event-1", span=[0, 8]))
        self.assertEqual(evidence["excerpt"], "Authored")
        self.assertCode("INVALID_REQUEST", "get_evidence", dict(run_id=self.run, event_id="event-1", span=[-1, 2]))
        self.assertCode("UNSUPPORTED_OPERATION", "acknowledge_feedback", dict(run_id=self.run))
        self.assertCode("NOT_FOUND", "get_assessment", dict(run_id=self.run, assessment_id="missing"))

    def test_typed_corruption_detected(self):
        self.ingest()
        self.backend.db.execute("UPDATE cv_projection SET body='{}' WHERE position=1")
        with self.assertRaises(ServiceError) as raised:
            self.backend.audit()
        self.assertEqual(raised.exception.code, "BACKEND_UNAVAILABLE")

    def test_duplicate_batch_still_requires_assigned_collector(self):
        self.ingest()
        stranger = ServiceBackend(self.path, principal=Principal("stranger", frozenset({"collect"}), frozenset({self.run})),
                                  service_id="authored-service")
        try:
            with self.assertRaises(ServiceError) as raised:
                stranger.execute("ingest_events", dict(run_id=self.run, batch_id="batch-1", events=self.example["events"]))
            self.assertEqual(raised.exception.code, "FORBIDDEN")
        finally:
            stranger.close()

    def test_feedback_observation_binds_retained_proposal(self):
        self.ingest()
        self.coverage()
        result = self.backend.execute("verify", self.request(self.checkpoint()))
        feedback = copy.deepcopy(self.example["events"][0])
        feedback.update(event_id="ack-4", sequence=4, event_type="feedback_acknowledgement")
        feedback["payload"] = dict(assessment_id=result["assessment_id"], proposal_id="wrong-proposal",
                                   proposal_revision=0, related_event_ids=[])
        with self.assertRaises(ServiceError) as raised:
            self.ingest([feedback], batch="wrong-ack")
        self.assertEqual(raised.exception.code, "CONFLICT")
        feedback["payload"]["proposal_id"] = self.example["request"]["proposal"]["proposal_id"]
        self.ingest([feedback], batch="right-ack")
        self.assertEqual(self.backend.execute("get_assessment", dict(run_id=self.run,
                         assessment_id=result["assessment_id"])), result)

    def test_two_stream_fixed_prefix_does_not_infer_ingestion_causality(self):
        config = [dict(stream_id=stream, collector_id="collector", producer_id="authored-host",
                       adapter_version="fixture-1", redaction_profile="authored-public") for stream in ("input", "report")]
        self.setup_run("other-run", streams=config)
        events = copy.deepcopy(self.example["events"])
        for index, event in enumerate(events):
            event["run_id"] = "other-run"
            event["stream_id"] = "input" if index < 2 else "report"
            if index == 2:
                event["sequence"] = 1
        self.ingest([events[2], events[1], events[0]], run="other-run")
        self.coverage(run="other-run", stream="input")
        self.coverage(run="other-run", stream="report")
        cp = self.checkpoint(run="other-run", streams=[dict(stream_id="input", requested=2), dict(stream_id="report", requested=1)])
        result = self.backend.execute("verify", self.request(cp))
        self.assertEqual([item["outcome"] for item in result["findings"]], ["PASS", "PASS"])
        self.assertEqual(result, core_verify(self.request(cp), checkpoint=cp, events=events, policy=self.example["policy"]))

    def test_foreign_checkpoint_policy_and_coverage_basis_are_denied(self):
        self.ingest()
        self.coverage()
        cp = self.checkpoint()
        self.setup_run("other-run")
        request = self.request(cp)
        request["run_id"] = "other-run"
        self.assertCode("FORBIDDEN", "verify", request)
        with self.assertRaises(ServiceError) as raised:
            self.coverage(run="other-run")
        self.assertEqual(raised.exception.code, "FORBIDDEN")
        self.assertCode("INVALID_CURSOR", "list_events", dict(run_id=self.run, after_cursor=123, limit=10))

    def test_receipt_checkpoint_and_cursor_corruption_detected(self):
        self.ingest()
        cp = self.checkpoint()
        original = self.backend.db.execute("SELECT receipt FROM cv_batches").fetchone()[0]
        receipt = json.loads(original)
        receipt["events"][0]["status"] = "changed"
        self.backend.db.execute("UPDATE cv_batches SET receipt=?", (json.dumps(receipt),))
        with self.assertRaises(ServiceError):
            self.backend.audit()
        self.backend.db.execute("UPDATE cv_batches SET receipt=?", (original,))
        self.backend.audit()
        body = self.backend.db.execute("SELECT body FROM cv_objects WHERE kind='checkpoint'").fetchone()[0]
        saved = json.loads(body)
        saved["checkpoint"]["streams"][0]["capabilities"] = []
        self.backend.db.execute("UPDATE cv_objects SET body=? WHERE kind='checkpoint'", (json.dumps(saved),))
        with self.assertRaises(ServiceError):
            self.backend.audit()
        self.backend.db.execute("UPDATE cv_objects SET body=? WHERE kind='checkpoint'", (body,))
        self.backend.audit()
        page = self.backend.execute("list_events", dict(run_id=self.run, after_cursor=None, limit=1))
        self.backend.db.execute("UPDATE cv_cursors SET through=through+1")
        self.assertCode("INVALID_CURSOR", "list_events", dict(run_id=self.run, after_cursor=page["next_cursor"], limit=1))

    def test_host_resolve_view_is_exact_frozen_authorized_and_detached(self):
        self.ingest()
        self.coverage()
        cp = self.checkpoint()
        request = self.request(cp)
        result = self.backend.execute("verify", request)
        view = self.backend.resolve_view(request)
        self.assertEqual(set(view), {"checkpoint", "events", "policy"})
        self.assertTrue(binding_matches(result["binding"], request, **view))
        self.assertEqual(result, core_verify(request, **view))
        extra = copy.deepcopy(self.example["events"][0])
        extra.update(event_id="late-4", sequence=4)
        self.ingest([extra], batch="late")
        self.assertEqual(self.backend.resolve_view(request), view)
        view["events"][0]["payload"]["status"] = "ERROR"
        self.assertNotEqual(self.backend.resolve_view(request), view)
        reader = ServiceBackend(self.path, principal=Principal("reader", frozenset({"read"}), frozenset({self.run})),
                                service_id="authored-service")
        try:
            self.assertTrue(binding_matches(result["binding"], request, **reader.resolve_view(request)))
        finally:
            reader.close()
        denied = ServiceBackend(self.path, principal=Principal("denied", frozenset({"verify"}), frozenset({self.run})),
                                service_id="authored-service")
        try:
            with self.assertRaises(ServiceError) as raised:
                denied.resolve_view(request)
            self.assertEqual(raised.exception.code, "FORBIDDEN")
        finally:
            denied.close()
        foreign = copy.deepcopy(request)
        foreign["run_id"] = "other-run"
        self.setup_run("other-run")
        with self.assertRaises(ServiceError) as raised:
            self.backend.resolve_view(foreign)
        self.assertEqual(raised.exception.code, "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
