"""Authored offline plumbing only. Backend callbacks are provisional doubles."""
from dataclasses import replace
import ast
from collections import Counter
import logging
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Annotated
import unittest
from unittest.mock import patch

from continuous_verification.tradingagents import (
    BoundaryError, FeedbackBoundary, Limits, LocalFeedback, UPSTREAM_COMMIT, make_verify_tool,
    make_trusted_model, observe_native_returns, TRUSTED_INSTRUCTION,
)


class BoundaryTests(unittest.TestCase):
    def make_boundary(self, **kwargs):
        self.events = []
        self.receipts = []

        def assessment_double(binding):
            result = LocalFeedback(binding, f"authored-{len(self.receipts)}", "READY", "ADVISE", "[]")
            self.receipts.append(result)
            return result

        defaults = dict(run_id="authored-run", proposal_id="report", policy_binding="authored-policy",
                        checkpoint=lambda record: f"authored-prefix-{record['revision']}",
                        assess=assessment_double, emit=lambda kind, data: self.events.append((kind, data)))
        return FeedbackBoundary(**(defaults | kwargs))

    def deliver(self, host):
        payload = host.verify()
        call_id = f"call-{host.counts['verify_calls']}"
        host.observe_tool_return(call_id, payload)
        host.observe_next_input("input", [(call_id, payload)])
        return payload

    def test_voluntary_omission_and_no_implicit_enforcement(self):
        host = self.make_boundary()
        host.submit("Authored report")
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        self.assertEqual(host.counts["verify_calls"], 0)
        self.deliver(host)
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))

    def test_delivery_input_ack_and_at_use_authorizer_are_distinct(self):
        allowed = [True]
        host = self.make_boundary(authorize=lambda binding, result: allowed[0])
        host.submit("Authored report")
        payload = host.verify()
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        host.observe_tool_return("c", payload)
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        host.acknowledge(host.feedback.assessment_id, "Authored acknowledgement")
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        host.observe_next_input("i", [("other", payload), ("c", "different")])
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        host.observe_next_input("i2", [("c", payload)])
        self.assertTrue(host.report_boundary_allowed(host.proposals[-1]["text"]))
        self.assertFalse(host.report_boundary_allowed("Unsubmitted revision with invented Close=101"))
        allowed[0] = False
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))

    def test_revision_preserves_old_proposal_and_rejects_old_result(self):
        host = self.make_boundary(authorize=lambda *_: True)
        old = host.submit("Authored first")
        self.deliver(host)
        host.submit("Authored revision")
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        host.assess = lambda _: self.receipts[0]
        with self.assertRaisesRegex(BoundaryError, "Stale"):
            host.verify()
        self.assertEqual(host.proposals[0]["text"], "Authored first")
        self.assertNotEqual(host.current, old)

    def test_separate_allowances_and_failed_refresh_invalidates(self):
        host = self.make_boundary(limits=Limits(1, 2, 1), authorize=lambda *_: True)
        host.submit("Authored")
        self.deliver(host)
        def unavailable():
            raise TimeoutError("authored unavailable source")
        with self.assertRaises(TimeoutError):
            host.source_round([unavailable])
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        self.assertEqual(host.counts, dict(source_rounds=1, verify_calls=1, remediations=0))
        with self.assertRaises(BoundaryError):
            host.source_round([])
        host.submit("Abstain from defective price")
        self.deliver(host)
        with self.assertRaises(BoundaryError):
            host.verify()
        with self.assertRaises(BoundaryError):
            host.submit("Excess correction")
        host.abstain("No supported replacement price")
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))

    def test_unready_gap_error_and_hold_cannot_release(self):
        for readiness, disposition in [("NOT_READY", "ADVISE"), ("CAPTURE_GAP", "ADVISE"),
                                       ("ERROR", "ADVISE"), ("READY", "HOLD"), ("READY", "RECHECK")]:
            with self.subTest(readiness=readiness, disposition=disposition):
                host = self.make_boundary(authorize=lambda *_: True)
                host.submit("Authored")
                host.assess = lambda b: LocalFeedback(b, "authored", readiness, disposition, "[]")
                self.deliver(host)
                self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))

    def test_timeout_spends_verify_allowance_and_clears_advice(self):
        host = self.make_boundary(limits=Limits(0, 2, 0), authorize=lambda *_: True)
        host.submit("Authored")
        self.deliver(host)
        def timeout(_):
            raise TimeoutError("authored backend timeout")
        host.assess = timeout
        with self.assertRaises(TimeoutError):
            host.verify()
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        self.assertEqual(host.counts["verify_calls"], 2)

    def test_wrong_run_checkpoint_policy_digest_or_revision_rejected(self):
        for field, value in [("run_id", "other"), ("checkpoint_id", "later"),
                             ("policy_binding", "other"), ("text_digest", "other"), ("revision", 2)]:
            with self.subTest(field=field):
                host = self.make_boundary()
                host.submit("Authored")
                host.assess = lambda b: LocalFeedback(replace(b, **{field: value}), "a", "READY", "ADVISE", "[]")
                with self.assertRaises(BoundaryError):
                    host.verify()

    def test_authored_defect_hold_revision_recheck_keeps_original_failure(self):
        host = self.make_boundary(authorize=lambda *_: True)
        authored_bad_row = "Close=99 Low=100; provider defect; no reconciled price"
        host.submit(authored_bad_row)
        host.assess = lambda b: LocalFeedback(b, "authored-failure", "READY", "HOLD",
                                             '[{"source_id":"authored-row","status":"FAIL"}]')
        self.deliver(host)
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        host.acknowledge("authored-failure", "Defect remains unresolved")
        host.submit("Abstain from a price-dependent conclusion; provider row remains defective")
        host.assess = lambda b: LocalFeedback(b, "authored-recheck", "READY", "ADVISE",
                                             '[{"source_id":"authored-row","status":"INCONCLUSIVE"}]')
        self.deliver(host)
        self.assertTrue(host.report_boundary_allowed(host.proposals[-1]["text"]))  # Authored authorizer, not a verifier result.
        self.assertEqual(host.proposals[0]["text"], authored_bad_row)
        self.assertTrue(any("authored-failure" in str(data) for _, data in self.events))
        host.abstain("Provider defect cannot be corrected by inventing a price")
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))


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
        ns = self.ns.copy()
        events, calls, inputs = [], [], []
        host = FeedbackBoundary(run_id="authored-native", proposal_id="report", policy_binding="test-policy",
            checkpoint=lambda p: "authored-prefix", emit=lambda k, d: events.append((k, d)),
            assess=lambda b: LocalFeedback(b, "authored-assessment", "READY", "HOLD",
                                           '[{"status":"FAIL","source_id":"authored-row"}]'))
        host.submit("Authored proposal; provider row is defective")

        def authored_source() -> str:
            """Return an authored defective row; never fetch a provider."""
            return "Authored row: Close=99 Low=100; do not invent a replacement"

        verify = make_verify_tool(host)
        self.assertEqual(verify.args, {})  # Agent cannot replace policy, proposal or checkpoint.
        source = StructuredTool.from_function(authored_source)
        ns.update(TOOLS=(source, verify), get_language_instruction=lambda: "",
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
                self_outer.assertIn("authored-assessment", text)
                self_outer.assertIn("Close=99 Low=100", text)
                return ns["AIMessage"](content="AUTHORED abstention: provider defect unresolved")

        self_outer = self
        spec = SimpleNamespace(key="market", agent_node="Market Analyst", report_key="market_report", tools=(source, verify))
        # No model, provider client, source runner or upstream constructor runs.
        with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("Network forbidden")):
            # _analyst_graph uses its original globals: supply required real classes.
            analyst = factory(make_trusted_model(AuthoredResponses(), host))
            def observed_agent(state):
                observe_native_returns(host, state["messages"])
                return analyst(state)
            graph = ns["_analyst_graph"](spec, observed_agent, max_tool_rounds=max_tool_rounds)
            result = graph.invoke(dict(messages=[], trade_date="2026-11-05"),
                                  config=dict(recursion_limit=8, max_concurrency=1))
        self.assertEqual(result, {"market_report": "AUTHORED abstention: provider defect unresolved"})
        self.assertEqual(len(inputs), 2)
        self.assertEqual(calls, [["authored_source", "verify_proposal"]] * max_tool_rounds)
        self.assertEqual(host.counts["verify_calls"], 1)
        self.assertFalse(host.report_boundary_allowed(host.proposals[-1]["text"]))
        self.assertEqual([k for k, _ in events if k.startswith("feedback.")],
                         ["feedback.prepared", "feedback.delivered", "feedback.input_included"])


if __name__ == "__main__":
    unittest.main()
