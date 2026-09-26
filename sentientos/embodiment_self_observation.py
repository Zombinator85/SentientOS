"""Bounded, non-authoritative embodiment evidence projected into World-State."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

EVIDENCE_SCHEMA = "sentientos.embodiment_self_observation:v1"
MANIFEST_SCHEMA = "sentientos.avatar_body_manifest:v1"
POSTURES = frozenset({"production", "rehearsal", "synthetic_test"})
CLASSES = frozenset({"body_manifest", "sensor_observation", "actuator_observation",
                     "avatar_commanded_state", "avatar_renderer_reported_state",
                     "avatar_independently_observed_state", "fulfillment_observation"})
FORBIDDEN = frozenset({"authority", "permission", "policy", "goal", "consciousness", "sentience"})
FALSE_AUTHORITY = {"decision_authority": False, "admission_authority": False,
                   "execution_authority": False, "adoption_authority": False,
                   "policy_authority": False, "goal_authority": False}


class EmbodimentEvidenceError(ValueError):
    """Fail-closed evidence contract violation."""


def semantic_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                                  ensure_ascii=False).encode()).hexdigest()


def _bounded(value: Any) -> Any:
    result: Any
    if isinstance(value, (str, bool, int, float)) or value is None:
        result = value
    elif isinstance(value, (list, tuple)):
        if len(value) > 128:
            raise EmbodimentEvidenceError("evidence_inventory_too_large")
        result = [_bounded(item) for item in value]
    elif isinstance(value, dict) and all(isinstance(key, str) for key in value):
        if set(value) & FORBIDDEN:
            raise EmbodimentEvidenceError("authority_or_identity_claim_forbidden")
        result = {key: _bounded(value[key]) for key in sorted(value)}
    else:
        raise EmbodimentEvidenceError("evidence_not_bounded_json")
    if len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()) > 32768:
        raise EmbodimentEvidenceError("evidence_too_large")
    return result


@dataclass(frozen=True)
class AvatarBodyManifest:
    installation_body_id: str
    avatar_asset_id: str
    source_artifact_digest: str
    asset_format: str
    rig_id: str
    rig_semantic_digest: str
    renderer_interface_id: str
    coordinate_convention: str
    bones: tuple[str, ...]
    expressions: tuple[str, ...]
    motion_channels: tuple[str, ...]
    viseme_channels: tuple[str, ...]
    sensor_bindings: tuple[str, ...]
    output_bindings: tuple[str, ...]
    body_generation: int
    predecessor_manifest_digest: str | None
    authoring_provenance: str | None
    schema_version: str = MANIFEST_SCHEMA

    def validate(self) -> None:
        data = asdict(self)
        if self.schema_version != MANIFEST_SCHEMA or self.body_generation < 1:
            raise EmbodimentEvidenceError("body_manifest_invalid")
        if any(not isinstance(data[name], str) or not data[name] for name in
               ("installation_body_id", "avatar_asset_id", "source_artifact_digest", "asset_format",
                "rig_id", "rig_semantic_digest", "renderer_interface_id", "coordinate_convention")):
            raise EmbodimentEvidenceError("body_manifest_identity_missing")
        inventories = (self.bones, self.expressions, self.motion_channels, self.viseme_channels,
                       self.sensor_bindings, self.output_bindings)
        if any(len(items) > 128 or len(items) != len(set(items)) or any(not item for item in items)
               for items in inventories):
            raise EmbodimentEvidenceError("body_manifest_inventory_invalid")
        _bounded(data)

    @property
    def semantic_digest(self) -> str:
        self.validate()
        return semantic_digest(asdict(self))


@dataclass(frozen=True)
class EmbodimentObservation:
    source_id: str
    source_schema: str
    source_digest: str
    observed_at: str
    provenance_class: str
    freshness: str
    posture: str
    evidence_class: str
    subject_id: str
    subject_kind: str
    payload: Mapping[str, Any]
    effect_claimed: bool = False
    effect_proven: bool = False
    schema_version: str = EVIDENCE_SCHEMA

    def validate(self) -> None:
        if (self.schema_version != EVIDENCE_SCHEMA or self.evidence_class not in CLASSES
                or self.posture not in POSTURES or not all((self.source_id, self.source_schema,
                                                            self.source_digest, self.observed_at,
                                                            self.provenance_class, self.freshness,
                                                            self.subject_id, self.subject_kind))):
            raise EmbodimentEvidenceError("embodiment_evidence_invalid")
        if self.effect_proven and self.evidence_class != "fulfillment_observation":
            raise EmbodimentEvidenceError("effect_proof_requires_fulfillment_evidence")
        if self.posture == "synthetic_test" and self.provenance_class == "production":
            raise EmbodimentEvidenceError("synthetic_evidence_cannot_claim_production")
        payload = _bounded(dict(self.payload))
        if self.evidence_class == "sensor_observation" and payload.get("healthy") is True and payload.get("present") is not True:
            raise EmbodimentEvidenceError("sensor_health_requires_presence")
        if self.evidence_class == "body_manifest":
            AvatarBodyManifest(**payload).validate()


class EmbodimentEvidenceOwner:
    """Explicitly injected evidence owner; performs no discovery or effects."""

    def __init__(self, observations: Sequence[EmbodimentObservation]) -> None:
        self._observations = tuple(observations)
        for observation in self._observations:
            observation.validate()

    def world_state_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen: dict[str, str] = {}
        for item in self._observations:
            item.validate()
            if item.source_id in seen and seen[item.source_id] != item.source_digest:
                raise EmbodimentEvidenceError("source_identity_digest_changed")
            seen[item.source_id] = item.source_digest
            is_fulfillment = item.evidence_class == "fulfillment_observation"
            records.append({
                "source_kind": "fulfillment" if is_fulfillment else "embodiment",
                "source_id": item.source_id, "schema_version": item.source_schema,
                "subject_id": item.subject_id,
                "subject_kind": item.subject_kind,
                "stage": "execution" if is_fulfillment else "observation",
                "disposition": "recorded", "evidence_strength": item.provenance_class,
                "staleness": item.freshness, "observed_at": item.observed_at,
                "effect_claimed": item.effect_claimed, "effect_proven": item.effect_proven,
                "payload": {"embodiment_evidence_class": item.evidence_class,
                            "evidence_posture": item.posture,
                            "source_semantic_digest": item.source_digest, **dict(item.payload)},
            })
        return records


def score_structured_assessment(*, expected: Mapping[str, Any], answers: Mapping[str, Any],
                                supported_sources: Sequence[str]) -> dict[str, Any]:
    """Externally score structured answers; model prose is not an oracle."""
    keys = sorted(expected)
    correct = sum(key in answers and answers[key] == expected[key] for key in keys)
    incorrect = sum(key in answers and answers[key] != expected[key] for key in keys)
    abstentions = sum(key not in answers or answers[key] is None for key in keys)
    unsupported = sorted(set(answers) - set(keys))
    claimed_sources = answers.get("source_ids", [])
    provenance_ok = isinstance(claimed_sources, list) and set(claimed_sources) <= set(supported_sources)
    return {"question_count": len(keys), "supported_correct": correct,
            "supported_incorrect": incorrect, "unsupported_assertions": len(unsupported),
            "abstentions": abstentions, "source_provenance_correct": provenance_ok,
            "score": correct - incorrect - len(unsupported), "authority": dict(FALSE_AUTHORITY)}
