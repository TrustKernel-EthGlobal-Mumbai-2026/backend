"""Offline polling of explicitly supplied, already-redacted native Trace JSONL."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .journal import CaptureError


class TraceTailer:
    def __init__(self, journal, source_id, path, *, max_line_bytes=8 * 1024 * 1024):
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("Explicit source identity required")
        self.journal, self.source_id = journal, source_id
        self.path = Path(path).resolve()
        self.max_line_bytes = max_line_bytes

    def poll(self, *, hook=None):
        source = self.journal.source(self.source_id)
        offset, line = (source["offset"], source["line"]) if source else (0, 0)
        try:
            with self.path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                identity = f"{stat.st_dev}:{stat.st_ino}"
                if source and (source["identity"] != identity or source["path"] != str(self.path)):
                    raise CaptureError("SOURCE_ROTATED")
                if stat.st_size < offset:
                    raise CaptureError("SOURCE_TRUNCATED")
                digest = hashlib.sha256()
                remaining = offset
                while remaining:
                    block = stream.read(min(remaining, 1024 * 1024))
                    if not block:
                        raise CaptureError("SOURCE_TRUNCATED")
                    digest.update(block)
                    remaining -= len(block)
                if source and digest.hexdigest() != source["prefix_hash"]:
                    raise CaptureError("SOURCE_PREFIX_CHANGED")
                count = 0
                while True:
                    raw = stream.readline(self.max_line_bytes + 1)
                    if len(raw) > self.max_line_bytes:
                        raise CaptureError("LINE_TOO_LARGE")
                    if not raw or not raw.endswith(b"\n"):
                        return {"accepted_lines": count, "offset": offset,
                                "pending_bytes": len(raw), "state": "PARTIAL_LINE" if raw else "CAUGHT_UP"}
                    digest.update(raw)
                    self.journal.receive(source_id=self.source_id, path=str(self.path), identity=identity,
                                         start=offset, end=offset + len(raw), line=line + 1,
                                         prefix_hash=digest.hexdigest(), raw=raw, hook=hook)
                    offset, line, count = offset + len(raw), line + 1, count + 1
        except (CaptureError, OSError) as exc:
            self.journal.issue(self.source_id, "CAPTURE_BLOCKED", offset, str(exc))
            raise
