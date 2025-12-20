"""Deterministic explanation contract and integrity enforcement.

Explanations are bounded, template-driven summaries over authoritative facts.
They avoid narrative drift by binding to request fingerprints, provenance,
policy decisions, and execution results with explicit digests.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Mapping, MutableMapping, Sequence, TypedDict


class ExplanationContractViolation(RuntimeError):
    """Raised when an explanation payload violates the contract."""


class ExplanationIntegrityError(RuntimeError):
    """Raised when integrity checks fail for an explanation artifact."""


class RequestFingerprint(TypedDict):
    """Canonical request fingerprint captured at admission."""

    id: str
    fingerprint: str


class AuthorityProvenance(TypedDict):
    """Authority provenance accompanying the request."""

    authority: str
    scope: str
    issued_at: str


class PolicyDecision(TypedDict):
    """Explicit policy evaluation outcome."""

    policy_id: str
    decision: str
    outcome: str


class ExecutionResult(TypedDict):
    """Execution results bound to the request."""

    action: str
    status: str
    result_reference: str


class ExplanationStatement(TypedDict):
    """A single deterministic explanation line derived from facts."""

    template: str
    text: str


class ExplanationArtifact(TypedDict):
    """Structured explanation artifact with provenance references."""

    schema_version: str
    request: RequestFingerprint
    provenance: AuthorityProvenance
    policy_decisions: Sequence[PolicyDecision]
    execution_results: Sequence[ExecutionResult]
    statements: Sequence[ExplanationStatement]
    referenced_hashes: Mapping[str, str]
    digest: str


@dataclass(frozen=True)
class ExplanationInputs:
    """Authoritative inputs used to build an explanation."""

    request: RequestFingerprint
    provenance: AuthorityProvenance
    policy_decisions: Sequence[PolicyDecision]
    execution_results: Sequence[ExecutionResult]


_SCHEMA_VERSION = "1.0"
_ALLOWED_DECISIONS = {"allowed", "denied", "skipped"}
_ALLOWED_STATUSES = {"succeeded", "failed"}


def _canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_payload(data: object) -> str:
    return hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()


def _validate_inputs(inputs: ExplanationInputs) -> None:
    for decision in inputs.policy_decisions:
        if decision["decision"] not in _ALLOWED_DECISIONS:
            raise ExplanationContractViolation(
                f"Unsupported policy decision value: {decision['decision']}"
            )
    for result in inputs.execution_results:
        if result["status"] not in _ALLOWED_STATUSES:
            raise ExplanationContractViolation(
                f"Unsupported execution status value: {result['status']}"
            )


def _compose_statements(inputs: ExplanationInputs) -> List[ExplanationStatement]:
    statements: List[ExplanationStatement] = [
        {
            "template": "request",
            "text": f"Request {inputs.request['id']} fingerprint {inputs.request['fingerprint']}",
        },
        {
            "template": "provenance",
            "text": (
                "Authorized by "
                f"{inputs.provenance['authority']} under scope {inputs.provenance['scope']} "
                f"(issued {inputs.provenance['issued_at']})"
            ),
        },
    ]
    for decision in inputs.policy_decisions:
        statements.append(
            {
                "template": "policy_decision",
                "text": f"Policy {decision['policy_id']} → {decision['decision']} ({decision['outcome']})",
            }
        )
    for result in inputs.execution_results:
        statements.append(
            {
                "template": "execution_result",
                "text": f"Action {result['action']} → {result['status']} (result {result['result_reference']})",
            }
        )
    return statements


def build_explanation_artifact(inputs: ExplanationInputs) -> ExplanationArtifact:
    """Build a deterministic explanation artifact from authoritative facts.

    The artifact references all inputs by hash and includes a digest over the
    entire payload to enable replay validation and tamper detection.
    """

    _validate_inputs(inputs)
    statements = _compose_statements(inputs)
    referenced_hashes: Dict[str, str] = {
        "request": _hash_payload(inputs.request),
        "provenance": _hash_payload(inputs.provenance),
        "policy_decisions": _hash_payload(inputs.policy_decisions),
        "execution_results": _hash_payload(inputs.execution_results),
    }
    payload: MutableMapping[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "request": inputs.request,
        "provenance": inputs.provenance,
        "policy_decisions": list(inputs.policy_decisions),
        "execution_results": list(inputs.execution_results),
        "statements": statements,
        "referenced_hashes": referenced_hashes,
    }
    digest = _hash_payload(payload)
    payload["digest"] = digest
    return payload  # type: ignore[return-value]


def validate_explanation_artifact(
    artifact: ExplanationArtifact, inputs: ExplanationInputs
) -> None:
    """Validate an explanation artifact against authoritative inputs.

    Raises ``ExplanationIntegrityError`` on any mismatch or replay divergence.
    """

    expected = build_explanation_artifact(inputs)
    if artifact.get("schema_version") != _SCHEMA_VERSION:
        raise ExplanationContractViolation("Unsupported schema version")
    if artifact.get("statements") != expected["statements"]:
        raise ExplanationContractViolation("Explanation statements drifted from contract templates")
    if artifact.get("referenced_hashes") != expected["referenced_hashes"]:
        raise ExplanationIntegrityError("Referenced fact hashes differ from authoritative inputs")
    if artifact.get("digest") != expected["digest"]:
        raise ExplanationIntegrityError("Explanation digest mismatch; replay diverged")


def build_explanation_with_fallback(
    inputs: ExplanationInputs,
) -> Mapping[str, object]:
    """Build an explanation and degrade safely to raw facts on failure."""

    try:
        return {"explanation": build_explanation_artifact(inputs), "facts": None}
    except Exception as exc:  # noqa: BLE001
        return {
            "explanation": None,
            "facts": {
                "request": inputs.request,
                "provenance": inputs.provenance,
                "policy_decisions": list(inputs.policy_decisions),
                "execution_results": list(inputs.execution_results),
                "error": str(exc),
            },
        }
