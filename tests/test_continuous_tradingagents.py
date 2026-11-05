"""Temporary authored packets; real accepted A core, no B persistence claim."""
import ast
from collections import Counter
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Annotated
import unittest
from unittest.mock import patch

from continuous_verification import CONTRACT_VERSION, ContractError, digest, text_digest, verify, validate_event
from continuous_verification.tradingagents import (
    BoundaryError, FeedbackBoundary, HostEventCapture, Limits, UPSTREAM_COMMIT,
    make_verify_tool, make_trusted_model, observe_native_returns, TRUSTED_INSTRUCTION,
    make_stored_assessor, make_host_ingest,
)


def authored_packet(revision=0, *, snapshot=True, completion="COMPLETE", boundary="ASSEMBLED"):
    # This checkpoint/service declaration is a clearly authored test double.
    capture = HostEventCapture(run_id="authored-run", stream_id="host", producer_id="authored-host",
        redaction_profile="authored-public", redact=lambda s: s, emit=lambda e: None)
    for r in range(revision + 1):
        result = capture.tool_result(call_id=f"snapshot-{r}", tool_name="authored_snapshot",
            content="Authored provider defect Close=99 Low=100; no invented repair", status="SUCCESS")
        input_event = capture.model_input(messages=[dict(role="tool", content=result["content"])],
            report_id="market-report", report_revision=r,
            included_event_ids=[result["event_id"]] if snapshot else [], boundary=boundary)
        report = capture.report(content=f"Authored report revision {r}; provider defect remains",
            report_id="market-report", revision=r, input_event_id=input_event["event_id"],
            completion=completion, phase="CLOSED")
    count = len(capture.events)
    checkpoint = dict(contract_version=CONTRACT_VERSION, run_id="authored-run",
        checkpoint_id=f"authored-prefix-{revision}", revision=revision,
        established_by=dict(service_id="authored-service-double", basis="SERVICE_ESTABLISHED"), created_at=None,
        streams=[dict(stream_id="host", requested=count, ingested_through=count, projected_through=count,
                      gaps=[], capabilities=[dict(name=name, state="CAPTURED", basis_event_ids=[input_event["event_id"]])
                      for name in ("phase_boundaries", "report_completion", "model_input", "tool_lifecycle")])])
    policy = dict(contract_version=CONTRACT_VERSION, policy_id="authored-offline", version="1",
        required_tool="authored_snapshot", checks=[dict(check_id=check, on_fail="HOLD", on_inconclusive="RECHECK")
        for check in ("required_snapshot_before_market_report", "report_completion")])
    proposal = dict(proposal_id="paper-proposal", revision=revision, content="Authored paper Hold; no trade",
        content_digest=text_digest("Authored paper Hold; no trade"), report_event_id=report["event_id"],
        report_id="market-report", report_revision=revision, dependencies=None, dependency_completeness="UNKNOWN")
    request = dict(contract_version=CONTRACT_VERSION, run_id="authored-run", request_id=f"request-{revision}",
        proposal=proposal, checkpoint=dict(checkpoint_id=checkpoint["checkpoint_id"], revision=revision, digest=digest(checkpoint)),
        policy=dict(policy_id=policy["policy_id"], version=policy["version"], digest=digest(policy),
                    checks=[c["check_id"] for c in policy["checks"]]), checks=[c["check_id"] for c in policy["checks"]])
    return dict(request=request, checkpoint=checkpoint, events=deepcopy(capture.events), policy=policy)


class BoundaryTests(unittest.TestCase):
    def test_provisional_B_seam_forwards_stored_refs_and_requires_ingest_receipt(self):
        packet = authored_packet()
        calls = []
        class AuthoredServiceDouble:
            def execute(self, operation, request):
                calls.append((operation, deepcopy(request)))
                if operation == "verify":
                    # Real accepted A core, authored in-memory service view only.
                    return verify(request, **{k: v for k, v in packet.items() if k != "request"})
                return {"authored_receipt": True}
        backend = AuthoredServiceDouble()
        host = self.make_boundary(assess=make_stored_assessor(backend))
        host.submit(**packet)
        self.deliver(host)
        self.assertEqual(calls[0], ("verify", packet["request"]))
        ingest = make_host_ingest(backend, run_id="authored-run", accept_receipt=lambda *_: False)
        with self.assertRaisesRegex(BoundaryError, "receipt"):
            ingest(packet["events"][0])
        accepted = make_host_ingest(backend, run_id="authored-run", accept_receipt=lambda r, e: r.get("authored_receipt") is True)
        accepted(packet["events"][0])
        self.assertEqual(calls[-1][1], calls[-2][1])
        self.assertEqual(set(calls[-1][1]), {"run_id", "batch_id", "events"})
        wrong_run = deepcopy(packet["events"][0])
        wrong_run["run_id"] = "other"
        with self.assertRaises(BoundaryError):
            accepted(wrong_run)

    def make_boundary(self, **kwargs):
        self.observations = []
        defaults = dict(run_id="authored-run", proposal_id="paper-proposal", assess=verify,
                        emit=lambda kind, data: self.observations.append((kind, data)))
        return FeedbackBoundary(**(defaults | kwargs))

    def deliver(self, host):
        payload = host.verify()
        call_id = f"verify-{host.counts['verify_calls']}"
        host.observe_tool_return(call_id, payload)
        host.observe_next_input("authored-next-input", [(call_id, payload)])
        return json.loads(payload)

    def report_event(self, packet):
        return next(e for e in packet["events"] if e["event_id"] == packet["request"]["proposal"]["report_event_id"])

    def test_accepted_binding_real_core_and_report_proposal_separation(self):
        packet = authored_packet()
        host = self.make_boundary(authorize=lambda *_: True)
        host.submit(**packet)
        result = self.deliver(host)
        self.assertEqual([f["outcome"] for f in result["findings"]], ["PASS", "PASS"])
        self.assertTrue(host.report_boundary_allowed(self.report_event(packet)))
        same_text_new_report = deepcopy(self.report_event(packet))
        same_text_new_report["event_id"] = "new-report-event"
        same_text_new_report["payload"]["revision"] += 1
        self.assertFalse(host.report_boundary_allowed(same_text_new_report))
        self.assertFalse(host.report_boundary_allowed(packet["request"]["proposal"]["content"]))
        self.assertEqual(result["scope"], "declared_checks_at_checkpoint")
        self.assertEqual(packet["request"]["proposal"]["dependency_completeness"], "UNKNOWN")
        host.packet["request"]["proposal"]["content"] += " changed downstream decision"
        host.packet["request"]["proposal"]["content_digest"] = text_digest(host.packet["request"]["proposal"]["content"])
        self.assertFalse(host.report_boundary_allowed(self.report_event(packet)))

    def test_delivery_input_ack_and_at_use_authorizer_are_distinct(self):
        packet = authored_packet()
        allowed = [True]
        host = self.make_boundary(authorize=lambda *_: allowed[0])
        host.submit(**packet)
        text = self.report_event(packet)
        self.assertFalse(host.report_boundary_allowed(text))  # Omitted verify.
        payload = host.verify()
        host.observe_tool_return("c", payload)
        host.acknowledge(host.feedback["assessment_id"], "Authored acknowledgement")
        self.assertFalse(host.report_boundary_allowed(text))
        host.observe_next_input("i", [("other", payload), ("c", "different")])
        self.assertFalse(host.report_boundary_allowed(text))
        host.observe_next_input("i2", [("c", payload)])
        self.assertTrue(host.report_boundary_allowed(text))
        self.assertFalse(host.report_boundary_allowed("Invented revised report Close=101"))
        allowed[0] = False
        self.assertFalse(host.report_boundary_allowed(text))

    def test_revision_rejects_old_result_and_identity_reuse(self):
        host = self.make_boundary()
        first = authored_packet()
        host.submit(**first)
        old_result = self.deliver(host)
        changed = deepcopy(first)
        changed["request"]["proposal"]["report_revision"] = 9
        with self.assertRaises(ContractError):
            host.submit(**changed)
        second = authored_packet(1)
        host.submit(**second)
        host.assess = lambda **_: old_result
        with self.assertRaisesRegex(BoundaryError, "Stale"):
            host.verify()
        self.assertEqual(host.proposals[0], first["request"]["proposal"])
        self.assertFalse(host.report_boundary_allowed(self.report_event(second)))

    def test_evidence_policy_checkpoint_bindings_and_malformed_result(self):
        original = authored_packet()
        old_result = verify(**original)
        for field in ("events", "checkpoint", "policy", "malformed"):
            with self.subTest(field=field):
                packet = deepcopy(original)
                if field == "events":
                    packet["events"][0]["content"] += " changed"
                    packet["events"][0]["content_digest"] = text_digest(packet["events"][0]["content"])
                elif field == "checkpoint":
                    packet["checkpoint"]["created_at"] = "2026-11-05T12:00:00Z"
                    packet["request"]["checkpoint"]["digest"] = digest(packet["checkpoint"])
                elif field == "policy":
                    packet["policy"]["version"] = "2"
                    packet["request"]["policy"].update(version="2", digest=digest(packet["policy"]))
                host = self.make_boundary(assess=lambda **_: {} if field == "malformed" else old_result)
                host.submit(**packet)
                with self.assertRaises((BoundaryError, ContractError)):
                    host.verify()

    def test_unknown_input_never_promoted_and_unready_gap_error_hold(self):
        packets = [authored_packet(boundary="UNKNOWN"), authored_packet(snapshot=False), authored_packet(completion="TRUNCATED")]
        lag, gap, cycle = authored_packet(), authored_packet(), authored_packet()
        lag["checkpoint"]["streams"][0]["projected_through"] = 1
        gap["checkpoint"]["streams"][0]["gaps"] = [[1, 1]]
        cycle["events"][0]["parents"] = [cycle["events"][-1]["event_id"]]
        for p in (lag, gap):
            p["request"]["checkpoint"]["digest"] = digest(p["checkpoint"])
        packets += [lag, gap, cycle]
        for packet in packets:
            with self.subTest(kind=packet["checkpoint"]["streams"][0]):
                host = self.make_boundary(authorize=lambda *_: True)
                host.submit(**packet)
                result = self.deliver(host)
                self.assertIn(result["disposition"], {"HOLD", "RECHECK"})
                self.assertFalse(host.report_boundary_allowed(self.report_event(packet)))

    def test_limits_timeout_failed_refresh_and_terminal_abstention(self):
        host = self.make_boundary(limits=Limits(1, 2, 1), authorize=lambda *_: True)
        host.submit(**authored_packet())
        self.deliver(host)
        def unavailable():
            raise TimeoutError("authored source failure")
        with self.assertRaises(TimeoutError):
            host.source_round([unavailable])
        self.assertEqual(host.counts, dict(source_rounds=1, verify_calls=1, remediations=0))
        with self.assertRaises(BoundaryError):
            host.source_round([])
        host.submit(**authored_packet(1))
        def timeout(**_):
            raise TimeoutError("authored backend failure")
        host.assess = timeout
        with self.assertRaises(TimeoutError):
            host.verify()
        with self.assertRaises(BoundaryError):
            host.verify()
        with self.assertRaises(BoundaryError):
            host.submit(**authored_packet(2))
        host.abstain("Provider defect cannot be corrected by inventing a price")
        self.assertFalse(host.report_boundary_allowed("any report"))

    def test_authored_omission_recheck_preserves_failure_and_defect(self):
        host = self.make_boundary()
        host.submit(**authored_packet(snapshot=False))
        first = self.deliver(host)
        self.assertEqual(first["findings"][0]["outcome"], "FAIL")
        host.acknowledge(first["assessment_id"], "Authored acknowledgement, no correction inferred")
        host.submit(**authored_packet(1))
        second = self.deliver(host)
        self.assertEqual(second["findings"][0]["outcome"], "PASS")
        self.assertNotEqual(first["binding"], second["binding"])
        self.assertIn("Close=99 Low=100", host.packet["events"][0]["content"])
        # PASS is only required-tool delivery, never validation of these prices.
        self.assertFalse(host.report_boundary_allowed(self.report_event(host.packet)))

    def test_capture_redaction_explicit_unknown_and_exact_causal_links(self):
        saved = []
        capture = HostEventCapture(run_id="authored", stream_id="host", producer_id="host",
            redaction_profile="authored-test", redact=lambda s: s.replace("PRIVATE", "[REDACTED]"), emit=saved.append)
        result = capture.tool_result(call_id="c", tool_name="snapshot", content="PRIVATE Close=99 Low=100", status="UNKNOWN")
        self.assertNotIn("PRIVATE", result["content"])
        self.assertEqual(result["content_digest"], text_digest(result["content"]))
        self.assertEqual(capture.tool_result(call_id="c", tool_name="snapshot", content="PRIVATE Close=99 Low=100", status="UNKNOWN"), result)
        with self.assertRaises(BoundaryError):
            capture.tool_result(call_id="c", tool_name="snapshot", content="Close=101", status="SUCCESS")
        input_event = capture.model_input(messages=[dict(role="tool", content=result["content"])], report_id="report",
            report_revision=0, included_event_ids=[result["event_id"]], boundary="UNKNOWN")
        report = capture.report(content="Authored report", report_id="report", revision=0,
            input_event_id=input_event["event_id"], completion="UNKNOWN", phase="UNKNOWN")
        self.assertEqual(input_event["payload"]["boundary"], "UNKNOWN")
        self.assertEqual(input_event["parents"], [result["event_id"]])
        self.assertEqual(report["parents"], [input_event["event_id"]])
        acknowledgement = capture.feedback(event_type="feedback_acknowledgement", assessment_id="authored-assessment",
            proposal_id="paper-proposal", proposal_revision=0, related_event_ids=[report["event_id"]],
            content="Authored acknowledgement; no correction inferred")
        self.assertEqual(acknowledgement["event_type"], "feedback_acknowledgement")
        for event in saved:
            validate_event(event)


class NativePinnedDispatchTests(unittest.TestCase):
    """Exact function ASTs with real LangGraph; no upstream package side effects.

    Source subset extraction is deliberate: importing the whole upstream package
    also loads provider and configuration modules. No source function is rewritten.
    This does not prove full GraphSetup integration or persistent restart resume.
    """

    @classmethod
    def setUpClass(cls):
        location = os.environ.get("TRUSTKERNEL_TRADINGAGENTS_UPSTREAM")
        if not location:
            raise unittest.SkipTest("Native integration NOT RUN: pinned source path not supplied")
        root = Path(location).resolve()
        pin = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        if pin != UPSTREAM_COMMIT:
            raise RuntimeError("Pinned source mismatch")
        try:
            from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
            from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
            from langchain_core.runnables import Runnable
            from langgraph.graph import END, START, StateGraph, MessagesState
            from langgraph.prebuilt import ToolNode
            from typing_extensions import TypedDict
        except ImportError as exc:
            raise unittest.SkipTest(f"Native integration NOT RUN: optional dependency missing: {exc.name}")
        import json
        namespace = dict(AIMessage=AIMessage, HumanMessage=HumanMessage, ToolMessage=ToolMessage,
                         ChatPromptTemplate=ChatPromptTemplate, MessagesPlaceholder=MessagesPlaceholder,
                         END=END, START=START, StateGraph=StateGraph, ToolNode=ToolNode,
                         MessagesState=MessagesState, TypedDict=TypedDict, Annotated=Annotated,
                         Counter=Counter, logger=logging.getLogger("authored-native-test"), json=json)
        subsets = {
            "tradingagents/agents/state.py": {"InvestDebateState", "RiskDebateState", "AgentState"},
            "tradingagents/agents/analysts/turn.py": {"WRAP_UP", "take_turn", "_as_text"},
            "tradingagents/graph/setup.py": {"_tools_or_done", "_analyst_graph"},
            "tradingagents/agents/analysts/market_analyst.py": {"create_market_analyst"},
        }
        for relative, names in subsets.items():
            data = (root / relative).read_bytes()
            original = subprocess.check_output(["git", "-C", str(root), "show", f"{UPSTREAM_COMMIT}:{relative}"])
            # Git working trees may normalize line endings; content must be identical.
            if data.replace(b"\r\n", b"\n") != original.replace(b"\r\n", b"\n"):
                raise RuntimeError("Changed pinned source: " + relative)
            tree = ast.parse(data, filename=relative)
            selected = [node for node in tree.body if getattr(node, "name", None) in names
                        or isinstance(node, ast.Assign) and any(getattr(t, "id", None) in names for t in node.targets)]
            exec(compile(ast.Module(body=selected, type_ignores=[]), relative, "exec"), namespace)
        cls.ns, cls.Runnable = namespace, Runnable

    def test_real_toolnode_dispatch_next_input_and_wrapup_text(self):
        self.dispatch(max_tool_rounds=1)

    def test_real_toolnode_dispatch_next_input_without_wrapup(self):
        self.dispatch(max_tool_rounds=2)

    def dispatch(self, max_tool_rounds):
        from langchain_core.tools import StructuredTool
        verify_core = verify
        ns = self.ns.copy()
        events, calls, inputs = [], [], []
        host = FeedbackBoundary(run_id="authored-run", proposal_id="paper-proposal",
            emit=lambda k, d: events.append((k, d)), assess=verify_core)
        packet = authored_packet(snapshot=False)
        host.submit(**packet)
        expected_assessment = verify_core(**packet)["assessment_id"]
        native_events, captured_inputs = [], []
        capture = HostEventCapture(run_id="authored-run", stream_id="native-host", producer_id="authored-native",
            redaction_profile="authored-public", redact=lambda s: s, emit=native_events.append)
        def capture_input(messages):
            event = capture.assembled_native_input(messages, report_id="market-report", report_revision=1)
            captured_inputs.append(event)
            return event

        def authored_source() -> str:
            """Return an authored defective row; never fetch a provider."""
            return "Authored row: Close=99 Low=100; do not invent a replacement"

        verify_tool = make_verify_tool(host)
        self.assertEqual(verify_tool.args, {})  # Agent cannot replace policy, proposal or checkpoint.
        source = StructuredTool.from_function(authored_source)
        ns.update(TOOLS=(source, verify_tool), get_language_instruction=lambda: "",
                  get_instrument_context_from_state=lambda state: "Authored instrument, no order authority")
        # Re-execute the exact factory AST so only its globals are injected.
        factory = ns["create_market_analyst"]
        from types import FunctionType
        factory = FunctionType(factory.__code__, ns)

        class AuthoredResponses(self.Runnable):
            def bind_tools(self, tools, **kwargs):
                calls.append([tool.name for tool in tools])
                return self

            def invoke(self, prompt, config=None, **kwargs):
                messages = prompt.to_messages() if hasattr(prompt, "to_messages") else prompt
                inputs.append(messages)
                self_outer.assertEqual(messages[0].content, TRUSTED_INSTRUCTION)
                if len(inputs) == 1:
                    return ns["AIMessage"](content="", tool_calls=[
                        dict(name="authored_source", args={}, id="source-call", type="tool_call"),
                        dict(name="verify_proposal", args={}, id="verify-call", type="tool_call")])
                # Observe native ToolMessages, or the exact pinned _as_text at cap.
                text = "\n".join(str(m.content) for m in messages)
                self_outer.assertIn(expected_assessment, text)
                self_outer.assertIn("Close=99 Low=100", text)
                return ns["AIMessage"](content="AUTHORED abstention: provider defect unresolved")

        self_outer = self
        spec = SimpleNamespace(key="market", agent_node="Market Analyst", report_key="market_report", tools=(source, verify_tool))
        # No model, provider client, source runner or upstream constructor runs.
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("Network forbidden")):
            # _analyst_graph uses its original globals: supply required real classes.
            analyst = factory(make_trusted_model(AuthoredResponses(), host, capture_input=capture_input))
            def observed_agent(state):
                observe_native_returns(host, state["messages"], capture=capture)
                output = analyst(state)
                if output["market_report"]:
                    capture.report(content=output["market_report"], report_id="market-report", revision=1,
                        input_event_id=captured_inputs[-1]["event_id"], completion="UNKNOWN", phase="CLOSED")
                return output
            graph = ns["_analyst_graph"](spec, observed_agent, max_tool_rounds=max_tool_rounds)
            result = graph.invoke(dict(messages=[], trade_date="2026-11-05"),
                                  config=dict(recursion_limit=8, max_concurrency=1))
        self.assertEqual(result, {"market_report": "AUTHORED abstention: provider defect unresolved"})
        self.assertEqual(len(inputs), 2)
        self.assertEqual(calls, [["authored_source", "verify_proposal"]] * max_tool_rounds)
        self.assertEqual(host.counts["verify_calls"], 1)
        self.assertEqual([e["event_type"] for e in native_events],
                         ["model_input", "tool_result", "tool_result", "model_input", "report"])
        actual_input, actual_report = captured_inputs[-1], native_events[-1]
        self.assertEqual(actual_input["payload"]["boundary"], "ASSEMBLED")
        self.assertEqual(actual_input["payload"]["included_event_ids"],
                         [e["event_id"] for e in native_events if e["event_type"] == "tool_result"])
        self.assertEqual(actual_report["payload"]["input_event_id"], actual_input["event_id"])
        self.assertEqual(actual_report["parents"], [actual_input["event_id"]])
        self.assertEqual(actual_report["payload"]["completion"], "UNKNOWN")
        self.assertEqual([e["payload"]["status"] for e in native_events if e["event_type"] == "tool_result"],
                         ["UNKNOWN", "UNKNOWN"])
        self.assertIn("authored_snapshot", host.packet["policy"]["required_tool"])
        self.assertEqual(host.feedback["findings"][0]["outcome"], "FAIL")
        self.assertNotEqual(actual_report["event_id"], host.packet["request"]["proposal"]["report_event_id"])
        self.assertFalse(host.report_boundary_allowed(actual_report))
        self.assertEqual([k for k, _ in events if k.startswith("feedback.")],
                         ["feedback.prepared", "feedback.delivered", "feedback.input_included"])


if __name__ == "__main__":
    unittest.main()
