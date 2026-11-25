"""Content-addressed, non-promoting host access-probe review records."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping

from .local_model_authority import digest_payload

SCHEMA = "sentientos.durable_learning_host_acceptance_review:v1"
ARTIFACT_PREFIX = "devexp-durable-learning-host-access-review-"
CONDITIONS = (
    "relevant_experience_available",
    "relevant_experience_withheld",
)
CRITERIA = (
    "protocol_profile_binding",
    "process_binding",
    "own_sentinel",
    "peer_and_scorer_denial",
    "supervisor_readback",
    "registry_and_profile_state",
    "runtime_access_setup",
)
CLAIM_LIMITS = {
    "process_isolation_verified": False,
    "filesystem_isolation_verified": False,
    "retention_contrast_eligible": False,
    "model_attention_established": False,
    "performance_improvement_established": False,
    "learning_established": False,
    "authority": False,
}
_HEX = re.compile(r"^[0-9a-f]{64}$")
_REVIEW_ID = re.compile(re.escape(ARTIFACT_PREFIX) + r"[0-9a-f]{24}$")


def _artifact_ref(value: Any) -> dict[str, str]:
    if (not isinstance(value, Mapping)
            or set(value) != {"artifact_id", "artifact_digest"}
            or not isinstance(value.get("artifact_id"), str)
            or not value["artifact_id"]
            or len(value["artifact_id"]) > 256
            or not isinstance(value.get("artifact_digest"), str)
            or _HEX.fullmatch(value["artifact_digest"]) is None):
        raise ValueError("durable_learning_host_review_artifact_ref_invalid")
    return {"artifact_id": value["artifact_id"],
        "artifact_digest": value["artifact_digest"]}


def _verify_refs(value: Any) -> dict[str, Any]:
    fields = {"branch_preflight", "profile_pair", "access_probe_completion",
        "registry_inventory_baseline", "registry_inventories",
        "profile_data_inventory_baseline", "profile_data_inventories"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("durable_learning_host_review_artifact_refs_invalid")
    refs = {key: _artifact_ref(value[key]) for key in (
        "branch_preflight", "profile_pair", "access_probe_completion",
        "registry_inventory_baseline", "profile_data_inventory_baseline")}
    for field in ("registry_inventories", "profile_data_inventories"):
        rows = value[field]
        if (not isinstance(rows, Mapping) or set(rows) != set(CONDITIONS)):
            raise ValueError("durable_learning_host_review_condition_refs_invalid")
        refs[field] = {condition: _artifact_ref(rows[condition])
            for condition in CONDITIONS}
    return refs


def _verify_review_semantic(value: Any, *,
        expected_artifact_refs: Mapping[str, Any] | None = None
        ) -> dict[str, Any]:
    fields = {"schema_version", "protocol", "reviewer", "host",
        "artifact_refs", "disposition", "bounded_access_observation_accepted",
        "criteria", "claim_limits", "review_summary", "authority"}
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema_version") != SCHEMA
            or value.get("authority") is not False):
        raise ValueError("durable_learning_host_review_shape_invalid")

    protocol = value.get("protocol")
    if (not isinstance(protocol, Mapping)
            or set(protocol) != {"artifact_id", "artifact_digest"}):
        raise ValueError("durable_learning_host_review_protocol_invalid")
    protocol_ref = _artifact_ref(protocol)

    reviewer = value.get("reviewer")
    if (not isinstance(reviewer, Mapping)
            or set(reviewer) != {"identity", "role",
                "run_operator_identity", "independent_from_run_operator",
                "reviewed_at"}
            or not isinstance(reviewer.get("identity"), str)
            or not reviewer["identity"] or len(reviewer["identity"]) > 256
            or not isinstance(reviewer.get("run_operator_identity"), str)
            or not reviewer["run_operator_identity"]
            or len(reviewer["run_operator_identity"]) > 256
            or reviewer["identity"].strip().casefold() ==
                reviewer["run_operator_identity"].strip().casefold()
            or reviewer.get("role") != "independent_reviewer"
            or reviewer.get("independent_from_run_operator") is not True
            or not isinstance(reviewer.get("reviewed_at"), str)):
        raise ValueError("durable_learning_host_review_reviewer_invalid")
    try:
        reviewed_at = datetime.fromisoformat(
            reviewer["reviewed_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "durable_learning_host_review_time_invalid") from exc
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("durable_learning_host_review_time_invalid")

    host = value.get("host")
    if (not isinstance(host, Mapping)
            or set(host) != {"host_identity", "os_name", "os_version",
                "os_build", "architecture"}
            or any(not isinstance(host.get(key), str) or not host[key]
                or len(host[key]) > (64 if key in {"os_version", "os_build"}
                    else 256) for key in (
                    "host_identity", "os_version", "os_build"))
            or host.get("os_name") != "Windows"
            or host.get("architecture") not in {"x64", "arm64"}):
        raise ValueError("durable_learning_host_review_host_invalid")

    refs = _verify_refs(value.get("artifact_refs"))
    if expected_artifact_refs is not None:
        if refs != _verify_refs(expected_artifact_refs):
            raise ValueError(
                "durable_learning_host_review_source_artifact_mismatch")

    disposition = value.get("disposition")
    bounded = value.get("bounded_access_observation_accepted")
    if (disposition not in {"accepted_bounded_access_observation", "rejected",
                "insufficient_evidence"}
            or type(bounded) is not bool
            or bounded != (disposition == "accepted_bounded_access_observation")):
        raise ValueError("durable_learning_host_review_disposition_invalid")

    criteria = value.get("criteria")
    if not isinstance(criteria, Mapping) or set(criteria) != set(CRITERIA):
        raise ValueError("durable_learning_host_review_criteria_invalid")
    statuses: list[str] = []
    checked_criteria: dict[str, dict[str, Any]] = {}
    for name in CRITERIA:
        row = criteria[name]
        if (not isinstance(row, Mapping)
                or set(row) != {"status", "evidence_refs", "finding"}
                or row.get("status") not in {"accepted", "rejected", "insufficient"}
                or not isinstance(row.get("evidence_refs"), list)
                or not 1 <= len(row["evidence_refs"]) <= 16
                or any(not isinstance(ref, str) or not ref or len(ref) > 512
                    for ref in row["evidence_refs"])
                or not isinstance(row.get("finding"), str)
                or not row["finding"] or len(row["finding"]) > 1024):
            raise ValueError("durable_learning_host_review_criterion_invalid")
        statuses.append(row["status"])
        checked_criteria[name] = {"status": row["status"],
            "evidence_refs": list(row["evidence_refs"]),
            "finding": row["finding"]}
    if disposition == "accepted_bounded_access_observation" and any(
            status != "accepted" for status in statuses):
        raise ValueError("durable_learning_host_review_acceptance_incomplete")

    claims = value.get("claim_limits")
    if (not isinstance(claims, Mapping)
            or dict(claims) != CLAIM_LIMITS):
        raise ValueError("durable_learning_host_review_claim_limit_invalid")
    summary = value.get("review_summary")
    if not isinstance(summary, str) or not summary or len(summary) > 4096:
        raise ValueError("durable_learning_host_review_summary_invalid")

    return {"schema_version": SCHEMA,
        "protocol": protocol_ref,
        "reviewer": {"identity": reviewer["identity"],
            "role": "independent_reviewer",
            "run_operator_identity": reviewer["run_operator_identity"],
            "independent_from_run_operator": True,
            "reviewed_at": reviewer["reviewed_at"]},
        "host": {key: host[key] for key in (
            "host_identity", "os_name", "os_version", "os_build",
            "architecture")},
        "artifact_refs": refs,
        "disposition": disposition,
        "bounded_access_observation_accepted": bounded,
        "criteria": checked_criteria,
        "claim_limits": dict(CLAIM_LIMITS),
        "review_summary": summary,
        "authority": False}


def create_host_acceptance_review(*, protocol: Mapping[str, Any],
        reviewer: Mapping[str, Any], host: Mapping[str, Any],
        artifact_refs: Mapping[str, Any], disposition: str,
        criteria: Mapping[str, Any], review_summary: str,
        expected_artifact_refs: Mapping[str, Any] | None = None
        ) -> dict[str, Any]:
    """Create a digest-bound review without granting experiment authority."""
    semantic = _verify_review_semantic({
        "schema_version": SCHEMA,
        "protocol": dict(protocol), "reviewer": dict(reviewer),
        "host": dict(host), "artifact_refs": dict(artifact_refs),
        "disposition": disposition,
        "bounded_access_observation_accepted": (
            disposition == "accepted_bounded_access_observation"),
        "criteria": {key: dict(criteria[key]) for key in criteria},
        "claim_limits": dict(CLAIM_LIMITS),
        "review_summary": review_summary, "authority": False},
        expected_artifact_refs=expected_artifact_refs)
    digest = digest_payload(semantic)
    artifact = {**semantic, "artifact_digest": digest,
        "artifact_id": ARTIFACT_PREFIX + digest[:24]}
    return verify_host_acceptance_review(artifact,
        expected_artifact_refs=expected_artifact_refs)


def verify_host_acceptance_review(value: Any, *,
        expected_artifact_refs: Mapping[str, Any] | None = None
        ) -> dict[str, Any]:
    """Recompute identity and enforce the non-promotion policy contract."""
    if (not isinstance(value, Mapping)
            or set(value) != {"schema_version", "artifact_id", "artifact_digest",
                "protocol", "reviewer", "host", "artifact_refs", "disposition",
                "bounded_access_observation_accepted", "criteria", "claim_limits",
                "review_summary", "authority"}):
        raise ValueError("durable_learning_host_review_artifact_invalid")
    semantic = _verify_review_semantic({key: item for key, item in value.items()
        if key not in {"artifact_id", "artifact_digest"}},
        expected_artifact_refs=expected_artifact_refs)
    digest = digest_payload(semantic)
    if (value.get("artifact_digest") != digest
            or value.get("artifact_id") != ARTIFACT_PREFIX + digest[:24]
            or _REVIEW_ID.fullmatch(str(value.get("artifact_id", ""))) is None):
        raise ValueError("durable_learning_host_review_digest_invalid")
    return {**semantic, "artifact_digest": digest,
        "artifact_id": ARTIFACT_PREFIX + digest[:24]}
