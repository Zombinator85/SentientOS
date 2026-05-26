from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib, json
from pathlib import Path
from typing import Any, Literal, Mapping

Status = Literal["shell_ready_for_design","shell_ready_for_operator_review","shell_blocked_capture_disabled","shell_blocked_missing_stub","shell_blocked_missing_host_candidate","shell_blocked_missing_zone_config","shell_blocked_missing_dry_run_proof","shell_blocked_missing_policy_chain","shell_blocked_live_capture_requested","shell_blocked_raw_media","shell_blocked_speaker_boundary","shell_blocked_external_authority","shell_failed"]
FORBIDDEN_NEXT_STEPS=("open_camera_now","enable_live_capture","enable_live_recording","store_raw_media","bypass_policy_chain","bypass_zone_config","bypass_dry_run","enable_speaker_output","enable_external_disclosure")
REVIEW_KINDS={"network_camera","quest_visor_overlay"}

@dataclass(frozen=True)
class HouseholdCameraLocalAdapterShellPolicy: schema_version:str="household_presence_camera_local_adapter_shell_policy.v1"; capture_enabled:bool=False; live_hardware_enabled:bool=False; raw_media_storage_enabled:bool=False; no_live_capture_performed:bool=True; speaker_output_enabled:bool=False; external_disclosure_enabled:bool=False
@dataclass(frozen=True)
class HouseholdCameraLocalAdapterShellBinding: source_kind:str=""; source_label:str=""; host_inventory_candidate_id:str=""; zone_config_id:str=""; policy_chain_id:str=""; dry_run_report_digest:str=""; stub_status:str=""; candidate_recommendation:str=""
@dataclass(frozen=True)
class HouseholdCameraLocalAdapterShellOperatorConfirmation: operator_id:str=""; confirmed_at:str=""; confirmation_scope:str=""; operator_confirmation_required:bool=True
@dataclass(frozen=True)
class HouseholdCameraLocalAdapterShellRuntimeIntent: requested_mode:Literal["design_only","dry_run_only","capture_disabled_shell","future_live_candidate"]="design_only"; capture_requested:bool=False; live_hardware_requested:bool=False; raw_media_requested:bool=False; speaker_output_requested:bool=False; external_disclosure_requested:bool=False; policy_chain_required:bool=True; zone_config_required:bool=True; dry_run_required:bool=True; operator_confirmation_required:bool=True
@dataclass(frozen=True)
class HouseholdCameraLocalAdapterShellRequest: intent:HouseholdCameraLocalAdapterShellRuntimeIntent; binding:HouseholdCameraLocalAdapterShellBinding; operator_confirmation:HouseholdCameraLocalAdapterShellOperatorConfirmation; dry_run_status:str=""; dry_run_proof_matches_binding:bool=False
@dataclass(frozen=True)
class HouseholdCameraLocalAdapterShellFinding: code:str; detail:str; blocked:bool
@dataclass(frozen=True)
class HouseholdCameraLocalAdapterShellReport: status:Status; findings:tuple[HouseholdCameraLocalAdapterShellFinding,...]; capture_enabled:bool; live_hardware_enabled:bool; raw_media_storage_enabled:bool; no_live_capture_performed:bool; speaker_output_enabled:bool; external_disclosure_enabled:bool; forbidden_next_steps:tuple[str,...]; deterministic_digest:str
@dataclass(frozen=True)
class HouseholdCameraLocalAdapterShellResult: report:HouseholdCameraLocalAdapterShellReport

def build_default_policy()->HouseholdCameraLocalAdapterShellPolicy: return HouseholdCameraLocalAdapterShellPolicy()
def validate_policy(policy:HouseholdCameraLocalAdapterShellPolicy)->dict[str,Any]:
 ok=policy.schema_version.endswith('.v1') and not any([policy.capture_enabled,policy.live_hardware_enabled,policy.raw_media_storage_enabled,policy.speaker_output_enabled,policy.external_disclosure_enabled]) and policy.no_live_capture_performed
 return {"ok":ok,"status":"household_presence_camera_local_adapter_shell_policy_valid" if ok else "household_presence_camera_local_adapter_shell_policy_invalid"}

def evaluate_local_adapter_shell(payload:Mapping[str,Any], policy:HouseholdCameraLocalAdapterShellPolicy|None=None)->HouseholdCameraLocalAdapterShellResult:
 p=policy or build_default_policy(); findings=[]
 i=dict(payload.get('intent',{})); b=dict(payload.get('binding',{})); c=dict(payload.get('operator_confirmation',{}))
 status: Status
 if i.get('capture_requested') is True or i.get('live_hardware_requested') is True: status='shell_blocked_live_capture_requested'; findings.append(HouseholdCameraLocalAdapterShellFinding('live_capture_requested','capture and live hardware requests are blocked',True))
 elif i.get('raw_media_requested') is True: status='shell_blocked_raw_media'; findings.append(HouseholdCameraLocalAdapterShellFinding('raw_media_requested','raw media is blocked',True))
 elif i.get('speaker_output_requested') is True: status='shell_blocked_speaker_boundary'; findings.append(HouseholdCameraLocalAdapterShellFinding('speaker_output_requested','speaker output is blocked',True))
 elif i.get('external_disclosure_requested') is True: status='shell_blocked_external_authority'; findings.append(HouseholdCameraLocalAdapterShellFinding('external_disclosure_requested','external disclosure blocked',True))
 elif not str(b.get('stub_status','')).startswith('stub_ready_'): status='shell_blocked_missing_stub'; findings.append(HouseholdCameraLocalAdapterShellFinding('missing_stub_proof','live adapter stub readiness required',True))
 elif not b.get('host_inventory_candidate_id'): status='shell_blocked_missing_host_candidate'; findings.append(HouseholdCameraLocalAdapterShellFinding('missing_host_candidate','host inventory candidate required',True))
 elif i.get('zone_config_required',True) and not b.get('zone_config_id'): status='shell_blocked_missing_zone_config'; findings.append(HouseholdCameraLocalAdapterShellFinding('missing_zone_config','zone config binding required',True))
 elif i.get('dry_run_required',True) and (not b.get('dry_run_report_digest') or payload.get('dry_run_status') not in {'dry_run_ready','dry_run_passed'} or payload.get('dry_run_proof_matches_binding') is not True): status='shell_blocked_missing_dry_run_proof'; findings.append(HouseholdCameraLocalAdapterShellFinding('missing_dry_run_proof','dry-run proof required',True))
 elif i.get('policy_chain_required',True) and not b.get('policy_chain_id'): status='shell_blocked_missing_policy_chain'; findings.append(HouseholdCameraLocalAdapterShellFinding('missing_policy_chain','policy chain required',True))
 elif i.get('operator_confirmation_required',True) and not (c.get('operator_id') and c.get('confirmed_at') and c.get('confirmation_scope')): status='shell_ready_for_operator_review'; findings.append(HouseholdCameraLocalAdapterShellFinding('missing_operator_confirmation','operator confirmation required for progression',False))
 elif i.get('requested_mode')=='future_live_candidate' or b.get('source_kind') in REVIEW_KINDS: status='shell_ready_for_operator_review'
 else: status='shell_ready_for_design'
 digest=hashlib.sha256(json.dumps({'status':status,'findings':[asdict(f) for f in findings],'intent':i,'binding':b,'policy':asdict(p)},sort_keys=True).encode()).hexdigest()
 return HouseholdCameraLocalAdapterShellResult(HouseholdCameraLocalAdapterShellReport(status=status,findings=tuple(findings),capture_enabled=False,live_hardware_enabled=False,raw_media_storage_enabled=False,no_live_capture_performed=True,speaker_output_enabled=False,external_disclosure_enabled=False,forbidden_next_steps=FORBIDDEN_NEXT_STEPS,deterministic_digest=digest))

def load_shell_fixture(path:str)->dict[str,Any]: return dict(json.loads(Path(path).read_text()))
def dumps_result(result:HouseholdCameraLocalAdapterShellResult)->str: return json.dumps(asdict(result),indent=2,sort_keys=True)
