"""Rebuildable visible-text inventory, explicitly short of an atomic ledger.

No matching a later source into an earlier model input. Input text is taken
only from its own captured envelope; no cross-event inferred exposure edges.
"""
from __future__ import annotations

import copy

from .journal import CaptureError, canonical, sha

VERSION = "native-visible-inventory-1"


def _strings(value, pointer):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _strings(item, pointer + "/" + str(i))


def _content(message, pointer):
    if not isinstance(message, dict):
        return
    content = message.get("content")
    if isinstance(content, str):
        yield pointer + "/content", content
    elif isinstance(content, list):
        for i, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") in ("text", "output_text") and isinstance(block.get("text"), str):
                yield pointer + f"/content/{i}/text", block["text"]


def _texts(event):
    payload = event["payload"]
    if event["kind"] == "llm.start":
        for pointer, text in _strings(payload.get("prompts"), "/payload/prompts"):
            yield "model_input", pointer, text
        messages = payload.get("messages", [])
        if isinstance(messages, list):
            for batch_i, batch in enumerate(messages):
                if isinstance(batch, list):
                    for msg_i, message in enumerate(batch):
                        for pointer, text in _content(message, f"/payload/messages/{batch_i}/{msg_i}"):
                            yield "model_input", pointer, text
    elif event["kind"] == "tool.end" and isinstance(payload.get("output"), str):
        yield "tool_return", "/payload/output", payload["output"]
    elif event["kind"] == "llm.end":
        response = payload.get("response", {})
        generations = response.get("generations", []) if isinstance(response, dict) else []
        if isinstance(generations, list):
            for batch_i, batch in enumerate(generations):
                if not isinstance(batch, list):
                    continue
                for gen_i, generation in enumerate(batch):
                    if isinstance(generation, dict):
                        prefix = f"/payload/response/generations/{batch_i}/{gen_i}"
                        message = generation.get("message")
                        if isinstance(message, dict):
                            for pointer, text in _content(message, prefix + "/message"):
                                yield "model_output", pointer, text
                        elif isinstance(generation.get("text"), str):
                            yield "model_output", prefix + "/text", generation["text"]


def project_event(position, event):
    rows = [{"id": "event:" + event["event_id"], "table": "events", "position": position,
             "run_id": event["run_id"], "seq": event["seq"], "event": event}]
    for role, pointer, text in _texts(event):
        identity = [event["event_id"], pointer, sha(text), VERSION]
        rows.append({"id": "text:" + sha(canonical(identity)), "table": "texts", "position": position,
                     "run_id": event["run_id"], "seq": event["seq"], "event_id": event["event_id"],
                     "pointer": pointer, "start": 0, "end": len(text), "text": text,
                     "text_sha256": sha(text), "role": role, "status": "VISIBLE_TEXT_ONLY"})
    return rows


class Projection:
    """In-memory incremental cache; restarting replays the authoritative journal."""
    def __init__(self):
        self.position = 0
        self._rows = []
        self.journal_identity = None

    def advance(self, journal, through=None):
        target = journal.watermark() if through is None else through
        if type(target) is not int:
            raise CaptureError("Invalid projection prefix")
        if target < self.position:
            raise CaptureError("Projection cannot rewind; use replay")
        if self.journal_identity not in (None, journal.identity):
            raise CaptureError("Projection belongs to another journal")
        events = journal.events(target, after=self.position)
        for position, event in events:
            self._rows.extend(project_event(position, event))
        self.position = target
        self.journal_identity = journal.identity
        return self

    def rows(self, *, streams=None):
        # Stream watermarks are optional storage filters, not public checkpoints.
        self._validate_streams(streams)
        return copy.deepcopy(sorted((row for row in self._rows if streams is None or
                                     row["run_id"] in streams and row["seq"] <= streams[row["run_id"]]),
                                    key=lambda row: (row["table"], row["id"])))

    @staticmethod
    def _validate_streams(streams):
        if streams is not None and (not isinstance(streams, dict) or any(
                not isinstance(run, str) or not run or type(seq) is not int or seq < 0
                for run, seq in streams.items())):
            raise CaptureError("Invalid stream watermarks")

    def snapshot(self, journal, *, required_position, streams=None):
        self._validate_streams(streams)
        if self.journal_identity not in (None, journal.identity):
            raise CaptureError("Projection belongs to another journal")
        if type(required_position) is not int or required_position < 0 or required_position > journal.watermark():
            raise CaptureError("Unavailable requested prefix")
        reasons = []
        if self.position != required_position:
            reasons.append("PROJECTION_PREFIX_MISMATCH")
        states = journal.stream_state(required_position)
        selected = states if streams is None else {run: states.get(run) for run in streams}
        for run, state in selected.items():
            required = state["observed"] if streams is None and state else (streams or {}).get(run, 0)
            if type(required) is not int or required < 0:
                raise CaptureError("Invalid stream watermark")
            if state is None or state["contiguous"] < required:
                reasons.append("CAPTURE_GAP:" + run)
        # Source faults are conservatively sticky. No operator-clear API yet.
        if journal.issues():
            reasons.append("SOURCE_CAPTURE_ISSUE")
        return {"projection_version": VERSION, "journal_position": required_position,
                "projected_position": self.position, "stream_state": selected,
                "capture_state": "NOT_READY" if reasons else "PREFIX_AVAILABLE",
                "reasons": reasons, "atomic_status": "UNAVAILABLE", "ledger_ready": False,
                "rows": self.rows(streams=streams) if not reasons else []}


def replay(journal, through=None):
    return Projection().advance(journal, through)
