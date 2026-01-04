"""Semantic attestation and compatibility evaluation for federation handshakes."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple


def _stable_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_semantic_layer_hash(
    ontology_hash: str,
    policy_hash: str,
    invariant_catalog_hash: str,
    failure_taxonomy_hash: str,
) -> str:
    payload = {
        "failure_taxonomy_hash": failure_taxonomy_hash,
        "invariant_catalog_hash": invariant_catalog_hash,
        "ontology_hash": ontology_hash,
        "policy_hash": policy_hash,
    }
    digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
    return digest


def _normalize_capabilities(
    declared_capabilities: Optional[Iterable[str]],
) -> Optional[Tuple[str, ...]]:
    if declared_capabilities is None:
        return None
    capabilities = tuple(sorted(str(cap) for cap in declared_capabilities))
    return capabilities


@dataclass(frozen=True)
class SemanticAttestation:
    node_id: str
    ontology_hash: str
    policy_hash: str
    invariant_catalog_hash: str
    failure_taxonomy_hash: str
    declared_capabilities: Optional[Tuple[str, ...]] = None
    semantic_layer_hash: str = field(init=False)

    def __post_init__(self) -> None:
        normalized = _normalize_capabilities(self.declared_capabilities)
        object.__setattr__(self, "declared_capabilities", normalized)
        semantic_hash = compute_semantic_layer_hash(
            self.ontology_hash,
            self.policy_hash,
            self.invariant_catalog_hash,
            self.failure_taxonomy_hash,
        )
        object.__setattr__(self, "semantic_layer_hash", semantic_hash)

    def to_dict(self) -> MutableMapping[str, object]:
        return {
            "node_id": self.node_id,
            "ontology_hash": self.ontology_hash,
            "policy_hash": self.policy_hash,
            "invariant_catalog_hash": self.invariant_catalog_hash,
            "failure_taxonomy_hash": self.failure_taxonomy_hash,
            "semantic_layer_hash": self.semantic_layer_hash,
            "declared_capabilities": list(self.declared_capabilities)
            if self.declared_capabilities is not None
            else None,
        }

    def serialize(self) -> str:
        return _stable_json(self.to_dict())


class CompatibilityResult(str, Enum):
    COMPATIBLE = "compatible"
    COMPATIBLE_WITH_DIVERGENCE = "compatible_with_divergence"
    PARALLEL = "parallel"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class CompatibilityExplanation:
    matched_hashes: Mapping[str, str]
    diverged_hashes: Mapping[str, Mapping[str, str]]
    semantic_divergence: bool
    peripheral_divergence: bool


def evaluate_compatibility(
    local: SemanticAttestation,
    remote: SemanticAttestation,
) -> Tuple[CompatibilityResult, CompatibilityExplanation]:
    matched: dict[str, str] = {}
    diverged: dict[str, dict[str, str]] = {}
    for field_name in (
        "ontology_hash",
        "policy_hash",
        "invariant_catalog_hash",
        "failure_taxonomy_hash",
    ):
        local_value = getattr(local, field_name)
        remote_value = getattr(remote, field_name)
        if local_value == remote_value:
            matched[field_name] = local_value
        else:
            diverged[field_name] = {"local": local_value, "remote": remote_value}

    semantic_divergence = "ontology_hash" in diverged
    peripheral_divergence = any(
        key in diverged
        for key in ("policy_hash", "invariant_catalog_hash", "failure_taxonomy_hash")
    )

    if not diverged:
        result = CompatibilityResult.COMPATIBLE
    elif semantic_divergence:
        result = CompatibilityResult.PARALLEL
    elif len(diverged) == 1:
        result = CompatibilityResult.COMPATIBLE_WITH_DIVERGENCE
    else:
        result = CompatibilityResult.INCOMPATIBLE

    explanation = CompatibilityExplanation(
        matched_hashes=matched,
        diverged_hashes=diverged,
        semantic_divergence=semantic_divergence,
        peripheral_divergence=peripheral_divergence,
    )
    return result, explanation


class HandshakeDecision(str, Enum):
    ACCEPT = "accept"
    DEFER = "defer"
    IGNORE = "ignore"


@dataclass(frozen=True)
class HandshakeRecord:
    remote_node_id: str
    attestation: SemanticAttestation
    compatibility: CompatibilityResult
    decision: HandshakeDecision

    def to_dict(self) -> MutableMapping[str, object]:
        return {
            "remote_node_id": self.remote_node_id,
            "attestation": self.attestation.to_dict(),
            "compatibility": self.compatibility.value,
            "decision": self.decision.value,
        }
