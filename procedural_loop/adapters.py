"""Offline authored fixture adapters; no model, network or trading integration.

Raw-source selection is independent of the shared verification contract. Session
packets are wired only against the parent-routed frozen contract.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / "fixtures"
SHAPES = {"single": "single_command_v1.json", "multi": "multi_handoff_v1.json"}
INITIAL_AS_OF = "2026-11-02T00:00:30Z"
EXPIRED_AS_OF = "2026-11-02T00:01:01Z"
REFRESH_AS_OF = "2026-11-02T00:01:05Z"
REQUIRED_CAPABILITIES = ["evidence_timestamps", "source_versions", "source_text",
                         "declared_dependencies", "observed_prefix"]


class AdapterInputError(ValueError):
    """A malformed or unsupported fixture cannot be treated as observed evidence."""


def _instant(value: str) -> datetime:
    from procedural_loop.contracts import parse_time
    try:
        result = parse_time(value)
    except (TypeError, ValueError) as exc:
        raise AdapterInputError("Invalid fixture time") from exc
    if result is None:
        raise AdapterInputError("Explicit timezone-bearing as-of/availability time required")
    return result


class FixtureSource:
    """Read-only source schedule. File existence is not consumer visibility.

    Selecting a row does not by itself update any session/context. All returned
    values are detached copies. Missing observation metadata stays missing for
    the contract/verifier to reject or mark inconclusive.
    """

    def __init__(self, shape: str, fixture_path: str | Path | None = None):
        if shape not in SHAPES:
            raise AdapterInputError("Unknown fixture shape; use single or multi")
        self.shape = shape
        self.path = Path(fixture_path) if fixture_path else FIXTURES / SHAPES[shape]
        self.bytes = self.path.read_bytes()
        self.sha256 = hashlib.sha256(self.bytes).hexdigest()
        self.document = json.loads(self.bytes)
        expected = "single-command-records/1" if shape == "single" else "multi-agent-steps/1"
        if self.document.get("fixture_format") != expected:
            raise AdapterInputError("Fixture format does not match adapter shape")
        schedule = self.document.get("source_schedule")
        if not isinstance(schedule, list) or not schedule:
            raise AdapterInputError("A nonempty explicit source schedule is required")
        ids = set()
        times = []
        for row in schedule:
            raw_id = row.get("event_id" if shape == "single" else "step_id")
            if not isinstance(raw_id, str) or not raw_id or raw_id in ids:
                raise AdapterInputError("Source record IDs must be explicit and unique")
            ids.add(raw_id)
            times.append(_instant(row.get("available_at")))
            if not isinstance(row.get("result" if shape == "single" else "observation"), dict):
                raise AdapterInputError("Source observation object required")
        if times != sorted(times) or len(set(times)) != len(times):
            raise AdapterInputError("Source schedule boundaries must strictly increase")

    def read(self, as_of: str) -> dict:
        """Select latest scheduled row visible at this explicit read boundary."""
        when = _instant(as_of)
        eligible = [(i, row) for i, row in enumerate(self.document["source_schedule"])
                    if _instant(row["available_at"]) <= when]
        if not eligible:
            raise AdapterInputError("No fixture observation is available at that boundary")
        index, row = eligible[-1]
        key = "result" if self.shape == "single" else "observation"
        return {"raw": copy.deepcopy(row), "raw_pointer": f"/source_schedule/{index}",
                "observation_pointer": f"/source_schedule/{index}/{key}",
                "artifact_path": str(self.path.resolve()), "artifact_sha256": self.sha256,
                "retrieved_at": as_of}


class ReplaySession:
    """Scripted host lifecycle; assessment/clearance belong to the verifier.

    Methods emit raw events as actions happen. Parent persists drain_events().
    Merely advancing time cannot read a newer fixture row or revise an extract.
    """

    def __init__(self, shape: str, run_id: str | None = None,
                 fixture_path: str | Path | None = None):
        self.source = FixtureSource(shape, fixture_path)
        self.shape = shape
        self.run_id = run_id or f"procedural-{shape}"
        self._events = []
        self._all_event_ids = []
        self._sequence = 0
        self._revision = 0
        self._evidence = []
        self._active = None
        self._as_of = None
        self._last_packet = None
        self._delivered = None
        self._ack_id = None
        self._refreshed = False

    def _emit(self, kind, as_of, actor, causal_refs=(), **payload):
        self._sequence += 1
        event = {"event_id": f"{self.run_id}:adapter:{self._sequence}",
                 "kind": kind, "as_of": as_of, "actor_id": actor,
                 "causal_refs": list(causal_refs), "mode": "offline_scripted_fixture",
                 "payload": copy.deepcopy(payload)}
        self._events.append(event)
        self._all_event_ids.append(event["event_id"])
        return event

    def drain_events(self):
        result, self._events = self._events, []
        return copy.deepcopy(result)

    def _read_evidence(self, as_of, refresh_ref=None):
        from procedural_loop.contracts import text_digest
        selected = self.source.read(as_of)
        row = selected["raw"]
        single = self.shape == "single"
        raw = row["result" if single else "observation"]
        content = raw.get("text" if single else "body")
        if not isinstance(content, str):
            raise AdapterInputError("Source text must be observed, not invented")
        version = raw.get("source_version" if single else "version")
        if not isinstance(version, str) or not version:
            raise AdapterInputError("Explicit source version is required")
        raw_id = row["event_id" if single else "step_id"]
        actor = row.get("actor_id" if single else "agent")
        if not isinstance(actor, str) or not actor:
            raise AdapterInputError("Explicit source actor required")
        evidence_id = f"{self.run_id}:{raw['observation_id']}"
        existing = next((e for e in self._evidence if e["id"] == evidence_id), None)
        if existing is not None:
            return existing
        parent_refs = [raw_id] + ([refresh_ref] if refresh_ref else [])
        observed = self._emit("source.observed", as_of, actor, parent_refs,
            fixture_artifact=selected["artifact_path"], fixture_sha256=selected["artifact_sha256"],
            raw_id=raw_id, raw_pointer=selected["raw_pointer"], raw=selected["raw"],
            source_observed_at=raw.get("source_observed_at" if single else "observed_at"),
            retrieved_at=as_of)
        old_id = raw.get("supersedes")
        evidence = {"id": evidence_id, "source_id": self.source.document.get("source_id"),
            "source_version": version, "supersedes": [f"{self.run_id}:{old_id}"] if old_id else [],
            "valid_at": raw.get("source_observed_at" if single else "observed_at"),
            "retrieved_at": as_of, "recorded_at": as_of, "content": content,
            "content_digest": text_digest(content),
            "pointer": {"uri": self.source.path.resolve().as_uri(),
                "json_pointer": selected["observation_pointer"] + ("/text" if single else "/body"),
                "span": [0, len(content)]},
            "run_id": self.run_id, "actor_id": actor,
            "call_id": row.get("command_id") if single else raw_id,
            "causal_refs": [raw_id, observed["event_id"]], "status": "AVAILABLE"}
        self._evidence.append(evidence)
        return evidence

    def _packet(self):
        from procedural_loop.contracts import SCHEMA_VERSION, require_valid_packet
        evidence = self._active
        if evidence is None:
            raise AdapterInputError("Initial source read is required")
        # Scalar mapping is explicitly fixture-authored, not inferred semantics.
        content = evidence["content"]
        prefix, suffix = "Synthetic ETH-USD quote: ", " USD at "
        if not content.startswith(prefix) or suffix not in content:
            raise AdapterInputError("Authored quote mapping cannot be resolved")
        amount = content[len(prefix):].split(suffix, 1)[0]
        start = len(prefix)
        self._revision += 1
        actor = self.source.document["proposal_template"]["actor_id"]
        refs = list(evidence["causal_refs"])
        if self.shape == "multi":
            handoff = self.source.document["handoff_template"]
            transfer = self._emit("agent.handoff", self._as_of, handoff["from_actor"], refs,
                to_actor=handoff["to_actor"], evidence_id=evidence["id"],
                template_pointer="/handoff_template", basis="fixture-authored explicit transfer")
            extracted = self._emit("agent.extracted", self._as_of, handoff["to_actor"],
                [transfer["event_id"]], to_actor=actor, value=amount,
                evidence_id=evidence["id"], source_version=evidence["source_version"])
            refs = [extracted["event_id"]]
        proposal_id = f"{self.run_id}:proposal:{self._revision}"
        submitted = self._emit("proposal.submitted", self._as_of, actor, refs,
            proposal_id=proposal_id, proposal_revision=self._revision,
            evidence_id=evidence["id"], source_version=evidence["source_version"], value=amount,
            proposal_template_pointer="/proposal_template", fixture_sha256=self.source.sha256)
        completeness = self.source.document.get("coverage", {}).get("complete_within_declared_fixture_scope")
        captured = completeness is True
        cap_known = {"evidence_timestamps": all(e["valid_at"] is not None and
            e["retrieved_at"] is not None and e["recorded_at"] is not None for e in self._evidence),
            "source_versions": all(e["source_version"] for e in self._evidence),
            "source_text": all(isinstance(e["content"], str) for e in self._evidence),
            "declared_dependencies": captured, "observed_prefix": captured}
        packet = {"schema_version": SCHEMA_VERSION,
            "packet_id": f"{self.run_id}:packet:{self._revision}", "run_id": self.run_id,
            "context": {"id": f"{self.run_id}:context", "revision": self._revision,
                "observed_at": self._as_of, "event_refs": list(self._all_event_ids)},
            "capabilities": [{"name": name, "scope": self.run_id,
                "state": "CAPTURED" if captured and cap_known[name] else "UNKNOWN",
                "detail": "Complete only for the authored quote dependency and scripted observed prefix; no external framework/hidden-reasoning claim."}
                for name in REQUIRED_CAPABILITIES],
            "evidence": copy.deepcopy(self._evidence),
            "proposal": {"id": proposal_id, "revision": self._revision,
                "as_of": self._as_of, "created_at": self._as_of, "run_id": self.run_id,
                "actor_id": actor, "call_id": submitted["event_id"],
                "causal_refs": refs + [submitted["event_id"]],
                "text": f"REVIEW_ONLY synthetic paper proposal; quote observation {amount} USD. No trade authority.",
                "dependencies": [{"evidence_id": evidence["id"],
                    "source_version": evidence["source_version"], "status": "DECLARED"}],
                "dependency_completeness": "COMPLETE" if captured else "UNKNOWN",
                "extracts": [{"id": f"{proposal_id}:extract:1", "evidence_id": evidence["id"],
                    "source_version": evidence["source_version"], "span": [start, start + len(amount)],
                    "quote": amount, "field": "observed_quote", "value": amount,
                    "unit": self.source.document.get("unit")}]},
            "policy": {"id": "synthetic-quote-freshness", "version": "1",
                "max_age_seconds": self.source.document["test_parameters"]["max_age_seconds"],
                "required_capabilities": list(REQUIRED_CAPABILITIES)}}
        require_valid_packet(packet, previous=self._last_packet)
        self._last_packet = copy.deepcopy(packet)
        return copy.deepcopy(packet)

    def initial_packet(self):
        if self._last_packet is not None:
            raise AdapterInputError("Initial packet already submitted")
        self._active = self._read_evidence("2026-11-02T00:00:00Z")
        self._as_of = INITIAL_AS_OF
        return self._packet()

    def advance_to(self, as_of):
        if self._last_packet is None:
            raise AdapterInputError("Initial packet required before time advance")
        if _instant(as_of) <= _instant(self._as_of):
            raise AdapterInputError("Advance must strictly increase explicit decision as-of")
        self._emit("clock.advanced", as_of, "scripted-host", [], previous_as_of=self._as_of,
                   note="No source read; already delivered evidence is reused")
        self._as_of = as_of
        self._delivered = None
        self._ack_id = None
        self._refreshed = False
        return self._packet()

    def deliver_finding(self, assessment):
        from procedural_loop.contracts import binding_matches
        if self._last_packet is None or not isinstance(assessment, dict):
            raise AdapterInputError("Deliver a blocked assessment for the current submitted packet")
        identity = assessment.get("assessment_id") or assessment.get("id")
        binding = assessment.get("binding")
        if not isinstance(binding, dict):
            raise AdapterInputError("Blocked assessment must carry a packet binding object")
        packet_id = assessment.get("packet_id") or binding.get("packet_id")
        if not isinstance(identity, str) or not identity or packet_id != self._last_packet["packet_id"]:
            raise AdapterInputError("Assessment must name the current packet and assessment identity")
        if not isinstance(binding, dict) or not binding_matches(binding, self._last_packet):
            raise AdapterInputError("Blocked assessment must bind exact current packet bytes")
        findings = assessment.get("findings", [])
        if not isinstance(findings, list):
            raise AdapterInputError("Explicit required findings must be a list")
        blocked = any((f.get("result") or f.get("status")) in ("FAIL", "ERROR", "INCONCLUSIVE", "NOT_APPLICABLE")
                      for f in findings if isinstance(f, dict) and f.get("required", True))
        if assessment.get("clearance") is not None or not blocked or not assessment.get("required_response"):
            raise AdapterInputError("Refresh requires non-PASS required findings, no clearance and a machine response")
        if self._delivered is not None:
            raise AdapterInputError("Finding already delivered for this proposal")
        self._delivered = copy.deepcopy(assessment)
        delivered = self._emit("finding.delivered", self._as_of, "scripted-host", [],
            assessment_id=identity, packet_id=packet_id, assessment=assessment)
        ack = self._emit("host.acknowledged", self._as_of, "scripted-host", [delivered["event_id"]],
            assessment_id=identity, response="hold paper proposal pending refresh and resubmission",
            enforcement="scripted host only; not a real framework or trade gate")
        self._ack_id = ack["event_id"]
        return copy.deepcopy(ack)

    def request_refresh(self, as_of=REFRESH_AS_OF):
        if self._delivered is None:
            raise AdapterInputError("Blocked finding delivery is required before refresh")
        if self._refreshed:
            raise AdapterInputError("Refresh already completed for this finding")
        if _instant(as_of) < _instant(self._as_of):
            raise AdapterInputError("Refresh cannot precede the current observed boundary")
        # Validate availability before emitting any transition.
        selected = self.source.read(as_of)
        raw = selected["raw"]["result" if self.shape == "single" else "observation"]
        version = raw.get("source_version" if self.shape == "single" else "version")
        if version == self._active["source_version"]:
            raise AdapterInputError("No new source version is available; immutable evidence is not refreshed by rereading it")
        request = self._emit("source.refresh_requested", as_of, "scripted-host", [self._ack_id],
            assessment_id=self._delivered.get("assessment_id") or self._delivered.get("id"),
            available_raw_pointer=selected["raw_pointer"])
        self._active = self._read_evidence(as_of, request["event_id"])
        self._as_of = as_of
        self._refreshed = True
        return copy.deepcopy(self._active)

    def revised_packet(self):
        if not self._refreshed:
            raise AdapterInputError("Explicit refresh is required before revision")
        packet = self._packet()
        self._refreshed = False
        self._delivered = None
        self._ack_id = None
        return packet


def distorted_packet(packet, *, value=None, source_version=None):
    """Authored mutation, not a correction. Original evidence remains unchanged."""
    from procedural_loop.contracts import require_valid_packet
    result = copy.deepcopy(packet)
    result["packet_id"] += ":distorted"
    result["proposal"]["id"] += ":distorted"
    for extract in result["proposal"]["extracts"]:
        extract["id"] += ":distorted"
        if value is not None:
            extract["value"] = value
        if source_version is not None:
            extract["source_version"] = source_version
    require_valid_packet(result)
    return result
