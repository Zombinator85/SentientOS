"""Request-scoped bridge from consented companion evidence to resident cognition.

This adapter does not own memory or write developmental history. It converts one
already-consented local observation into a transient World-State snapshot and
delegates the decision to the existing ResidentDevelopmentalCognitionOwner.
"""
from __future__ import annotations

import hashlib
from contextlib import nullcontext
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .embodiment_self_observation import EmbodimentEvidenceOwner, EmbodimentObservation
from .local_model_authority import digest_payload
from .longitudinal_self_model import LongitudinalSelfModelRuntimeConfig
from .persistent_epistemic_state import PersistentEpistemicStateOwner
from .resident_developmental_cognition import (
    ResidentCompanionInteractionResult,
    ResidentDevelopmentalCognitionOwner,
)
from .world_state_board import WorldStateBoardBuilder, WorldStateSnapshot


class DevelopmentalCompanionBridgeError(ValueError):
    """Invalid request evidence or adapter composition."""


class CognitionWorkloadUnavailable(RuntimeError):
    """The active latency-sensitive workload does not admit cognition inference."""

    code = "cognition_unavailable_during_gaming"


class CognitionEvidenceUnavailable(RuntimeError):
    """No current external or proprioceptive evidence is available for grounding."""

    code = "cognition_current_evidence_unavailable"


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
                 self_model_owner: Any | None = None,
                 self_model_config: LongitudinalSelfModelRuntimeConfig | None = None,
                 epistemic_state_owner: PersistentEpistemicStateOwner | None = None,
                 epistemic_state_config: Mapping[str, Any] | None = None,
                 cognition_inference_gate: Any | None = None,
                 cognition_available: Any | None = None,
                 clock: Any | None = None) -> None:
        if not isinstance(owner, ResidentDevelopmentalCognitionOwner):
            raise TypeError("resident_developmental_cognition_owner_required")
        if (proprioception_provider is not None
                and not callable(proprioception_provider)):
            raise TypeError("proprioception_provider_must_be_callable")
        if cognition_inference_gate is not None and not callable(cognition_inference_gate):
            raise TypeError("cognition_inference_gate_invalid")
        if cognition_available is not None and not callable(cognition_available):
            raise TypeError("cognition_availability_provider_invalid")
        if (self_model_owner is not None
                and not callable(getattr(self_model_owner, "cognitive_projection", None))):
            raise TypeError("self_model_projection_owner_invalid")
        if (self_model_config is not None and self_model_config.enabled
                and self_model_config.cognitive_consumption_enabled
                and self_model_owner is None):
            raise ValueError("enabled_self_model_projection_owner_required")
        epistemic_config = dict(epistemic_state_config or {})
        if epistemic_state_owner is not None and not epistemic_config:
            raise ValueError("epistemic_state_projection_config_required")
        if (epistemic_config.get("cognitive_consumption_enabled") is True
                and epistemic_state_owner is None):
            raise ValueError("enabled_epistemic_projection_owner_required")
        self._owner = owner
        self._proprioception_provider = proprioception_provider
        self._self_model_owner = self_model_owner
        self._self_model_config = self_model_config
        self._epistemic_state_owner = epistemic_state_owner
        self._epistemic_state_config = epistemic_config
        self._cognition_inference_gate = cognition_inference_gate
        self._cognition_available = cognition_available
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
            history_record_ids = linkage.get("cognition_history_record_ids", [])
            retrieved_record_ids = observation.get("retrieved_record_ids", ())
            history_lineage_valid = (
                isinstance(history_record_ids, list)
                and all(isinstance(item, str) for item in history_record_ids)
                and len(set(history_record_ids)) == len(history_record_ids)
                and isinstance(retrieved_record_ids, (list, tuple))
                and all(isinstance(item, str) for item in retrieved_record_ids)
                and set(history_record_ids).issubset(retrieved_record_ids))
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
                and observation.get("schema_version") ==
                    "sentientos.resident_cognition_observation:v8"
                and observation.get("companion_history_citation_ids") == list(history_record_ids)
                and history_lineage_valid
                and linkage.get("cognition_model_id") == observation.get("model_id")
                and linkage.get("cognition_model_artifact_digest") ==
                    observation.get("model_artifact_digest")
                and linkage.get("self_model_projection_id") ==
                    observation.get("self_model_projection_id")
                and linkage.get("self_model_projection_digest") ==
                    observation.get("self_model_projection_digest")
                and linkage.get("epistemic_projection_id") ==
                    observation.get("epistemic_projection_id")
                and linkage.get("epistemic_projection_digest") ==
                    observation.get("epistemic_projection_digest")
            )
        except Exception:
            return False

    def _projection_boundary(self) -> tuple[str, int]:
        now = self._clock() if callable(self._clock) else datetime.now(timezone.utc)
        if isinstance(now, str):
            try:
                now = datetime.fromisoformat(now.replace("Z", "+00:00"))
            except ValueError as exc:
                raise DevelopmentalCompanionBridgeError(
                    "cognitive_projection_time_invalid") from exc
        if (not isinstance(now, datetime) or now.tzinfo is None
                or now.utcoffset() is None):
            raise DevelopmentalCompanionBridgeError(
                "cognitive_projection_time_invalid")
        tick_id = now.isoformat()
        if tick_id.endswith("-00:00"):
            raise DevelopmentalCompanionBridgeError(
                "cognitive_projection_time_offset_unknown")
        try:
            projection_tick = int(now.timestamp())
        except (OSError, OverflowError, ValueError) as exc:
            raise DevelopmentalCompanionBridgeError(
                "cognitive_projection_time_unrepresentable") from exc
        return tick_id, projection_tick

    def _prior_cognitive_context(self, *, tick_id: str,
            projection_tick: int) -> tuple[Any | None, Any | None]:
        prior_self_model = None
        config = self._self_model_config
        if (config is not None and config.enabled
                and config.cognitive_consumption_enabled):
            prior_self_model = self._self_model_owner.cognitive_projection(
                before_tick=tick_id, max_claims=config.max_projection_claims,
                allowed_predicates=config.allowed_predicates)
        prior_epistemic_state = None
        if (self._epistemic_state_owner is not None
                and self._epistemic_state_config.get(
                    "cognitive_consumption_enabled") is True):
            maximum = self._epistemic_state_config.get(
                "max_cognitive_projection_count")
            if (not isinstance(maximum, int) or isinstance(maximum, bool)
                    or not 1 <= maximum <= 128):
                raise DevelopmentalCompanionBridgeError(
                    "epistemic_projection_bound_invalid")
            prior_epistemic_state = self._epistemic_state_owner.cognitive_projection(
                max_states=maximum, current_tick=projection_tick)
        return prior_self_model, prior_epistemic_state

    def can_handle(self) -> bool:
        if self._cognition_available is None:
            return True
        try:
            return self._cognition_available() is True
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
        tick_id, projection_tick = self._projection_boundary()
        prior_self_model, prior_epistemic_state = self._prior_cognitive_context(
            tick_id=tick_id, projection_tick=projection_tick)
        snapshot = build_companion_snapshot(
            screen_observation=screen_observation,
            proprioception=proprioception, clock=self._clock)
        if not snapshot.facts:
            raise CognitionEvidenceUnavailable()
        gate = (self._cognition_inference_gate()
            if self._cognition_inference_gate is not None else nullcontext())
        with gate:
            return self._owner.run_companion_interaction(
                snapshot=snapshot, request_id=request_id, question=question,
                prior_self_model=prior_self_model,
                prior_epistemic_state=prior_epistemic_state)
