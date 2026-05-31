"""Deterministic sandbox-only live memory commit adapter.

This adapter consumes explicit live commit safety-interlock evidence and sandbox
commit candidates, then optionally writes deterministic JSON manifests under an
explicit caller-provided sandbox root. It never writes, deletes, purges, or
mutates real live memory or live indexes; never materializes prompts; never
executes actions; never discloses externally; and never grants truth, policy,
consent, or authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

SandboxCommitStatus = Literal[
    "sandbox_commit_artifacts_ready",
    "sandbox_commit_artifacts_ready_with_warnings",
    "sandbox_commit_deferred_for_operator_review",
    "sandbox_commit_rejected",
    "sandbox_commit_blocked",
    "sandbox_commit_noop",
    "sandbox_commit_invalid",
    "sandbox_commit_failed",
]

SandboxCommitDecision = Literal[
    "sandbox_commit_artifacts_ready",
    "sandbox_commit_artifacts_ready_with_warnings",
    "sandbox_commit_deferred_for_operator_review",
    "sandbox_commit_rejected",
    "sandbox_commit_blocked",
    "sandbox_commit_noop",
]

SANDBOX_COMMIT_CANDIDATE_TYPES = frozenset({
    "ai_capsule_sandbox_commit_candidate",
    "human_summary_sandbox_commit_candidate",
    "dual_capsule_sandbox_commit_candidate",
    "protect_receipt_sandbox_commit_candidate",
    "merge_receipt_sandbox_commit_candidate",
    "tomb_archive_sandbox_commit_candidate",
    "tomb_deferred_sandbox_commit_candidate",
    "operator_review_sandbox_commit_candidate",
    "noop_sandbox_commit_candidate",
    "mixed_sandbox_commit_candidate",
})

READY_INTERLOCK_DECISIONS = frozenset({
    "live_commit_adapter_consideration_eligible",
    "live_commit_adapter_consideration_eligible_with_warnings",
    "live_commit_adapter_consideration_deferred_for_operator_review",
    "live_commit_adapter_consideration_rejected",
    "live_commit_adapter_consideration_noop",
})

NON_AUTHORITY_STATEMENTS = (
    "sandbox commit is not a real memory write",
    "sandbox commit is not deletion",
    "sandbox commit is not purge",
    "sandbox commit is not index mutation",
    "sandbox commit is not policy",
    "sandbox commit is not truth",
    "sandbox commit is not consent",
    "sandbox commit is not authority",
    "sandbox commit is not prompt assembly",
    "sandbox commit is not action execution",
    "sandbox commit is not external disclosure",
)

FORBIDDEN_NEXT_STEPS = (
    "write_live_memory_now",
    "delete_live_memory_now",
    "purge_live_memory_now",
    "mutate_vector_index",
    "mutate_live_index",
    "assemble_prompt_now",
    "retrieve_live_context",
    "execute_action_ingress",
    "bypass_safety_interlock",
    "bypass_execution_gate",
    "bypass_operator_approval_packet",
    "bypass_commit_plan_packet",
    "bypass_live_boundary_admission",
    "bypass_governed_writer_adapter",
    "bypass_tomb_verifier",
    "bypass_receipt_gate",
    "bypass_distillation_contract",
    "enable_external_disclosure",
)

INVARIANTS: dict[str, bool] = {
    "sandbox_commit_is_not_real_memory_write": True,
    "sandbox_commit_is_not_memory_deletion": True,
    "sandbox_commit_is_not_memory_purge": True,
    "sandbox_commit_is_not_index_mutation": True,
    "sandbox_commit_is_not_policy": True,
    "sandbox_commit_is_not_truth": True,
    "sandbox_commit_is_not_consent": True,
    "sandbox_commit_is_not_authority": True,
    "sandbox_commit_is_not_prompt_assembly": True,
    "sandbox_commit_is_not_action_execution": True,
    "sandbox_commit_is_not_external_disclosure": True,
    "future_real_live_memory_adapter_required": True,
    "future_real_memory_root_admission_required": True,
    "safety_interlock_required": True,
    "sandbox_root_required_for_writes": True,
}

DISABLED_SURFACES: dict[str, bool] = {
    "live_memory_write_enabled": False,
    "live_memory_delete_enabled": False,
    "live_memory_purge_enabled": False,
    "live_index_mutation_enabled": False,
    "prompt_materialization_enabled": False,
    "action_execution_enabled": False,
    "external_disclosure_enabled": False,
    "remote_service_enabled": False,
}

RAW_PAYLOAD_KEYS = frozenset({"raw_payload", "private_payload", "secret", "secrets", "media", "audio", "video", "image", "prompt", "prompt_payload", "private_memory"})
RAW_PAYLOAD_PATTERN = re.compile(r"(begin private|secret:|data:(?:image|audio|video)|provider prompt text|raw/private/media/secret/prompt)", re.I)
REAL_ROOT_MARKERS = ("live_memory", "memory/live", "real_memory", "/home/", "\\users\\")


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
        for key, item in value.items():
            if str(key).lower() in RAW_PAYLOAD_KEYS or _has_raw_payload(item):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return any(_has_raw_payload(item) for item in value)
    elif isinstance(value, str):
        return bool(RAW_PAYLOAD_PATTERN.search(value))
    return False


def _flag(mapping: Mapping[str, Any], *names: str) -> bool:
    return any(mapping.get(name) is True for name in names)


@dataclass(frozen=True)
class SandboxedLiveMemoryCommitPolicy:
    schema_version: str = "sandboxed-live-memory-commit-adapter.v1"
    default_posture: str = "deny"
    require_safety_interlock_ready: bool = True
    require_matching_safety_interlock_digest: bool = True
    require_matching_safety_interlock_decision: bool = True
    require_scope_alignment: bool = True
    allow_warnings: bool = True
    allow_operator_review_deferrals: bool = True
    allow_noop: bool = True
    allow_rejections: bool = True
    block_hard_override_attempts: bool = True


@dataclass(frozen=True)
class SandboxCommitFinding:
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    candidate_id: str | None = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SandboxCommitCandidate:
    candidate_id: str
    record_id: str
    candidate_type: str
    claimed_safety_interlock_digest: str
    claimed_safety_interlock_decision: str
    operator_scope_keys: tuple[str, ...]
    sandbox_relative_path: str
    metadata: Mapping[str, Any]
    claims: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SandboxCommitCandidate | None":
        candidate_id = str(raw.get("candidate_id") or "")
        record_id = str(raw.get("record_id") or "")
        candidate_type = str(raw.get("candidate_type") or "")
        if not candidate_id or not record_id or candidate_type not in SANDBOX_COMMIT_CANDIDATE_TYPES:
            return None
        return cls(
            candidate_id=candidate_id,
            record_id=record_id,
            candidate_type=candidate_type,
            claimed_safety_interlock_digest=str(raw.get("claimed_safety_interlock_digest") or raw.get("safety_interlock_digest") or ""),
            claimed_safety_interlock_decision=str(raw.get("claimed_safety_interlock_decision") or raw.get("safety_interlock_decision") or ""),
            operator_scope_keys=_as_tuple(raw.get("operator_scope_keys")),
            sandbox_relative_path=str(raw.get("sandbox_relative_path") or f"records/{candidate_id}.json"),
            metadata=_as_mapping(raw.get("metadata")),
            claims=_as_mapping(raw.get("claims") or raw.get("sandbox_commit_claims")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SandboxCommitRecord:
    candidate_id: str
    record_id: str
    candidate_type: str
    sandbox_decision: SandboxCommitDecision
    safety_interlock_decision: str
    safety_interlock_digest: str
    operator_scope_keys: tuple[str, ...]
    safety_interlock_scope_keys: tuple[str, ...]
    sandbox_relative_path: str
    artifact_name: str
    sandbox_only: bool = True
    written_to_live_memory: bool = False
    deleted_live_memory: bool = False
    purged_live_memory: bool = False
    mutated_live_index: bool = False
    non_authority_statements: tuple[str, ...] = NON_AUTHORITY_STATEMENTS
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_digest(self) -> "SandboxCommitRecord":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class SandboxCommitPacket:
    schema_version: str
    records: tuple[SandboxCommitRecord, ...]
    sandbox_only: bool = True
    non_authority_statements: tuple[str, ...] = NON_AUTHORITY_STATEMENTS
    forbidden_next_steps: tuple[str, ...] = FORBIDDEN_NEXT_STEPS
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(INVARIANTS)
        data.update(DISABLED_SURFACES)
        return data

    def with_digest(self) -> "SandboxCommitPacket":
        data = self.to_dict(); data.pop("digest", None)
        return replace(self, digest=_digest(data))


@dataclass(frozen=True)
class SandboxCommitReport:
    status: SandboxCommitStatus
    findings: tuple[SandboxCommitFinding, ...]
    summary_counts: Mapping[str, int]
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SandboxCommitResult:
    status: SandboxCommitStatus
    packet: SandboxCommitPacket | None
    report: SandboxCommitReport
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "packet": self.packet.to_dict() if self.packet else None, "report": self.report.to_dict(), "digest": self.digest}


def build_default_policy() -> SandboxedLiveMemoryCommitPolicy:
    return SandboxedLiveMemoryCommitPolicy()


def validate_policy(policy: SandboxedLiveMemoryCommitPolicy | None = None) -> dict[str, Any]:
    active = policy or build_default_policy()
    warnings: list[str] = []
    if active.default_posture != "deny":
        warnings.append("default_posture_should_remain_deny")
    return {"status": "valid" if not warnings else "valid_with_warnings", "policy": asdict(active), "warnings": warnings, "digest": _digest(asdict(active))}


def _policy_from_payload(payload: Mapping[str, Any], policy: SandboxedLiveMemoryCommitPolicy | None) -> SandboxedLiveMemoryCommitPolicy:
    if policy is not None:
        return policy
    raw = _as_mapping(payload.get("policy"))
    if raw:
        allowed = set(SandboxedLiveMemoryCommitPolicy.__dataclass_fields__)
        return SandboxedLiveMemoryCommitPolicy(**{str(k): v for k, v in raw.items() if str(k) in allowed})
    return build_default_policy()


def _candidate_payloads(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("sandbox_commit_candidates", payload.get("commit_candidates", payload.get("candidates", ())))
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


def _blocked(code: str, findings: Sequence[SandboxCommitFinding] | None = None) -> SandboxCommitResult:
    finding_list = tuple(findings or (SandboxCommitFinding("error", code, code.replace("_", " ")),))
    report = SandboxCommitReport("sandbox_commit_blocked", finding_list, {"error_count": len(finding_list)})
    report = replace(report, digest=_digest(report.to_dict()))
    return SandboxCommitResult("sandbox_commit_blocked", None, report, _digest(report.to_dict()))


def _blocker_for_candidate(candidate: SandboxCommitCandidate) -> str | None:
    claims = candidate.claims
    metadata = candidate.metadata
    all_data = {"claims": claims, "metadata": metadata, "path": candidate.sandbox_relative_path}
    if ".." in Path(candidate.sandbox_relative_path).parts or Path(candidate.sandbox_relative_path).is_absolute():
        return "path_traversal"
    if any(marker in candidate.sandbox_relative_path.lower() for marker in REAL_ROOT_MARKERS):
        return "real_memory_root_claim"
    if _has_raw_payload(all_data):
        return "raw_payload_leak"
    if _flag(claims, "live_write", "writes_live_memory", "real_memory_write") or metadata.get("live_write_claimed") is True:
        return "live_write_claim"
    if _flag(claims, "live_delete", "deletes_live_memory") or metadata.get("live_delete_claimed") is True:
        return "live_delete_claim"
    if _flag(claims, "live_purge", "purges_live_memory") or metadata.get("live_purge_claimed") is True:
        return "live_purge_claim"
    if _flag(claims, "index_mutation", "mutates_index", "mutates_live_index") or metadata.get("index_mutation_claimed") is True:
        return "index_mutation_claim"
    if _flag(claims, "prompt_materialization", "prompt_assembly", "assembles_prompt") or metadata.get("prompt_materialization_requested") is True:
        return "prompt_materialization"
    if _flag(claims, "action_execution", "executes_action", "action_ingress") or metadata.get("action_execution_requested") is True:
        return "action_execution"
    if _flag(claims, "external_disclosure", "discloses_externally", "remote_service") or metadata.get("external_disclosure_requested") is True:
        return "external_disclosure"
    if _flag(claims, "authority", "grants_authority") or metadata.get("authority_claimed") is True:
        return "authority_smuggling"
    if _flag(claims, "consent") or metadata.get("consent_claimed") is True:
        return "consent_smuggling"
    if _flag(claims, "policy") or metadata.get("policy_claimed") is True:
        return "policy_smuggling"
    if _flag(claims, "truth") or metadata.get("truth_claimed") is True:
        return "truth_smuggling"
    return None


def _decision_for(candidate: SandboxCommitCandidate, interlock_decision: str, warning: bool) -> SandboxCommitDecision:
    if candidate.candidate_type == "noop_sandbox_commit_candidate" or interlock_decision == "live_commit_adapter_consideration_noop":
        return "sandbox_commit_noop"
    if candidate.candidate_type == "operator_review_sandbox_commit_candidate" or interlock_decision == "live_commit_adapter_consideration_deferred_for_operator_review" or candidate.metadata.get("operator_review_requested") is True:
        return "sandbox_commit_deferred_for_operator_review"
    if interlock_decision == "live_commit_adapter_consideration_rejected" or candidate.metadata.get("rejected") is True:
        return "sandbox_commit_rejected"
    if warning or interlock_decision.endswith("with_warnings"):
        return "sandbox_commit_artifacts_ready_with_warnings"
    return "sandbox_commit_artifacts_ready"


def evaluate_sandboxed_live_memory_commit_adapter(payload: Mapping[str, Any], policy: SandboxedLiveMemoryCommitPolicy | None = None) -> SandboxCommitResult:
    try:
        active_policy = _policy_from_payload(payload, policy)
        interlock = _as_mapping(payload.get("safety_interlock_packet") or payload.get("interlock_packet"))
        if not interlock:
            return _blocked("missing_safety_interlock_packet")
        interlock_records = _records(interlock)
        interlock_digest = str(interlock.get("digest") or "")
        if not interlock_records or not interlock_digest:
            return _blocked("invalid_safety_interlock_packet")
        interlock_record = interlock_records[0]
        interlock_decision = str(interlock_record.get("live_commit_adapter_decision") or interlock_record.get("interlock_decision") or interlock_record.get("sandbox_decision") or "")
        interlock_scope = _as_tuple(interlock_record.get("operator_scope_keys"))
        if active_policy.require_safety_interlock_ready and interlock_decision not in READY_INTERLOCK_DECISIONS:
            return _blocked("safety_interlock_not_ready")
        raw_candidates = _candidate_payloads(payload)
        if not raw_candidates:
            return _blocked("missing_sandbox_commit_candidate")
        records: list[SandboxCommitRecord] = []
        findings: list[SandboxCommitFinding] = []
        for raw in raw_candidates:
            candidate = SandboxCommitCandidate.from_mapping(raw)
            if candidate is None:
                return _blocked("invalid_sandbox_commit_candidate")
            blocker = _blocker_for_candidate(candidate)
            if blocker:
                return _blocked(blocker, [SandboxCommitFinding("error", blocker, blocker.replace("_", " "), candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_safety_interlock_digest and candidate.claimed_safety_interlock_digest != interlock_digest:
                return _blocked("safety_interlock_digest_mismatch", [SandboxCommitFinding("error", "safety_interlock_digest_mismatch", "candidate safety interlock digest does not match", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_matching_safety_interlock_decision and candidate.claimed_safety_interlock_decision != interlock_decision:
                return _blocked("safety_interlock_decision_mismatch", [SandboxCommitFinding("error", "safety_interlock_decision_mismatch", "candidate safety interlock decision does not match", candidate.candidate_id, candidate.record_id)])
            if active_policy.require_scope_alignment and candidate.operator_scope_keys and set(candidate.operator_scope_keys) != set(interlock_scope):
                return _blocked("scope_mismatch", [SandboxCommitFinding("error", "scope_mismatch", "candidate scope does not match safety interlock scope", candidate.candidate_id, candidate.record_id)])
            warning = bool(candidate.metadata.get("warning_only") or interlock_decision.endswith("with_warnings"))
            if warning:
                findings.append(SandboxCommitFinding("warning", "sandbox_commit_warning", "candidate is warning metadata", candidate.candidate_id, candidate.record_id))
            decision = _decision_for(candidate, interlock_decision, warning)
            artifact_name = Path(candidate.sandbox_relative_path).name
            records.append(SandboxCommitRecord(candidate.candidate_id, candidate.record_id, candidate.candidate_type, decision, interlock_decision, interlock_digest, candidate.operator_scope_keys, interlock_scope, candidate.sandbox_relative_path, artifact_name).with_digest())
        counts: dict[str, int] = {"candidate_count": len(records), "warning_count": sum(1 for f in findings if f.severity == "warning")}
        for record in records:
            counts[record.sandbox_decision] = counts.get(record.sandbox_decision, 0) + 1
            counts[record.candidate_type] = counts.get(record.candidate_type, 0) + 1
        decisions = {record.sandbox_decision for record in records}
        if counts["warning_count"]:
            status: SandboxCommitStatus = "sandbox_commit_artifacts_ready_with_warnings"
        elif decisions <= {"sandbox_commit_noop"}:
            status = "sandbox_commit_noop"
        elif decisions <= {"sandbox_commit_deferred_for_operator_review"}:
            status = "sandbox_commit_deferred_for_operator_review"
        elif decisions <= {"sandbox_commit_rejected"}:
            status = "sandbox_commit_rejected"
        elif "sandbox_commit_artifacts_ready_with_warnings" in decisions:
            status = "sandbox_commit_artifacts_ready_with_warnings"
        else:
            status = "sandbox_commit_artifacts_ready"
        packet = SandboxCommitPacket(active_policy.schema_version, tuple(records)).with_digest()
        report = SandboxCommitReport(status, tuple(findings), dict(sorted(counts.items())))
        report = replace(report, digest=_digest(report.to_dict()))
        return SandboxCommitResult(status, packet, report, _digest({"packet": packet.to_dict(), "report": report.to_dict()}))
    except Exception as exc:
        return _blocked("failed", [SandboxCommitFinding("error", "failed", str(exc))])


def _safe_sandbox_root(sandbox_root: Path) -> Path:
    if not str(sandbox_root):
        raise ValueError("missing_sandbox_root")
    root = sandbox_root.expanduser().resolve()
    lower = str(root).lower()
    if not root.is_absolute() or any(marker in lower for marker in REAL_ROOT_MARKERS):
        raise ValueError("unsafe_sandbox_root")
    return root


def _safe_artifact_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or any(marker in str(rel).lower() for marker in REAL_ROOT_MARKERS):
        raise ValueError("path_traversal")
    target = (root / rel).resolve()
    if root not in (target, *target.parents):
        raise ValueError("path_traversal")
    return target


def build_receipt_manifest(result: SandboxCommitResult) -> dict[str, Any]:
    records = [record.to_dict() for record in result.packet.records] if result.packet else []
    manifest = {
        "manifest_kind": "sandbox_live_memory_commit_receipt_manifest",
        "sandbox_only": True,
        "status": result.status,
        "records": records,
        "non_authority_statements": list(NON_AUTHORITY_STATEMENTS),
        "forbidden_next_steps": list(FORBIDDEN_NEXT_STEPS),
    }
    manifest["digest"] = _digest(manifest)
    return manifest


def build_rollback_manifest(result: SandboxCommitResult) -> dict[str, Any]:
    records = []
    if result.packet:
        for record in result.packet.records:
            records.append({
                "candidate_id": record.candidate_id,
                "record_id": record.record_id,
                "sandbox_relative_path": record.sandbox_relative_path,
                "rollback_kind": "remove_sandbox_artifact_only",
                "real_memory_rollback_required": False,
                "live_memory_was_mutated": False,
                "digest": record.digest,
            })
    manifest = {
        "manifest_kind": "sandbox_live_memory_commit_rollback_manifest",
        "sandbox_only": True,
        "status": result.status,
        "records": records,
        "non_authority_statements": list(NON_AUTHORITY_STATEMENTS),
        "forbidden_next_steps": list(FORBIDDEN_NEXT_STEPS),
    }
    manifest["digest"] = _digest(manifest)
    return manifest


def write_sandbox_artifacts(payload: Mapping[str, Any], sandbox_root: str | Path, policy: SandboxedLiveMemoryCommitPolicy | None = None) -> dict[str, Any]:
    root = _safe_sandbox_root(Path(sandbox_root))
    result = evaluate_sandboxed_live_memory_commit_adapter(payload, policy)
    if result.status in {"sandbox_commit_blocked", "sandbox_commit_invalid", "sandbox_commit_failed"} or result.packet is None:
        return {"status": result.status, "result": result.to_dict(), "written_files": []}
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for record in result.packet.records:
        target = _safe_artifact_path(root, record.sandbox_relative_path)
        artifact = {
            "artifact_kind": "sandbox_live_memory_commit_artifact",
            "sandbox_only": True,
            "record": record.to_dict(),
            "non_authority_statements": list(NON_AUTHORITY_STATEMENTS),
        }
        artifact["digest"] = _digest(artifact)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(str(target))
    receipt_path = root / "sandbox_receipt_manifest.json"
    rollback_path = root / "sandbox_rollback_manifest.json"
    packet_path = root / "sandbox_commit_packet.json"
    for path, data in (
        (receipt_path, build_receipt_manifest(result)),
        (rollback_path, build_rollback_manifest(result)),
        (packet_path, result.to_dict()),
    ):
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(str(path))
    return {"status": result.status, "result": result.to_dict(), "sandbox_root": str(root), "written_files": sorted(written), "receipt_manifest": str(receipt_path), "rollback_manifest": str(rollback_path), "packet_path": str(packet_path)}


def evaluate_packet(payload: Mapping[str, Any], policy: SandboxedLiveMemoryCommitPolicy | None = None) -> SandboxCommitResult:
    return evaluate_sandboxed_live_memory_commit_adapter(payload, policy)


__all__ = [
    "FORBIDDEN_NEXT_STEPS", "INVARIANTS", "NON_AUTHORITY_STATEMENTS", "READY_INTERLOCK_DECISIONS", "SANDBOX_COMMIT_CANDIDATE_TYPES",
    "SandboxedLiveMemoryCommitPolicy", "SandboxCommitCandidate", "SandboxCommitFinding", "SandboxCommitPacket", "SandboxCommitRecord", "SandboxCommitReport", "SandboxCommitResult",
    "build_default_policy", "validate_policy", "evaluate_sandboxed_live_memory_commit_adapter", "evaluate_packet", "build_receipt_manifest", "build_rollback_manifest", "write_sandbox_artifacts",
]
