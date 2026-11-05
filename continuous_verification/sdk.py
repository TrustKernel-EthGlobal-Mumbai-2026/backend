"""Transport boundary bound to accepted verification contract 0.2.

Backend.execute is the reviewed local B service operation seam. B validates its
DTOs and referenced-object ownership; verify additionally binds A at this boundary.
"""
from dataclasses import dataclass
import json
from typing import Any, Protocol

from .contracts import (
    ContractError, digest, validate_request as validate_verify_request,
    validate_result as validate_verify_result,
)


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


_SAFE_SERVICE_ERRORS = {
    "INVALID_REQUEST": "Service request is invalid.",
    "FORBIDDEN": "Service operation or object is not permitted.",
    "NOT_FOUND": "Requested service object was not found.",
    "CONFLICT": "Service identity or content conflict.",
    "INVALID_CURSOR": "Event cursor is invalid for this request.",
    "UNSUPPORTED_OPERATION": "Service operation is not supported.",
    "BACKEND_UNAVAILABLE": "Service is unavailable.",
}


class ServiceErrorAdapter:
    """Map B's typed service errors using a trusted host-supplied exception class.

    A trusted host supplies the exact service exception class, never model JSON.
    Public messages are fixed here; raw messages/issues are not serialized. This
    adapter does not create a service, configure coverage or replace B validation.
    """

    def __init__(self, backend: Backend, error_type: type[Exception]):
        if not isinstance(error_type, type) or not issubclass(error_type, Exception):
            raise TypeError("Expected a trusted service exception class.")
        self.backend, self.error_type = backend, error_type

    def execute(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.backend.execute(operation, request)
        except self.error_type as error:
            code = getattr(error, "code", None)
            if type(code) is str and code in _SAFE_SERVICE_ERRORS:
                raise InterfaceError(code, _SAFE_SERVICE_ERRORS[code]) from None
            raise InterfaceError("BACKEND_ERROR", "Backend operation failed.") from None


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

    @classmethod
    def from_service(cls, backend, *, access: Access | None = None):
        """Wrap an already configured reviewed B instance; never open a model path.

        The trusted host retains backend ownership/close responsibility. Default
        preliminary grants mirror its principal; B always authorizes independently.
        """
        from .service import ServiceBackend, ServiceError
        if not isinstance(backend, ServiceBackend):
            raise TypeError("Expected a configured ServiceBackend instance.")
        grants = access if access is not None else Access(
            backend.principal.permissions, backend.principal.run_ids)
        return cls(ServiceErrorAdapter(backend, ServiceError), grants)

    def call(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        try:
            if operation not in OPERATIONS:
                raise InterfaceError("UNKNOWN_OPERATION", "Unknown operation.")
            value = validate_request(request)
            if operation == "verify":
                try:
                    validate_verify_request(value)
                except ContractError:
                    raise InterfaceError("INVALID_REQUEST", "Verification request violates contract 0.2.") from None
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
            if operation == "verify":
                try:
                    validate_verify_result(result)
                except ContractError:
                    raise InterfaceError("BACKEND_ERROR", "Verification result violates contract 0.2.") from None
                if result["run_id"] != value["run_id"] or result["request_id"] != value["request_id"]:
                    raise InterfaceError("BACKEND_ERROR", "Verification result scope mismatch.")
                binding = result["binding"]
                if binding is not None and any(binding[key] != expected for key, expected in (
                    ("request_digest", digest(value)),
                    ("proposal_digest", digest(value["proposal"])),
                    ("checkpoint_digest", value["checkpoint"]["digest"]),
                    ("policy_digest", value["policy"]["digest"]),
                )):
                    raise InterfaceError("BACKEND_ERROR", "Verification result binding mismatch.")
            return {"ok": True, "result": result}
        except InterfaceError as error:
            return failure(error)
        except Exception:
            # Never echo backend tracebacks, request contents, paths or secrets.
            return failure(InterfaceError("BACKEND_ERROR", "Backend operation failed."))
