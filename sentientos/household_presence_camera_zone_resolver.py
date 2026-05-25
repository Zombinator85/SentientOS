from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from sentientos.household_presence_camera_zone_config import PRECEDENCE, HouseholdCameraZoneConfigPolicy, HouseholdCameraZoneConfig, validate_zone_config

REGION_SHAPES = {"full_frame", "normalized_rectangle", "normalized_polygon", "named_region", "source_declared_region", "unknown_region"}


@dataclass(frozen=True)
class HouseholdCameraZoneResolverPolicy:
    schema_version: str = "household_presence_camera_zone_resolver.v1"
    min_confidence: float = 0.75
    fail_on_source_mismatch: bool = False


@dataclass(frozen=True)
class HouseholdCameraEventRegion:
    region_shape: str
    normalized_coordinates: tuple[float, ...] = ()
    named_region_reference: str = ""


@dataclass(frozen=True)
class HouseholdCameraZoneResolverInput:
    source_id: str
    source_kind: str
    event_id: str
    entity_class: str
    region: HouseholdCameraEventRegion
    metadata: dict[str, Any]


@dataclass(frozen=True)
class HouseholdCameraZoneMatch:
    zone_id: str
    zone_class: str
    overlap_kind: str
    overlap_score: float


@dataclass(frozen=True)
class HouseholdCameraZoneResolution:
    effective_zone: str
    matched_zones: tuple[HouseholdCameraZoneMatch, ...]
    precedence_rank: int
    redaction_required: bool


@dataclass(frozen=True)
class HouseholdCameraZoneResolverReport:
    status: str
    restrictions: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class HouseholdCameraZoneResolverResult:
    input: HouseholdCameraZoneResolverInput
    resolution: HouseholdCameraZoneResolution
    report: HouseholdCameraZoneResolverReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _coords_ok(coords: tuple[float, ...]) -> bool:
    return bool(coords) and all(0.0 <= c <= 1.0 for c in coords)


def _rect_overlap(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != 4 or len(b) != 4:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    aarea = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    return inter / aarea if aarea > 0 else 0.0


def _poly_box(coords: tuple[float, ...]) -> tuple[float, float, float, float] | None:
    if len(coords) < 6 or len(coords) % 2 != 0:
        return None
    xs = coords[0::2]
    ys = coords[1::2]
    return (min(xs), min(ys), max(xs), max(ys))


def resolve_camera_event_zone(config_payload: Mapping[str, Any], event_payload: Mapping[str, Any], policy: HouseholdCameraZoneResolverPolicy | None = None) -> HouseholdCameraZoneResolverResult:
    p = policy or HouseholdCameraZoneResolverPolicy()
    config_res = validate_zone_config(config_payload, HouseholdCameraZoneConfigPolicy(min_confidence=p.min_confidence))
    e = HouseholdCameraZoneResolverInput(
        source_id=str(event_payload.get("source_id", "unknown")),
        source_kind=str(event_payload.get("source_kind", "unknown_source")),
        event_id=str(event_payload.get("event_id", "unknown")),
        entity_class=str(event_payload.get("entity_class", "unknown")),
        region=HouseholdCameraEventRegion(
            region_shape=str(event_payload.get("region_shape", "unknown_region")),
            normalized_coordinates=tuple(float(x) for x in event_payload.get("normalized_coordinates", [])),
            named_region_reference=str(event_payload.get("named_region_reference", "")),
        ),
        metadata=dict(event_payload.get("metadata", {})) if isinstance(event_payload.get("metadata"), Mapping) else {},
    )
    warnings: set[str] = set()
    restrictions: set[str] = {"block_speaker_output", "block_external_disclosure"}
    matched: list[HouseholdCameraZoneMatch] = []
    if e.region.region_shape not in REGION_SHAPES:
        warnings.add("invalid_region_shape")
    if e.region.region_shape in {"normalized_rectangle", "normalized_polygon"} and not _coords_ok(e.region.normalized_coordinates):
        warnings.add("invalid_normalized_coordinates")

    for z in config_res.normalized_config:
        if z.source_id != e.source_id:
            continue
        score = 0.0
        kind = "none"
        if e.region.region_shape == "full_frame":
            score = 1.0
            kind = "full_frame_intersects"
        elif e.region.region_shape in {"named_region", "source_declared_region"}:
            if e.region.named_region_reference and e.region.named_region_reference == z.zone_id:
                score = 1.0
                kind = "named_region_exact"
        elif e.region.region_shape == "normalized_rectangle" and z.region_shape == "normalized_rectangle":
            score = _rect_overlap(e.region.normalized_coordinates, tuple(float(x) for x in z.__dict__.get("normalized_coordinates", ())))
            kind = "rectangle_overlap" if score > 0 else "none"
        elif e.region.region_shape == "normalized_polygon":
            eb = _poly_box(e.region.normalized_coordinates)
            zb = _poly_box(tuple(float(x) for x in z.__dict__.get("normalized_coordinates", ()))) if z.region_shape == "normalized_polygon" else None
            if eb and zb:
                score = _rect_overlap(eb, zb)
                kind = "polygon_bbox_overlap" if score > 0 else "none"
            else:
                warnings.add("polygon_requires_operator_review")
        if score > 0:
            matched.append(HouseholdCameraZoneMatch(z.zone_id, z.zone_class, kind, round(score, 6)))

    if e.region.region_shape == "unknown_region" or not matched:
        warnings.add("operator_review_required")
        restrictions.update({"block_storage", "block_profile", "block_naming", "block_evidence_retention"})
    if config_res.report.status in {"review_required", "blocked"}:
        warnings.add("config_review_required")
    for f in config_res.report.findings:
        if f.code in {"stale_or_expired_config", "low_confidence_review_required"}:
            warnings.add(f.code)

    if policy and p.fail_on_source_mismatch and all(z.source_id != e.source_id for z in config_res.normalized_config):
        warnings.add("source_mismatch")
        restrictions.update({"block_storage", "block_profile", "block_naming", "block_evidence_retention"})

    ordered = tuple(sorted(matched, key=lambda m: (PRECEDENCE.get(m.zone_class, 999), m.zone_class, m.zone_id)))
    effective = ordered[0].zone_class if ordered else "unknown_zone"
    redaction_required = effective in {"deadzone", "exterior_sensitive_zone"} or any(m.zone_class == "exterior_sensitive_zone" for m in ordered)

    if effective == "deadzone":
        restrictions.update({"block_storage", "block_profile", "block_naming", "block_evidence_retention", "block_child_visible_output"})
    if effective == "exterior_sensitive_zone":
        restrictions.update({"block_storage", "block_profile", "block_evidence_retention"})
    if effective == "adult_private_zone":
        restrictions.update({"block_profile", "block_naming", "block_child_visible_output", "block_explicit_general_memory"})
    if effective in {"protected_care_zone", "bathroom_child_safety_zone"}:
        restrictions.update({"allow_summary_only", "block_storage", "block_evidence_retention"})
    if effective == "child_safety_zone":
        restrictions.update({"block_child_visible_output", "block_adult_private_leak"})
    if effective == "wildlife_zone":
        restrictions.add("allow_wildlife_ledger_candidate")
    if effective == "exterior_security_zone":
        restrictions.add("allow_security_event_metadata")

    status = "valid"
    if any(k in warnings for k in {"operator_review_required", "invalid_normalized_coordinates", "source_mismatch"}):
        status = "review_required"
    if "invalid_normalized_coordinates" in warnings or "invalid_region_shape" in warnings:
        status = "blocked"

    resolution = HouseholdCameraZoneResolution(effective_zone=effective, matched_zones=ordered, precedence_rank=PRECEDENCE.get(effective, 999), redaction_required=redaction_required)
    report = HouseholdCameraZoneResolverReport(status=status, restrictions=tuple(sorted(restrictions)), warnings=tuple(sorted(warnings)))
    digest = hashlib.sha256(json.dumps({"event": asdict(e), "resolution": asdict(resolution), "report": asdict(report)}, sort_keys=True).encode()).hexdigest()
    return HouseholdCameraZoneResolverResult(input=e, resolution=resolution, report=report, digest=digest)


def dumps_result(result: HouseholdCameraZoneResolverResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)
