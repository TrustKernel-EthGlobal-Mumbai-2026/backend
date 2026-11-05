"""Authored doubles and separate real persisted A/B transport integration tests."""
import asyncio
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from continuous_verification.cli import main
from continuous_verification import verify, digest
from continuous_verification.service import Principal, ServiceBackend, ServiceError
from continuous_verification.sdk import (
    Access, Client, InterfaceError, MAX_BYTES, OPERATIONS, ServiceErrorAdapter, decode_request,
)

ROOT = Path(__file__).resolve().parents[1]
AUTHORED_PACKET = json.loads((ROOT / "continuous_verification/schemas/example.json").read_text(encoding="utf-8"))
REQUEST = AUTHORED_PACKET["request"]
# Pure-core result over authored example, never a persisted service result.
VERIFY_RESULT = verify(**copy.deepcopy(AUTHORED_PACKET))
# Deliberately contains a failing rule, unready state and separate disposition.
AUTHORED_RESULT = {"fixture": "TRANSPORT_TEST_DOUBLE", "readiness": "NOT_READY",
                   "findings": [{"rule_id": "authored", "status": "FAIL"}],
                   "disposition": "HOLD", "assessment_id": "authored-assessment",
                   "next_cursor": "opaque:1"}


class AuthoredBackend:
    """Accepted verify fixture plus provisional other-operation data; no B service."""

    def __init__(self):
        self.calls = []

    def execute(self, operation, request):
        self.calls.append((operation, request))
        return VERIFY_RESULT if operation == "verify" else AUTHORED_RESULT


def fixture_client(permissions=None):
    return Client(AuthoredBackend(), Access(
        frozenset(permissions if permissions is not None else OPERATIONS.values()),
        frozenset({"authored-run"})))


def service_client(backend):
    """Trusted host wiring to actual reviewed B; no dynamic/model-selected factory."""
    return Client.from_service(backend, access=Access(
        frozenset(OPERATIONS.values()), frozenset({"authored-run", "other-run"})))


def prepare_persisted_service(path, mode="pass"):
    """Author a temporary typed host recording; never native history conversion."""
    packet = copy.deepcopy(AUTHORED_PACKET)
    principal = Principal("collector", frozenset({"configure", *OPERATIONS.values()}),
                          frozenset({"authored-run", "other-run"}))
    backend = ServiceBackend(path, principal=principal, service_id="authored-service",
                             project_on_ingest=mode != "lag")
    try:
        client = service_client(backend)
        for run in ("authored-run", "other-run"):
            backend.configure_run(run, [dict(stream_id="host", collector_id="collector",
                producer_id="authored-host", adapter_version="fixture-1", redaction_profile="authored-public")])
            registered = client.call("register_run", dict(run_id=run, registration_id="registration-1"))
            if not registered["ok"]:
                raise AssertionError(registered)
            backend.install_policy(run, packet["policy"])
        if mode == "fail":
            packet["events"][0]["payload"]["status"] = "ERROR"
        if mode == "cycle":
            packet["events"][0]["parents"] = ["event-3"]
        events = [packet["events"][-1]] if mode == "gap" else packet["events"]
        ingest = dict(run_id="authored-run", batch_id="batch-1", events=events)
        receipt = client.call("ingest_events", ingest)
        if not receipt["ok"]:
            raise AssertionError(receipt)
        if mode not in {"unknown", "gap"}:
            backend.record_coverage("authored-run", "host", packet["checkpoint"]["streams"][0]["capabilities"])
        checkpoint_request = dict(run_id="authored-run", checkpoint_id="checkpoint-1", revision=0,
                                  registry_revision=0, streams=[dict(stream_id="host", requested=3)])
        checkpoint = client.call("checkpoint", checkpoint_request)
        if not checkpoint["ok"]:
            raise AssertionError(checkpoint)
        request = packet["request"]
        request["checkpoint"]["digest"] = digest(checkpoint["result"])
        return backend, request, ingest, checkpoint_request
    except BaseException:
        backend.close()
        raise


class PersistedInterfaceTests(unittest.TestCase):
    """Real accepted A/B code and SQLite over exclusively authored temporary data."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="authored persisted transport ")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "journal with spaces.sqlite"
        self.backend, self.request, self.ingest, self.checkpoint_request = prepare_persisted_service(self.path)
        self.addCleanup(lambda: self.backend.close())
        self.client = service_client(self.backend)

    def cli_call(self, operation, request, *, client=None):
        out, err = io.StringIO(), io.StringIO()
        code = main([operation], client=client or self.client,
                    stdin=io.StringIO(json.dumps(request)), stdout=out, stderr=err)
        result = json.loads(out.getvalue())
        self.assertEqual(code, 0 if result["ok"] else 2 if result["error"]["code"] == "INVALID_REQUEST" else 3)
        self.assertEqual(err.getvalue(), "" if result["ok"] else result["error"]["code"] + "\n")
        return result

    def parity(self, operation, request, *, error=None):
        result = self.client.call(operation, request)
        self.assertEqual(self.cli_call(operation, request), result)
        if error:
            self.assertEqual(result["error"]["code"], error)
        else:
            self.assertTrue(result["ok"], result)
        return result

    def test_actual_sdk_and_injected_cli_all_operations_exact_results(self):
        result = self.parity("verify", self.request)["result"]
        self.assertEqual(result, verify(self.request, **self.backend.resolve_view(self.request)))
        self.assertEqual([f["outcome"] for f in result["findings"]], ["PASS", "PASS"])
        for operation, request in (
            ("register_run", dict(run_id="authored-run", registration_id="registration-1")),
            ("ingest_events", self.ingest), ("checkpoint", self.checkpoint_request),
            ("get_assessment", dict(run_id="authored-run", assessment_id=result["assessment_id"])),
            ("get_evidence", dict(run_id="authored-run", event_id="event-3", span=[0, 8])),
            ("get_run_state", dict(run_id="authored-run")),
            ("list_events", dict(run_id="authored-run", after_cursor=None, limit=1)),
        ):
            self.parity(operation, request)
        self.assertEqual(self.client.call("get_evidence", dict(run_id="authored-run",
                         event_id="event-3", span=[0, 8]))["result"]["excerpt"], "Authored")
        self.assertFalse(self.client.call("get_run_state", dict(run_id="authored-run"))["result"]["atomic_semantic_ready"])
        self.parity("acknowledge_feedback", dict(run_id="authored-run"), error="UNSUPPORTED_OPERATION")

    def test_actual_nested_foreign_refs_conflicts_and_model_configuration_denied(self):
        result = self.client.call("verify", self.request)["result"]
        for operation, request in (
            ("get_evidence", dict(run_id="other-run", event_id="event-1")),
            ("get_assessment", dict(run_id="other-run", assessment_id=result["assessment_id"])),
        ):
            self.parity(operation, request, error="FORBIDDEN")
        foreign_checkpoint = copy.deepcopy(self.request)
        foreign_checkpoint.update(run_id="other-run", request_id="foreign-checkpoint")
        self.parity("verify", foreign_checkpoint, error="FORBIDDEN")
        policy = copy.deepcopy(AUTHORED_PACKET["policy"])
        policy["policy_id"] = "other-policy"
        self.backend.install_policy("other-run", policy)
        foreign_policy = copy.deepcopy(self.request)
        foreign_policy.update(request_id="foreign-policy")
        foreign_policy["policy"].update(policy_id="other-policy", digest=digest(policy))
        self.parity("verify", foreign_policy, error="FORBIDDEN")
        foreign = copy.deepcopy(AUTHORED_PACKET["events"][0])
        foreign.update(run_id="other-run", event_id="foreign-event")
        self.assertTrue(self.client.call("ingest_events", dict(run_id="other-run", batch_id="foreign", events=[foreign]))["ok"])
        for field in ("report_event_id", "dependencies"):
            request = copy.deepcopy(self.request)
            request.update(request_id="foreign-" + field)
            request["proposal"][field] = ["foreign-event"] if field == "dependencies" else "foreign-event"
            self.parity("verify", request, error="FORBIDDEN")
        for field in ("checkpoint", "policy"):
            request = copy.deepcopy(self.request)
            request.update(request_id="stale-" + field)
            request[field]["digest"] = "0" * 64
            self.parity("verify", request, error="CONFLICT")
        for operation, request in (
            ("register_run", dict(run_id="authored-run", registration_id="registration-1", streams=[])),
            ("checkpoint", dict(self.checkpoint_request, established_by="SERVICE_ESTABLISHED")),
            ("get_evidence", dict(run_id="authored-run", event_id="event-3", path="not-a-server-file")),
            ("list_events", dict(run_id="authored-run", after_cursor=None, limit=True)),
        ):
            self.parity(operation, request, error="INVALID_REQUEST")
        self.parity("get_evidence", dict(run_id="authored-run", event_id="absent"), error="NOT_FOUND")

    def test_actual_cursor_pins_prefix_across_cli_and_restart(self):
        first = self.parity("list_events", dict(run_id="authored-run", after_cursor=None, limit=1))["result"]
        cursor = first["next_cursor"]
        late = copy.deepcopy(AUTHORED_PACKET["events"][0])
        late.update(event_id="late-4", sequence=4)
        self.assertTrue(self.client.call("ingest_events", dict(run_id="authored-run", batch_id="late", events=[late]))["ok"])
        principal = self.backend.principal
        self.backend.close()
        self.backend = ServiceBackend(self.path, principal=principal, service_id="authored-service")
        self.client = service_client(self.backend)
        continuation = self.parity("list_events", dict(run_id="authored-run", after_cursor=cursor, limit=100))["result"]
        self.assertEqual(continuation["snapshot_id"], first["snapshot_id"])
        self.assertEqual([e["event_id"] for e in continuation["events"]], ["event-2", "event-3"])
        self.assertFalse(continuation["has_more"])
        self.assertIsNone(continuation["next_cursor"])
        self.parity("list_events", dict(run_id="other-run", after_cursor=cursor, limit=1), error="FORBIDDEN")
        self.parity("list_events", dict(run_id="authored-run", after_cursor="invalid", limit=1), error="INVALID_CURSOR")
        latest = self.parity("list_events", dict(run_id="authored-run", after_cursor=None, limit=100))["result"]
        self.assertEqual(len(latest["events"]), 4)

    def test_backend_principal_and_assigned_collector_cannot_be_bypassed_by_sdk_grants(self):
        self.backend.close()
        self.backend = ServiceBackend(self.path, principal=Principal("viewer", frozenset({"read", "verify"}),
                                      frozenset({"authored-run"})), service_id="authored-service")
        self.client = service_client(self.backend)  # deliberately broader preliminary SDK grants
        scoped = Client.from_service(self.backend)
        self.assertEqual(scoped.access.permissions, self.backend.principal.permissions)
        self.assertEqual(scoped.access.run_ids, self.backend.principal.run_ids)
        self.assertEqual(scoped.call("checkpoint", self.checkpoint_request)["error"]["code"], "FORBIDDEN")
        for operation, request in (("ingest_events", self.ingest), ("checkpoint", self.checkpoint_request),
                ("register_run", dict(run_id="authored-run", registration_id="registration-1")),
                ("get_run_state", dict(run_id="other-run"))):
            self.parity(operation, request, error="FORBIDDEN")
        self.backend.close()
        self.backend = ServiceBackend(self.path, principal=Principal("unassigned", frozenset({"collect"}),
                                      frozenset({"authored-run"})), service_id="authored-service")
        self.client = service_client(self.backend)
        self.parity("ingest_events", self.ingest, error="FORBIDDEN")

    def test_actual_persisted_status_matrix_survives_sdk_cli_and_reopen(self):
        for mode in ("pass", "fail", "unknown", "lag", "gap", "cycle"):
            with self.subTest(mode=mode):
                backend, request, _, _ = prepare_persisted_service(Path(self.tmp.name) / (mode + ".sqlite"), mode)
                try:
                    client = service_client(backend)
                    result = client.call("verify", request)
                    self.assertTrue(result["ok"], result)
                    self.assertEqual(result["result"], verify(request, **backend.resolve_view(request)))
                    self.assertEqual(self.cli_call("verify", request, client=client), result)
                    expected_status = {"lag": "NOT_READY", "gap": "CAPTURE_GAP", "cycle": "ERROR"}.get(mode, "ASSESSED")
                    self.assertEqual(result["result"]["status"], expected_status)
                    outcomes = [f["outcome"] for f in result["result"]["findings"]]
                    if mode == "pass": self.assertEqual(outcomes, ["PASS", "PASS"])
                    if mode == "fail": self.assertIn("FAIL", outcomes)
                    if mode == "unknown": self.assertEqual(set(outcomes), {"INCONCLUSIVE"})
                    if mode in {"lag", "gap", "cycle"}:
                        self.assertNotIn("PASS", outcomes)
                        self.assertEqual(result["result"]["disposition"], "HOLD")
                    if mode == "cycle": self.assertIsNone(result["result"]["binding"])
                    principal = backend.principal
                finally:
                    backend.close()
                reopened = ServiceBackend(Path(self.tmp.name) / (mode + ".sqlite"), principal=principal,
                                          service_id="authored-service")
                try:
                    read = service_client(reopened).call("get_assessment", dict(run_id="authored-run",
                            assessment_id=result["result"]["assessment_id"]))
                    self.assertEqual(read, result)
                finally:
                    reopened.close()


class TransportTests(unittest.TestCase):
    def test_service_error_adapter_uses_trusted_type_and_fixed_messages(self):
        class AuthoredServiceError(Exception):
            def __init__(self, code):
                self.code = code
                self.public_message = "authored private diagnostic must not leak"
                self.issues = [{"private": "authored private content"}]
                super().__init__(self.public_message)
        codes = {"INVALID_REQUEST", "FORBIDDEN", "NOT_FOUND", "CONFLICT", "INVALID_CURSOR",
                 "UNSUPPORTED_OPERATION", "BACKEND_UNAVAILABLE"}
        for code in codes | {"UNREVIEWED_ERROR"}:
            class AuthoredService:
                def execute(self, operation, request):
                    raise AuthoredServiceError(code)
            client = Client(ServiceErrorAdapter(AuthoredService(), AuthoredServiceError),
                            fixture_client().access)
            result = client.call("verify", REQUEST)
            self.assertEqual(result["error"]["code"], code if code in codes else "BACKEND_ERROR")
            self.assertNotIn("private", json.dumps(result))
            # Unadapted typed exceptions remain generic until the host opts in.
            self.assertEqual(Client(AuthoredService(), fixture_client().access).call(
                "verify", REQUEST)["error"]["code"], "BACKEND_ERROR")

    def test_verify_contract_rejects_malformed_inputs_before_backend(self):
        for mutate in (
            lambda r: r.update(contract_version="continuous-verification-0.1"),
            lambda r: r["proposal"].update(content="changed without digest"),
            lambda r: r.update(checkpoint={"path": "not-a-server-file"}),
            lambda r: r.update(policy={"coverage": "model-selected"}),
            lambda r: r.update(unknown_key=True),
        ):
            request = copy.deepcopy(REQUEST)
            mutate(request)
            client = fixture_client()
            out = io.StringIO()
            code = main(["verify"], client=client, stdin=io.StringIO(json.dumps(request)),
                        stdout=out, stderr=io.StringIO())
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(out.getvalue())["error"]["code"], "INVALID_REQUEST")
            self.assertEqual(client.backend.calls, [])

    def test_verify_contract_rejects_forged_and_foreign_results(self):
        for mutate in (
            lambda r: r.update(assessment_id="forged-id"),
            lambda r: r.update(run_id="other-run"),
            lambda r: r.update(status="NOT_READY"),
            lambda r: r["binding"].update(request_digest="0" * 64),
        ):
            result = copy.deepcopy(VERIFY_RESULT)
            mutate(result)
            if result["assessment_id"] != "forged-id":
                result["assessment_id"] = "assessment-" + digest(
                    {k: v for k, v in result.items() if k != "assessment_id"})
            class AuthoredInvalidResult:
                def execute(self, operation, request):
                    return result
            response = Client(AuthoredInvalidResult(), fixture_client().access).call("verify", REQUEST)
            self.assertEqual(response["error"]["code"], "BACKEND_ERROR")

    def test_valid_result_for_old_request_is_rejected(self):
        for mutate in (
            lambda r: r.update(request_id="new-request"),
            lambda r: r["proposal"].update(revision=1),
            lambda r: r["checkpoint"].update(digest="1" * 64),
            lambda r: r["policy"].update(digest="2" * 64),
        ):
            request = copy.deepcopy(REQUEST)
            mutate(request)
            self.assertEqual(fixture_client().call("verify", request)["error"]["code"], "BACKEND_ERROR")

    def test_valid_core_statuses_preserved_through_sdk_and_cli_authored_adapter(self):
        for mode in ("pass", "fail", "unready", "gap", "error"):
            packet = copy.deepcopy(AUTHORED_PACKET)
            if mode == "fail":
                packet["events"][0]["payload"]["status"] = "ERROR"
            if mode == "unready":
                packet["checkpoint"]["streams"][0]["projected_through"] = 0
            if mode == "gap":
                packet["checkpoint"]["streams"][0]["gaps"] = [[1, 1]]
            packet["request"]["checkpoint"]["digest"] = digest(packet["checkpoint"])
            if mode == "error":
                # Reproduce a future-parent cycle in authored input to A0.2.
                packet["events"][0]["parents"] = ["event-3"]
            result = verify(**packet)
            if mode == "pass":
                self.assertTrue(all(f["outcome"] == "PASS" for f in result["findings"]))
            if mode == "fail":
                self.assertTrue(any(f["outcome"] == "FAIL" for f in result["findings"]))
            if mode == "error":
                self.assertEqual(result["status"], "ERROR")
                self.assertIsNone(result["binding"])
                self.assertFalse(any(f["outcome"] == "PASS" for f in result["findings"]))
            if mode in {"unready", "gap"}:
                self.assertEqual(result["status"], "NOT_READY" if mode == "unready" else "CAPTURE_GAP")
            class AuthoredCoreResult:
                def execute(self, operation, request):
                    return result
            client = Client(AuthoredCoreResult(), fixture_client().access)
            out = io.StringIO()
            code = main(["verify"], client=client,
                        stdin=io.StringIO(json.dumps(packet["request"])),
                        stdout=out, stderr=io.StringIO())
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue()), {"ok": True, "result": result})

    def test_every_operation_cli_sdk_preserves_result_and_input(self):
        for operation in OPERATIONS:
            with self.subTest(operation=operation):
                client = fixture_client()
                request = dict(REQUEST, after_cursor="opaque:0") if operation == "list_events" else REQUEST
                out, err = io.StringIO(), io.StringIO()
                code = main([operation], client=client,
                            stdin=io.StringIO(json.dumps(request)), stdout=out, stderr=err)
                self.assertEqual(code, 0)  # invocation success is not rule PASS
                self.assertEqual(json.loads(out.getvalue()), client.call(operation, request))
                self.assertEqual(json.loads(out.getvalue())["result"],
                                 VERIFY_RESULT if operation == "verify" else AUTHORED_RESULT)
                self.assertEqual(client.backend.calls[0], (operation, request))
                self.assertEqual(err.getvalue(), "")

    def test_no_backend_never_fabricates_success(self):
        out, err = io.StringIO(), io.StringIO()
        code = main(["verify"], stdin=io.StringIO(json.dumps(REQUEST)), stdout=out, stderr=err)
        result = json.loads(out.getvalue())
        self.assertEqual(code, 3)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "BACKEND_UNAVAILABLE")
        self.assertNotIn("result", result)
        self.assertEqual(err.getvalue().strip(), "BACKEND_UNAVAILABLE")

    def test_permission_and_run_scope_deny_before_backend(self):
        client = fixture_client({"read", "verify"})
        for operation in ("register_run", "ingest_events", "checkpoint", "acknowledge_feedback"):
            self.assertEqual(client.call(operation, REQUEST)["error"]["code"], "FORBIDDEN")
        forged = dict(REQUEST, run_id="other-run", permissions=["collect"], run_ids=["other-run"])
        self.assertEqual(client.call("get_evidence", forged)["error"]["code"], "FORBIDDEN")
        self.assertEqual(client.backend.calls, [])
        no_grants = Client(client.backend)
        self.assertEqual(no_grants.call("verify", REQUEST)["error"]["code"], "FORBIDDEN")

    def test_strict_json_limits_and_request_validation(self):
        bad = ['[]', '{', '{"run_id":"a","run_id":"b"}',
               '{"run_id":"a","x":NaN}', '{"run_id":"a","x":1e999}',
               json.dumps({"run_id": "a", "x": "z" * MAX_BYTES}),
               '{"run_id":"a","x":' + '[' * 40 + '0' + ']' * 40 + '}']
        for raw in bad:
            with self.subTest(raw=raw[:60]), self.assertRaises(InterfaceError):
                decode_request(raw)
        client = fixture_client()
        for value in ({}, {"run_id": False}, {"run_id": " "}, {"run_id": "x" * 257},
                      {"run_id": "a", "x": object()}, {"run_id": "a", 1: "bad"}):
            self.assertFalse(client.call("verify", value)["ok"])
        self.assertEqual(client.backend.calls, [])

    def test_cli_parse_and_input_errors_are_json(self):
        for args, source in [(["wrong"], "{}"), (["verify", "--unknown"], "{}"),
                             (["verify"], "{}"), (["verify"], "{invalid")]:
            out, err = io.StringIO(), io.StringIO()
            self.assertEqual(main(args, stdin=io.StringIO(source), stdout=out, stderr=err), 2)
            self.assertFalse(json.loads(out.getvalue())["ok"])
            self.assertTrue(err.getvalue())

    def test_safe_path_and_argument_subprocess_handling(self):
        with tempfile.TemporaryDirectory(prefix="authored transport spaces ") as directory:
            # Shell metacharacters and a leading dash remain a literal filename.
            path = Path(directory) / "-request & echo SHOULD_NOT_EXECUTE.json"
            path.write_text(json.dumps(REQUEST), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-B", "-m", "continuous_verification.cli", "verify",
                 "--request", str(path)], cwd=ROOT, capture_output=True, text=True, timeout=15)
            self.assertEqual(completed.returncode, 3)
            self.assertEqual(json.loads(completed.stdout)["error"]["code"], "BACKEND_UNAVAILABLE")
            self.assertEqual(completed.stderr.strip(), "BACKEND_UNAVAILABLE")
            missing = io.StringIO()
            self.assertEqual(main(["verify", "--request", str(path) + ".absent"],
                                  stdout=missing, stderr=io.StringIO()), 2)
            self.assertEqual(json.loads(missing.getvalue())["error"]["code"], "INPUT_ERROR")

    def test_backend_errors_do_not_echo_private_data(self):
        class Broken:
            def execute(self, operation, request):
                raise RuntimeError("private diagnostic must not leak")
        result = Client(Broken(), fixture_client().access).call("verify", REQUEST)
        self.assertEqual(result["error"]["code"], "BACKEND_ERROR")
        self.assertNotIn("private", json.dumps(result))

    def test_invalid_backend_results_remain_backend_errors(self):
        for value in ([], {"invalid": float("nan")}, {"invalid": object()}):
            class Broken:
                def execute(self, operation, request):
                    return value
            result = Client(Broken(), fixture_client().access).call("verify", REQUEST)
            self.assertEqual(result["error"]["code"], "BACKEND_ERROR")

    def test_mcp_missing_and_unsupported_dependency_are_explicit(self):
        from importlib.metadata import PackageNotFoundError
        from continuous_verification.mcp_server import build_server
        with patch("continuous_verification.mcp_server.version", side_effect=PackageNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "dependency missing"):
                build_server()
        with patch("continuous_verification.mcp_server.version", return_value="2.0.0"):
            with self.assertRaisesRegex(RuntimeError, "Unsupported"):
                build_server()

    def test_requests_and_results_are_copied(self):
        client = fixture_client()
        result = client.call("verify", REQUEST)
        result["result"]["findings"].clear()
        self.assertTrue(VERIFY_RESULT["findings"])
        self.assertIsNot(client.backend.calls[0][1], REQUEST)


@unittest.skipUnless(importlib.util.find_spec("mcp"),
                     "MISSING optional official mcp>=1.28,<2: genuine discovery/invocation unexecuted")
class GenuineMCPTests(unittest.TestCase):
    def test_official_stdio_actual_persisted_service_parity_matrix_and_restart(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        def write_host(path, *, actor="collector", permissions=frozenset(OPERATIONS.values())):
            # The host code and argv are authored/operator-owned, never tool arguments.
            path.write_text(
                "import sys\n"
                "from continuous_verification.service import Principal, ServiceBackend, ServiceError\n"
                "from continuous_verification.sdk import Access, Client, ServiceErrorAdapter\n"
                "from continuous_verification.mcp_server import build_server\n"
                f"permissions = {permissions!r}\n"
                "runs = frozenset({'authored-run','other-run'})\n"
                f"b = ServiceBackend(sys.argv[1], principal=Principal({actor!r}, permissions, runs), "
                "service_id='authored-service')\n"
                "try:\n"
                "    build_server(Client.from_service(b)).run(transport='stdio')\n"
                "finally:\n"
                "    b.close()\n", encoding="utf-8")

        async def session_plan(host, database, plan, *, late_request=None, continuation=None):
            params = StdioServerParameters(command=sys.executable,
                args=["-B", str(host), str(database)], env={"PYTHONPATH": str(ROOT)})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self.assertEqual({t.name for t in listed.tools}, set(OPERATIONS))
                    # No trusted configure/policy/coverage method becomes an MCP tool.
                    for operation, request, expected in plan:
                        response = await session.call_tool(operation, {"request": request})
                        self.assertFalse(response.isError)
                        self.assertEqual(json.loads(response.content[0].text), expected, operation)
                    if late_request:
                        response = await session.call_tool("ingest_events", {"request": late_request})
                        self.assertTrue(json.loads(response.content[0].text)["ok"])
                    if continuation:
                        request, expected = continuation
                        response = await session.call_tool("list_events", {"request": request})
                        self.assertEqual(json.loads(response.content[0].text), expected)

        with tempfile.TemporaryDirectory(prefix="authored real service MCP ") as directory:
            root = Path(directory)
            host = root / "trusted host with spaces.py"
            write_host(host)
            for mode in ("pass", "fail", "unknown", "lag", "gap", "cycle"):
                with self.subTest(mode=mode):
                    database = root / (mode + " authored.sqlite")
                    backend, request, ingest, checkpoint = prepare_persisted_service(database, mode)
                    try:
                        client = service_client(backend)
                        result = client.call("verify", request)
                        self.assertTrue(result["ok"], result)
                        self.assertEqual(result["result"], verify(request, **backend.resolve_view(request)))
                        first_request = dict(run_id="authored-run", after_cursor=None, limit=1)
                        first = client.call("list_events", first_request)
                        operations = [
                            ("register_run", dict(run_id="authored-run", registration_id="registration-1")),
                            ("ingest_events", ingest), ("checkpoint", checkpoint), ("verify", request),
                            ("get_assessment", dict(run_id="authored-run", assessment_id=result["result"]["assessment_id"])),
                            ("get_evidence", dict(run_id="authored-run", event_id="event-3", span=[0, 8])),
                            ("get_run_state", dict(run_id="authored-run")),
                            ("list_events", first_request),
                            ("acknowledge_feedback", dict(run_id="authored-run")),
                            ("get_evidence", dict(run_id="other-run", event_id="event-3")),
                            ("get_assessment", dict(run_id="other-run", assessment_id=result["result"]["assessment_id"])),
                            ("list_events", dict(run_id="authored-run", after_cursor="invalid", limit=1)),
                            ("register_run", dict(run_id="authored-run", registration_id="registration-1", coverage="model-issued")),
                        ]
                        foreign = copy.deepcopy(request)
                        foreign.update(run_id="other-run", request_id="foreign-checkpoint")
                        stale = copy.deepcopy(request)
                        stale.update(request_id="stale-checkpoint")
                        stale["checkpoint"]["digest"] = "0" * 64
                        operations.extend([("verify", foreign), ("verify", stale)])
                        if mode == "pass":
                            other_policy = copy.deepcopy(AUTHORED_PACKET["policy"])
                            other_policy["policy_id"] = "other-policy"
                            backend.install_policy("other-run", other_policy)
                            event = copy.deepcopy(AUTHORED_PACKET["events"][0])
                            event.update(run_id="other-run", event_id="foreign-event")
                            self.assertTrue(client.call("ingest_events", dict(run_id="other-run",
                                batch_id="foreign-event-batch", events=[event]))["ok"])
                            foreign_policy = copy.deepcopy(request)
                            foreign_policy.update(request_id="foreign-policy")
                            foreign_policy["policy"].update(policy_id="other-policy", digest=digest(other_policy))
                            operations.append(("verify", foreign_policy))
                            for field in ("dependencies", "report_event_id"):
                                nested = copy.deepcopy(request)
                                nested.update(request_id="foreign-" + field)
                                nested["proposal"][field] = ["foreign-event"] if field == "dependencies" else "foreign-event"
                                operations.append(("verify", nested))
                            operations.extend([
                                ("get_evidence", dict(run_id="authored-run", event_id="event-3", path="not-a-server-file")),
                                ("get_assessment", dict(run_id="authored-run", assessment_id="absent")),
                            ])
                        cursor = first["result"]["next_cursor"]
                        continuation = None
                        if cursor:
                            operations.append(("list_events", dict(run_id="other-run", after_cursor=cursor, limit=100)))
                            page_request = dict(run_id="authored-run", after_cursor=cursor, limit=100)
                            continuation = (page_request, client.call("list_events", page_request))
                        plan = []
                        for operation, body in operations:
                            expected = client.call(operation, body)
                            # The actual CLI function uses this same persisted backend.
                            out = io.StringIO()
                            exit_code = main([operation], client=client, stdin=io.StringIO(json.dumps(body)),
                                             stdout=out, stderr=io.StringIO())
                            self.assertEqual(json.loads(out.getvalue()), expected)
                            self.assertEqual(exit_code == 0, expected["ok"])
                            plan.append((operation, body, expected))
                        principal = backend.principal
                    finally:
                        backend.close()  # one service owner at a time
                    late = copy.deepcopy(AUTHORED_PACKET["events"][0])
                    late.update(event_id="late-4", sequence=4)
                    late_request = dict(run_id="authored-run", batch_id="late", events=[late]) if mode == "pass" else None
                    asyncio.run(asyncio.wait_for(session_plan(host, database, plan,
                        late_request=late_request, continuation=continuation), timeout=45))
                    if mode == "pass":
                        # A new real stdio process reopens the same SQLite/cursor state.
                        asyncio.run(asyncio.wait_for(session_plan(host, database, [],
                            continuation=continuation), timeout=45))
                    reopened = ServiceBackend(database, principal=principal, service_id="authored-service")
                    try:
                        self.assertEqual(service_client(reopened).call("get_assessment", dict(
                            run_id="authored-run", assessment_id=result["result"]["assessment_id"])), result)
                        if mode == "pass":
                            self.assertEqual(reopened.audit()["typed_events"], 5)  # includes separate foreign run
                    finally:
                        reopened.close()

    def test_official_sdk_stdio_discovery_and_authored_transport_parity(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def check(args, expected):
            params = StdioServerParameters(command=sys.executable, args=args,
                                           env={"PYTHONPATH": str(ROOT)})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    self.assertEqual({tool.name for tool in listed.tools}, set(OPERATIONS))
                    for tool in listed.tools:
                        self.assertEqual(set(tool.inputSchema["properties"]), {"request"})
                    for operation in OPERATIONS:
                        called = await session.call_tool(operation, {"request": REQUEST})
                        self.assertFalse(called.isError)
                        self.assertEqual(json.loads(called.content[0].text),
                                         expected[operation] if operation in expected else expected)
                    malformed = await session.call_tool("get_evidence", {"request": {"path": "not-a-server-file"}})
                    self.assertEqual(json.loads(malformed.content[0].text)["error"]["code"], "INVALID_REQUEST")
                    path_arg = await session.call_tool("get_evidence", {"path": "not-a-server-file"})
                    self.assertTrue(path_arg.isError)
                    invalid_verify = await session.call_tool("verify", {"request": {"run_id": "authored-run"}})
                    self.assertEqual(json.loads(invalid_verify.content[0].text)["error"]["code"], "INVALID_REQUEST")

        with tempfile.TemporaryDirectory(prefix="authored MCP host ") as directory:
            host = Path(directory) / "host with spaces.py"
            # An explicit authored host is used; no production fixture switch.
            host.write_text(
                "from continuous_verification.mcp_server import build_server\n"
                "from continuous_verification.sdk import Client, Access, OPERATIONS\n"
                "class AuthoredBackend:\n"
                "    def execute(self, operation, request):\n"
                f"        return {VERIFY_RESULT!r} if operation == 'verify' else {AUTHORED_RESULT!r}\n"
                "build_server(Client(AuthoredBackend(), Access(frozenset(OPERATIONS.values()), "
                "frozenset({'authored-run'})))).run(transport='stdio')\n", encoding="utf-8")
            asyncio.run(asyncio.wait_for(check(["-B", str(host)],
                         {op: {"ok": True, "result": VERIFY_RESULT if op == "verify" else AUTHORED_RESULT}
                          for op in OPERATIONS}), timeout=45))
        asyncio.run(asyncio.wait_for(check(["-B", "-m", "continuous_verification.mcp_server"],
                     Client().call("verify", REQUEST)), timeout=45))


if __name__ == "__main__":
    unittest.main()
