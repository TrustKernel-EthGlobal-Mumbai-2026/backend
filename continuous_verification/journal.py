"""Private storage mechanism for native Trace v1; not a public event contract.

SQLite (FULL synchronous commits) is the receipt and tail-cursor authority.
The original redacted source remains read-only; projections are rebuildable.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

STORAGE_VERSION = "native-receipt-journal-1"
APPLICATION_ID = 0x544B4331  # TKC1, stored in the SQLite header.


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


class CaptureError(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CaptureError("Duplicate JSON key")
        result[key] = value
    return result


def decode_trace(raw):
    """Validate only the producer's native envelope and self-hash."""
    try:
        event = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(CaptureError("Nonfinite JSON")))
        if not isinstance(event, dict):
            raise CaptureError("Trace event must be an object")
        if type(event.get("schema_version")) is not int or event["schema_version"] != 1 or type(event.get("seq")) is not int or event["seq"] < 1:
            raise CaptureError("Unsupported native trace envelope")
        for key in ("run_id", "event_id", "kind", "timestamp", "event_hash"):
            if not isinstance(event.get(key), str) or not event[key]:
                raise CaptureError("Missing trace identity")
        if not isinstance(event.get("payload"), dict) or "previous_hash" not in event:
            raise CaptureError("Missing trace payload/chain")
        body = {key: value for key, value in event.items() if key != "event_hash"}
        # Native Trace.digest uses default separators, unlike our storage hash.
        if sha(json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False)) != event["event_hash"]:
            raise CaptureError("Trace self-hash mismatch")
        return event
    except (UnicodeError, json.JSONDecodeError, TypeError, KeyError) as exc:
        raise CaptureError("Malformed trace line") from exc


class Journal:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if self.path.exists():
            # Inspect before changing journal mode or executing any DDL. Never
            # adopt a historical trace/index DB merely because its name matches.
            with self.path.open("rb") as stream:
                header = stream.read(100)
            if header[:16] != b"SQLite format 3\x00" or int.from_bytes(header[68:72], "big") != APPLICATION_ID:
                # Do not even open unrelated WAL databases through SQLite: a
                # read-only connection can otherwise create shared-memory files.
                raise CaptureError("Not a continuous capture journal")
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as existing:
                try:
                    row = existing.execute("SELECT value FROM metadata WHERE key='storage_version'").fetchone()
                except sqlite3.DatabaseError as exc:
                    raise CaptureError("Not a continuous capture journal") from exc
                if not row or row[0] != STORAGE_VERSION:
                    raise CaptureError("Unsupported capture storage version")
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              position INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
              run_id TEXT NOT NULL, seq INTEGER NOT NULL, event_json TEXT NOT NULL,
              chain_hash TEXT NOT NULL, UNIQUE(run_id,seq));
            CREATE TABLE IF NOT EXISTS sources (
              source_id TEXT PRIMARY KEY, path TEXT NOT NULL, identity TEXT NOT NULL,
              offset INTEGER NOT NULL, line INTEGER NOT NULL, prefix_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts (
              cursor INTEGER PRIMARY KEY, source_id TEXT NOT NULL, start INTEGER NOT NULL,
              end INTEGER NOT NULL, line INTEGER NOT NULL, position INTEGER NOT NULL,
              raw BLOB NOT NULL, chain_hash TEXT NOT NULL, UNIQUE(source_id,start));
            CREATE TABLE IF NOT EXISTS issues (
              id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, code TEXT NOT NULL,
              offset INTEGER NOT NULL, detail TEXT NOT NULL,
              UNIQUE(source_id,code,offset,detail));
        """)
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('storage_version',?)", (STORAGE_VERSION,))
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('journal_id',?)", (str(uuid.uuid4()),))
        self.identity = self.db.execute("SELECT value FROM metadata WHERE key='journal_id'").fetchone()[0]
        self.db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        # Persist the format marker before this journal can issue any receipts.
        self.db.execute("PRAGMA wal_checkpoint(FULL)")

    def close(self):
        self.db.close()

    def source(self, source_id):
        row = self.db.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
        return dict(row) if row else None

    def issue(self, source_id, code, offset, detail):
        self.db.execute("INSERT OR IGNORE INTO issues(source_id,code,offset,detail) VALUES(?,?,?,?)",
                        (source_id, code, offset, detail))

    def issues(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM issues ORDER BY id")]

    def receive(self, *, source_id, path, identity, start, end, line, prefix_hash, raw, hook=None):
        """Commit event, exact receipt and cursor together; return only after commit.

        hook is a failure-injection seam for authored recovery tests. An exception
        after_commit represents a lost acknowledgement; retry is safe.
        """
        if (type(start) is not int or start < 0 or type(end) is not int or
                type(line) is not int or line < 1 or not isinstance(raw, bytes) or
                not raw.endswith(b"\n") or end != start + len(raw)):
            raise CaptureError("Invalid complete-line receipt")
        event = decode_trace(raw)
        encoded = canonical(event)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            source = self.source(source_id)
            if source and (source["path"] != path or source["identity"] != identity):
                raise CaptureError("Source identity changed")
            receipt = self.db.execute("SELECT * FROM receipts WHERE source_id=? AND start=?",
                                      (source_id, start)).fetchone()
            if receipt:
                if bytes(receipt["raw"]) != raw or receipt["end"] != end or receipt["line"] != line:
                    raise CaptureError("Receipt identity collision")
                self.db.execute("COMMIT")
                return dict(receipt)
            if start != (source["offset"] if source else 0) or line != (source["line"] + 1 if source else 1):
                raise CaptureError("Noncontiguous source receipt")
            existing = self.db.execute("SELECT * FROM events WHERE event_id=? OR (run_id=? AND seq=?)",
                                       (event["event_id"], event["run_id"], event["seq"])).fetchall()
            if existing:
                if len(existing) != 1 or existing[0]["event_json"] != encoded:
                    raise CaptureError("Event identity collision")
                position = existing[0]["position"]
            else:
                last = self.db.execute("SELECT position,chain_hash FROM events ORDER BY position DESC LIMIT 1").fetchone()
                position = last["position"] + 1 if last else 1
                chain = sha(canonical([last["chain_hash"] if last else None, encoded]))
                self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",
                                (position, event["event_id"], event["run_id"], event["seq"], encoded, chain))
            last = self.db.execute("SELECT cursor,chain_hash FROM receipts ORDER BY cursor DESC LIMIT 1").fetchone()
            cursor = last["cursor"] + 1 if last else 1
            chain = sha(canonical([last["chain_hash"] if last else None, source_id, start, end,
                                   line, position, sha(raw)]))
            self.db.execute("INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?)",
                            (cursor, source_id, start, end, line, position, raw, chain))
            self.db.execute("INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?,?)",
                            (source_id, path, identity, end, line, prefix_hash))
            if hook:
                hook("before_commit")
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        if hook:
            hook("after_commit")
        return {"cursor": cursor, "position": position, "source_id": source_id, "end": end}

    def events(self, through=None, *, after=0):
        limit = self.watermark() if through is None else through
        if type(limit) is not int or limit < 0 or limit > self.watermark():
            raise CaptureError("Unavailable journal prefix")
        if type(after) is not int or after < 0 or after > limit:
            raise CaptureError("Invalid journal cursor")
        return [(row["position"], json.loads(row["event_json"])) for row in self.db.execute(
            "SELECT position,event_json FROM events WHERE position>? AND position<=? ORDER BY position", (after, limit))]

    def watermark(self):
        return self.db.execute("SELECT COALESCE(MAX(position),0) FROM events").fetchone()[0]

    def stream_state(self, through=None):
        streams = {}
        for _, event in self.events(through):
            streams.setdefault(event["run_id"], {})[event["seq"]] = event
        result = {}
        for run, events in sorted(streams.items()):
            contiguous, previous, reasons, gaps, mismatches = 0, None, [], [], []
            expected = 1
            for seq in sorted(events):
                if seq > expected:
                    gaps.append([expected, seq - 1])
                expected = seq + 1
                event = events[seq]
                predecessor = events.get(seq - 1)
                if (seq == 1 and event["previous_hash"] is not None or predecessor is not None and
                        event["previous_hash"] != predecessor["event_hash"]):
                    mismatches.append(seq)
                if seq == contiguous + 1 and event["previous_hash"] == previous:
                    contiguous, previous = seq, event["event_hash"]
            if gaps:
                reasons.append("SEQUENCE_GAP")
            if mismatches:
                reasons.append("SOURCE_CHAIN_MISMATCH")
            result[run] = {"observed": max(events), "contiguous": contiguous, "reasons": reasons,
                           "gap_ranges": gaps, "chain_mismatch_positions": mismatches}
        return result

    def audit(self):
        """Detect local journal corruption, including exact receipt bytes."""
        if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise CaptureError("SQLite integrity failure")
        previous = None
        for row in self.db.execute("SELECT * FROM events ORDER BY position"):
            event = decode_trace(row["event_json"].encode())
            if (event["event_id"], event["run_id"], event["seq"]) != (row["event_id"], row["run_id"], row["seq"]):
                raise CaptureError("Stored identity mismatch")
            previous = sha(canonical([previous, row["event_json"]]))
            if previous != row["chain_hash"]:
                raise CaptureError("Journal chain mismatch")
        previous = None
        for row in self.db.execute("SELECT * FROM receipts ORDER BY cursor"):
            event = decode_trace(bytes(row["raw"]))
            stored = self.db.execute("SELECT event_json FROM events WHERE position=?", (row["position"],)).fetchone()
            if not stored or canonical(event) != stored[0] or row["end"] - row["start"] != len(row["raw"]):
                raise CaptureError("Receipt binding mismatch")
            previous = sha(canonical([previous, row["source_id"], row["start"], row["end"], row["line"],
                                      row["position"], sha(bytes(row["raw"]))]))
            if previous != row["chain_hash"]:
                raise CaptureError("Receipt chain mismatch")
        for source in self.db.execute("SELECT * FROM sources"):
            rows = list(self.db.execute("SELECT * FROM receipts WHERE source_id=? ORDER BY start", (source["source_id"],)))
            offset, line, digest = 0, 0, hashlib.sha256()
            for row in rows:
                if row["start"] != offset or row["line"] != line + 1:
                    raise CaptureError("Source receipt gap")
                digest.update(row["raw"])
                offset, line = row["end"], row["line"]
            if (offset, line, digest.hexdigest()) != (source["offset"], source["line"], source["prefix_hash"]):
                raise CaptureError("Source cursor mismatch")
        return {"events": self.watermark(), "receipts": self.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]}
