"""Readiness controls; optional actual-import runner tests are separate."""
import unittest
from unittest.mock import patch
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import importlib.util
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from tools import tradingagents_integration as integration
from tools.tradingagents_integration import PROFILE, ROOT, preflight_plan, approval_template, validate_approval, read_existing_budget, reviewed_budget_summary


def authored_review(path=None, total=4.128377500000004):
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest() if path else "0"*64
    return dict(budget_sha256_before=fingerprint, budget_sha256_after=fingerprint, unchanged=True,
        reserved_including_existing_holds=str(total), initial_active_hard=[3,5,5], existing_unsettled_rows=1)


class ReadinessPlanTests(unittest.TestCase):
    def test_default_plan_disables_paid_and_preserves_unknowns(self):
        plan = preflight_plan()
        self.assertFalse(plan["execution_enabled"])
        self.assertIn("NOT_OPENED", plan["budget_status"])
        self.assertIn("NOT_CHECKED", plan["model_access"])
        self.assertEqual(plan["new_user_approval"], "REQUIRED")
        self.assertEqual(PROFILE["tool_choice"], "auto")
        self.assertFalse(PROFILE["live_sources"])
        self.assertEqual(PROFILE["cumulative_hard_limit_usd"], 5)
        self.assertEqual(PROFILE["max_model_calls"], 4)
        plan["profile"]["model"] = "changed"
        self.assertEqual(PROFILE["model"], "gpt-6.1-terra")

    def test_template_is_not_approval_and_exact_bindings_expiry_are_required(self):
        fixture = dict(origin="AUTHORED_UNIT_ONLY")
        review = authored_review()
        template = approval_template(fixture, review)
        output = ROOT / ".local-runs/authored-unit-approval-never-launched"
        with self.assertRaises(PermissionError):
            validate_approval(template, fixture, output=output, review=review)
        authored_approval_double = dict(template, approved=True, approval_id="authored-unit-double-not-user-approval",
            launch_output=".local-runs/authored-unit-approval-never-launched",
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            budget_review="CONFIRMED_PINNED_LEDGER_PRESERVE_KNOWN_HOLD",
            pricing_review="CONFIRMED_ORIGINAL_UPPER_RATES_CONSERVATIVE", model_account_access="UNPROBED_CALL_MAY_FAIL_AND_RETAIN_HOLD")
        validate_approval(authored_approval_double, fixture, output=output, review=review)
        for key, value in (("profile_digest", "wrong"), ("implementation_digest", "wrong"), ("fixture_digest", "wrong"),
                           ("incremental_limit_usd", 5), ("launch_output", ".local-runs/other"),
                           ("approved", False), ("expires_at", "2020-01-01T00:00:00Z")):
            with self.subTest(key=key), self.assertRaises(PermissionError):
                validate_approval(dict(authored_approval_double, **{key: value}), fixture, output=output, review=review)

    def test_authored_budget_gate_pins_historical_hold_and_rejects_new_or_changed_state(self):
        # Authored temporary DB only; no actual private ledger is opened.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runs").mkdir()
            (root / "budget_policy.json").write_text(json.dumps(dict(hard_limit_usd=5, initial_limit_usd=3)), "utf-8")
            path = root / "runs/approved-budget.sqlite"
            db = sqlite3.connect(path)
            try:
                db.executescript("CREATE TABLE budget(id INTEGER,reserved REAL); INSERT INTO budget VALUES(1,4.128377500000004);"
                    "CREATE TABLE budget_policy(id INTEGER,initial_limit REAL,active_limit REAL,hard_limit REAL);"
                    "INSERT INTO budget_policy VALUES(1,3,5,5);"
                    "CREATE TABLE requests(id TEXT,reserved REAL,charge REAL,status TEXT,response_id TEXT);"
                    "INSERT INTO requests VALUES('authored-historical-hold',0.16024,NULL,'in_flight_or_unknown',NULL);"
                    "INSERT INTO requests VALUES('authored-settled',3.9,3.473855,'settled','authored-response');")
                db.commit()
                review = authored_review(path)
                before = path.read_bytes()
                initial = read_existing_budget(root, review=review)
                baseline = initial["baseline"]
                self.assertEqual(baseline["hold_id"], "authored-historical-hold")
                self.assertAlmostEqual(initial["required_reserve"], .64096)
                self.assertEqual(before, path.read_bytes())
                mutations = [
                    "UPDATE requests SET id='changed' WHERE id='authored-historical-hold'",
                    "UPDATE requests SET reserved=.15 WHERE id='authored-historical-hold'",
                    "UPDATE requests SET status='settled',charge=.01 WHERE id='authored-historical-hold'",
                    "INSERT INTO requests VALUES('new-unknown',.16024,NULL,'in_flight_or_unknown',NULL)",
                    "UPDATE budget SET reserved=4.2",
                ]
                for mutation in mutations:
                    db.execute("SAVEPOINT authored_mutation")
                    db.execute(mutation)
                    db.execute("RELEASE authored_mutation")
                    db.commit()
                    before = path.read_bytes()
                    with self.subTest(mutation=mutation), self.assertRaises(PermissionError):
                        read_existing_budget(root, review=review, baseline=baseline)
                    self.assertEqual(before, path.read_bytes())
                    # Restore authored fixture rows, never a real budget/hold.
                    db.execute("DELETE FROM requests")
                    db.executemany("INSERT INTO requests VALUES(?,?,?,?,?)", list(baseline["rows"].values()))
                    db.execute("UPDATE budget SET reserved=?", (baseline["total"],))
                    db.commit()
                with self.assertRaises(PermissionError):
                    read_existing_budget(root, review=review)  # Physical identity changed since closed review.
                with self.assertRaises(PermissionError):
                    reviewed_budget_summary(authored_review(total=4.9))
                db.execute("INSERT INTO requests VALUES('our-request',.16024,.01,'settled','authored-new-response')")
                db.execute("UPDATE budget SET reserved=?", (baseline["total"]+.01,))
                db.commit()
                allowed = read_existing_budget(root, review=review, baseline=baseline, owned_ids={"our-request"},remaining_calls=3)
                self.assertEqual(allowed["baseline"]["rows"]["authored-historical-hold"], baseline["rows"]["authored-historical-hold"])
            finally:
                db.close()

    def test_paid_flag_alone_is_rejected_before_child_or_budget(self):
        with patch.object(sys, "argv", ["integration", "--mode", "paid", "--output", ".local-runs/never-created"]), \
             patch.object(integration.subprocess, "run") as child:
            with self.assertRaises(SystemExit):
                integration.main()
            child.assert_not_called()

    def test_supervisor_timeout_or_operator_stop_retains_unknowns_without_reconciliation(self):
        (ROOT / ".local-runs").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".local-runs", prefix="supervisor-unit-") as directory:
            root = Path(directory).resolve()
            self.assertTrue(root.is_relative_to(ROOT / ".local-runs"))
            for name, exception in (("timeout", subprocess.TimeoutExpired("authored-child", 120)), ("operator", KeyboardInterrupt())):
                target = root / name
                with patch.object(sys, "argv", ["integration", "--mode", "scripted", "--upstream", str(root / "upstream/TradingAgents"), "--output", str(target)]), \
                     patch.object(integration.subprocess, "run", side_effect=exception):
                    self.assertEqual(integration.main(), 1)
                stop = json.loads((target / "supervisor-stop.json").read_text("utf-8"))
                self.assertEqual(stop["outcome"], "WALL_TIMEOUT_NOT_PASS" if name == "timeout" else "OPERATOR_STOP_NOT_PASS")
                self.assertIn("never reconciled", stop["unknown_paid_reservations"])


class RealImportedRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = os.environ.get("TRUSTKERNEL_TRADINGAGENTS_UPSTREAM")
        if not cls.upstream or importlib.util.find_spec("langchain_openai") is None:
            raise unittest.SkipTest("Actual imported runner NOT RUN: optional pinned path/native dependencies unavailable")

    def setUp(self):
        (ROOT / ".local-runs").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".local-runs", prefix="real-import-tests-")
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(ROOT / ".local-runs"))
        self.addCleanup(self.temp.cleanup)
        self.review_path = self.root / "authored-review.json"
        self.review_path.write_text(json.dumps(authored_review()), "utf-8")

    def invoke(self, name, *args):
        target = self.root / name
        result = subprocess.run([sys.executable, "-B", str(ROOT / "tools/tradingagents_integration.py"), "--upstream", self.upstream,
            "--output", str(target), "--budget-review", str(self.review_path), *args], cwd=ROOT, capture_output=True, text=True, timeout=40)
        self.assertTrue((target / "readiness.json").is_file(), result.stdout + result.stderr)
        return result, json.loads((target / "readiness.json").read_text("utf-8")), target

    def test_default_preflight_real_imports_without_model_or_budget(self):
        result, report, target = self.invoke("preflight")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(report["actual_import"])
        self.assertFalse(report["execution_enabled"])
        self.assertEqual(report["outcome"], "NO_PAID_PREFLIGHT_COMPLETE")
        self.assertIn("NOT_OPENED", report["budget_status"])
        self.assertFalse((target / "feedback.sqlite").exists())
        self.assertFalse((target / "runtime-trace").exists())
        self.assertFalse(json.loads((target / "approval-required.json").read_text("utf-8"))["approved"])

    def test_same_client_imported_graph_and_http_override_progress(self):
        result, report, target = self.invoke("normal", "--mode", "scripted")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["readiness"], "READY_FOR_APPROVAL")
        self.assertTrue(report["real_import"])
        self.assertFalse(report["full_graph_setup"])
        self.assertFalse(report["provider_generated_verify"])
        self.assertEqual(report["response_origin"], "AUTHORED_HTTP_OVERRIDE")
        self.assertEqual(report["joined_generated_dispatched_delivered_ids"], ["authored-verify"])
        self.assertEqual(report["exact_next_wire_feedback_requests"], [2, 3])
        self.assertTrue(report["next_action_observed"])
        self.assertTrue(report["original_preserved"])
        self.assertEqual(report["allowances"], dict(source_rounds=1, verify_calls=2, remediations=1))
        self.assertEqual([f["outcome"] for f in report["recheck"]["findings"]], ["PASS", "PASS"])
        self.assertFalse(report["service_state"]["atomic_semantic_ready"])
        trace = [json.loads(line) for line in (target / "runtime-trace/trace.jsonl").read_text("utf-8").splitlines()]
        for kind in ("llm.start", "llm.end", "tool.start", "tool.end", "smoke.tools_offered", "smoke.wire_request"):
            self.assertIn(kind, [e["kind"] for e in trace])
        self.assertTrue(all(w["tool_choice"] == "auto" and "verify_proposal" in w["tools"] for w in report["state"]["wire_requests"]))
        wires = [e["payload"]["body"] for e in trace if e["kind"] == "smoke.wire_request"]
        self.assertTrue(all(body["max_output_tokens"] == 1024 and body["store"] is False for body in wires))

    def test_no_call_and_truncated_or_ignored_feedback_are_honest_outcomes(self):
        for scenario in ("omit", "truncated", "ignore"):
            with self.subTest(scenario=scenario):
                result, report, _ = self.invoke(scenario, "--mode", "scripted", "--scenario", scenario)
                self.assertNotEqual(report["readiness"], "READY_FOR_APPROVAL")
                self.assertFalse(report["provider_generated_verify"])
                if scenario == "omit":
                    self.assertEqual(result.returncode, 1)
                    self.assertFalse(report["dispatch_observed"])
                    self.assertIsNone(report["original"])
                    self.assertFalse(report["observed_progress"])
                elif scenario == "truncated":
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(report["outcome"], "OUTPUT_CAP_WITH_PARTIAL_PROGRESS")
                    self.assertEqual(report["recheck"]["findings"][1]["outcome"], "FAIL")
                else:
                    self.assertEqual(result.returncode, 0)
                    self.assertTrue(report["observed_progress"])
                    self.assertEqual(report["recheck"]["findings"][0]["outcome"], "FAIL")
