from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping, cast

DenialClassification = Literal[
    "missing_operator_grant", "expired_operator_grant", "revoked_operator_grant", "scope_mismatch",
    "disabled_capture_boundary_missing", "local_shell_proof_missing", "live_adapter_stub_proof_missing",
    "host_candidate_missing", "zone_config_missing", "dry_run_proof_missing", "policy_chain_missing",
    "capture_attempt_blocked", "live_hardware_request_blocked", "raw_media_request_blocked",
    "raw_media_payload_blocked", "base64_media_blocked", "speaker_boundary_blocked",
    "external_authority_blocked", "unknown_capture_authorization_blocked",
]
LedgerStatus = Literal[
    "capture_denial_ledger_valid", "capture_denial_ledger_valid_with_warnings",
    "capture_denial_ledger_blocked_media_payload", "capture_denial_ledger_blocked_external_authority",
    "capture_denial_ledger_invalid", "capture_denial_ledger_failed",
]
FORBIDDEN_NEXT_STEPS = (
    "open_camera_now", "attempt_capture", "enable_live_capture", "store_raw_media", "attach_media_payload",
    "bypass_policy_chain", "bypass_zone_config", "bypass_disabled_capture_boundary", "bypass_dry_run",
    "enable_speaker_output", "enable_external_disclosure",
)
MAP = {
    "capture_authorization_blocked_missing_operator_grant": "missing_operator_grant",
    "capture_authorization_blocked_expired_grant": "expired_operator_grant",
    "capture_authorization_blocked_revoked_grant": "revoked_operator_grant",
    "capture_authorization_blocked_scope_mismatch": "scope_mismatch",
    "capture_authorization_blocked_missing_disabled_capture_proof": "disabled_capture_boundary_missing",
    "capture_authorization_blocked_missing_shell_proof": "local_shell_proof_missing",
    "capture_authorization_blocked_missing_stub_proof": "live_adapter_stub_proof_missing",
    "capture_authorization_blocked_missing_host_candidate": "host_candidate_missing",
    "capture_authorization_blocked_missing_zone_config": "zone_config_missing",
    "capture_authorization_blocked_missing_dry_run_proof": "dry_run_proof_missing",
    "capture_authorization_blocked_missing_policy_chain": "policy_chain_missing",
    "capture_authorization_blocked_raw_media": "raw_media_request_blocked",
    "capture_authorization_blocked_speaker_boundary": "speaker_boundary_blocked",
    "capture_authorization_blocked_external_authority": "external_authority_blocked",
}
NEXT_ACTION = {
    "missing_operator_grant": "renew_operator_grant", "expired_operator_grant": "renew_operator_grant",
    "revoked_operator_grant": "operator_review", "scope_mismatch": "operator_review",
    "disabled_capture_boundary_missing": "operator_review", "local_shell_proof_missing": "operator_review",
    "live_adapter_stub_proof_missing": "operator_review", "host_candidate_missing": "operator_review",
    "zone_config_missing": "bind_zone_config", "dry_run_proof_missing": "rerun_dry_run",
    "policy_chain_missing": "attach_policy_chain_proof", "capture_attempt_blocked": "no_action_allowed",
    "live_hardware_request_blocked": "no_action_allowed", "raw_media_request_blocked": "no_action_allowed",
    "raw_media_payload_blocked": "remove_media_payload", "base64_media_blocked": "remove_media_payload",
    "speaker_boundary_blocked": "operator_review", "external_authority_blocked": "operator_review",
    "unknown_capture_authorization_blocked": "operator_review",
}

@dataclass(frozen=True)
class HouseholdCameraCaptureDenialLedgerPolicy:
    schema_version: str = "household_presence_camera_capture_denial_ledger_policy.v1"
    allow_non_denial_warning: bool = False

@dataclass(frozen=True)
class HouseholdCameraCaptureDenialInput:
    payload: dict[str, Any]

@dataclass(frozen=True)
class HouseholdCameraCaptureDenialRecord:
    record_id: str; request_id: str; source_candidate_id: str | None; zone_config_id: str | None; policy_chain_id: str | None
    authorization_status: str; denial_classification: DenialClassification; denial_reason: str; denying_layer: str; requested_mode: str
    observed_at: str; operator_label: str | None; proof_digests: tuple[str, ...]; safe_next_action: str
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    media_present: bool = False; raw_media_stored: bool = False; external_disclosure_performed: bool = False; speaker_output_performed: bool = False
    digest: str = ""

@dataclass(frozen=True)
class HouseholdCameraCaptureDenialFinding:
    code: str
    message: str

@dataclass(frozen=True)
class HouseholdCameraCaptureDenialLedger:
    records: tuple[HouseholdCameraCaptureDenialRecord, ...]
    digest: str

@dataclass(frozen=True)
class HouseholdCameraCaptureDenialLedgerReport:
    status: LedgerStatus
    summary_counts: dict[str, int]
    findings: tuple[HouseholdCameraCaptureDenialFinding, ...]

@dataclass(frozen=True)
class HouseholdCameraCaptureDenialLedgerResult:
    status: LedgerStatus
    ledger: HouseholdCameraCaptureDenialLedger
    report: HouseholdCameraCaptureDenialLedgerReport
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _dig(v: Any) -> str: return hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()

def build_default_policy() -> HouseholdCameraCaptureDenialLedgerPolicy: return HouseholdCameraCaptureDenialLedgerPolicy()
def validate_policy(policy: HouseholdCameraCaptureDenialLedgerPolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith('.v1'); return {"ok": ok, "status": "household_presence_camera_capture_denial_ledger_policy_valid" if ok else "household_presence_camera_capture_denial_ledger_policy_invalid"}

def _classification(item: Mapping[str, Any]) -> str:
    c = str(item.get("denial_classification", "")).strip()
    if c: return c
    s = str(item.get("status", "")).strip()
    if s in MAP: return MAP[s]
    if "raw_media_payload" in s: return "raw_media_payload_blocked"
    if "base64" in s: return "base64_media_blocked"
    return "unknown_capture_authorization_blocked"

def evaluate_capture_denial_ledger(payload: Mapping[str, Any], policy: HouseholdCameraCaptureDenialLedgerPolicy | None = None) -> HouseholdCameraCaptureDenialLedgerResult:
    _ = policy or build_default_policy()
    events = payload.get("records", payload.get("events", [payload]))
    if not isinstance(events, list): events = [payload]
    records=[]; findings=[]; blocked_external=False; blocked_media=False
    for i,e in enumerate(events):
        if not isinstance(e, Mapping): continue
        media_keys=("raw_media","base64","image","video","audio","screenshot","thumbnail","transcript","raw_media_payload","base64_media")
        if any(k in e and e.get(k) for k in media_keys): blocked_media=True
        cls=cast(DenialClassification, _classification(e))
        auth_status=str(e.get("status","capture_authorization_blocked_unknown"))
        if auth_status in {"capture_authorization_ready_for_dry_run_only","capture_authorization_valid_for_future_review"}:
            findings.append(HouseholdCameraCaptureDenialFinding("not_a_denial","non-denial record rejected")); continue
        if cls=="external_authority_blocked": blocked_external=True
        rid=str(e.get("record_id",f"denial-{i+1:04d}"))
        req=str(e.get("request_id",f"request-{i+1:04d}"))
        base={"rid":rid,"req":req,"c":cls,"s":auth_status}
        rec=HouseholdCameraCaptureDenialRecord(rid,req,e.get("source_candidate_id"),e.get("zone_config_id"),e.get("policy_chain_id"),auth_status,cls,str(e.get("denial_reason",cls)),str(e.get("denying_layer","household_presence_camera_capture_authorization")),str(e.get("requested_mode","capture_attempt")),str(e.get("observed_at",e.get("attempted_at","1970-01-01T00:00:00Z"))),e.get("operator_label"),tuple(sorted(str(x) for x in e.get("proof_digests",[]))),NEXT_ACTION.get(cls,"operator_review"),digest=_dig(base))
        records.append(rec)
    counts: dict[str,int]={}
    for r in records: counts[r.denial_classification]=counts.get(r.denial_classification,0)+1
    digest=_dig([r.digest for r in records])
    ledger_status: LedgerStatus="capture_denial_ledger_valid"
    if blocked_media: ledger_status="capture_denial_ledger_blocked_media_payload"
    elif blocked_external: ledger_status="capture_denial_ledger_blocked_external_authority"
    elif findings: ledger_status="capture_denial_ledger_valid_with_warnings"
    ledger=HouseholdCameraCaptureDenialLedger(tuple(records),digest)
    report=HouseholdCameraCaptureDenialLedgerReport(ledger_status,dict(sorted(counts.items())),tuple(findings))
    return HouseholdCameraCaptureDenialLedgerResult(ledger_status,ledger,report)
