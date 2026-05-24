from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

InventoryStatus = Literal[
    "inventory_ready",
    "inventory_ready_with_warnings",
    "inventory_manual_review_required",
    "inventory_blocked",
    "inventory_failed",
]
SurfaceClassification = Literal[
    "existing_live_surface",
    "existing_metadata_surface",
    "existing_schema_surface",
    "existing_doc_surface",
    "existing_test_surface",
    "planned_future_surface",
    "unknown_surface",
]
Recommendation = Literal[
    "reuse_existing_surface",
    "wrap_with_policy_gate",
    "document_before_use",
    "needs_deadzone_policy",
    "needs_speaker_gate",
    "needs_child_safety_review",
    "needs_adult_private_filter",
    "needs_affective_non_authority_check",
    "defer_live_runtime",
    "do_not_duplicate",
]


@dataclass(frozen=True)
class HouseholdPresenceSensorInventoryPolicy:
    workspace_root: str
    metadata_only: bool = True
    static_analysis_only: bool = True


@dataclass(frozen=True)
class HouseholdPresenceSensorMapping:
    household_presence_modality: str
    zone_relevance: str
    memory_entity_implications: str


@dataclass(frozen=True)
class HouseholdPresenceSensorSurface:
    repo_path: str
    surface_kind: SurfaceClassification
    live_runtime_or_metadata_only: str
    authority_level: str
    action_or_speaker_capability: str
    mapping: HouseholdPresenceSensorMapping
    linked_artifacts: tuple[str, ...]
    risk_notes: tuple[str, ...]
    integration_recommendations: tuple[Recommendation, ...]


@dataclass(frozen=True)
class HouseholdPresenceSensorInventory:
    policy: HouseholdPresenceSensorInventoryPolicy
    surfaces: tuple[HouseholdPresenceSensorSurface, ...]
    future_adapter_sequence: tuple[str, ...]


@dataclass(frozen=True)
class HouseholdPresenceSensorInventoryResult:
    status: InventoryStatus
    warnings: tuple[str, ...]
    inventory: HouseholdPresenceSensorInventory

KNOWN = (
    HouseholdPresenceSensorSurface("camera_daemon.py", "existing_live_surface", "live_runtime", "observation", "none", HouseholdPresenceSensorMapping("camera_exterior", "exterior|mixed", "entity sightings only; no authority"), ("tests/test_camera_daemon.py",), ("live camera path; must not run in inventory",), ("defer_live_runtime", "wrap_with_policy_gate", "do_not_duplicate")),
    HouseholdPresenceSensorSurface("vision_tracker.py", "existing_live_surface", "live_runtime", "observation", "none", HouseholdPresenceSensorMapping("camera_interior", "interior|mixed", "vision events; non-authoritative"), ("tests/test_vision_tracker.py",), ("vision surface exists already",), ("reuse_existing_surface", "wrap_with_policy_gate", "do_not_duplicate")),
    HouseholdPresenceSensorSurface("face_emotion.py", "existing_live_surface", "live_runtime", "non_authoritative_affect", "none", HouseholdPresenceSensorMapping("camera_interior", "interior", "affect signals must never grant authority"), (), ("affective inference must remain non-authority",), ("needs_affective_non_authority_check", "defer_live_runtime", "do_not_duplicate")),
    HouseholdPresenceSensorSurface("scripts/perception/gaze_adapter.py", "existing_metadata_surface", "metadata_only", "observation", "none", HouseholdPresenceSensorMapping("quest_operator_visor", "operator", "gaze metadata only"), (), ("embodied gaze path exists",), ("reuse_existing_surface", "do_not_duplicate")),
    HouseholdPresenceSensorSurface("docs/PERCEPTION_BUS.md", "existing_doc_surface", "metadata_only", "documentation", "none", HouseholdPresenceSensorMapping("local_device_context", "mixed", "documents event bus semantics"), ("docs/schemas/perception_bus.schema.json",), ("contract doc must align with schema",), ("document_before_use", "do_not_duplicate")),
    HouseholdPresenceSensorSurface("docs/schemas/perception_bus.schema.json", "existing_schema_surface", "metadata_only", "schema", "none", HouseholdPresenceSensorMapping("local_device_context", "mixed", "perception envelope schema"), ("docs/PERCEPTION_BUS.md",), ("schema should be reused",), ("reuse_existing_surface", "do_not_duplicate")),
    HouseholdPresenceSensorSurface("sentientos/host_inventory.py", "existing_metadata_surface", "metadata_only", "observation", "none", HouseholdPresenceSensorMapping("usb_device_presence", "local", "host device inventory only"), ("tests/test_host_inventory.py",), ("host inventory already implements metadata inventory",), ("reuse_existing_surface", "do_not_duplicate")),
    HouseholdPresenceSensorSurface("sentientos/embodiment/embodiment_daemon.py", "existing_live_surface", "live_runtime", "runtime_observation", "none", HouseholdPresenceSensorMapping("local_device_context", "mixed", "embodiment stream ingress"), (), ("do not invoke daemon from inventory",), ("defer_live_runtime", "do_not_duplicate")),
    HouseholdPresenceSensorSurface("sentientos/embodiment/embodiment_digest.py", "existing_metadata_surface", "metadata_only", "digest", "none", HouseholdPresenceSensorMapping("local_device_context", "mixed", "deterministic embodiment digest"), (), (), ("reuse_existing_surface", "do_not_duplicate")),
    HouseholdPresenceSensorSurface("talkback_bridge.py", "existing_live_surface", "live_runtime", "gated_host_interaction", "speaker_output", HouseholdPresenceSensorMapping("camera_speaker_exterior", "exterior", "speaker/output bridge"), (), ("speaker output requires strict gating",), ("needs_speaker_gate", "wrap_with_policy_gate", "defer_live_runtime", "do_not_duplicate")),
)

FUTURE_SEQUENCE = (
    "stabilize existing camera/vision/perception bus docs and tests",
    "add policy-gated exterior camera event bridge using existing camera/vision surfaces where possible",
    "add deadzone/masking metadata and event redaction contract",
    "add wildlife ledger adapter from policy-gated exterior event metadata",
    "add protected care event summaries without raw bathroom retention",
    "add host inventory / USB sensory device discovery bridge using existing host_inventory work",
    "add roomfield/Wi-Fi RF stub only after inventory confirms available hardware path",
    "add roomfield fusion",
    "add Quest/operator visor read-only overlay if existing surfaces support it",
    "add speaker policy gate before any talkback/runtime output",
)


def build_default_inventory(workspace_root: str = ".") -> HouseholdPresenceSensorInventoryResult:
    policy = HouseholdPresenceSensorInventoryPolicy(workspace_root=str(Path(workspace_root).resolve()))
    inventory = HouseholdPresenceSensorInventory(policy=policy, surfaces=tuple(sorted(KNOWN, key=lambda s: s.repo_path)), future_adapter_sequence=FUTURE_SEQUENCE)
    warnings = tuple(sorted(f"missing_surface:{s.repo_path}" for s in inventory.surfaces if not (Path(workspace_root) / s.repo_path).exists()))
    status: InventoryStatus = "inventory_ready" if not warnings else "inventory_ready_with_warnings"
    return HouseholdPresenceSensorInventoryResult(status=status, warnings=warnings, inventory=inventory)


def inventory_result_to_dict(result: HouseholdPresenceSensorInventoryResult) -> dict[str, object]:
    def sdict(s: HouseholdPresenceSensorSurface) -> dict[str, object]:
        return {
            "repo_path": s.repo_path,
            "surface_kind": s.surface_kind,
            "live_runtime_or_metadata_only": s.live_runtime_or_metadata_only,
            "authority_level": s.authority_level,
            "action_or_speaker_capability": s.action_or_speaker_capability,
            "mapping": s.mapping.__dict__,
            "linked_artifacts": list(s.linked_artifacts),
            "risk_notes": list(s.risk_notes),
            "integration_recommendations": list(s.integration_recommendations),
        }
    return {"status": result.status, "warnings": list(result.warnings), "policy": result.inventory.policy.__dict__, "surfaces": [sdict(x) for x in result.inventory.surfaces], "future_adapter_sequence": list(result.inventory.future_adapter_sequence)}


def dumps_inventory_json(result: HouseholdPresenceSensorInventoryResult) -> str:
    return json.dumps(inventory_result_to_dict(result), indent=2, sort_keys=True) + "\n"


def validate_inventory_contains_known_surfaces(result: HouseholdPresenceSensorInventoryResult) -> tuple[bool, tuple[str, ...]]:
    paths = {s.repo_path for s in result.inventory.surfaces}
    missing = tuple(sorted(s.repo_path for s in KNOWN if s.repo_path not in paths))
    return (len(missing) == 0, missing)
