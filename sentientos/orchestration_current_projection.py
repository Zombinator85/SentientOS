from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

_CURRENT_ORCHESTRATION_EXPORT_PACKET_CONSUMER_RECEIPT_CLASSIFICATIONS = {
    "receipt_structurally_consumable",
    "receipt_consumable_with_caution",
    "receipt_fragmented",
    "receipt_contradicted",
    "receipt_minimal",
    "no_current_receipt_needed",
}

_CURRENT_ORCHESTRATION_HANDOFF_ACCEPTANCE_POSTURE_CLASSIFICATIONS = {
    "handoff_acceptance_clear",
    "handoff_acceptance_cautionary",
    "handoff_acceptance_fragmented",
    "handoff_acceptance_contradicted",
    "handoff_acceptance_minimal",
    "no_current_handoff_acceptance_posture",
}


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _current_orchestration_export_packet_consumer_receipt_id(
    *,
    current_orchestration_state_id: str,
    current_orchestration_export_packet_id: str,
    receipt_classification: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "current_orchestration_state_id": current_orchestration_state_id,
                "current_orchestration_export_packet_id": current_orchestration_export_packet_id,
                "receipt_classification": receipt_classification,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return f"ocr-{digest.hexdigest()[:16]}"


def _current_orchestration_handoff_acceptance_posture_id(
    *,
    current_orchestration_state_id: str,
    current_orchestration_export_packet_id: str,
    current_orchestration_export_packet_consumer_receipt_id: str,
    handoff_acceptance_classification: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "current_orchestration_state_id": current_orchestration_state_id,
                "current_orchestration_export_packet_id": current_orchestration_export_packet_id,
                "current_orchestration_export_packet_consumer_receipt_id": (
                    current_orchestration_export_packet_consumer_receipt_id
                ),
                "handoff_acceptance_classification": handoff_acceptance_classification,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return f"ohp-{digest.hexdigest()[:16]}"


def resolve_current_orchestration_export_packet_consumer_receipt(
    repo_root: Path,
    *,
    anti_sovereignty_payload_builder: Callable[..., dict[str, Any]],
    current_orchestration_export_packet: Mapping[str, Any] | None = None,
    current_orchestration_digest: Mapping[str, Any] | None = None,
    current_orchestration_coherence_brief: Mapping[str, Any] | None = None,
    current_orchestration_transition_brief: Mapping[str, Any] | None = None,
    current_orchestration_closure_brief: Mapping[str, Any] | None = None,
    current_orchestration_next_move_brief: Mapping[str, Any] | None = None,
    current_orchestration_handoff_packet_brief: Mapping[str, Any] | None = None,
    current_operator_facing_orchestration_brief: Mapping[str, Any] | None = None,
    current_orchestration_resolution_path_brief: Mapping[str, Any] | None = None,
    current_orchestration_pressure_signal: Mapping[str, Any] | None = None,
    current_resumed_operation_readiness: Mapping[str, Any] | None = None,
    current_orchestration_wake_readiness_detector: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one bounded, observational-only receipt describing current export-packet consumability."""

    _ = repo_root.resolve()
    export_packet_map = (
        current_orchestration_export_packet
        if isinstance(current_orchestration_export_packet, Mapping)
        else {}
    )
    digest_map = current_orchestration_digest if isinstance(current_orchestration_digest, Mapping) else {}
    coherence_map = (
        current_orchestration_coherence_brief if isinstance(current_orchestration_coherence_brief, Mapping) else {}
    )
    transition_map = (
        current_orchestration_transition_brief if isinstance(current_orchestration_transition_brief, Mapping) else {}
    )
    closure_map = (
        current_orchestration_closure_brief if isinstance(current_orchestration_closure_brief, Mapping) else {}
    )
    next_move_map = (
        current_orchestration_next_move_brief if isinstance(current_orchestration_next_move_brief, Mapping) else {}
    )
    handoff_map = (
        current_orchestration_handoff_packet_brief
        if isinstance(current_orchestration_handoff_packet_brief, Mapping)
        else {}
    )
    operator_map = (
        current_operator_facing_orchestration_brief
        if isinstance(current_operator_facing_orchestration_brief, Mapping)
        else {}
    )
    path_map = (
        current_orchestration_resolution_path_brief
        if isinstance(current_orchestration_resolution_path_brief, Mapping)
        else {}
    )
    pressure_map = (
        current_orchestration_pressure_signal if isinstance(current_orchestration_pressure_signal, Mapping) else {}
    )
    resumed_map = (
        current_resumed_operation_readiness if isinstance(current_resumed_operation_readiness, Mapping) else {}
    )
    wake_map = (
        current_orchestration_wake_readiness_detector
        if isinstance(current_orchestration_wake_readiness_detector, Mapping)
        else {}
    )

    export_packet_id = str(export_packet_map.get("current_orchestration_export_packet_id") or "")
    export_packet_classification = str(export_packet_map.get("export_packet_classification") or "export_packet_minimal")
    export_packet_maturity = str(export_packet_map.get("export_packet_maturity_posture") or "minimal")
    export_packet_suitable = bool(export_packet_map.get("suitable_for_bounded_downstream_inspection"))
    state_id = str((((export_packet_map.get("basis") or {}).get("basis_evidence") or {}).get("current_orchestration_state_id") or ""))
    if not state_id:
        state_id = str(((export_packet_map.get("basis") or {}).get("basis_evidence") or {}).get("current_supervisory_state_id") or "")

    digest_classification = str(digest_map.get("digest_classification") or "minimal_current_picture")
    coherence_classification = str(coherence_map.get("coherence_classification") or "insufficient_current_signal")
    transition_classification = str(transition_map.get("transition_classification") or "transition_uncertain")
    closure_classification = str(closure_map.get("closure_classification") or "no_current_closure_posture")
    next_move_classification = str(next_move_map.get("next_move_classification") or "no_current_next_move")
    handoff_classification = str(handoff_map.get("handoff_packet_brief_classification") or "no_current_packet_brief")
    operator_loop_posture = str(operator_map.get("loop_posture") or "informational")
    path_classification = str(path_map.get("resolution_path_classification") or "no_current_resolution_path")
    pressure_classification = str(pressure_map.get("pressure_classification") or "insufficient_signal")
    resumed_verdict = str(resumed_map.get("resumed_operation_readiness_verdict") or "not_ready")
    wake_classification = str(wake_map.get("wake_readiness_classification") or "not_wake_ready")

    contradiction_present = (
        export_packet_classification == "export_packet_contradicted"
        or digest_classification == "contradictory_current_picture"
        or coherence_classification == "materially_contradictory"
        or transition_classification == "transition_contradicted"
    )
    fragmentation_present = (
        export_packet_classification == "export_packet_fragmented"
        or pressure_classification == "fragmentation_pressure"
        or handoff_classification == "packet_continuity_uncertain"
        or path_classification == "fragmented_path"
        or closure_classification == "closure_blocked_by_fragmentation"
    )
    caution_present = (
        export_packet_classification == "export_packet_cautionary"
        or export_packet_maturity == "cautionary"
        or operator_loop_posture == "cautionary"
        or resumed_verdict in {"hold_for_operator_review", "not_ready"}
        or wake_classification in {"wake_ready_with_caution", "wake_blocked_pending_operator"}
        or next_move_classification
        in {"hold_for_operator_review_next", "rerun_packetization_gate_next", "rerun_packet_synthesis_next"}
    )

    non_default_neighboring_evidence = sum(
        1
        for value, default in (
            (digest_classification, "minimal_current_picture"),
            (coherence_classification, "insufficient_current_signal"),
            (transition_classification, "transition_uncertain"),
            (closure_classification, "no_current_closure_posture"),
            (next_move_classification, "no_current_next_move"),
            (handoff_classification, "no_current_packet_brief"),
            (path_classification, "no_current_resolution_path"),
            (pressure_classification, "insufficient_signal"),
            (wake_classification, "not_wake_ready"),
            (resumed_verdict, "not_ready"),
        )
        if value != default
    )
    linkage_present = bool(export_packet_id and isinstance(export_packet_map.get("basis"), Mapping))
    linkage_sufficient = linkage_present and non_default_neighboring_evidence >= 2
    no_receipt_needed = export_packet_classification == "export_packet_minimal" and non_default_neighboring_evidence <= 1

    if contradiction_present:
        receipt_classification = "receipt_contradicted"
        picture_posture = "contradictory"
        rationale = "current_export_packet_and_neighboring_surfaces_materially_disagree"
    elif fragmentation_present:
        receipt_classification = "receipt_fragmented"
        picture_posture = "fragmented"
        rationale = "current_export_picture_is_materially_fragmented_for_bounded_consumer_receipt"
    elif no_receipt_needed:
        receipt_classification = "no_current_receipt_needed"
        picture_posture = "minimal"
        rationale = "current_export_picture_is_sparse_enough_that_additional_receipt_is_not_meaningfully_needed"
    elif export_packet_classification == "export_packet_minimal":
        receipt_classification = "receipt_minimal"
        picture_posture = "minimal"
        rationale = "current_export_picture_is_sparse_but_still_boundedly_interpretable"
    elif export_packet_classification == "export_packet_ready" and not caution_present and linkage_sufficient:
        receipt_classification = "receipt_structurally_consumable"
        picture_posture = "mature"
        rationale = "current_export_packet_is_mature_linked_and_coherent_for_bounded_observational_consumption"
    else:
        receipt_classification = "receipt_consumable_with_caution"
        picture_posture = "cautionary"
        rationale = "current_export_packet_is_observationally_consumable_but_material_caution_signals_remain"

    if receipt_classification not in _CURRENT_ORCHESTRATION_EXPORT_PACKET_CONSUMER_RECEIPT_CLASSIFICATIONS:
        receipt_classification = "receipt_minimal"

    consumable_observational_packet = receipt_classification in {
        "receipt_structurally_consumable",
        "receipt_consumable_with_caution",
        "receipt_minimal",
    }
    export_receipt_id = _current_orchestration_export_packet_consumer_receipt_id(
        current_orchestration_state_id=state_id,
        current_orchestration_export_packet_id=export_packet_id,
        receipt_classification=receipt_classification,
    )
    return {
        "schema_version": "current_orchestration_export_packet_consumer_receipt.v1",
        "resolved_at": _iso_utc_now(),
        "current_orchestration_export_packet_consumer_receipt_id": export_receipt_id,
        "receipt_classification": receipt_classification,
        "consumable_as_bounded_observational_packet": consumable_observational_packet,
        "received_picture_posture": picture_posture,
        "linkage_to_underlying_current_surfaces_present": linkage_present,
        "linkage_to_underlying_current_surfaces_sufficient": linkage_sufficient,
        "observational_only_receipt": True,
        "source_current_orchestration_export_packet_ref": {
            "current_orchestration_export_packet_id": export_packet_id or None,
            "export_packet_classification": export_packet_classification,
            "export_packet_maturity_posture": export_packet_maturity,
            "surface": "sentientos.orchestration_intent_fabric.resolve_current_orchestration_export_packet",
        },
        "basis": {
            "compact_rationale": rationale,
            "basis_evidence": {
                "export_packet_classification": export_packet_classification,
                "export_packet_maturity_posture": export_packet_maturity,
                "export_packet_suitable_for_bounded_downstream_inspection": export_packet_suitable,
                "current_digest_classification": digest_classification,
                "current_coherence_classification": coherence_classification,
                "current_transition_classification": transition_classification,
                "current_closure_classification": closure_classification,
                "current_next_move_classification": next_move_classification,
                "current_handoff_packet_brief_classification": handoff_classification,
                "current_operator_loop_posture": operator_loop_posture,
                "current_resolution_path_classification": path_classification,
                "current_pressure_classification": pressure_classification,
                "current_resumed_operation_readiness_verdict": resumed_verdict,
                "current_wake_readiness_classification": wake_classification,
                "neighboring_evidence_count": non_default_neighboring_evidence,
            },
            "compressed_surface_linkage": {
                "current_orchestration_export_packet_surface": "resolve_current_orchestration_export_packet",
                "current_orchestration_digest_surface": "resolve_current_orchestration_digest",
                "current_orchestration_coherence_brief_surface": "resolve_current_orchestration_coherence_brief",
                "current_orchestration_transition_brief_surface": "resolve_current_orchestration_transition_brief",
                "current_orchestration_closure_brief_surface": "resolve_current_orchestration_closure_brief",
                "current_orchestration_next_move_brief_surface": "resolve_current_orchestration_next_move_brief",
                "current_orchestration_handoff_packet_brief_surface": "resolve_current_orchestration_handoff_packet_brief",
                "current_operator_facing_orchestration_brief_surface": "resolve_current_operator_facing_orchestration_brief",
                "current_orchestration_resolution_path_brief_surface": "resolve_current_orchestration_resolution_path_brief",
                "current_orchestration_pressure_signal_surface": "resolve_current_orchestration_pressure_signal",
                "current_resumed_operation_readiness_surface": "resolve_current_resumed_operation_readiness_verdict",
                "current_orchestration_wake_readiness_detector_surface": "resolve_current_orchestration_wake_readiness_detector",
            },
            "historical_honesty": {
                "no_new_truth_source": True,
                "derived_from_existing_surfaces_only": True,
                "does_not_overstate_downstream_consumability": True,
            },
        },
        "boundaries": {
            "non_sovereign": True,
            "non_authoritative": True,
            "non_executing": True,
            "diagnostic_only": True,
            "receipt_only": True,
            "decision_power": "none",
            "does_not_plan_or_schedule": True,
            "does_not_execute_or_route_work": True,
            "does_not_create_new_truth_source": True,
            "does_not_create_new_orchestration_layer": True,
            "does_not_imply_permission_to_execute": True,
        },
        **anti_sovereignty_payload_builder(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "current_orchestration_export_packet_consumer_receipt_only": True,
                "non_executing": True,
                "does_not_execute_or_route_work": True,
                "does_not_create_new_authority_surface": True,
            },
        ),
    }


def resolve_current_orchestration_handoff_acceptance_posture(
    repo_root: Path,
    *,
    anti_sovereignty_payload_builder: Callable[..., dict[str, Any]],
    current_orchestration_export_packet: Mapping[str, Any] | None = None,
    current_orchestration_export_packet_consumer_receipt: Mapping[str, Any] | None = None,
    current_orchestration_digest: Mapping[str, Any] | None = None,
    current_orchestration_coherence_brief: Mapping[str, Any] | None = None,
    current_orchestration_transition_brief: Mapping[str, Any] | None = None,
    current_orchestration_closure_brief: Mapping[str, Any] | None = None,
    current_orchestration_next_move_brief: Mapping[str, Any] | None = None,
    current_orchestration_handoff_packet_brief: Mapping[str, Any] | None = None,
    current_operator_facing_orchestration_brief: Mapping[str, Any] | None = None,
    current_orchestration_resolution_path_brief: Mapping[str, Any] | None = None,
    current_orchestration_pressure_signal: Mapping[str, Any] | None = None,
    current_resumed_operation_readiness: Mapping[str, Any] | None = None,
    current_orchestration_wake_readiness_detector: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one bounded, observational-only current handoff acceptance posture."""

    _ = repo_root.resolve()
    export_packet_map = (
        current_orchestration_export_packet if isinstance(current_orchestration_export_packet, Mapping) else {}
    )
    receipt_map = (
        current_orchestration_export_packet_consumer_receipt
        if isinstance(current_orchestration_export_packet_consumer_receipt, Mapping)
        else {}
    )
    digest_map = current_orchestration_digest if isinstance(current_orchestration_digest, Mapping) else {}
    coherence_map = (
        current_orchestration_coherence_brief if isinstance(current_orchestration_coherence_brief, Mapping) else {}
    )
    transition_map = (
        current_orchestration_transition_brief if isinstance(current_orchestration_transition_brief, Mapping) else {}
    )
    closure_map = (
        current_orchestration_closure_brief if isinstance(current_orchestration_closure_brief, Mapping) else {}
    )
    next_move_map = (
        current_orchestration_next_move_brief if isinstance(current_orchestration_next_move_brief, Mapping) else {}
    )
    handoff_map = (
        current_orchestration_handoff_packet_brief
        if isinstance(current_orchestration_handoff_packet_brief, Mapping)
        else {}
    )
    operator_map = (
        current_operator_facing_orchestration_brief
        if isinstance(current_operator_facing_orchestration_brief, Mapping)
        else {}
    )
    path_map = (
        current_orchestration_resolution_path_brief
        if isinstance(current_orchestration_resolution_path_brief, Mapping)
        else {}
    )
    pressure_map = (
        current_orchestration_pressure_signal if isinstance(current_orchestration_pressure_signal, Mapping) else {}
    )
    resumed_map = (
        current_resumed_operation_readiness if isinstance(current_resumed_operation_readiness, Mapping) else {}
    )
    wake_map = (
        current_orchestration_wake_readiness_detector
        if isinstance(current_orchestration_wake_readiness_detector, Mapping)
        else {}
    )

    export_packet_id = str(export_packet_map.get("current_orchestration_export_packet_id") or "")
    export_packet_classification = str(export_packet_map.get("export_packet_classification") or "export_packet_minimal")
    export_packet_maturity = str(export_packet_map.get("export_packet_maturity_posture") or "minimal")
    receipt_id = str(receipt_map.get("current_orchestration_export_packet_consumer_receipt_id") or "")
    receipt_classification = str(receipt_map.get("receipt_classification") or "no_current_receipt_needed")
    receipt_consumable = bool(receipt_map.get("consumable_as_bounded_observational_packet"))
    receipt_linkage_present = bool(receipt_map.get("linkage_to_underlying_current_surfaces_present"))
    receipt_linkage_sufficient = bool(receipt_map.get("linkage_to_underlying_current_surfaces_sufficient"))

    digest_classification = str(digest_map.get("digest_classification") or "minimal_current_picture")
    coherence_classification = str(coherence_map.get("coherence_classification") or "insufficient_current_signal")
    transition_classification = str(transition_map.get("transition_classification") or "transition_uncertain")
    closure_classification = str(closure_map.get("closure_classification") or "no_current_closure_posture")
    next_move_classification = str(next_move_map.get("next_move_classification") or "no_current_next_move")
    handoff_classification = str(handoff_map.get("handoff_packet_brief_classification") or "no_current_packet_brief")
    operator_loop_posture = str(operator_map.get("loop_posture") or "informational")
    path_classification = str(path_map.get("resolution_path_classification") or "no_current_resolution_path")
    pressure_classification = str(pressure_map.get("pressure_classification") or "insufficient_signal")
    resumed_verdict = str(resumed_map.get("resumed_operation_readiness_verdict") or "not_ready")
    wake_classification = str(wake_map.get("wake_readiness_classification") or "not_wake_ready")

    state_id = str(
        ((((export_packet_map.get("basis") or {}).get("basis_evidence") or {}).get("current_orchestration_state_id")) or "")
    )
    if not state_id:
        state_id = str(
            ((((receipt_map.get("basis") or {}).get("basis_evidence") or {}).get("current_orchestration_state_id")) or "")
        )

    contradictory = (
        export_packet_classification == "export_packet_contradicted"
        or receipt_classification == "receipt_contradicted"
        or digest_classification == "contradictory_current_picture"
        or coherence_classification == "materially_contradictory"
        or transition_classification == "transition_contradicted"
    )
    fragmented = (
        export_packet_classification == "export_packet_fragmented"
        or receipt_classification == "receipt_fragmented"
        or handoff_classification == "packet_continuity_uncertain"
        or path_classification == "fragmented_path"
        or pressure_classification == "fragmentation_pressure"
        or closure_classification == "closure_blocked_by_fragmentation"
    )
    cautionary = (
        export_packet_classification == "export_packet_cautionary"
        or receipt_classification == "receipt_consumable_with_caution"
        or export_packet_maturity == "cautionary"
        or operator_loop_posture == "cautionary"
        or wake_classification in {"wake_ready_with_caution", "wake_blocked_pending_operator"}
        or resumed_verdict in {"hold_for_operator_review", "not_ready"}
        or next_move_classification in {"hold_for_operator_review_next", "rerun_packetization_gate_next"}
    )
    minimal = (
        export_packet_classification == "export_packet_minimal"
        or receipt_classification in {"receipt_minimal", "no_current_receipt_needed"}
        or export_packet_maturity == "minimal"
    )
    no_current = (
        export_packet_classification == "export_packet_minimal"
        and receipt_classification == "no_current_receipt_needed"
        and digest_classification == "minimal_current_picture"
        and coherence_classification == "insufficient_current_signal"
        and transition_classification == "transition_uncertain"
        and closure_classification == "no_current_closure_posture"
        and next_move_classification == "no_current_next_move"
        and handoff_classification == "no_current_packet_brief"
        and path_classification == "no_current_resolution_path"
        and pressure_classification == "insufficient_signal"
        and wake_classification == "not_wake_ready"
        and resumed_verdict == "not_ready"
    )

    export_receipt_alignment_clean = (
        export_packet_classification == "export_packet_ready"
        and receipt_classification == "receipt_structurally_consumable"
        and receipt_consumable
        and not contradictory
        and not fragmented
        and not cautionary
    )
    linkage_present = bool(export_packet_id and receipt_id and receipt_linkage_present)
    linkage_sufficient = bool(linkage_present and receipt_linkage_sufficient)

    if contradictory:
        classification = "handoff_acceptance_contradicted"
        rationale = "current_export_packet_and_consumer_receipt_materially_disagree"
    elif fragmented:
        classification = "handoff_acceptance_fragmented"
        rationale = "current_handoff_picture_is_materially_fragmented_for_acceptance_posture"
    elif no_current:
        classification = "no_current_handoff_acceptance_posture"
        rationale = "current_surfaces_do_not_show_a_meaningful_active_handoff_acceptance_posture"
    elif export_receipt_alignment_clean and linkage_sufficient:
        classification = "handoff_acceptance_clear"
        rationale = "current_export_packet_and_receipt_align_cleanly_for_bounded_observational_acceptance"
    elif minimal:
        classification = "handoff_acceptance_minimal"
        rationale = "current_handoff_picture_is_sparse_but_still_boundedly_interpretable"
    else:
        classification = "handoff_acceptance_cautionary"
        rationale = "current_handoff_picture_is_usable_but_material_caution_signals_remain"

    if classification not in _CURRENT_ORCHESTRATION_HANDOFF_ACCEPTANCE_POSTURE_CLASSIFICATIONS:
        classification = "no_current_handoff_acceptance_posture"

    return {
        "schema_version": "current_orchestration_handoff_acceptance_posture.v1",
        "resolved_at": _iso_utc_now(),
        "current_orchestration_handoff_acceptance_posture_id": _current_orchestration_handoff_acceptance_posture_id(
            current_orchestration_state_id=state_id,
            current_orchestration_export_packet_id=export_packet_id,
            current_orchestration_export_packet_consumer_receipt_id=receipt_id,
            handoff_acceptance_classification=classification,
        ),
        "handoff_acceptance_classification": classification,
        "export_packet_and_consumer_receipt_align_cleanly": export_receipt_alignment_clean,
        "bounded_downstream_acceptance_posture_supported": classification
        in {"handoff_acceptance_clear", "handoff_acceptance_cautionary", "handoff_acceptance_minimal"},
        "linkage_to_export_packet_and_consumer_receipt_present": linkage_present,
        "linkage_to_export_packet_and_consumer_receipt_sufficient": linkage_sufficient,
        "accepted_picture_posture": classification.removeprefix("handoff_acceptance_"),
        "observational_only_posture": True,
        "source_current_orchestration_export_packet_ref": {
            "current_orchestration_export_packet_id": export_packet_id or None,
            "export_packet_classification": export_packet_classification,
            "surface": "sentientos.orchestration_intent_fabric.resolve_current_orchestration_export_packet",
        },
        "source_current_orchestration_export_packet_consumer_receipt_ref": {
            "current_orchestration_export_packet_consumer_receipt_id": receipt_id or None,
            "receipt_classification": receipt_classification,
            "surface": "sentientos.orchestration_intent_fabric.resolve_current_orchestration_export_packet_consumer_receipt",
        },
        "basis": {
            "compact_rationale": rationale,
            "basis_evidence": {
                "export_packet_classification": export_packet_classification,
                "export_packet_maturity_posture": export_packet_maturity,
                "receipt_classification": receipt_classification,
                "receipt_consumable_as_bounded_observational_packet": receipt_consumable,
                "current_digest_classification": digest_classification,
                "current_coherence_classification": coherence_classification,
                "current_transition_classification": transition_classification,
                "current_closure_classification": closure_classification,
                "current_next_move_classification": next_move_classification,
                "current_handoff_packet_brief_classification": handoff_classification,
                "current_operator_loop_posture": operator_loop_posture,
                "current_resolution_path_classification": path_classification,
                "current_pressure_classification": pressure_classification,
                "current_resumed_operation_readiness_verdict": resumed_verdict,
                "current_wake_readiness_classification": wake_classification,
            },
            "compressed_surface_linkage": {
                "current_orchestration_export_packet_surface": "resolve_current_orchestration_export_packet",
                "current_orchestration_export_packet_consumer_receipt_surface": (
                    "resolve_current_orchestration_export_packet_consumer_receipt"
                ),
                "current_orchestration_digest_surface": "resolve_current_orchestration_digest",
                "current_orchestration_coherence_brief_surface": "resolve_current_orchestration_coherence_brief",
                "current_orchestration_transition_brief_surface": "resolve_current_orchestration_transition_brief",
                "current_orchestration_closure_brief_surface": "resolve_current_orchestration_closure_brief",
                "current_orchestration_next_move_brief_surface": "resolve_current_orchestration_next_move_brief",
                "current_orchestration_handoff_packet_brief_surface": "resolve_current_orchestration_handoff_packet_brief",
                "current_operator_facing_orchestration_brief_surface": "resolve_current_operator_facing_orchestration_brief",
                "current_orchestration_resolution_path_brief_surface": "resolve_current_orchestration_resolution_path_brief",
                "current_orchestration_pressure_signal_surface": "resolve_current_orchestration_pressure_signal",
                "current_resumed_operation_readiness_surface": "resolve_current_resumed_operation_readiness_verdict",
                "current_orchestration_wake_readiness_detector_surface": "resolve_current_orchestration_wake_readiness_detector",
            },
            "historical_honesty": {
                "no_new_truth_source": True,
                "derived_from_existing_surfaces_only": True,
                "does_not_overstate_downstream_acceptance_confidence": True,
            },
        },
        "boundaries": {
            "non_sovereign": True,
            "non_authoritative": True,
            "non_executing": True,
            "diagnostic_only": True,
            "decision_power": "none",
            "does_not_plan_or_schedule": True,
            "does_not_execute_or_route_work": True,
            "does_not_create_new_truth_source": True,
            "does_not_create_new_orchestration_layer": True,
            "does_not_imply_permission_to_execute": True,
        },
        **anti_sovereignty_payload_builder(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "current_orchestration_handoff_acceptance_posture_only": True,
                "non_executing": True,
                "does_not_execute_or_route_work": True,
                "does_not_create_new_authority_surface": True,
            },
        ),
    }


_CURRENT_ORCHESTRATION_COHERENCE_CLASSIFICATIONS = {
    "coherent_current_picture",
    "strained_but_coherent",
    "fragmentation_dominant",
    "materially_contradictory",
    "insufficient_current_signal",
}

_CURRENT_ORCHESTRATION_COHERENCE_POSTURES = {
    "informational_only",
    "conservative_caution",
}

_CURRENT_ORCHESTRATION_DIGEST_CLASSIFICATIONS = {
    "mature_current_picture",
    "cautionary_current_picture",
    "fragmented_current_picture",
    "contradictory_current_picture",
    "minimal_current_picture",
}

_CURRENT_ORCHESTRATION_DIGEST_ALIGNMENT = {
    "aligned",
    "cautionary",
    "fragmented",
    "contradictory",
}

_CURRENT_ORCHESTRATION_DIGEST_RESUMED_MOTION = {
    "plausible",
    "blocked",
    "not_applicable",
}

_CURRENT_ORCHESTRATION_TRANSITION_BRIEF_CLASSIFICATIONS = {
    "poised_for_resumed_progress",
    "poised_for_packet_refresh",
    "poised_for_operator_resolution",
    "poised_for_result_closure",
    "poised_for_conservative_hold",
    "poised_for_no_material_transition",
    "transition_uncertain",
    "transition_contradicted",
}

_CURRENT_ORCHESTRATION_TRANSITION_BRIEF_RESUMED_MOTION = {
    "plausible",
    "blocked",
    "not_applicable",
}

_CURRENT_ORCHESTRATION_TRANSITION_BRIEF_POSTURES = {
    "informational_only",
    "conservative_caution",
}

def _current_orchestration_coherence_brief_id(
    *,
    current_orchestration_state_id: str,
    orchestration_watchpoint_id: str,
    watchpoint_satisfaction_id: str,
    re_evaluation_trigger_id: str,
    orchestration_resumption_candidate_id: str,
    coherence_classification: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "current_orchestration_state_id": current_orchestration_state_id,
                "orchestration_watchpoint_id": orchestration_watchpoint_id,
                "watchpoint_satisfaction_id": watchpoint_satisfaction_id,
                "re_evaluation_trigger_id": re_evaluation_trigger_id,
                "orchestration_resumption_candidate_id": orchestration_resumption_candidate_id,
                "coherence_classification": coherence_classification,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return f"ocoh-{digest.hexdigest()[:16]}"


def _current_orchestration_digest_id(
    *,
    current_orchestration_state_id: str,
    orchestration_watchpoint_id: str,
    watchpoint_satisfaction_id: str,
    re_evaluation_trigger_id: str,
    orchestration_resumption_candidate_id: str,
    digest_classification: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "current_orchestration_state_id": current_orchestration_state_id,
                "orchestration_watchpoint_id": orchestration_watchpoint_id,
                "watchpoint_satisfaction_id": watchpoint_satisfaction_id,
                "re_evaluation_trigger_id": re_evaluation_trigger_id,
                "orchestration_resumption_candidate_id": orchestration_resumption_candidate_id,
                "digest_classification": digest_classification,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return f"ocd-{digest.hexdigest()[:16]}"


def _current_orchestration_transition_brief_id(
    *,
    current_orchestration_state_id: str,
    orchestration_watchpoint_id: str,
    watchpoint_satisfaction_id: str,
    re_evaluation_trigger_id: str,
    orchestration_resumption_candidate_id: str,
    transition_classification: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "current_orchestration_state_id": current_orchestration_state_id,
                "orchestration_watchpoint_id": orchestration_watchpoint_id,
                "watchpoint_satisfaction_id": watchpoint_satisfaction_id,
                "re_evaluation_trigger_id": re_evaluation_trigger_id,
                "orchestration_resumption_candidate_id": orchestration_resumption_candidate_id,
                "transition_classification": transition_classification,
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    return f"otb-{digest.hexdigest()[:16]}"


def resolve_current_orchestration_resumption_candidate_projection(
    repo_root: Path,
    *,
    anti_sovereignty_payload_builder: Callable[..., dict[str, Any]],
    normalized_current_surface_boundaries_builder: Callable[..., dict[str, Any]],
    iso_utc_now: Callable[[], str],
    resumption_candidate_id_builder: Callable[..., str],
    resolve_current_orchestration_state: Callable[..., Mapping[str, Any]],
    resolve_current_orchestration_watchpoint: Callable[..., Mapping[str, Any]],
    resolve_watchpoint_satisfaction: Callable[..., Mapping[str, Any]],
    resolve_re_evaluation_trigger_recommendation: Callable[..., Mapping[str, Any]],
    re_evaluation_recommendations: set[str],
    re_evaluation_expected_actors: set[str],
    watchpoint_satisfaction_statuses: set[str],
    current_orchestration_state: Mapping[str, Any] | None = None,
    current_orchestration_watchpoint: Mapping[str, Any] | None = None,
    watchpoint_satisfaction: Mapping[str, Any] | None = None,
    re_evaluation_trigger_recommendation: Mapping[str, Any] | None = None,
    current_proposal: Mapping[str, Any] | None = None,
    active_packet_visibility: Mapping[str, Any] | None = None,
    operator_brief_lifecycle: Mapping[str, Any] | None = None,
    packetization_gate: Mapping[str, Any] | None = None,
    unified_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve current resumption-candidate projection from canonical current-state surfaces."""
    state_map = current_orchestration_state if isinstance(current_orchestration_state, Mapping) else {}
    if not state_map:
        state_map = resolve_current_orchestration_state(
            repo_root,
            current_proposal=current_proposal,
            active_packet_visibility=active_packet_visibility,
            operator_brief_lifecycle=operator_brief_lifecycle,
            packetization_gate=packetization_gate,
            unified_result=unified_result,
        )
    watchpoint_map = current_orchestration_watchpoint if isinstance(current_orchestration_watchpoint, Mapping) else {}
    if not watchpoint_map:
        watchpoint_map = resolve_current_orchestration_watchpoint(
            repo_root,
            current_orchestration_state=state_map,
            current_proposal=current_proposal,
            active_packet_visibility=active_packet_visibility,
            operator_brief_lifecycle=operator_brief_lifecycle,
            packetization_gate=packetization_gate,
            unified_result=unified_result,
        )
    satisfaction_map = watchpoint_satisfaction if isinstance(watchpoint_satisfaction, Mapping) else {}
    if not satisfaction_map:
        satisfaction_map = resolve_watchpoint_satisfaction(
            repo_root,
            current_orchestration_state=state_map,
            current_orchestration_watchpoint=watchpoint_map,
            operator_brief_lifecycle=operator_brief_lifecycle,
            unified_result=unified_result,
            packetization_gate=packetization_gate,
            current_proposal=current_proposal,
            active_packet_visibility=active_packet_visibility,
        )
    trigger_map = (
        re_evaluation_trigger_recommendation if isinstance(re_evaluation_trigger_recommendation, Mapping) else {}
    )
    if not trigger_map:
        trigger_map = resolve_re_evaluation_trigger_recommendation(
            repo_root,
            current_orchestration_state=state_map,
            current_orchestration_watchpoint=watchpoint_map,
            watchpoint_satisfaction=satisfaction_map,
            operator_brief_lifecycle=operator_brief_lifecycle,
            unified_result=unified_result,
            packetization_gate=packetization_gate,
            current_proposal=current_proposal,
            active_packet_visibility=active_packet_visibility,
        )
    state_id = str(state_map.get("current_orchestration_state_id") or "")
    watchpoint_id = str(watchpoint_map.get("orchestration_watchpoint_id") or "")
    satisfaction_id = str(satisfaction_map.get("watchpoint_satisfaction_id") or "")
    trigger_id = str(trigger_map.get("re_evaluation_trigger_id") or "")
    watchpoint_class = str(watchpoint_map.get("watchpoint_class") or "no_watchpoint_needed")
    satisfaction_status = str(satisfaction_map.get("satisfaction_status") or "watchpoint_pending")
    recommendation = str(trigger_map.get("recommendation") or "no_re_evaluation_needed")
    expected_actor = str(trigger_map.get("expected_actor") or "none")
    state_class = str(state_map.get("current_supervisory_state") or "no_active_orchestration_item")
    resolution_path = str(state_map.get("current_resolution_path") or "none")
    active_packet_id = str(((state_map.get("source_linkage") or {}).get("active_packet_ref") or {}).get("handoff_packet_id") or "")
    proposal_id = str(((state_map.get("source_linkage") or {}).get("current_proposal_ref") or {}).get("proposal_id") or "")
    operator_receipt_id = str(
        ((state_map.get("source_linkage") or {}).get("operator_brief_ref") or {}).get("operator_resolution_receipt_id") or ""
    )
    unified_result_id = str(
        ((state_map.get("source_linkage") or {}).get("unified_result_ref") or {}).get("orchestration_result_id") or ""
    )
    candidate_class = "no_resume_candidate"
    continuity_posture = "none"
    operator_influence_in_path = False
    rationale = "no_active_re_evaluation_recommendation_to_resume"
    if recommendation == "clear_wait_and_continue_current_packet":
        candidate_class = "resumption_candidate"
        continuity_posture = "continue_current_active_packet"
        operator_influence_in_path = watchpoint_class == "await_operator_resolution" and bool(operator_receipt_id)
        rationale = "re_evaluation_recommends_clearing_wait_and_continuing_current_packet"
    elif recommendation == "rerun_packet_synthesis":
        candidate_class = "resumption_candidate"
        continuity_posture = "refresh_packet_from_current_proposal_state"
        operator_influence_in_path = bool(operator_receipt_id) or watchpoint_class == "await_operator_resolution"
        rationale = "re_evaluation_recommends_packet_refresh_after_operator_visible_context_change"
    elif recommendation in {"rerun_delegated_judgment", "rerun_packetization_gate"}:
        candidate_class = "resumption_candidate"
        continuity_posture = "recompute_from_proposal_level_state"
        operator_influence_in_path = watchpoint_class == "await_operator_resolution" and bool(operator_receipt_id)
        rationale = "re_evaluation_recommends_bounded_recomputation_from_current_proposal_state"
    elif recommendation == "hold_for_manual_review":
        candidate_class = "manual_review_hold"
        continuity_posture = "none"
        operator_influence_in_path = True
        rationale = "stale_or_fragmented_wake_context_requires_manual_review_before_resumption"
    elif recommendation == "no_re_evaluation_needed":
        rationale = "current_watchpoint_context_does_not_require_re_entry"
    if recommendation not in re_evaluation_recommendations:
        recommendation = "hold_for_manual_review"
        expected_actor = "operator"
        candidate_class = "manual_review_hold"
        continuity_posture = "none"
        operator_influence_in_path = True
        rationale = "unrecognized_re_evaluation_recommendation_defaulted_to_manual_review"
    if expected_actor not in re_evaluation_expected_actors:
        expected_actor = "operator"
    if satisfaction_status not in watchpoint_satisfaction_statuses:
        satisfaction_status = "watchpoint_pending"
    resume_ready = recommendation in {
        "rerun_delegated_judgment",
        "rerun_packetization_gate",
        "rerun_packet_synthesis",
        "clear_wait_and_continue_current_packet",
    }
    uses_unified_result_context = watchpoint_class in {
        "await_internal_execution_result",
        "await_external_fulfillment_receipt",
    } and recommendation in {"rerun_delegated_judgment", "no_re_evaluation_needed", "hold_for_manual_review"}
    return {
        "schema_version": "current_orchestration_resumption_candidate.v1",
        "resolved_at": iso_utc_now(),
        "orchestration_resumption_candidate_id": resumption_candidate_id_builder(
            current_orchestration_state_id=state_id,
            orchestration_watchpoint_id=watchpoint_id,
            watchpoint_satisfaction_id=satisfaction_id,
            re_evaluation_trigger_id=trigger_id,
            bounded_resume_mode=recommendation,
            continuity_posture=continuity_posture,
        ),
        "resumption_candidate_class": candidate_class,
        "bounded_resume_mode": recommendation,
        "continuity_posture": continuity_posture,
        "operator_influence_in_path": operator_influence_in_path,
        "resume_ready": resume_ready,
        "source_lineage": {
            "current_orchestration_state_ref": {
                "current_orchestration_state_id": state_id or None,
                "current_state_class": state_class,
                "current_resolution_path": resolution_path,
                "current_state_surface": "sentientos.orchestration_intent_fabric.resolve_current_orchestration_state",
            },
            "current_orchestration_watchpoint_ref": {
                "orchestration_watchpoint_id": watchpoint_id or None,
                "watchpoint_class": watchpoint_class,
                "watchpoint_surface": "sentientos.orchestration_intent_fabric.resolve_current_orchestration_watchpoint",
            },
            "watchpoint_satisfaction_ref": {
                "watchpoint_satisfaction_id": satisfaction_id or None,
                "satisfaction_status": satisfaction_status,
                "watchpoint_satisfaction_surface": "sentientos.orchestration_intent_fabric.resolve_watchpoint_satisfaction",
            },
            "re_evaluation_trigger_ref": {
                "re_evaluation_trigger_id": trigger_id or None,
                "recommendation": recommendation,
                "expected_actor": expected_actor,
                "re_evaluation_surface": "sentientos.orchestration_intent_fabric.resolve_re_evaluation_trigger_recommendation",
            },
            "active_packet_ref": {
                "handoff_packet_id": active_packet_id or None,
                "active_packet_surface": "sentientos.orchestration_intent_fabric.resolve_active_handoff_packet_candidate",
            },
            "proposal_ref": {
                "proposal_id": proposal_id or None,
                "proposal_visibility_surface": "sentientos.orchestration_intent_fabric.synthesize_next_move_proposal",
            },
            "operator_resolution_ref": {
                "operator_resolution_receipt_id": operator_receipt_id or None,
                "operator_visibility_surface": "sentientos.orchestration_intent_fabric.resolve_operator_action_brief_lifecycle",
            },
            "unified_result_ref": (
                {
                    "orchestration_result_id": unified_result_id or None,
                    "unified_result_surface": "sentientos.orchestration_intent_fabric.resolve_unified_orchestration_result",
                }
                if uses_unified_result_context
                else {"not_needed_for_current_resumption_path": True}
            ),
        },
        "basis": {
            "compact_rationale": rationale,
            "derived_from_existing_surfaces_only": [
                "resolve_current_orchestration_state",
                "resolve_current_orchestration_watchpoint",
                "resolve_watchpoint_satisfaction",
                "resolve_re_evaluation_trigger_recommendation",
                "resolve_active_handoff_packet_candidate",
                "resolve_operator_action_brief_lifecycle",
                "resolve_unified_orchestration_result",
                "derive_packetization_gate",
                "synthesize_next_move_proposal",
            ],
        },
        "resumption_summary": {
            "watchpoint_class": watchpoint_class,
            "satisfaction_status": satisfaction_status,
            "re_evaluation_trigger": recommendation,
            "expected_actor": expected_actor,
            "continuity_posture": continuity_posture,
            "operator_influence_in_path": operator_influence_in_path,
            "resume_ready": resume_ready,
            "diagnostic_only": True,
            "non_authoritative": True,
            "decision_power": "none",
            "non_executing": True,
        },
        "boundaries": normalized_current_surface_boundaries_builder(does_not_schedule_or_trigger_events=True),
        **anti_sovereignty_payload_builder(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "resumption_candidate_only": True,
                "non_authoritative": True,
                "decision_power": "none",
                "non_executing": True,
                "does_not_schedule_or_trigger_events": True,
                "does_not_execute_or_route_work": True,
                "does_not_create_new_orchestration_layer": True,
            },
        ),
    }


def resolve_current_resumed_operation_readiness_verdict_projection(
    *,
    anti_sovereignty_payload_builder: Callable[..., dict[str, Any]],
    normalized_current_surface_boundaries_builder: Callable[..., dict[str, Any]],
    current_resumed_operation_readiness_id_builder: Callable[..., str],
    resumed_operation_readiness_verdicts: set[str],
    current_orchestration_state: Mapping[str, Any],
    current_orchestration_watchpoint: Mapping[str, Any],
    watchpoint_satisfaction: Mapping[str, Any],
    re_evaluation_trigger_recommendation: Mapping[str, Any],
    current_orchestration_resumption_candidate: Mapping[str, Any],
    delegated_operation_readiness: Mapping[str, Any] | None = None,
    packetization_gate: Mapping[str, Any] | None = None,
    active_packet_visibility: Mapping[str, Any] | None = None,
    current_proposal: Mapping[str, Any] | None = None,
    operator_resolution_influence: Mapping[str, Any] | None = None,
    unified_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state_map = current_orchestration_state if isinstance(current_orchestration_state, Mapping) else {}
    watchpoint_map = current_orchestration_watchpoint if isinstance(current_orchestration_watchpoint, Mapping) else {}
    satisfaction_map = watchpoint_satisfaction if isinstance(watchpoint_satisfaction, Mapping) else {}
    trigger_map = re_evaluation_trigger_recommendation if isinstance(re_evaluation_trigger_recommendation, Mapping) else {}
    candidate_map = current_orchestration_resumption_candidate if isinstance(current_orchestration_resumption_candidate, Mapping) else {}
    delegated_map = delegated_operation_readiness if isinstance(delegated_operation_readiness, Mapping) else {}
    gate_map = packetization_gate if isinstance(packetization_gate, Mapping) else {}
    active_packet_map = active_packet_visibility if isinstance(active_packet_visibility, Mapping) else {}
    proposal_map = current_proposal if isinstance(current_proposal, Mapping) else {}
    operator_influence_map = operator_resolution_influence if isinstance(operator_resolution_influence, Mapping) else {}
    unified_result_map = unified_result if isinstance(unified_result, Mapping) else {}
    watchpoint_class = str(watchpoint_map.get("watchpoint_class") or "no_watchpoint_needed")
    satisfaction_status = str(satisfaction_map.get("satisfaction_status") or "watchpoint_pending")
    trigger_recommendation = str(trigger_map.get("recommendation") or "no_re_evaluation_needed")
    state_class = str(state_map.get("current_supervisory_state") or "no_active_orchestration_item")
    candidate_class = str(candidate_map.get("resumption_candidate_class") or "no_resume_candidate")
    resume_ready = bool(candidate_map.get("resume_ready"))
    continuity_posture = str(candidate_map.get("continuity_posture") or "none")
    delegated_readiness = str(delegated_map.get("readiness_verdict") or "insufficient_history")
    packetization_outcome = str(gate_map.get("packetization_outcome") or "packetization_hold_insufficient_confidence")
    packetization_allowed = bool(gate_map.get("packetization_allowed"))
    operator_influence_state = str(operator_influence_map.get("operator_influence_state") or "no_operator_influence_yet")
    unified_result_classification = str(unified_result_map.get("result_classification") or "pending_or_unresolved")
    active_packet_present = bool(active_packet_map) or bool(((state_map.get("source_linkage") or {}).get("active_packet_ref") or {}).get("handoff_packet_id"))
    proposal_present = bool(proposal_map) or bool(((state_map.get("source_linkage") or {}).get("current_proposal_ref") or {}).get("proposal_id"))
    explicit_manual_review_hold = trigger_recommendation == "hold_for_manual_review" or candidate_class == "manual_review_hold"
    stale_or_fragmented_wake_context = satisfaction_status in {"watchpoint_fragmented", "watchpoint_stale"}
    unresolved_operator_influence = (
        watchpoint_class == "await_operator_resolution" and satisfaction_status != "watchpoint_satisfied"
    ) or operator_influence_state in {"operator_decline_preserved_hold", "operator_defer_preserved_hold"}
    continuity_confidence = (
        resume_ready
        and candidate_class == "resumption_candidate"
        and continuity_posture != "none"
        and trigger_recommendation in {"rerun_delegated_judgment", "rerun_packetization_gate", "rerun_packet_synthesis", "clear_wait_and_continue_current_packet"}
        and delegated_readiness in {"ready_for_bounded_supervised_operation", "ready_with_caution"}
        and not explicit_manual_review_hold
        and not stale_or_fragmented_wake_context
        and not unresolved_operator_influence
    )
    missing_packet_or_proposal_continuity = (
        continuity_confidence and continuity_posture == "continue_current_active_packet" and not active_packet_present
    ) or (
        continuity_confidence and continuity_posture in {"refresh_packet_from_current_proposal_state", "recompute_from_proposal_level_state"} and not proposal_present
    ) or (
        continuity_confidence and continuity_posture == "continue_current_active_packet" and not packetization_allowed and packetization_outcome.startswith("packetization_hold_")
    )
    no_meaningful_resume = candidate_class == "no_resume_candidate" or trigger_recommendation == "no_re_evaluation_needed" or watchpoint_class == "no_watchpoint_needed"
    state_id = str(state_map.get("current_orchestration_state_id") or "")
    watchpoint_id = str(watchpoint_map.get("orchestration_watchpoint_id") or "")
    satisfaction_id = str(satisfaction_map.get("watchpoint_satisfaction_id") or "")
    trigger_id = str(trigger_map.get("re_evaluation_trigger_id") or "")
    candidate_id = str(candidate_map.get("orchestration_resumption_candidate_id") or "")
    if explicit_manual_review_hold or stale_or_fragmented_wake_context or unresolved_operator_influence:
        verdict = "hold_for_operator_review"
        rationale = "wake_context_or_operator_resolution_state_requires_operator_review_before_resumed_continuation"
    elif no_meaningful_resume:
        verdict = "not_ready"
        rationale = "no_active_watchpoint_or_meaningful_resumption_candidate_is_visible"
    elif missing_packet_or_proposal_continuity:
        verdict = "not_ready"
        rationale = "resumption_candidate_continuity_dependencies_are_missing_or_held"
    elif continuity_confidence and delegated_readiness == "ready_for_bounded_supervised_operation":
        verdict = "ready_to_proceed"
        rationale = "continuity_is_intact_and_candidate_is_ready_under_existing_bounded_supervision_signals"
    elif continuity_confidence:
        verdict = "proceed_with_caution"
        rationale = "candidate_is_resume_ready_but_existing_readiness_surfaces_indicate_caution"
    else:
        verdict = "not_ready"
        rationale = "bounded_resumption_confidence_is_not_sufficiently_supported_by_current_surfaces"
    if verdict not in resumed_operation_readiness_verdicts:
        verdict = "not_ready"
        rationale = "unrecognized_resumed_operation_readiness_state_defaulted_to_not_ready"
    return {
        "schema_version": "current_resumed_operation_readiness_verdict.v1",
        "current_resumed_operation_readiness_id": current_resumed_operation_readiness_id_builder(
            current_orchestration_state_id=state_id,
            orchestration_watchpoint_id=watchpoint_id,
            watchpoint_satisfaction_id=satisfaction_id,
            re_evaluation_trigger_id=trigger_id,
            orchestration_resumption_candidate_id=candidate_id,
            resumed_operation_readiness_verdict=verdict,
        ),
        "readiness_kind": "bounded_resumed_operation_readiness",
        "resumed_operation_readiness_verdict": verdict,
        "basis": {
            "compact_rationale": rationale,
            "based_on": {
                "continuity_confidence": continuity_confidence,
                "stale_or_fragmented_wake_context": stale_or_fragmented_wake_context,
                "unresolved_operator_influence": unresolved_operator_influence,
                "missing_packet_or_proposal_continuity": missing_packet_or_proposal_continuity,
                "explicit_manual_review_hold": explicit_manual_review_hold,
            },
            "current_surface_snapshot": {
                "current_supervisory_state": state_class,
                "watchpoint_class": watchpoint_class,
                "watchpoint_satisfaction_status": satisfaction_status,
                "re_evaluation_recommendation": trigger_recommendation,
                "resumption_candidate_class": candidate_class,
                "continuity_posture": continuity_posture,
                "resume_ready": resume_ready,
                "delegated_operation_readiness_verdict": delegated_readiness,
                "packetization_outcome": packetization_outcome,
                "operator_influence_state": operator_influence_state,
                "unified_result_classification": unified_result_classification,
            },
            "derived_from_existing_surfaces_only": [
                "resolve_current_orchestration_state",
                "resolve_current_orchestration_watchpoint",
                "resolve_watchpoint_satisfaction",
                "resolve_re_evaluation_trigger_recommendation",
                "resolve_current_orchestration_resumption_candidate",
                "derive_delegated_operation_readiness_verdict",
                "derive_packetization_gate",
                "resolve_active_handoff_packet_candidate",
                "synthesize_next_move_proposal",
                "derive_operator_resolution_influence",
                "resolve_unified_orchestration_result",
            ],
        },
        "source_linkage": {
            "current_orchestration_state_ref": {"current_orchestration_state_id": state_id or None},
            "current_orchestration_watchpoint_ref": {"orchestration_watchpoint_id": watchpoint_id or None},
            "watchpoint_satisfaction_ref": {"watchpoint_satisfaction_id": satisfaction_id or None},
            "re_evaluation_trigger_ref": {"re_evaluation_trigger_id": trigger_id or None},
            "current_orchestration_resumption_candidate_ref": {"orchestration_resumption_candidate_id": candidate_id or None},
        },
        "boundaries": normalized_current_surface_boundaries_builder(does_not_schedule_or_trigger_events=True),
        **anti_sovereignty_payload_builder(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "readiness_only": True,
                "non_authoritative": True,
                "decision_power": "none",
                "non_executing": True,
                "does_not_schedule_or_trigger_events": True,
                "does_not_execute_or_route_work": True,
                "does_not_create_new_orchestration_layer": True,
                "does_not_imply_permission_to_execute": True,
                "resumption_readiness_only": True,
            },
        ),
    }


def resolve_current_orchestration_wake_readiness_detector_projection(
    *,
    anti_sovereignty_payload_builder: Callable[..., dict[str, Any]],
    current_wake_readiness_detector_id_builder: Callable[..., str],
    iso_utc_now: Callable[[], str],
    current_wake_readiness_classifications: set[str],
    current_wake_readiness_postures: set[str],
    current_orchestration_state: Mapping[str, Any] | None = None,
    current_orchestration_watchpoint: Mapping[str, Any] | None = None,
    watchpoint_satisfaction: Mapping[str, Any] | None = None,
    re_evaluation_trigger_recommendation: Mapping[str, Any] | None = None,
    current_orchestration_resumption_candidate: Mapping[str, Any] | None = None,
    current_resumed_operation_readiness: Mapping[str, Any] | None = None,
    current_orchestration_watchpoint_brief: Mapping[str, Any] | None = None,
    current_orchestration_pressure_signal: Mapping[str, Any] | None = None,
    active_packet_visibility: Mapping[str, Any] | None = None,
    current_proposal: Mapping[str, Any] | None = None,
    operator_resolution_influence: Mapping[str, Any] | None = None,
    unified_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _ = (active_packet_visibility, current_proposal, unified_result)
    state_map = current_orchestration_state if isinstance(current_orchestration_state, Mapping) else {}
    watchpoint_map = current_orchestration_watchpoint if isinstance(current_orchestration_watchpoint, Mapping) else {}
    satisfaction_map = watchpoint_satisfaction if isinstance(watchpoint_satisfaction, Mapping) else {}
    trigger_map = re_evaluation_trigger_recommendation if isinstance(re_evaluation_trigger_recommendation, Mapping) else {}
    candidate_map = current_orchestration_resumption_candidate if isinstance(current_orchestration_resumption_candidate, Mapping) else {}
    readiness_map = current_resumed_operation_readiness if isinstance(current_resumed_operation_readiness, Mapping) else {}
    watchpoint_brief_map = current_orchestration_watchpoint_brief if isinstance(current_orchestration_watchpoint_brief, Mapping) else {}
    pressure_map = current_orchestration_pressure_signal if isinstance(current_orchestration_pressure_signal, Mapping) else {}
    influence_map = operator_resolution_influence if isinstance(operator_resolution_influence, Mapping) else {}
    watchpoint_class = str(watchpoint_map.get("watchpoint_class") or "no_watchpoint_needed")
    satisfaction_status = str(satisfaction_map.get("satisfaction_status") or "watchpoint_pending")
    trigger_recommendation = str(trigger_map.get("recommendation") or "no_re_evaluation_needed")
    readiness_verdict = str(readiness_map.get("resumed_operation_readiness_verdict") or "not_ready")
    pressure_classification = str(pressure_map.get("pressure_classification") or "insufficient_signal")
    wait_kind = str(watchpoint_brief_map.get("wait_kind") or "continuity_uncertain")
    operator_influence_state = str(influence_map.get("operator_influence_state") or "no_operator_influence_yet")
    watchpoint_satisfied = satisfaction_status == "watchpoint_satisfied"
    resumption_materially_available = bool(candidate_map.get("resume_ready")) and readiness_verdict in {"ready_to_proceed", "proceed_with_caution"}
    no_active_watchpoint = watchpoint_class == "no_watchpoint_needed" or satisfaction_status == "no_active_watchpoint"
    no_meaningful_resume = str(candidate_map.get("resumption_candidate_class") or "no_resume_candidate") == "no_resume_candidate" or trigger_recommendation == "no_re_evaluation_needed"
    fragmentation_block = satisfaction_status in {"watchpoint_fragmented", "watchpoint_stale"} or pressure_classification in {"fragmentation_pressure", "mixed_pressure"}
    operator_block = (
        (watchpoint_class == "await_operator_resolution" and not watchpoint_satisfied)
        or readiness_verdict == "hold_for_operator_review"
        or trigger_recommendation == "hold_for_manual_review"
        or operator_influence_state in {"operator_decline_preserved_hold", "operator_defer_preserved_hold"}
    )
    caution_posture = readiness_verdict == "proceed_with_caution" or pressure_classification in {"hold_pressure", "redirect_pressure", "repacketization_pressure"}
    conservative_hold = bool((watchpoint_brief_map.get("watchpoint_posture") or {}).get("requires_conservative_hold"))
    if no_active_watchpoint and no_meaningful_resume:
        classification = "wake_not_applicable"
        rationale = "no_active_watchpoint_or_meaningful_resumption_is_visible_in_current_orchestration_surfaces"
        posture = "informational_only"
    elif fragmentation_block:
        classification = "wake_blocked_by_fragmentation"
        rationale = "stale_or_fragmented_watchpoint_context_blocks_honest_wake_readiness"
        posture = "strongly_blocked"
    elif operator_block:
        classification = "wake_blocked_pending_operator"
        rationale = "operator_dependency_or_manual_review_hold_blocks_current_wake_readiness"
        posture = "strongly_blocked"
    elif watchpoint_satisfied and resumption_materially_available and not conservative_hold and not caution_posture:
        classification = "wake_ready"
        rationale = "watchpoint_is_satisfied_and_resumption_surfaces_support_bounded_ready_re-entry"
        posture = "informational_only"
    elif watchpoint_satisfied and resumption_materially_available:
        classification = "wake_ready_with_caution"
        rationale = "watchpoint_is_satisfied_but_current_readiness_or_pressure_posture_requires_caution"
        posture = "informational_only"
    else:
        classification = "not_wake_ready"
        rationale = "current_watchpoint_and_resumption_surfaces_do_not_yet_support_bounded_wake_readiness"
        posture = "informational_only"
    if classification not in current_wake_readiness_classifications:
        classification = "not_wake_ready"
    if posture not in current_wake_readiness_postures:
        posture = "informational_only"
    state_id = str(state_map.get("current_orchestration_state_id") or "")
    watchpoint_id = str(watchpoint_map.get("orchestration_watchpoint_id") or "")
    satisfaction_id = str(satisfaction_map.get("watchpoint_satisfaction_id") or "")
    trigger_id = str(trigger_map.get("re_evaluation_trigger_id") or "")
    candidate_id = str(candidate_map.get("orchestration_resumption_candidate_id") or "")
    return {
        "schema_version": "current_orchestration_wake_readiness_detector.v1",
        "resolved_at": iso_utc_now(),
        "current_orchestration_wake_readiness_detector_id": current_wake_readiness_detector_id_builder(
            current_orchestration_state_id=state_id,
            orchestration_watchpoint_id=watchpoint_id,
            watchpoint_satisfaction_id=satisfaction_id,
            re_evaluation_trigger_id=trigger_id,
            orchestration_resumption_candidate_id=candidate_id,
            wake_readiness_classification=classification,
        ),
        "wake_readiness_classification": classification,
        "watchpoint_satisfaction_present": watchpoint_satisfied,
        "resumption_materially_available": resumption_materially_available,
        "result_posture": posture,
        "basis": {
            "compact_rationale": rationale,
            "wake_evidence": {
                "watchpoint_class": watchpoint_class,
                "watchpoint_satisfaction_status": satisfaction_status,
                "re_evaluation_recommendation": trigger_recommendation,
                "resumed_operation_readiness_verdict": readiness_verdict,
                "watchpoint_wait_kind": wait_kind,
                "pressure_classification": pressure_classification,
                "operator_influence_state": operator_influence_state,
                "conservative_hold": conservative_hold,
            },
            "derived_from_existing_surfaces_only": [
                "resolve_current_orchestration_state",
                "resolve_current_orchestration_watchpoint",
                "resolve_watchpoint_satisfaction",
                "resolve_re_evaluation_trigger_recommendation",
                "resolve_current_orchestration_resumption_candidate",
                "resolve_current_resumed_operation_readiness_verdict",
                "resolve_current_orchestration_watchpoint_brief",
                "resolve_current_orchestration_pressure_signal",
                "resolve_active_handoff_packet_candidate",
                "current proposal visibility",
                "operator-resolution visibility",
                "resolve_unified_orchestration_result",
            ],
        },
        "boundaries": {
            "non_sovereign": True,
            "non_authoritative": True,
            "non_executing": True,
            "diagnostic_only": True,
            "decision_power": "none",
            "informational_observability_only": posture == "informational_only",
            "strongly_blocked_interpretation": posture == "strongly_blocked",
            "does_not_plan_or_schedule": True,
            "does_not_execute_or_route_work": True,
            "does_not_create_new_truth_source": True,
            "does_not_imply_permission_to_execute": True,
        },
        **anti_sovereignty_payload_builder(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "wake_readiness_detector_only": True,
                "non_executing": True,
                "does_not_execute_or_route_work": True,
                "does_not_create_new_orchestration_layer": True,
                "does_not_create_new_authority_surface": True,
            },
        ),
    }

def resolve_current_orchestration_coherence_brief(
    repo_root: Path,
    *,
    anti_sovereignty_payload_builder: Callable[..., dict[str, Any]],
    current_orchestration_state: Mapping[str, Any] | None = None,
    current_orchestration_watchpoint: Mapping[str, Any] | None = None,
    current_orchestration_watchpoint_brief: Mapping[str, Any] | None = None,
    watchpoint_satisfaction: Mapping[str, Any] | None = None,
    re_evaluation_trigger_recommendation: Mapping[str, Any] | None = None,
    current_re_evaluation_basis_brief: Mapping[str, Any] | None = None,
    current_orchestration_resumption_candidate: Mapping[str, Any] | None = None,
    current_resumed_operation_readiness: Mapping[str, Any] | None = None,
    current_orchestration_wake_readiness_detector: Mapping[str, Any] | None = None,
    current_orchestration_pressure_signal: Mapping[str, Any] | None = None,
    proposal_packet_continuity_review: Mapping[str, Any] | None = None,
    current_orchestration_next_move_brief: Mapping[str, Any] | None = None,
    current_orchestration_handoff_packet_brief: Mapping[str, Any] | None = None,
    current_operator_facing_orchestration_brief: Mapping[str, Any] | None = None,
    current_orchestration_resolution_path_brief: Mapping[str, Any] | None = None,
    current_orchestration_closure_brief: Mapping[str, Any] | None = None,
    active_packet_visibility: Mapping[str, Any] | None = None,
    operator_resolution_influence: Mapping[str, Any] | None = None,
    unified_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one bounded, observational coherence brief for the current orchestration picture."""

    _ = repo_root.resolve()
    state_map = current_orchestration_state if isinstance(current_orchestration_state, Mapping) else {}
    watchpoint_map = current_orchestration_watchpoint if isinstance(current_orchestration_watchpoint, Mapping) else {}
    watchpoint_brief_map = (
        current_orchestration_watchpoint_brief if isinstance(current_orchestration_watchpoint_brief, Mapping) else {}
    )
    satisfaction_map = watchpoint_satisfaction if isinstance(watchpoint_satisfaction, Mapping) else {}
    trigger_map = re_evaluation_trigger_recommendation if isinstance(re_evaluation_trigger_recommendation, Mapping) else {}
    basis_map = current_re_evaluation_basis_brief if isinstance(current_re_evaluation_basis_brief, Mapping) else {}
    candidate_map = (
        current_orchestration_resumption_candidate
        if isinstance(current_orchestration_resumption_candidate, Mapping)
        else {}
    )
    readiness_map = current_resumed_operation_readiness if isinstance(current_resumed_operation_readiness, Mapping) else {}
    wake_map = (
        current_orchestration_wake_readiness_detector
        if isinstance(current_orchestration_wake_readiness_detector, Mapping)
        else {}
    )
    pressure_map = (
        current_orchestration_pressure_signal if isinstance(current_orchestration_pressure_signal, Mapping) else {}
    )
    continuity_map = (
        proposal_packet_continuity_review if isinstance(proposal_packet_continuity_review, Mapping) else {}
    )
    next_move_map = (
        current_orchestration_next_move_brief if isinstance(current_orchestration_next_move_brief, Mapping) else {}
    )
    handoff_brief_map = (
        current_orchestration_handoff_packet_brief
        if isinstance(current_orchestration_handoff_packet_brief, Mapping)
        else {}
    )
    operator_facing_map = (
        current_operator_facing_orchestration_brief
        if isinstance(current_operator_facing_orchestration_brief, Mapping)
        else {}
    )
    resolution_path_map = (
        current_orchestration_resolution_path_brief
        if isinstance(current_orchestration_resolution_path_brief, Mapping)
        else {}
    )
    closure_brief_map = (
        current_orchestration_closure_brief if isinstance(current_orchestration_closure_brief, Mapping) else {}
    )
    active_packet_map = active_packet_visibility if isinstance(active_packet_visibility, Mapping) else {}
    influence_map = operator_resolution_influence if isinstance(operator_resolution_influence, Mapping) else {}
    unified_map = unified_result if isinstance(unified_result, Mapping) else {}

    pressure_classification = str(pressure_map.get("pressure_classification") or "insufficient_signal")
    wake_classification = str(wake_map.get("wake_readiness_classification") or "not_wake_ready")
    continuity_classification = str(continuity_map.get("review_classification") or "insufficient_history")
    next_move_classification = str(next_move_map.get("next_move_classification") or "no_current_next_move")
    resolution_path_classification = str(
        resolution_path_map.get("resolution_path_classification") or "no_current_resolution_path"
    )
    closure_classification = str(closure_brief_map.get("closure_classification") or "no_current_closure_posture")
    watchpoint_class = str(watchpoint_map.get("watchpoint_class") or "no_watchpoint_needed")
    wait_kind = str(watchpoint_brief_map.get("wait_kind") or "continuity_uncertain")
    satisfaction_status = str(satisfaction_map.get("satisfaction_status") or "watchpoint_pending")
    recommendation = str(trigger_map.get("recommendation") or "no_re_evaluation_needed")
    readiness_verdict = str(readiness_map.get("resumed_operation_readiness_verdict") or "not_ready")
    basis_classification = str(basis_map.get("basis_classification") or "no_current_re_evaluation_basis")
    operator_facing_classification = str(
        operator_facing_map.get("operator_facing_classification") or "operator_attention_not_currently_needed"
    )
    operator_facing_posture = str(operator_facing_map.get("loop_posture") or "informational")
    state_class = str(state_map.get("current_supervisory_state") or "no_active_orchestration_item")
    operator_influence_state = str(influence_map.get("operator_influence_state") or "no_operator_influence_yet")
    unified_result_classification = str(unified_map.get("result_classification") or "pending_or_unresolved")
    active_packet_available = bool(active_packet_map.get("active_packet_available"))

    evidence_signals = [
        pressure_classification != "insufficient_signal",
        continuity_classification != "insufficient_history",
        wake_classification != "not_wake_ready",
        next_move_classification != "no_current_next_move",
        resolution_path_classification != "no_current_resolution_path",
        closure_classification != "no_current_closure_posture",
        watchpoint_class != "no_watchpoint_needed",
        wait_kind != "no_active_watchpoint",
        satisfaction_status != "no_active_watchpoint",
        recommendation != "no_re_evaluation_needed",
        active_packet_available,
        unified_result_classification != "pending_or_unresolved",
    ]
    sparse_signal = sum(1 for flag in evidence_signals if flag) <= 2

    fragmentation_signals = (
        pressure_classification in {"fragmentation_pressure"}
        or wake_classification == "wake_blocked_by_fragmentation"
        or continuity_classification in {"fragmented_continuity", "insufficient_history"}
        or resolution_path_classification == "fragmented_path"
        or closure_classification == "closure_blocked_by_fragmentation"
        or wait_kind == "continuity_uncertain"
        or satisfaction_status in {"watchpoint_fragmented", "watchpoint_stale"}
        or handoff_brief_map.get("handoff_packet_brief_classification") == "packet_continuity_uncertain"
    )

    contradiction_signals = (
        (
            closure_classification == "closure_already_satisfied"
            and (
                state_class
                in {
                    "waiting_for_operator_resolution",
                    "waiting_for_internal_result",
                    "waiting_for_external_fulfillment",
                }
                or watchpoint_class in {
                    "await_operator_resolution",
                    "await_internal_execution_result",
                    "await_external_fulfillment_receipt",
                }
                or next_move_classification != "no_current_next_move"
            )
        )
        or (
            wake_classification in {"wake_ready", "wake_ready_with_caution"}
            and readiness_verdict in {"hold_for_operator_review", "not_ready"}
            and next_move_classification == "continue_current_packet_next"
        )
        or (
            recommendation == "hold_for_manual_review"
            and next_move_classification in {
                "continue_current_packet_next",
                "rerun_delegated_judgment_next",
                "rerun_packetization_gate_next",
                "rerun_packet_synthesis_next",
            }
        )
        or (
            resolution_path_classification == "completed_or_no_active_path"
            and closure_classification
            in {
                "closure_pending_on_operator_resolution",
                "closure_pending_on_internal_result",
                "closure_pending_on_external_fulfillment",
                "closure_pending_on_packet_continuity",
            }
        )
    )

    aligned = (
        not fragmentation_signals
        and recommendation in {"clear_wait_and_continue_current_packet", "rerun_delegated_judgment", "no_re_evaluation_needed"}
        and next_move_classification in {"continue_current_packet_next", "rerun_delegated_judgment_next", "no_current_next_move"}
        and closure_classification in {"closure_materially_reachable", "closure_already_satisfied", "no_current_closure_posture"}
        and resolution_path_classification
        in {"proposal_centered_path", "packet_centered_path", "internal_result_path", "external_fulfillment_path", "completed_or_no_active_path", "no_current_resolution_path"}
        and wake_classification in {"wake_ready", "wake_ready_with_caution", "wake_not_applicable"}
    )

    bounded_strain = (
        pressure_classification in {"hold_pressure", "redirect_pressure", "repacketization_pressure", "mixed_pressure"}
        or operator_facing_classification
        in {"operator_should_review_hold", "operator_should_review_packet_refresh_context", "operator_should_review_redirect_or_constraint_path"}
        or operator_facing_posture == "cautionary"
        or recommendation == "hold_for_manual_review"
        or next_move_classification in {"hold_for_operator_review_next", "rerun_packetization_gate_next", "rerun_packet_synthesis_next"}
        or closure_classification
        in {
            "closure_pending_on_operator_resolution",
            "closure_pending_on_internal_result",
            "closure_pending_on_external_fulfillment",
            "closure_pending_on_packet_continuity",
        }
    )

    if sparse_signal:
        classification = "insufficient_current_signal"
        rationale = "current_surfaces_are_too_sparse_to_support_an_honest_coherence_judgment"
    elif contradiction_signals:
        classification = "materially_contradictory"
        rationale = "neighboring_current_surfaces_materially_disagree_about_path_wake_or_closure_posture"
    elif fragmentation_signals:
        classification = "fragmentation_dominant"
        rationale = "fragmentation_or_continuity_uncertainty_signals_materially_dominate_the_current_picture"
    elif bounded_strain and aligned:
        classification = "strained_but_coherent"
        rationale = "pressure_or_hold_signals_are_present_but_current_path_and_closure_surfaces_remain_aligned"
    elif aligned:
        classification = "coherent_current_picture"
        rationale = "current_continuity_pressure_wake_next_move_path_and_closure_surfaces_remain_cleanly_aligned"
    elif bounded_strain:
        classification = "strained_but_coherent"
        rationale = "strain_signals_are_present_without_material_cross_surface_contradiction_or_fragmentation_dominance"
    else:
        classification = "insufficient_current_signal"
        rationale = "current_surfaces_do_not_support_a_stronger_honest_coherence_classification"

    if classification not in _CURRENT_ORCHESTRATION_COHERENCE_CLASSIFICATIONS:
        classification = "insufficient_current_signal"

    posture = (
        "conservative_caution"
        if classification
        in {
            "strained_but_coherent",
            "fragmentation_dominant",
            "materially_contradictory",
            "insufficient_current_signal",
        }
        else "informational_only"
    )
    if posture not in _CURRENT_ORCHESTRATION_COHERENCE_POSTURES:
        posture = "conservative_caution"

    state_id = str(state_map.get("current_orchestration_state_id") or "")
    watchpoint_id = str(watchpoint_map.get("orchestration_watchpoint_id") or "")
    satisfaction_id = str(satisfaction_map.get("watchpoint_satisfaction_id") or "")
    trigger_id = str(trigger_map.get("re_evaluation_trigger_id") or "")
    candidate_id = str(candidate_map.get("orchestration_resumption_candidate_id") or "")

    return {
        "schema_version": "current_orchestration_coherence_brief.v1",
        "resolved_at": _iso_utc_now(),
        "current_orchestration_coherence_brief_id": _current_orchestration_coherence_brief_id(
            current_orchestration_state_id=state_id,
            orchestration_watchpoint_id=watchpoint_id,
            watchpoint_satisfaction_id=satisfaction_id,
            re_evaluation_trigger_id=trigger_id,
            orchestration_resumption_candidate_id=candidate_id,
            coherence_classification=classification,
        ),
        "coherence_classification": classification,
        "coherence_posture": posture,
        "informational_only": posture == "informational_only",
        "conservatively_cautionary": posture == "conservative_caution",
        "cross_surface_alignment": {
            "continuity_pressure_wake_next_move_path_closure_aligned": aligned,
            "strain_present_but_bounded": bounded_strain and not fragmentation_signals and not contradiction_signals,
            "fragmentation_materially_prevents_clean_reading": bool(fragmentation_signals),
            "neighboring_surfaces_materially_disagree": bool(contradiction_signals),
        },
        "basis": {
            "compact_rationale": rationale,
            "basis_evidence": {
                "current_supervisory_state": state_class,
                "watchpoint_class": watchpoint_class,
                "watchpoint_wait_kind": wait_kind,
                "watchpoint_satisfaction_status": satisfaction_status,
                "re_evaluation_recommendation": recommendation,
                "re_evaluation_basis_classification": basis_classification,
                "resumed_operation_readiness_verdict": readiness_verdict,
                "wake_readiness_classification": wake_classification,
                "pressure_classification": pressure_classification,
                "proposal_packet_continuity_classification": continuity_classification,
                "current_next_move_classification": next_move_classification,
                "current_handoff_packet_brief_classification": str(
                    handoff_brief_map.get("handoff_packet_brief_classification") or "no_current_packet_brief"
                ),
                "current_operator_facing_classification": operator_facing_classification,
                "current_resolution_path_classification": resolution_path_classification,
                "current_closure_classification": closure_classification,
                "active_packet_available": active_packet_available,
                "operator_influence_state": operator_influence_state,
                "unified_result_classification": unified_result_classification,
            },
            "materially_supporting_surfaces": [
                "resolve_current_orchestration_state",
                "resolve_current_orchestration_watchpoint",
                "resolve_current_orchestration_watchpoint_brief",
                "resolve_watchpoint_satisfaction",
                "resolve_re_evaluation_trigger_recommendation",
                "resolve_current_re_evaluation_basis_brief",
                "resolve_current_orchestration_resumption_candidate",
                "resolve_current_resumed_operation_readiness_verdict",
                "resolve_current_orchestration_wake_readiness_detector",
                "resolve_current_orchestration_pressure_signal",
                "derive_proposal_packet_continuity_review",
                "resolve_current_orchestration_next_move_brief",
                "resolve_current_orchestration_handoff_packet_brief",
                "resolve_current_operator_facing_orchestration_brief",
                "resolve_current_orchestration_resolution_path_brief",
                "resolve_current_orchestration_closure_brief",
                "active handoff packet visibility",
                "operator-resolution visibility",
                "unified result visibility",
            ],
            "historical_honesty": {
                "no_new_truth_source": True,
                "derived_from_existing_surfaces_only": True,
                "does_not_flatten_material_disagreement_into_fake_coherence": True,
            },
        },
        "boundaries": {
            "non_sovereign": True,
            "non_authoritative": True,
            "non_executing": True,
            "diagnostic_only": True,
            "decision_power": "none",
            "does_not_plan_or_schedule": True,
            "does_not_execute_or_route_work": True,
            "does_not_create_new_truth_source": True,
            "does_not_create_new_orchestration_layer": True,
            "does_not_imply_permission_to_execute": True,
        },
        **anti_sovereignty_payload_builder(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "current_orchestration_coherence_brief_only": True,
                "non_executing": True,
                "does_not_execute_or_route_work": True,
                "does_not_create_new_authority_surface": True,
            },
        ),
    }

def resolve_current_orchestration_digest(
    repo_root: Path,
    *,
    anti_sovereignty_payload_builder: Callable[..., dict[str, Any]],
    current_orchestration_state: Mapping[str, Any] | None = None,
    current_orchestration_watchpoint: Mapping[str, Any] | None = None,
    current_orchestration_watchpoint_brief: Mapping[str, Any] | None = None,
    watchpoint_satisfaction: Mapping[str, Any] | None = None,
    re_evaluation_trigger_recommendation: Mapping[str, Any] | None = None,
    current_re_evaluation_basis_brief: Mapping[str, Any] | None = None,
    current_orchestration_resumption_candidate: Mapping[str, Any] | None = None,
    current_resumed_operation_readiness: Mapping[str, Any] | None = None,
    current_orchestration_wake_readiness_detector: Mapping[str, Any] | None = None,
    current_orchestration_pressure_signal: Mapping[str, Any] | None = None,
    proposal_packet_continuity_review: Mapping[str, Any] | None = None,
    current_orchestration_next_move_brief: Mapping[str, Any] | None = None,
    current_orchestration_handoff_packet_brief: Mapping[str, Any] | None = None,
    current_operator_facing_orchestration_brief: Mapping[str, Any] | None = None,
    current_orchestration_resolution_path_brief: Mapping[str, Any] | None = None,
    current_orchestration_closure_brief: Mapping[str, Any] | None = None,
    current_orchestration_coherence_brief: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one bounded, observational digest for the current orchestration picture."""

    _ = repo_root.resolve()
    state_map = current_orchestration_state if isinstance(current_orchestration_state, Mapping) else {}
    watchpoint_map = current_orchestration_watchpoint if isinstance(current_orchestration_watchpoint, Mapping) else {}
    watchpoint_brief_map = (
        current_orchestration_watchpoint_brief if isinstance(current_orchestration_watchpoint_brief, Mapping) else {}
    )
    satisfaction_map = watchpoint_satisfaction if isinstance(watchpoint_satisfaction, Mapping) else {}
    trigger_map = re_evaluation_trigger_recommendation if isinstance(re_evaluation_trigger_recommendation, Mapping) else {}
    basis_map = current_re_evaluation_basis_brief if isinstance(current_re_evaluation_basis_brief, Mapping) else {}
    candidate_map = (
        current_orchestration_resumption_candidate
        if isinstance(current_orchestration_resumption_candidate, Mapping)
        else {}
    )
    readiness_map = current_resumed_operation_readiness if isinstance(current_resumed_operation_readiness, Mapping) else {}
    wake_map = (
        current_orchestration_wake_readiness_detector
        if isinstance(current_orchestration_wake_readiness_detector, Mapping)
        else {}
    )
    pressure_map = (
        current_orchestration_pressure_signal if isinstance(current_orchestration_pressure_signal, Mapping) else {}
    )
    continuity_map = (
        proposal_packet_continuity_review if isinstance(proposal_packet_continuity_review, Mapping) else {}
    )
    next_move_map = (
        current_orchestration_next_move_brief if isinstance(current_orchestration_next_move_brief, Mapping) else {}
    )
    handoff_brief_map = (
        current_orchestration_handoff_packet_brief
        if isinstance(current_orchestration_handoff_packet_brief, Mapping)
        else {}
    )
    operator_map = (
        current_operator_facing_orchestration_brief
        if isinstance(current_operator_facing_orchestration_brief, Mapping)
        else {}
    )
    path_map = (
        current_orchestration_resolution_path_brief
        if isinstance(current_orchestration_resolution_path_brief, Mapping)
        else {}
    )
    closure_map = (
        current_orchestration_closure_brief if isinstance(current_orchestration_closure_brief, Mapping) else {}
    )
    coherence_map = (
        current_orchestration_coherence_brief if isinstance(current_orchestration_coherence_brief, Mapping) else {}
    )

    state_class = str(state_map.get("current_supervisory_state") or "no_active_orchestration_item")
    watchpoint_class = str(watchpoint_map.get("watchpoint_class") or "no_watchpoint_needed")
    wait_kind = str(watchpoint_brief_map.get("wait_kind") or "no_active_watchpoint")
    satisfaction_status = str(satisfaction_map.get("satisfaction_status") or "no_active_watchpoint")
    recommendation = str(trigger_map.get("recommendation") or "no_re_evaluation_needed")
    basis_classification = str(basis_map.get("basis_classification") or "no_current_re_evaluation_basis")
    resume_mode = str(candidate_map.get("bounded_resume_mode") or "no_re_evaluation_needed")
    readiness_verdict = str(readiness_map.get("resumed_operation_readiness_verdict") or "not_ready")
    wake_classification = str(wake_map.get("wake_readiness_classification") or "not_wake_ready")
    pressure_classification = str(pressure_map.get("pressure_classification") or "insufficient_signal")
    continuity_classification = str(continuity_map.get("review_classification") or "insufficient_history")
    next_move_classification = str(next_move_map.get("next_move_classification") or "no_current_next_move")
    handoff_classification = str(
        handoff_brief_map.get("handoff_packet_brief_classification") or "no_current_packet_brief"
    )
    operator_classification = str(
        operator_map.get("operator_facing_classification") or "operator_attention_not_currently_needed"
    )
    operator_loop_posture = str(operator_map.get("loop_posture") or "informational")
    path_classification = str(path_map.get("resolution_path_classification") or "no_current_resolution_path")
    closure_classification = str(closure_map.get("closure_classification") or "no_current_closure_posture")
    coherence_classification = str(coherence_map.get("coherence_classification") or "insufficient_current_signal")

    evidence_count = sum(
        1
        for present in (
            state_class != "no_active_orchestration_item",
            watchpoint_class != "no_watchpoint_needed",
            satisfaction_status != "no_active_watchpoint",
            recommendation != "no_re_evaluation_needed",
            wake_classification != "not_wake_ready",
            pressure_classification != "insufficient_signal",
            continuity_classification != "insufficient_history",
            next_move_classification != "no_current_next_move",
            path_classification != "no_current_resolution_path",
            closure_classification != "no_current_closure_posture",
            coherence_classification != "insufficient_current_signal",
        )
        if present
    )

    contradictory = (
        coherence_classification == "materially_contradictory"
        or (
            path_classification == "completed_or_no_active_path"
            and closure_classification
            in {
                "closure_pending_on_operator_resolution",
                "closure_pending_on_internal_result",
                "closure_pending_on_external_fulfillment",
                "closure_pending_on_packet_continuity",
            }
        )
        or (
            closure_classification == "closure_already_satisfied"
            and next_move_classification != "no_current_next_move"
        )
    )
    fragmented = (
        coherence_classification == "fragmentation_dominant"
        or pressure_classification == "fragmentation_pressure"
        or continuity_classification in {"fragmented_continuity", "insufficient_history"}
        or path_classification == "fragmented_path"
        or closure_classification == "closure_blocked_by_fragmentation"
        or satisfaction_status in {"watchpoint_fragmented", "watchpoint_stale"}
        or wait_kind == "continuity_uncertain"
        or handoff_classification == "packet_continuity_uncertain"
    )
    cautionary = (
        recommendation == "hold_for_manual_review"
        or readiness_verdict in {"hold_for_operator_review", "not_ready"}
        or wake_classification in {"wake_ready_with_caution", "wake_blocked_pending_operator"}
        or pressure_classification in {"hold_pressure", "redirect_pressure", "repacketization_pressure", "mixed_pressure"}
        or operator_loop_posture == "cautionary"
        or next_move_classification in {"hold_for_operator_review_next", "rerun_packetization_gate_next", "rerun_packet_synthesis_next"}
        or closure_classification
        in {
            "closure_pending_on_operator_resolution",
            "closure_pending_on_internal_result",
            "closure_pending_on_external_fulfillment",
            "closure_pending_on_packet_continuity",
        }
        or coherence_classification == "strained_but_coherent"
    )
    aligned = (
        coherence_classification == "coherent_current_picture"
        and not cautionary
        and not fragmented
        and not contradictory
        and recommendation in {"clear_wait_and_continue_current_packet", "rerun_delegated_judgment", "no_re_evaluation_needed"}
        and next_move_classification in {"continue_current_packet_next", "rerun_delegated_judgment_next", "no_current_next_move"}
    )

    if contradictory:
        classification = "contradictory_current_picture"
        picture_posture = "contradictory"
        rationale = "neighboring_current_surfaces_materially_disagree_and_should_not_be_flattened"
    elif fragmented:
        classification = "fragmented_current_picture"
        picture_posture = "fragmented"
        rationale = "fragmentation_or_continuity_uncertainty_materially_dominates_the_current_picture"
    elif evidence_count <= 3:
        classification = "minimal_current_picture"
        picture_posture = "cautionary"
        rationale = "current_evidence_is_sparse_so_only_a_minimal_honest_picture_is_supported"
    elif aligned and evidence_count >= 8:
        classification = "mature_current_picture"
        picture_posture = "aligned"
        rationale = "neighboring_current_surfaces_are_rich_and_cleanly_aligned"
    else:
        classification = "cautionary_current_picture"
        picture_posture = "cautionary"
        rationale = "current_picture_is_mostly_aligned_but_material_caution_signals_remain"

    if classification not in _CURRENT_ORCHESTRATION_DIGEST_CLASSIFICATIONS:
        classification = "minimal_current_picture"
    if picture_posture not in _CURRENT_ORCHESTRATION_DIGEST_ALIGNMENT:
        picture_posture = "cautionary"

    resumed_bounded_motion = "not_applicable"
    if wake_classification in {"wake_not_applicable"} and recommendation == "no_re_evaluation_needed":
        resumed_bounded_motion = "not_applicable"
    elif (
        wake_classification in {"wake_ready", "wake_ready_with_caution"}
        and readiness_verdict in {"ready_to_proceed", "proceed_with_caution"}
        and recommendation in {"clear_wait_and_continue_current_packet", "rerun_delegated_judgment"}
    ):
        resumed_bounded_motion = "plausible"
    else:
        resumed_bounded_motion = "blocked"
    if resumed_bounded_motion not in _CURRENT_ORCHESTRATION_DIGEST_RESUMED_MOTION:
        resumed_bounded_motion = "blocked"

    digest_posture = (
        "informational_only" if classification == "mature_current_picture" else "conservative_caution"
    )
    state_id = str(state_map.get("current_orchestration_state_id") or "")
    watchpoint_id = str(watchpoint_map.get("orchestration_watchpoint_id") or "")
    satisfaction_id = str(satisfaction_map.get("watchpoint_satisfaction_id") or "")
    trigger_id = str(trigger_map.get("re_evaluation_trigger_id") or "")
    candidate_id = str(candidate_map.get("orchestration_resumption_candidate_id") or "")

    return {
        "schema_version": "current_orchestration_digest.v1",
        "resolved_at": _iso_utc_now(),
        "current_orchestration_digest_id": _current_orchestration_digest_id(
            current_orchestration_state_id=state_id,
            orchestration_watchpoint_id=watchpoint_id,
            watchpoint_satisfaction_id=satisfaction_id,
            re_evaluation_trigger_id=trigger_id,
            orchestration_resumption_candidate_id=candidate_id,
            digest_classification=classification,
        ),
        "digest_classification": classification,
        "overall_picture_posture": picture_posture,
        "resumed_bounded_motion": resumed_bounded_motion,
        "digest_posture": digest_posture,
        "informational_only": digest_posture == "informational_only",
        "conservatively_cautionary": digest_posture == "conservative_caution",
        "bounded_summary": {
            "current_path": path_classification,
            "current_next_move": next_move_classification,
            "current_closure_posture": closure_classification,
            "current_coherence_posture": coherence_classification,
            "current_operator_facing_posture": operator_classification,
        },
        "basis": {
            "compact_rationale": rationale,
            "basis_evidence": {
                "current_supervisory_state": state_class,
                "watchpoint_class": watchpoint_class,
                "watchpoint_wait_kind": wait_kind,
                "watchpoint_satisfaction_status": satisfaction_status,
                "re_evaluation_recommendation": recommendation,
                "re_evaluation_basis_classification": basis_classification,
                "resumption_mode": resume_mode,
                "resumed_operation_readiness_verdict": readiness_verdict,
                "wake_readiness_classification": wake_classification,
                "pressure_classification": pressure_classification,
                "proposal_packet_continuity_classification": continuity_classification,
                "current_next_move_classification": next_move_classification,
                "current_handoff_packet_brief_classification": handoff_classification,
                "current_operator_facing_classification": operator_classification,
                "current_resolution_path_classification": path_classification,
                "current_closure_classification": closure_classification,
                "current_coherence_classification": coherence_classification,
                "evidence_count": evidence_count,
            },
            "surface_linkage": {
                "current_orchestration_state_surface": "resolve_current_orchestration_state",
                "current_orchestration_watchpoint_surface": "resolve_current_orchestration_watchpoint",
                "current_orchestration_watchpoint_brief_surface": "resolve_current_orchestration_watchpoint_brief",
                "watchpoint_satisfaction_surface": "resolve_watchpoint_satisfaction",
                "re_evaluation_trigger_surface": "resolve_re_evaluation_trigger_recommendation",
                "current_re_evaluation_basis_brief_surface": "resolve_current_re_evaluation_basis_brief",
                "current_orchestration_resumption_candidate_surface": "resolve_current_orchestration_resumption_candidate",
                "current_resumed_operation_readiness_surface": "resolve_current_resumed_operation_readiness_verdict",
                "current_orchestration_wake_readiness_detector_surface": "resolve_current_orchestration_wake_readiness_detector",
                "current_orchestration_pressure_signal_surface": "resolve_current_orchestration_pressure_signal",
                "proposal_packet_continuity_review_surface": "derive_proposal_packet_continuity_review",
                "current_orchestration_next_move_brief_surface": "resolve_current_orchestration_next_move_brief",
                "current_orchestration_handoff_packet_brief_surface": "resolve_current_orchestration_handoff_packet_brief",
                "current_operator_facing_orchestration_brief_surface": "resolve_current_operator_facing_orchestration_brief",
                "current_orchestration_resolution_path_brief_surface": "resolve_current_orchestration_resolution_path_brief",
                "current_orchestration_closure_brief_surface": "resolve_current_orchestration_closure_brief",
                "current_orchestration_coherence_brief_surface": "resolve_current_orchestration_coherence_brief",
            },
            "historical_honesty": {
                "no_new_truth_source": True,
                "derived_from_existing_surfaces_only": True,
                "does_not_flatten_material_ambiguity_into_fake_clarity": True,
            },
        },
        "boundaries": {
            "non_sovereign": True,
            "non_authoritative": True,
            "non_executing": True,
            "diagnostic_only": True,
            "decision_power": "none",
            "does_not_plan_or_schedule": True,
            "does_not_execute_or_route_work": True,
            "does_not_create_new_truth_source": True,
            "does_not_create_new_orchestration_layer": True,
            "does_not_imply_permission_to_execute": True,
        },
        **anti_sovereignty_payload_builder(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "current_orchestration_digest_only": True,
                "non_executing": True,
                "does_not_execute_or_route_work": True,
                "does_not_create_new_authority_surface": True,
            },
        ),
    }

def resolve_current_orchestration_transition_brief(
    repo_root: Path,
    *,
    anti_sovereignty_payload_builder: Callable[..., dict[str, Any]],
    current_orchestration_state: Mapping[str, Any] | None = None,
    current_orchestration_watchpoint: Mapping[str, Any] | None = None,
    current_orchestration_watchpoint_brief: Mapping[str, Any] | None = None,
    watchpoint_satisfaction: Mapping[str, Any] | None = None,
    re_evaluation_trigger_recommendation: Mapping[str, Any] | None = None,
    current_re_evaluation_basis_brief: Mapping[str, Any] | None = None,
    current_orchestration_resumption_candidate: Mapping[str, Any] | None = None,
    current_resumed_operation_readiness: Mapping[str, Any] | None = None,
    current_orchestration_wake_readiness_detector: Mapping[str, Any] | None = None,
    current_orchestration_pressure_signal: Mapping[str, Any] | None = None,
    proposal_packet_continuity_review: Mapping[str, Any] | None = None,
    current_orchestration_next_move_brief: Mapping[str, Any] | None = None,
    current_orchestration_handoff_packet_brief: Mapping[str, Any] | None = None,
    current_operator_facing_orchestration_brief: Mapping[str, Any] | None = None,
    current_orchestration_resolution_path_brief: Mapping[str, Any] | None = None,
    current_orchestration_closure_brief: Mapping[str, Any] | None = None,
    current_orchestration_coherence_brief: Mapping[str, Any] | None = None,
    current_orchestration_digest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one bounded observational brief for current transition posture if the picture shifts next."""

    _ = repo_root.resolve()
    state_map = current_orchestration_state if isinstance(current_orchestration_state, Mapping) else {}
    watchpoint_map = current_orchestration_watchpoint if isinstance(current_orchestration_watchpoint, Mapping) else {}
    watchpoint_brief_map = (
        current_orchestration_watchpoint_brief if isinstance(current_orchestration_watchpoint_brief, Mapping) else {}
    )
    satisfaction_map = watchpoint_satisfaction if isinstance(watchpoint_satisfaction, Mapping) else {}
    trigger_map = re_evaluation_trigger_recommendation if isinstance(re_evaluation_trigger_recommendation, Mapping) else {}
    basis_map = current_re_evaluation_basis_brief if isinstance(current_re_evaluation_basis_brief, Mapping) else {}
    candidate_map = (
        current_orchestration_resumption_candidate
        if isinstance(current_orchestration_resumption_candidate, Mapping)
        else {}
    )
    readiness_map = current_resumed_operation_readiness if isinstance(current_resumed_operation_readiness, Mapping) else {}
    wake_map = (
        current_orchestration_wake_readiness_detector
        if isinstance(current_orchestration_wake_readiness_detector, Mapping)
        else {}
    )
    pressure_map = (
        current_orchestration_pressure_signal if isinstance(current_orchestration_pressure_signal, Mapping) else {}
    )
    continuity_map = proposal_packet_continuity_review if isinstance(proposal_packet_continuity_review, Mapping) else {}
    next_move_map = (
        current_orchestration_next_move_brief if isinstance(current_orchestration_next_move_brief, Mapping) else {}
    )
    handoff_map = (
        current_orchestration_handoff_packet_brief
        if isinstance(current_orchestration_handoff_packet_brief, Mapping)
        else {}
    )
    operator_map = (
        current_operator_facing_orchestration_brief
        if isinstance(current_operator_facing_orchestration_brief, Mapping)
        else {}
    )
    path_map = (
        current_orchestration_resolution_path_brief
        if isinstance(current_orchestration_resolution_path_brief, Mapping)
        else {}
    )
    closure_map = (
        current_orchestration_closure_brief if isinstance(current_orchestration_closure_brief, Mapping) else {}
    )
    coherence_map = (
        current_orchestration_coherence_brief if isinstance(current_orchestration_coherence_brief, Mapping) else {}
    )
    digest_map = current_orchestration_digest if isinstance(current_orchestration_digest, Mapping) else {}

    state_class = str(state_map.get("current_supervisory_state") or "no_active_orchestration_item")
    watchpoint_class = str(watchpoint_map.get("watchpoint_class") or "no_watchpoint_needed")
    wait_kind = str(watchpoint_brief_map.get("wait_kind") or "no_active_watchpoint")
    satisfaction_status = str(satisfaction_map.get("satisfaction_status") or "no_active_watchpoint")
    recommendation = str(trigger_map.get("recommendation") or "no_re_evaluation_needed")
    basis_classification = str(basis_map.get("basis_classification") or "no_current_re_evaluation_basis")
    readiness_verdict = str(readiness_map.get("resumed_operation_readiness_verdict") or "not_ready")
    wake_classification = str(wake_map.get("wake_readiness_classification") or "not_wake_ready")
    pressure_classification = str(pressure_map.get("pressure_classification") or "insufficient_signal")
    continuity_classification = str(continuity_map.get("review_classification") or "insufficient_history")
    next_move_classification = str(next_move_map.get("next_move_classification") or "no_current_next_move")
    handoff_classification = str(handoff_map.get("handoff_packet_brief_classification") or "no_current_packet_brief")
    operator_classification = str(
        operator_map.get("operator_facing_classification") or "operator_attention_not_currently_needed"
    )
    path_classification = str(path_map.get("resolution_path_classification") or "no_current_resolution_path")
    closure_classification = str(closure_map.get("closure_classification") or "no_current_closure_posture")
    coherence_classification = str(coherence_map.get("coherence_classification") or "insufficient_current_signal")
    digest_classification = str(digest_map.get("digest_classification") or "minimal_current_picture")

    resumed_bounded_motion = "blocked"
    if wake_classification == "wake_not_applicable" and recommendation == "no_re_evaluation_needed":
        resumed_bounded_motion = "not_applicable"
    elif (
        wake_classification in {"wake_ready", "wake_ready_with_caution"}
        and readiness_verdict in {"ready_to_proceed", "proceed_with_caution"}
        and recommendation in {"clear_wait_and_continue_current_packet", "rerun_delegated_judgment"}
    ):
        resumed_bounded_motion = "plausible"
    if resumed_bounded_motion not in _CURRENT_ORCHESTRATION_TRANSITION_BRIEF_RESUMED_MOTION:
        resumed_bounded_motion = "blocked"

    contradiction_material = (
        coherence_classification == "materially_contradictory"
        or digest_classification == "contradictory_current_picture"
        or (
            path_classification == "completed_or_no_active_path"
            and closure_classification
            in {
                "closure_pending_on_operator_resolution",
                "closure_pending_on_internal_result",
                "closure_pending_on_external_fulfillment",
                "closure_pending_on_packet_continuity",
            }
        )
        or (closure_classification == "closure_already_satisfied" and next_move_classification != "no_current_next_move")
    )
    fragmentation_material = (
        coherence_classification == "fragmentation_dominant"
        or pressure_classification == "fragmentation_pressure"
        or continuity_classification in {"fragmented_continuity", "insufficient_history"}
        or satisfaction_status in {"watchpoint_fragmented", "watchpoint_stale"}
        or wait_kind == "continuity_uncertain"
        or handoff_classification == "packet_continuity_uncertain"
    )
    no_material_transition = (
        state_class in {"no_active_orchestration_item", "completed_recently_no_current_item"}
        and watchpoint_class == "no_watchpoint_needed"
        and satisfaction_status in {"no_active_watchpoint", "watchpoint_satisfied"}
        and recommendation == "no_re_evaluation_needed"
        and next_move_classification == "no_current_next_move"
        and handoff_classification in {"no_current_packet_brief", "packet_not_currently_material"}
    )
    result_closure_material = closure_classification in {
        "closure_pending_on_internal_result",
        "closure_pending_on_external_fulfillment",
        "closure_already_satisfied",
    }

    category_scores = {
        "resumed": 0,
        "packet": 0,
        "operator": 0,
        "result": 0,
        "hold": 0,
    }
    if resumed_bounded_motion == "plausible":
        category_scores["resumed"] += 2
    if recommendation == "clear_wait_and_continue_current_packet":
        category_scores["resumed"] += 1
    if next_move_classification in {"continue_current_packet_next", "rerun_delegated_judgment_next"}:
        category_scores["resumed"] += 1

    if handoff_classification in {"refreshed_packet_required", "packetization_gate_pending"}:
        category_scores["packet"] += 2
    if next_move_classification in {"rerun_packet_synthesis_next", "rerun_packetization_gate_next"}:
        category_scores["packet"] += 1
    if pressure_classification == "repacketization_pressure":
        category_scores["packet"] += 1

    if watchpoint_class == "await_operator_resolution":
        category_scores["operator"] += 2
    if operator_classification in {
        "operator_should_review_hold",
        "operator_should_review_fragmentation",
        "operator_should_review_packet_refresh_context",
        "operator_should_review_redirect_or_constraint_path",
    }:
        category_scores["operator"] += 1
    if recommendation == "hold_for_manual_review":
        category_scores["operator"] += 1
    if closure_classification == "closure_pending_on_operator_resolution":
        category_scores["operator"] += 1

    if closure_classification in {
        "closure_pending_on_internal_result",
        "closure_pending_on_external_fulfillment",
        "closure_already_satisfied",
    }:
        category_scores["result"] += 3
    if path_classification in {"internal_result_path", "external_fulfillment_path", "completed_or_no_active_path"}:
        category_scores["result"] += 1

    if wake_classification in {"wake_blocked_pending_operator", "wake_blocked_by_fragmentation"}:
        category_scores["hold"] += 1
    if readiness_verdict in {"hold_for_operator_review", "not_ready"}:
        category_scores["hold"] += 1
    if next_move_classification == "hold_for_operator_review_next":
        category_scores["hold"] += 1
    if pressure_classification in {"hold_pressure", "mixed_pressure"}:
        category_scores["hold"] += 1

    strongest_score = max(category_scores.values()) if category_scores else 0
    top_categories = [key for key, score in category_scores.items() if score == strongest_score and score >= 2]
    if contradiction_material:
        classification = "transition_contradicted"
        rationale = "neighboring_transition_surfaces_materially_disagree_on_the_next_bounded_posture"
    elif fragmentation_material:
        classification = "transition_uncertain"
        rationale = "fragmentation_and_continuity_uncertainty_materially_weaken_transition_confidence"
    elif no_material_transition:
        classification = "poised_for_no_material_transition"
        rationale = "current_surfaces_show_no_meaningful_transition_pressure_beyond_ongoing_idle_or_completed_posture"
    elif result_closure_material:
        classification = "poised_for_result_closure"
        rationale = "current_resolution_and_closure_surfaces_center_the_picture_on_result_or_fulfillment_closure"
    elif top_categories and top_categories[0] == "resumed":
        classification = "poised_for_resumed_progress"
        rationale = "current_surfaces_align_on_bounded_resumption_posture_without_new_authority_claims"
    elif top_categories and top_categories[0] == "packet":
        classification = "poised_for_packet_refresh"
        rationale = "current_next_move_and_packet_surfaces_materially_indicate_refresh_or_gate_relief_posture"
    elif top_categories and top_categories[0] == "operator":
        classification = "poised_for_operator_resolution"
        rationale = "operator_dependency_is_the_material_current_transition_posture"
    elif top_categories and top_categories[0] == "result":
        classification = "poised_for_result_closure"
        rationale = "current_resolution_and_closure_surfaces_center_the_picture_on_result_or_fulfillment_closure"
    elif top_categories and top_categories[0] == "hold":
        classification = "poised_for_conservative_hold"
        rationale = "current_readiness_and_pressure_surfaces_honestly_point_to_conservative_hold"
    else:
        classification = "transition_uncertain"
        rationale = "current_surfaces_do_not_support_a_stronger_honest_transition_posture"

    if classification not in _CURRENT_ORCHESTRATION_TRANSITION_BRIEF_CLASSIFICATIONS:
        classification = "transition_uncertain"

    transition_posture = (
        "informational_only"
        if classification in {"poised_for_resumed_progress", "poised_for_no_material_transition"}
        else "conservative_caution"
    )
    if transition_posture not in _CURRENT_ORCHESTRATION_TRANSITION_BRIEF_POSTURES:
        transition_posture = "conservative_caution"

    state_id = str(state_map.get("current_orchestration_state_id") or "")
    watchpoint_id = str(watchpoint_map.get("orchestration_watchpoint_id") or "")
    satisfaction_id = str(satisfaction_map.get("watchpoint_satisfaction_id") or "")
    trigger_id = str(trigger_map.get("re_evaluation_trigger_id") or "")
    candidate_id = str(candidate_map.get("orchestration_resumption_candidate_id") or "")

    return {
        "schema_version": "current_orchestration_transition_brief.v1",
        "resolved_at": _iso_utc_now(),
        "current_orchestration_transition_brief_id": _current_orchestration_transition_brief_id(
            current_orchestration_state_id=state_id,
            orchestration_watchpoint_id=watchpoint_id,
            watchpoint_satisfaction_id=satisfaction_id,
            re_evaluation_trigger_id=trigger_id,
            orchestration_resumption_candidate_id=candidate_id,
            transition_classification=classification,
        ),
        "transition_classification": classification,
        "transition_posture": transition_posture,
        "toward_resumed_progress": classification == "poised_for_resumed_progress",
        "toward_packet_refresh": classification == "poised_for_packet_refresh",
        "toward_operator_resolution": classification == "poised_for_operator_resolution",
        "toward_result_closure": classification == "poised_for_result_closure",
        "toward_conservative_hold": classification == "poised_for_conservative_hold",
        "resumed_bounded_motion": resumed_bounded_motion,
        "fragmentation_or_contradiction_material": classification in {"transition_uncertain", "transition_contradicted"},
        "informational_only": transition_posture == "informational_only",
        "conservatively_cautionary": transition_posture == "conservative_caution",
        "basis": {
            "compact_rationale": rationale,
            "basis_evidence": {
                "current_supervisory_state": state_class,
                "watchpoint_class": watchpoint_class,
                "watchpoint_wait_kind": wait_kind,
                "watchpoint_satisfaction_status": satisfaction_status,
                "re_evaluation_recommendation": recommendation,
                "re_evaluation_basis_classification": basis_classification,
                "resumed_operation_readiness_verdict": readiness_verdict,
                "wake_readiness_classification": wake_classification,
                "pressure_classification": pressure_classification,
                "proposal_packet_continuity_classification": continuity_classification,
                "current_next_move_classification": next_move_classification,
                "current_handoff_packet_brief_classification": handoff_classification,
                "current_operator_facing_classification": operator_classification,
                "current_resolution_path_classification": path_classification,
                "current_closure_classification": closure_classification,
                "current_coherence_classification": coherence_classification,
                "current_digest_classification": digest_classification,
                "posture_scorecard": category_scores,
            },
            "materially_supporting_surfaces": [
                "resolve_current_orchestration_state",
                "resolve_current_orchestration_watchpoint",
                "resolve_current_orchestration_watchpoint_brief",
                "resolve_watchpoint_satisfaction",
                "resolve_re_evaluation_trigger_recommendation",
                "resolve_current_re_evaluation_basis_brief",
                "resolve_current_orchestration_resumption_candidate",
                "resolve_current_resumed_operation_readiness_verdict",
                "resolve_current_orchestration_wake_readiness_detector",
                "resolve_current_orchestration_pressure_signal",
                "derive_proposal_packet_continuity_review",
                "resolve_current_orchestration_next_move_brief",
                "resolve_current_orchestration_handoff_packet_brief",
                "resolve_current_operator_facing_orchestration_brief",
                "resolve_current_orchestration_resolution_path_brief",
                "resolve_current_orchestration_closure_brief",
                "resolve_current_orchestration_coherence_brief",
                "resolve_current_orchestration_digest",
            ],
            "historical_honesty": {
                "no_new_truth_source": True,
                "derived_from_existing_surfaces_only": True,
                "does_not_fabricate_stronger_transition_confidence_than_visible_support": True,
            },
        },
        "boundaries": {
            "non_sovereign": True,
            "non_authoritative": True,
            "non_executing": True,
            "diagnostic_only": True,
            "decision_power": "none",
            "does_not_plan_or_schedule": True,
            "does_not_execute_or_route_work": True,
            "does_not_create_new_truth_source": True,
            "does_not_create_new_orchestration_layer": True,
            "does_not_imply_permission_to_execute": True,
        },
        **anti_sovereignty_payload_builder(
            recommendation_only=True,
            diagnostic_only=True,
            does_not_change_admission_or_execution=True,
            additional_fields={
                "current_orchestration_transition_brief_only": True,
                "non_executing": True,
                "does_not_execute_or_route_work": True,
                "does_not_create_new_authority_surface": True,
            },
        ),
    }
