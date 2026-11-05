"""Authored packets only; no corpus builders, providers or model calls."""
import copy
import json
from pathlib import Path
import unittest

from continuous_verification import (
    CONTRACT_VERSION, ContractError, digest, text_digest, validate_event,
    validate_checkpoint, validate_request, validate_policy, validate_result,
    assessment_binding, binding_matches, verify,
)


def example():
    return json.loads((Path(__file__).resolve().parents[1] / "continuous_verification/schemas/example.json").read_text("utf-8"))


def rebind(p):
    p["request"]["checkpoint"]["digest"] = digest(p["checkpoint"])
    p["request"]["policy"]["digest"] = digest(p["policy"])
    return p


class ContractTests(unittest.TestCase):
    def test_example_and_result(self):
        p = example()
        for e in p["events"]:
            validate_event(e)
        validate_checkpoint(p["checkpoint"])
        validate_request(p["request"])
        validate_policy(p["policy"])
        validate_result(verify(**p))

    def test_malformed_shapes(self):
        for field, value in [("sequence", True), ("observed_at", "2026-11-05"), ("recorded_at", "2026-11-05T01:00:00-00:00"), ("occurred_at", "2026-02-30T01:00:00Z"), ("event_type", "invented")]:
            with self.subTest(field=field):
                e = example()["events"][0]
                e[field] = value
                with self.assertRaises(ContractError):
                    validate_event(e)
        e = example()["events"][0]
        e["extra"] = None
        with self.assertRaises(ContractError):
            validate_event(e)

    def test_unknown_is_valid(self):
        p = example()
        e = p["events"][0]
        e.update(occurred_at=None, observed_at=None, recorded_at=None)
        validate_event(e)
        p["request"]["proposal"].update(dependencies=None, dependency_completeness="UNKNOWN")
        validate_request(p["request"])

    def test_exact_content_and_spans(self):
        e = example()["events"][0]
        e["content"] += "\r\n"
        with self.assertRaises(ContractError):
            validate_event(e)
        e["content_digest"] = text_digest(e["content"])
        for span in [[0, len(e["content"]) + 1], [2, 1], [0, True], [0, 1, 2]]:
            e["origin"]["span"] = span
            with self.assertRaises(ContractError):
                validate_event(e)

    def test_immutable_identity(self):
        p = example()
        e = copy.deepcopy(p["events"][0])
        e["content"] += "changed"
        e["content_digest"] = text_digest(e["content"])
        with self.assertRaises(ContractError):
            validate_event(e, previous=p["events"][0])
        cp = copy.deepcopy(p["checkpoint"])
        cp["streams"][0]["projected_through"] += 1
        with self.assertRaises(ContractError):
            validate_checkpoint(cp, previous=p["checkpoint"])
        policy = copy.deepcopy(p["policy"])
        policy["required_tool"] = "other"
        with self.assertRaises(ContractError):
            validate_policy(policy, previous=p["policy"])
        req = copy.deepcopy(p["request"])
        req["proposal"]["revision"] += 1
        with self.assertRaises(ContractError):
            validate_request(req, previous=p["request"])

    def test_binding_all_inputs_and_read_only(self):
        p = example()
        before = copy.deepcopy(p)
        b = assessment_binding(**p)
        self.assertTrue(binding_matches(b, **p))
        for section in ["request", "checkpoint", "policy", "events"]:
            q = copy.deepcopy(p)
            if section == "request":
                q[section]["proposal"]["revision"] += 1
            elif section == "checkpoint":
                q[section]["revision"] += 1
            elif section == "policy":
                q[section]["version"] += "new"
            else:
                q[section].reverse()
            self.assertFalse(binding_matches(b, **q))
        verify(**p)
        self.assertEqual(p, before)

    def test_non_json_and_duplicate_streams(self):
        for value in [float("nan"), {1: "bad"}, {"x": object()}, "\ud800"]:
            with self.assertRaises((ValueError, UnicodeError)):
                digest(value)
        p = example()
        p["checkpoint"]["streams"] *= 2
        with self.assertRaises(ContractError):
            validate_checkpoint(p["checkpoint"])

    def test_source_occurrence_versus_version(self):
        old = example()["events"][0]
        old.update(event_type="source", payload=dict(source_id="source-1", source_version="v1", valid_at=None, retrieved_at=None, status="OK"))
        new = copy.deepcopy(old)
        new.update(event_id="new-occurrence", sequence=2)
        new["payload"]["retrieved_at"] = "2026-11-05T12:30:00+05:30"
        validate_event(new, previous=old)
        new["content"] += "new source bytes"
        new["content_digest"] = text_digest(new["content"])
        with self.assertRaises(ContractError):
            validate_event(new, previous=old)
        new["payload"]["source_version"] = "v2"
        validate_event(new, previous=old)

    def test_result_cannot_disguise_unready_as_pass(self):
        result = verify(**example())
        result["status"] = "NOT_READY"
        with self.assertRaises(ContractError):
            validate_result(result)

    def test_proposal_revision_and_previous_scope(self):
        old = example()["request"]
        new = copy.deepcopy(old)
        new["request_id"] = "new-request"
        new["proposal"]["content"] += "changed"
        new["proposal"]["content_digest"] = text_digest(new["proposal"]["content"])
        with self.assertRaises(ContractError):
            validate_request(new, previous=old)
        new["proposal"]["revision"] += 1
        validate_request(new, previous=old)
        new["run_id"] = "other-run"
        with self.assertRaises(ContractError):
            validate_request(new, previous=old)


if __name__ == "__main__":
    unittest.main()
