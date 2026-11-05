"""Transport boundary only; domain contracts and the real backend are pending.

Backend.execute is a provisional seam, not an accepted service interface. It
must validate domain schemas and enforce object ownership before accessing data.
"""
from dataclasses import dataclass
import json
from typing import Any, Protocol


OPERATIONS = {
    "register_run": "collect", "ingest_events": "collect", "checkpoint": "collect",
    "verify": "verify", "acknowledge_feedback": "feedback",
    "get_assessment": "read", "get_evidence": "read",
    "get_run_state": "read", "list_events": "read",
}
MAX_BYTES = 1024 * 1024
MAX_DEPTH = 32


class InterfaceError(Exception):
    """Safe, public transport/adapter error, never a per-rule finding."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Backend(Protocol):
    def execute(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        """Validate A's schema, authorize referenced objects, invoke B's core."""
        ...


@dataclass(frozen=True)
class Access:
    """Trusted host grants; never constructed from an MCP request body."""

    permissions: frozenset[str] = frozenset()
    run_ids: frozenset[str] = frozenset()


def _json_copy(value: Any) -> Any:
    def check(item: Any, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise ValueError("depth")
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("keys")
            for child in item.values():
                check(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                check(child, depth + 1)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("type")
    try:
        check(value, 0)
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_BYTES:
            raise ValueError("size")
        return json.loads(encoded)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise InterfaceError("INVALID_JSON", "Expected bounded finite JSON data.") from None


def decode_request(text: str) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise ValueError("size")
        value = json.loads(text, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))
    except (ValueError, RecursionError, UnicodeError):
        raise InterfaceError("INVALID_JSON", "Expected bounded JSON without duplicate keys.") from None
    return validate_request(value)


def validate_request(request: Any) -> dict[str, Any]:
    value = _json_copy(request)
    if not isinstance(value, dict):
        raise InterfaceError("INVALID_REQUEST", "Request must be a JSON object.")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 256:
        raise InterfaceError("INVALID_REQUEST", "An explicit run_id is required.")
    return value


def failure(error: InterfaceError) -> dict[str, Any]:
    return {"ok": False, "error": {"code": error.code, "message": str(error)}}


class Client:
    """All transports dispatch here; ok means invocation, never clearance.

    The wrapper never generates assessment/graph IDs, interprets cursors, reads
    server paths or collapses readiness, findings and disposition into a verdict.
    """

    def __init__(self, backend: Backend | None = None, access: Access | None = None):
        self.backend = backend
        self.access = access or Access()

    def call(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        try:
            if operation not in OPERATIONS:
                raise InterfaceError("UNKNOWN_OPERATION", "Unknown operation.")
            value = validate_request(request)
            if self.backend is None:
                raise InterfaceError("BACKEND_UNAVAILABLE", "No real backend has been configured.")
            if OPERATIONS[operation] not in self.access.permissions:
                raise InterfaceError("FORBIDDEN", "Operation is not permitted.")
            if value["run_id"] not in self.access.run_ids:
                raise InterfaceError("FORBIDDEN", "Run is not permitted.")
            raw_result = self.backend.execute(operation, value)
            try:
                result = _json_copy(raw_result)
            except InterfaceError:
                raise InterfaceError("BACKEND_ERROR", "Backend returned invalid JSON.") from None
            if not isinstance(result, dict):
                raise InterfaceError("BACKEND_ERROR", "Backend returned an invalid result.")
            return {"ok": True, "result": result}
        except InterfaceError as error:
            return failure(error)
        except Exception:
            # Never echo backend tracebacks, request contents, paths or secrets.
            return failure(InterfaceError("BACKEND_ERROR", "Backend operation failed."))
