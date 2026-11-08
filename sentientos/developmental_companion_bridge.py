"""Request-scoped bridge from consented companion evidence to resident cognition.

This adapter does not own memory or write developmental history. It converts one
already-consented local observation into a transient World-State snapshot and
delegates the decision to the existing ResidentDevelopmentalCognitionOwner.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Mapping, Sequence

from .embodiment_self_observation import EmbodimentEvidenceOwner, EmbodimentObservation
from .local_model_authority import digest_payload
from .resident_developmental_cognition import (
    ResidentCompanionInteractionResult,
    ResidentDevelopmentalCognitionOwner,
)
from .world_state_board import WorldStateBoardBuilder, WorldStateSnapshot


class DevelopmentalCompanionBridgeError(ValueError):
    """Invalid request evidence or adapter composition."""


def _screen_record(observation: Mapping[str, Any]) -> dict[str, Any]:
    text = observation.get("text")
    captured_at = observation.get("captured_at")
    capture_digest = observation.get("capture_digest")
    if (observation.get("modality") != "screen"
            or observation.get("raw_frame_retained") is not False
            or observation.get("capture_scope")
                != "allowlisted_foreground_game_client_area"
            or not isinstance(text, str) or not text.strip() or len(text) > 1200
            or not isinstance(captured_at, str) or len(captured_at) > 64
            or not isinstance(capture_digest, str) or len(capture_digest) != 64
            or any(char not in "0123456789abcdef" for char in capture_digest)):
        raise DevelopmentalCompanionBridgeError("consented_screen_observation_invalid")
    try:
        event_time = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DevelopmentalCompanionBridgeError(
            "consented_screen_observation_time_invalid") from exc
    if event_time.tzinfo is None or event_time.utcoffset() is None:
        raise DevelopmentalCompanionBridgeError(
            "consented_screen_observation_time_invalid")
    text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "source_kind": "embodiment",
        "source_id": f"consented-screen:{capture_digest}",
        "schema_version": "sentientos.consented_screen_ocr_observation:v1",
        "subject_id": f"game-screen:{capture_digest[:24]}",
        "subject_kind": "allowlisted_foreground_game_screen",
        "stage": "observation",
        "disposition": "captured",
        "evidence_strength": "bounded_local_capture_unverified_issuer",
        "observed_at": captured_at,
        "staleness": "unknown",
        "effect_claimed": False,
        "effect_proven": False,
        "payload": {
            "ocr_text": text,
            "text_digest": text_digest,
            "capture_digest": capture_digest,
            "capture_scope": "allowlisted_foreground_game_client_area",
            "raw_frame_retained": False,
            "capture_time_posture": "caller_asserted_local_capture_time",
        },
    }


def build_companion_snapshot(*, screen_observation: Mapping[str, Any] | None = None,
        proprioception: Sequence[EmbodimentObservation] = (),
        clock: Any | None = None) -> WorldStateSnapshot:
    """Build one bounded snapshot; source provenance remains explicitly qualified."""
    records: list[Mapping[str, Any]] = []
    if screen_observation is not None:
        if not isinstance(screen_observation, Mapping):
            raise DevelopmentalCompanionBridgeError("consented_screen_observation_invalid")
        records.append(_screen_record(screen_observation))
    if proprioception:
        try:
            records.extend(EmbodimentEvidenceOwner(proprioception).world_state_records())
        except (TypeError, ValueError) as exc:
            raise DevelopmentalCompanionBridgeError(
                "proprioception_evidence_invalid") from exc
    return WorldStateBoardBuilder(clock=clock).build(records)


class ResidentDevelopmentalCompanionBridge:
    """Route one user turn through the existing resident cognition owner."""

    def __init__(self, owner: ResidentDevelopmentalCognitionOwner, *,
                 proprioception_provider: Any | None = None,
                 clock: Any | None = None) -> None:
        if not isinstance(owner, ResidentDevelopmentalCognitionOwner):
            raise TypeError("resident_developmental_cognition_owner_required")
        if (proprioception_provider is not None
                and not callable(proprioception_provider)):
            raise TypeError("proprioception_provider_must_be_callable")
        self._owner = owner
        self._proprioception_provider = proprioception_provider
        self._clock = clock

    def verify_committed_response(self, *, linkage: Mapping[str, Any],
            response_text: str, request_id: str) -> bool:
        """Verify transcript delivery against the durable owner observation and receipt."""
        try:
            observation_id = linkage.get("cognition_observation_id")
            observation_digest = linkage.get("cognition_observation_digest")
            observation = self._owner.verified_cognition_observation(
                str(observation_id), str(observation_digest))
            expected_tick = "companion-interaction-" + hashlib.sha256(
                request_id.encode("utf-8")).hexdigest()[:32]
            text_digest = digest_payload({"text": response_text})
            return (
                linkage.get("response_origin") == "resident_developmental_cognition"
                and observation.get("condition_id") == "companion-interaction"
                and observation.get("tick_id") == expected_tick
                and observation.get("correlation_id") ==
                    f"{expected_tick}:resident_developmental_cognition:companion-interaction"
                and linkage.get("cognition_snapshot_id") ==
                    observation.get("current_snapshot_id")
                and linkage.get("cognition_snapshot_digest") ==
                    observation.get("current_snapshot_digest")
                and linkage.get("inference_receipt_id") ==
                    observation.get("inference_receipt_id")
                and linkage.get("inference_receipt_digest") ==
                    observation.get("inference_receipt_digest")
                and linkage.get("invocation_output_digest") ==
                    observation.get("output_digest")
                and linkage.get("response_digest") == text_digest
                and linkage.get("assistant_output_lineage") == {
                    "status": "resident_cognition_interaction",
                    "cognition_observation_id": observation_id,
                    "cognition_observation_digest": observation_digest,
                    "inference_receipt_id": observation.get("inference_receipt_id"),
                    "inference_receipt_digest": observation.get("inference_receipt_digest"),
                    "invocation_output_digest": observation.get("output_digest"),
                    "response_digest": text_digest,
                }
                and linkage.get("cognition_evidence_ids") ==
                    list(linkage.get("cognition_evidence_ids", ()))
                and set(linkage.get("cognition_evidence_ids", ())) <=
                    set(observation.get("current_fact_ids", ()))
                and linkage.get("cognition_prior_record_ids") ==
                    list(observation.get("retrieved_record_ids", ()))
                and linkage.get("cognition_model_id") == observation.get("model_id")
                and linkage.get("cognition_model_artifact_digest") ==
                    observation.get("model_artifact_digest")
            )
        except Exception:
            return False

    def respond(self, *, request_id: str, question: str,
                screen_observation: Mapping[str, Any] | None = None
                ) -> ResidentCompanionInteractionResult:
        proprioception: Sequence[EmbodimentObservation] = ()
        if self._proprioception_provider is not None:
            value = self._proprioception_provider()
            if not isinstance(value, (tuple, list)) or any(
                    not isinstance(item, EmbodimentObservation) for item in value):
                raise DevelopmentalCompanionBridgeError(
                    "proprioception_provider_output_invalid")
            proprioception = tuple(value)
        snapshot = build_companion_snapshot(
            screen_observation=screen_observation,
            proprioception=proprioception, clock=self._clock)
        return self._owner.run_companion_interaction(
            snapshot=snapshot, request_id=request_id, question=question)
