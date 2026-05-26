from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib, json
from pathlib import Path
from typing import Any, Literal, Mapping

DeviceClassification = Literal["usb_camera_candidate","integrated_camera_candidate","network_camera_metadata_candidate","virtual_camera_candidate","unknown_video_device_candidate","non_camera_device","microphone_only_device","speaker_or_talkback_device","quest_or_visor_candidate","unsupported_device"]
ReadinessRecommendation = Literal["candidate_for_offline_fixture","candidate_for_operator_review","candidate_for_dry_run_only","candidate_for_future_live_stub","blocked_microphone_only","blocked_speaker_or_talkback","blocked_unknown_device","blocked_missing_policy_chain","blocked_missing_zone_config","blocked_live_hardware","blocked_external_disclosure"]

@dataclass(frozen=True)
class HouseholdCameraHostInventoryBridgePolicy:
    schema_version: str = "household_presence_camera_host_inventory_bridge_policy.v1"
    live_hardware_allowed: bool = False
    raw_media_allowed: bool = False
    speaker_output_allowed: bool = False
    external_disclosure_allowed: bool = False

@dataclass(frozen=True)
class HouseholdCameraHostInventoryInput:
    inventory_id: str
    devices: tuple[dict[str, Any], ...]

@dataclass(frozen=True)
class HouseholdCameraHostDeviceCandidate:
    device_id: str
    device_label: str
    classification: DeviceClassification
    evidence_path: str

@dataclass(frozen=True)
class HouseholdCameraSourceCandidate:
    candidate_id: str
    source_label: str
    source_kind: DeviceClassification
    evidence_path: str
    modality_candidates: tuple[str, ...]
    household_presence_modality: str
    possible_zone_bindings: tuple[str, ...]
    privacy_risks: tuple[str, ...]
    readiness_recommendation: ReadinessRecommendation
    dry_run_recommendation: str
    operator_confirmation_required: bool
    live_hardware_allowed: bool
    raw_media_allowed: bool
    speaker_output_allowed: bool
    external_disclosure_allowed: bool
    confidence: float
    observed_at: str
    updated_at: str
    review_after: str
    notes: tuple[str, ...]
    risk_notes: tuple[str, ...]

@dataclass(frozen=True)
class HouseholdCameraHostInventoryFinding:
    device_id: str
    classification: DeviceClassification
    finding: str

@dataclass(frozen=True)
class HouseholdCameraHostInventoryBridgeReport:
    status: str
    findings: tuple[HouseholdCameraHostInventoryFinding, ...]
    candidates: tuple[HouseholdCameraSourceCandidate, ...]
    deterministic_digest: str

@dataclass(frozen=True)
class HouseholdCameraHostInventoryBridgeResult:
    policy: HouseholdCameraHostInventoryBridgePolicy
    report: HouseholdCameraHostInventoryBridgeReport
    def to_dict(self) -> dict[str, Any]: return asdict(self)


def build_default_policy() -> HouseholdCameraHostInventoryBridgePolicy: return HouseholdCameraHostInventoryBridgePolicy()
def validate_policy(policy: HouseholdCameraHostInventoryBridgePolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1") and (policy.live_hardware_allowed, policy.raw_media_allowed, policy.speaker_output_allowed, policy.external_disclosure_allowed) == (False, False, False, False)
    return {"ok": ok, "status": "household_presence_camera_host_inventory_bridge_policy_valid" if ok else "household_presence_camera_host_inventory_bridge_policy_invalid"}


def _classify(d: Mapping[str, Any]) -> DeviceClassification:
    typ = str(d.get("device_type", "")).lower(); name = str(d.get("name", "")).lower(); tags = " ".join(str(x).lower() for x in d.get("tags", []))
    text = f"{typ} {name} {tags}"
    if "microphone" in text and "camera" not in text: return "microphone_only_device"
    if "speaker" in text or "talkback" in text: return "speaker_or_talkback_device"
    if "quest" in text or "visor" in text: return "quest_or_visor_candidate"
    if "network_camera" in text or "rtsp" in text or "onvif" in text: return "network_camera_metadata_candidate"
    if "virtual" in text and "camera" in text: return "virtual_camera_candidate"
    if "integrated" in text and "camera" in text: return "integrated_camera_candidate"
    if "usb" in text and "camera" in text: return "usb_camera_candidate"
    if "camera" in text or "video" in text: return "unknown_video_device_candidate"
    if "keyboard" in text or "mouse" in text: return "non_camera_device"
    return "unsupported_device"


def evaluate_inventory(payload: Mapping[str, Any], policy: HouseholdCameraHostInventoryBridgePolicy | None = None) -> HouseholdCameraHostInventoryBridgeResult:
    p = policy or build_default_policy()
    devices = payload.get("devices", []) if isinstance(payload.get("devices"), list) else []
    policy_chain_present = bool(payload.get("policy_chain_present", True)); zone_config_present = bool(payload.get("zone_config_present", True))
    findings: list[HouseholdCameraHostInventoryFinding] = []; candidates: list[HouseholdCameraSourceCandidate] = []
    for d in devices:
        if not isinstance(d, Mapping):
            continue
        did = str(d.get("device_id", "unknown")); label = str(d.get("name", did)); cls = _classify(d)
        findings.append(HouseholdCameraHostInventoryFinding(did, cls, f"classified:{cls}"))
        if cls in {"microphone_only_device","speaker_or_talkback_device","non_camera_device","unsupported_device"}:
            continue
        rec: ReadinessRecommendation = "candidate_for_dry_run_only"
        notes = ["operator_confirmation_required", "zone_config_binding_required", "policy_chain_required_before_future_live_stub"]
        if cls in {"virtual_camera_candidate","network_camera_metadata_candidate","unknown_video_device_candidate","quest_or_visor_candidate"}: rec = "candidate_for_operator_review"
        if cls == "quest_or_visor_candidate": notes.append("future_overlay_metadata_only")
        if not policy_chain_present: rec = "blocked_missing_policy_chain"
        if not zone_config_present: rec = "blocked_missing_zone_config"
        if cls == "speaker_or_talkback_device": rec = "blocked_speaker_or_talkback"
        candidates.append(HouseholdCameraSourceCandidate(
            candidate_id=f"candidate:{did}", source_label=label, source_kind=cls, evidence_path=str(d.get("host_inventory_path", "inventory.json")), modality_candidates=("camera_metadata",), household_presence_modality="camera_candidate", possible_zone_bindings=("exterior","interior","mixed"), privacy_risks=("operator_review_required",), readiness_recommendation=rec, dry_run_recommendation="dry_run_only", operator_confirmation_required=True, live_hardware_allowed=False, raw_media_allowed=False, speaker_output_allowed=False, external_disclosure_allowed=False, confidence=float(d.get("confidence", 0.5)), observed_at=str(d.get("observed_at", "")), updated_at=str(d.get("updated_at", "")), review_after=str(d.get("review_after", "")), notes=tuple(notes), risk_notes=("no_live_hardware_discovery", "no_network_fetch"),
        ))
    status = "bridge_ready" if candidates else "bridge_ready_with_warnings"
    digest = hashlib.sha256(json.dumps({"findings": [asdict(f) for f in findings], "candidates": [asdict(c) for c in candidates]}, sort_keys=True).encode()).hexdigest()
    return HouseholdCameraHostInventoryBridgeResult(p, HouseholdCameraHostInventoryBridgeReport(status, tuple(findings), tuple(candidates), digest))

def load_inventory_fixture(path: str) -> dict[str, Any]: return dict(json.loads(Path(path).read_text()))
def inspect_repo_metadata(workspace_root: str) -> dict[str, Any]:
    root = Path(workspace_root)
    paths = ["sentientos/host_inventory.py","sentientos/household_presence_sensor_inventory.py","sentientos/household_presence_camera_live_adapter_readiness.py","sentientos/household_presence_camera_dry_run_adapter.py","sentientos/household_presence_camera_policy_chain.py"]
    return {"workspace_root": str(root.resolve()), "paths": [{"path": p, "exists": (root/p).exists()} for p in paths]}

def dumps_result(result: HouseholdCameraHostInventoryBridgeResult) -> str: return json.dumps(result.to_dict(), indent=2, sort_keys=True)
