from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


SCHEMA_VERSION = "sentientos.landing_validation_plan:v1"
VALIDATION_PROFILES = ("solo", "exhaustive")
SOLO_MATRIX_STATUS = "not_requested_for_solo_profile"
EXHAUSTIVE_MATRIX_STATUSES = {
    "matrix_passed", "matrix_failed", "matrix_timed_out", "matrix_resumed", "matrix_reused",
}


def canonical_digest(payload: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "artifact_digest"}
    encoded = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def seal_validation_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    plan = dict(payload)
    plan["schema_version"] = SCHEMA_VERSION
    plan["artifact_digest"] = canonical_digest(plan)
    return plan


def verify_validation_plan(plan: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if plan.get("schema_version") != SCHEMA_VERSION:
        reasons.append("validation_plan_schema_invalid")
    requested = str(plan.get("requested_profile", ""))
    effective = str(plan.get("effective_profile", ""))
    if requested not in VALIDATION_PROFILES or effective != requested:
        reasons.append("validation_profile_invalid_or_mutated")
    matrix_status = str(plan.get("exhaustive_matrix_status", ""))
    if effective == "solo" and matrix_status != SOLO_MATRIX_STATUS:
        reasons.append("solo_matrix_status_inconsistent")
    if effective == "exhaustive" and matrix_status not in EXHAUSTIVE_MATRIX_STATUSES:
        reasons.append("exhaustive_matrix_status_inconsistent")
    stages = plan.get("stage_results", {})
    if not isinstance(stages, Mapping):
        reasons.append("validation_stage_results_invalid")
    else:
        for stage in plan.get("required_stage_ids", []):
            result = stages.get(stage)
            if not isinstance(result, Mapping) or result.get("status") != "passed":
                reasons.append(f"required_stage_not_passed:{stage}")
    if plan.get("artifact_digest") != canonical_digest(plan):
        reasons.append("validation_plan_digest_mismatch")
    return not reasons, tuple(reasons)
