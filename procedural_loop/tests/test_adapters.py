"""Adapter boundary tests; no model calls or source mutations."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from procedural_loop.adapters import (AdapterInputError, FixtureSource, ReplaySession,
                                      distorted_packet)
from procedural_loop.contracts import clearance_binding, require_valid_packet


T0 = "2026-11-02T00:00:00Z"
INITIAL = "2026-11-02T00:00:30Z"
EXPIRED = "2026-11-02T00:01:01Z"
REFRESH = "2026-11-02T00:01:05Z"


class SourceBoundaryTests(unittest.TestCase):
    def test_source_boundary_does_not_reveal_future_row(self):
        for shape in ("single", "multi"):
            source = FixtureSource(shape)
            before = source.read("2026-11-02T00:00:59.999999Z")
            at = source.read("2026-11-02T00:01:00Z")
            key = "result" if shape == "single" else "observation"
            self.assertEqual(before["raw"][key]["observation_id"], "synthetic-quote-v1")
            self.assertEqual(at["raw"][key]["observation_id"], "synthetic-quote-v2")
            self.assertNotIn("synthetic-quote-v2", json.dumps(before))

    def test_shapes_preserve_same_authored_semantics(self):
        for when in (INITIAL, REFRESH):
            single = FixtureSource("single").read(when)["raw"]["result"]
            multi = FixtureSource("multi").read(when)["raw"]["observation"]
            self.assertEqual((single["value"], single["source_version"], single["source_observed_at"]),
                             (multi["amount"], multi["version"], multi["observed_at"]))
            self.assertEqual(single["text"], multi["body"])

    def test_exact_raw_pointer_and_digest(self):
        for shape in ("single", "multi"):
            source = FixtureSource(shape)
            selected = source.read(REFRESH)
            original = json.loads(Path(selected["artifact_path"]).read_bytes())
            self.assertEqual(selected["raw"], original["source_schedule"][1])
            self.assertEqual(selected["raw_pointer"], "/source_schedule/1")
            self.assertEqual(selected["artifact_sha256"], hashlib.sha256(source.path.read_bytes()).hexdigest())
            self.assertEqual(selected["retrieved_at"], REFRESH)

    def test_returned_copy_cannot_contaminate_next_read(self):
        source = FixtureSource("single")
        row = source.read(INITIAL)
        row["raw"]["result"]["value"] = "9999"
        self.assertEqual(source.read(INITIAL)["raw"]["result"]["value"], "2540")

    def test_unknown_observed_time_is_not_fabricated(self):
        document = copy.deepcopy(FixtureSource("single").document)
        del document["source_schedule"][0]["result"]["source_observed_at"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unknown.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            selected = FixtureSource("single", path).read(INITIAL)
            self.assertNotIn("source_observed_at", selected["raw"]["result"])

    def test_unavailable_or_naive_as_of_rejected(self):
        source = FixtureSource("single")
        for value in ("2026-11-01T23:59:59Z", "2026-11-02T00:00:00", None,
                      "not-a-date", "2026-11-02T00:00:00-00:00"):
            with self.assertRaises(AdapterInputError):
                source.read(value)

    def test_duplicate_raw_id_and_wrong_shape_rejected(self):
        document = copy.deepcopy(FixtureSource("single").document)
        document["source_schedule"][1]["event_id"] = document["source_schedule"][0]["event_id"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(AdapterInputError):
                FixtureSource("single", path)
            with self.assertRaises(AdapterInputError):
                FixtureSource("multi", path)

    def test_authored_fixtures_unchanged_by_reads(self):
        for shape in ("single", "multi"):
            source = FixtureSource(shape)
            before = source.path.read_bytes()
            source.read(INITIAL)
            source.read(REFRESH)
            self.assertEqual(before, source.path.read_bytes())


def blocked_assessment(packet):
    """Authored interface stub only; actual verifier exercised by parent runner."""
    return {"assessment_id": "authored-test-blocked", "binding": clearance_binding(packet),
            "findings": [{"result": "FAIL", "required": True}], "clearance": None,
            "required_response": {"action": "refresh_and_resubmit"}}


class SessionLifecycleTests(unittest.TestCase):
    def test_time_advance_reuses_exact_delivered_snapshot_without_future_context(self):
        for shape in ("single", "multi"):
            session = ReplaySession(shape)
            initial = session.initial_packet()
            stale = session.advance_to(EXPIRED)
            self.assertEqual(initial["evidence"], stale["evidence"])
            self.assertEqual(stale["proposal"]["extracts"][0]["value"], "2540")
            self.assertNotIn("synthetic-quote-v2", json.dumps(stale))
            self.assertNotEqual(initial["proposal"]["id"], stale["proposal"]["id"])
            self.assertGreater(stale["context"]["revision"], initial["context"]["revision"])
            require_valid_packet(stale, previous=initial)

    def test_dynamic_delivery_refresh_then_revision(self):
        for shape in ("single", "multi"):
            session = ReplaySession(shape)
            initial = session.initial_packet()
            stale = session.advance_to(EXPIRED)
            session.drain_events()
            ack = session.deliver_finding(blocked_assessment(stale))
            self.assertEqual(ack["kind"], "host.acknowledged")
            fresh = session.request_refresh(REFRESH)
            self.assertEqual(fresh["source_version"], "2")
            self.assertEqual(fresh["valid_at"], "2026-11-02T00:01:00Z")
            self.assertEqual(fresh["retrieved_at"], REFRESH)
            self.assertEqual(stale["proposal"]["extracts"][0]["value"], "2540")
            revised = session.revised_packet()
            self.assertEqual(revised["proposal"]["extracts"][0]["value"], "2560")
            self.assertEqual(revised["evidence"][0], initial["evidence"][0])
            self.assertEqual(revised["evidence"][1]["supersedes"], [initial["evidence"][0]["id"]])
            require_valid_packet(revised, previous=stale)
            kinds = [e["kind"] for e in session.drain_events()]
            self.assertEqual(kinds[:4], ["finding.delivered", "host.acknowledged",
                                        "source.refresh_requested", "source.observed"])
            self.assertEqual(kinds[-1], "proposal.submitted")
            self.assertEqual(session.drain_events(), [])

    def test_refresh_and_revision_require_observable_predecessors(self):
        session = ReplaySession("single")
        with self.assertRaises(AdapterInputError):
            session.advance_to(EXPIRED)
        session.initial_packet()
        with self.assertRaises(AdapterInputError):
            session.request_refresh()
        with self.assertRaises(AdapterInputError):
            session.revised_packet()
        with self.assertRaises(AdapterInputError):
            session.initial_packet()
        with self.assertRaises(AdapterInputError):
            session.advance_to(INITIAL)

    def test_same_version_reread_is_refused_without_immutable_mutation(self):
        for shape in ("single", "multi"):
            session = ReplaySession(shape)
            packet = session.initial_packet()
            session.deliver_finding(blocked_assessment(packet))
            session.drain_events()
            with self.assertRaisesRegex(AdapterInputError, "No new source version"):
                session.request_refresh("2026-11-02T00:00:31Z")
            self.assertEqual(session.drain_events(), [])
            with self.assertRaises(AdapterInputError):
                session.revised_packet()
            # A later explicit eligible refresh remains possible after that refusal.
            refreshed = session.request_refresh(REFRESH)
            revised = session.revised_packet()
            self.assertEqual(refreshed["source_version"], "2")
            self.assertEqual(revised["evidence"][0], packet["evidence"][0])

    def test_wrong_packet_binding_clearance_and_missing_response_reject_delivery(self):
        session = ReplaySession("single")
        initial = session.initial_packet()
        stale = session.advance_to(EXPIRED)
        cases = [blocked_assessment(initial)] + [blocked_assessment(stale) for _ in range(6)]
        cases[1]["clearance"] = {"id": "not-a-refresh-trigger"}
        cases[2]["required_response"] = None
        cases[3]["findings"][0]["result"] = "PASS"
        del cases[4]["binding"]
        cases[5]["binding"] = "not-an-object"
        cases[6]["findings"] = None
        for case in cases:
            with self.assertRaises(AdapterInputError):
                session.deliver_finding(case)
        self.assertNotIn("host.acknowledged", [e["kind"] for e in session.drain_events()])

    def test_multi_topology_and_exact_source_id_retained(self):
        session = ReplaySession("multi")
        packet = session.initial_packet()
        events = session.drain_events()
        by_id = {e["event_id"]: e for e in events}
        self.assertEqual(packet["evidence"][0]["actor_id"], "quote-researcher")
        self.assertEqual(packet["proposal"]["actor_id"], "paper-planner")
        handoff = next(e for e in events if e["kind"] == "agent.handoff")
        extract = next(e for e in events if e["kind"] == "agent.extracted")
        self.assertIn(handoff["event_id"], extract["causal_refs"])
        self.assertEqual(extract["actor_id"], "quote-analyst")
        self.assertIn("multi-source-v1", packet["evidence"][0]["causal_refs"])
        for reference in packet["proposal"]["causal_refs"]:
            self.assertIn(reference, by_id)

    def test_detached_packets_and_instances(self):
        session = ReplaySession("single")
        packet = session.initial_packet()
        packet["evidence"][0]["source_version"] = "edited"
        stale = session.advance_to(EXPIRED)
        self.assertEqual(stale["evidence"][0]["source_version"], "1")
        other = ReplaySession("single").initial_packet()
        self.assertEqual(other["proposal"]["revision"], 1)

    def test_value_and_version_mutations_do_not_modify_source(self):
        packet = ReplaySession("single").initial_packet()
        wrong_value = distorted_packet(packet, value="9999")
        wrong_version = distorted_packet(packet, source_version="nonexistent-revision")
        self.assertEqual(wrong_value["evidence"], packet["evidence"])
        self.assertEqual(wrong_value["proposal"]["extracts"][0]["quote"], "2540")
        self.assertEqual(wrong_value["proposal"]["extracts"][0]["value"], "9999")
        self.assertEqual(wrong_version["proposal"]["extracts"][0]["source_version"], "nonexistent-revision")
        self.assertEqual(packet["proposal"]["extracts"][0]["value"], "2540")

    def test_unknown_clock_and_coverage_remain_unknown(self):
        document = copy.deepcopy(FixtureSource("single").document)
        document["source_schedule"][0]["result"]["source_observed_at"] = None
        document["coverage"]["complete_within_declared_fixture_scope"] = None
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unknown.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            packet = ReplaySession("single", fixture_path=path).initial_packet()
            self.assertIsNone(packet["evidence"][0]["valid_at"])
            self.assertEqual(packet["proposal"]["dependency_completeness"], "UNKNOWN")
            self.assertTrue(all(c["state"] == "UNKNOWN" for c in packet["capabilities"]))


if __name__ == "__main__":
    unittest.main()
