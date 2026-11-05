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
from tools.tradingagents_integration import PROFILE, ROOT, preflight_plan, approval_template, validate_approval, read_existing_budget, reviewed_budget_summary, CheckpointTransport
from continuous_verification import digest
from continuous_verification.service import Principal, ServiceBackend
from continuous_verification.tradingagents import BoundaryError


def authored_review(path=None, total=4.288617500000004):
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest() if path else "0"*64
    return dict(budget_sha256_before=fingerprint, budget_sha256_after=fingerprint, unchanged=True,
        reserved_including_existing_holds=str(total), initial_active_hard=[3,10,10], existing_unsettled_rows=2,
        review_version="ten-dollar-two-holds-v1", known_unknown_holds=[
            ["authored-historical-hold", .16024, None, "in_flight_or_unknown", None],
            ["authored-expired-key-hold", .16024, None, "in_flight_or_unknown", None]])


class ReadinessPlanTests(unittest.TestCase):
    def test_default_plan_disables_paid_and_preserves_unknowns(self):
        plan = preflight_plan()
        self.assertFalse(plan["execution_enabled"])
        self.assertIn("NOT_OPENED", plan["budget_status"])
        self.assertIn("NOT_CHECKED", plan["model_access"])
        self.assertEqual(plan["new_user_approval"], "REQUIRED")
        self.assertEqual(PROFILE["tool_choice"], "auto")
        self.assertFalse(PROFILE["live_sources"])
        self.assertEqual(PROFILE["cumulative_hard_limit_usd"], 10)
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
            budget_review="CONFIRMED_TEN_DOLLAR_LEDGER_PRESERVE_BOTH_KNOWN_HOLDS",
            pricing_review="CONFIRMED_ORIGINAL_UPPER_RATES_CONSERVATIVE", model_account_access="UNPROBED_CALL_MAY_FAIL_AND_RETAIN_HOLD")
        validate_approval(authored_approval_double, fixture, output=output, review=review)
        # Previously approved five-dollar/single-hold artifacts are never upgraded.
        old_review = dict(review, initial_active_hard=[3,5,5], existing_unsettled_rows=1)
        old_review.pop("review_version")
        old_review.pop("known_unknown_holds")
        with self.assertRaises(PermissionError):
            reviewed_budget_summary(old_review)
        with self.assertRaises(PermissionError):
            validate_approval(dict(authored_approval_double,
                budget_review="CONFIRMED_PINNED_LEDGER_PRESERVE_KNOWN_HOLD"), fixture, output=output, review=review)
        with self.assertRaises(PermissionError):
            validate_approval(authored_approval_double, fixture, output=output, review=old_review)
        original_read = Path.read_bytes
        for dependency in ("cli.py", "sdk.py", "capture.py", "journal.py", "projection.py", "contract.schema.json"):
            def changed_bytes(path, dependency=dependency):
                content = original_read(path)
                return content + b"\n" if path.name == dependency else content
            with self.subTest(dependency=dependency), patch.object(Path, "read_bytes", changed_bytes):
                with self.assertRaises(PermissionError):
                    validate_approval(authored_approval_double, fixture, output=output, review=review)
        for key, value in (("profile_digest", "wrong"), ("implementation_digest", "wrong"), ("fixture_digest", "wrong"),
                           ("incremental_limit_usd", 5), ("launch_output", ".local-runs/other"),
                           ("verify_transport", "injected-cli"),
                           ("approved", False), ("expires_at", "2020-01-01T00:00:00Z")):
            with self.subTest(key=key), self.assertRaises(PermissionError):
                validate_approval(dict(authored_approval_double, **{key: value}), fixture, output=output, review=review)

    def test_authored_budget_gate_pins_historical_hold_and_rejects_new_or_changed_state(self):
        # Authored temporary DB only; no actual private ledger is opened.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runs").mkdir()
            (root / "budget_policy.json").write_text(json.dumps(dict(hard_limit_usd=10, initial_limit_usd=3)), "utf-8")
            path = root / "runs/approved-budget.sqlite"
            db = sqlite3.connect(path)
            try:
                db.executescript("CREATE TABLE budget(id INTEGER,reserved REAL); INSERT INTO budget VALUES(1,4.288617500000004);"
                    "CREATE TABLE budget_policy(id INTEGER,initial_limit REAL,active_limit REAL,hard_limit REAL);"
                    "INSERT INTO budget_policy VALUES(1,3,10,10);"
                    "CREATE TABLE requests(id TEXT,reserved REAL,charge REAL,status TEXT,response_id TEXT);"
                    "INSERT INTO requests VALUES('authored-historical-hold',0.16024,NULL,'in_flight_or_unknown',NULL);"
                    "INSERT INTO requests VALUES('authored-expired-key-hold',0.16024,NULL,'in_flight_or_unknown',NULL);"
                    "INSERT INTO requests VALUES('authored-settled',3.9,3.473855,'settled','authored-response');")
                db.commit()
                review = authored_review(path)
                before = path.read_bytes()
                initial = read_existing_budget(root, review=review)
                baseline = initial["baseline"]
                self.assertEqual(baseline["hold_ids"], ["authored-expired-key-hold", "authored-historical-hold"])
                self.assertAlmostEqual(initial["required_reserve"], .64096)
                self.assertEqual(before, path.read_bytes())
                # Even with the exact DB hash, the review must explicitly name
                # both actual unknown tuples. Never silently adopt a new hold.
                for field, value in ((0, "wrong-id"), (1, .15), (2, 0), (3, "settled"), (4, "unexpected-response")):
                    bad = deepcopy(review)
                    bad["known_unknown_holds"][1][field] = value
                    with self.subTest(review_field=field), self.assertRaises(PermissionError):
                        read_existing_budget(root, review=bad)
                for bad in (dict(review, known_unknown_holds=review["known_unknown_holds"][:1]),
                            dict(review, known_unknown_holds=[review["known_unknown_holds"][0]]*2),
                            dict(review, existing_unsettled_rows=3),
                            dict(review, initial_active_hard=[3,5,5]),
                            dict(review, initial_active_hard=[3,9,10])):
                    with self.assertRaises(PermissionError):
                        reviewed_budget_summary(bad)
                mutations = [
                    "UPDATE requests SET id='changed' WHERE id='authored-historical-hold'",
                    "UPDATE requests SET reserved=.15 WHERE id='authored-historical-hold'",
                    "UPDATE requests SET status='settled',charge=.01 WHERE id='authored-historical-hold'",
                    "DELETE FROM requests WHERE id='authored-expired-key-hold'",
                    "UPDATE requests SET id='changed' WHERE id='authored-expired-key-hold'",
                    "UPDATE requests SET reserved=.15 WHERE id='authored-expired-key-hold'",
                    "UPDATE requests SET charge=.01,status='settled',response_id='invented' WHERE id='authored-expired-key-hold'",
                    "UPDATE requests SET response_id='invented' WHERE id='authored-expired-key-hold'",
                    "UPDATE requests SET charge=1 WHERE id='authored-settled'",
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
                db.execute("UPDATE budget_policy SET active_limit=5")
                db.commit()
                with self.assertRaises(PermissionError):
                    read_existing_budget(root, review=review, baseline=baseline)
                db.execute("UPDATE budget_policy SET active_limit=10")
                db.commit()
                policy_path = root / "budget_policy.json"
                policy_bytes = policy_path.read_bytes()
                policy_path.write_text(json.dumps(dict(hard_limit_usd=5, initial_limit_usd=3)), "utf-8")
                with self.assertRaises(PermissionError):
                    read_existing_budget(root, review=review, baseline=baseline)
                policy_path.write_bytes(policy_bytes)
                with self.assertRaises(PermissionError):
                    read_existing_budget(root, review=review)  # Physical identity changed since closed review.
                with self.assertRaises(PermissionError):
                    reviewed_budget_summary(authored_review(total=9.9))
                db.execute("INSERT INTO requests VALUES('our-request',.16024,NULL,'in_flight_or_unknown',NULL)")
                db.execute("UPDATE budget SET reserved=?", (baseline["total"]+.16024,))
                db.commit()
                # Only the tracked in-flight reservation at its permitted boundary
                # may be pending. A third retained unknown is never adopted.
                with self.assertRaises(PermissionError):
                    read_existing_budget(root, review=review, baseline=baseline, owned_ids={"our-request"}, remaining_calls=3)
                pending = read_existing_budget(root, review=review, baseline=baseline, owned_ids={"our-request"},
                    allow_pending={"our-request"}, remaining_calls=3)
                self.assertEqual(pending["baseline"], baseline)
                db.execute("UPDATE requests SET charge=.01,status='settled',response_id='authored-new-response' WHERE id='our-request'")
                db.execute("UPDATE budget SET reserved=?", (baseline["total"]+.01,))
                db.commit()
                allowed = read_existing_budget(root, review=review, baseline=baseline, owned_ids={"our-request"},remaining_calls=3)
                for identity in baseline["hold_ids"]:
                    self.assertEqual(allowed["baseline"]["rows"][identity], baseline["rows"][identity])
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


class InjectedCliCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.packet = json.loads((ROOT / "continuous_verification/schemas/example.json").read_text("utf-8"))
        self.packet["events"][1]["payload"]["included_event_ids"] = []
        self.packet["events"][1]["parents"] = []
        self.run = self.packet["request"]["run_id"]
        principal = Principal("collector", frozenset({"configure", "collect", "read", "verify"}), frozenset({self.run}))
        self.backend = ServiceBackend(self.root / "authored-cli.sqlite", principal=principal, service_id="authored-service")
        self.addCleanup(self.backend.close)
        self.backend.configure_run(self.run, [dict(stream_id="host", collector_id="collector", producer_id="authored-host",
            adapter_version="fixture-1", redaction_profile="authored-public")])
        self.backend.execute("register_run", dict(run_id=self.run, registration_id="authored-cli-registration"))
        self.backend.install_policy(self.run, self.packet["policy"])
        self.backend.execute("ingest_events", dict(run_id=self.run, batch_id="authored-cli-batch", events=self.packet["events"]))
        self.backend.record_coverage(self.run, "host", self.packet["checkpoint"]["streams"][0]["capabilities"])
        checkpoint = self.backend.execute("checkpoint", dict(run_id=self.run, checkpoint_id="checkpoint-1", revision=0,
            registry_revision=0, streams=[dict(stream_id="host", requested=3)]))
        self.request = self.packet["request"]
        self.request["checkpoint"]["digest"] = digest(checkpoint)

    def test_actual_cli_parser_exact_request_envelope_exit_and_failing_assessment(self):
        events = []
        route = CheckpointTransport(self.backend, self.run, selection="injected-cli", emit=lambda kind, data: events.append((kind,data)))
        result = route.verify(self.request, origin="MODEL_TOOL_DISPATCH", turn=1, model_call_id="authored-call")
        request_event, result_event = events[0][1], events[1][1]
        self.assertEqual(request_event["request"], self.request)
        self.assertEqual(request_event["checkpoint"], self.request["checkpoint"])
        self.assertEqual(result_event["cli_argv"], ["verify"])
        self.assertEqual(result_event["cli_exit_code"], 0)
        self.assertEqual(result_event["cli_stderr"], "")
        self.assertEqual(result_event["cli_envelope"], {"ok":True,"result":result})
        self.assertEqual(result_event["assessment_id"], result["assessment_id"])
        self.assertEqual(result_event["result_status"], "ASSESSED")
        self.assertEqual(result["disposition"], "HOLD")
        self.assertEqual([f["outcome"] for f in result["findings"]], ["FAIL","PASS"])
        self.assertFalse(result_event["cli_subprocess"])
        self.assertFalse(result_event["agent_shell_command"])
        direct = route.verify(self.request, origin="HOST_RECHECK")
        self.assertEqual(direct, result)
        self.assertEqual(events[-1][1]["transport"], "DIRECT_NATIVE_HOST")
        self.assertIsNone(events[-1][1]["cli_exit_code"])

    def test_actual_cli_safe_denial_retains_exit_and_does_not_invent_assessment(self):
        events = []
        route = CheckpointTransport(self.backend, self.run, selection="injected-cli", emit=lambda kind,data:events.append((kind,data)))
        foreign = deepcopy(self.request)
        foreign["run_id"] = "authored-foreign"
        with self.assertRaises(BoundaryError):
            route.verify(foreign, origin="MODEL_TOOL_DISPATCH",turn=1,model_call_id="authored-denied")
        event = events[-1][1]
        self.assertEqual(event["cli_exit_code"], 3)
        self.assertEqual(event["cli_envelope"]["error"]["code"], "FORBIDDEN")
        self.assertEqual(event["cli_stderr"], "FORBIDDEN\n")
        self.assertIsNone(event["assessment_id"])
        self.assertEqual(event["result_status"], "TRANSPORT_ERROR")


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
                    skipped = [e for e in report["state"]["monitor_events"] if e["kind"] == "smoke.checkpoint_skipped"]
                    self.assertEqual({e["payload"]["origin"] for e in skipped}, {"MODEL_TOOL_DISPATCH","HOST_RECHECK"})
                    self.assertEqual(report["cli_parser_invocations"], 0)
                elif scenario == "truncated":
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(report["outcome"], "OUTPUT_CAP_WITH_PARTIAL_PROGRESS")
                    self.assertEqual(report["recheck"]["findings"][1]["outcome"], "FAIL")
                else:
                    self.assertEqual(result.returncode, 0)
                    self.assertTrue(report["observed_progress"])
                    self.assertEqual(report["recheck"]["findings"][0]["outcome"], "FAIL")

    def test_injected_cli_checkpoint_wire_feedback_turn_monitor_and_unique_run_identity(self):
        direct_process, direct, direct_dir = self.invoke("identity-direct", "--mode", "scripted")
        process, report, target = self.invoke("identity-cli", "--mode", "scripted", "--verify-transport", "injected-cli")
        self.assertEqual(direct_process.returncode,0)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        self.assertNotEqual(direct["run_id"],report["run_id"])
        self.assertNotEqual(direct["launch_id"],report["launch_id"])
        self.assertEqual(report["launch_id"],json.loads((target/"parent.json").read_text("utf-8"))["nonce"])
        self.assertIn(report["launch_id"],report["run_id"])
        self.assertEqual(report["service_state"]["run_id"],report["run_id"])
        self.assertEqual(report["cli_parser_invocations"],1)
        self.assertEqual(report["cli_subprocess_invocations"],0)
        self.assertFalse(report["agent_issued_shell_command"])
        monitor = [json.loads(line) for line in (target/"turns-checkpoints.jsonl").read_text("utf-8").splitlines()]
        self.assertTrue(all(e["run_id"]==report["run_id"] for e in monitor))
        self.assertEqual([e["payload"]["turn"] for e in monitor if e["kind"]=="smoke.turn_start"],[1,2,3])
        request_starts = [e for e in monitor if e["kind"]=="smoke.request_start"]
        self.assertEqual([e["payload"]["first_request"] for e in request_starts],[True,False,False])
        checkpoints = [e["payload"] for e in monitor if e["kind"]=="smoke.checkpoint_result"]
        self.assertEqual([e["origin"] for e in checkpoints],["MODEL_TOOL_DISPATCH","HOST_RECHECK"])
        cli, host = checkpoints
        self.assertEqual(cli["transport"],"HOST_INJECTED_CLI_PARSER")
        self.assertEqual(cli["cli_exit_code"],0)
        self.assertEqual(cli["cli_envelope"],{"ok":True,"result":report["original"]})
        self.assertEqual(cli["assessment_id"],report["original"]["assessment_id"])
        self.assertEqual(cli["checkpoint"],report["requests"][0]["checkpoint"])
        self.assertEqual(host["transport"],"DIRECT_NATIVE_HOST")
        self.assertEqual(host["assessment_id"],report["recheck"]["assessment_id"])
        trace = [json.loads(line) for line in (target/"runtime-trace/trace.jsonl").read_text("utf-8").splitlines()]
        next_wire = next(e["payload"]["body"] for e in trace if e["kind"]=="smoke.wire_request" and e["payload"]["proof"]["call"]==2)
        feedback = next(item for item in next_wire["input"] if item.get("type")=="function_call_output" and item.get("call_id")==cli["model_call_id"])
        self.assertEqual(json.loads(feedback["output"]),cli["cli_envelope"]["result"])
        self.assertEqual(report["allowances"],dict(source_rounds=1,verify_calls=2,remediations=1))
        self.assertFalse(report["provider_generated_verify"])
