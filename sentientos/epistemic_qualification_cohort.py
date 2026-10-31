"""Stateless summaries of model-bound epistemic qualification reports.

The summarizer groups supplied scored samples by exact case commitment and
execution identity. It does not run inference, persist a model profile, or
interpret synthetic results as real-model qualification.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .local_model_authority import digest_payload

SCHEMA = "sentientos.epistemic_qualification_cohort:v2"
MAX_REPORTS = 256
MAX_REPORT_BYTES = 1_048_576
SCORE_FIELDS = (
    "state_stance_correct", "answer_correct", "citations_correct",
)
IDENTITY_FIELDS = (
    "model_id", "model_artifact_digest", "active_model_identity_digest",
    "generation_config_digest", "evaluator_version",
)


def _canonical(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("epistemic_cohort_report_limit_exceeded")
    return encoded


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def _valid_digest(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 71 and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:]))


def _verify_report_tree(value: Any, *, path: str = "report") -> None:
    if isinstance(value, Mapping):
        supplied = value.get("report_digest")
        if supplied is not None:
            if not _valid_digest(supplied):
                raise ValueError(f"epistemic_cohort_report_digest_invalid:{path}")
            unsigned = {key: item for key, item in value.items() if key != "report_digest"}
            if _digest(unsigned) != supplied:
                raise ValueError(f"epistemic_cohort_report_digest_mismatch:{path}")
        for key, child in value.items():
            if isinstance(child, (Mapping, list, tuple)):
                _verify_report_tree(child, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _verify_report_tree(child, path=f"{path}[{index}]")


def _verify_execution_binding(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"epistemic_cohort_execution_binding_missing:{path}")
    supplied = value.get("binding_digest")
    if not _valid_digest(supplied):
        raise ValueError(f"epistemic_cohort_execution_binding_digest_invalid:{path}")
    unsigned = {key: item for key, item in value.items() if key != "binding_digest"}
    if _digest(unsigned) != supplied:
        raise ValueError(f"epistemic_cohort_execution_binding_digest_mismatch:{path}")
    if value.get("schema") != "sentientos.epistemic_execution_binding:v1":
        raise ValueError(f"epistemic_cohort_execution_binding_schema_invalid:{path}")
    return dict(value)


def _sample_outcome(pair_status: Any, sample: Mapping[str, Any], binding: Mapping[str, Any]) -> str:
    if (pair_status not in {"case_passed", "case_failed"}
            or sample.get("measurement_status") != "scored"
            or binding.get("complete") is not True):
        return "insufficient"
    scores = [sample.get(field) for field in SCORE_FIELDS]
    if not all(isinstance(score, bool) for score in scores):
        return "insufficient"
    return "scored_pass" if all(score is True for score in scores) else "scored_fail"


def _pair_nodes(value: Any, *, path: str = "report") -> list[tuple[str, Mapping[str, Any]]]:
    found: list[tuple[str, Mapping[str, Any]]] = []
    if isinstance(value, Mapping):
        before, after = value.get("before"), value.get("after")
        if (isinstance(before, Mapping) and isinstance(after, Mapping)
                and "execution_binding" in before and "execution_binding" in after):
            found.append((path, value))
        else:
            for key, child in value.items():
                if isinstance(child, (Mapping, list, tuple)):
                    found.extend(_pair_nodes(child, path=f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found.extend(_pair_nodes(child, path=f"{path}[{index}]"))
    return found


def summarize_qualification_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Group exact pair samples by committed case and observed execution identity.

    Invalid report or binding digests fail closed. A valid report remains a
    supplied claim: oracle independence, preregistration timing, and real-model
    qualification are never inferred from its digest or scores.
    """
    if not isinstance(reports, Sequence) or isinstance(reports, (str, bytes)):
        raise ValueError("epistemic_cohort_reports_must_be_a_sequence")
    if not reports or len(reports) > MAX_REPORTS:
        raise ValueError("epistemic_cohort_report_count_invalid")
    groups: dict[str, dict[str, Any]] = {}
    unattributed: list[dict[str, Any]] = []
    seen: set[str] = set()
    pair_count = 0
    for report_index, report in enumerate(reports):
        if not isinstance(report, Mapping):
            raise ValueError("epistemic_cohort_report_object_required")
        _canonical(report)
        _verify_report_tree(report)
        report_digest = report.get("report_digest")
        if not _valid_digest(report_digest):
            raise ValueError(f"epistemic_cohort_report_digest_required:{report_index}")
        assert isinstance(report_digest, str)
        if report_digest in seen:
            raise ValueError("epistemic_cohort_duplicate_report")
        seen.add(report_digest)
        schema = report.get("schema_version")
        if not isinstance(schema, str) or not schema:
            raise ValueError(f"epistemic_cohort_report_schema_unsupported:{report_index}")
        nodes = _pair_nodes(report)
        if not nodes:
            raise ValueError(f"epistemic_cohort_pair_samples_missing:{report_index}")
        for pair_path, pair in nodes:
            pair_count += 1
            case_commitment = pair.get("case_commitment")
            case_id = pair.get("case_id")
            pair_status = pair.get("status")
            commitment_valid = _valid_digest(case_commitment)
            for condition in ("before", "after"):
                sample = pair[condition]
                binding = _verify_execution_binding(sample.get("execution_binding"),
                    path=f"{report_index}:{pair_path}.{condition}")
                if (binding.get("condition") != condition
                        or binding.get("case_id") != case_id
                        or (report.get("evaluator_version") is not None
                            and binding.get("evaluator_version") != report.get("evaluator_version"))):
                    raise ValueError(
                        f"epistemic_cohort_execution_binding_context_mismatch:{report_index}:{pair_path}.{condition}")
                outcome = _sample_outcome(pair_status, sample, binding)
                identity = {field: binding.get(field) for field in IDENTITY_FIELDS}
                identity_complete = (binding.get("complete") is True
                    and all(isinstance(identity[field], str) and identity[field]
                        for field in IDENTITY_FIELDS))
                if not commitment_valid or not identity_complete:
                    unattributed.append({
                        "source_report_digest": report_digest,
                        "case_commitment": case_commitment if commitment_valid else None,
                        "case_id": case_id,
                        "condition": condition,
                        "pair_status": pair_status,
                        "sample_outcome": "insufficient",
                        "execution_binding_digest": binding["binding_digest"],
                    })
                    continue
                group_payload = {"case_commitment": case_commitment, **identity}
                group_id = _digest(group_payload)
                group = groups.setdefault(group_id, {
                    "group_id": group_id,
                    "case_commitment": case_commitment,
                    "case_id": case_id,
                    "execution_identity": identity,
                    "sample_count": 0,
                    "sample_outcomes": {"scored_pass": 0, "scored_fail": 0, "insufficient": 0},
                    "pair_status_counts": {},
                    "conditions": {"before": 0, "after": 0},
                    "source_report_digests": [],
                    "samples": [],
                })
                if group["case_id"] != case_id:
                    raise ValueError("epistemic_cohort_case_id_commitment_conflict")
                group["sample_count"] += 1
                group["sample_outcomes"][outcome] += 1
                group["pair_status_counts"][str(pair_status)] = (
                    group["pair_status_counts"].get(str(pair_status), 0) + 1)
                group["conditions"][condition] += 1
                if report_digest not in group["source_report_digests"]:
                    group["source_report_digests"].append(report_digest)
                group["samples"].append({
                    "source_report_digest": report_digest,
                    "condition": condition,
                    "pair_status": pair_status,
                    "sample_outcome": outcome,
                    "execution_status": sample.get("execution_status"),
                    "execution_binding_digest": binding["binding_digest"],
                })
    ordered = [groups[key] for key in sorted(groups)]
    for group in ordered:
        group["source_report_digests"].sort()
        group["samples"].sort(key=lambda row: (
            row["source_report_digest"], row["condition"], row["execution_binding_digest"]))
    unattributed.sort(key=lambda row: (
        str(row["source_report_digest"]), str(row["condition"]),
        str(row["execution_binding_digest"])))
    payload = {
        "schema_version": SCHEMA,
        "status": "cohort_summary_ready",
        "input_report_count": len(reports),
        "paired_result_count": pair_count,
        "group_count": len(ordered),
        "groups": ordered,
        "unattributed_samples": unattributed,
        "oracle_independence_verified": False,
        "preregistration_timing_verified": False,
        "real_model_qualification_established": False,
        "causal_claim_made": False,
        "authority": False,
        "persistent_storage_performed": False,
        "provider_calls_performed": False,
    }
    return {**payload, "summary_digest": _digest(payload)}


__all__ = ["MAX_REPORTS", "SCHEMA", "summarize_qualification_reports"]
