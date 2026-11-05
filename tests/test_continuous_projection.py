"""Prefix/replay tests over temporary authored trace inputs only."""
import tempfile
import unittest
from pathlib import Path

from continuous_verification.capture import TraceTailer
from continuous_verification.journal import CaptureError, Journal, canonical
from continuous_verification.projection import Projection, replay
from continuous_verification.service import CaptureService
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


if __name__ == "__main__":
    unittest.main()
