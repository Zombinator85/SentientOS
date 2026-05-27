from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Mapping

Status = Literal[
    "disabled_capture_ready_for_design",
    "disabled_capture_ready_for_dry_run",
    "disabled_capture_operator_review_required",
    "disabled_capture_blocked_capture_requested",
    "disabled_capture_blocked_live_hardware_requested",
    "disabled_capture_blocked_raw_media_requested",
    "disabled_capture_blocked_missing_shell_proof",
    "disabled_capture_blocked_missing_stub_proof",
    "disabled_capture_blocked_missing_policy_chain",
    "disabled_capture_blocked_missing_zone_config",
    "disabled_capture_blocked_missing_dry_run_proof",
    "disabled_capture_blocked_speaker_boundary",
    "disabled_capture_blocked_external_authority",
    "disabled_capture_failed",
]
Mode = Literal["design_only", "dry_run_only", "disabled_capture_boundary", "capture_attempt", "future_live_candidate"]

FORBIDDEN_NEXT_STEPS = (
    "open_camera_now", "attempt_capture", "enable_live_capture", "enable_live_recording", "store_raw_media", "attach_media_payload",
    "bypass_policy_chain", "bypass_zone_config", "bypass_dry_run", "enable_speaker_output", "enable_external_disclosure",
)

@dataclass(frozen=True)
class HouseholdCameraDisabledCapturePolicy:
    schema_version: str = "household_presence_camera_disabled_capture_adapter_policy.v1"
    allow_design_only_without_dry_run_proof: bool = True
    policy_chain_required: bool = True

@dataclass(frozen=True)
class HouseholdCameraDisabledCaptureOperatorConfirmation:
    operator_id: str = ""
    operator_label: str = ""
    confirmed_at: str = ""
    confirmation_scope: str = ""

@dataclass(frozen=True)
class HouseholdCameraDisabledCaptureRequest:
    request_id: str
    requested_mode: Mode
    capture_attempted: bool = False
    capture_requested: bool = False
    live_hardware_requested: bool = False
    raw_media_requested: bool = False
    raw_media_payload_present: bool = False
    base64_media_present: bool = False
    speaker_output_requested: bool = False
    external_disclosure_requested: bool = False
    shell_proof_digest: str = ""
    stub_proof_digest: str = ""
    dry_run_proof_digest: str = ""
    zone_config_id: str = ""
    policy_chain_id: str = ""
    confidence: float = 0.0
    notes: tuple[str, ...] = ()

@dataclass(frozen=True)
class HouseholdCameraDisabledCaptureBinding:
    capture_enabled: bool = False
    capture_available: bool = False
    live_hardware_enabled: bool = False
    raw_media_storage_enabled: bool = False
    no_live_capture_performed: bool = True
    speaker_output_enabled: bool = False
    external_disclosure_enabled: bool = False

@dataclass(frozen=True)
class HouseholdCameraDisabledCaptureAttempt:
    request_id: str
    attempted: bool

@dataclass(frozen=True)
class HouseholdCameraDisabledCaptureFinding:
    code: str
    blocked: bool
    details: str

@dataclass(frozen=True)
class HouseholdCameraDisabledCaptureReport:
    status: Status
    binding: HouseholdCameraDisabledCaptureBinding
    findings: tuple[HouseholdCameraDisabledCaptureFinding, ...]
    forbidden_next_steps: tuple[str, ...]
    deterministic_digest: str

@dataclass(frozen=True)
class HouseholdCameraDisabledCaptureResult:
    request: dict[str, Any]
    report: HouseholdCameraDisabledCaptureReport
    def to_dict(self) -> dict[str, Any]: return {"request": self.request, "report": asdict(self.report)}


def build_default_policy() -> HouseholdCameraDisabledCapturePolicy: return HouseholdCameraDisabledCapturePolicy()
def validate_policy(policy: HouseholdCameraDisabledCapturePolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1")
    return {"ok": ok, "status": "household_presence_camera_disabled_capture_adapter_policy_valid" if ok else "household_presence_camera_disabled_capture_adapter_policy_invalid"}

def _blocked(status: Status, code: str, details: str, request: dict[str, Any]) -> HouseholdCameraDisabledCaptureResult:
    rep = HouseholdCameraDisabledCaptureReport(status, HouseholdCameraDisabledCaptureBinding(), (HouseholdCameraDisabledCaptureFinding(code, True, details),), FORBIDDEN_NEXT_STEPS, hashlib.sha256(json.dumps({"status": status, "request": request, "code": code}, sort_keys=True).encode()).hexdigest())
    return HouseholdCameraDisabledCaptureResult(request=request, report=rep)

def evaluate_disabled_capture(payload: Mapping[str, Any], policy: HouseholdCameraDisabledCapturePolicy | None = None) -> HouseholdCameraDisabledCaptureResult:
    p = policy or build_default_policy()
    req = dict(payload)
    mode = str(req.get("requested_mode", "design_only"))
    checks = [
        (bool(req.get("capture_attempted")), "disabled_capture_blocked_capture_requested", "capture_attempted"),
        (bool(req.get("capture_requested")), "disabled_capture_blocked_capture_requested", "capture_requested"),
        (bool(req.get("live_hardware_requested")), "disabled_capture_blocked_live_hardware_requested", "live_hardware_requested"),
        (bool(req.get("raw_media_requested")), "disabled_capture_blocked_raw_media_requested", "raw_media_requested"),
        (bool(req.get("raw_media_payload_present")) or bool(req.get("base64_media_present")), "disabled_capture_blocked_raw_media_requested", "media_payload_present"),
        (bool(req.get("speaker_output_requested")), "disabled_capture_blocked_speaker_boundary", "speaker_output_requested"),
        (bool(req.get("external_disclosure_requested")), "disabled_capture_blocked_external_authority", "external_disclosure_requested"),
    ]
    for cond, st, detail in checks:
        if cond:
            return _blocked(st, detail, detail, req)  # type: ignore[arg-type]
    if not req.get("shell_proof_digest"):
        return _blocked("disabled_capture_blocked_missing_shell_proof", "missing_shell_proof", "shell proof required", req)
    if not req.get("stub_proof_digest"):
        return _blocked("disabled_capture_blocked_missing_stub_proof", "missing_stub_proof", "stub proof required", req)
    if p.policy_chain_required and not req.get("policy_chain_id"):
        return _blocked("disabled_capture_blocked_missing_policy_chain", "missing_policy_chain", "policy chain id required", req)
    if not req.get("zone_config_id"):
        return _blocked("disabled_capture_blocked_missing_zone_config", "missing_zone_config", "zone config id required", req)
    if mode != "design_only" and not req.get("dry_run_proof_digest"):
        return _blocked("disabled_capture_blocked_missing_dry_run_proof", "missing_dry_run_proof", "dry run proof required", req)
    if mode == "design_only" and (not req.get("dry_run_proof_digest")) and (not p.allow_design_only_without_dry_run_proof):
        return _blocked("disabled_capture_blocked_missing_dry_run_proof", "missing_dry_run_proof", "dry run proof required", req)
    if mode == "dry_run_only": status: Status = "disabled_capture_ready_for_dry_run"
    elif mode in {"disabled_capture_boundary", "future_live_candidate"}: status = "disabled_capture_operator_review_required"
    else: status = "disabled_capture_ready_for_design"
    findings = (HouseholdCameraDisabledCaptureFinding("capture_disabled", False, "capture remains unavailable"),)
    rep = HouseholdCameraDisabledCaptureReport(status, HouseholdCameraDisabledCaptureBinding(), findings, FORBIDDEN_NEXT_STEPS, hashlib.sha256(json.dumps({"status": status, "request": req, "policy": asdict(p)}, sort_keys=True).encode()).hexdigest())
    return HouseholdCameraDisabledCaptureResult(request=req, report=rep)

def load_fixture(path: str) -> dict[str, Any]: return dict(json.loads(Path(path).read_text()))
def dumps_result(result: HouseholdCameraDisabledCaptureResult) -> str: return json.dumps(result.to_dict(), indent=2, sort_keys=True)
