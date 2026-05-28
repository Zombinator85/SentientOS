from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping

ReviewMode = Literal["design_only", "dry_run_only", "future_live_review"]

ReviewStatus = Literal[
    "capture_review_packet_ready_for_operator_review",
    "capture_review_packet_ready_for_dry_run_only",
    "capture_review_packet_valid_with_warnings",
    "capture_review_packet_blocked_missing_authorization",
    "capture_review_packet_blocked_missing_denial_ledger",
    "capture_review_packet_blocked_missing_disabled_capture_proof",
    "capture_review_packet_blocked_missing_shell_proof",
    "capture_review_packet_blocked_missing_stub_proof",
    "capture_review_packet_blocked_missing_host_candidate",
    "capture_review_packet_blocked_missing_zone_config",
    "capture_review_packet_blocked_missing_dry_run_proof",
    "capture_review_packet_blocked_missing_policy_chain",
    "capture_review_packet_blocked_unresolved_denials",
    "capture_review_packet_blocked_scope_mismatch",
    "capture_review_packet_blocked_stale_proof",
    "capture_review_packet_blocked_media_payload",
    "capture_review_packet_blocked_speaker_boundary",
    "capture_review_packet_blocked_external_authority",
    "capture_review_packet_invalid",
    "capture_review_packet_failed",
]

FORBIDDEN_NEXT_STEPS = (
    "open_camera_now",
    "attempt_capture",
    "enable_live_capture",
    "enable_live_recording",
    "store_raw_media",
    "attach_media_payload",
    "bypass_authorization_envelope",
    "bypass_denial_ledger",
    "bypass_policy_chain",
    "bypass_zone_config",
    "bypass_disabled_capture_boundary",
    "bypass_dry_run",
    "enable_speaker_output",
    "enable_external_disclosure",
)


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewPacketPolicy:
    schema_version: str = "household_presence_camera_capture_review_packet_policy.v1"
    allow_first_review_without_denial_ledger: bool = False
    allow_design_only_without_dry_run_proof: bool = True
    max_unresolved_denials: int = 0
    stale_proof_seconds: int = 86400
    stale_proof_mode: Literal["block", "warn"] = "block"


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewProofSet:
    authorization_envelope_digest: str = ""
    denial_ledger_digest: str = ""
    disabled_capture_proof_digest: str = ""
    local_shell_proof_digest: str = ""
    live_adapter_stub_proof_digest: str = ""
    host_candidate_digest: str = ""
    zone_config_id: str = ""
    zone_config_digest: str = ""
    dry_run_proof_digest: str = ""
    readiness_proof_digest: str = ""
    policy_chain_id: str = ""
    policy_chain_digest: str = ""
    operator_grant_id: str | None = None
    source_candidate_id: str = ""
    requested_mode: ReviewMode = "design_only"
    observed_at: str = ""
    reviewed_at: str = ""
    review_after: str = ""
    expires_at: str = ""
    unresolved_denial_count: int = 0
    media_payload_present: bool = False
    base64_media_present: bool = False
    speaker_output_requested: bool = False
    external_disclosure_requested: bool = False
    notes: str = ""


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewInput:
    proof_set: HouseholdCameraCaptureReviewProofSet


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewFinding:
    code: str
    message: str


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewPacket:
    status: ReviewStatus
    digest: str
    review_enables_live_capture: bool = False
    capture_enabled: bool = False
    capture_available: bool = False
    live_hardware_enabled: bool = False
    raw_media_storage_enabled: bool = False
    no_live_capture_performed: bool = True
    speaker_output_enabled: bool = False
    external_disclosure_enabled: bool = False
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewReport:
    status: ReviewStatus
    findings: tuple[HouseholdCameraCaptureReviewFinding, ...]


@dataclass(frozen=True)
class HouseholdCameraCaptureReviewResult:
    status: ReviewStatus
    packet: HouseholdCameraCaptureReviewPacket
    report: HouseholdCameraCaptureReviewReport

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PROOF_SET_FIELDS = frozenset(HouseholdCameraCaptureReviewProofSet.__dataclass_fields__)
_REQUIRED_PROOF_CHECKS: tuple[tuple[str, ReviewStatus], ...] = (
    ("authorization_envelope_digest", "capture_review_packet_blocked_missing_authorization"),
    (
        "disabled_capture_proof_digest",
        "capture_review_packet_blocked_missing_disabled_capture_proof",
    ),
    ("local_shell_proof_digest", "capture_review_packet_blocked_missing_shell_proof"),
    ("live_adapter_stub_proof_digest", "capture_review_packet_blocked_missing_stub_proof"),
    ("host_candidate_digest", "capture_review_packet_blocked_missing_host_candidate"),
    ("zone_config_digest", "capture_review_packet_blocked_missing_zone_config"),
    ("policy_chain_digest", "capture_review_packet_blocked_missing_policy_chain"),
)


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def build_default_policy() -> HouseholdCameraCaptureReviewPacketPolicy:
    return HouseholdCameraCaptureReviewPacketPolicy()


def validate_policy(policy: HouseholdCameraCaptureReviewPacketPolicy) -> dict[str, Any]:
    ok = policy.schema_version.endswith(".v1")
    return {
        "ok": ok,
        "status": "household_presence_camera_capture_review_packet_policy_valid"
        if ok
        else "household_presence_camera_capture_review_packet_policy_invalid",
    }


def _get(payload: Mapping[str, Any]) -> HouseholdCameraCaptureReviewProofSet:
    proof_payload = payload.get("proof_set", payload)
    if not isinstance(proof_payload, Mapping):
        return HouseholdCameraCaptureReviewProofSet()
    kwargs = {key: value for key, value in proof_payload.items() if key in _PROOF_SET_FIELDS}
    return HouseholdCameraCaptureReviewProofSet(**kwargs)


def _result(
    status: ReviewStatus,
    digest_payload: Mapping[str, Any],
    finding: HouseholdCameraCaptureReviewFinding,
) -> HouseholdCameraCaptureReviewResult:
    packet = HouseholdCameraCaptureReviewPacket(status, _digest(digest_payload))
    report = HouseholdCameraCaptureReviewReport(status, (finding,))
    return HouseholdCameraCaptureReviewResult(status, packet, report)


def evaluate_capture_review_packet(
    payload: Mapping[str, Any],
    policy: HouseholdCameraCaptureReviewPacketPolicy | None = None,
) -> HouseholdCameraCaptureReviewResult:
    active_policy = policy or build_default_policy()
    proof_set = _get(payload)
    findings: list[HouseholdCameraCaptureReviewFinding] = []

    for field_name, blocked_status in _REQUIRED_PROOF_CHECKS:
        if not getattr(proof_set, field_name):
            return _result(
                blocked_status,
                {"status": blocked_status, "missing": field_name},
                HouseholdCameraCaptureReviewFinding("missing_required_proof", field_name),
            )

    if (
        not proof_set.denial_ledger_digest
        and not active_policy.allow_first_review_without_denial_ledger
    ):
        status: ReviewStatus = "capture_review_packet_blocked_missing_denial_ledger"
        return _result(
            status,
            {"status": status},
            HouseholdCameraCaptureReviewFinding("missing_denial_ledger", status),
        )

    dry_run_required = not (
        proof_set.requested_mode == "design_only"
        and active_policy.allow_design_only_without_dry_run_proof
    )
    if not proof_set.dry_run_proof_digest and dry_run_required:
        status = "capture_review_packet_blocked_missing_dry_run_proof"
        return _result(
            status,
            {"status": status},
            HouseholdCameraCaptureReviewFinding("missing_dry_run_proof", status),
        )

    if proof_set.unresolved_denial_count > active_policy.max_unresolved_denials:
        status = "capture_review_packet_blocked_unresolved_denials"
        return _result(
            status,
            {"status": status},
            HouseholdCameraCaptureReviewFinding(
                "unresolved_denials", str(proof_set.unresolved_denial_count)
            ),
        )

    if proof_set.media_payload_present or proof_set.base64_media_present:
        status = "capture_review_packet_blocked_media_payload"
        return _result(
            status,
            {"status": status},
            HouseholdCameraCaptureReviewFinding("media_payload", status),
        )

    if proof_set.speaker_output_requested:
        status = "capture_review_packet_blocked_speaker_boundary"
        return _result(
            status,
            {"status": status},
            HouseholdCameraCaptureReviewFinding("speaker_boundary", status),
        )

    if proof_set.external_disclosure_requested:
        status = "capture_review_packet_blocked_external_authority"
        return _result(
            status,
            {"status": status},
            HouseholdCameraCaptureReviewFinding("external_authority", status),
        )

    if (
        proof_set.source_candidate_id
        and proof_set.zone_config_id
        and proof_set.policy_chain_id
        and proof_set.source_candidate_id
        not in proof_set.zone_config_id + proof_set.policy_chain_id
    ):
        status = "capture_review_packet_blocked_scope_mismatch"
        return _result(
            status,
            {"status": status},
            HouseholdCameraCaptureReviewFinding("scope_mismatch", status),
        )

    status = "capture_review_packet_ready_for_operator_review"
    if proof_set.requested_mode == "dry_run_only":
        status = "capture_review_packet_ready_for_dry_run_only"

    if proof_set.reviewed_at and proof_set.expires_at and proof_set.reviewed_at > proof_set.expires_at:
        if active_policy.stale_proof_mode == "block":
            status = "capture_review_packet_blocked_stale_proof"
        else:
            status = "capture_review_packet_valid_with_warnings"
            findings.append(
                HouseholdCameraCaptureReviewFinding("stale_proof", "stale proof warned")
            )

    digest = _digest({"status": status, "proof_set": asdict(proof_set)})
    packet = HouseholdCameraCaptureReviewPacket(status, digest)
    report = HouseholdCameraCaptureReviewReport(status, tuple(findings))
    return HouseholdCameraCaptureReviewResult(status, packet, report)
