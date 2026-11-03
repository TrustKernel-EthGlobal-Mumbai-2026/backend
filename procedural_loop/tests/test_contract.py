"""Boundary tests only: no historical builders, network or model calls."""
import copy
import json
import unittest
from datetime import timezone
from pathlib import Path

from procedural_loop.contracts import (
    SCHEMA_VERSION, ContractError, binding_matches, canonical_json,
    clearance_binding, digest, parse_time, require_valid_packet, text_digest,
    validate_packet,
)


def packet():
    content = "ETH-USD Close = 2540 USD."
    return {
        "schema_version": SCHEMA_VERSION, "packet_id": "command:p1", "run_id": "command:run1",
        "context": {"id": "context", "revision": 1,
                    "observed_at": "2026-11-02T00:00:30Z", "event_refs": ["retrieve-v1"]},
        "capabilities": [{"name": "source_text", "scope": "command:run1",
                          "state": "CAPTURED", "detail": "Authored fixture source"}],
        "evidence": [{
            "id": "e1", "source_id": "fixture:price", "source_version": "v1", "supersedes": [],
            "valid_at": "2026-11-02T00:00:00Z", "retrieved_at": "2026-11-02T00:00:00Z",
            "recorded_at": "2026-11-02T00:00:00Z", "content": content,
            "content_digest": text_digest(content),
            "pointer": {"uri": "fixture://price/v1", "json_pointer": "/content", "span": [0, len(content)]},
            "run_id": "command:run1", "actor_id": "agent", "call_id": "retrieve-v1",
            "causal_refs": [], "status": "AVAILABLE",
        }],
        "proposal": {
            "id": "proposal", "revision": 1, "as_of": "2026-11-02T00:00:30Z",
            "created_at": "2026-11-02T00:00:30Z", "run_id": "command:run1", "actor_id": "agent",
            "call_id": "propose-v1", "causal_refs": ["retrieve-v1"], "text": "Paper research only.",
            "dependencies": [{"evidence_id": "e1", "source_version": "v1", "status": "DECLARED"}],
            "dependency_completeness": "COMPLETE",
            "extracts": [{"id": "x1", "evidence_id": "e1", "source_version": "v1", "span": [16, 20],
                          "quote": "2540", "field": "Close", "value": "2540", "unit": "USD"}],
        },
        "policy": {"id": "fixture:policy", "version": "1", "max_age_seconds": 60,
                   "required_capabilities": ["source_text"]},
    }


class ContractTests(unittest.TestCase):
    def codes(self, value, previous=None):
        return {i["code"] for i in validate_packet(value, previous)}

    def test_valid_roundtrip_and_exact_source_span(self):
        value = packet()
        self.assertEqual(validate_packet(value), [])
        require_valid_packet(json.loads(canonical_json(value)))
        source = value["evidence"][0]["content"]
        self.assertEqual(len(source), 25)
        self.assertEqual(source[16:20], "2540")

    def test_schema_file_is_same_interface_version(self):
        schema = json.loads((Path(__file__).parents[1] / "contract.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], SCHEMA_VERSION)
        self.assertEqual(set(schema["required"]), set(packet()))

    def test_unknown_prerequisites_are_valid_without_clearance(self):
        value = packet()
        for key in ("valid_at", "retrieved_at", "recorded_at"):
            value["evidence"][0][key] = None
        for key in ("as_of", "created_at"):
            value["proposal"][key] = None
        value["context"]["observed_at"] = None
        value["proposal"]["dependencies"] = None
        value["proposal"]["dependency_completeness"] = "UNKNOWN"
        value["proposal"]["extracts"][0]["unit"] = None
        value["capabilities"][0]["state"] = "UNKNOWN"
        self.assertEqual(validate_packet(value), [])
        self.assertNotIn("clearance", clearance_binding(value))
        value["capabilities"] = []
        self.assertEqual(validate_packet(value), [])

    def test_partial_provisional_and_no_data_not_rewritten(self):
        value = packet()
        value["proposal"]["dependencies"][0]["status"] = "PROVISIONAL"
        value["proposal"]["dependency_completeness"] = "PARTIAL"
        value["evidence"][0]["status"] = "NO_DATA"
        value["capabilities"][0]["state"] = "NOT_CAPTURED"
        before = copy.deepcopy(value)
        self.assertEqual(validate_packet(value), [])
        self.assertEqual(value, before)

    def test_extraction_faults_remain_available_to_verifier(self):
        for field, mutation in (("quote", "9999"), ("value", "9999"), ("source_version", "wrong-version"),
                                ("evidence_id", "uncaptured-source")):
            with self.subTest(field=field):
                value = packet()
                value["proposal"]["extracts"][0][field] = mutation
                value["proposal"]["dependencies"][0]["evidence_id"] = "uncaptured-dependency"
                value["evidence"][0]["supersedes"] = ["uncaptured-predecessor"]
                self.assertEqual(validate_packet(value), [])

    def test_temporal_semantics_are_left_to_verifier(self):
        value = packet()
        value["evidence"][0]["valid_at"] = "2026-11-03T00:00:00Z"
        value["evidence"][0]["retrieved_at"] = "2026-11-01T00:00:00Z"
        self.assertEqual(validate_packet(value), [])

    def test_missing_key_type_and_unknown_field_are_explicit_errors(self):
        mutations = [lambda p: p.pop("policy"), lambda p: p.update(extra=True),
                     lambda p: p["context"].update(revision=True),
                     lambda p: p["policy"].update(max_age_seconds=-1),
                     lambda p: p["evidence"][0].update(supersedes="e0"),
                     lambda p: p["proposal"]["extracts"][0].update(value=2540)]
        for mutate in mutations:
            value = packet()
            mutate(value)
            with self.subTest(value=value):
                self.assertTrue(validate_packet(value))
                with self.assertRaises(ContractError) as caught:
                    require_valid_packet(value)
                self.assertTrue(all(set(i) == {"path", "code", "message"} for i in caught.exception.issues))

    def test_time_offsets_and_invalid_clocks(self):
        self.assertIsNone(parse_time(None))
        self.assertEqual(parse_time("2026-11-02T05:30:30+05:30").astimezone(timezone.utc),
                         parse_time("2026-11-02T00:00:30Z"))
        for bad in ("2026-11-02", "2026-11-02T00:00:30", "2026-11-31T00:00:30Z",
                    "2026-11-02T00:00:30+00:99", "2026-11-02T00:00:30-00:00", "", 123):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_time(bad)
                value = packet()
                value["context"]["observed_at"] = bad
                self.assertTrue(self.codes(value) & {"TYPE", "TIMESTAMP"})

    def test_hash_and_pointer_mutations_rejected(self):
        value = packet()
        value["evidence"][0]["content"] += " altered"
        self.assertIn("DIGEST", self.codes(value))
        for span in ([-1, 2], [0, 26], [20, 16], [0], [False, 2]):
            value = packet()
            value["proposal"]["extracts"][0]["span"] = span
            self.assertTrue(self.codes(value), span)
        value = packet()
        value["evidence"][0]["pointer"]["json_pointer"] = "/invalid~escape"
        self.assertIn("PATTERN", self.codes(value))

    def test_duplicate_ids_and_cross_run_scope_rejected(self):
        mutations = [lambda p: p["evidence"].append(copy.deepcopy(p["evidence"][0])),
                     lambda p: p["capabilities"].append(copy.deepcopy(p["capabilities"][0])),
                     lambda p: p["proposal"]["extracts"].append(copy.deepcopy(p["proposal"]["extracts"][0])),
                     lambda p: p["evidence"][0].update(run_id="different"),
                     lambda p: p["proposal"].update(run_id="different"),
                     lambda p: p["capabilities"][0].update(scope="different"),
                     lambda p: p["evidence"][0].update(supersedes=["e1"])]
        for mutate in mutations:
            value = packet()
            mutate(value)
            self.assertTrue(self.codes(value))

    def test_binding_catches_every_bound_component(self):
        original = packet()
        binding = clearance_binding(original)
        self.assertTrue(binding_matches(binding, original))
        mutations = [lambda p: p.update(packet_id="p2"),
                     lambda p: p["context"].update(revision=2),
                     lambda p: p["proposal"].update(as_of="2026-11-02T00:01:01Z"),
                     lambda p: p["policy"].update(version="2"),
                     lambda p: p["evidence"][0].update(source_version="v2"),
                     lambda p: p["capabilities"][0].update(state="UNKNOWN")]
        for mutate in mutations:
            value = copy.deepcopy(original)
            mutate(value)
            self.assertEqual(validate_packet(value), [])
            self.assertFalse(binding_matches(binding, value))
        self.assertFalse(binding_matches({**binding, "extra": True}, original))
        self.assertFalse(binding_matches({}, original))
        self.assertFalse(binding_matches(binding, {"malformed": True}))

    def test_bindings_and_validation_do_not_mutate_input(self):
        value = packet()
        before = copy.deepcopy(value)
        require_valid_packet(value, copy.deepcopy(value))
        binding_matches(clearance_binding(value), value)
        self.assertEqual(value, before)

    def test_canonical_order_raw_unicode_and_non_json_rejected(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))
        self.assertNotEqual(text_digest("x\n"), text_digest("x\r\n"))
        self.assertNotEqual(text_digest("2540"), digest("2540"))
        self.assertNotEqual(text_digest("é"), text_digest("e\u0301"))
        for bad in ({1: "key"}, {"x": float("nan")}, {"x": float("inf")}, (1, 2), {1, 2}, "\ud800"):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises((ValueError, UnicodeError)):
                    canonical_json(bad)
                self.assertIn("JSON", self.codes(bad))

    def test_previous_packet_prevents_immutable_revision_reuse(self):
        original = packet()
        mutations = [lambda p: p["proposal"].update(text="Changed paper proposal"),
                     lambda p: p["policy"].update(max_age_seconds=120),
                     lambda p: p["context"].update(observed_at="2026-11-02T00:01:00Z"),
                     lambda p: p["evidence"][0].update(retrieved_at="2026-11-02T00:00:01Z"),
                     lambda p: p["capabilities"][0].update(state="UNKNOWN")]
        for mutate in mutations:
            value = copy.deepcopy(original)
            value["packet_id"] = "p2"
            mutate(value)
            self.assertIn("IMMUTABLE_IDENTITY", self.codes(value, original))
        self.assertIn("PREVIOUS_RUN", self.codes({**original, "run_id": "different",
                      "evidence": [], "capabilities": [], "proposal": {**original["proposal"], "run_id": "different"}}, original))
        self.assertIn("INVALID_PREVIOUS", self.codes(original, {}))

    def test_correct_successor_retains_old_evidence_and_versions(self):
        original = packet()
        value = copy.deepcopy(original)
        value["packet_id"] = "p2"
        value["proposal"].update(revision=2, as_of="2026-11-02T00:01:05Z", created_at="2026-11-02T00:01:05Z")
        value["context"].update(revision=2, observed_at="2026-11-02T00:01:05Z")
        new = copy.deepcopy(value["evidence"][0])
        new.update(id="e2", source_version="v2", supersedes=["e1"],
                   valid_at="2026-11-02T00:01:00Z", retrieved_at="2026-11-02T00:01:05Z",
                   recorded_at="2026-11-02T00:01:05Z", content="ETH-USD Close = 2550 USD.")
        new["content_digest"] = text_digest(new["content"])
        value["evidence"].append(new)
        value["proposal"]["dependencies"][0].update(evidence_id="e2", source_version="v2")
        value["proposal"]["extracts"][0].update(evidence_id="e2", source_version="v2", quote="2550", value="2550")
        self.assertEqual(validate_packet(value, original), [])
        self.assertEqual(original["evidence"][0]["content"], "ETH-USD Close = 2540 USD.")
        self.assertFalse(binding_matches(clearance_binding(original), value))

    def test_same_source_version_allows_retrieval_occurrences_not_changed_facts(self):
        original = packet()
        value = copy.deepcopy(original)
        value["packet_id"] = "p2"
        value["context"]["revision"] = 2
        occurrence = copy.deepcopy(original["evidence"][0])
        occurrence.update(id="e1-second-retrieval", retrieved_at="2026-11-02T00:00:01Z")
        value["evidence"].append(occurrence)
        self.assertEqual(validate_packet(value, original), [])
        occurrence["content"] = "ETH-USD Close = 9999 USD."
        occurrence["content_digest"] = text_digest(occurrence["content"])
        self.assertIn("SOURCE_VERSION_CONFLICT", self.codes(value))
        value["evidence"] = [occurrence]
        self.assertIn("IMMUTABLE_IDENTITY", self.codes(value, original))


if __name__ == "__main__":
    unittest.main()
