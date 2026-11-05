"""Offline controls only; authored sources/Responses never establish market facts."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from tools import correction_experiment as experiment
from tools.tradingagents_integration import real_runtime, checked_upstream


def review():
    return dict(review_version="ten-dollar-two-holds-v1",budget_sha256_before="0"*64,budget_sha256_after="0"*64,
        unchanged=True,reserved_including_existing_holds="4.343925",initial_active_hard=[3,10,10],existing_unsettled_rows=2,
        known_unknown_holds=[["authored-old",.16024,None,"in_flight_or_unknown",None],
                             ["authored-authfail",.16024,None,"in_flight_or_unknown",None]])


class Controls(unittest.TestCase):
    def test_full_window_scheduling_stop_and_near_deadline_no_request(self):
        clock=[0.0];progress=[]
        waited=experiment.wait_slot(420,deadline=420,clock=lambda:clock[0],sleep=lambda n:clock.__setitem__(0,clock[0]+n),
            stopped=lambda:False,progress=progress.append)
        self.assertEqual((clock[0],waited),(420,420))
        self.assertTrue(progress)
        clock[0]=0
        with self.assertRaises(experiment.BoundaryError):
            experiment.wait_slot(180,deadline=420,clock=lambda:clock[0],sleep=lambda n:clock.__setitem__(0,clock[0]+n),
                stopped=lambda:clock[0]>=3)
        self.assertEqual(clock[0],3)
        with self.assertRaises(experiment.BoundaryError):
            experiment.wait_slot(421,deadline=420,clock=lambda:clock[0],sleep=lambda n:None,stopped=lambda:False)
        clock[0]=391
        limits=experiment.PhaseLimits(experiment.model_profile(),start=0,clock=lambda:clock[0]);limits.phase="correction"
        with self.assertRaises(experiment.BoundaryError): limits.model()
        self.assertEqual(sum(limits.calls.values()),0)

    def test_profiles_phase_deadlines_call_caps_and_reserve_fit(self):
        terra=experiment.model_profile(); sol=experiment.model_profile("gpt-6.1-sol")
        self.assertEqual(experiment.reviewed_budget_summary(review(),profile=terra)["proposed_worst_reserve"],1.76264)
        self.assertEqual(experiment.reviewed_budget_summary(review(),profile=sol)["proposed_worst_reserve"],3.52528)
        self.assertLess(4.343925+1.76264+3.52528,10)
        clock=[0.0]; limits=experiment.PhaseLimits(terra,start=0,clock=lambda:clock[0])
        for _ in range(6): limits.model()
        with self.assertRaises(experiment.BoundaryError): limits.model()
        limits.phase="correction"
        for _ in range(5): limits.model()
        with self.assertRaises(experiment.BoundaryError): limits.model()
        clock[0]=420
        with self.assertRaises(experiment.BoundaryError): limits.check()
        with self.assertRaises(PermissionError): experiment.checked_profile(dict(terra,wall_seconds=421))
        with self.assertRaises(ValueError): experiment.model_profile("unreviewed")
        clock[0]=151; limits=experiment.PhaseLimits(terra,start=0,clock=lambda:clock[0])
        with self.assertRaises(experiment.BoundaryError): limits.model()

    def test_new_approval_exact_model_source_policy_dependency_and_old_smoke_reject(self):
        with patch.object(experiment,"implementation_digest",return_value="test-implementation"):
            profile=experiment.model_profile(); source="a"*64; baseline=review()
            output=experiment.ROOT/".local-runs/authored-never-launched"
            template=experiment.approval_template(profile,source,baseline)
            with self.assertRaises(PermissionError):
                experiment.validate_approval(template,profile=profile,bundle_sha256=source,review=baseline,output=output)
            approved=dict(template,approved=True,approval_id="authored-test-not-human-approval",launch_output=str(output),
                expires_at=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
                budget_review="CONFIRMED_BOTH_KNOWN_HOLDS_ALL_ROWS_CARRY_PRESERVED",pricing_review="CONFIRMED_CONSERVATIVE_FOR_SELECTED_MODEL",
                source_review="CONFIRMED_REAL_FRESH_MARKET_NEWS_SAME_BUNDLE_FOR_BOTH_ARMS")
            experiment.validate_approval(approved,profile=profile,bundle_sha256=source,review=baseline,output=output)
            for key,value in (("milestone","actual-imported-analyst-smoke-v1"),("model","gpt-6.1-sol"),
                    ("source_bundle_sha256","b"*64),("policy_digest","other"),("implementation_digest","edited"),
                    ("budget_review_digest","other"),("incremental_limit_usd",10),("profile_digest","other")):
                with self.subTest(key=key),self.assertRaises(PermissionError):
                    experiment.validate_approval(dict(approved,**{key:value}),profile=profile,bundle_sha256=source,review=baseline,output=output)

    def test_budget_two_full_hold_tuples_old_review_third_hold_carry_and_own_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"runs").mkdir()
            (root/"budget_policy.json").write_text(json.dumps(dict(initial_limit_usd=3,hard_limit_usd=10)),"utf-8")
            path=root/"runs/approved-budget.sqlite";db=sqlite3.connect(path)
            db.executescript("CREATE TABLE budget(id INTEGER,reserved REAL); INSERT INTO budget VALUES(1,4.343925);"
                "CREATE TABLE budget_policy(id INTEGER,initial_limit REAL,active_limit REAL,hard_limit REAL); INSERT INTO budget_policy VALUES(1,3,10,10);"
                "CREATE TABLE requests(id TEXT,reserved REAL,charge REAL,status TEXT,response_id TEXT);")
            baseline=review()
            db.executemany("INSERT INTO requests VALUES(?,?,?,?,?)",baseline["known_unknown_holds"]+[["settled",4,.01,"settled","authored-receipt"]]);db.commit()
            import hashlib
            baseline.update(budget_sha256_before=hashlib.sha256(path.read_bytes()).hexdigest(),budget_sha256_after=hashlib.sha256(path.read_bytes()).hexdigest())
            before=path.read_bytes(); state=experiment.read_existing_budget(root,review=baseline)
            self.assertEqual(before,path.read_bytes())
            for sql in ("UPDATE requests SET id='changed' WHERE id='authored-old'","DELETE FROM requests WHERE id='authored-authfail'",
                        "UPDATE requests SET charge=.1,status='settled' WHERE id='authored-authfail'",
                        "INSERT INTO requests VALUES('third',.16024,NULL,'in_flight_or_unknown',NULL)","UPDATE budget SET reserved=4.4"):
                db.execute(sql);db.commit()
                with self.subTest(sql=sql),self.assertRaises(PermissionError):
                    experiment.read_existing_budget(root,review=baseline,baseline=state["baseline"])
                db.execute("DELETE FROM requests");db.executemany("INSERT INTO requests VALUES(?,?,?,?,?)",list(state["baseline"]["rows"].values()))
                db.execute("UPDATE budget SET reserved=4.343925");db.commit()
            with self.assertRaises(PermissionError): experiment.reviewed_budget_summary(dict(baseline,existing_unsettled_rows=1))
            db.execute("INSERT INTO requests VALUES('terra-own',.16024,NULL,'in_flight_or_unknown',NULL)")
            db.execute("UPDATE budget SET reserved=?",(4.343925+.16024,));db.commit()
            experiment.read_existing_budget(root,review=baseline,baseline=state["baseline"],owned_ids={"terra-own"},allow_pending={"terra-own"},remaining_calls=10)
            with self.assertRaises(PermissionError):
                experiment.read_existing_budget(root,review=baseline,baseline=state["baseline"],owned_ids={"terra-own"},remaining_calls=10)
            db.execute("UPDATE requests SET charge=.1,status='settled',response_id='authored-terra-receipt' WHERE id='terra-own'")
            db.execute("UPDATE budget SET reserved=?",(4.443925,));db.commit()
            experiment.read_existing_budget(root,review=baseline,baseline=state["baseline"],owned_ids={"terra-own"},remaining_calls=10)
            # New explicit post-Terra closed review, never automatic adoption.
            second=review();second.update(budget_sha256_before=hashlib.sha256(path.read_bytes()).hexdigest(),
                budget_sha256_after=hashlib.sha256(path.read_bytes()).hexdigest(),reserved_including_existing_holds="4.443925")
            sol=experiment.model_profile("gpt-6.1-sol")
            next_state=experiment.read_existing_budget(root,review=second,profile=sol)
            self.assertIn("terra-own",next_state["baseline"]["rows"])
            db.execute("INSERT INTO requests VALUES('sol-own',.32048,NULL,'in_flight_or_unknown',NULL)")
            db.execute("UPDATE budget SET reserved=?",(4.443925+.32048,));db.commit()
            experiment.read_existing_budget(root,review=second,profile=sol,baseline=next_state["baseline"],owned_ids={"sol-own"},allow_pending={"sol-own"},remaining_calls=10)
            db.close()

    def test_paid_flag_without_exact_correction_approval_rejects_before_child(self):
        with patch.object(sys,"argv",["experiment","--mode","paid","--source-bundle","unused","--output","unused"]),patch.object(experiment.subprocess,"run") as child:
            with self.assertRaises(SystemExit): experiment.main()
            child.assert_not_called()


class AuthoredSource:
    """Test-only internal replay double, not a source bundle/market capture format."""
    ticker="ETH-USD";asset_type="crypto";as_of="2026-11-05";context="AUTHORED source double, no actual data"
    catalog=[dict(tool=name,args=args,status="AVAILABLE") for name,args in [
        ("get_stock_data",dict(symbol="ETH-USD",start_date="2026-09-06",end_date="2026-11-05",trade_date="2026-11-05")),
        ("get_indicators",dict(symbol="ETH-USD",indicator="rsi",curr_date="2026-11-05",look_back_days=10,trade_date="2026-11-05")),
        ("get_indicators",dict(symbol="ETH-USD",indicator="macd",curr_date="2026-11-05",look_back_days=10,trade_date="2026-11-05")),
        ("get_verified_market_snapshot",dict(symbol="ETH-USD",curr_date="2026-11-05",look_back_days=10,trade_date="2026-11-05")),
        ("get_news",dict(ticker="ETH-USD",start_date="2026-10-29",end_date="2026-11-05",trade_date="2026-11-05"))]]
    bundle_sha256="a"*64
    manifest={"origin":"AUTHORED_OFFLINE_ONLY","coverage":["market","news"],"gaps":[]}
    def __init__(self,status="AVAILABLE",size=0): self.status=status;self.size=size
    def native_tools(self,runtime):
        from tradingagents.agents.analysts import news_analyst
        return (*runtime["market"].TOOLS,news_analyst.TOOLS[0])
    def replay(self,name,args):
        if self.status=="RAISE": raise RuntimeError("AUTHORED invocation failure, no source response")
        return dict(text="AUTHORED source "+name+" "+"x"*self.size,status=self.status,source_status=self.status,
            arguments=args,source_refs=["authored-only"],captured_at="2026-11-05T00:00:00Z")


def responses(scenario):
    research=0
    def response(body,state):
        nonlocal research
        if scenario=="provider_error":
            import httpx
            raise httpx.ReadTimeout("AUTHORED transport timeout, no provider request")
        names=[tool["name"] for tool in body.get("tools",[])]
        if names==["verify_proposal"]:
            name="verify_proposal";args={}
            if scenario=="omit_verify": name=None
        elif state["revision"]==0:
            research+=1
            if scenario=="clean_sequence" and research<=4:
                name,args=[("get_stock_data",dict(start_date="2026-09-06",end_date="2026-11-05")),
                    ("get_indicators",dict(indicator="rsi",curr_date="2026-11-05",look_back_days=10)),
                    ("get_verified_market_snapshot",dict(curr_date="2026-11-05",look_back_days=10)),
                    ("get_news",dict(start_date="2026-10-29",end_date="2026-11-05"))][research-1]
            else: name=None
        elif not any(r.get("status")=="AVAILABLE" for r in state["source_records"].values()) and scenario not in {"ignore","unavailable"}:
            name="get_verified_market_snapshot";args=dict(curr_date="2026-11-05",look_back_days=10)
        else: name=None
        count=len(state["wire"])
        if name:
            output=[dict(type="function_call",id=f"fc_authored_{count}",call_id=f"authored-call-{count}",name=name,arguments=json.dumps(args),status="completed")]
        else:
            output=[dict(type="message",id=f"msg_authored_{count}",role="assistant",status="completed",content=[dict(type="output_text",text=f"AUTHORED provider-I/O report rev{state['revision']}; evidence gaps retained.",annotations=[])])]
        truncated=scenario=="truncated" and state["revision"]==0 and name is None
        return dict(id=f"resp_authored_{count}",object="response",created_at=0,status="incomplete" if truncated else "completed",
            incomplete_details=dict(reason="max_output_tokens") if truncated else None,model=body["model"],output=output,
            usage=dict(input_tokens=100,output_tokens=100,total_tokens=200,input_tokens_details=dict(cached_tokens=0),output_tokens_details=dict(reasoning_tokens=0)))
    return response


class ImportedProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream=os.environ.get("TRUSTKERNEL_TRADINGAGENTS_UPSTREAM")
        if not cls.upstream or importlib.util.find_spec("langchain_openai") is None:
            raise unittest.SkipTest("Actual native client/ToolNode NOT RUN without optional pinned dependencies")
    def run_case(self,scenario="correct",status="AVAILABLE",size=0,model="gpt-6.1-terra"):
        (experiment.ROOT/".local-runs").mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=experiment.ROOT/".local-runs",prefix="correction-tests-")
        self.addCleanup(self.temp.cleanup); target=Path(self.temp.name)
        import uuid
        with real_runtime(checked_upstream(self.upstream)) as runtime:
            result=experiment.run_arm(runtime,target,AuthoredSource(status,size),profile=experiment.model_profile(model),mode="scripted",
                launch_id=uuid.uuid4().hex,authored=responses(scenario))
        events=[json.loads(x) for x in (target/"phases-turns.jsonl").read_text("utf-8").splitlines()]
        return result,events,target

    def test_actual_initial_report_model_cli_feedback_revision_new_prefix_and_model_recheck(self):
        result,events,target=self.run_case(model="gpt-6.1-sol")
        self.assertEqual(result["outcome"],"CORRECTION_RECHECK_RECORDED",result)
        self.assertEqual([r["payload"]["revision"] for r in result["reports"]],[0,1])
        self.assertEqual([f["outcome"] for f in result["assessments"][0]["findings"]],["FAIL","PASS"])
        self.assertEqual([f["outcome"] for f in result["assessments"][1]["findings"]],["PASS","PASS"])
        self.assertTrue(result["original_assessments_preserved"])
        self.assertEqual(len([e for e in events if e["kind"]=="checkpoint.model_requested"]),2)
        self.assertEqual(len([e for e in events if e["kind"]=="checkpoint.cli_result"]),2)
        self.assertTrue(result["wire_proofs"][2]["feedback_call_in_wire"])
        self.assertTrue(result["wire_proofs"][2]["feedback_in_wire"])
        self.assertNotEqual(result["requests"][0]["checkpoint"],result["requests"][1]["checkpoint"])
        self.assertGreaterEqual(result["observation_seconds"],420)
        self.assertLess(result["elapsed_seconds"],20)
        self.assertEqual(result["timing_mode"],"AUTHORED_SIMULATED_SCHEDULE")
        self.assertFalse(result["provider_generated_reports"])
        self.assertFalse(result["service_state"]["atomic_semantic_ready"])

    def test_clean_real_native_stock_indicator_snapshot_news_sequence_never_induces_failure(self):
        result,events,_=self.run_case("clean_sequence")
        self.assertEqual(result["outcome"],"NO_CORRECTION_NEEDED",result)
        self.assertEqual(result["calls"],dict(research=5,correction=1))
        self.assertEqual(len(result["reports"]),1)
        self.assertEqual([e["payload"]["name"] for e in events if e["kind"]=="source.call"],
            ["get_stock_data","get_indicators","get_verified_market_snapshot","get_news"])

    def test_model_omits_verifier_no_host_fallback_or_assessment(self):
        result,events,_=self.run_case("omit_verify")
        self.assertEqual(result["outcome"],"STOPPED_PARTIAL_NOT_PASS")
        self.assertEqual(result["assessments"],[])
        self.assertFalse(any(e["kind"]=="checkpoint.cli_request" for e in events))
        self.assertLess(result["observation_seconds"],420)

    def test_returned_unavailable_string_never_establishes_snapshot_success(self):
        result,events,_=self.run_case("clean_sequence",status="NO_DATA")
        self.assertEqual(result["assessments"][0]["findings"][0]["outcome"],"FAIL")
        snapshots=[e["payload"] for e in events if e["kind"]=="source.delivered" and e["payload"]["source_status"]=="NO_DATA"]
        self.assertTrue(snapshots)
        self.assertTrue(all(e["status"]=="ERROR" for e in snapshots))
        self.assertTrue(all(record["source_status"]=="NO_DATA" for record in result["source_records"].values()))

    def test_invocation_failure_and_provider_timeout_are_explicit_no_success_or_retry(self):
        result,events,_=self.run_case("clean_sequence",status="RAISE")
        self.assertEqual(result["outcome"],"STOPPED_PARTIAL_NOT_PASS")
        self.assertEqual(result["assessments"],[])
        self.assertTrue(any(e["kind"]=="source.invocation_error" and e["payload"]["call_id"] for e in events))
        result,events,_=self.run_case("provider_error")
        self.assertEqual(sum(result["calls"].values()),1)
        self.assertEqual(len(result["wire_proofs"]),1)
        self.assertEqual(result["reports"],[])
        self.assertFalse(result["provider_generated_reports"])
        self.assertFalse(any(e["kind"]=="checkpoint.cli_request" for e in events))

    def test_truncated_report_retained_and_cli_completion_fails_then_rechecks_revision(self):
        result,_,_=self.run_case("truncated")
        self.assertEqual(result["reports"][0]["payload"]["completion"],"TRUNCATED")
        self.assertEqual(result["assessments"][0]["findings"][1]["outcome"],"FAIL")

    def test_noncompliance_does_not_become_repair_and_oversize_evidence_is_not_truncated(self):
        result,_,_=self.run_case("ignore")
        self.assertEqual(result["assessments"][1]["findings"][0]["outcome"],"FAIL")
        result,events,_=self.run_case("correct",size=50000)
        self.assertEqual(result["outcome"],"STOPPED_PARTIAL_NOT_PASS")
        self.assertEqual(len(result["reports"]),1)
        self.assertTrue(any(e["kind"]=="model.input_bound_exceeded" for e in events))

    def test_combined_envelope_preflight_serializes_actual_full_history_and_blocks_oversize(self):
        with real_runtime(checked_upstream(self.upstream)) as runtime:
            estimate=experiment.envelope_preflight(runtime,AuthoredSource(),experiment.model_profile())
            self.assertTrue(estimate["fits"],estimate)
            self.assertEqual(len(estimate["measurements"]),3)
            self.assertEqual(estimate["provider_requests"],0)
            blocked=experiment.envelope_preflight(runtime,AuthoredSource(size=5000),experiment.model_profile())
            self.assertFalse(blocked["fits"],blocked)
            self.assertTrue(any(m["wire_bytes"]>40000 or m["budget_envelope_bytes"]>50000 for m in blocked["measurements"]))

if __name__=="__main__": unittest.main()
