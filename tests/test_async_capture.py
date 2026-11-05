"""Offline, newly authored logs/host events only; no private corpus or network."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from continuous_verification import binding_matches, digest
from continuous_verification.async_capture import AsyncCaptureError, AsyncTraceCapture
from continuous_verification.journal import Journal, sha
from continuous_verification.service import Principal, ServiceBackend, ServiceError
from tests.test_continuous_capture import event, line


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root/"trace.jsonl"
        self.path.write_bytes(b"")
        self.dbpath = self.root/"journal.sqlite"
        self.workers = []
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.stop_workers)

    def stop_workers(self):
        for worker in self.workers:
            worker.stop()

    def worker(self, **kwargs):
        native = kwargs.pop("native", True)
        worker = AsyncTraceCapture(self.dbpath, "authored-source" if native else None,
                                   self.path if native else None, poll_interval=0.01, **kwargs)
        self.workers.append(worker)
        return worker.start()

    def wait_for(self, worker, predicate):
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            try:
                state = worker.snapshot()
            except AsyncCaptureError as exc:
                if exc.code != "QUEUE_FULL":
                    raise
                threading.Event().wait(0.01)
                continue
            if predicate(state):
                return state
            threading.Event().wait(0.01)
        self.fail("Authored worker condition did not become observable")

    def test_growing_producer_log_updates_inventory_without_caller_poll(self):
        worker = self.worker()
        first = event(kind="llm.start", payload={"prompts": ["Visible authored input μ"]})
        self.path.write_bytes(line(first))
        state = self.wait_for(worker, lambda value: value["journal_position"] == 1)
        self.assertEqual(state["projected_position"], 1)
        self.assertEqual(state["durable_offset"], len(line(first)))
        self.assertEqual(state["durable_prefix_sha256"], sha(line(first)))
        self.assertNotEqual(state["owner_thread"], threading.get_ident())
        self.assertFalse(state["ledger_ready"])
        self.assertEqual(state["native_to_typed_mapping"], "UNKNOWN_NOT_ASSERTED")
        second = event(2, first["event_hash"])
        producer = threading.Thread(target=lambda: self.append(line(second)))
        producer.start(); producer.join()
        self.wait_for(worker, lambda value: value["journal_position"] == 2)
        rows = worker.snapshot(include_rows=True)
        self.assertEqual(rows["rows_state"], "VISIBLE_INVENTORY_ONLY")
        texts = [row["text"] for row in rows["rows"] if row["table"] == "texts"]
        self.assertIn("Visible authored input μ", texts)
        final = worker.stop()
        self.assertEqual(final["lifecycle"], "STOPPED")
        self.assertFalse(worker._thread.is_alive())

    def append(self, raw):
        with self.path.open("ab") as stream:
            stream.write(raw)

    def test_partial_line_and_projection_lag_are_not_complete_inventory(self):
        raw = line(event())
        self.path.write_bytes(raw[:-2])
        worker = self.worker(project_on_poll=False)
        state = worker.barrier(project=False)
        self.assertEqual(state["native_state"], "NOT_READY")
        self.assertEqual(state["durable_offset"], 0)
        self.assertEqual(state["poll"]["state"], "PARTIAL_LINE")
        self.append(raw[-2:])
        self.wait_for(worker, lambda value: value["journal_position"] == 1)
        state = worker.snapshot(include_rows=True)
        self.assertIn("NATIVE_PROJECTION_LAG", state["reasons"])
        self.assertEqual(state["rows"], [])
        state = worker.barrier()
        self.assertEqual(state["native_state"], "PREFIX_AVAILABLE")
        self.assertEqual(state["projected_position"], 1)
        self.assertFalse(state["ledger_ready"])

    def test_bounded_batch_duplicate_retry_and_restart_replay(self):
        first = event()
        second = event(2, first["event_hash"])
        self.path.write_bytes(line(first)+line(first)+line(second))
        worker = self.worker(batch_lines=1)
        self.wait_for(worker, lambda value: value["journal_position"] == 2)
        before = worker.snapshot(include_rows=True)["rows"]
        worker.stop()
        journal = Journal(self.dbpath)
        try:
            self.assertEqual(journal.audit(), {"events": 2, "receipts": 3})
        finally:
            journal.close()
        restart = self.worker()
        self.assertEqual(restart.barrier()["durable_line"], 3)
        self.assertEqual(restart.snapshot(include_rows=True)["rows"], before)

    def test_source_gap_is_visible_and_late_fill_changes_only_new_inventory(self):
        first = event()
        second = event(2, first["event_hash"])
        third = event(3, second["event_hash"])
        self.path.write_bytes(line(first)+line(third))
        worker = self.worker()
        old = self.wait_for(worker, lambda value: value["journal_position"] == 2)
        self.assertEqual(old["streams"]["authored"]["gap_ranges"], [[2, 2]])
        self.assertEqual(old["native_state"], "NOT_READY")
        self.append(line(second))
        self.wait_for(worker, lambda value: value["native_state"] == "PREFIX_AVAILABLE")
        self.assertEqual(old["streams"]["authored"]["gap_ranges"], [[2, 2]])
        self.assertFalse(old["ledger_ready"])

    def test_rotation_truncation_rewrite_and_line_limits_latch_fault(self):
        worker = self.worker()
        self.path.write_bytes(line(event()))
        self.wait_for(worker, lambda value: value["journal_position"] == 1)
        self.path.write_bytes(b"")
        state = self.wait_for(worker, lambda value: value["source_fault"] is not None)
        self.assertEqual(state["source_fault"], "SOURCE_TRUNCATED")
        self.path.write_bytes(line(event()))
        self.assertEqual(worker.barrier()["source_fault"], "SOURCE_TRUNCATED")
        worker.stop()
        # Separate newly authored store/identity for rotation control.
        self.dbpath = self.root/"rotation.sqlite"
        rotated = self.worker()
        self.wait_for(rotated, lambda value: value["journal_position"] == 1)
        self.path.rename(self.root/"rotated.jsonl")
        self.path.write_bytes(line(event()))
        self.assertEqual(self.wait_for(rotated, lambda value: value["source_fault"] is not None)["source_fault"], "SOURCE_ROTATED")

    def test_source_size_and_line_bounds_fail_without_receipt(self):
        self.path.write_bytes(line(event()))
        worker = self.worker(max_source_bytes=5)
        state = self.wait_for(worker, lambda value: value["source_fault"] is not None)
        self.assertEqual(state["source_fault"], "SOURCE_SIZE_LIMIT")
        self.assertEqual(state["durable_offset"], 0)
        worker.stop()
        self.dbpath = self.root/"line-limit.sqlite"
        worker = self.worker(max_line_bytes=5)
        self.assertEqual(self.wait_for(worker, lambda value: value["source_fault"] is not None)["source_fault"], "LINE_TOO_LARGE")

    def test_control_queue_full_timeout_cancel_and_owner_exclusion(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def hook(stage):
            if stage == "before_commit":
                entered.set(); release.wait(3)
        self.path.write_bytes(line(event()))
        worker = self.worker(queue_size=1, failure_hook=hook)
        self.assertTrue(entered.wait(2))
        pending = worker.submit("get_run_state", {"run_id": "authored"})
        with self.assertRaises(AsyncCaptureError) as raised:
            worker.snapshot()
        self.assertEqual(raised.exception.code, "QUEUE_FULL")
        with self.assertRaises(AsyncCaptureError) as raised:
            worker._wait(pending, 0.01)
        self.assertEqual(raised.exception.code, "COMMAND_TIMEOUT")
        self.assertTrue(pending.cancelled())
        duplicate = AsyncTraceCapture(self.dbpath)
        with self.assertRaises(AsyncCaptureError) as raised:
            duplicate.start()
        self.assertEqual(raised.exception.code, "ALREADY_OWNED")
        release.set()
        self.wait_for(worker, lambda value: value["journal_position"] == 1)
        with self.assertRaises(AsyncCaptureError):
            worker.submit("get_run_state", {"run_id": "authored", "oversize": "x"*(1024*1024)})

    def test_abrupt_worker_process_crash_before_after_commit_and_recovery(self):
        self.path.write_bytes(line(event()))
        script = """
import os,sys
from continuous_verification.async_capture import AsyncTraceCapture
def crash(stage):
    if stage==sys.argv[3]: os._exit(41)
w=AsyncTraceCapture(sys.argv[1],'authored-source',sys.argv[2],failure_hook=crash).start()
w.barrier(timeout=10)
"""
        for stage, expected in (("before_commit", 0), ("after_commit", 1)):
            self.dbpath = self.root/(stage+".sqlite")
            result = subprocess.run([sys.executable,"-S","-B","-c",script,str(self.dbpath),str(self.path),stage], capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 41, result.stderr.decode())
            journal = Journal(self.dbpath)
            try:
                self.assertEqual(journal.audit()["events"], expected)
            finally:
                journal.close()
            worker = self.worker()
            self.wait_for(worker, lambda value: value["journal_position"] == 1)
            worker.stop()
            journal = Journal(self.dbpath)
            try:
                self.assertEqual(journal.audit(), {"events":1,"receipts":1})
            finally:
                journal.close()


class TypedWorkerTests(unittest.TestCase):
    stop_workers = WorkerTests.stop_workers
    worker = WorkerTests.worker
    wait_for = WorkerTests.wait_for
    append = WorkerTests.append

    def setUp(self):
        WorkerTests.setUp(self)
        self.example = json.loads((Path(__file__).resolve().parents[1]/
                                   "continuous_verification/schemas/example.json").read_text("utf-8"))
        self.run = self.example["request"]["run_id"]
        self.actor = Principal("collector", frozenset({"configure","collect","read","verify"}), frozenset({self.run}))

    def configured(self, *, native=True):
        worker = self.worker(native=native, principal=self.actor, service_id="authored-service")
        worker.configure_run(self.run, [dict(stream_id="host", collector_id="collector", producer_id="authored-host",
                              adapter_version="fixture-1", redaction_profile="authored-public")])
        worker.execute("register_run", dict(run_id=self.run, registration_id="registration-1"))
        worker.install_policy(self.run, self.example["policy"])
        return worker

    def ingest(self, worker, events=None, batch="authored-batch"):
        return worker.submit("ingest_events", dict(run_id=self.run, batch_id=batch,
                             events=self.example["events"] if events is None else events))

    def checkpoint(self, worker, revision=0):
        return worker.execute("checkpoint", dict(run_id=self.run, checkpoint_id="checkpoint-1",revision=revision,
                              registry_revision=0, streams=[dict(stream_id="host", requested=3)]))

    def request(self, checkpoint, request_id="request-1"):
        request = copy.deepcopy(self.example["request"])
        request["request_id"] = request_id
        request["checkpoint"] = dict(checkpoint_id=checkpoint["checkpoint_id"], revision=checkpoint["revision"],
                                     digest=digest(checkpoint))
        return request

    def test_explicit_typed_futures_sdk_and_native_producer_share_one_owner(self):
        from continuous_verification.sdk import Client, Access
        worker = self.configured()
        self.path.write_bytes(line(event()))
        future = self.ingest(worker)
        receipt = future.result(2)
        self.assertEqual([item["status"] for item in receipt["events"]], ["ACCEPTED"]*3)
        worker.record_coverage(self.run, "host", self.example["checkpoint"]["streams"][0]["capabilities"])
        request = self.request(self.checkpoint(worker))
        client = Client(backend=worker, access=Access(frozenset({"verify","read"}), frozenset({self.run})))
        response = client.call("verify", request)
        self.assertTrue(response["ok"])
        self.assertEqual([item["outcome"] for item in response["result"]["findings"]], ["PASS","PASS"])
        self.assertTrue(binding_matches(response["result"]["binding"], request, **worker.resolve_view(request)))
        state = self.wait_for(worker, lambda value: value["journal_position"] == 1)
        self.assertFalse(state["ledger_ready"])
        self.assertEqual(state["typed_events"], "EXPLICIT_A0.2_HOST_INPUT_ONLY")
        worker.stop()
        backend = ServiceBackend(self.dbpath, principal=self.actor, service_id="authored-service")
        try:
            self.assertEqual(backend.journal.audit()["events"], 1)
            self.assertEqual(backend.audit()["typed_events"], 3)
            self.assertEqual(backend.execute("verify", request), response["result"])
        finally:
            backend.close()

    def test_frozen_typed_assessment_survives_late_native_partial_and_source_fault(self):
        worker = self.configured()
        self.ingest(worker).result(2)
        worker.record_coverage(self.run, "host", self.example["checkpoint"]["streams"][0]["capabilities"])
        checkpoint = self.checkpoint(worker)
        request = self.request(checkpoint)
        result = worker.execute("verify", request)
        self.append(b'{"pending_native_line":')
        native = worker.barrier()
        self.assertEqual(native["native_state"], "NOT_READY")
        self.assertFalse(native["ledger_ready"])
        self.assertEqual(worker.execute("verify", request), result)
        self.assertEqual(self.checkpoint(worker), checkpoint)
        self.assertEqual(worker.execute("get_assessment", dict(run_id=self.run, assessment_id=result["assessment_id"])), result)
        self.assertTrue(binding_matches(result["binding"], request, **worker.resolve_view(request)))
        self.append(b"broken}\n")
        self.wait_for(worker, lambda value: value["source_fault"] is not None)
        self.assertEqual(worker.execute("verify", request), result)

    def test_typed_gap_and_lag_never_pass_late_event_requires_new_checkpoint(self):
        worker = self.configured(native=False)
        events = self.example["events"]
        self.ingest(worker, [events[0],events[2]]).result(2)
        old_cp = self.checkpoint(worker)
        old_request = self.request(old_cp)
        old = worker.execute("verify", old_request)
        self.assertEqual(old["status"], "CAPTURE_GAP")
        self.assertEqual({finding["outcome"] for finding in old["findings"]}, {"INCONCLUSIVE"})
        self.ingest(worker, [events[1]], batch="late-event").result(2)
        worker.record_coverage(self.run, "host", self.example["checkpoint"]["streams"][0]["capabilities"])
        self.assertEqual(self.checkpoint(worker), old_cp)
        self.assertEqual(worker.execute("verify", old_request), old)
        new = worker.execute("verify", self.request(self.checkpoint(worker, revision=1), "new-request"))
        self.assertEqual({finding["outcome"] for finding in new["findings"]}, {"PASS"})
        self.assertEqual(worker.snapshot()["native_state"], "NOT_CONFIGURED")

    def test_ingest_future_ack_waits_for_real_commit_and_lost_ack_retry_is_exact(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        owner_ids = []
        class DelayedBackend(ServiceBackend):
            def _ingest(backend, request, hook):
                owner_ids.append(threading.get_ident())
                def pause(stage):
                    if stage == "after_commit":
                        entered.set(); release.wait(3)
                return super()._ingest(request, pause)
        with patch("continuous_verification.async_capture.ServiceBackend", DelayedBackend):
            worker = self.configured(native=False)
            future = self.ingest(worker)
            self.assertTrue(entered.wait(2))
            self.assertFalse(future.done())
            with self.assertRaises(AsyncCaptureError) as raised:
                worker._wait(future, 0.01)
            self.assertEqual(raised.exception.code, "COMMAND_TIMEOUT")
            self.assertFalse(future.cancelled())  # already executing/committed, completion unknown
            release.set()
            receipt = future.result(2)
            self.assertEqual(self.ingest(worker).result(2), receipt)
            self.assertTrue(all(owner != threading.get_ident() for owner in owner_ids))
            worker.stop()
        backend = ServiceBackend(self.dbpath, principal=self.actor, service_id="authored-service")
        try:
            self.assertEqual(backend.audit()["typed_events"], 3)
        finally:
            backend.close()

    def test_default_principal_does_not_grant_sdk_capture_or_policy_authority(self):
        worker = self.worker(native=False)
        with self.assertRaises(ServiceError) as raised:
            worker.configure_run(self.run, [])
        self.assertEqual(raised.exception.code, "FORBIDDEN")
        with self.assertRaises(ServiceError) as raised:
            self.ingest(worker).result(2)
        self.assertEqual(raised.exception.code, "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
