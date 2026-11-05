"""Accepted A contract checks plus authored transport doubles; no persisted B core."""
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


class TransportTests(unittest.TestCase):
    def test_proposed_service_error_adapter_uses_trusted_type_and_fixed_messages(self):
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
