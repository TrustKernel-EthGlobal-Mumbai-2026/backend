"""Operator-configured local host; no model-selected paths, grants or factories.

Bootstrap starts empty with UNKNOWN coverage. Client tools are verify/read only.
Reuse the existing single-owner worker; async capture waits for its accepted API.
"""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

from . import contracts
from .cli import main as cli_main
from .mcp_server import build_server
from .sdk import Access, Client, InterfaceError, MAX_BYTES, ServiceErrorAdapter, failure
from .service import Principal, ServiceBackend, ServiceError
from .tradingagents import LocalServiceWorker

CONFIG_VERSION = "trustkernel-host-1"
CLIENT_OPERATIONS = ("verify", "get_assessment", "get_evidence", "get_run_state", "list_events")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_DIRECTORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}\Z")


class HostError(InterfaceError):
    def __init__(self, message="Invalid or unavailable trusted host configuration."):
        super().__init__("CONFIG_ERROR", message)


@dataclass(frozen=True)
class HostConfig:
    directory: Path
    body: dict

    @property
    def state(self):
        if self.body["mode"] != "new":
            raise HostError("Existing-service profiles have no initialization authority.")
        return self.directory / self.body["state_directory"]

    @property
    def database(self):
        if self.body["mode"] == "existing":
            selected = Path(self.body["database"])
            return selected if selected.is_absolute() else self.directory / selected
        return self.state / "journal.sqlite"

    @property
    def run_ids(self):
        if self.body["mode"] == "existing":
            return frozenset(self.body["run_ids"])
        return frozenset(run["run_id"] for run in self.body["runs"])


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise HostError()


def _identifier(value):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise HostError()


def _read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result
    try:
        with path.open("rb") as source:
            data = source.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("size")
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
        contracts.canonical_json(value)
        return value
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise HostError() from None


def load_config(path) -> HostConfig:
    """Read one explicitly operator-selected JSON configuration, without mutation."""
    source = Path(path).resolve()
    body = _read_json(source)
    if type(body) is not dict:
        raise HostError()
    if body.get("config_version") != CONFIG_VERSION:
        raise HostError()
    for name in ("service_id", "client_id"):
        if name not in body:
            raise HostError()
        _identifier(body[name])
    if body.get("mode") == "existing":
        _keys(body, {"config_version", "mode", "database", "service_id", "client_id", "run_ids"})
        if (type(body["database"]) is not str or not body["database"] or "\x00" in body["database"]
                or body["database"].startswith(("\\\\", "//")) or "://" in body["database"]
                or type(body["run_ids"]) is not list or not 1 <= len(body["run_ids"]) <= 100):
            raise HostError()
        for run in body["run_ids"]:
            _identifier(run)
        if len(set(body["run_ids"])) != len(body["run_ids"]):
            raise HostError()
        return HostConfig(source.parent, body)
    _keys(body, {"config_version", "mode", "state_directory", "service_id", "collector_id", "client_id", "runs"})
    if body["mode"] != "new":
        raise HostError()
    _identifier(body["collector_id"])
    if body["collector_id"] == body["client_id"]:
        raise HostError("Client and collector identities must be distinct.")
    name = body["state_directory"]
    if type(name) is not str or not _DIRECTORY.fullmatch(name) or name.endswith((" ", ".")):
        raise HostError("State must name a new direct child directory beside the configuration.")
    if type(body["runs"]) is not list or not 1 <= len(body["runs"]) <= 100:
        raise HostError()
    runs = set()
    for run in body["runs"]:
        _keys(run, {"run_id", "registration_id", "streams", "policy"})
        _identifier(run["run_id"])
        _identifier(run["registration_id"])
        if run["run_id"] in runs:
            raise HostError()
        runs.add(run["run_id"])
        if type(run["streams"]) is not list or not 1 <= len(run["streams"]) <= 100:
            raise HostError()
        streams = set()
        for stream in run["streams"]:
            _keys(stream, {"stream_id", "producer_id", "adapter_version", "redaction_profile"})
            for value in stream.values():
                _identifier(value)
            if stream["stream_id"] in streams:
                raise HostError()
            streams.add(stream["stream_id"])
        try:
            contracts.validate_policy(run["policy"])
        except contracts.ContractError:
            raise HostError("Operator policy violates the accepted contract.") from None
    config = HostConfig(source.parent, body)
    if config.state.resolve().parent != source.parent or config.state.is_symlink():
        raise HostError("State directory escapes the configuration directory.")
    return config


def _binding(config):
    return {"host_version": CONFIG_VERSION, "config_digest": contracts.digest(config.body)}


def _check_initialized(config):
    if config.body["mode"] == "existing":
        if not config.database.is_file() or config.database.is_symlink():
            raise HostError("Existing-service database is missing or not a regular local file.")
        return
    if (not config.database.is_file() or config.database.is_symlink()
            or config.database.resolve().parent != config.state.resolve()
            or _read_json(config.state / "host.json") != _binding(config)):
        raise HostError("Host state is missing or does not match the operator configuration.")


def _worker(config, *, actor, permissions):
    principal = Principal(actor, frozenset(permissions), config.run_ids)
    return LocalServiceWorker(lambda: ServiceBackend(config.database, principal=principal,
                                                      service_id=config.body["service_id"]))


def initialize(path) -> dict:
    """Create new operator-owned state only; never overwrite or seed observations."""
    config = load_config(path)
    if config.body["mode"] != "new":
        raise HostError("Existing-service profiles cannot initialize state.")
    try:
        config.state.mkdir(exist_ok=False)
    except OSError:
        raise HostError("Initialization requires a new state directory.") from None
    worker = None
    try:
        worker = _worker(config, actor=config.body["collector_id"], permissions={"configure", "collect"})
        for run in config.body["runs"]:
            streams = [dict(stream, collector_id=config.body["collector_id"]) for stream in run["streams"]]
            worker.configure_run(run["run_id"], streams)
            worker.install_policy(run["run_id"], run["policy"])
            worker.execute("register_run", {"run_id": run["run_id"], "registration_id": run["registration_id"]})
        (config.state / "host.json").write_text(json.dumps(_binding(config)), encoding="utf-8")
    except Exception:
        # Partial setup is preserved for inspection. Never delete or reuse it.
        raise HostError("Host initialization failed; retained partial state requires operator review.") from None
    finally:
        if worker is not None:
            worker.close()
    return {"run_ids": sorted(config.run_ids), "coverage": "UNKNOWN", "observations_seeded": 0}


@contextmanager
def collector_session(path):
    """Trusted Python host API only; separate collect authority, no configuration grant.

    This is not a poller/daemon. B's proposed async API is intentionally unbound.
    """
    config = load_config(path)
    if config.body["mode"] != "new":
        raise HostError("Existing-service profiles expose verify/read only.")
    _check_initialized(config)
    worker = None
    try:
        worker = _worker(config, actor=config.body["collector_id"], permissions={"collect"})
        yield worker
    finally:
        if worker is not None:
            worker.close()


@contextmanager
def client_session(path):
    """Configured SDK/CLI/MCP client with fixed verify/read grants; owns no collector."""
    config = load_config(path)
    _check_initialized(config)
    worker = None
    try:
        worker = _worker(config, actor=config.body["client_id"], permissions={"verify", "read"})
        yield Client(ServiceErrorAdapter(worker, ServiceError), Access(
            frozenset({"verify", "read"}), config.run_ids))
    finally:
        if worker is not None:
            worker.close()


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InterfaceError("INVALID_ARGUMENTS", "Invalid host arguments; see --help.")


def main(argv=None) -> int:
    parser = _Parser(description="Configured local TrustKernel CLI; operator initialization is separate.")
    parser.add_argument("--config", required=True, help="Operator-owned JSON configuration")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("init", help="Initialize new empty state; no observations or coverage")
    for operation in CLIENT_OPERATIONS:
        command = commands.add_parser(operation)
        command.add_argument("--request", help="UTF-8 inline request file; otherwise stdin")
    try:
        args = parser.parse_args(argv)
        if args.operation == "init":
            print(json.dumps({"ok": True, "result": initialize(args.config)}))
            return 0
        with client_session(args.config) as client:
            forwarded = [args.operation] + (["--request", args.request] if args.request is not None else [])
            return cli_main(forwarded, client=client)
    except InterfaceError as error:
        result = failure(error)
        code = 2 if error.code == "INVALID_ARGUMENTS" else 3
    except Exception:
        result = failure(InterfaceError("BACKEND_UNAVAILABLE", "Configured host could not open its service."))
        code = 3
    print(json.dumps(result))
    print(result["error"]["code"], file=sys.stderr)
    return code


def mcp_main(argv=None) -> int:
    parser = _Parser(description="Configured TrustKernel stdio MCP; verify/read tools only.")
    parser.add_argument("--config", required=True, help="Operator-owned JSON configuration")
    try:
        args = parser.parse_args(argv)
        with client_session(args.config) as client:
            build_server(client, operations=CLIENT_OPERATIONS).run(transport="stdio")
        return 0
    except InterfaceError as error:
        print(error.code, file=sys.stderr)
    except Exception:
        print("Configured MCP host unavailable; check configuration and optional MCP dependency.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
