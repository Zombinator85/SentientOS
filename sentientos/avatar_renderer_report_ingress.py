"""Bounded ingress for Godot's non-authoritative renderer self-reports."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Mapping

from .embodiment_self_observation import (
    EmbodimentEvidenceOwner,
    EmbodimentObservation,
    semantic_digest,
)

RENDERER_REPORT_SCHEMA = "sentientos.avatar_renderer_report:v1"
MAX_RENDERER_REPORT_BYTES = 32_768
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CORRELATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_REPORT_FIELDS = frozenset({
    "schema_version", "evidence_class", "source_id", "renderer_generation_id",
    "sequence", "reported_at", "session_id", "turn_id", "output_digest",
    "output_mode", "commanded_state", "renderer_state", "frame_delta_seconds",
    "apply_duration_usec", "body_generation", "effect_proven",
    "independent_observation", "source_digest",
})


class RendererReportIngressError(ValueError):
    """Invalid, oversized, or conflicting renderer report."""


def renderer_report_observation(report: Mapping[str, Any]) -> EmbodimentObservation:
    """Convert one Godot self-report into unverified embodiment evidence."""
    if not isinstance(report, Mapping) or set(report) != _REPORT_FIELDS:
        raise RendererReportIngressError("renderer_report_shape_invalid")
    try:
        bounded = json.loads(json.dumps(report, ensure_ascii=False, allow_nan=False))
        encoded = json.dumps(bounded, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise RendererReportIngressError("renderer_report_not_bounded_json") from exc
    if len(encoded) > MAX_RENDERER_REPORT_BYTES:
        raise RendererReportIngressError("renderer_report_too_large")
    if (bounded["schema_version"] != RENDERER_REPORT_SCHEMA
            or bounded["evidence_class"] != "avatar_renderer_reported_state"
            or bounded["source_id"] != "godot-procedural-demo"
            or not isinstance(bounded["renderer_generation_id"], str)
            or not bounded["renderer_generation_id"].startswith("godot-demo-")
            or type(bounded["sequence"]) is not int or bounded["sequence"] < 1
            or not isinstance(bounded["reported_at"], str) or not bounded["reported_at"]
            or bounded["body_generation"] != "godot-procedural-demo-unadopted"
            or bounded["effect_proven"] is not False
            or bounded["independent_observation"] is not False
            or not isinstance(bounded["source_digest"], str)
            or not _SHA256.fullmatch(bounded["source_digest"])):
        raise RendererReportIngressError("renderer_report_identity_invalid")
    source_payload = dict(bounded)
    claimed_source_digest = source_payload.pop("source_digest")
    expected_source_digest = "sha256:" + hashlib.sha256(json.dumps(
        source_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")).hexdigest()
    if claimed_source_digest != expected_source_digest:
        raise RendererReportIngressError("renderer_report_source_digest_mismatch")
    try:
        timestamp = datetime.fromisoformat(bounded["reported_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise RendererReportIngressError("renderer_report_timestamp_invalid") from exc
    if timestamp.tzinfo is None:
        raise RendererReportIngressError("renderer_report_timestamp_invalid")
    state = bounded["commanded_state"]
    renderer_state = bounded["renderer_state"]
    intensity = state.get("intensity") if isinstance(state, dict) else None
    frame_delta = bounded["frame_delta_seconds"]
    apply_duration = bounded["apply_duration_usec"]
    if (not isinstance(state, dict)
            or set(state) != {"expression", "mood", "intensity", "motion", "workload_mode"}
            or any(not isinstance(state[key], str) or not state[key]
                   for key in ("expression", "mood", "motion"))
            or state["workload_mode"] not in {"normal", "gaming"}
            or not isinstance(intensity, (int, float)) or isinstance(intensity, bool)
            or not 0 <= intensity <= 1
            or not isinstance(renderer_state, dict)
            or set(renderer_state) != {"expression", "motion", "applied_render_cap_fps"}
            or not isinstance(renderer_state["expression"], dict)
            or not isinstance(renderer_state["motion"], dict)
            or not isinstance(renderer_state["expression"].get("status"), str)
            or set(renderer_state["motion"]) != {
                "active_motion", "animation_player_active", "head_rotation_radians",
                "left_arm_rotation_radians", "body_position", "observed_nodes",
            }
            or not isinstance(renderer_state["motion"].get("observed_nodes"), dict)
            or type(renderer_state["applied_render_cap_fps"]) is not int
            or renderer_state["applied_render_cap_fps"] not in {15, 60}
            or (frame_delta is not None and (
                type(frame_delta) not in {int, float} or not math.isfinite(frame_delta)
                or frame_delta < 0))
            or type(apply_duration) is not int or apply_duration < 0):
        raise RendererReportIngressError("renderer_report_state_invalid")
    session_id, turn_id = bounded["session_id"], bounded["turn_id"]
    output_digest, output_mode = bounded["output_digest"], bounded["output_mode"]
    if (session_id is None) != (turn_id is None):
        raise RendererReportIngressError("renderer_report_correlation_incomplete")
    if session_id is not None and (
            not isinstance(session_id, str) or not _CORRELATION_ID.fullmatch(session_id)
            or not isinstance(turn_id, str) or not _CORRELATION_ID.fullmatch(turn_id)
            or not isinstance(output_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", output_digest)
            or output_mode != "chat_response_visual_only"):
        raise RendererReportIngressError("renderer_report_correlation_invalid")
    if session_id is None and any(value is not None for value in (output_digest, output_mode)):
        raise RendererReportIngressError("renderer_report_correlation_invalid")

    report_digest = semantic_digest(bounded)
    source_id = (f"godot-renderer:{bounded['renderer_generation_id']}:{bounded['sequence']}")
    observation = EmbodimentObservation(
        source_id=source_id,
        source_schema=RENDERER_REPORT_SCHEMA,
        source_digest=report_digest,
        observed_at=bounded["reported_at"],
        provenance_class="godot_procedural_demo_unverified",
        freshness="unknown",
        posture="synthetic_test",
        evidence_class="avatar_renderer_reported_state",
        subject_id=source_id,
        subject_kind="avatar_renderer_reported_state",
        payload={
            "renderer_report": bounded,
            "renderer_report_digest": report_digest,
            "renderer_source_digest_claim": bounded["source_digest"],
            "capture_status": "unverified_renderer_self_report",
        },
        effect_claimed=False,
        effect_proven=False,
    )
    observation.validate()
    return observation


def renderer_report_world_state_record(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project the report with the repository's existing non-authoritative owner."""
    observation = renderer_report_observation(report)
    records = EmbodimentEvidenceOwner([observation]).world_state_records()
    if len(records) != 1:
        raise RendererReportIngressError("renderer_report_projection_invalid")
    return records[0]
