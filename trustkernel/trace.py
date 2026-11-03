"""Lossless observable-event JSONL after privacy filtering; SQLite is rebuildable."""
import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.callbacks import BaseCallbackHandler


def utc():
    return datetime.now(timezone.utc).isoformat()


def plain(value):
    if isinstance(value, type):
        if hasattr(value, 'model_json_schema'):
            return dict(schema_class=f'{value.__module__}.{value.__name__}', schema=value.model_json_schema())
        return f'{value.__module__}.{value.__name__}'
    if hasattr(value, "model_dump"):
        # LLMResult annotates generations/messages as base classes. Preserve
        # subclass fields such as AIMessage.tool_calls and usage_metadata.
        return plain(value.model_dump(serialize_as_any=True))
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def digest(value):
    return hashlib.sha256(json.dumps(plain(value), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Redactor:
    def __init__(self):
        self.secrets = sorted({v for k, v in os.environ.items()
                               if re.search(r'key|token|secret|password|credential', k, re.I)
                               and len(v) >= 6}, key=len, reverse=True)

    def clean(self, value):
        value = plain(value)
        if isinstance(value, dict):
            return {k: ("[REDACTED]" if re.search(
                r'api.?key|authorization|password|secret|private.?key|access.?token|refresh.?token|encrypted_content', k, re.I)
                else self.clean(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r'\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_\-]{12,}', '[REDACTED]', value)
            value = re.sub(r'(?i)Bearer\s+[^\s\"\']+', 'Bearer [REDACTED]', value)
            value = re.sub(r'(?i)(api[_-]?key|token|password|secret|signature)=([^&\s]+)', r'\1=[REDACTED]', value)
            value = re.sub(r'(https?://)[^/\s:@]+:[^/\s@]+@', r'\1[REDACTED]@', value)
            value = re.sub(r'\b0x[0-9a-fA-F]{64}\b', '[REDACTED_KEY_OR_HASH]', value)
        return value


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
 seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE, run_id TEXT, timestamp TEXT,
 kind TEXT, span_id TEXT, parent_id TEXT, payload_json TEXT, event_hash TEXT);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind);
CREATE INDEX IF NOT EXISTS events_span ON events(span_id);
"""


def index_event(db, event):
    db.execute('INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?)', (
        event['seq'], event['event_id'], event['run_id'], event['timestamp'], event['kind'],
        event['span_id'], event['parent_id'], json.dumps(event['payload'], ensure_ascii=False), event['event_hash']))


class Trace:
    def __init__(self, directory, run_id, metadata):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.run_id, self.metadata = run_id, metadata
        self.redactor = Redactor()
        self.lock = threading.RLock()
        self.seq, self.previous = 0, None
        self.raw = (self.directory / 'trace.jsonl').open('x', encoding='utf-8')
        self.console = (self.directory / 'console.log').open('x', encoding='utf-8')
        self.db = sqlite3.connect(self.directory / 'trace.sqlite', check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.execute('PRAGMA journal_mode=WAL')

    def emit(self, kind, payload, span_id=None, parent_id=None):
        with self.lock:
            cleaned = self.redactor.clean(payload)
            self.seq += 1
            event = dict(schema_version=1, seq=self.seq, event_id=str(uuid.uuid4()),
                         run_id=self.run_id, timestamp=utc(), kind=kind,
                         span_id=str(span_id) if span_id else None,
                         parent_id=str(parent_id) if parent_id else None,
                         context=self.metadata, payload=cleaned, previous_hash=self.previous)
            event['event_hash'] = digest(event)
            self.previous = event['event_hash']
            self.raw.write(json.dumps(event, ensure_ascii=False) + '\n')
            self.raw.flush()
            os.fsync(self.raw.fileno())
            index_event(self.db, event)
            self.db.commit()
            line = f"{event['timestamp']} [{self.run_id}] #{self.seq} {kind} {span_id or ''}"
            print(line, flush=True)
            self.console.write(line + '\n')
            self.console.flush()

    def artifact(self, name, value):
        (self.directory / name).write_text(json.dumps(self.redactor.clean(value), indent=2, ensure_ascii=False), encoding='utf-8')

    def close(self):
        self.db.close()
        self.raw.close()
        self.console.close()


class Observer(BaseCallbackHandler):
    raise_error = True
    run_inline = True

    def __init__(self, trace, before_llm=None, after_llm=None):
        self.trace, self.before_llm, self.after_llm = trace, before_llm, after_llm

    def event(self, kind, data, kwargs):
        self.trace.emit(kind, data, kwargs.get('run_id'), kwargs.get('parent_run_id'))

    def on_chat_model_start(self, serialized, messages, **kw):
        self.event('llm.start', dict(serialized=serialized, messages=messages, metadata=kw), kw)
        if self.before_llm:
            self.before_llm(messages, kw)

    def on_llm_start(self, serialized, prompts, **kw):
        self.event('llm.start', dict(serialized=serialized, prompts=prompts, metadata=kw), kw)
        if self.before_llm:
            self.before_llm(prompts, kw)

    def on_llm_end(self, response, **kw):
        self.event('llm.end', dict(response=response, metadata=kw), kw)
        if self.after_llm:
            self.after_llm(response, kw)

    def on_llm_error(self, error, **kw):
        self.event('llm.error', dict(error_type=type(error).__name__, error=str(error)), kw)

    def on_chain_start(self, serialized, inputs, **kw):
        self.event('step.start', dict(serialized=serialized, inputs=inputs, metadata=kw), kw)

    def on_chain_end(self, outputs, **kw):
        self.event('step.end', dict(outputs=outputs, metadata=kw), kw)

    def on_chain_error(self, error, **kw):
        self.event('step.error', dict(error_type=type(error).__name__, error=str(error)), kw)

    def on_tool_start(self, serialized, input_str, **kw):
        self.event('tool.start', dict(tool=serialized, input=input_str, metadata=kw), kw)

    def on_tool_end(self, output, **kw):
        self.event('tool.end', dict(output=output, metadata=kw), kw)

    def on_tool_error(self, error, **kw):
        self.event('tool.error', dict(error_type=type(error).__name__, error=str(error)), kw)


def rebuild(raw_path, db_path):
    with closing(sqlite3.connect(db_path)) as db, db:
        db.executescript(SCHEMA)
        previous = None
        for line in Path(raw_path).read_text(encoding='utf-8').splitlines():
            event = json.loads(line)
            saved = event.pop('event_hash')
            if digest(event) != saved or event['previous_hash'] != previous:
                raise ValueError('Trace hash chain invalid')
            event['event_hash'] = saved
            index_event(db, event)
            previous = saved
