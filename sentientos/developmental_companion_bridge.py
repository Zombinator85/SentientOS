"""Request-scoped bridge from consented companion evidence to resident cognition.

Ordinary companion turns use this adapter to convert consented local evidence
into a transient World-State snapshot and never write developmental history.
An explicit operator feedback operation may delegate one scoped writeback to
the same existing ResidentDevelopmentalCognitionOwner; this adapter owns no
memory store or parallel developmental controller.
"""
from __future__ import annotations

import hashlib
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from .embodiment_self_observation import EmbodimentEvidenceOwner, EmbodimentObservation
from .local_model_authority import digest_payload
from .longitudinal_self_model import LongitudinalSelfModelRuntimeConfig
from .persistent_epistemic_state import PersistentEpistemicStateOwner
from .resident_developmental_cognition import (
    ResidentDevelopmentalCycleResult,
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


MAX_OPERATOR_FEEDBACK_CAPTURE_AGE = timedelta(seconds=60)
MAX_OPERATOR_FEEDBACK_FUTURE_SKEW = timedelta(seconds=5)


def _screen_record(observation: Mapping[str, Any], *,
        staleness: str = "unknown") -> dict[str, Any]:
    if staleness not in {"fresh", "aging", "stale", "expired", "unknown"}:
        raise DevelopmentalCompanionBridgeError("screen_observation_staleness_invalid")
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
        "staleness": staleness,
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
        additional_records: Sequence[Mapping[str, Any]] = (),
        screen_staleness: str = "unknown",
        clock: Any | None = None) -> WorldStateSnapshot:
    """Build one bounded snapshot; source provenance remains explicitly qualified."""
    records: list[Mapping[str, Any]] = []
    if screen_observation is not None:
        if not isinstance(screen_observation, Mapping):
            raise DevelopmentalCompanionBridgeError("consented_screen_observation_invalid")
        records.append(_screen_record(screen_observation, staleness=screen_staleness))
    if proprioception:
        try:
            records.extend(EmbodimentEvidenceOwner(proprioception).world_state_records())
        except (TypeError, ValueError) as exc:
            raise DevelopmentalCompanionBridgeError(
                "proprioception_evidence_invalid") from exc
    if not isinstance(additional_records, (tuple, list)) or any(
            not isinstance(record, Mapping) for record in additional_records):
        raise DevelopmentalCompanionBridgeError("additional_world_state_records_invalid")
    records.extend(additional_records)
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
            if self._self_model_owner is None:
                raise DevelopmentalCompanionBridgeError(
                    "enabled_self_model_projection_owner_required")
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

    def operator_feedback_sources_allowed(self) -> bool:
        return {"operator_feedback", "embodiment"}.issubset(
            set(self._owner.config.allowed_source_kinds))

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

    def record_operator_feedback(self, *, tick_id: str, request_id: str,
            response_text: str, linkage: Mapping[str, Any], feedback: str,
            screen_observation: Mapping[str, Any]) -> ResidentDevelopmentalCycleResult:
        """Commit one explicit outcome report through existing cognition owners.

        This operation is opt-in and separate from ``respond``. It verifies
        that the reviewed assistant response was committed through this bridge,
        combines the operator's bounded outcome report with a fresh consented
        screen capture and available proprioception, then delegates the entire
        interpretation/admission/writeback transaction to ``run_tick``.
        Nothing here upgrades the operator report to truth or proves an effect.
        """
        if (not isinstance(tick_id, str) or not tick_id.strip() or len(tick_id) > 256
                or not isinstance(request_id, str) or not request_id.strip()
                or len(request_id) > 256
                or not isinstance(response_text, str) or not response_text.strip()
                or len(response_text) > 32_000
                or not isinstance(linkage, Mapping)
                or not isinstance(feedback, str) or not feedback.strip()
                or len(feedback) > 1200
                or not isinstance(screen_observation, Mapping)):
            raise DevelopmentalCompanionBridgeError(
                "operator_feedback_request_invalid")
        if not self.can_handle():
            raise CognitionWorkloadUnavailable()
        if not self.operator_feedback_sources_allowed():
            raise DevelopmentalCompanionBridgeError(
                "operator_feedback_sources_not_allowlisted")
        if not self.verify_committed_response(linkage=linkage,
                response_text=response_text, request_id=request_id):
            raise DevelopmentalCompanionBridgeError(
                "operator_feedback_prior_response_unverified")

        proprioception: Sequence[EmbodimentObservation] = ()
        if self._proprioception_provider is not None:
            value = self._proprioception_provider()
            if not isinstance(value, (tuple, list)) or any(
                    not isinstance(item, EmbodimentObservation) for item in value):
                raise DevelopmentalCompanionBridgeError(
                    "proprioception_provider_output_invalid")
            proprioception = tuple(value)

        screen_record = _screen_record(screen_observation)
        now = self._clock() if callable(self._clock) else datetime.now(timezone.utc)
        if isinstance(now, str):
            try:
                now = datetime.fromisoformat(now.replace("Z", "+00:00"))
            except ValueError as exc:
                raise DevelopmentalCompanionBridgeError(
                    "operator_feedback_clock_invalid") from exc
        captured_at = datetime.fromisoformat(
            str(screen_observation["captured_at"]).replace("Z", "+00:00"))
        if (not isinstance(now, datetime) or now.tzinfo is None
                or now.utcoffset() is None or captured_at.tzinfo is None
                or captured_at.utcoffset() is None):
            raise DevelopmentalCompanionBridgeError(
                "operator_feedback_capture_time_invalid")
        capture_age = now.astimezone(timezone.utc) - captured_at.astimezone(timezone.utc)
        if (capture_age < -MAX_OPERATOR_FEEDBACK_FUTURE_SKEW
                or capture_age > MAX_OPERATOR_FEEDBACK_CAPTURE_AGE):
            raise DevelopmentalCompanionBridgeError(
                "operator_feedback_capture_not_fresh")
        feedback_digest = hashlib.sha256(feedback.encode("utf-8")).hexdigest()
        source_id = "operator-feedback:" + hashlib.sha256(
            f"{tick_id}\0{request_id}".encode("utf-8")).hexdigest()[:32]
        capture_age_seconds = max(0.0, capture_age.total_seconds())
        feedback_record = {
            "source_kind": "operator_feedback",
            "source_id": source_id,
            "schema_version": "sentientos.operator_feedback_on_companion_interaction:v1",
            "subject_id": str(linkage["cognition_observation_id"]),
            "subject_kind": "companion_interaction_outcome",
            "stage": "observation",
            "disposition": "operator_reported",
            "evidence_strength": "operator_supplied_unverified_report",
            "observed_at": screen_observation.get("captured_at"),
            "staleness": "fresh",
            "effect_claimed": False,
            "effect_proven": False,
            "payload": {
                "prior_response_origin": "resident_developmental_cognition",
                "prior_request_id_digest": hashlib.sha256(
                    request_id.encode("utf-8")).hexdigest(),
                "prior_response_digest": linkage.get("response_digest"),
                "prior_cognition_observation_id": linkage.get(
                    "cognition_observation_id"),
                "prior_cognition_observation_digest": linkage.get(
                    "cognition_observation_digest"),
                "screen_capture_digest": screen_record["payload"]["capture_digest"],
                "screen_text_digest": screen_record["payload"]["text_digest"],
                "capture_age_seconds_at_writeback": capture_age_seconds,
                "freshness_window_seconds": MAX_OPERATOR_FEEDBACK_CAPTURE_AGE.total_seconds(),
                "operator_feedback": feedback,
                "operator_feedback_digest": feedback_digest,
                "operator_feedback_provenance": "operator_supplied_unverified_report",
                "current_truth": False,
                "authority": False,
            },
        }
        tick_time, projection_tick = self._projection_boundary()
        prior_self_model, prior_epistemic_state = self._prior_cognitive_context(
            tick_id=tick_time, projection_tick=projection_tick)
        snapshot = build_companion_snapshot(
            screen_observation=screen_observation,
            proprioception=proprioception,
            additional_records=(feedback_record,),
            screen_staleness="fresh",
            clock=self._clock,
        )
        gate = (self._cognition_inference_gate()
            if self._cognition_inference_gate is not None else nullcontext())
        with gate:
            return self._owner.run_tick(snapshot=snapshot, tick_id=tick_id,
                prior_self_model=prior_self_model,
                prior_epistemic_state=prior_epistemic_state)
