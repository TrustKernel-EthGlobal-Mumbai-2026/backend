"""Opt-in real-import analyst smoke readiness; default NO-PAID preflight."""
import argparse
from contextlib import contextmanager, closing
from copy import deepcopy
import hashlib
import importlib
import io
import json
import os
import sqlite3
import subprocess
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from continuous_verification import digest
from continuous_verification.tradingagents import UPSTREAM_COMMIT, BoundaryError
from tools.continuous_demo import new_output, write_new

PROFILE = dict(model="gpt-6.1-terra", endpoint="https://api.openai.com/v1", effort="medium",
    service_tier="default", max_model_calls=4, max_output_tokens=1024,
    source_rounds=1, verify_calls=2, remediations=1, graph_tool_rounds=3,
    max_concurrency=1, recursion_limit=12, request_timeout_seconds=25,
    wall_seconds=120, max_input_bytes=40000, retries=0,
    cumulative_hard_limit_usd=10.0, proposed_incremental_limit_usd=0.65,
    tool_choice="auto", live_sources=False)


def preflight_plan(verify_transport="direct"):
    """Presence/status only; never open budget files or inspect credential values."""
    return dict(profile=deepcopy(PROFILE), profile_digest=digest(PROFILE), execution_enabled=False, verify_transport=verify_transport,
        credential_status="ENV_NAME_PRESENT_VALUE_UNREAD" if "OPENAI_API_KEY" in os.environ else "ENV_NAME_ABSENT",
        budget_status="NOT_OPENED_OR_MUTATED; existing cumulative ledger/unknown holds require separate review",
        model_access="NOT_CHECKED; no account/provider request", new_user_approval="REQUIRED",
        paid_launch_status="DISABLED_PENDING_NEW_APPROVAL_AND_RUNTIME_GATES",
        scope="real imported bounded market analyst/subgraph; not full GraphSetup",
        source_mode="authored frozen tool returns; no native vendor/source body runs")


def checked_upstream(path):
    """Reuse the original pin/origin/tracked-integrity guard before child sandbox."""
    from trustkernel import runner
    root = Path(path).resolve()
    if root.name != "TradingAgents" or root.parent.name != "upstream":
        raise ValueError("Expected reviewed upstream/TradingAgents checkout")
    previous = os.environ.get("GIT_OPTIONAL_LOCKS")  # Only this noncredential setting; no env enumeration.
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        with patch.object(runner, "ROOT", root.parent.parent):
            runner.upstream_check()
    finally:
        if previous is None:
            os.environ.pop("GIT_OPTIONAL_LOCKS", None)
        else:
            os.environ["GIT_OPTIONAL_LOCKS"] = previous
    return root


@contextmanager
def real_runtime(upstream):
    """Import actual installed pinned package, blocking implicit dotenv discovery.

    This executes normal Python imports, never AST extraction. File bytes are not
    patched; process-local frozen tools are installed separately during a run.
    """
    import dotenv
    sys.path.insert(0, str(upstream))
    with patch.object(dotenv, "find_dotenv", return_value=""), patch.object(dotenv, "load_dotenv", return_value=False):
        package = importlib.import_module("tradingagents")
        market = importlib.import_module("tradingagents.agents.analysts.market_analyst")
        setup = importlib.import_module("tradingagents.graph.setup")
        config = importlib.import_module("tradingagents.dataflows.config")
        defaults = importlib.import_module("tradingagents.default_config")
        modules = [package, market, setup]
        for module in modules:
            if not Path(module.__file__).resolve().is_relative_to(upstream):
                raise ValueError("Unexpected installed module origin")
        yield dict(package=package, market=market, setup=setup, config=config, defaults=defaults,
            import_proof=[dict(module=m.__name__, file=str(Path(m.__file__).relative_to(upstream)),
                sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()) for m in modules])


def implementation_digest():
    paths = ["tools/tradingagents_integration.py",
        "trustkernel/runner.py", "trustkernel/trace.py", "trustkernel/replay.py", "trustkernel/safety.py", "trustkernel/billing.py"]
    # Bind every accepted package Python/schema dependency, including CLI/SDK and
    # capture/journal/projection. A transport-handler edit invalidates approval.
    paths += sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "continuous_verification").rglob("*")
        if p.is_file() and p.suffix in {".py", ".json"})
    return digest({p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths})


def frozen_fixture(runtime):
    news = importlib.import_module("tradingagents.agents.analysts.news_analyst")
    names = {t.name for module in (runtime["market"], news) for t in module.TOOLS}
    return dict(fixture_id="authored-imported-smoke-v1", kind="AUTHORED_FROZEN",
        ticker="ETH-USD", as_of="2026-11-05", provenance="Authored fixture; no provider retrieval or price authority",
        tools={name: dict(origin="AUTHORED", text="AUTHORED provider-row defect: Close=99 Low=100; do not reconcile or replace") for name in sorted(names)})


def approval_template(fixture, review=None, *, verify_transport="direct"):
    return dict(approved=False, approval_id=None, expires_at=None, launch_output=None, milestone="actual-imported-analyst-smoke-v1",
        profile_digest=digest(PROFILE), implementation_digest=implementation_digest(), verify_transport=verify_transport,
        fixture_digest=digest(fixture), upstream_commit=UPSTREAM_COMMIT,
        incremental_limit_usd=PROFILE["proposed_incremental_limit_usd"],
        budget_review="REQUIRED_TEN_DOLLAR_REVIEW_AND_BOTH_KNOWN_HOLDS",
        budget_review_digest=digest(review) if review else None,
        pricing_review="REQUIRED_ORIGINAL_UPPER_RATES_STILL_CONSERVATIVE",
        model_account_access="UNPROBED_ACKNOWLEDGEMENT_REQUIRED")


def validate_approval(approval, fixture, *, output, review=None, verify_transport="direct", now=None):
    """A reviewed operator artifact is required; this does not create approval."""
    template = approval_template(fixture, review, verify_transport=verify_transport)
    for key in ("milestone", "profile_digest", "implementation_digest", "fixture_digest", "upstream_commit", "incremental_limit_usd", "budget_review_digest", "verify_transport"):
        if approval.get(key) != template[key]:
            raise PermissionError("Approval binding mismatch")
    if (approval.get("approved") is not True or not isinstance(approval.get("approval_id"), str) or not approval["approval_id"]
            or approval.get("budget_review") != "CONFIRMED_TEN_DOLLAR_LEDGER_PRESERVE_BOTH_KNOWN_HOLDS"
            or approval.get("pricing_review") != "CONFIRMED_ORIGINAL_UPPER_RATES_CONSERVATIVE"
            or approval.get("model_account_access") != "UNPROBED_CALL_MAY_FAIL_AND_RETAIN_HOLD"):
        raise PermissionError("New explicit approval and launch reviews required")
    reviewed_budget_summary(review)
    launch = approval.get("launch_output")
    if (not isinstance(launch, str) or not launch or (ROOT / launch).resolve() != Path(output).resolve()
            or not Path(output).resolve().is_relative_to(ROOT / ".local-runs")):
        raise PermissionError("Approval must bind one new supervised output; reuse is not allowed")
    try:
        expiry = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
        instant = datetime.fromtimestamp(now if now is not None else time.time(), timezone.utc)
        if expiry.tzinfo is None or not instant < expiry <= instant + timedelta(hours=1):
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise PermissionError("Approval needs a future explicit-timezone expiry within one hour") from None


def reviewed_budget_summary(review):
    """Validate an operator's closed/read-only review artifact, not the ledger."""
    from trustkernel.billing import upper_charge
    try:
        fingerprint = review["budget_sha256_before"]
        total = float(review["reserved_including_existing_holds"])
        initial, active, hard = review["initial_active_hard"]
        holds = review["known_unknown_holds"]
        # Operator-supplied exact SELECT id,reserved,charge,status,response_id
        # tuples, never inferred from whichever unknown rows happen to exist.
        if (review["review_version"] != "ten-dollar-two-holds-v1"
                or not isinstance(holds, list) or len(holds) != 2
                or any(not isinstance(row, list) or len(row) != 5
                    or not isinstance(row[0], str) or not row[0]
                    or row[1:] != [0.16024, None, "in_flight_or_unknown", None] for row in holds)
                or len({row[0] for row in holds}) != 2):
            raise ValueError()
        required = upper_charge(PROFILE["model"], dict(input_tokens=60000, output_tokens=2048)) * PROFILE["max_model_calls"]
        if (review["unchanged"] is not True or fingerprint != review["budget_sha256_after"]
                or len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint)
                or review["existing_unsettled_rows"] != 2 or [initial, active, hard] != [3, 10, 10]
                or not 0 <= total <= active or required > PROFILE["proposed_incremental_limit_usd"]
                or total + required > active):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise PermissionError("Reviewed unchanged budget baseline does not fit this smoke") from None
    return dict(review_digest=digest(review), ledger_sha256=fingerprint, committed_including_historical_hold=total,
        initial=initial, active=active, hard=hard, remaining=active-total, proposed_worst_reserve=required,
        known_unknown_holds=deepcopy(holds), historical_hold_reserved=0.32048,
        historical_hold_policy="PRESERVE_BOTH_UNCHANGED; never settle/release/reconcile", fits=True)


def read_existing_budget(operational_root, *, review, baseline=None, owned_ids=(), allow_pending=(),
                         remaining_calls=PROFILE["max_model_calls"]):
    """Future paid launch only: pin historical rows; permit only this run's writes.

    Review SHA binds the closed DB before the first read. Both known unknown
    rows remain reserved in this runner; their reviewed full tuples are pinned along
    with all settled rows/carry. New unknowns or unrelated changes refuse a call.
    Never called against real files by preflight/scripted readiness modes.
    """
    import math
    root = Path(operational_root).resolve()
    reviewed = reviewed_budget_summary(review)
    if type(remaining_calls) is not int or not 0 <= remaining_calls <= PROFILE["max_model_calls"]:
        raise PermissionError("Invalid remaining request allowance")
    policy_path, db_path = root / "budget_policy.json", root / "runs/approved-budget.sqlite"
    if not policy_path.is_file() or not db_path.is_file() or any(Path(str(db_path)+suffix).exists() for suffix in ("-wal", "-journal")):
        raise PermissionError("Existing closed cumulative ledger without WAL/journal is required")
    if baseline is None and hashlib.sha256(db_path.read_bytes()).hexdigest() != reviewed["ledger_sha256"]:
        raise PermissionError("Closed ledger changed since operator review")
    policy = json.loads(policy_path.read_text("utf-8"))
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")  # One consistent read-only snapshot for total/policy/rows.
        total = db.execute("SELECT reserved FROM budget WHERE id=1").fetchone()[0]
        limits = list(db.execute("SELECT initial_limit,active_limit,hard_limit FROM budget_policy WHERE id=1").fetchone())
        rows = {r[0]: list(r) for r in db.execute("SELECT id,reserved,charge,status,response_id FROM requests ORDER BY id")}
    if baseline is None and (hashlib.sha256(db_path.read_bytes()).hexdigest() != reviewed["ledger_sha256"]
            or any(Path(str(db_path)+suffix).exists() for suffix in ("-wal", "-journal"))):
        raise PermissionError("Closed ledger changed while baseline was read")
    if (policy.get("hard_limit_usd") != PROFILE["cumulative_hard_limit_usd"]
            or policy.get("initial_limit_usd") != limits[0]
            or limits != [reviewed["initial"], reviewed["active"], reviewed["hard"]]):
        raise PermissionError("Existing cumulative/active policy changed")
    unknowns = {k: r for k,r in rows.items() if r[3] != "settled" or r[2] is None}
    if baseline is None:
        if (not math.isclose(total,reviewed["committed_including_historical_hold"],rel_tol=0,abs_tol=1e-9)
                or unknowns != {row[0]: row for row in reviewed["known_unknown_holds"]}):
            raise PermissionError("Reviewed historical state changed")
        baseline = dict(rows=deepcopy(rows), policy=deepcopy(policy), total=total, hold_ids=sorted(unknowns))
    if any(rows.get(k) != r for k,r in baseline["rows"].items()) or policy != baseline["policy"]:
        raise PermissionError("Historical row/hold or policy changed; no reconciliation allowed")
    extra = set(rows)-set(baseline["rows"])
    if extra != set(owned_ids):
        raise PermissionError("Unexpected concurrent budget requests")
    from trustkernel.billing import upper_charge
    reserve = upper_charge(PROFILE["model"], dict(input_tokens=60000, output_tokens=2048))
    expected_total = baseline["total"]
    for identity in extra:
        row = rows[identity]
        if row[1] != reserve:
            raise PermissionError("This run's conservative reservation changed")
        if identity in allow_pending and row[2] is None and row[3] == "in_flight_or_unknown" and row[4] is None:
            expected_total += row[1]
        elif row[3] == "settled" and type(row[2]) in (int,float) and 0 <= row[2] <= row[1] and isinstance(row[4], str) and row[4]:
            expected_total += row[2]
        else:
            raise PermissionError("New/unexpected unknown hold remains reserved; stop")
    if not math.isclose(total,expected_total,rel_tol=0,abs_tol=1e-9):
        raise PermissionError("Concurrent cumulative balance change")
    required = reserve * remaining_calls
    if not 0 <= total <= limits[1] or total+required > limits[1] or total-baseline["total"]+required > PROFILE["proposed_incremental_limit_usd"]:
        raise PermissionError("Existing active/cumulative/incremental headroom refused")
    return dict(path=db_path,policy=policy,committed_upper=total,active_limit=limits[1],required_reserve=required,
        baseline=baseline,review=review)


def child_guards(output, *, paid=False, budget_path=None):
    """Reuse original network guard; restrict file writes to new output (and future approved ledger)."""
    from trustkernel.safety import network_guard
    network_guard(paid)
    output = Path(output).resolve()
    def audit(event, args):
        if event == "sqlite3.connect":
            raw = str(args[0])
            if raw.startswith("file:"):
                from urllib.parse import urlsplit, unquote
                raw = unquote(urlsplit(raw).path)
                if os.name == "nt" and raw.startswith("/"):
                    raw = raw[1:]
            path = Path(raw).resolve()
            if not path.is_relative_to(output) and not (paid and budget_path and path == budget_path):
                raise PermissionError("No external SQLite access in smoke child")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            mode, flags = args[1], args[2]
            writing = bool((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            budget_allowed = paid and budget_path and str(path) in {str(budget_path) + suffix for suffix in ("", "-journal", "-wal", "-shm")}
            if writing and not path.is_relative_to(output) and not budget_allowed:
                raise PermissionError("Smoke child refuses external file writes")
            policy_read = paid and budget_path and path == budget_path.parent.parent / "budget_policy.json"
            if not writing and (path.name.startswith(".env") or path.name in {".netrc", "budget_policy.json", "approved-budget.sqlite"}) and not (budget_allowed or policy_read):
                raise PermissionError("Credential/private budget file access disabled")
    sys.addaudithook(audit)


def _complete(message):
    meta = message.response_metadata
    if meta.get("status") == "incomplete" or meta.get("finish_reason") == "length":
        return "TRUNCATED"
    if meta.get("status") == "completed" or meta.get("finish_reason") == "stop":
        return "COMPLETE"
    return "UNKNOWN"


class CheckpointTransport:
    """Trusted host route, never a model-issued shell/OS CLI command.

    Only model-generated native tool dispatch opts into the actual injected CLI
    parser. Host rechecks stay direct and explicitly labeled. Neither checkpoint,
    grants, backend nor file paths can be supplied by model arguments.
    """
    def __init__(self, backend, run_id, *, selection="direct", emit=lambda kind, data: None):
        if selection not in {"direct", "injected-cli"}:
            raise ValueError("Unknown verification transport")
        from continuous_verification.sdk import Access, Client, ServiceErrorAdapter
        from continuous_verification.service import ServiceError
        self.backend, self.selection, self.emit = backend, selection, emit
        self.client = Client(ServiceErrorAdapter(backend, ServiceError), Access(frozenset({"verify"}), frozenset({run_id})))

    def verify(self, request, *, origin, turn=None, model_call_id=None):
        from continuous_verification import canonical_json
        from continuous_verification.cli import main as cli_main
        selected = self.selection == "injected-cli" and origin == "MODEL_TOOL_DISPATCH"
        common = dict(origin=origin, turn=turn, model_call_id=model_call_id, run_id=request["run_id"],
            request_id=request["request_id"], checkpoint=deepcopy(request["checkpoint"]),
            proposal_revision=request["proposal"]["revision"], report_event_id=request["proposal"]["report_event_id"],
            report_revision=request["proposal"]["report_revision"], request_digest=digest(request),
            transport="HOST_INJECTED_CLI_PARSER" if selected else "DIRECT_NATIVE_HOST",
            cli_subprocess=False, agent_shell_command=False)
        self.emit("smoke.checkpoint_dispatch", dict(common, request=deepcopy(request)))
        envelope, code, stderr = None, None, ""
        try:
            if selected:
                out, err = io.StringIO(), io.StringIO()
                code = cli_main(["verify"], client=self.client, stdin=io.StringIO(canonical_json(request)), stdout=out, stderr=err)
                envelope, stderr = json.loads(out.getvalue()), err.getvalue()
                if code != 0 or envelope.get("ok") is not True:
                    self.emit("smoke.checkpoint_result", dict(common, cli_argv=["verify"], cli_exit_code=code,
                        cli_envelope=envelope, cli_stderr=stderr, assessment_id=None, result_status="TRANSPORT_ERROR"))
                    raise BoundaryError("Injected CLI verification refused; no assessment invented")
                result = envelope["result"]
            else:
                result = self.backend.execute("verify", deepcopy(request))
        except BoundaryError:
            raise
        except Exception as error:
            self.emit("smoke.checkpoint_result", dict(common, cli_exit_code=code, cli_envelope=envelope,
                result_status="TRANSPORT_ERROR", error_type=type(error).__name__, assessment_id=None))
            raise
        self.emit("smoke.checkpoint_result", dict(common, cli_argv=["verify"] if selected else None,
            cli_exit_code=code, cli_envelope=envelope, cli_stderr=stderr, result_status=result["status"],
            assessment_id=result["assessment_id"], disposition=result["disposition"], result_digest=digest(result)))
        return result


def run_cycle(runtime, output, fixture, *, mode, launch_id, scenario="normal", budget_info=None, verify_transport="direct"):
    """One shared real-import/client/ToolNode path; only HTTP model I/O differs."""
    import httpx
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import Runnable
    from langchain_core.tools import StructuredTool
    from langchain_core.utils.function_calling import convert_to_openai_tool
    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI
    from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS
    from trustkernel import trace as trace_module
    from trustkernel.replay import fixture_tools
    from continuous_verification.tradingagents import StoredFeedbackHost, LocalServiceWorker, Limits, make_verify_tool, make_trusted_model
    from continuous_verification.service import ServiceBackend, Principal
    if not isinstance(launch_id, str) or len(launch_id) != 32 or any(c not in "0123456789abcdef" for c in launch_id):
        raise ValueError("Expected supervised launch nonce")
    run_id = mode + "-real-import-smoke-" + launch_id
    # Reuse original regex/key-field privacy filtering without enumerating any
    # credential environment values during readiness/scripted execution.
    class NoCredentialEnumeration(trace_module.Redactor):
        def __init__(self):
            self.secrets = []
    with patch.object(trace_module, "Redactor", NoCredentialEnumeration):
        trace = trace_module.Trace(output / "runtime-trace", run_id, dict(mode=mode, launch_id=launch_id, upstream_commit=UPSTREAM_COMMIT,
            response_origin="PROVIDER" if mode == "paid" else "AUTHORED_HTTP_OVERRIDE", hidden_reasoning_access=False))
    principal = Principal("smoke-collector", frozenset({"configure", "collect", "verify", "read"}), frozenset({run_id}))
    backend = LocalServiceWorker(lambda: ServiceBackend(output / "feedback.sqlite", principal=principal, service_id="smoke-local-service"))
    state = dict(model_calls=0, wire_requests=[], outputs=[], dispatches=[], inputs=[], stop=None, monitor_events=[], checkpoint_context={})
    monitor_sink = (output / "turns-checkpoints.jsonl").open("x", encoding="utf-8")
    def monitor(kind, data):
        with trace.lock:
            cleaned = trace.redactor.clean(data)
            trace.emit(kind, cleaned)
            event = dict(sequence=len(state["monitor_events"])+1, kind=kind, run_id=run_id,
                observed_at=datetime.now(timezone.utc).isoformat(), response_origin="PROVIDER" if mode == "paid" else "AUTHORED_HTTP_OVERRIDE",
                payload=cleaned)
            monitor_sink.write(json.dumps(event, ensure_ascii=False) + "\n")
            monitor_sink.flush()
            os.fsync(monitor_sink.fileno())
            state["monitor_events"].append(event)
    def boundary_observation(kind, data):
        if kind == "verification.requested":
            calls = state["outputs"][-1]["tool_calls"] if state["outputs"] else []
            call_id = next((c["id"] for c in calls if c["name"] == "verify_proposal"), None)
            origin = "HOST_RECHECK" if data["origin"] == "host" else "MODEL_TOOL_DISPATCH" if call_id else "COOPERATIVE_HOST"
            state["checkpoint_context"] = dict(origin=origin, turn=state["model_calls"] if origin == "MODEL_TOOL_DISPATCH" else None,
                model_call_id=call_id if origin == "MODEL_TOOL_DISPATCH" else None)
    start = time.time()
    deadline = min(start + PROFILE["wall_seconds"], budget_info["approval_expires_epoch"]) if budget_info else start + PROFILE["wall_seconds"]
    budget = None
    if mode == "paid":
        from trustkernel.safety import Budget
        budget = Budget(budget_info["path"], PROFILE["cumulative_hard_limit_usd"], PROFILE["model"], deadline, Path(budget_info["path"]).parent.parent / "STOP", trace,
            PROFILE["max_model_calls"], initial_limit=budget_info["policy"]["initial_limit_usd"])
    class Observer(trace_module.Observer):
        def on_tool_start(self, serialized, input_str, **kw):
            super().on_tool_start(serialized, input_str, **kw)
            state["dispatches"].append(serialized.get("name"))
    def before_paid(messages, metadata):
        read_existing_budget(budget_info["path"].parent.parent, review=budget_info["review"], baseline=budget_info["baseline"],
            owned_ids=set(budget.pending.values()), remaining_calls=PROFILE["max_model_calls"] - budget.calls)
        budget.before(messages, metadata)
        # Detect a writer racing the initial check before the HTTP request. If
        # rejected, our just-created hold stays reserved; never roll it back.
        read_existing_budget(budget_info["path"].parent.parent, review=budget_info["review"], baseline=budget_info["baseline"],
            owned_ids=set(budget.pending.values()), allow_pending=[budget.pending[str(metadata.get("run_id"))]],
            remaining_calls=PROFILE["max_model_calls"] - budget.calls)
    def after_paid(response, metadata):
        budget.settle(response, metadata)
        read_existing_budget(budget_info["path"].parent.parent, review=budget_info["review"], baseline=budget_info["baseline"],
            owned_ids=set(budget.pending.values()), remaining_calls=PROFILE["max_model_calls"] - budget.calls)
    observer = Observer(trace, before_paid if budget else None, after_paid if budget else None)
    policy = dict(contract_version="continuous-verification-0.2", policy_id="authored-smoke-procedure", version="1",
        required_tool="get_verified_market_snapshot", checks=[dict(check_id=name, on_fail="HOLD", on_inconclusive="RECHECK")
        for name in ("required_snapshot_before_market_report", "report_completion")])
    backend.configure_run(run_id, [dict(stream_id="host", collector_id=principal.actor_id, producer_id="smoke-host",
        adapter_version="tradingagents-feedback-0.2", redaction_profile="smoke-redacted")])
    backend.execute("register_run", dict(run_id=run_id, registration_id="smoke-registration"))
    backend.install_policy(run_id, policy)
    host = StoredFeedbackHost(backend=backend, run_id=run_id, stream_id="host", producer_id="smoke-host", redaction_profile="smoke-redacted",
        redact=lambda text: trace.redactor.clean(text), proposal_id="smoke-paper-proposal", policy=policy,
        limits=Limits(PROFILE["source_rounds"], PROFILE["verify_calls"], PROFILE["remediations"]), observe=boundary_observation)
    checkpoint_transport = CheckpointTransport(backend, run_id, selection=verify_transport, emit=monitor)
    def assess(request, *, checkpoint, events, policy):
        return checkpoint_transport.verify(request, **state["checkpoint_context"])
    host.boundary.assess = assess
    def coverage(input_event, report):
        backend.record_coverage(run_id, "host", [dict(name=name, state="CAPTURED", basis_event_ids=[basis])
            for name, basis in (("model_input", input_event["event_id"]), ("tool_lifecycle", input_event["event_id"]),
                ("phase_boundaries", report["event_id"]), ("report_completion", report["event_id"]))])
    def submit(report, revision):
        return host.submit_report(report_event=report, proposal_content="Paper abstention pending scoped report checks; no execution authority",
            proposal_revision=revision, request_id=f"smoke-request-{revision}", checkpoint_id="smoke-prefix", checkpoint_revision=revision,
            streams=[dict(stream_id="host", requested=len(host.capture.events))])
    initial_input = host.assemble_input([dict(type="human", content="AUTHORED seed checkpoint input; required snapshot omitted")],
        report_id="smoke-market-report", report_revision=0)
    initial_report = host.capture.report(content="AUTHORED seed report: snapshot not yet called; this is not a provider-generated historical failure",
        report_id="smoke-market-report", revision=0, input_event_id=initial_input["event_id"], completion="COMPLETE", phase="CLOSED")
    coverage(initial_input, initial_report)
    request0 = submit(initial_report, 0)
    def observe_wire(request):
        if request.url.scheme != "https" or request.url.host != "api.openai.com" or request.url.path != "/v1/responses":
            raise PermissionError("Only configured OpenAI Responses endpoint is allowed")
        body = json.loads(request.content)
        if len(request.content) > PROFILE["max_input_bytes"]:
            raise PermissionError("Wire input bound exceeded")
        if budget:
            read_existing_budget(budget_info["path"].parent.parent, review=budget_info["review"], baseline=budget_info["baseline"],
                owned_ids=set(budget.pending.values()), allow_pending=[list(budget.pending.values())[-1]],
                remaining_calls=PROFILE["max_model_calls"] - budget.calls)
        matched = [item["call_id"] for item in body.get("input", []) if isinstance(item, dict)
            and item.get("type") == "function_call_output" and item.get("call_id") in host.boundary.delivered
            and item.get("output") == host.boundary.delivered[item["call_id"]]]
        record = dict(call=state["model_calls"], origin="PROVIDER_REQUEST" if mode == "paid" else "AUTHORED_HTTP_OVERRIDE",
            tool_choice=body.get("tool_choice"), tools=[t.get("name") for t in body.get("tools", [])],
            feedback_call_ids=matched, retained_body_digest=digest(trace.redactor.clean(body)))
        first = not state["wire_requests"]
        state["wire_requests"].append(record)
        monitor("smoke.request_start", dict(turn=state["model_calls"], first_request=first,
            phase="SDK_SERIALIZED_BEFORE_HTTP", provider_request=mode == "paid", verify_transport=verify_transport,
            feedback_call_ids=matched))
        print(f"TURN {state['model_calls']} REQUEST ATTEMPT START ({'APPROVED_PROVIDER' if mode == 'paid' else 'AUTHORED_HTTP_OVERRIDE'}; verify route={verify_transport})", flush=True)
        trace.emit("smoke.wire_request", dict(proof=record, body=body))
        return record
    def authored_http(request):
        observe_wire(request)
        step = len(state["wire_requests"])
        if scenario != "omit" and step == 1:
            result = [dict(type="function_call", id="fc_authored_verify", call_id="authored-verify", name="verify_proposal", arguments="{}", status="completed")]
        elif scenario == "normal" and step == 2:
            result = [dict(type="function_call", id="fc_authored_source", call_id="authored-snapshot", name="get_verified_market_snapshot",
                arguments=json.dumps(dict(curr_date=fixture["as_of"], look_back_days=1)), status="completed")]
        else:
            result = [dict(type="message", id="msg_authored_report", role="assistant", status="completed",
                content=[dict(type="output_text", text="AUTHORED model-I/O override: abstain; provider-row defect or omitted source remains unresolved", annotations=[])])]
        response = dict(id=f"resp_authored_{step}", object="response", created_at=0, status="completed", model=PROFILE["model"],
            output=result, usage=dict(input_tokens=100, output_tokens=50, total_tokens=150,
                input_tokens_details=dict(cached_tokens=0), output_tokens_details=dict(reasoning_tokens=0)))
        if scenario == "truncated" and step > 1:
            response.update(status="incomplete", incomplete_details=dict(reason="max_output_tokens"))
        return httpx.Response(200, json=response)
    class ApiOnlyTransport(httpx.HTTPTransport):
        def handle_request(self, request):
            observe_wire(request)
            return super().handle_request(request)
    transport = ApiOnlyTransport(retries=0) if mode == "paid" else httpx.MockTransport(authored_http)
    client = httpx.Client(transport=transport, trust_env=False, timeout=PROFILE["request_timeout_seconds"])
    model_options = dict(model=PROFILE["model"], base_url=PROFILE["endpoint"], reasoning_effort=PROFILE["effort"],
        use_responses_api=True, store=False, service_tier=PROFILE["service_tier"], max_tokens=PROFILE["max_output_tokens"],
        max_retries=0, timeout=PROFILE["request_timeout_seconds"], http_client=client)
    if mode != "paid":
        model_options["api_key"] = "authored-offline-placeholder-not-a-credential"
    model = NormalizedChatOpenAI(**model_options)
    class ObservedModel(Runnable):
        def __init__(self, delegate):
            self.delegate = delegate
        def bind_tools(self, tools, **kwargs):
            trace.emit("smoke.tools_offered", dict(definitions=[convert_to_openai_tool(t) for t in tools], tool_choice="auto"))
            return ObservedModel(self.delegate.bind_tools(tools, tool_choice="auto", parallel_tool_calls=False))
        def invoke(self, messages, config=None, **kwargs):
            if state["model_calls"] >= PROFILE["max_model_calls"] or time.time() >= deadline:
                raise PermissionError("Model call or wall-time bound reached")
            state["model_calls"] += 1
            monitor("smoke.turn_start", dict(turn=state["model_calls"], phase="ENTERING_MODEL_CLIENT", verify_transport=verify_transport))
            result = self.delegate.invoke(messages, config=config, **kwargs)
            record = dict(call=state["model_calls"], origin="PROVIDER" if mode == "paid" else "AUTHORED_HTTP_OVERRIDE",
                content=result.content, tool_calls=result.tool_calls, completion=_complete(result), response_id=result.response_metadata.get("id"))
            state["outputs"].append(record)
            trace.emit("smoke.model_output", record)
            monitor("smoke.turn_result", dict(turn=state["model_calls"], completion=record["completion"],
                response_id=record["response_id"], action="TOOL_CALL" if result.tool_calls else "VISIBLE_MESSAGE" if result.content else "EMPTY",
                tool_call_ids=[c["id"] for c in result.tool_calls], tool_names=[c["name"] for c in result.tool_calls]))
            if not any(c["name"] == "verify_proposal" for c in result.tool_calls):
                monitor("smoke.verify_not_requested_this_turn", dict(turn=state["model_calls"], status="NOT_REQUESTED_THIS_TURN"))
            if len(result.tool_calls) > 1:
                raise PermissionError("Smoke permits one tool call per model turn, never silently splits a batch")
            return result
    captured_inputs, reports = [], []
    def capture_input(messages):
        event = host.assemble_input(messages, report_id="smoke-market-report", report_revision=1)
        captured_inputs.append(event)
        state["inputs"].append(dict(event_id=event["event_id"], boundary=event["payload"]["boundary"],
            included_event_ids=event["payload"]["included_event_ids"]))
        return event
    error = None
    original = recheck = request1 = None
    try:
        with fixture_tools(fixture, trace), runtime["config"].run_config({**runtime["defaults"].DEFAULT_CONFIG, "output_language": "English"}):
            source_tools = []
            for original_tool in runtime["market"].TOOLS:
                def serve(_tool=original_tool, **kwargs):
                    return host.boundary.source_round([lambda: _tool.func(**kwargs)])[0]
                source_tools.append(StructuredTool.from_function(serve, name=original_tool.name,
                    description=original_tool.description, args_schema=original_tool.args_schema))
            tools = (*source_tools, make_verify_tool(host.boundary))
            spec = replace(ANALYST_NODE_SPECS["market"], tools=tools)
            with patch.object(runtime["market"], "TOOLS", tools):
                analyst = runtime["market"].create_market_analyst(make_trusted_model(ObservedModel(model), host.boundary, capture_input=capture_input))
                def agent(agent_state):
                    host.observe_native_returns(agent_state["messages"], classify_status=lambda m:
                        "SUCCESS" if m.name in fixture["tools"] and getattr(m, "status", None) != "error" else "UNKNOWN")
                    output_state = analyst(agent_state)
                    if output_state["market_report"]:
                        message = output_state["messages"][0]
                        reports.append(host.capture.report(content=output_state["market_report"], report_id="smoke-market-report", revision=1,
                            input_event_id=captured_inputs[-1]["event_id"], completion=_complete(message), phase="CLOSED"))
                    return output_state
                graph = runtime["setup"]._analyst_graph(spec, agent, max_tool_rounds=PROFILE["graph_tool_rounds"])
                graph.invoke(dict(messages=[HumanMessage(content="AUTHORED checkpoint setup: the host registered a seed report with an omitted snapshot. "
                    "Review that report, voluntarily call verify_proposal before source remediation, then react to its returned findings. "
                    "No tool call is forced. All sources are frozen authored fixtures; abstain on unresolved provider defects.")],
                    company_of_interest="ETH-USD", asset_type="crypto", trade_date=fixture["as_of"],
                    instrument_context="AUTHORED frozen ETH-USD research fixture; no current-price or order authority"),
                    config=dict(callbacks=[observer], recursion_limit=PROFILE["recursion_limit"], max_concurrency=1))
        if host.boundary.pending_returns:
            original = next(iter(host.boundary.pending_returns.values()))
        if original and reports:
            host.record_revision(original["assessment_id"], reports[-1])
            coverage(captured_inputs[-1], reports[-1])
            request1 = submit(reports[-1], 1)
            recheck = json.loads(host.boundary.verify(origin="host"))
    except Exception as exc:
        error = type(exc).__name__
        trace.emit("smoke.stop", dict(error_type=error, outcome="STOPPED_NOT_PASS"))
    finally:
        requested = any(c["name"] == "verify_proposal" for item in state["outputs"] for c in item["tool_calls"])
        if not requested:
            monitor("smoke.checkpoint_skipped", dict(origin="MODEL_TOOL_DISPATCH", turn=state["model_calls"],
                transport="NOT_USED", selected_transport=verify_transport, reason="model_did_not_request_verify_proposal"))
        if recheck is None:
            monitor("smoke.checkpoint_skipped", dict(origin="HOST_RECHECK", transport="NOT_USED",
                reason="no_initial_assessment_or_completed_report_or_stopped"))
        host.boundary.abstain("Host stops at the bounded smoke boundary; report procedure is not decision/price clearance")
        original_preserved = None
        if original:
            original_preserved = backend.execute("get_assessment", dict(run_id=run_id, assessment_id=original["assessment_id"])) == original
        service_state = backend.execute("get_run_state", dict(run_id=run_id))
        backend.audit()
        backend.close()
        client.close()
        monitor_sink.close()
        trace.close()
    verify_ids = [c["id"] for out in state["outputs"] for c in out["tool_calls"] if c["name"] == "verify_proposal"]
    verify_from_model = bool(verify_ids)
    feedback_requests = [w["call"] for w in state["wire_requests"] if w["feedback_call_ids"]]
    next_action = any(out["call"] in feedback_requests and (out["content"] or out["tool_calls"]) for out in state["outputs"])
    joined = sorted(set(verify_ids) & set(host.deliveries))
    progress = joined and "verify_proposal" in state["dispatches"] and bool(feedback_requests) and next_action
    truncated = any(out["completion"] == "TRUNCATED" for out in state["outputs"])
    return dict(mode=mode, run_id=run_id, launch_id=launch_id, response_origin="PROVIDER" if mode == "paid" else "AUTHORED_HTTP_OVERRIDE", real_import=True,
        full_graph_setup=False, error=error, observed_progress=bool(progress), provider_generated_verify=bool(mode == "paid" and verify_from_model),
        model_generated_verify_shape=verify_from_model, dispatch_observed="verify_proposal" in state["dispatches"],
        model_verify_call_ids=verify_ids, joined_generated_dispatched_delivered_ids=joined,
        verify_transport=verify_transport, cli_parser_invocations=sum(e["kind"] == "smoke.checkpoint_result" and
            e["payload"].get("cli_exit_code") is not None for e in state["monitor_events"]),
        cli_subprocess_invocations=0, agent_issued_shell_command=False,
        delivered_call_ids=list(host.deliveries), exact_next_wire_feedback_requests=feedback_requests, next_action_observed=bool(next_action),
        outcome="STOPPED_NOT_PASS" if error else "OUTPUT_CAP_WITH_PARTIAL_PROGRESS" if truncated else
            "PROGRESSION_OBSERVED" if progress else "VOLUNTARY_VERIFY_OR_CONTINUATION_NOT_OBSERVED",
        state=trace.redactor.clean(state), original=original, recheck=recheck, original_preserved=original_preserved,
        requests=[request0, request1], allowances=host.boundary.counts, service_state=service_state,
        provider_defect="UNRESOLVED AUTHORED Close=99 Low=100", elapsed_seconds=round(time.time()-start, 3))


def child(args):
    output = Path(args.output).resolve()
    if output == ROOT / ".local-runs" or not output.is_relative_to(ROOT / ".local-runs"):
        raise PermissionError("Child output outside supervised new-output root")
    marker = json.loads((output / "parent.json").read_text("utf-8"))
    if (marker["nonce"] != args.nonce or marker["profile_digest"] != digest(PROFILE) or marker["mode"] != args.mode
            or marker["verify_transport"] != args.verify_transport):
        raise PermissionError("Supervisor binding mismatch")
    write_new(output / "child-started.json", json.dumps(dict(mode=args.mode, paid_authorized=False)) + "\n")
    args.output_authorized = True
    plan = preflight_plan(args.verify_transport)
    review = json.loads(Path(args.budget_review).read_text("utf-8")) if args.budget_review else None
    if review:
        plan["budget_review_summary"] = reviewed_budget_summary(review)
    root = checked_upstream(args.upstream)
    budget_info = approved_fixture = None
    if args.mode == "paid":
        if not args.approval or not args.fixture or not review:
            raise PermissionError("NEW approval, reviewed fixture and closed-ledger review artifact required")
        approved_fixture = json.loads(Path(args.fixture).read_text("utf-8"))
        approval = json.loads(Path(args.approval).read_text("utf-8"))
        validate_approval(approval, approved_fixture, output=output, review=review, verify_transport=args.verify_transport)
        if "OPENAI_API_KEY" not in os.environ:
            raise PermissionError("API credential environment name absent; no credentials searched")
        budget_info = read_existing_budget(root.parent.parent, review=review)
        budget_info["approval_expires_epoch"] = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00")).timestamp()
        plan.update(execution_enabled=True, new_user_approval="VALIDATED_OPERATOR_ARTIFACT",
            budget_status="PINNED_CUMULATIVE_READ_CHECK_PASSED; both historical unknown holds remain reserved",
            paid_launch_status="APPROVED_EXECUTION_WITH_RUNTIME_LIMITS")
    child_guards(output, paid=args.mode == "paid", budget_path=budget_info["path"] if budget_info else None)
    with real_runtime(root) as runtime:
        fixture = frozen_fixture(runtime)
        if approved_fixture is not None and fixture != approved_fixture:
            raise PermissionError("Reviewed frozen fixture differs from actual imported tool fixture")
        plan.update(upstream_commit=UPSTREAM_COMMIT, import_proof=runtime["import_proof"], dotenv_discovery="DISABLED",
            actual_import=True, implementation_digest=implementation_digest(), fixture_digest=digest(fixture))
        write_new(output / "fixture.json", json.dumps(fixture, indent=2) + "\n")
        write_new(output / "approval-required.json", json.dumps(approval_template(fixture, review, verify_transport=args.verify_transport), indent=2) + "\n")
        if args.mode == "preflight":
            plan.update(readiness="NEEDS_SCRIPTED_REAL_IMPORT_PROOF", outcome="NO_PAID_PREFLIGHT_COMPLETE")
        else:
            result = run_cycle(runtime, output, fixture, mode=args.mode, launch_id=marker["nonce"], scenario=args.scenario, budget_info=budget_info,
                verify_transport=args.verify_transport)
            plan.update(result)
            mechanism_ready = args.mode == "scripted" and args.scenario == "normal" and result["outcome"] == "PROGRESSION_OBSERVED" and result["original_preserved"]
            plan["readiness"] = "READY_FOR_APPROVAL" if mechanism_ready and review else "MECHANISM_READY_REVIEW_ARTIFACT_REQUIRED" if mechanism_ready else "OUTCOME_RECORDED_NOT_APPROVAL"
    write_new(output / "readiness.json", json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    write_new(output / "VIEW.md", """# Bounded actual-import smoke artifact

Read readiness.json for proof stages, outcome, limits and all still-pending paid gates.
Scripted mode uses AUTHORED in-process HTTP responses through the real imported
NormalizedChatOpenAI client. It is not provider behavior. Preflight makes no calls.
Read runtime-trace/trace.jsonl (UTF-8) for original redacted callback events,
smoke.tools_offered, smoke.wire_request and smoke.model_output. Tool IDs join the
model-emitted call to actual dispatch, result, next request and next visible action.
Read feedback.sqlite ONLY READ-ONLY for cv_events, cv_objects kind=assessment and
cv_batches. Reports/checkpoints are immutable. Original seed report is authored.
Price truth/semantic readiness/global clearance are not established by this smoke.
approval-required.json is deliberately NOT approved and cannot authorize spending.
No hidden reasoning is claimed; .env files and credential values are not inspected.
turns-checkpoints.jsonl is the per-turn/checkpoint monitor. It distinguishes native
direct access, HOST_INJECTED_CLI_PARSER, model dispatch, host recheck and omitted
tools. Injected CLI means cli.main(argv,client,stdin/stdout) in process, not an OS
CLI subprocess or model-issued shell command. The bounded supervisor child is
unchanged and separate from this transport distinction.
""")
    return 0 if args.mode == "preflight" or plan.get("outcome") == "PROGRESSION_OBSERVED" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "scripted", "paid"), default="preflight")
    parser.add_argument("--output", required=True, help="NEW directory under checkout .local-runs")
    parser.add_argument("--upstream", default=os.environ.get("TRUSTKERNEL_TRADINGAGENTS_UPSTREAM"))
    parser.add_argument("--scenario", choices=("normal", "omit", "ignore", "truncated"), default="normal")
    parser.add_argument("--verify-transport", choices=("direct", "injected-cli"), default="direct")
    parser.add_argument("--approval", help="NEW user-approved operator artifact; never generated approved by this program")
    parser.add_argument("--fixture", help="Exact reviewed fixture.json from preflight/scripted artifact")
    parser.add_argument("--budget-review", default=os.environ.get("TRUSTKERNEL_BUDGET_REVIEW"), help="Closed read-only operator review JSON; never the ledger itself")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--nonce", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mode == "paid" and args.scenario != "normal":
        parser.error("Authored response scenarios are never available in paid mode")
    if args.mode == "paid" and not args.child and (not args.approval or not args.fixture or not args.budget_review):
        parser.error("Paid disabled: NEW approval, reviewed fixture and closed-ledger review artifact required")
    if args.child:
        try:
            return child(args)
        except Exception as exc:
            # No raw exception, request, credential or private path is printed.
            failure = dict(outcome="STOPPED_NOT_PASS", error_type=type(exc).__name__, paid_mode=args.mode == "paid")
            if getattr(args, "output_authorized", False):
                try:
                    write_new(Path(args.output) / "failure.json", json.dumps(failure, indent=2) + "\n")
                except OSError:
                    pass
            print("SMOKE STOPPED: " + type(exc).__name__)
            return 1
    if not args.upstream:
        parser.error("Supply --upstream or TRUSTKERNEL_TRADINGAGENTS_UPSTREAM; no source paths are guessed")
    try:
        output = new_output(args.output, ROOT)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"New-output guard refused ({type(exc).__name__}).\n")
    nonce = uuid.uuid4().hex
    write_new(output / "parent.json", json.dumps(dict(nonce=nonce, mode=args.mode, profile_digest=digest(PROFILE),
        verify_transport=args.verify_transport)) + "\n")
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", "--nonce", nonce,
        "--mode", args.mode, "--output", str(output), "--upstream", str(Path(args.upstream).resolve()), "--scenario", args.scenario,
        "--verify-transport", args.verify_transport]
    for name in ("approval", "fixture", "budget_review"):
        if getattr(args, name):
            command.extend(["--" + name.replace("_", "-"), str(Path(getattr(args, name)).resolve())])
    try:
        code = subprocess.run(command, cwd=ROOT, timeout=PROFILE["wall_seconds"], check=False).returncode
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as stopped:
        write_new(output / "supervisor-stop.json", json.dumps(dict(outcome=
            "WALL_TIMEOUT_NOT_PASS" if isinstance(stopped, subprocess.TimeoutExpired) else "OPERATOR_STOP_NOT_PASS",
            unknown_paid_reservations="Retained; never reconciled or reset by supervisor")) + "\n")
        code = 1
    print(f"Smoke artifacts: {output}")
    print("Read readiness.json/failure.json and VIEW.md; runtime-trace/trace.jsonl and feedback.sqlite are local review artifacts.")
    print("NO PAID EXECUTION in preflight/scripted modes. Future paid mode requires NEW approval plus unchanged budget/key/model gates.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
