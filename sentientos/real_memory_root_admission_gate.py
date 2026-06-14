"""Deterministic metadata-only real memory-root admission gate.

The gate consumes supplied final live memory commit review evidence and
explicit real memory root admission gate candidates to decide whether a later
Real Memory Root Admission Packet metadata rung may be considered. It never writes, deletes, purges, indexes,
persists, applies, merges, completes tombs, assembles prompts, retrieves live
context, executes actions, discloses externally, touches real memory roots, or
grants truth, policy, consent, or authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import PurePath
from typing import Any, Literal, Mapping, Sequence

RealRootAdmissionStatus = Literal[
    "real_memory_root_admission_gate_ready",
    "real_memory_root_admission_gate_ready_with_warnings",
    "real_memory_root_admission_gate_deferred_for_operator_review",
    "real_memory_root_admission_gate_rejected",
    "real_memory_root_admission_gate_blocked",
    "real_memory_root_admission_gate_noop",
    "real_memory_root_admission_gate_invalid",
    "real_memory_root_admission_gate_failed",
]

RealRootAdmissionDecision = Literal[
    "real_memory_root_admission_gate_ready_for_later_real_memory_root_admission_packet",
    "real_memory_root_admission_gate_ready_with_warnings",
    "real_memory_root_admission_gate_deferred_for_operator_review",
    "real_memory_root_admission_gate_rejected",
    "real_memory_root_admission_gate_blocked",
    "real_memory_root_admission_gate_noop",
]

REAL_ROOT_ADMISSION_CANDIDATE_TYPES = frozenset({
    "ai_capsule_real_memory_root_admission_gate_candidate",
    "human_summary_real_memory_root_admission_gate_candidate",
    "dual_capsule_real_memory_root_admission_gate_candidate",
    "protect_receipt_real_memory_root_admission_gate_candidate",
    "merge_receipt_real_memory_root_admission_gate_candidate",
    "tomb_archive_real_memory_root_admission_gate_candidate",
    "tomb_deferred_real_memory_root_admission_gate_candidate",
    "operator_review_real_memory_root_admission_gate_candidate",
    "noop_real_memory_root_admission_gate_candidate",
    "mixed_real_memory_root_admission_gate_candidate",
})

READY_SANDBOX_DECISIONS = frozenset({
    "final_live_memory_commit_review_gate_ready_for_later_real_memory_root_admission_gate",
    "final_live_memory_commit_review_gate_ready_with_warnings",
    "final_live_memory_commit_review_gate_deferred_for_operator_review",
    "final_live_memory_commit_review_gate_rejected",
    "final_live_memory_commit_review_gate_noop",
    "sandbox_commit_artifacts_ready",
    "sandbox_commit_artifacts_ready_with_warnings",
    "sandbox_commit_deferred_for_operator_review",
    "sandbox_commit_rejected",
    "sandbox_commit_noop",
})

INVARIANTS: dict[str, bool] = {
    "real_memory_root_admission_gate_is_not_memory_write": True,
    "real_memory_root_admission_gate_is_not_memory_deletion": True,
    "real_memory_root_admission_gate_is_not_memory_purge": True,
    "real_memory_root_admission_gate_is_not_index_mutation": True,
    "real_memory_root_admission_gate_is_not_capsule_persistence": True,
    "real_memory_root_admission_gate_is_not_prompt_assembly": True,
    "real_memory_root_admission_gate_is_not_execution": True,
    "real_memory_root_admission_gate_is_not_live_commit": True,
    "real_memory_root_admission_gate_is_not_truth": True,
    "real_memory_root_admission_gate_is_not_policy": True,
    "real_memory_root_admission_gate_is_not_authority": True,
    "real_memory_root_admission_gate_is_not_consent": True,
    "real_memory_root_admission_gate_does_not_execute_action": True,
    "real_memory_root_admission_gate_does_not_disclose_externally": True,
    "real_memory_root_access_enabled": False,
    "live_memory_write_enabled": False,
    "live_memory_deletion_enabled": False,
    "live_memory_purge_enabled": False,
    "live_index_mutation_enabled": False,
    "prompt_materialization_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
    "future_real_memory_root_admission_packet_required": True,
    "final_operator_review_required": True,
}

SAFE_NEXT_ACTIONS = (
    "no_action_allowed",
    "inspect_real_memory_root_admission_gate_metadata",
    "operator_review_required",
    "prepare_later_real_memory_root_admission_packet",
    "prepare_final_operator_review_later",
    "rerun_with_ready_sandbox_commit_packet",
    "rerun_with_matching_sandbox_commit_digest",
    "rerun_with_matching_sandbox_commit_decision",
    "rerun_with_sandbox_receipt_manifest_digest",
    "rerun_with_sandbox_rollback_manifest_digest",
    "rerun_with_sandbox_artifact_plan",
    "rerun_with_scope_alignment",
    "sustain_default_deny",
)

FORBIDDEN_NEXT_STEPS = (
    "write_live_memory_now",
    "delete_live_memory_now",
    "purge_live_memory_now",
    "mutate_vector_index",
    "mutate_live_index",
    "persist_capsule_now",
    "persist_summary_now",
    "apply_protection_now",
    "apply_merge_now",
    "complete_tomb_now",
    "run_real_live_commit_adapter_now",
    "treat_sandbox_commit_as_real_commit",
    "treat_sandbox_receipt_as_live_receipt",
    "treat_sandbox_rollback_as_applied_rollback",
    "touch_real_memory_root",
    "open_real_memory_path_for_write",
    "chmod_real_memory_path",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "infer_truth_from_admission",
    "infer_authority_from_admission",
    "infer_consent_from_admission",
    "convert_admission_to_policy",
    "convert_admission_to_action",
    "bypass_sandbox_commit_adapter",
    "bypass_real_memory_root_admission_gate",
    "bypass_safety_interlock",
    "bypass_execution_gate",
    "bypass_operator_approval_packet",
    "bypass_commit_plan_packet",
    "bypass_live_boundary_admission",
    "bypass_governed_writer_adapter",
    "bypass_tomb_verifier",
    "bypass_receipt_gate",
    "bypass_distillation_contract",
    "bypass_operator_review",
    "enable_external_disclosure",
)

RAW_PAYLOAD_KEYS = frozenset({"raw_payload", "private_payload", "secret", "secrets", "media", "audio", "video", "image", "prompt", "prompt_payload", "provider_prompt", "private_memory"})
RAW_PAYLOAD_PATTERN = re.compile(r"(begin private|secret:|data:(?:image|audio|video)|provider prompt text|raw/private/media/secret/provider-prompt|private memory)", re.I)
REAL_ROOT_MARKERS = ("live_memory", "memory/live", "real_memory", "memory_root", "cathedral_memory")
DEVICE_PREFIXES = ("/dev/", "\\\\.\\", "//?/", "\\\\?\\")
OPERATOR_HOME_PREFIXES = ("~/", "$home", "%userprofile%", "/home/", "/users/", "c:/users/", "c:\\users\\")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return tuple(str(item) for item in value)
    return ()


def _has_raw_payload(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(key).lower() in RAW_PAYLOAD_KEYS or _has_raw_payload(item) for key, item in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return any(_has_raw_payload(item) for item in value)
    if isinstance(value, str):
        return bool(RAW_PAYLOAD_PATTERN.search(value))
    return False


def _flag(mapping: Mapping[str, Any], *names: str) -> bool:
    return any(mapping.get(name) is True for name in names)


@dataclass(frozen=True)
class RealMemoryRootAdmissionPolicy:
    schema_version: str = "real-memory-root-admission-gate/v1"
    default_posture: str = "deny"
    require_sandbox_commit_ready: bool = True
    require_matching_sandbox_commit_digest: bool = True
    require_matching_sandbox_commit_decision: bool = True
    require_receipt_manifest_digest_for_non_noop: bool = True
    require_rollback_manifest_digest_for_non_noop: bool = True
    require_artifact_plan_for_non_noop: bool = True
    require_scope_alignment: bool = True
    allow_inert_review_path_metadata: bool = False
    allow_mixed_scope_diagnostic_packet: bool = False
    block_real_memory_root_access_claims: bool = True
    block_live_mutation_claims: bool = True
    block_prompt_materialization: bool = True
    block_live_context_retrieval: bool = True
    block_action_execution: bool = True
    block_external_disclosure: bool = True
    block_authority_smuggling: bool = True
    block_consent_smuggling: bool = True
    block_policy_smuggling: bool = True
    block_truth_smuggling: bool = True
    block_raw_payload_leakage: bool = True


@dataclass(frozen=True)
class RealRootAdmissionFinding:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealRootAdmissionCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    claimed_sandbox_commit_digest: str
    claimed_sandbox_commit_decision: str
    claimed_sandbox_receipt_manifest_digest: str
    claimed_sandbox_rollback_manifest_digest: str
    operator_scope_keys: tuple[str, ...]
    real_root_path_metadata: Mapping[str, Any]
    sandbox_artifact_plan: Mapping[str, Any]
    admission_claims: Mapping[str, Any]
    metadata: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RealRootAdmissionCandidate | None":
        candidate_type = str(raw.get("candidate_type") or "")
        candidate_id = str(raw.get("candidate_id") or "")
        record_id = str(raw.get("record_id") or "")
        if not candidate_id or not record_id or candidate_type not in REAL_ROOT_ADMISSION_CANDIDATE_TYPES:
            return None
        return cls(
            candidate_id=candidate_id,
            record_id=record_id,
            candidate_type=candidate_type,
            claimed_sandbox_commit_digest=str(raw.get("claimed_sandbox_commit_digest") or raw.get("sandbox_commit_digest") or ""),
            claimed_sandbox_commit_decision=str(raw.get("claimed_sandbox_commit_decision") or raw.get("sandbox_commit_decision") or ""),
            claimed_sandbox_receipt_manifest_digest=str(raw.get("claimed_sandbox_receipt_manifest_digest") or raw.get("sandbox_receipt_manifest_digest") or ""),
            claimed_sandbox_rollback_manifest_digest=str(raw.get("claimed_sandbox_rollback_manifest_digest") or raw.get("sandbox_rollback_manifest_digest") or ""),
            operator_scope_keys=_as_tuple(raw.get("operator_scope_keys")),
            real_root_path_metadata=_as_mapping(raw.get("real_root_path_metadata") or raw.get("path_metadata")),
            sandbox_artifact_plan=_as_mapping(raw.get("sandbox_artifact_plan")),
            admission_claims=_as_mapping(raw.get("admission_claims") or raw.get("claims")),
            metadata=_as_mapping(raw.get("metadata")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RealRootAdmissionRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    admission_decision: RealRootAdmissionDecision
    sandbox_commit_decision: str
    sandbox_commit_digest: str
    sandbox_record_digest: str
    sandbox_receipt_manifest_digest: str
    sandbox_rollback_manifest_digest: str
    operator_scope_keys: tuple[str, ...]
    sandbox_scope_keys: tuple[str, ...]
    real_root_path_metadata: Mapping[str, Any]
    sandbox_artifact_plan: Mapping[str, Any]
    safe_next_actions: tuple[str, ...]
    future_adapter_consideration_record: Mapping[str, Any]
    admission_future_consideration_only: bool = True
    sandbox_commit_is_real_commit: bool = False
    sandbox_receipt_is_live_receipt: bool = False
    sandbox_rollback_is_applied_rollback: bool = False
    real_memory_root_access_performed: bool = False
    live_memory_write_claimed: bool = False
    live_memory_delete_claimed: bool = False
    live_memory_purge_claimed: bool = False
    live_index_mutation_claimed: bool = False
    prompt_assembly_claimed: bool = False
    live_context_retrieval_claimed: bool = False
    action_execution_claimed: bool = False
    external_disclosure_claimed: bool = False
    authority_claimed: bool = False
    consent_claimed: bool = False
    policy_claimed: bool = False
    truth_claimed: bool = False
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "RealRootAdmissionRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class RealRootAdmissionPacket:
    schema_version: str
    records: tuple[RealRootAdmissionRecord, ...]
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""
    real_memory_root_admission_gate_is_not_memory_write: bool = True
    real_memory_root_admission_gate_is_not_memory_deletion: bool = True
    real_memory_root_admission_gate_is_not_memory_purge: bool = True
    real_memory_root_admission_gate_is_not_index_mutation: bool = True
    real_memory_root_admission_gate_is_not_capsule_persistence: bool = True
    real_memory_root_admission_gate_is_not_prompt_assembly: bool = True
    real_memory_root_admission_gate_is_not_execution: bool = True
    real_memory_root_admission_gate_is_not_live_commit: bool = True
    real_memory_root_admission_gate_is_not_truth: bool = True
    real_memory_root_admission_gate_is_not_policy: bool = True
    real_memory_root_admission_gate_is_not_authority: bool = True
    real_memory_root_admission_gate_is_not_consent: bool = True
    real_memory_root_admission_gate_does_not_execute_action: bool = True
    real_memory_root_admission_gate_does_not_disclose_externally: bool = True
    real_memory_root_access_enabled: bool = False
    live_memory_write_enabled: bool = False
    live_memory_deletion_enabled: bool = False
    live_memory_purge_enabled: bool = False
    live_index_mutation_enabled: bool = False
    prompt_materialization_enabled: bool = False
    external_disclosure_enabled: bool = False
    remote_service_enabled: bool = False
    real_memory_root_admission_gate_passed: bool = False
    real_memory_root_admission_enabled: bool = False
    real_memory_root_admission_packet_created: bool = False
    real_memory_root_admitted: bool = False
    live_commit_execution_enabled: bool = False
    live_commit_applied: bool = False
    live_adapter_admitted: bool = False
    executor_invocation_authority_granted: bool = False
    executor_activation_authority_granted: bool = False
    executor_release_authority_granted: bool = False
    executor_permit_authority_granted: bool = False
    executor_authorization_granted: bool = False
    runtime_enablement_authority_granted: bool = False
    lock_acquisition_authority_granted: bool = False
    lockfile_creation_authority_granted: bool = False
    future_real_memory_root_admission_packet_required: bool = True
    final_operator_review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        return data

    def with_digest(self) -> "RealRootAdmissionPacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class RealRootAdmissionReport:
    status: RealRootAdmissionStatus
    findings: tuple[RealRootAdmissionFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [finding.to_dict() for finding in self.findings], "summary_counts": dict(sorted(self.summary_counts.items())), "digest": self.digest}


@dataclass(frozen=True)
class RealRootAdmissionResult:
    status: RealRootAdmissionStatus
    packet: RealRootAdmissionPacket | None
    report: RealRootAdmissionReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> RealMemoryRootAdmissionPolicy:
    return RealMemoryRootAdmissionPolicy()


def validate_policy(policy: RealMemoryRootAdmissionPolicy | Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = asdict(policy) if isinstance(policy, RealMemoryRootAdmissionPolicy) else dict(policy or asdict(build_default_policy()))
    findings: list[dict[str, str]] = []
    if raw.get("default_posture") != "deny":
        findings.append({"severity": "error", "code": "default_posture_not_deny", "message": "real-root admission must default deny"})
    for key, expected in INVARIANTS.items():
        if raw.get(key, expected) != expected:
            findings.append({"severity": "error", "code": f"invariant_{key}_changed", "message": f"{key} must remain {expected}"})
    status = "invalid" if findings else "valid"
    return {"status": status, "findings": findings, "policy": raw, "digest": _digest({"status": status, "findings": findings, "policy": raw})}


def _policy_from_payload(payload: Mapping[str, Any], policy: RealMemoryRootAdmissionPolicy | None) -> RealMemoryRootAdmissionPolicy:
    if policy is not None:
        return policy
    raw = _as_mapping(payload.get("policy"))
    if raw:
        allowed = set(RealMemoryRootAdmissionPolicy.__dataclass_fields__)
        return RealMemoryRootAdmissionPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def _candidate_payloads(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("real_memory_root_admission_gate_candidates", payload.get("real_memory_root_admission_gate_candidate", payload.get("real_root_admission_candidates", payload.get("real_root_admission_candidate", payload.get("candidates", ())))))
    if isinstance(raw, Mapping):
        return (_as_mapping(raw),)
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray, str)):
        return tuple(_as_mapping(item) for item in raw)
    return ()


def _records(packet: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = packet.get("records", ())
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray, str)):
        return tuple(_as_mapping(item) for item in raw)
    return ()


def _blocked(code: str, findings: Sequence[RealRootAdmissionFinding] | None = None) -> RealRootAdmissionResult:
    finding_list = tuple(findings or (RealRootAdmissionFinding("error", code, code.replace("_", " ")),))
    report = RealRootAdmissionReport("real_memory_root_admission_gate_blocked", finding_list, {"candidate_count": 0, "error_count": sum(1 for f in finding_list if f.severity == "error")})
    report = replace(report, digest=_digest(report.to_dict()))
    return RealRootAdmissionResult("real_memory_root_admission_gate_blocked", None, report, _digest({"packet": None, "report": report.to_dict()}))


def _path_metadata_blocker(metadata: Mapping[str, Any], policy: RealMemoryRootAdmissionPolicy) -> str | None:
    if not metadata:
        return "missing_real_root_path_metadata"
    inert = metadata.get("inert_metadata_only") is True
    review_allowed = metadata.get("explicitly_allowed_for_review") is True and policy.allow_inert_review_path_metadata
    value = str(metadata.get("path") or metadata.get("root") or metadata.get("display_path") or "")
    lower = value.replace("\\", "/").lower()
    if metadata.get("access_requested") is True or metadata.get("open_for_write_requested") is True or metadata.get("chmod_requested") is True:
        return "real_memory_root_access_claim"
    if metadata.get("symlink_risk") is True or metadata.get("device_path") is True:
        return "unsafe_real_root_path_metadata"
    if not value:
        return "missing_real_root_path_metadata"
    if not inert:
        return "real_root_path_metadata_not_inert"
    if ".." in PurePath(lower).parts or "../" in lower or "..\\" in value:
        return "path_traversal"
    unsafe = lower.startswith(DEVICE_PREFIXES) or lower.startswith(OPERATOR_HOME_PREFIXES) or any(marker in lower for marker in REAL_ROOT_MARKERS) or value.startswith(("/", "~")) or re.match(r"^[a-zA-Z]:[\\/]", value) is not None
    if unsafe and not review_allowed:
        return "unsafe_real_root_path_metadata"
    if unsafe and review_allowed:
        return None
    if metadata.get("ambiguous") is True or metadata.get("absolute") is True:
        return "unsafe_real_root_path_metadata"
    return None


def _claims_blocker(candidate: RealRootAdmissionCandidate, policy: RealMemoryRootAdmissionPolicy) -> str | None:
    claims = candidate.admission_claims
    metadata = candidate.metadata
    all_data = {"claims": claims, "metadata": metadata, "real_root_path_metadata": candidate.real_root_path_metadata, "sandbox_artifact_plan": candidate.sandbox_artifact_plan}
    if policy.block_raw_payload_leakage and _has_raw_payload(all_data):
        return "raw_payload_leak"
    if policy.block_real_memory_root_access_claims and (_flag(claims, "real_memory_root_access", "touches_real_memory_root", "opens_real_memory_path", "chmod_real_memory_path") or metadata.get("real_memory_root_access_claimed") is True):
        return "real_memory_root_access_claim"
    if policy.block_live_mutation_claims and (_flag(claims, "live_write", "writes_live_memory", "real_memory_write") or metadata.get("live_write_claimed") is True):
        return "live_write_claim"
    if policy.block_live_mutation_claims and (_flag(claims, "live_delete", "deletes_live_memory") or metadata.get("live_delete_claimed") is True):
        return "live_delete_claim"
    if policy.block_live_mutation_claims and (_flag(claims, "live_purge", "purges_live_memory") or metadata.get("live_purge_claimed") is True):
        return "live_purge_claim"
    if policy.block_live_mutation_claims and (_flag(claims, "index_mutation", "mutates_index", "mutates_live_index") or metadata.get("index_mutation_claimed") is True):
        return "index_mutation_claim"
    if _flag(claims, "sandbox_commit_is_real_commit", "convert_sandbox_commit_to_live_commit") or metadata.get("sandbox_commit_is_real_commit") is True:
        return "sandbox_commit_conversion_claim"
    if _flag(claims, "sandbox_receipt_is_live_receipt") or metadata.get("sandbox_receipt_is_live_receipt") is True:
        return "sandbox_receipt_conversion_claim"
    if _flag(claims, "sandbox_rollback_is_applied_rollback") or metadata.get("sandbox_rollback_is_applied_rollback") is True:
        return "sandbox_rollback_conversion_claim"
    if policy.block_prompt_materialization and (_flag(claims, "prompt_materialization", "prompt_assembly", "assembles_prompt") or metadata.get("prompt_materialization_requested") is True):
        return "prompt_materialization"
    if policy.block_live_context_retrieval and (_flag(claims, "live_context_retrieval", "retrieves_live_context") or metadata.get("live_context_retrieval_requested") is True):
        return "live_context_retrieval"
    if policy.block_action_execution and (_flag(claims, "action_execution", "executes_action", "action_ingress") or metadata.get("action_execution_requested") is True):
        return "action_execution"
    if policy.block_external_disclosure and (_flag(claims, "external_disclosure", "discloses_externally", "remote_service") or metadata.get("external_disclosure_requested") is True):
        return "external_disclosure"
    if policy.block_authority_smuggling and (_flag(claims, "authority", "grants_authority") or metadata.get("authority_claimed") is True):
        return "authority_smuggling"
    if policy.block_consent_smuggling and (_flag(claims, "consent") or metadata.get("consent_claimed") is True):
        return "consent_smuggling"
    if policy.block_policy_smuggling and (_flag(claims, "policy") or metadata.get("policy_claimed") is True):
        return "policy_smuggling"
    if policy.block_truth_smuggling and (_flag(claims, "truth") or metadata.get("truth_claimed") is True):
        return "truth_smuggling"
    return _path_metadata_blocker(candidate.real_root_path_metadata, policy)


def _decision_for(candidate: RealRootAdmissionCandidate, sandbox_decision: str, warning: bool) -> RealRootAdmissionDecision:
    if candidate.candidate_type == "noop_real_memory_root_admission_gate_candidate" or sandbox_decision == "final_live_memory_commit_review_gate_noop":
        return "real_memory_root_admission_gate_noop"
    if candidate.candidate_type == "operator_review_real_memory_root_admission_gate_candidate" or sandbox_decision == "final_live_memory_commit_review_gate_deferred_for_operator_review" or candidate.metadata.get("operator_review_requested") is True:
        return "real_memory_root_admission_gate_deferred_for_operator_review"
    if sandbox_decision == "final_live_memory_commit_review_gate_rejected" or candidate.metadata.get("rejected") is True:
        return "real_memory_root_admission_gate_rejected"
    if warning or sandbox_decision.endswith("with_warnings"):
        return "real_memory_root_admission_gate_ready_with_warnings"
    return "real_memory_root_admission_gate_ready_for_later_real_memory_root_admission_packet"


def _safe_actions(decision: str) -> tuple[str, ...]:
    if decision == "real_memory_root_admission_gate_noop":
        return ("no_action_allowed", "inspect_real_memory_root_admission_gate_metadata", "sustain_default_deny")
    if decision == "real_memory_root_admission_gate_deferred_for_operator_review":
        return ("no_action_allowed", "inspect_real_memory_root_admission_gate_metadata", "operator_review_required", "sustain_default_deny")
    if decision == "real_memory_root_admission_gate_rejected":
        return ("no_action_allowed", "inspect_real_memory_root_admission_gate_metadata", "sustain_default_deny")
    return ("no_action_allowed", "inspect_real_memory_root_admission_gate_metadata", "operator_review_required", "prepare_later_real_memory_root_admission_packet", "prepare_final_operator_review_later", "sustain_default_deny")


def evaluate_real_memory_root_admission_gate(payload: Mapping[str, Any], policy: RealMemoryRootAdmissionPolicy | None = None) -> RealRootAdmissionResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        sandbox = _as_mapping(payload.get("final_live_memory_commit_review_gate") or payload.get("sandbox_commit_packet") or payload.get("sandboxed_live_memory_commit_packet"))
        if not sandbox:
            return _blocked("missing_sandbox_commit_packet")
        sandbox_records = _records(sandbox)
        sandbox_digest = str(sandbox.get("digest") or "")
        if not sandbox_records or not sandbox_digest:
            return _blocked("invalid_sandbox_commit_packet")
        sandbox_record = sandbox_records[0]
        sandbox_decision = str(sandbox_record.get("final_live_memory_commit_review_gate_decision") or sandbox_record.get("final_review_decision") or sandbox_record.get("review_decision") or sandbox_record.get("sandbox_decision") or sandbox_record.get("decision") or "")
        sandbox_scope = _as_tuple(sandbox_record.get("operator_scope_keys"))
        sandbox_record_digest = str(sandbox_record.get("digest") or "")
        if active_policy.require_sandbox_commit_ready and sandbox_decision not in READY_SANDBOX_DECISIONS:
            return _blocked("sandbox_commit_not_ready")
        raw_candidates = _candidate_payloads(payload)
        if not raw_candidates:
            return _blocked("missing_real_memory_root_admission_gate_candidate")
        records: list[RealRootAdmissionRecord] = []
        findings: list[RealRootAdmissionFinding] = []
        for raw in raw_candidates:
            candidate = RealRootAdmissionCandidate.from_mapping(raw)
            if candidate is None:
                return _blocked("invalid_real_memory_root_admission_gate_candidate")
            non_noop = candidate.candidate_type != "noop_real_memory_root_admission_gate_candidate" and sandbox_decision != "final_live_memory_commit_review_gate_noop"
            blocker = _claims_blocker(candidate, active_policy)
            if blocker:
                return _blocked(blocker, [RealRootAdmissionFinding("error", blocker, blocker.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_sandbox_commit_digest and candidate.claimed_sandbox_commit_digest != sandbox_digest:
                return _blocked("sandbox_commit_digest_mismatch", [RealRootAdmissionFinding("error", "sandbox_commit_digest_mismatch", "candidate final live memory commit review gate digest does not match", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_sandbox_commit_decision and candidate.claimed_sandbox_commit_decision != sandbox_decision:
                return _blocked("sandbox_commit_decision_mismatch", [RealRootAdmissionFinding("error", "sandbox_commit_decision_mismatch", "candidate final live memory commit review gate decision does not match", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_receipt_manifest_digest_for_non_noop and not candidate.claimed_sandbox_receipt_manifest_digest:
                return _blocked("missing_sandbox_receipt_manifest_digest", [RealRootAdmissionFinding("error", "missing_sandbox_receipt_manifest_digest", "sandbox receipt manifest digest is required for non-noop candidates", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_rollback_manifest_digest_for_non_noop and not candidate.claimed_sandbox_rollback_manifest_digest:
                return _blocked("missing_sandbox_rollback_manifest_digest", [RealRootAdmissionFinding("error", "missing_sandbox_rollback_manifest_digest", "sandbox rollback manifest digest is required for non-noop candidates", candidate.candidate_id, candidate.record_id)])
            if non_noop and active_policy.require_artifact_plan_for_non_noop and not candidate.sandbox_artifact_plan:
                return _blocked("missing_sandbox_artifact_plan", [RealRootAdmissionFinding("error", "missing_sandbox_artifact_plan", "sandbox artifact plan evidence is required for non-noop candidates", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_scope_alignment and candidate.operator_scope_keys and set(candidate.operator_scope_keys) != set(sandbox_scope):
                if active_policy.allow_mixed_scope_diagnostic_packet and candidate.candidate_type == "mixed_real_memory_root_admission_gate_candidate" and candidate.metadata.get("diagnostic_warning") is True:
                    findings.append(RealRootAdmissionFinding("warning", "scope_mismatch_diagnostic", "scope mismatch allowed for diagnostic packet", candidate.candidate_id, candidate.record_id))
                else:
                    return _blocked("scope_mismatch", [RealRootAdmissionFinding("error", "scope_mismatch", "candidate scope does not match sandbox commit scope", candidate.candidate_id, candidate.record_id)])
            warning = bool(candidate.metadata.get("warning_only") or candidate.metadata.get("diagnostic_warning")) or sandbox_decision.endswith("with_warnings") or any(f.severity == "warning" and f.candidate_id == candidate.candidate_id for f in findings)
            if warning:
                findings.append(RealRootAdmissionFinding("warning", "real_memory_root_admission_gate_warning", "candidate is warning/diagnostic metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, sandbox_decision, warning)
            future_record = {
                "candidate_id": candidate.candidate_id,
                "eligible_for_future_real_live_commit_adapter_consideration": decision in {"real_memory_root_admission_gate_ready_for_later_real_memory_root_admission_packet", "real_memory_root_admission_gate_ready_with_warnings"},
                "decision": decision,
                "real_live_commit_performed": False,
                "real_memory_root_access_performed": False,
                "future_real_memory_root_admission_packet_required": True,
                "final_operator_review_required": True,
            }
            records.append(RealRootAdmissionRecord(
                candidate.candidate_id,
                candidate.record_id,
                candidate.candidate_type,
                decision,
                sandbox_decision,
                sandbox_digest,
                sandbox_record_digest,
                candidate.claimed_sandbox_receipt_manifest_digest,
                candidate.claimed_sandbox_rollback_manifest_digest,
                candidate.operator_scope_keys,
                sandbox_scope,
                dict(candidate.real_root_path_metadata),
                dict(candidate.sandbox_artifact_plan),
                _safe_actions(decision),
                future_record,
            ).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for finding in findings if finding.severity == "warning")}
        for record in records:
            counts[record.admission_decision] = counts.get(record.admission_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.admission_decision for record in records}
        if counts["warning_count"]:
            status: RealRootAdmissionStatus = "real_memory_root_admission_gate_ready_with_warnings"
        elif decisions <= {"real_memory_root_admission_gate_noop"}:
            status = "real_memory_root_admission_gate_noop"
        elif decisions <= {"real_memory_root_admission_gate_deferred_for_operator_review"}:
            status = "real_memory_root_admission_gate_deferred_for_operator_review"
        elif decisions <= {"real_memory_root_admission_gate_rejected"}:
            status = "real_memory_root_admission_gate_rejected"
        elif "real_memory_root_admission_gate_ready_with_warnings" in decisions:
            status = "real_memory_root_admission_gate_ready_with_warnings"
        else:
            status = "real_memory_root_admission_gate_ready"
        packet = RealRootAdmissionPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = RealRootAdmissionReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return RealRootAdmissionResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [RealRootAdmissionFinding("error", "failed", str(exc))])


def evaluate_packet(payload: Mapping[str, Any], policy: RealMemoryRootAdmissionPolicy | None = None) -> RealRootAdmissionResult:
    return evaluate_real_memory_root_admission_gate(payload, policy)


__all__ = [
    "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "READY_SANDBOX_DECISIONS", "REAL_ROOT_ADMISSION_CANDIDATE_TYPES", "SAFE_NEXT_ACTIONS",
    "RealMemoryRootAdmissionPolicy", "RealRootAdmissionCandidate", "RealRootAdmissionFinding", "RealRootAdmissionPacket", "RealRootAdmissionRecord", "RealRootAdmissionReport", "RealRootAdmissionResult",
    "build_default_policy", "validate_policy", "evaluate_real_memory_root_admission_gate", "evaluate_packet",
]
