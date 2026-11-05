"""Authored temporary native traces; no private corpus or native dependencies."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from continuous_verification.capture import TraceTailer
from continuous_verification.journal import CaptureError, Journal, sha


def event(seq=1, previous=None, run="authored", **updates):
    value = dict(schema_version=1, seq=seq, event_id=f"{run}-{seq}", run_id=run,
                 timestamp="2026-01-01T00:00:00Z", kind="tool.end", span_id="call-1",
                 parent_id=None, context={}, payload={"output": "Price 42. μ"}, previous_hash=previous)
    value.update(updates)
    value["event_hash"] = sha(json.dumps(value, sort_keys=True, ensure_ascii=False))
    return value


def line(value):
    return (json.dumps(value, ensure_ascii=False) + "\n").encode()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "trace.jsonl"
        self.dbpath = self.root / "journal.sqlite"
        self.journal = Journal(self.dbpath)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: self.journal.close())

    def poll(self, source="trace", **kwargs):
        return TraceTailer(self.journal, source, self.path).poll(**kwargs)

    def test_partial_line_and_restart(self):
        raw = line(event())
        self.path.write_bytes(raw[:-3])
        self.assertEqual(self.poll()["state"], "PARTIAL_LINE")
        self.assertEqual(self.journal.watermark(), 0)
        with self.path.open("ab") as stream:
            stream.write(raw[-3:])
        self.assertEqual(self.poll()["accepted_lines"], 1)
        self.journal.close()
        self.journal = Journal(self.dbpath)
        self.assertEqual(self.poll()["accepted_lines"], 0)
        self.assertEqual(self.journal.audit(), {"events": 1, "receipts": 1})

    def test_retry_duplicates_preserve_receipts(self):
        raw = line(event())
        self.path.write_bytes(raw + raw)
        self.assertEqual(self.poll()["accepted_lines"], 2)
        self.assertEqual(self.journal.audit(), {"events": 1, "receipts": 2})
        receipts = self.journal.db.execute("SELECT start,end,raw FROM receipts ORDER BY cursor").fetchall()
        self.assertEqual([(r[0], r[1], bytes(r[2])) for r in receipts],
                         [(0, len(raw), raw), (len(raw), 2 * len(raw), raw)])

    def test_identity_collisions_halt_without_ack(self):
        first = event()
        self.path.write_bytes(line(first) + line(event(payload={"output": "changed"})))
        with self.assertRaisesRegex(CaptureError, "collision"):
            self.poll()
        self.assertEqual(self.journal.source("trace")["offset"], len(line(first)))
        self.assertEqual(self.journal.watermark(), 1)
        self.assertEqual(len(self.journal.issues()), 1)

    def test_sequence_identity_collision_different_id(self):
        self.path.write_bytes(line(event()) + line(event(event_id="other")))
        with self.assertRaisesRegex(CaptureError, "collision"):
            self.poll()

    def test_crash_before_commit_and_after_commit_before_ack(self):
        self.path.write_bytes(line(event()))
        def before(stage):
            if stage == "before_commit":
                raise RuntimeError("authored crash")
        with self.assertRaises(RuntimeError):
            self.poll(hook=before)
        self.assertIsNone(self.journal.source("trace"))
        self.assertEqual(self.journal.watermark(), 0)
        def after(stage):
            if stage == "after_commit":
                raise RuntimeError("lost acknowledgement")
        with self.assertRaises(RuntimeError):
            self.poll(hook=after)
        self.journal.close()
        self.journal = Journal(self.dbpath)
        self.assertEqual(self.poll()["accepted_lines"], 0)
        self.assertEqual(self.journal.audit()["receipts"], 1)

    def test_rotation_truncation_and_same_size_rewrite_are_observable(self):
        raw = line(event())
        for mode in ("rotate", "truncate", "rewrite"):
            with self.subTest(mode=mode):
                self.path.write_bytes(raw)
                self.poll(mode)
                if mode == "rotate":
                    self.path.rename(self.root / "old-trace.jsonl")
                    self.path.write_bytes(raw)
                elif mode == "truncate":
                    self.path.write_bytes(b"")
                else:
                    self.path.write_bytes(raw.replace(b"Price", b"price"))
                with self.assertRaisesRegex(CaptureError, "SOURCE_"):
                    self.poll(mode)
                self.assertEqual(self.journal.source(mode)["offset"], len(raw))
        self.assertEqual(len(self.journal.issues()), 3)

    def test_gap_and_out_of_order_recovery_at_fixed_prefix(self):
        one = event()
        two = event(2, one["event_hash"])
        three = event(3, two["event_hash"])
        self.path.write_bytes(line(one) + line(three))
        self.poll()
        self.assertEqual(self.journal.stream_state()["authored"]["reasons"], ["SEQUENCE_GAP"])
        self.assertEqual(self.journal.stream_state()["authored"]["gap_ranges"], [[2, 2]])
        with self.path.open("ab") as stream:
            stream.write(line(two))
        self.poll()
        self.assertEqual(self.journal.stream_state()["authored"]["contiguous"], 3)
        self.assertEqual(self.journal.stream_state(2)["authored"]["contiguous"], 1)

    def test_hash_chain_mismatch_is_unready(self):
        self.path.write_bytes(line(event()) + line(event(2, "wrong")))
        self.poll()
        self.assertEqual(self.journal.stream_state()["authored"]["reasons"], ["SOURCE_CHAIN_MISMATCH"])

    def test_malformed_complete_line_and_bad_self_hash(self):
        for i, raw in enumerate((b"{bad}\n", b' {"seq":1,"seq":2}\n', line({**event(), "event_hash": "bad"}))):
            self.path.write_bytes(raw)
            with self.assertRaises(CaptureError):
                self.poll(str(i))
            self.assertIsNone(self.journal.source(str(i)))

    def test_receipt_and_event_tampering_rejected(self):
        self.path.write_bytes(line(event()))
        self.poll()
        self.journal.db.execute("UPDATE receipts SET raw=?", (line(event(payload={"output": "other"})),))
        with self.assertRaises(CaptureError):
            self.journal.audit()

    def test_missing_source_and_oversize_line(self):
        with self.assertRaises(OSError):
            self.poll()
        self.path.write_bytes(line(event()))
        with self.assertRaisesRegex(CaptureError, "LINE_TOO_LARGE"):
            TraceTailer(self.journal, "small", self.path, max_line_bytes=5).poll()

    def test_acknowledged_receipt_retry_cannot_rewind_or_change_bytes(self):
        one = event()
        two = event(2, one["event_hash"])
        raw = line(one)
        self.path.write_bytes(raw + line(two))
        self.poll()
        source = self.journal.source("trace")
        receipt = dict(source_id="trace", path=source["path"], identity=source["identity"],
                       start=0, end=len(raw), line=1, prefix_hash=sha(raw), raw=raw)
        self.journal.receive(**receipt)
        self.assertEqual(self.journal.source("trace"), source)
        changed = line(event(payload={"output": "Changed text"}))
        with self.assertRaisesRegex(CaptureError, "collision"):
            self.journal.receive(**{**receipt, "raw": changed, "end": len(changed)})
        self.assertEqual(self.journal.audit(), {"events": 2, "receipts": 2})

    def test_direct_storage_rejects_partial_receipt_and_schema_bool(self):
        raw = line(event())
        kwargs = dict(source_id="direct", path=str(self.path), identity="authored",
                      start=0, end=len(raw) - 1, line=1, prefix_hash=sha(raw[:-1]), raw=raw[:-1])
        with self.assertRaisesRegex(CaptureError, "complete-line"):
            self.journal.receive(**kwargs)
        self.path.write_bytes(line(event(schema_version=True)))
        with self.assertRaises(CaptureError):
            self.poll()

    def test_event_and_cursor_corruption_detected_on_audit(self):
        self.path.write_bytes(line(event()))
        self.poll()
        self.journal.db.execute("UPDATE events SET chain_hash='corrupted'")
        with self.assertRaisesRegex(CaptureError, "Journal chain"):
            self.journal.audit()
        self.journal.db.execute("UPDATE events SET chain_hash=?", (sha(json.dumps(
            [None, self.journal.db.execute('SELECT event_json FROM events').fetchone()[0]],
            ensure_ascii=False, sort_keys=True, separators=(',', ':'))),))
        self.journal.audit()
        self.journal.db.execute("UPDATE sources SET offset=offset+1")
        with self.assertRaisesRegex(CaptureError, "cursor"):
            self.journal.audit()

    def test_abrupt_process_exit_before_and_after_commit(self):
        self.path.write_bytes(line(event()))
        script = """
import os, sys
from continuous_verification.capture import TraceTailer
from continuous_verification.journal import Journal
journal = Journal(sys.argv[1])
def crash(stage):
    if stage == sys.argv[3]:
        os._exit(23)
TraceTailer(journal, 'process', sys.argv[2]).poll(hook=crash)
"""
        for stage, count in (("before_commit", 0), ("after_commit", 1)):
            with self.subTest(stage=stage):
                path = self.root / f"{stage}.sqlite"
                result = subprocess.run([sys.executable, "-S", "-B", "-c", script,
                                         str(path), str(self.path), stage], capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 23, result.stderr.decode())
                journal = Journal(path)
                try:
                    self.assertEqual(journal.audit()["events"], count)
                    self.assertEqual(TraceTailer(journal, "process", self.path).poll()["accepted_lines"], 1 - count)
                    self.assertEqual(journal.audit(), {"events": 1, "receipts": 1})
                finally:
                    journal.close()

    def test_existing_unrelated_sqlite_is_refused_without_changes(self):
        path = self.root / "historical-like.sqlite"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY)")
            db.execute("INSERT INTO events VALUES(1)")
        before = path.read_bytes()
        with self.assertRaisesRegex(CaptureError, "Not a continuous capture journal"):
            Journal(path)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(path.with_name(path.name + "-wal").exists())


if __name__ == "__main__":
    unittest.main()
