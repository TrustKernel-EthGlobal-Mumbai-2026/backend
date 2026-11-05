"""Native storage facade and trusted local, stored-reference typed-event backend.

Typed events bind accepted continuous-verification-0.2. Native inventory is
never silently translated into assembled inputs, reports or capture coverage.
"""
import json
from contextlib import contextmanager
from dataclasses import dataclass

from .capture import TraceTailer
from .journal import Journal
from .projection import Projection
from .contracts import (CONTRACT_VERSION, ContractError, canonical_json, digest,
                        validate_event, validate_checkpoint, validate_request,
                        validate_policy, validate_result)
from .verifier import verify as core_verify


class CaptureService:
    def __init__(self, journal_path):
        self.journal = Journal(journal_path)
        try:
            self.journal.audit()
        except BaseException:
            self.journal.close()
            raise
        self.projection = Projection()

    def ingest_trace(self, source_id, path):
        return TraceTailer(self.journal, source_id, path).poll()

    def project(self, through=None):
        self.projection.advance(self.journal, through)

    def storage_snapshot(self, required_position, streams=None):
        return self.projection.snapshot(self.journal, required_position=required_position, streams=streams)

    def close(self):
        self.journal.close()


class ServiceError(ValueError):
    """Allowlisted public error. Never contains a local path or request content."""
    def __init__(self, code, public_message, issues=()):
        self.code, self.public_message = code, public_message
        # An unknown JSON key can occur inside a validator's path; do not echo
        # arbitrary client-controlled key text into public diagnostics.
        self.issues = [{"path": "$", "code": item["code"][:64]} for item in list(issues)[:32]]
        super().__init__(public_message)


@dataclass(frozen=True)
class Principal:
    actor_id: str
    permissions: frozenset[str]
    run_ids: frozenset[str]


_PERMISSIONS = {"register_run": "collect", "ingest_events": "collect", "checkpoint": "collect",
                "verify": "verify", "get_assessment": "read", "get_evidence": "read",
                "get_run_state": "read", "list_events": "read", "acknowledge_feedback": "feedback"}
_CAPABILITIES = ("phase_boundaries", "report_completion", "model_input", "tool_lifecycle")
_STREAM_KEYS = {"stream_id", "collector_id", "producer_id", "adapter_version", "redaction_profile"}


def _error(code, message):
    raise ServiceError(code, message)


def _keys(value, required, optional=()):
    if type(value) is not dict or set(value) - set(required) - set(optional) or not set(required) <= set(value):
        _error("INVALID_REQUEST", "Unexpected or missing request fields.")


def _text(value):
    if type(value) is not str or not value or len(value) > 256:
        _error("INVALID_REQUEST", "Expected a bounded nonempty identifier.")
    return value


def _integer(value):
    if type(value) is not int or value < 0:
        _error("INVALID_REQUEST", "Expected a nonnegative integer.")
    return value


class ServiceBackend:
    """Local single-worker backend; host injects grants, collectors and policies.

    A typed procedural projection is synchronous by default, in the receipt
    transaction. Disable project_on_ingest for explicit host-worker lag/recovery.
    No transport authentication or complete semantic ledger is claimed.
    """
    def __init__(self, journal_path, *, principal, service_id, project_on_ingest=True):
        if not isinstance(principal, Principal) or not principal.actor_id:
            _error("FORBIDDEN", "A trusted principal is required.")
        _text(service_id)
        self.principal, self.service_id = principal, service_id
        self.project_on_ingest = project_on_ingest
        self.journal = Journal(journal_path)
        self.db = self.journal.db
        try:
            self.journal.audit()
        except BaseException:
            self.close()
            raise
        row = self.db.execute("SELECT value FROM metadata WHERE key='typed_service_version'").fetchone()
        if row and row[0] != "typed-service-0.2-1":
            self.close()
            _error("BACKEND_UNAVAILABLE", "Unsupported typed service storage version.")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS cv_runs(run TEXT PRIMARY KEY, config TEXT NOT NULL, registration TEXT);
          CREATE TABLE IF NOT EXISTS cv_coverage(run TEXT, stream TEXT, body TEXT NOT NULL, PRIMARY KEY(run,stream));
          CREATE TABLE IF NOT EXISTS cv_events(position INTEGER PRIMARY KEY, run TEXT NOT NULL,
            event_id TEXT NOT NULL, stream TEXT NOT NULL, seq INTEGER NOT NULL, body TEXT NOT NULL,
            UNIQUE(run,event_id), UNIQUE(run,stream,seq));
          CREATE TABLE IF NOT EXISTS cv_event_chain(position INTEGER PRIMARY KEY, chain_hash TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS cv_projection(position INTEGER PRIMARY KEY, run TEXT NOT NULL,
            event_id TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(run,event_id));
          CREATE TABLE IF NOT EXISTS cv_objects(run TEXT NOT NULL, kind TEXT NOT NULL,
            id TEXT NOT NULL, revision TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(run,kind,id,revision));
          CREATE TABLE IF NOT EXISTS cv_batches(run TEXT, id TEXT, request TEXT NOT NULL,
            receipt TEXT NOT NULL, PRIMARY KEY(run,id));
          CREATE TABLE IF NOT EXISTS cv_batch_chain(position INTEGER PRIMARY KEY, run TEXT, id TEXT,
            chain_hash TEXT NOT NULL, UNIQUE(run,id));
          CREATE TABLE IF NOT EXISTS cv_object_chain(position INTEGER PRIMARY KEY, run TEXT, kind TEXT,
            id TEXT, revision TEXT, chain_hash TEXT NOT NULL, UNIQUE(run,kind,id,revision));
          CREATE TABLE IF NOT EXISTS cv_cursors(id TEXT PRIMARY KEY, run TEXT NOT NULL, snapshot TEXT NOT NULL,
            through INTEGER NOT NULL, after_position INTEGER NOT NULL);
        """)
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES('typed_service_version','typed-service-0.2-1')")
        try:
            self.audit()
        except BaseException:
            self.close()
            raise

    def close(self):
        self.journal.close()

    @contextmanager
    def _transaction(self, hook=None):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            if hook:
                hook("before_commit")
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        if hook:
            hook("after_commit")

    def _authorize(self, run, permission):
        _text(run)
        if permission not in self.principal.permissions or run not in self.principal.run_ids:
            _error("FORBIDDEN", "Operation or run is not permitted.")

    def _run(self, run, *, active=True):
        row = self.db.execute("SELECT * FROM cv_runs WHERE run=?", (run,)).fetchone()
        if not row:
            _error("NOT_FOUND", "Run is not configured.")
        if active and row["registration"] is None:
            _error("BACKEND_UNAVAILABLE", "Run is not registered.")
        return json.loads(row["config"])

    def _collector(self, config, stream):
        binding = next((item for item in config if item["stream_id"] == stream), None)
        if not binding or binding["collector_id"] != self.principal.actor_id:
            _error("FORBIDDEN", "Collector is not assigned to the stream.")
        return binding

    def configure_run(self, run_id, streams):
        """Operator-only, host API. Initial registered set is immutable."""
        self._authorize(run_id, "configure")
        if type(streams) is not list or not streams:
            _error("INVALID_REQUEST", "A complete registered stream set is required.")
        seen = set()
        for item in streams:
            _keys(item, _STREAM_KEYS)
            for value in item.values():
                _text(value)
            if item["stream_id"] in seen:
                _error("INVALID_REQUEST", "Duplicate registered stream.")
            seen.add(item["stream_id"])
        config = canonical_json(sorted(streams, key=lambda item: item["stream_id"]))
        with self._transaction():
            old = self.db.execute("SELECT config FROM cv_runs WHERE run=?", (run_id,)).fetchone()
            if old and old[0] != config:
                _error("CONFLICT", "Registered stream configuration is immutable.")
            self.db.execute("INSERT OR IGNORE INTO cv_runs VALUES(?,?,NULL)", (run_id, config))

    def _put(self, run, kind, identity, revision, value):
        body = canonical_json(value)
        old = self.db.execute("SELECT body FROM cv_objects WHERE run=? AND kind=? AND id=? AND revision=?",
                              (run, kind, identity, str(revision))).fetchone()
        if old and old[0] != body:
            _error("CONFLICT", "Immutable identity has different content.")
        if old:
            return
        self.db.execute("INSERT OR IGNORE INTO cv_objects VALUES(?,?,?,?,?)",
                        (run, kind, identity, str(revision), body))
        previous = self.db.execute("SELECT chain_hash FROM cv_object_chain ORDER BY position DESC LIMIT 1").fetchone()
        chain = digest([previous[0] if previous else None, run, kind, identity, str(revision), body])
        self.db.execute("INSERT INTO cv_object_chain(run,kind,id,revision,chain_hash) VALUES(?,?,?,?,?)",
                        (run, kind, identity, str(revision), chain))

    def _load(self, run, kind, identity, revision="0"):
        _text(identity)
        row = self.db.execute("SELECT body FROM cv_objects WHERE run=? AND kind=? AND id=? AND revision=?",
                              (run, kind, identity, str(revision))).fetchone()
        if row:
            return json.loads(row[0])
        if self.db.execute("SELECT 1 FROM cv_objects WHERE run=? AND kind=? AND id=?", (run, kind, identity)).fetchone():
            _error("CONFLICT", "Referenced object revision is not stored.")
        if self.db.execute("SELECT 1 FROM cv_objects WHERE kind=? AND id=?", (kind, identity)).fetchone():
            _error("FORBIDDEN", "Referenced object is not available in this run.")
        _error("NOT_FOUND", "Referenced object was not found.")

    def _event(self, run, event_id, *, required=True):
        _text(event_id)
        row = self.db.execute("SELECT body FROM cv_events WHERE run=? AND event_id=?", (run, event_id)).fetchone()
        if row:
            return json.loads(row[0])
        if self.db.execute("SELECT 1 FROM cv_events WHERE event_id=?", (event_id,)).fetchone():
            _error("FORBIDDEN", "Referenced event is not available in this run.")
        if required:
            _error("NOT_FOUND", "Referenced event was not found.")
        return None

    def install_policy(self, run_id, policy):
        self._authorize(run_id, "configure")
        self._run(run_id, active=False)
        self._validate(validate_policy, policy)
        with self._transaction():
            self._put(run_id, "policy", policy["policy_id"], policy["version"], policy)

    @staticmethod
    def _validate(validator, value):
        try:
            validator(value)
        except ContractError as exc:
            raise ServiceError("INVALID_REQUEST", "Accepted contract validation failed.", exc.issues) from None

    def record_coverage(self, run_id, stream_id, observations):
        """Trusted collector observations only; never called by execute."""
        self._authorize(run_id, "collect")
        config = self._run(run_id)
        self._collector(config, stream_id)
        checkpoint = self._checkpoint_shape(run_id, "coverage-validation", 0, [dict(
            stream_id=stream_id, requested=0, ingested_through=0, projected_through=0,
            gaps=[], capabilities=observations)])
        self._validate(validate_checkpoint, checkpoint)
        with self._transaction():
            for capability in observations:
                if capability["state"] == "CAPTURED" and not capability["basis_event_ids"]:
                    _error("INVALID_REQUEST", "Captured coverage needs retained basis events.")
                for event_id in capability["basis_event_ids"]:
                    self._event(run_id, event_id)
            self.db.execute("INSERT OR REPLACE INTO cv_coverage VALUES(?,?,?)",
                            (run_id, stream_id, canonical_json(observations)))

    def project(self, run_id):
        self._authorize(run_id, "collect")
        config = self._run(run_id)
        for stream in config:
            self._collector(config, stream["stream_id"])
        with self._transaction():
            self._project(run_id)

    def _project(self, run):
        # Accepted typed records retain exact content, origin spans and lifecycle
        # fields; no text mining or complete semantic decomposition is inferred.
        self.db.execute("INSERT OR IGNORE INTO cv_projection SELECT position,run,event_id,body FROM cv_events WHERE run=?", (run,))

    @staticmethod
    def _checkpoint_shape(run, identity, revision, streams, service_id="validation-only"):
        return dict(contract_version=CONTRACT_VERSION, run_id=run, checkpoint_id=identity,
                    revision=revision, established_by=dict(service_id=service_id, basis="SERVICE_ESTABLISHED"),
                    streams=streams, created_at=None)

    def _state(self, run, through=None):
        config = self._run(run)
        maximum = self.db.execute("SELECT COALESCE(MAX(position),0) FROM cv_events WHERE run=?", (run,)).fetchone()[0]
        through = maximum if through is None else through
        result = []
        for item in config:
            seqs = [row[0] for row in self.db.execute(
                "SELECT seq FROM cv_events WHERE run=? AND stream=? AND position<=? ORDER BY seq",
                (run, item["stream_id"], through))]
            contiguous, gaps, expected = 0, [], 1
            for seq in seqs:
                if seq > expected:
                    gaps.append([expected, seq - 1])
                if seq == contiguous + 1:
                    contiguous = seq
                expected = seq + 1
            projected = 0
            for row in self.db.execute("SELECT e.seq FROM cv_events e JOIN cv_projection p ON e.position=p.position "
                                       "WHERE e.run=? AND e.stream=? AND e.position<=? ORDER BY e.seq",
                                       (run, item["stream_id"], through)):
                if row[0] != projected + 1:
                    break
                projected = row[0]
            result.append(dict(stream_id=item["stream_id"], observed=max(seqs, default=0),
                               ingested_through=contiguous, projected_through=projected, gaps=gaps))
        return result

    def _event_references(self, run, event):
        for parent in event["parents"]:
            self._event(run, parent, required=False)
        payload = event["payload"]
        for key in ("input_event_id", "delivery_event_id", "model_input_event_id"):
            if payload.get(key) is not None:
                self._event(run, payload[key], required=False)
        for key in ("included_event_ids", "related_event_ids"):
            for identity in payload.get(key, []):
                self._event(run, identity, required=False)
        if "assessment_id" in payload:
            assessment = self._load(run, "assessment", payload["assessment_id"])
            original = self._load(run, "request", assessment["request_id"])["proposal"]
            if (payload.get("proposal_id"), payload.get("proposal_revision")) != (
                    original["proposal_id"], original["revision"]):
                _error("CONFLICT", "Feedback proposal does not match its retained assessment.")

    def _ingest(self, request, hook):
        _keys(request, {"run_id", "batch_id", "events"})
        run, batch = request["run_id"], _text(request["batch_id"])
        config = self._run(run)
        events = request["events"]
        if type(events) is not list or not events or len(events) > 1000:
            _error("INVALID_REQUEST", "Expected 1 to 1000 accepted events.")
        with self._transaction(hook):
            old = self.db.execute("SELECT request,receipt FROM cv_batches WHERE run=? AND id=?", (run, batch)).fetchone()
            if old:
                if old[0] != canonical_json(request):
                    _error("CONFLICT", "Batch identity has different content.")
                for event in events:
                    self._collector(config, event["stream_id"])
                return json.loads(old[1])
            receipts = []
            for event in events:
                self._validate(validate_event, event)
                if event["run_id"] != run:
                    _error("FORBIDDEN", "Event belongs to another run.")
                binding = self._collector(config, event["stream_id"])
                if (event["producer"]["id"], event["producer"]["adapter_version"], event["origin"]["redaction_profile"]) != (
                        binding["producer_id"], binding["adapter_version"], binding["redaction_profile"]):
                    _error("FORBIDDEN", "Event producer binding is not registered.")
                body = canonical_json(event)
                old_event = self.db.execute("SELECT * FROM cv_events WHERE run=? AND (event_id=? OR (stream=? AND seq=?))",
                                            (run, event["event_id"], event["stream_id"], event["sequence"])).fetchall()
                if old_event:
                    if len(old_event) != 1 or old_event[0]["body"] != body:
                        _error("CONFLICT", "Event identity or stream position has different content.")
                    position, status = old_event[0]["position"], "DUPLICATE"
                else:
                    position = self.db.execute("INSERT INTO cv_events(run,event_id,stream,seq,body) VALUES(?,?,?,?,?)",
                                               (run, event["event_id"], event["stream_id"], event["sequence"], body)).lastrowid
                    last = self.db.execute("SELECT chain_hash FROM cv_event_chain ORDER BY position DESC LIMIT 1").fetchone()
                    chain = digest([last[0] if last else None, position, body])
                    self.db.execute("INSERT INTO cv_event_chain VALUES(?,?)", (position, chain))
                    status = "ACCEPTED"
                payload = event["payload"]
                if event["event_type"] == "source":
                    self._put(run, "source", payload["source_id"], payload["source_version"],
                              {key: payload[key] for key in ("valid_at", "status")} | {"content_digest": event["content_digest"]})
                elif event["event_type"] == "report":
                    self._put(run, "report", payload["report_id"], payload["revision"],
                              {"payload": payload, "content_digest": event["content_digest"]})
                elif event["event_type"] == "model_input":
                    self._put(run, "model_input", payload["input_id"], "0",
                              {"payload": payload, "content_digest": event["content_digest"], "parents": event["parents"]})
                receipts.append(dict(event_id=event["event_id"], receipt_position=position, status=status))
            # References resolve after staging the whole batch; cross-stream and
            # out-of-order missing parents stay explicit, never manufactured.
            for event in events:
                self._event_references(run, event)
            if self.project_on_ingest:
                self._project(run)
            receipt = dict(run_id=run, batch_id=batch, receipt_id="receipt-" + digest(request),
                           events=receipts, streams=self._state(run))
            self.db.execute("INSERT INTO cv_batches VALUES(?,?,?,?)", (run, batch, canonical_json(request), canonical_json(receipt)))
            previous = self.db.execute("SELECT chain_hash FROM cv_batch_chain ORDER BY position DESC LIMIT 1").fetchone()
            chain = digest([previous[0] if previous else None, run, batch, request, receipt])
            self.db.execute("INSERT INTO cv_batch_chain(run,id,chain_hash) VALUES(?,?,?)", (run, batch, chain))
        return receipt

    def _checkpoint(self, request):
        _keys(request, {"run_id", "checkpoint_id", "revision", "registry_revision", "streams"})
        run, identity, revision = request["run_id"], _text(request["checkpoint_id"]), _integer(request["revision"])
        if type(request["registry_revision"]) is not int or request["registry_revision"] != 0:
            _error("CONFLICT", "Registered stream revision does not match.")
        config = self._run(run)
        if type(request["streams"]) is not list:
            _error("INVALID_REQUEST", "Expected the complete registered stream vector.")
        requested = {}
        for item in request["streams"]:
            _keys(item, {"stream_id", "requested"})
            stream = _text(item["stream_id"])
            if stream in requested:
                _error("INVALID_REQUEST", "Duplicate stream in checkpoint.")
            requested[stream] = _integer(item["requested"])
        if set(requested) != {item["stream_id"] for item in config}:
            _error("INVALID_REQUEST", "Checkpoint must include all registered streams.")
        # Establishing coverage for the whole registered set requires the assigned
        # host collector, not merely an arbitrary caller with a collect grant.
        for item in config:
            self._collector(config, item["stream_id"])
        with self._transaction():
            old = self.db.execute("SELECT body FROM cv_objects WHERE run=? AND kind='checkpoint' AND id=? AND revision=?",
                                  (run, identity, str(revision))).fetchone()
            if old:
                saved = json.loads(old[0])
                if saved["request"] != request:
                    _error("CONFLICT", "Checkpoint identity has different requested content.")
                return saved["checkpoint"]
            streams, events = [], []
            for state in self._state(run):
                stream = state["stream_id"]
                target = requested[stream]
                rows = list(self.db.execute("SELECT body FROM cv_events WHERE run=? AND stream=? AND seq<=? ORDER BY seq",
                                            (run, stream, target)))
                events.extend(json.loads(row[0]) for row in rows)
                gaps = [[start, min(end, target)] for start, end in state["gaps"] if start <= target]
                # Missing tail is worker lag/NOT_READY, not an observed dropped
                # interior sequence. A later event can make a gap observable.
                coverage = self.db.execute("SELECT body FROM cv_coverage WHERE run=? AND stream=?", (run, stream)).fetchone()
                caps = json.loads(coverage[0]) if coverage else [dict(name=name, state="UNKNOWN", basis_event_ids=[]) for name in _CAPABILITIES]
                streams.append(dict(stream_id=stream, requested=target,
                                    ingested_through=min(state["ingested_through"], target),
                                    projected_through=min(state["projected_through"], target), gaps=gaps, capabilities=caps))
            checkpoint = self._checkpoint_shape(run, identity, revision, streams, self.service_id)
            self._validate(validate_checkpoint, checkpoint)
            events.sort(key=lambda event: (event["stream_id"], event["sequence"], event["event_id"]))
            self._put(run, "checkpoint", identity, revision,
                      dict(request=request, checkpoint=checkpoint, events=events, event_digest=digest(events),
                           through=self.db.execute("SELECT COALESCE(MAX(position),0) FROM cv_events WHERE run=?", (run,)).fetchone()[0]))
        return checkpoint

    def _resolved(self, request, *, check_optional_refs=True):
        run = request["run_id"]
        self._run(run)
        ref = request["checkpoint"]
        saved = self._load(run, "checkpoint", ref["checkpoint_id"], ref["revision"])
        policy = self._load(run, "policy", request["policy"]["policy_id"], request["policy"]["version"])
        if ref["digest"] != digest(saved["checkpoint"]) or request["policy"]["digest"] != digest(policy):
            _error("CONFLICT", "Stored checkpoint or policy digest does not match.")
        if check_optional_refs:
            self._event(run, request["proposal"]["report_event_id"], required=False)
            for dependency in request["proposal"]["dependencies"] or []:
                self._event(run, dependency, required=False)
        return dict(checkpoint=saved["checkpoint"], events=saved["events"], policy=policy)

    def resolve_view(self, request):
        """Read-authorized host API: exact immutable inputs used by verify.

        Does not establish coverage, register policy, assess or extend a prefix.
        Returned JSON is detached from persistence; no extra model tool exists.
        """
        self._validate(validate_request, request)
        request = json.loads(canonical_json(request))
        self._authorize(request["run_id"], "read")
        with self._transaction():
            old = self.db.execute("SELECT body FROM cv_objects WHERE run=? AND kind='request' AND id=? AND revision='0'",
                                  (request["run_id"], request["request_id"])).fetchone()
            if old and old[0] != canonical_json(request):
                _error("CONFLICT", "Request identity has different content.")
            # Historical unresolved references remain unresolved in their own
            # frozen view; this read must not consult newly arrived foreign data.
            return self._resolved(request, check_optional_refs=old is None)

    def _verify(self, request):
        self._validate(validate_request, request)
        run = request["run_id"]
        self._run(run)
        with self._transaction():
            self._put(run, "request", request["request_id"], "0", request)
            retained = self.db.execute("SELECT body FROM cv_objects WHERE run=? AND kind='request_result' AND id=? AND revision='0'",
                                       (run, request["request_id"])).fetchone()
            if retained:
                return json.loads(retained[0])
            view = self._resolved(request)
            proposal = request["proposal"]
            self._put(run, "proposal", proposal["proposal_id"], proposal["revision"], proposal)
            result = core_verify(request, **view)
            self._validate(validate_result, result)
            self._put(run, "assessment", result["assessment_id"], "0", result)
            self._put(run, "request_result", request["request_id"], "0", result)
        return result

    def audit(self):
        """Replay stored typed bindings; corruption raises a safe service error."""
        previous = None
        try:
            for row in self.db.execute("SELECT * FROM cv_events ORDER BY position"):
                event = json.loads(row["body"])
                validate_event(event)
                if (event["run_id"], event["event_id"], event["stream_id"], event["sequence"]) != (
                        row["run"], row["event_id"], row["stream"], row["seq"]):
                    raise ValueError()
                previous = digest([previous, row["position"], row["body"]])
                chain = self.db.execute("SELECT chain_hash FROM cv_event_chain WHERE position=?", (row["position"],)).fetchone()
                if not chain or chain[0] != previous:
                    raise ValueError()
            if self.db.execute("SELECT COUNT(*) FROM cv_event_chain").fetchone()[0] != self.db.execute("SELECT COUNT(*) FROM cv_events").fetchone()[0]:
                raise ValueError()
            for row in self.db.execute("SELECT p.body,p.run,p.event_id,e.body AS event_body,e.run AS event_run,e.event_id AS identity FROM cv_projection p LEFT JOIN cv_events e ON p.position=e.position"):
                if row["body"] != row["event_body"] or (row["run"], row["event_id"]) != (row["event_run"], row["identity"]):
                    raise ValueError()
            previous = None
            for row in self.db.execute("SELECT * FROM cv_object_chain ORDER BY position"):
                obj = self.db.execute("SELECT body FROM cv_objects WHERE run=? AND kind=? AND id=? AND revision=?",
                                      (row["run"], row["kind"], row["id"], row["revision"])).fetchone()
                if not obj:
                    raise ValueError()
                previous = digest([previous, row["run"], row["kind"], row["id"], row["revision"], obj[0]])
                if previous != row["chain_hash"]:
                    raise ValueError()
            if self.db.execute("SELECT COUNT(*) FROM cv_object_chain").fetchone()[0] != self.db.execute("SELECT COUNT(*) FROM cv_objects").fetchone()[0]:
                raise ValueError()
            for row in self.db.execute("SELECT * FROM cv_objects"):
                value = json.loads(row["body"])
                if row["kind"] == "checkpoint":
                    validate_checkpoint(value["checkpoint"])
                    expected = []
                    for stream in value["checkpoint"]["streams"]:
                        expected.extend(json.loads(item[0]) for item in self.db.execute(
                            "SELECT body FROM cv_events WHERE run=? AND stream=? AND seq<=? AND position<=? ORDER BY seq",
                            (row["run"], stream["stream_id"], stream["requested"], value["through"])))
                    expected.sort(key=lambda event: (event["stream_id"], event["sequence"], event["event_id"]))
                    if expected != value["events"] or digest(expected) != value["event_digest"]:
                        raise ValueError()
                elif row["kind"] in ("assessment", "request_result"):
                    validate_result(value)
                elif row["kind"] == "policy":
                    validate_policy(value)
                elif row["kind"] == "request":
                    validate_request(value)
            for row in self.db.execute("SELECT * FROM cv_batches"):
                request, receipt = json.loads(row["request"]), json.loads(row["receipt"])
                if (receipt["receipt_id"] != "receipt-" + digest(request) or
                        len(request["events"]) != len(receipt["events"])):
                    raise ValueError()
                for event, accepted in zip(request["events"], receipt["events"]):
                    stored = self.db.execute("SELECT body FROM cv_events WHERE position=? AND run=?", (accepted["receipt_position"], row["run"])).fetchone()
                    if not stored or json.loads(stored[0]) != event:
                        raise ValueError()
            previous = None
            for row in self.db.execute("SELECT * FROM cv_batch_chain ORDER BY position"):
                batch = self.db.execute("SELECT request,receipt FROM cv_batches WHERE run=? AND id=?", (row["run"], row["id"])).fetchone()
                if not batch:
                    raise ValueError()
                previous = digest([previous, row["run"], row["id"], json.loads(batch[0]), json.loads(batch[1])])
                if previous != row["chain_hash"]:
                    raise ValueError()
            if self.db.execute("SELECT COUNT(*) FROM cv_batch_chain").fetchone()[0] != self.db.execute("SELECT COUNT(*) FROM cv_batches").fetchone()[0]:
                raise ValueError()
        except (ValueError, KeyError, TypeError, ContractError):
            _error("BACKEND_UNAVAILABLE", "Stored typed bindings failed audit.")
        return {"typed_events": self.db.execute("SELECT COUNT(*) FROM cv_events").fetchone()[0],
                "procedural_records": self.db.execute("SELECT COUNT(*) FROM cv_projection").fetchone()[0]}

    def _list(self, request):
        _keys(request, {"run_id", "after_cursor", "limit"})
        run, limit = request["run_id"], request["limit"]
        self._run(run)
        if type(limit) is not int or not 1 <= limit <= 100:
            _error("INVALID_REQUEST", "Page limit must be 1 through 100.")
        with self._transaction():
            cursor = request["after_cursor"]
            if cursor is None:
                after = 0
                through = self.db.execute("SELECT COALESCE(MAX(position),0) FROM cv_events WHERE run=?", (run,)).fetchone()[0]
                snapshot = "snapshot-" + digest([self.journal.identity, run, through])
            else:
                if type(cursor) is not str or not cursor or len(cursor) > 256:
                    _error("INVALID_CURSOR", "Cursor is invalid.")
                row = self.db.execute("SELECT * FROM cv_cursors WHERE id=?", (cursor,)).fetchone()
                if not row:
                    _error("INVALID_CURSOR", "Cursor was not found.")
                if row["run"] != run:
                    _error("FORBIDDEN", "Cursor belongs to another run.")
                after, through, snapshot = row["after_position"], row["through"], row["snapshot"]
                if (snapshot != "snapshot-" + digest([self.journal.identity, run, through]) or
                        cursor != "cursor-" + digest([self.journal.identity, run, snapshot, after]) or not 0 <= after <= through):
                    _error("INVALID_CURSOR", "Cursor binding is invalid.")
            rows = list(self.db.execute("SELECT position,body FROM cv_events WHERE run=? AND position>? AND position<=? ORDER BY position LIMIT ?",
                                        (run, after, through, limit + 1)))
            more, page = len(rows) > limit, rows[:limit]
            next_cursor = None
            if more:
                next_cursor = "cursor-" + digest([self.journal.identity, run, snapshot, page[-1]["position"]])
                self.db.execute("INSERT OR IGNORE INTO cv_cursors VALUES(?,?,?,?,?)",
                                (next_cursor, run, snapshot, through, page[-1]["position"]))
            return dict(run_id=run, snapshot_id=snapshot, events=[json.loads(row["body"]) for row in page],
                        next_cursor=next_cursor, has_more=more)

    def execute(self, operation, request, *, hook=None):
        """D-compatible signature; optional hook is trusted failure-test injection."""
        if operation not in _PERMISSIONS:
            _error("UNSUPPORTED_OPERATION", "Operation is not implemented.")
        if type(request) is not dict or "run_id" not in request:
            _error("INVALID_REQUEST", "An explicit run scope is required.")
        # Finite JSON copy prevents caller mutation; bound size before any write.
        try:
            body = canonical_json(request)
            if len(body.encode()) > 1024 * 1024:
                raise ValueError()
            request = json.loads(body)
        except (ValueError, UnicodeError, RecursionError):
            _error("INVALID_REQUEST", "Expected bounded finite JSON.")
        run = request["run_id"]
        self._authorize(run, _PERMISSIONS[operation])
        if operation == "acknowledge_feedback":
            _error("UNSUPPORTED_OPERATION", "Use explicit captured feedback lifecycle events; acknowledgement operation is not implemented.")
        if operation == "ingest_events":
            return self._ingest(request, hook)
        if operation == "checkpoint":
            return self._checkpoint(request)
        if operation == "verify":
            return self._verify(request)
        if operation == "list_events":
            return self._list(request)
        if operation == "register_run":
            _keys(request, {"run_id", "registration_id"})
            registration = _text(request["registration_id"])
            config = self._run(run, active=False)
            for item in config:
                self._collector(config, item["stream_id"])
            with self._transaction():
                old = self.db.execute("SELECT registration FROM cv_runs WHERE run=?", (run,)).fetchone()[0]
                if old is not None and old != registration:
                    _error("CONFLICT", "Run already has a registration identity.")
                self.db.execute("UPDATE cv_runs SET registration=? WHERE run=?", (registration, run))
            return dict(run_id=run, registry_revision=0, streams=config, coverage="HOST_OBSERVATIONS_ONLY")
        self._run(run)
        if operation == "get_assessment":
            _keys(request, {"run_id", "assessment_id"})
            return self._load(run, "assessment", request["assessment_id"])
        if operation == "get_evidence":
            _keys(request, {"run_id", "event_id"}, {"span"})
            event = self._event(run, request["event_id"])
            result = dict(run_id=run, event_id=event["event_id"], event=event)
            if "span" in request:
                span = request["span"]
                if type(span) is not list or len(span) != 2 or any(type(item) is not int for item in span) or not 0 <= span[0] <= span[1] <= len(event["content"]):
                    _error("INVALID_REQUEST", "Span must bind retained Unicode content.")
                result.update(span=span, excerpt=event["content"][span[0]:span[1]])
            return result
        _keys(request, {"run_id"})
        coverage = {item["stream_id"]: [dict(name=name, state="UNKNOWN", basis_event_ids=[]) for name in _CAPABILITIES]
                    for item in self._run(run)}
        for row in self.db.execute("SELECT stream,body FROM cv_coverage WHERE run=?", (run,)):
            coverage[row["stream"]] = json.loads(row["body"])
        return dict(run_id=run, registry_revision=0, streams=self._state(run), coverage=coverage,
                    raw_ingested_events=self.db.execute("SELECT COUNT(*) FROM cv_events WHERE run=?", (run,)).fetchone()[0],
                    procedural_records=self.db.execute("SELECT COUNT(*) FROM cv_projection WHERE run=?", (run,)).fetchone()[0],
                    procedural_projection="accepted-typed-records-0.2-1", atomic_semantic_ready=False,
                    native_trace_mapping="NOT_IMPLEMENTED")
