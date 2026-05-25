from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, cast

from sentientos.household_presence_camera_event_bridge import bridge_event
from sentientos.household_presence_camera_zone_resolver import resolve_camera_event_zone
from sentientos.household_presence_deadzone_redaction import evaluate_redaction_request
from sentientos.household_presence_camera_redaction_pipeline import evaluate_pipeline

Decision = Literal[
    "live_awareness_only","redacted_ambient_journal","wildlife_ledger_candidate","security_event_metadata","nuisance_evidence_metadata","protected_care_summary","operator_review_required","blocked_by_deadzone","blocked_by_missing_redaction","blocked_by_adult_private_policy","blocked_by_child_visible_policy","blocked_by_speaker_boundary","blocked_by_external_authority_boundary","blocked_by_unknown_zone","blocked_by_stale_config","blocked_by_low_confidence","blocked_by_policy",
]

@dataclass(frozen=True)
class HouseholdCameraPolicyChainPolicy:
    schema_version: str = "household_presence_camera_policy_chain_policy.v1"
    stale_config_blocks: bool = False
    low_confidence_blocks: bool = False


@dataclass(frozen=True)
class HouseholdCameraPolicyChainInput:
    event: dict[str, Any]
    config: dict[str, Any]
    policy_flags: dict[str, Any]


@dataclass(frozen=True)
class HouseholdCameraPolicyChainStage:
    name: str
    status: str


@dataclass(frozen=True)
class HouseholdCameraPolicyChainDecision:
    route: Decision
    blocked: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class HouseholdCameraPolicyChainReport:
    stages: tuple[HouseholdCameraPolicyChainStage, ...]
    bridge_status: str
    zone_status: str
    redaction_status: str
    pipeline_status: str


@dataclass(frozen=True)
class HouseholdCameraPolicyChainResult:
    decision: HouseholdCameraPolicyChainDecision
    report: HouseholdCameraPolicyChainReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_default_policy() -> HouseholdCameraPolicyChainPolicy:
    return HouseholdCameraPolicyChainPolicy()


def validate_policy(policy: HouseholdCameraPolicyChainPolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1")
    return {"ok": ok, "status": "household_camera_policy_chain_policy_valid" if ok else "household_camera_policy_chain_policy_invalid"}


def evaluate_policy_chain(payload: Mapping[str, Any], policy: HouseholdCameraPolicyChainPolicy | None = None) -> HouseholdCameraPolicyChainResult:
    p = policy or build_default_policy()
    event = dict(payload.get("event", {})) if isinstance(payload.get("event"), Mapping) else {}
    config = dict(payload.get("config", {})) if isinstance(payload.get("config"), Mapping) else {}
    stages = [HouseholdCameraPolicyChainStage("input_loaded", "ok")]
    bridge = bridge_event(event)
    stages.append(HouseholdCameraPolicyChainStage("event_bridge_normalized", bridge.status))
    zone = resolve_camera_event_zone(config, event)
    stages.append(HouseholdCameraPolicyChainStage("zone_resolved", zone.report.status))
    redaction = evaluate_redaction_request({"event_id": str(event.get("event_id", "unknown")), "zone": zone.resolution.effective_zone, "entity_class": str(event.get("entity_class", "unknown")), "event_type": str(event.get("event_type", "generic")), "redaction_required": zone.resolution.redaction_required, "redaction_state": "applied" if bool(event.get("metadata", {}).get("redaction_applied", False)) else "required_not_applied" if zone.resolution.redaction_required else "not_required", "speaker_output_requested": bool(event.get("metadata", {}).get("speaker_action_requested", False)), "external_disclosure_requested": bool(event.get("metadata", {}).get("external_authority_contact", False)), "named_profile_requested": bool(event.get("metadata", {}).get("named_profile_requested", False)), "intimate_profile_requested": bool(event.get("metadata", {}).get("intimate_profile_requested", False)), "license_plate_tracking_requested": bool(event.get("metadata", {}).get("license_plate_tracking_requested", False)), "metadata": dict(event.get("metadata", {})) if isinstance(event.get("metadata"), Mapping) else {}})
    stages.append(HouseholdCameraPolicyChainStage("redaction_contract_evaluated", redaction.decision.status))
    pipe = evaluate_pipeline({**event, "zone": zone.resolution.effective_zone})

    valid_routes = set(Decision.__args__)  # type: ignore[attr-defined]
    route = cast(Decision, pipe.decision.route if pipe.decision.route in valid_routes else "blocked_by_policy")
    reasons = set(pipe.decision.reasons)
    blocked = pipe.decision.blocked
    warnings = set(zone.report.warnings)
    if "stale_or_expired_config" in warnings:
        route = "blocked_by_stale_config" if p.stale_config_blocks else "operator_review_required"
        blocked = p.stale_config_blocks
    if "low_confidence_review_required" in warnings:
        route = "blocked_by_low_confidence" if p.low_confidence_blocks else "operator_review_required"
        blocked = p.low_confidence_blocks
    if zone.resolution.effective_zone == "unknown_zone":
        route = "blocked_by_unknown_zone" if blocked else "operator_review_required"
    if route == "operator_review_required":
        stages.append(HouseholdCameraPolicyChainStage("operator_review_marked", "required"))
    stages.append(HouseholdCameraPolicyChainStage("downstream_route_selected", route))
    if blocked or route.startswith("blocked_"):
        stages.append(HouseholdCameraPolicyChainStage("blocked", "yes"))

    digest = hashlib.sha256(json.dumps({"event": event, "route": route, "stages": [asdict(s) for s in stages]}, sort_keys=True).encode()).hexdigest()
    return HouseholdCameraPolicyChainResult(HouseholdCameraPolicyChainDecision(route=route, blocked=blocked or route.startswith("blocked_"), reasons=tuple(sorted(reasons))), HouseholdCameraPolicyChainReport(tuple(stages), bridge.status, zone.report.status, redaction.decision.status, pipe.status), digest)


def dumps_result(result: HouseholdCameraPolicyChainResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)
