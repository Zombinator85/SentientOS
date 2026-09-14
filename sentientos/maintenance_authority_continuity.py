"""Deterministic, local-only maintenance authority continuity derivation.

This module consumes evidence; it never performs maintenance, Git operations, or
runtime adoption.  The deliberately closed records make every authority-bearing
input explicit and digest bound.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, cast

from sentientos import maintenance_activation_profiles as profiles

POLICY_SCHEMA = "sentientos.maintenance_continuity_policy:v1"
GENERATION_SCHEMA = "sentientos.maintenance_authority_generation:v1"
COMPLETION_SCHEMA = "sentientos.completed_maintenance_generation_evidence:v1"
SUCCESSOR_SCHEMA = "sentientos.exact_successor_repository_evidence:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_authority_continuity_receipt:v1"
RESULT_SCHEMA = "sentientos.maintenance_authority_continuity_result:v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any, omitted: str | None = None) -> str:
    body = {k: v for k, v in value.items() if k != omitted} if omitted else value
    return "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()


def _load(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("continuity_input_not_regular")
    return cast(dict[str, Any], json.loads(p.read_text(encoding="utf-8")))


def _time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("continuity_timestamp_invalid")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _closed(value: Mapping[str, Any], schema: str, keys: set[str], digest_key: str) -> dict[str, Any]:
    record = dict(value)
    if set(record) != keys or record.get("schema_version") != schema:
        raise ValueError("continuity_closed_schema_invalid")
    if record.get(digest_key) != digest(record, digest_key):
        raise ValueError(digest_key + "_invalid")
    return record


POLICY_KEYS = {"schema_version", "policy_id", "policy_digest", "lineage_id", "repository_identity", "generation_root", "receipt_root", "initial_generation_path", "operator_reference", "approval_reference", "created_at", "constraints"}
GENERATION_KEYS = {"schema_version", "generation_id", "generation_digest", "lineage_id", "ordinal", "base_sha", "manifest_path", "manifest_digest", "profile_bundle_digest", "predecessor_generation_digest", "prior_receipt_digest", "created_at"}
COMPLETION_KEYS = {"schema_version", "evidence_id", "evidence_digest", "generation_digest", "task_id", "lease_id", "lease_digest", "admission_status", "implementation_status", "implementation_evidence_digest", "validation_status", "validation_evidence_digest", "validated_commit_sha", "commit_status", "commit_evidence_digest", "landing_status", "landing_evidence_digest", "terminal_status", "closure_evidence_digest", "integrity_status"}
SUCCESSOR_KEYS = {"schema_version", "evidence_id", "evidence_digest", "mode", "predecessor_base_sha", "successor_sha", "validated_commit_sha", "commit_parent_sha", "expected_old_sha", "base_ref", "base_ref_after", "canonical_tracked_ref", "canonical_tracked_ref_sha", "checkout_synchronization", "checkout_head_sha", "current_repository_sha", "current_repository_clean", "network_performed", "runtime_adoption_performed"}
RECEIPT_KEYS = {"schema_version", "receipt_id", "receipt_digest", "lineage_id", "ordinal", "predecessor_generation_digest", "predecessor_base_sha", "completed_task_id", "completion_evidence_digest", "validation_evidence_digest", "commit_evidence_digest", "landing_evidence_digest", "closure_evidence_digest", "successor_evidence_digest", "successor_classification", "successor_sha", "same_or_narrower", "successor_manifest_digest", "successor_profile_bundle_digest", "successor_generation_digest", "prior_receipt_digest", "created_at"}


def validate_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    p = _closed(value, POLICY_SCHEMA, POLICY_KEYS, "policy_digest")
    if p["constraints"] != ["same_or_narrower", "local_fast_forward_base_ref", "no_runtime_adoption"]:
        raise ValueError("continuity_policy_constraints_invalid")
    for key in ("generation_root", "receipt_root", "initial_generation_path"):
        if not Path(p[key]).is_absolute(): raise ValueError(key + "_must_be_absolute")
    return p


def validate_generation(value: Mapping[str, Any], policy: Mapping[str, Any]) -> dict[str, Any]:
    g = dict(value)
    if set(g) != GENERATION_KEYS or g.get("schema_version") != GENERATION_SCHEMA:
        raise ValueError("continuity_closed_schema_invalid")
    if g.get("generation_digest") != _generation_digest(g):
        raise ValueError("generation_digest_invalid")
    if g["lineage_id"] != policy["lineage_id"] or not isinstance(g["ordinal"], int) or g["ordinal"] < 0:
        raise ValueError("generation_lineage_invalid")
    if g["generation_id"] != f"{g['lineage_id']}:generation:{g['ordinal']}": raise ValueError("generation_id_invalid")
    manifest = profiles.validate_manifest(_load(g["manifest_path"]))
    if manifest["manifest_digest"] != g["manifest_digest"] or manifest["base_sha"] != g["base_sha"]:
        raise ValueError("generation_manifest_binding_invalid")
    return g


def _generation_digest(value: Mapping[str, Any]) -> str:
    # The transition receipt is intentionally excluded to avoid a digest cycle; its
    # own digest is nevertheless carried by the immutable descriptor.
    return digest({k: v for k, v in value.items() if k != "prior_receipt_digest"}, "generation_digest")


def _generation_path(policy: Mapping[str, Any], ordinal: int) -> Path:
    return Path(policy["generation_root"]) / f"generation-{ordinal}.json"


def _receipt_path(policy: Mapping[str, Any], ordinal: int) -> Path:
    return Path(policy["receipt_root"]) / f"receipt-{ordinal}.json"


def _write(path: Path, value: Mapping[str, Any]) -> str:
    data = canonical_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data: raise ValueError("continuity_output_conflict")
        return "reused"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    return "created"


def _current_generation(policy: Mapping[str, Any]) -> dict[str, Any]:
    first = Path(policy["initial_generation_path"])
    generation = validate_generation(_load(first), policy)
    if generation["ordinal"] != 0: raise ValueError("initial_generation_not_zero")
    ordinal = 0
    while _generation_path(policy, ordinal + 1).exists():
        nxt = validate_generation(_load(_generation_path(policy, ordinal + 1)), policy)
        receipt = _closed(_load(_receipt_path(policy, ordinal + 1)), RECEIPT_SCHEMA, RECEIPT_KEYS, "receipt_digest")
        if nxt["ordinal"] != ordinal + 1 or nxt["predecessor_generation_digest"] != generation["generation_digest"] or receipt["successor_generation_digest"] != nxt["generation_digest"] or nxt["prior_receipt_digest"] != receipt["receipt_digest"]:
            raise ValueError("continuity_lineage_branched_or_corrupt")
        generation, ordinal = nxt, ordinal + 1
    if _receipt_path(policy, ordinal + 1).exists(): raise ValueError("continuity_orphan_receipt")
    return generation


def _verify_completion(value: Mapping[str, Any], generation: Mapping[str, Any]) -> dict[str, Any]:
    c = _closed(value, COMPLETION_SCHEMA, COMPLETION_KEYS, "evidence_digest")
    required = {"admission_status":"admitted", "implementation_status":"implemented", "validation_status":"passed", "commit_status":"committed", "landing_status":"landed", "terminal_status":"completed", "integrity_status":"verified"}
    if c["generation_digest"] != generation["generation_digest"] or any(c[k] != v for k, v in required.items()):
        raise ValueError("maintenance_generation_not_successfully_closed")
    for key in ("lease_digest", "implementation_evidence_digest", "validation_evidence_digest", "commit_evidence_digest", "landing_evidence_digest", "closure_evidence_digest"):
        if not isinstance(c[key], str) or not c[key].startswith("sha256:"): raise ValueError("completion_identity_invalid")
    return c


def _verify_successor(value: Mapping[str, Any], generation: Mapping[str, Any], completion: Mapping[str, Any]) -> dict[str, Any]:
    s = _closed(value, SUCCESSOR_SCHEMA, SUCCESSOR_KEYS, "evidence_digest")
    sha = s["successor_sha"]
    exact = s["mode"] == "local_fast_forward_base_ref" and completion["validated_commit_sha"] == sha == s["validated_commit_sha"] and s["commit_parent_sha"] == generation["base_sha"] == s["predecessor_base_sha"] == s["expected_old_sha"] and s["base_ref"] == s["canonical_tracked_ref"] and s["base_ref_after"] == sha == s["canonical_tracked_ref_sha"] == s["checkout_head_sha"] == s["current_repository_sha"] and s["checkout_synchronization"] in {"synchronized", "already_exact"} and s["current_repository_clean"] is True and s["network_performed"] is False and s["runtime_adoption_performed"] is False
    if not exact: raise ValueError("exact_local_successor_not_proven")
    return s


def _same_or_narrower(old: Mapping[str, Any], new: Mapping[str, Any]) -> bool:
    list_fields = ("authority_classes", "allowed_candidate_kinds", "allowed_path_prefixes")
    if any(not set(new[k]).issubset(old[k]) for k in list_fields): return False
    if not set(old["forbidden_paths"]).issubset(new["forbidden_paths"]): return False
    if new["publication_mode"] != old["publication_mode"] or new["publication_mode"] != "local_fast_forward_base_ref": return False
    if new["expires_at"] != old["expires_at"] or new["not_before"] != old["not_before"]: return False
    if any(new["budgets"][k] > old["budgets"][k] for k in old["budgets"]): return False
    for k, v in old["validation_bounds"].items():
        if isinstance(v, int) and not isinstance(v, bool) and new["validation_bounds"][k] > v: return False
        if isinstance(v, bool) and v and not new["validation_bounds"][k]: return False
    for key in ("remote_name", "tracked_base_ref", "base_ref", "head_ref_prefix", "codex_executable", "git_executable", "python_executable", "publication_client_executable"):
        if new.get(key) != old.get(key): return False
    return True


def derive_next(policy_path: str | Path, completion_path: str | Path, successor_path: str | Path, evaluation_time: str) -> dict[str, Any]:
    """Derive no more than one exact successor generation."""
    try:
        policy = validate_policy(_load(policy_path)); predecessor = _current_generation(policy)
        supplied_completion = _closed(_load(completion_path), COMPLETION_SCHEMA, COMPLETION_KEYS, "evidence_digest")
        supplied_successor = _closed(_load(successor_path), SUCCESSOR_SCHEMA, SUCCESSOR_KEYS, "evidence_digest")
        if predecessor["ordinal"] > 0 and supplied_completion["generation_digest"] != predecessor["generation_digest"]:
            prior = _closed(_load(_receipt_path(policy, predecessor["ordinal"])), RECEIPT_SCHEMA, RECEIPT_KEYS, "receipt_digest")
            if prior["completion_evidence_digest"] == supplied_completion["evidence_digest"] and prior["successor_evidence_digest"] == supplied_successor["evidence_digest"]:
                return {"schema_version":RESULT_SCHEMA, "status":"successor_generation_ready", "generation_id":predecessor["generation_id"], "generation_digest":predecessor["generation_digest"], "receipt_digest":prior["receipt_digest"], "write_status":"reused", "effects_performed":[], "runtime_adoption_performed":False, "git_operations_performed":0, "network_performed":False}
        old_manifest = profiles.validate_manifest(_load(predecessor["manifest_path"]))
        if not (_time(old_manifest["not_before"]) <= _time(evaluation_time) < _time(old_manifest["expires_at"])):
            raise ValueError("predecessor_expired_or_not_yet_valid")
        completion = _verify_completion(supplied_completion, predecessor)
        successor = _verify_successor(supplied_successor, predecessor, completion)
        ordinal = predecessor["ordinal"] + 1
        manifest = dict(old_manifest)
        manifest["base_sha"] = successor["successor_sha"]
        manifest["manifest_id"] = f"{policy['lineage_id']}-generation-{ordinal}"
        manifest["output_directory"] = str(Path(policy["generation_root"]) / f"profile-{ordinal}")
        manifest["manifest_digest"] = profiles.digest(manifest, "manifest_digest")
        if not _same_or_narrower(old_manifest, manifest): raise ValueError("successor_authority_widened")
        manifest_path = Path(policy["generation_root"]) / f"manifest-{ordinal}.json"
        _write(manifest_path, manifest)
        rendered = profiles.render_profile_bundle(manifest_path)
        verified = profiles.verify_profile_bundle(manifest_path, evaluation_time)
        if verified["status"] != "profile_bundle_ready": raise ValueError("successor_profile_invalid")
        generation = {"schema_version":GENERATION_SCHEMA, "generation_id":f"{policy['lineage_id']}:generation:{ordinal}", "generation_digest":"", "lineage_id":policy["lineage_id"], "ordinal":ordinal, "base_sha":successor["successor_sha"], "manifest_path":str(manifest_path), "manifest_digest":manifest["manifest_digest"], "profile_bundle_digest":rendered["bundle_digest"], "predecessor_generation_digest":predecessor["generation_digest"], "prior_receipt_digest":"", "created_at":evaluation_time}
        receipt = {"schema_version":RECEIPT_SCHEMA, "receipt_id":f"{policy['lineage_id']}:receipt:{ordinal}", "receipt_digest":"", "lineage_id":policy["lineage_id"], "ordinal":ordinal, "predecessor_generation_digest":predecessor["generation_digest"], "predecessor_base_sha":predecessor["base_sha"], "completed_task_id":completion["task_id"], "completion_evidence_digest":completion["evidence_digest"], "validation_evidence_digest":completion["validation_evidence_digest"], "commit_evidence_digest":completion["commit_evidence_digest"], "landing_evidence_digest":completion["landing_evidence_digest"], "closure_evidence_digest":completion["closure_evidence_digest"], "successor_evidence_digest":successor["evidence_digest"], "successor_classification":"exact_local_fast_forward_base_ref", "successor_sha":successor["successor_sha"], "same_or_narrower":True, "successor_manifest_digest":manifest["manifest_digest"], "successor_profile_bundle_digest":rendered["bundle_digest"], "successor_generation_digest":"", "prior_receipt_digest":predecessor["prior_receipt_digest"], "created_at":evaluation_time}
        # The receipt owns the transition; generation points to that receipt. Avoid a digest cycle.
        generation["generation_digest"] = _generation_digest(generation)
        receipt["successor_generation_digest"] = generation["generation_digest"]
        receipt["receipt_digest"] = digest(receipt, "receipt_digest")
        generation["prior_receipt_digest"] = receipt["receipt_digest"]
        _write(_receipt_path(policy, ordinal), receipt)
        gs = _write(_generation_path(policy, ordinal), generation)
        return {"schema_version":RESULT_SCHEMA, "status":"successor_generation_ready", "generation_id":generation["generation_id"], "generation_digest":generation["generation_digest"], "receipt_digest":receipt["receipt_digest"], "write_status":gs, "effects_performed":["successor_maintenance_configuration_generation_write", "maintenance_authority_continuity_receipt_write"], "runtime_adoption_performed":False, "git_operations_performed":0, "network_performed":False}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {"schema_version":RESULT_SCHEMA, "status":"continuity_not_ready", "reason_codes":[str(exc)], "effects_performed":[], "runtime_adoption_performed":False, "git_operations_performed":0, "network_performed":False}


def inspect(policy_path: str | Path) -> dict[str, Any]:
    try:
        p = validate_policy(_load(policy_path)); g = _current_generation(p)
        return {"schema_version":RESULT_SCHEMA, "status":"continuity_ready", "lineage_id":p["lineage_id"], "current_generation_id":g["generation_id"], "ordinal":g["ordinal"]}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {"schema_version":RESULT_SCHEMA, "status":"continuity_blocked", "reason_codes":[str(exc)]}


def inspect_receipts(policy_path: str | Path) -> dict[str, Any]:
    result = inspect(policy_path)
    if result["status"] == "continuity_ready": result["receipt_count"] = result["ordinal"]
    return result


doctor = inspect
