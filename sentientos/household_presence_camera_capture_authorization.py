from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping

Status = Literal[
    "capture_authorization_valid_for_future_review",
    "capture_authorization_ready_for_dry_run_only",
    "capture_authorization_operator_review_required",
    "capture_authorization_blocked_missing_operator_grant",
    "capture_authorization_blocked_expired_grant",
    "capture_authorization_blocked_revoked_grant",
    "capture_authorization_blocked_scope_mismatch",
    "capture_authorization_blocked_missing_disabled_capture_proof",
    "capture_authorization_blocked_missing_shell_proof",
    "capture_authorization_blocked_missing_stub_proof",
    "capture_authorization_blocked_missing_host_candidate",
    "capture_authorization_blocked_missing_zone_config",
    "capture_authorization_blocked_missing_dry_run_proof",
    "capture_authorization_blocked_missing_policy_chain",
    "capture_authorization_blocked_raw_media",
    "capture_authorization_blocked_speaker_boundary",
    "capture_authorization_blocked_external_authority",
    "capture_authorization_failed",
]
Mode = Literal["design_only", "dry_run_only", "future_live_review", "capture_attempt"]

FORBIDDEN_NEXT_STEPS = (
    "open_camera_now",
    "attempt_capture",
    "enable_live_capture",
    "enable_live_recording",
    "store_raw_media",
    "attach_media_payload",
    "bypass_policy_chain",
    "bypass_zone_config",
    "bypass_disabled_capture_boundary",
    "bypass_dry_run",
    "enable_speaker_output",
    "enable_external_disclosure",
)


@dataclass(frozen=True)
class HouseholdCameraCaptureAuthorizationPolicy:
    schema_version: str = "household_presence_camera_capture_authorization_policy.v1"
    allow_design_only_without_dry_run_proof: bool = True


@dataclass(frozen=True)
class HouseholdCameraCaptureAuthorizationResult:
    status: Status
    findings: tuple[str, ...]
    authorization_enables_live_capture: bool = False
    capture_enabled: bool = False
    capture_available: bool = False
    live_hardware_enabled: bool = False
    raw_media_storage_enabled: bool = False
    no_live_capture_performed: bool = True
    speaker_output_enabled: bool = False
    external_disclosure_enabled: bool = False
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    deterministic_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_default_policy() -> HouseholdCameraCaptureAuthorizationPolicy:
    return HouseholdCameraCaptureAuthorizationPolicy()


def validate_policy(policy: HouseholdCameraCaptureAuthorizationPolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1")
    return {
        "ok": ok,
        "status": (
            "household_presence_camera_capture_authorization_policy_valid"
            if ok
            else "household_presence_camera_capture_authorization_policy_invalid"
        ),
    }


def _has(values: Mapping[str, Any], key: str) -> bool:
    return bool(str(values.get(key, "")).strip())


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def evaluate_capture_authorization(
    payload: Mapping[str, Any],
    policy: HouseholdCameraCaptureAuthorizationPolicy | None = None,
) -> HouseholdCameraCaptureAuthorizationResult:
    resolved_policy = policy or build_default_policy()
    findings: list[str] = []
    grant = (
        dict(payload.get("operator_grant", {}))
        if isinstance(payload.get("operator_grant"), Mapping)
        else {}
    )
    request = (
        dict(payload.get("request", {}))
        if isinstance(payload.get("request"), Mapping)
        else {}
    )
    mode = str(request.get("requested_mode", "design_only"))

    if not grant:
        return HouseholdCameraCaptureAuthorizationResult(
            "capture_authorization_blocked_missing_operator_grant",
            ("missing_operator_grant",),
            deterministic_digest=_digest({"f": ["missing_operator_grant"]}),
        )
    if not _has(grant, "expires_at"):
        findings.append("missing_grant_expiry")
    if str(grant.get("expires_at", "")) <= str(request.get("requested_at", "")):
        return HouseholdCameraCaptureAuthorizationResult(
            "capture_authorization_blocked_expired_grant",
            ("expired_grant",),
            deterministic_digest=_digest({"f": ["expired_grant"]}),
        )
    if _has(grant, "revoked_at"):
        return HouseholdCameraCaptureAuthorizationResult(
            "capture_authorization_blocked_revoked_grant",
            ("revoked_grant",),
            deterministic_digest=_digest({"f": ["revoked_grant"]}),
        )

    grant_rules: tuple[tuple[str, str, Status], ...] = (
        (
            "live_capture_allowed",
            "grant_allows_live_capture",
            "capture_authorization_blocked_scope_mismatch",
        ),
        (
            "raw_media_allowed",
            "grant_allows_raw_media",
            "capture_authorization_blocked_raw_media",
        ),
        (
            "speaker_output_allowed",
            "grant_allows_speaker_output",
            "capture_authorization_blocked_speaker_boundary",
        ),
        (
            "external_disclosure_allowed",
            "grant_allows_external_disclosure",
            "capture_authorization_blocked_external_authority",
        ),
    )
    for grant_key, grant_tag, grant_status in grant_rules:
        if grant.get(grant_key) is True:
            return HouseholdCameraCaptureAuthorizationResult(
                grant_status,
                (grant_tag,),
                deterministic_digest=_digest({"f": [grant_tag]}),
            )

    required_request_fields: tuple[tuple[str, Status, str], ...] = (
        (
            "disabled_capture_proof_digest",
            "capture_authorization_blocked_missing_disabled_capture_proof",
            "missing_disabled_capture_proof",
        ),
        (
            "local_shell_proof_digest",
            "capture_authorization_blocked_missing_shell_proof",
            "missing_shell_proof",
        ),
        (
            "live_adapter_stub_proof_digest",
            "capture_authorization_blocked_missing_stub_proof",
            "missing_stub_proof",
        ),
        (
            "host_inventory_candidate_digest",
            "capture_authorization_blocked_missing_host_candidate",
            "missing_host_candidate",
        ),
        (
            "zone_config_id",
            "capture_authorization_blocked_missing_zone_config",
            "missing_zone_config",
        ),
        (
            "policy_chain_id",
            "capture_authorization_blocked_missing_policy_chain",
            "missing_policy_chain",
        ),
    )
    for request_key, missing_field_status, missing_field_tag in required_request_fields:
        if not _has(request, request_key):
            return HouseholdCameraCaptureAuthorizationResult(
                missing_field_status,
                (missing_field_tag,),
                deterministic_digest=_digest({"f": [missing_field_tag]}),
            )

    if mode != "design_only" or not resolved_policy.allow_design_only_without_dry_run_proof:
        if not _has(request, "dry_run_proof_digest"):
            return HouseholdCameraCaptureAuthorizationResult(
                "capture_authorization_blocked_missing_dry_run_proof",
                ("missing_dry_run_proof",),
                deterministic_digest=_digest({"f": ["missing_dry_run_proof"]}),
            )

    if any(
        bool(request.get(key, False))
        for key in (
            "capture_requested",
            "live_hardware_requested",
            "raw_media_requested",
            "raw_media_payload_present",
            "base64_media_present",
        )
    ):
        return HouseholdCameraCaptureAuthorizationResult(
            "capture_authorization_blocked_raw_media",
            ("raw_or_capture_requested",),
            deterministic_digest=_digest({"f": ["raw_or_capture_requested"]}),
        )
    if bool(request.get("speaker_output_requested", False)):
        return HouseholdCameraCaptureAuthorizationResult(
            "capture_authorization_blocked_speaker_boundary",
            ("speaker_output_requested",),
            deterministic_digest=_digest({"f": ["speaker_output_requested"]}),
        )
    if bool(request.get("external_disclosure_requested", False)):
        return HouseholdCameraCaptureAuthorizationResult(
            "capture_authorization_blocked_external_authority",
            ("external_disclosure_requested",),
            deterministic_digest=_digest({"f": ["external_disclosure_requested"]}),
        )
    if mode == "capture_attempt":
        return HouseholdCameraCaptureAuthorizationResult(
            "capture_authorization_blocked_scope_mismatch",
            ("capture_attempt_blocked",),
            deterministic_digest=_digest({"f": ["capture_attempt_blocked"]}),
        )

    final_status: Status = (
        "capture_authorization_ready_for_dry_run_only"
        if mode in {"design_only", "dry_run_only"}
        else "capture_authorization_operator_review_required"
    )
    return HouseholdCameraCaptureAuthorizationResult(
        final_status,
        tuple(findings),
        deterministic_digest=_digest(
            {"status": final_status, "f": findings, "mode": mode}
        ),
    )
