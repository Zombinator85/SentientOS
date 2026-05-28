from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib, json
from typing import Any, Literal, Mapping

ReviewMode = Literal["design_only", "dry_run_only", "future_live_review"]
ReviewStatusLiteral = Literal[
"capture_review_packet_ready_for_operator_review","capture_review_packet_ready_for_dry_run_only","capture_review_packet_valid_with_warnings",
"capture_review_packet_blocked_missing_authorization","capture_review_packet_blocked_missing_denial_ledger","capture_review_packet_blocked_missing_disabled_capture_proof",
"capture_review_packet_blocked_missing_shell_proof","capture_review_packet_blocked_missing_stub_proof","capture_review_packet_blocked_missing_host_candidate",
"capture_review_packet_blocked_missing_zone_config","capture_review_packet_blocked_missing_dry_run_proof","capture_review_packet_blocked_missing_policy_chain",
"capture_review_packet_blocked_unresolved_denials","capture_review_packet_blocked_scope_mismatch","capture_review_packet_blocked_stale_proof",
"capture_review_packet_blocked_media_payload","capture_review_packet_blocked_speaker_boundary","capture_review_packet_blocked_external_authority",
"capture_review_packet_invalid","capture_review_packet_failed",
]
ReviewStatus = str
FORBIDDEN_NEXT_STEPS=("open_camera_now","attempt_capture","enable_live_capture","enable_live_recording","store_raw_media","attach_media_payload","bypass_authorization_envelope","bypass_denial_ledger","bypass_policy_chain","bypass_zone_config","bypass_disabled_capture_boundary","bypass_dry_run","enable_speaker_output","enable_external_disclosure")

@dataclass(frozen=True)
class HouseholdCameraCaptureReviewPacketPolicy:
    schema_version:str="household_presence_camera_capture_review_packet_policy.v1"; allow_first_review_without_denial_ledger:bool=False; allow_design_only_without_dry_run_proof:bool=True; max_unresolved_denials:int=0; stale_proof_seconds:int=86400; stale_proof_mode:Literal["block","warn"]="block"
@dataclass(frozen=True)
class HouseholdCameraCaptureReviewProofSet:
    authorization_envelope_digest:str=""; denial_ledger_digest:str=""; disabled_capture_proof_digest:str=""; local_shell_proof_digest:str=""; live_adapter_stub_proof_digest:str=""; host_candidate_digest:str=""; zone_config_id:str=""; zone_config_digest:str=""; dry_run_proof_digest:str=""; readiness_proof_digest:str=""; policy_chain_id:str=""; policy_chain_digest:str=""; operator_grant_id:str|None=None; source_candidate_id:str=""; requested_mode:ReviewMode="design_only"; observed_at:str=""; reviewed_at:str=""; review_after:str=""; expires_at:str=""; unresolved_denial_count:int=0; media_payload_present:bool=False; base64_media_present:bool=False; speaker_output_requested:bool=False; external_disclosure_requested:bool=False; notes:str=""
@dataclass(frozen=True)
class HouseholdCameraCaptureReviewInput: proof_set:HouseholdCameraCaptureReviewProofSet
@dataclass(frozen=True)
class HouseholdCameraCaptureReviewFinding: code:str; message:str
@dataclass(frozen=True)
class HouseholdCameraCaptureReviewPacket:
    status:ReviewStatus; digest:str; review_enables_live_capture:bool=False; capture_enabled:bool=False; capture_available:bool=False; live_hardware_enabled:bool=False; raw_media_storage_enabled:bool=False; no_live_capture_performed:bool=True; speaker_output_enabled:bool=False; external_disclosure_enabled:bool=False; forbidden_next_steps:tuple[str,...]=FORBIDDEN_NEXT_STEPS
@dataclass(frozen=True)
class HouseholdCameraCaptureReviewReport: status:ReviewStatus; findings:tuple[HouseholdCameraCaptureReviewFinding,...]
@dataclass(frozen=True)
class HouseholdCameraCaptureReviewResult:
    status:ReviewStatus; packet:HouseholdCameraCaptureReviewPacket; report:HouseholdCameraCaptureReviewReport
    def to_dict(self)->dict[str,Any]: return asdict(self)

def _dig(v:Any)->str: return hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest()
def build_default_policy()->HouseholdCameraCaptureReviewPacketPolicy: return HouseholdCameraCaptureReviewPacketPolicy()
def validate_policy(policy:HouseholdCameraCaptureReviewPacketPolicy)->dict[str,Any]: return {"ok":policy.schema_version.endswith('.v1'),"status":"household_presence_camera_capture_review_packet_policy_valid" if policy.schema_version.endswith('.v1') else "household_presence_camera_capture_review_packet_policy_invalid"}

def _get(payload:Mapping[str,Any])->HouseholdCameraCaptureReviewProofSet: return HouseholdCameraCaptureReviewProofSet(**{k:v for k,v in payload.items() if k in HouseholdCameraCaptureReviewProofSet.__dataclass_fields__})

def evaluate_capture_review_packet(payload:Mapping[str,Any], policy:HouseholdCameraCaptureReviewPacketPolicy|None=None)->HouseholdCameraCaptureReviewResult:
    p=policy or build_default_policy(); ps=_get(payload.get("proof_set",payload))
    f: list[HouseholdCameraCaptureReviewFinding] = []
    checks=[("authorization_envelope_digest","capture_review_packet_blocked_missing_authorization"),("disabled_capture_proof_digest","capture_review_packet_blocked_missing_disabled_capture_proof"),("local_shell_proof_digest","capture_review_packet_blocked_missing_shell_proof"),("live_adapter_stub_proof_digest","capture_review_packet_blocked_missing_stub_proof"),("host_candidate_digest","capture_review_packet_blocked_missing_host_candidate"),("zone_config_digest","capture_review_packet_blocked_missing_zone_config"),("policy_chain_digest","capture_review_packet_blocked_missing_policy_chain")]
    for k,s in checks:
        if not getattr(ps,k):
            return HouseholdCameraCaptureReviewResult(s,HouseholdCameraCaptureReviewPacket(s,_dig({"status":s,"missing":k})),HouseholdCameraCaptureReviewReport(s,(HouseholdCameraCaptureReviewFinding("missing_required_proof",k),)))
    if not ps.denial_ledger_digest and not p.allow_first_review_without_denial_ledger:
        s="capture_review_packet_blocked_missing_denial_ledger"; return HouseholdCameraCaptureReviewResult(s,HouseholdCameraCaptureReviewPacket(s,_dig({"status":s})),HouseholdCameraCaptureReviewReport(s,(HouseholdCameraCaptureReviewFinding("missing_denial_ledger",s),)))
    if not ps.dry_run_proof_digest and not (ps.requested_mode=="design_only" and p.allow_design_only_without_dry_run_proof):
        s="capture_review_packet_blocked_missing_dry_run_proof"; return HouseholdCameraCaptureReviewResult(s,HouseholdCameraCaptureReviewPacket(s,_dig({"status":s})),HouseholdCameraCaptureReviewReport(s,(HouseholdCameraCaptureReviewFinding("missing_dry_run_proof",s),)))
    if ps.unresolved_denial_count>p.max_unresolved_denials: s="capture_review_packet_blocked_unresolved_denials"; return HouseholdCameraCaptureReviewResult(s,HouseholdCameraCaptureReviewPacket(s,_dig({"status":s})),HouseholdCameraCaptureReviewReport(s,(HouseholdCameraCaptureReviewFinding("unresolved_denials",str(ps.unresolved_denial_count)),)))
    if ps.media_payload_present or ps.base64_media_present: s="capture_review_packet_blocked_media_payload"; return HouseholdCameraCaptureReviewResult(s,HouseholdCameraCaptureReviewPacket(s,_dig({"status":s})),HouseholdCameraCaptureReviewReport(s,(HouseholdCameraCaptureReviewFinding("media_payload",s),)))
    if ps.speaker_output_requested: s="capture_review_packet_blocked_speaker_boundary"; return HouseholdCameraCaptureReviewResult(s,HouseholdCameraCaptureReviewPacket(s,_dig({"status":s})),HouseholdCameraCaptureReviewReport(s,(HouseholdCameraCaptureReviewFinding("speaker_boundary",s),)))
    if ps.external_disclosure_requested: s="capture_review_packet_blocked_external_authority"; return HouseholdCameraCaptureReviewResult(s,HouseholdCameraCaptureReviewPacket(s,_dig({"status":s})),HouseholdCameraCaptureReviewReport(s,(HouseholdCameraCaptureReviewFinding("external_authority",s),)))
    if ps.source_candidate_id and ps.zone_config_id and ps.policy_chain_id and ps.source_candidate_id not in ps.zone_config_id+ps.policy_chain_id:
        s="capture_review_packet_blocked_scope_mismatch"; return HouseholdCameraCaptureReviewResult(s,HouseholdCameraCaptureReviewPacket(s,_dig({"status":s})),HouseholdCameraCaptureReviewReport(s,(HouseholdCameraCaptureReviewFinding("scope_mismatch",s),)))
    status:ReviewStatus="capture_review_packet_ready_for_operator_review"
    if ps.requested_mode=="dry_run_only": status="capture_review_packet_ready_for_dry_run_only"
    if ps.requested_mode=="future_live_review": status="capture_review_packet_ready_for_operator_review"
    findings=tuple(f)
    if ps.reviewed_at and ps.expires_at and ps.reviewed_at>ps.expires_at:
        if p.stale_proof_mode=="block": status="capture_review_packet_blocked_stale_proof"
        else: status="capture_review_packet_valid_with_warnings"; findings+=(HouseholdCameraCaptureReviewFinding("stale_proof","stale proof warned"),)
    d=_dig({"status":status,"proof_set":asdict(ps)})
    return HouseholdCameraCaptureReviewResult(status,HouseholdCameraCaptureReviewPacket(status,d),HouseholdCameraCaptureReviewReport(status,findings))
