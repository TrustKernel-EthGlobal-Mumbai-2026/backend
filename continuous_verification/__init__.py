"""Offline continuous-verification candidate API; no persistence or transports."""
from .contracts import (
    CONTRACT_VERSION, ContractError, canonical_json, digest, text_digest,
    validate_event, validate_checkpoint, validate_request, validate_policy,
    validate_result, assessment_binding, binding_matches,
)
from .verifier import verify

__all__ = [
    "CONTRACT_VERSION", "ContractError", "canonical_json", "digest", "text_digest",
    "validate_event", "validate_checkpoint", "validate_request", "validate_policy",
    "validate_result", "assessment_binding", "binding_matches", "verify",
]
