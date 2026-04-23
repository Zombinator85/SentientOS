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
