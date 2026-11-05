"""Readiness controls; optional actual-import runner tests are separate."""
import unittest
from unittest.mock import patch
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from tools import tradingagents_integration as integration
from tools.tradingagents_integration import PROFILE, ROOT, preflight_plan, approval_template, validate_approval, read_existing_budget


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
        self.assertEqual(PROFILE["model"], "gpt-6.1-sol")

    def test_template_is_not_approval_and_exact_bindings_expiry_are_required(self):
        fixture = dict(origin="AUTHORED_UNIT_ONLY")
        template = approval_template(fixture)
        with self.assertRaises(PermissionError):
            validate_approval(template, fixture)
        authored_approval_double = dict(template, approved=True, approval_id="authored-unit-double-not-user-approval",
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            budget_review="CONFIRMED_UNCHANGED_CUMULATIVE_NO_UNKNOWNS",
            pricing_review="CONFIRMED_ORIGINAL_UPPER_RATES_CONSERVATIVE", model_account_access="CONFIRMED_BY_OPERATOR")
        validate_approval(authored_approval_double, fixture)
        for key, value in (("profile_digest", "wrong"), ("implementation_digest", "wrong"), ("fixture_digest", "wrong"),
                           ("incremental_limit_usd", 5), ("approved", False), ("expires_at", "2020-01-01T00:00:00Z")):
            with self.subTest(key=key), self.assertRaises(PermissionError):
                validate_approval(dict(authored_approval_double, **{key: value}), fixture)

    def test_authored_budget_gate_reads_only_and_refuses_unknowns_or_low_active_headroom(self):
        # Entire store/policy are authored temporary inputs, never the real ledger.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runs").mkdir()
            policy = root / "budget_policy.json"
            policy.write_text(json.dumps(dict(hard_limit_usd=5, initial_limit_usd=5)), "utf-8")
            path = root / "runs/approved-budget.sqlite"
            db = sqlite3.connect(path)
            try:
                db.executescript("CREATE TABLE budget(id INTEGER,reserved REAL); INSERT INTO budget VALUES(1,1);"
                    "CREATE TABLE budget_policy(id INTEGER,initial_limit REAL,active_limit REAL,hard_limit REAL);"
                    "INSERT INTO budget_policy VALUES(1,5,5,5);"
                    "CREATE TABLE requests(id TEXT,charge REAL,status TEXT);")
                db.commit()
                before = path.read_bytes()
                result = read_existing_budget(root)
                self.assertEqual(result["committed_upper"], 1)
                self.assertEqual(before, path.read_bytes())
                db.execute("INSERT INTO requests VALUES('authored-unknown',NULL,'in_flight_or_unknown')")
                db.commit()
                before = path.read_bytes()
                with self.assertRaises(PermissionError):
                    read_existing_budget(root)
                self.assertEqual(before, path.read_bytes())
                db.execute("DELETE FROM requests")
                db.execute("UPDATE budget SET reserved=4.9")
                db.commit()
                before = path.read_bytes()
                with self.assertRaises(PermissionError):
                    read_existing_budget(root)
                self.assertEqual(before, path.read_bytes())
            finally:
                db.close()

    def test_paid_flag_alone_is_rejected_before_child_or_budget(self):
        with patch.object(sys, "argv", ["integration", "--mode", "paid", "--output", ".local-runs/never-created"]), \
             patch.object(integration.subprocess, "run") as child:
            with self.assertRaises(SystemExit):
                integration.main()
            child.assert_not_called()

    def test_supervisor_timeout_retains_unknowns_without_budget_reconciliation(self):
        (ROOT / ".local-runs").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".local-runs", prefix="supervisor-unit-") as directory:
            root = Path(directory).resolve()
            self.assertTrue(root.is_relative_to(ROOT / ".local-runs"))
            target = root / "run"
            with patch.object(sys, "argv", ["integration", "--mode", "scripted", "--upstream", str(root / "upstream/TradingAgents"), "--output", str(target)]), \
                 patch.object(integration.subprocess, "run", side_effect=subprocess.TimeoutExpired("authored-child", 120)):
                self.assertEqual(integration.main(), 1)
            stop = json.loads((target / "supervisor-stop.json").read_text("utf-8"))
            self.assertEqual(stop["outcome"], "WALL_TIMEOUT_NOT_PASS")
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

    def invoke(self, name, *args):
        target = self.root / name
        result = subprocess.run([sys.executable, "-B", str(ROOT / "tools/tradingagents_integration.py"), "--upstream", self.upstream,
            "--output", str(target), *args], cwd=ROOT, capture_output=True, text=True, timeout=40)
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
