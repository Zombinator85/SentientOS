from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping
import hashlib, json

ReadinessStatus = Literal["ready_for_design","ready_for_stub_only","ready_for_operator_review","blocked_missing_policy_chain","blocked_missing_zone_config","blocked_missing_deadzone_redaction","blocked_missing_event_bridge","blocked_missing_sensor_inventory","blocked_missing_tests","blocked_live_runtime_risk","blocked_speaker_boundary","blocked_external_authority_boundary","failed"]
SurfaceClass = Literal["existing_live_camera_surface","existing_vision_surface","existing_perception_bus_surface","existing_affect_or_gaze_surface","existing_talkback_surface","existing_host_inventory_surface","policy_chain_surface","zone_config_surface","redaction_surface","fixture_surface","docs_surface","tests_surface","unknown_surface"]
Severity = Literal["info","warning","error","blocked"]

REQ = {
 "sensor_inventory":"sentientos/household_presence_sensor_inventory.py", "event_bridge":"sentientos/household_presence_camera_event_bridge.py", "deadzone_redaction":"sentientos/household_presence_deadzone_redaction.py", "redaction_pipeline":"sentientos/household_presence_camera_redaction_pipeline.py", "zone_config":"sentientos/household_presence_camera_zone_config.py", "zone_resolver":"sentientos/household_presence_camera_zone_resolver.py", "policy_chain":"sentientos/household_presence_camera_policy_chain.py", "matrix_runner":"scripts/run_work_item_review_packet_matrix.py", "landing_gate":"scripts/codex_pr_landing_gate.py", "landing_supervisor":"scripts/codex_landing_supervisor.py",
}
ALLOWED=("design_live_adapter_stub","add_offline_adapter_fixtures","add_operator_confirmed_dry_run","add_policy_chain_contract_tests","add_host_inventory_bridge","manual_operator_review")
FORBIDDEN=("open_camera_now","enable_live_recording","enable_speaker_output","enable_external_disclosure","bypass_policy_chain","bypass_zone_config","bypass_deadzone_redaction","store_raw_video_without_redaction","child_visible_sensitive_output")

@dataclass(frozen=True)
class HouseholdCameraLiveAdapterReadinessPolicy: schema_version:str="household_camera_live_adapter_readiness_policy.v1"; require_fixtures:bool=True
@dataclass(frozen=True)
class HouseholdCameraLiveAdapterSurface: surface_id:str; path:str; classification:SurfaceClass; exists:bool
@dataclass(frozen=True)
class HouseholdCameraLiveAdapterPrerequisite: prerequisite_id:str; ok:bool; evidence_path:str=""
@dataclass(frozen=True)
class HouseholdCameraLiveAdapterFinding: finding_id:str; severity:Severity; surface_id:str; message:str; recommendation:str; task_owned:bool; evidence_path:str=""
@dataclass(frozen=True)
class HouseholdCameraLiveAdapterReadinessReport:
    status:ReadinessStatus; surfaces:tuple[HouseholdCameraLiveAdapterSurface,...]; prerequisites:tuple[HouseholdCameraLiveAdapterPrerequisite,...]; findings:tuple[HouseholdCameraLiveAdapterFinding,...]; missing_prerequisites:tuple[str,...]; blocked_reasons:tuple[str,...]; allowed_next_steps:tuple[str,...]=ALLOWED; forbidden_next_steps:tuple[str,...]=FORBIDDEN; deterministic_digest:str=""
@dataclass(frozen=True)
class HouseholdCameraLiveAdapterReadinessResult:
    report:HouseholdCameraLiveAdapterReadinessReport
    def to_dict(self)->dict[str,Any]: return asdict(self)

def build_default_policy()->HouseholdCameraLiveAdapterReadinessPolicy: return HouseholdCameraLiveAdapterReadinessPolicy()
def validate_policy(policy:HouseholdCameraLiveAdapterReadinessPolicy)->dict[str,Any]: ok=policy.schema_version.endswith('.v1'); return {"ok":ok,"status":"household_camera_live_adapter_readiness_policy_valid" if ok else "household_camera_live_adapter_readiness_policy_invalid"}

def _classify(path:str)->SurfaceClass:
    if "camera_daemon" in path: return "existing_live_camera_surface"
    if "vision_tracker" in path: return "existing_vision_surface"
    if "PERCEPTION_BUS" in path or "perception_bus" in path: return "existing_perception_bus_surface"
    if "face_emotion" in path or "gaze_adapter" in path: return "existing_affect_or_gaze_surface"
    if "talkback" in path: return "existing_talkback_surface"
    if "host_inventory" in path: return "existing_host_inventory_surface"
    if "policy_chain" in path: return "policy_chain_surface"
    if "zone_config" in path or "zone_resolver" in path: return "zone_config_surface"
    if "redaction" in path: return "redaction_surface"
    if "/fixtures/" in path: return "fixture_surface"
    if path.startswith("docs/"): return "docs_surface"
    if path.startswith("tests/"): return "tests_surface"
    return "unknown_surface"

def inspect_repo_surfaces(workspace_root:str)->tuple[HouseholdCameraLiveAdapterSurface,...]:
    known=[*REQ.values(),"camera_daemon.py","vision_tracker.py","face_emotion.py","scripts/perception/gaze_adapter.py","docs/PERCEPTION_BUS.md","docs/schemas/perception_bus.schema.json","talkback_bridge.py","sentientos/host_inventory.py","tests/test_household_presence_camera_live_adapter_readiness.py","tests/test_build_household_presence_camera_live_adapter_readiness_script.py"]
    root=Path(workspace_root); out=[]
    for p in known:
        out.append(HouseholdCameraLiveAdapterSurface(surface_id=p.replace('/','_'),path=p,classification=_classify(p),exists=(root/p).exists()))
    return tuple(out)

def evaluate_readiness(payload:Mapping[str,Any], policy:HouseholdCameraLiveAdapterReadinessPolicy|None=None)->HouseholdCameraLiveAdapterReadinessResult:
    pol=policy or build_default_policy(); root=str(payload.get("workspace_root",".")); surfaces=inspect_repo_surfaces(root); exists={s.path:s.exists for s in surfaces}
    prereq=[]; findings=[]; missing=[]; blocked=[]
    simulated=set(payload.get("simulate_missing",())) if isinstance(payload.get("simulate_missing"),(list,tuple,set)) else set()
    for k,v in REQ.items():
        ok=exists.get(v,False) and k not in simulated; prereq.append(HouseholdCameraLiveAdapterPrerequisite(k,ok,v if ok else ""))
        if not ok: missing.append(k)
    fixtures_dir=Path(root)/str(payload.get("fixtures_dir","tests/fixtures/household_presence_camera_live_adapter_readiness"))
    fixtures_ok=fixtures_dir.exists() and any(fixtures_dir.glob("*.json"))
    prereq.append(HouseholdCameraLiveAdapterPrerequisite("offline_fixtures",fixtures_ok,str(fixtures_dir) if fixtures_ok else ""))
    if pol.require_fixtures and not fixtures_ok: missing.append("offline_fixtures")
    risk=dict(payload.get("risk_flags",{})) if isinstance(payload.get("risk_flags"),Mapping) else {}
    if risk.get("live_runtime_risk_present"): blocked.append("blocked_live_runtime_risk")
    if risk.get("talkback_boundary_risk"): blocked.append("blocked_speaker_boundary")
    if risk.get("external_authority_risk"): blocked.append("blocked_external_authority_boundary")
    for m in missing: findings.append(HouseholdCameraLiveAdapterFinding(f"missing_{m}","blocked",m,f"Missing prerequisite: {m}","add prerequisite surface",True))
    for b in blocked: findings.append(HouseholdCameraLiveAdapterFinding(b,"blocked",b,"Boundary risk present","clear risk before stub",True))
    status:ReadinessStatus="ready_for_stub_only"
    mapping={"policy_chain":"blocked_missing_policy_chain","zone_config":"blocked_missing_zone_config","deadzone_redaction":"blocked_missing_deadzone_redaction","event_bridge":"blocked_missing_event_bridge","sensor_inventory":"blocked_missing_sensor_inventory","offline_fixtures":"blocked_missing_tests"}
    for m in missing:
        if m in mapping: status=mapping[m] # type: ignore[assignment]
    if blocked: status=blocked[0] # type: ignore[assignment]
    if status=="ready_for_stub_only" and risk.get("operator_review_required",True): status="ready_for_operator_review"
    digest=hashlib.sha256(json.dumps({"status":status,"missing":sorted(missing),"blocked":sorted(blocked),"surfaces":[asdict(s) for s in surfaces]},sort_keys=True).encode()).hexdigest()
    report=HouseholdCameraLiveAdapterReadinessReport(status,surfaces,tuple(prereq),tuple(findings),tuple(sorted(missing)),tuple(blocked),deterministic_digest=digest)
    return HouseholdCameraLiveAdapterReadinessResult(report)

def dumps_result(result:HouseholdCameraLiveAdapterReadinessResult)->str: return json.dumps(result.to_dict(),indent=2,sort_keys=True)
