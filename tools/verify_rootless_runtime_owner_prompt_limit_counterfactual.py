"""Verify a same-source CPU counterfactual for required-history prompt budgeting."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from work.rootless_history_boundary_campaign import (  # noqa: E402
    verify_experiment_implementation,
)


class VerificationError(ValueError):
    """Raised when paired preview evidence is inconsistent."""


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError("counterfactual_artifact_not_object")
    return value


def _semantic_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise VerificationError(code)


def verify(*, plan_path: Path, wide_preview_path: Path,
        counterfactual_path: Path) -> dict[str, Any]:
    plan = _read_object(plan_path)
    wide = _read_object(wide_preview_path)
    low = _read_object(counterfactual_path)

    plan_digest = plan.get("plan_digest")
    implementation = verify_experiment_implementation(plan)
    _require(implementation.get("experiment_implementation_matches_current") is True,
        "counterfactual_plan_implementation_not_current")
    implementation_digest = wide.get("implementation_digest")
    _require(isinstance(implementation_digest, str)
        and implementation_digest == low.get("current_implementation_digest")
        and implementation_digest
            == implementation.get("experiment_implementation_digest"),
        "counterfactual_implementation_binding_mismatch")
    _require(plan.get("task_family_id")
        == "rootless_integer_affine_transfer_wide_range_v7"
        and isinstance(plan.get("cross_range_history_enabled_competence"), dict),
        "counterfactual_transfer_protocol_not_bound")
    _require(plan_digest == wide.get("plan_digest")
        and plan_digest == low.get("plan_digest"),
        "counterfactual_plan_binding_mismatch")
    _require(wide.get("cycle_id") == low.get("cycle_id")
        and wide.get("campaign_id") == low.get("campaign_id"),
        "counterfactual_cycle_binding_mismatch")

    wide_limit = wide.get("prompt_limit_chars")
    old = low.get("old_limit_replay")
    baseline = low.get("wide_limit_success")
    _require(type(wide_limit) is int and type(old) is dict
        and type(baseline) is dict,
        "counterfactual_limit_rows_invalid")
    old_limit = old.get("limit_chars")
    _require(type(old_limit) is int and old_limit < wide_limit
        and baseline.get("limit_chars") == wide_limit,
        "counterfactual_limits_invalid")
    _require(type(baseline.get("present_chars")) is int
        and type(baseline.get("restored_chars")) is int
        and baseline["present_chars"] < wide_limit
        and baseline["restored_chars"] < wide_limit
        and baseline["present_chars"] > old_limit
        and baseline["restored_chars"] > old_limit,
        "counterfactual_prompt_bounds_not_discriminating")

    condition_ids = wide.get("condition_selected_record_ids")
    prompt_sizes = wide.get("condition_prompt_sizes")
    _require(type(condition_ids) is dict and type(prompt_sizes) is dict,
        "counterfactual_wide_condition_rows_invalid")
    present_ids = condition_ids.get("history_present")
    restored_ids = condition_ids.get("history_restored")
    withheld_ids = condition_ids.get("history_withheld")
    _require(type(present_ids) is list and present_ids
        and present_ids == restored_ids and withheld_ids == [],
        "counterfactual_wide_selection_invalid")
    _require(present_ids == baseline.get("selected_record_ids"),
        "counterfactual_wide_selected_ids_mismatch")
    _require(prompt_sizes.get("history_present", {}).get("prompt_chars")
        == baseline.get("present_chars")
        and prompt_sizes.get("history_restored", {}).get("prompt_chars")
        == baseline.get("restored_chars"),
        "counterfactual_wide_prompt_size_mismatch")

    expected_ids = old.get("expected_record_ids")
    actual_ids = old.get("selected_record_ids")
    _require(type(expected_ids) is list and expected_ids == present_ids
        and type(actual_ids) is list and actual_ids,
        "counterfactual_low_selection_invalid")
    missing_ids = [record_id for record_id in expected_ids
        if record_id not in actual_ids]
    _require(len(missing_ids) == 1
        and all(record_id in expected_ids for record_id in actual_ids)
        and old.get("status") == "required_history_binding_mismatch",
        "counterfactual_low_failure_not_reproduced")
    expected_digests = old.get("expected_record_digests")
    selected_digests = old.get("selected_record_digests")
    valid_digest_list = lambda values: (type(values) is list
        and all(isinstance(value, str) and len(value) == 71
            and value.startswith("sha256:")
            and all(character in "0123456789abcdef" for character in value[7:])
            for value in values))
    _require(valid_digest_list(expected_digests)
        and len(expected_digests) == len(expected_ids)
        and valid_digest_list(selected_digests)
        and len(selected_digests) == len(actual_ids)
        and all(isinstance(record_id, str) and len(record_id) == 31
            and record_id.startswith("devrec-")
            for record_id in expected_ids)
        and len(set(expected_ids)) == len(expected_ids)
        and actual_ids == [record_id for record_id in expected_ids
            if record_id in set(actual_ids)],
        "counterfactual_record_digest_bindings_invalid")
    expected_digest_by_id = dict(zip(expected_ids, expected_digests))
    _require(selected_digests == [expected_digest_by_id[record_id]
        for record_id in actual_ids],
        "counterfactual_selected_record_digest_mismatch")

    _require(low.get("only_changed_variable")
        == "runtime owner preview maximum input characters",
        "counterfactual_variable_scope_invalid")
    _require(all(value is False for value in (
        wide.get("inference_performed"), wide.get("learning_established"),
        wide.get("authority"), wide.get("owner_state_mutated"),
        low.get("inference_performed"), low.get("learning_established"),
        low.get("authority"))),
        "counterfactual_no_inference_posture_invalid")

    digest_payload = {
        "plan_digest": plan_digest,
        "implementation_digest": implementation_digest,
        "wide_prompt_limit": wide_limit,
        "old_prompt_limit": old_limit,
        "detail": {
            "actual_ids": actual_ids,
            "actual_digests": old["selected_record_digests"],
            "expected_ids": expected_ids,
            "expected_digests": old["expected_record_digests"],
            "objective_condition_request_count": old.get(
                "objective_condition_request_count"),
            "request_count": old.get("request_count"),
            "inference_performed": False,
        },
    }
    recomputed_audit_digest = _semantic_digest(digest_payload)
    _require(low.get("audit_digest") == recomputed_audit_digest,
        "counterfactual_audit_digest_mismatch")

    return {
        "status": "verified",
        "schema_version": low.get("schema_version"),
        "plan_digest": plan_digest,
        "implementation_digest": implementation_digest,
        "wide_prompt_limit_chars": wide_limit,
        "old_prompt_limit_chars": old_limit,
        "wide_prompt_chars": baseline["present_chars"],
        "required_record_count": len(expected_ids),
        "low_limit_selected_record_count": len(actual_ids),
        "omitted_required_record_ids": missing_ids,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
        "report_origin_attested": False,
        "audit_digest": recomputed_audit_digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--wide-preview", type=Path, required=True)
    parser.add_argument("--counterfactual", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(plan_path=args.plan,
            wide_preview_path=args.wide_preview,
            counterfactual_path=args.counterfactual)
    except Exception as exc:
        print(json.dumps({"status": "invalid",
            "reason": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
