from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Mapping

Status = Literal[
    "stub_ready_for_design",
    "stub_ready_for_operator_review",
    "stub_blocked_missing_operator_confirmation",
    "stub_blocked_live_hardware_requested",
    "stub_blocked_missing_host_candidate",
    "stub_blocked_missing_zone_config",
    "stub_blocked_missing_dry_run_proof",
    "stub_blocked_missing_policy_chain",
    "stub_blocked_raw_media",
    "stub_blocked_speaker_boundary",
    "stub_blocked_external_authority",
    "stub_failed",
]

FORBIDDEN_NEXT_STEPS: tuple[str, ...] = (
    "open_camera_now",
    "enable_live_recording",
    "store_raw_media",
    "bypass_policy_chain",
    "bypass_zone_config",
    "bypass_dry_run",
    "enable_speaker_output",
    "enable_external_disclosure",
)

BLOCKED_RECOMMENDATIONS = {"microphone_only", "speaker", "talkback", "unknown", "speaker_talkback"}
REVIEW_RECOMMENDATIONS = {"network_camera_metadata_only", "quest_visor_overlay_only"}

@dataclass(frozen=True)
class HouseholdCameraLiveAdapterStubPolicy:
    schema_version: str = "household_presence_camera_live_adapter_stub_policy.v1"
    allow_live_mode: bool = False
    live_hardware_enabled: bool = False
    no_live_capture_performed: bool = True

@dataclass(frozen=True)
class HouseholdCameraLiveAdapterOperatorConfirmation:
    operator_id: str = ""
    operator_label: str = ""
    confirmed_at: str = ""
    confirmation_scope: str = ""
    stub_only: bool = True
    live_hardware_allowed: bool = False
    dry_run_required: bool = True
    policy_chain_required: bool = True
    zone_config_required: bool = True
    raw_media_allowed: bool = False
    speaker_output_allowed: bool = False
    external_disclosure_allowed: bool = False

@dataclass(frozen=True)
class HouseholdCameraLiveAdapterBinding:
    host_inventory_candidate_id: str = ""
    source_label: str = ""
    source_kind: str = ""
    zone_config_id: str = ""
    policy_chain_id: str = ""
    dry_run_report_digest: str = ""
    dry_run_status: str = ""
    readiness_status: str = ""
    candidate_recommendation: str = ""
    confidence: float = 0.0
    review_after: str = ""
    expires_at: str = ""
    notes: str = ""

@dataclass(frozen=True)
class HouseholdCameraLiveAdapterDryRunProof:
    dry_run_report_digest: str = ""
    dry_run_status: str = ""
    proof_matches_binding: bool = False
    is_stale: bool = False

@dataclass(frozen=True)
class HouseholdCameraLiveAdapterStubRequest:
    operator_confirmation: HouseholdCameraLiveAdapterOperatorConfirmation
    binding: HouseholdCameraLiveAdapterBinding
    dry_run_proof: HouseholdCameraLiveAdapterDryRunProof

@dataclass(frozen=True)
class HouseholdCameraLiveAdapterStubFinding:
    code: str
    detail: str
    blocked: bool

@dataclass(frozen=True)
class HouseholdCameraLiveAdapterStubReport:
    status: Status
    findings: tuple[HouseholdCameraLiveAdapterStubFinding, ...]
    live_hardware_enabled: bool
    no_live_capture_performed: bool
    forbidden_next_steps: tuple[str, ...]
    deterministic_digest: str

@dataclass(frozen=True)
class HouseholdCameraLiveAdapterStubResult:
    report: HouseholdCameraLiveAdapterStubReport
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def build_default_policy() -> HouseholdCameraLiveAdapterStubPolicy: return HouseholdCameraLiveAdapterStubPolicy()

def validate_policy(policy: HouseholdCameraLiveAdapterStubPolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1") and policy.allow_live_mode is False and policy.live_hardware_enabled is False and policy.no_live_capture_performed is True
    return {"ok": ok, "status": "household_presence_camera_live_adapter_stub_policy_valid" if ok else "household_presence_camera_live_adapter_stub_policy_invalid"}

def _load_confirmation(raw: Mapping[str, Any]) -> tuple[list[HouseholdCameraLiveAdapterStubFinding], Status | None]:
    findings: list[HouseholdCameraLiveAdapterStubFinding] = []
    if not raw: return [HouseholdCameraLiveAdapterStubFinding("missing_operator_confirmation", "operator confirmation payload missing", True)], "stub_blocked_missing_operator_confirmation"
    if not (raw.get("operator_id") or raw.get("operator_label")): findings.append(HouseholdCameraLiveAdapterStubFinding("missing_operator_identity", "operator_id or operator_label required", True))
    if not raw.get("confirmed_at"): findings.append(HouseholdCameraLiveAdapterStubFinding("missing_confirmed_at", "confirmed_at required", True))
    if not raw.get("confirmation_scope"): findings.append(HouseholdCameraLiveAdapterStubFinding("missing_confirmation_scope", "confirmation_scope required", True))
    if raw.get("stub_only") is not True: findings.append(HouseholdCameraLiveAdapterStubFinding("stub_only_required", "stub_only must be true", True))
    if raw.get("live_hardware_allowed") is True: return findings + [HouseholdCameraLiveAdapterStubFinding("live_hardware_requested", "live_hardware_allowed must be false", True)], "stub_blocked_live_hardware_requested"
    if raw.get("raw_media_allowed") is True: return findings + [HouseholdCameraLiveAdapterStubFinding("raw_media_requested", "raw_media_allowed must be false", True)], "stub_blocked_raw_media"
    if raw.get("speaker_output_allowed") is True: return findings + [HouseholdCameraLiveAdapterStubFinding("speaker_output_requested", "speaker_output_allowed must be false", True)], "stub_blocked_speaker_boundary"
    if raw.get("external_disclosure_allowed") is True: return findings + [HouseholdCameraLiveAdapterStubFinding("external_disclosure_requested", "external_disclosure_allowed must be false", True)], "stub_blocked_external_authority"
    if raw.get("dry_run_required") is not True: findings.append(HouseholdCameraLiveAdapterStubFinding("dry_run_required", "dry_run_required must be true", True))
    if raw.get("policy_chain_required") is not True: findings.append(HouseholdCameraLiveAdapterStubFinding("policy_chain_required", "policy_chain_required must be true", True))
    if raw.get("zone_config_required") is not True: findings.append(HouseholdCameraLiveAdapterStubFinding("zone_config_required", "zone_config_required must be true", True))
    return findings, None

def evaluate_live_adapter_stub(payload: Mapping[str, Any], policy: HouseholdCameraLiveAdapterStubPolicy | None = None) -> HouseholdCameraLiveAdapterStubResult:
    p = policy or build_default_policy(); findings: list[HouseholdCameraLiveAdapterStubFinding] = []
    confirmation = dict(payload.get("operator_confirmation", {})) if isinstance(payload.get("operator_confirmation"), Mapping) else {}
    binding = dict(payload.get("binding", {})) if isinstance(payload.get("binding"), Mapping) else {}
    proof = dict(payload.get("dry_run_proof", {})) if isinstance(payload.get("dry_run_proof"), Mapping) else {}
    cfindings, forced = _load_confirmation(confirmation); findings.extend(cfindings)
    if forced: status = forced
    elif not binding.get("host_inventory_candidate_id"): status = "stub_blocked_missing_host_candidate"; findings.append(HouseholdCameraLiveAdapterStubFinding("missing_host_inventory_candidate_id", "host inventory candidate binding required", True))
    elif not binding.get("zone_config_id"): status = "stub_blocked_missing_zone_config"; findings.append(HouseholdCameraLiveAdapterStubFinding("missing_zone_config_id", "zone config binding required", True))
    elif not (binding.get("policy_chain_id") or confirmation.get("policy_chain_required") is True): status = "stub_blocked_missing_policy_chain"; findings.append(HouseholdCameraLiveAdapterStubFinding("missing_policy_chain_binding", "policy chain id or explicit policy requirement required", True))
    elif not proof.get("dry_run_report_digest") or not proof.get("dry_run_status"): status = "stub_blocked_missing_dry_run_proof"; findings.append(HouseholdCameraLiveAdapterStubFinding("missing_dry_run_proof", "dry-run proof digest and status required", True))
    elif proof.get("proof_matches_binding") is not True or proof.get("is_stale") is True or proof.get("dry_run_status") in {"dry_run_failed", "dry_run_blocked", "failed", "stale"} or proof.get("dry_run_report_digest") != binding.get("dry_run_report_digest"): status = "stub_blocked_missing_dry_run_proof"; findings.append(HouseholdCameraLiveAdapterStubFinding("invalid_dry_run_proof", "dry-run proof failed/stale/mismatched", True))
    elif str(binding.get("readiness_status", "")).startswith("blocked") or str(binding.get("readiness_status", "")).endswith("failing") or binding.get("readiness_status") in {"failed", "failing"}: status = "stub_failed"; findings.append(HouseholdCameraLiveAdapterStubFinding("readiness_blocked", "readiness status is blocked/failing", True))
    elif str(binding.get("candidate_recommendation", "")).lower() in BLOCKED_RECOMMENDATIONS: status = "stub_failed"; findings.append(HouseholdCameraLiveAdapterStubFinding("candidate_blocked", "candidate recommendation blocked", True))
    elif str(binding.get("candidate_recommendation", "")).lower() in REVIEW_RECOMMENDATIONS: status = "stub_ready_for_operator_review"; findings.append(HouseholdCameraLiveAdapterStubFinding("candidate_requires_review", "candidate remains metadata-only and not live", False))
    else: status = "stub_ready_for_design"
    if any(f.blocked for f in findings) and status in {"stub_ready_for_design", "stub_ready_for_operator_review"}: status = "stub_failed"
    digest_payload = {"status": status, "findings": [asdict(f) for f in findings], "binding": binding, "proof": proof, "policy": asdict(p)}
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True).encode()).hexdigest()
    report = HouseholdCameraLiveAdapterStubReport(status=status, findings=tuple(findings), live_hardware_enabled=False, no_live_capture_performed=True, forbidden_next_steps=FORBIDDEN_NEXT_STEPS, deterministic_digest=digest)
    return HouseholdCameraLiveAdapterStubResult(report)

def load_stub_fixture(path: str) -> dict[str, Any]: return dict(json.loads(Path(path).read_text()))
def dumps_result(result: HouseholdCameraLiveAdapterStubResult) -> str: return json.dumps(result.to_dict(), indent=2, sort_keys=True)
