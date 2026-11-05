"""Supervised local capture and explicit A0.2 service calls on one SQLite owner.

No daemon, network, implicit semantic conversion or second persistence authority.
Native visible-text inventory and explicit typed host events stay distinct.
"""
from __future__ import annotations

import copy
import json
import math
from concurrent.futures import Future, TimeoutError as FutureTimeout
from pathlib import Path
import queue
import threading
import time

from .capture import TraceTailer
from .contracts import canonical_json
from .journal import CaptureError
from .projection import Projection
from .service import Principal, ServiceBackend


class AsyncCaptureError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class _BatchBoundary(Exception):
    pass


_OWNERS = set()
_OWNERS_LOCK = threading.Lock()


class AsyncTraceCapture:
    """Single-process supervised worker. All database work occurs in its thread.

    submit/execute accept the existing B operation DTOs, not arbitrary Python
    callbacks. configure/coverage methods retain existing host authorization.
    Timeouts are not acknowledgements: a running command may still commit.
    """
    def __init__(self, journal_path, source_id=None, trace_path=None, *, principal=None,
                 service_id="async-native-capture", poll_interval=0.1, batch_lines=32,
                 queue_size=16, project_on_poll=True, max_source_bytes=64*1024*1024,
                 max_line_bytes=1024*1024, failure_hook=None):
        if ((trace_path is None) != (source_id is None) or
                trace_path is not None and (not isinstance(source_id, str) or not source_id)):
            raise ValueError("Native trace path and explicit source identity must be supplied together")
        if not isinstance(poll_interval, (int, float)) or isinstance(poll_interval, bool) or not math.isfinite(poll_interval) or not 0.01 <= poll_interval <= 10:
            raise ValueError("Poll interval must be 0.01..10 seconds")
        for value, maximum in ((batch_lines, 1000), (queue_size, 256),
                               (max_source_bytes, 256*1024*1024), (max_line_bytes, 8*1024*1024)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("Invalid worker bound")
        self.journal_path = Path(journal_path).resolve()
        self.trace_path = Path(trace_path).resolve() if trace_path is not None else None
        if self.trace_path == self.journal_path:
            raise ValueError("Read-only trace and journal must be different files")
        self.source_id, self.principal = source_id, principal
        self.service_id, self.poll_interval = service_id, poll_interval
        self.batch_lines, self.project_on_poll = batch_lines, project_on_poll
        self.max_source_bytes, self.max_line_bytes = max_source_bytes, max_line_bytes
        self.failure_hook = failure_hook  # trusted authored recovery seam only
        self._queue = queue.Queue(queue_size)
        self._stop = threading.Event()
        self._started = threading.Event()
        self._done = threading.Event()
        self._state_lock = threading.Lock()
        self._last = None
        self._startup_error = None
        self._thread = None

    def start(self, timeout=5):
        if self._thread is not None:
            raise AsyncCaptureError("ALREADY_STARTED", "Create a new worker object to restart capture.")
        with _OWNERS_LOCK:
            if self.journal_path in _OWNERS:
                raise AsyncCaptureError("ALREADY_OWNED", "This process already owns the journal.")
            _OWNERS.add(self.journal_path)
        self._thread = threading.Thread(target=self._run, name="trustkernel-local-capture", daemon=False)
        try:
            self._thread.start()
        except BaseException:
            with _OWNERS_LOCK:
                _OWNERS.discard(self.journal_path)
            raise
        if not self._started.wait(timeout):
            self._stop.set()
            raise AsyncCaptureError("START_TIMEOUT", "Worker startup did not finish; stop and inspect it.")
        if self._startup_error:
            self._done.wait(timeout)
            raise AsyncCaptureError("START_FAILED", "The journal could not be opened or audited.")
        return self

    def _submit(self, command, payload):
        if self._thread is None or self._done.is_set() or self._stop.is_set():
            raise AsyncCaptureError("NOT_RUNNING", "The supervised worker is not running.")
        try:
            encoded = canonical_json(payload)
            if len(encoded.encode()) > 1024*1024:
                raise ValueError()
            payload = json.loads(encoded)
        except (ValueError, UnicodeError, RecursionError):
            raise AsyncCaptureError("INVALID_REQUEST", "Expected finite JSON control data of at most 1 MiB.") from None
        future = Future()
        try:
            self._queue.put_nowait((command, copy.deepcopy(payload), future))
        except queue.Full:
            raise AsyncCaptureError("QUEUE_FULL", "Worker control queue is full; no command was accepted.") from None
        return future

    @staticmethod
    def _wait(future, timeout):
        try:
            return future.result(timeout)
        except FutureTimeout:
            cancelled = future.cancel()
            raise AsyncCaptureError("COMMAND_TIMEOUT", "Command cancelled before execution." if cancelled else
                                    "Completion is unknown; retry the immutable request identity.") from None

    def submit(self, operation, request):
        """Explicit accepted A/B operation; future result follows actual commit."""
        return self._submit("execute", [operation, request])

    def execute(self, operation, request, *, timeout=2):
        return self._wait(self.submit(operation, request), timeout)

    def _host(self, method, args, timeout):
        return self._wait(self._submit("host", [method, list(args)]), timeout)

    def configure_run(self, run_id, streams, *, timeout=2):
        return self._host("configure_run", (run_id, streams), timeout)

    def install_policy(self, run_id, policy, *, timeout=2):
        return self._host("install_policy", (run_id, policy), timeout)

    def record_coverage(self, run_id, stream_id, observations, *, timeout=2):
        return self._host("record_coverage", (run_id, stream_id, observations), timeout)

    def resolve_view(self, request, *, timeout=2):
        return self._host("resolve_view", (request,), timeout)

    def snapshot(self, *, timeout=2, include_rows=False):
        if self._done.is_set():
            with self._state_lock:
                return copy.deepcopy(self._last)
        return self._wait(self._submit("snapshot", include_rows), timeout)

    def barrier(self, *, timeout=2, project=True):
        """One bounded native poll, not an unbounded drain/semantic checkpoint."""
        return self._wait(self._submit("barrier", project), timeout)

    def stop(self, timeout=5):
        self._stop.set()
        if self._thread is None:
            return None
        try:
            self._queue.put_nowait(("wake", None, None))
        except queue.Full:
            pass
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise AsyncCaptureError("STOP_TIMEOUT", "Worker still owns SQLite; retry stop before replacing it.")
        with self._state_lock:
            return copy.deepcopy(self._last)

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()

    def _poll(self, backend, projection, *, project):
        if self.trace_path is None or self._source_fault is not None:
            return
        committed = 0
        def boundary(stage):
            nonlocal committed
            if self.failure_hook:
                self.failure_hook(stage)
            if stage == "after_commit":
                committed += 1
                if self.trace_path.stat().st_size > self.max_source_bytes:
                    raise CaptureError("SOURCE_SIZE_LIMIT")
                if committed >= self.batch_lines:
                    raise _BatchBoundary()
        try:
            if self.trace_path.stat().st_size > self.max_source_bytes:
                raise CaptureError("SOURCE_SIZE_LIMIT")
            self._poll_result = TraceTailer(backend.journal, self.source_id, self.trace_path,
                                           max_line_bytes=self.max_line_bytes).poll(hook=boundary)
        except _BatchBoundary:
            self._poll_result = dict(state="BATCH_LIMIT", accepted_lines=committed, pending_bytes=None)
        except (CaptureError, OSError) as exc:
            code = str(exc)
            self._source_fault = code if isinstance(exc, CaptureError) and code in {
                "SOURCE_SIZE_LIMIT", "SOURCE_ROTATED", "SOURCE_TRUNCATED", "SOURCE_PREFIX_CHANGED", "LINE_TOO_LARGE"
            } else "INVALID_NATIVE_TRACE" if isinstance(exc, CaptureError) else "SOURCE_IO_UNAVAILABLE"
            source = backend.journal.source(self.source_id)
            backend.journal.issue(self.source_id, "ASYNC_SOURCE_FAULT", source["offset"] if source else 0,
                                  "Source identity, integrity, availability or configured bound failed")
            self._poll_result = dict(state="FAULT", accepted_lines=committed, pending_bytes=None)
        if project:
            projection.advance(backend.journal)

    def _snapshot(self, backend, projection, *, include_rows=False, lifecycle="RUNNING"):
        journal = backend.journal
        position = journal.watermark()
        streams = journal.stream_state(position)
        source = journal.source(self.source_id) if self.trace_path is not None else None
        offset = source["offset"] if source else 0
        unread = 0
        if self.trace_path is not None:
            try:
                unread = max(0, self.trace_path.stat().st_size-offset)
            except OSError:
                unread = None
        reasons = []
        if self._source_fault or journal.issues():
            reasons.append("SOURCE_CAPTURE_FAULT")
        if unread is None or unread > 0:
            reasons.append("NATIVE_SOURCE_PREFIX_LAG")
        if projection.position != position:
            reasons.append("NATIVE_PROJECTION_LAG")
        if any(state["reasons"] for state in streams.values()):
            reasons.append("NATIVE_STREAM_GAP_OR_CHAIN_MISMATCH")
        result = dict(lifecycle=lifecycle, owner_thread=threading.get_ident(),
            native_capture_configured=self.trace_path is not None,
            native_state="NOT_CONFIGURED" if self.trace_path is None else "NOT_READY" if reasons else "PREFIX_AVAILABLE",
            durable_offset=offset, durable_line=source["line"] if source else 0,
            durable_prefix_sha256=source["prefix_hash"] if source else None,
            journal_position=position, projected_position=projection.position, streams=streams,
            unread_bytes=unread, poll=copy.deepcopy(self._poll_result), reasons=reasons,
            source_fault=self._source_fault,
            atomic_status="UNAVAILABLE", ledger_ready=False, hidden_reasoning="UNAVAILABLE",
            typed_events="EXPLICIT_A0.2_HOST_INPUT_ONLY", rows=[], rows_state="NOT_REQUESTED")
        result["native_to_typed_mapping"] = "UNKNOWN_NOT_ASSERTED"
        if include_rows and not reasons:
            rows = projection.rows()
            if len(rows) <= 100 and len(json.dumps(rows, ensure_ascii=False).encode()) <= 1024*1024:
                result.update(rows=rows, rows_state="VISIBLE_INVENTORY_ONLY")
            else:
                result["rows_state"] = "SNAPSHOT_ROW_BOUND_EXCEEDED"
        elif include_rows:
            result["rows_state"] = "NOT_READY"
        with self._state_lock:
            self._last = copy.deepcopy(result)
        return result

    def _run(self):
        backend = None
        self._source_fault, self._poll_result = None, dict(state="NOT_POLLED")
        try:
            principal = self.principal or Principal("async-native-capture", frozenset(), frozenset())
            backend = ServiceBackend(self.journal_path, principal=principal, service_id=self.service_id)
            projection = Projection().advance(backend.journal)
            self._snapshot(backend, projection)
            self._started.set()
            next_poll = 0.0
            while not self._stop.is_set():
                if time.monotonic() >= next_poll:
                    self._poll(backend, projection, project=self.project_on_poll)
                    self._snapshot(backend, projection)
                    next_poll = time.monotonic()+self.poll_interval
                try:
                    command, payload, future = self._queue.get(timeout=max(0, next_poll-time.monotonic()))
                except queue.Empty:
                    continue
                if future is None or not future.set_running_or_notify_cancel():
                    continue
                try:
                    if command == "execute":
                        operation, request = payload
                        # Native inventory has no inferred binding to explicit
                        # typed checkpoints. Preserve accepted frozen semantics,
                        # including retained assessments and idempotent retries.
                        value = backend.execute(operation, request)
                    elif command == "host":
                        method, args = payload
                        if method not in ("configure_run", "install_policy", "record_coverage", "resolve_view"):
                            raise AsyncCaptureError("INVALID_REQUEST", "Unknown trusted host operation.")
                        value = getattr(backend, method)(*args)
                    elif command == "barrier":
                        self._poll(backend, projection, project=bool(payload))
                        value = self._snapshot(backend, projection)
                    else:
                        value = self._snapshot(backend, projection, include_rows=bool(payload))
                    future.set_result(copy.deepcopy(value))
                except Exception as exc:
                    future.set_exception(exc)
            self._snapshot(backend, projection, lifecycle="STOPPED")
        except BaseException as exc:
            self._startup_error = type(exc).__name__ if not self._started.is_set() else None
            with self._state_lock:
                self._last = dict(self._last or {}, lifecycle="FAILED", failure_type=type(exc).__name__,
                                  ledger_ready=False, atomic_status="UNAVAILABLE")
        finally:
            if backend is not None:
                backend.close()
            with _OWNERS_LOCK:
                _OWNERS.discard(self.journal_path)
            self._started.set()
            self._done.set()
            while True:
                try:
                    _, _, pending = self._queue.get_nowait()
                except queue.Empty:
                    break
                if pending is not None and pending.set_running_or_notify_cancel():
                    pending.set_exception(AsyncCaptureError("NOT_RUNNING", "Worker stopped before executing this command."))
