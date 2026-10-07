"""Deterministic base/candidate validation comparison primitives.

Repository health is observational. This module answers only whether comparable,
complete base and candidate runs show a newly introduced failure.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re
from typing import Any, Mapping

from sentientos.forge_failures import semantic_failure_signature

SCHEMA = "sentientos.validation_causality_comparison:v1"
STATUS_NO_REGRESSION = "no_regression"
STATUS_IMPROVED = "improved"
STATUS_REGRESSION = "regression_detected"
STATUS_INCOMPLETE = "comparison_incomplete"
STATUS_BASE_INVALID = "base_evidence_invalid"
STATUS_CANDIDATE_INVALID = "candidate_evidence_invalid"
STATUS_COMMAND_MISMATCH = "command_contract_mismatch"
STATUS_ENVIRONMENT_MISMATCH = "environment_not_comparable"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_json(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def command_contract_digest(command: list[str] | tuple[str, ...]) -> str:
    normalized = ["${JUNITXML}" if item.startswith("/tmp/") and item.endswith(".xml") else str(item) for item in command]
    runner = normalized[normalized.index("-m") + 1] if "-m" in normalized and normalized.index("-m") + 1 < len(normalized) else "direct"
    return digest_json({"runner": runner, "argv": normalized})


def environment_digest(environment: Mapping[str, Any]) -> str:
    return digest_json(environment)


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _failure_rows(run: Mapping[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None]:
    rows = run.get("normalized_failure_multiset")
    if not isinstance(rows, list):
        return None, "failure_multiset_missing"
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            return None, "failure_multiset_row_invalid"
        nodeid, error_type, message = row.get("nodeid"), row.get("exception_type"), row.get("message")
        count, signature = row.get("count"), row.get("signature")
        if not isinstance(nodeid, str) or not isinstance(error_type, str) or not isinstance(message, str):
            return None, "failure_multiset_identity_invalid"
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            return None, "failure_multiset_count_invalid"
        expected = semantic_failure_signature(nodeid, error_type, message)
        if signature != expected or signature in seen:
            return None, "failure_multiset_signature_invalid"
        seen.add(signature)
        normalized.append({
            "signature": signature,
            "nodeid": nodeid,
            "exception_type": error_type,
            "message": message,
            "count": count,
        })
    return sorted(normalized, key=lambda item: item["signature"]), None


def _validate_run(
    run: object,
    *,
    expected_sha: str,
    expected_workspace_identity: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(run, Mapping):
        return None, "run_provenance_missing"
    if run.get("repository_sha") != expected_sha or not _SHA_RE.fullmatch(expected_sha):
        return None, "repository_sha_mismatch"
    workspace_identity = run.get("workspace_identity")
    if not isinstance(workspace_identity, str) or not _valid_digest(workspace_identity):
        return None, "workspace_identity_invalid"
    if expected_workspace_identity is not None and workspace_identity != expected_workspace_identity:
        return None, "candidate_workspace_identity_mismatch"
    if run.get("complete") is not True:
        return None, "run_incomplete"
    if run.get("exit_code") not in (0, 1):
        return None, "run_exit_status_invalid"
    if not isinstance(run.get("tests_collected"), int) or run["tests_collected"] <= 0:
        return None, "run_tests_not_collected"
    if not isinstance(run.get("tests_executed"), int) or run["tests_executed"] <= 0:
        return None, "run_tests_not_executed"
    if not _valid_digest(run.get("junit_sha256")):
        return None, "junit_evidence_digest_invalid"
    if not _valid_digest(run.get("command_contract_digest")):
        return None, "command_contract_digest_invalid"
    if not _valid_digest(run.get("environment_digest")):
        return None, "environment_digest_invalid"
    contract = run.get("command_contract")
    environment = run.get("environment_identity")
    if not isinstance(contract, Mapping) or not isinstance(contract.get("argv"), list):
        return None, "command_contract_missing"
    if contract.get("runner") != (contract["argv"][contract["argv"].index("-m") + 1] if "-m" in contract["argv"] and contract["argv"].index("-m") + 1 < len(contract["argv"]) else "direct"):
        return None, "command_contract_runner_invalid"
    if command_contract_digest(contract["argv"]) != run.get("command_contract_digest"):
        return None, "command_contract_digest_invalid"
    if not isinstance(environment, Mapping) or environment_digest(environment) != run.get("environment_digest"):
        return None, "environment_digest_invalid"
    rows, failure_error = _failure_rows(run)
    if rows is None:
        return None, failure_error
    failures = sum(row["count"] for row in rows)
    if failures and run.get("exit_code") == 0:
        return None, "run_exit_failure_count_contradiction"
    if not failures and run.get("exit_code") != 0:
        return None, "run_exit_failure_count_contradiction"
    return dict(run), None


def _validate_incomplete_run(
    run: object,
    *,
    expected_sha: str,
    expected_workspace_identity: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate the custody and command identity of a run that did not complete.

    Incomplete runs cannot establish failure equivalence, but their bound provenance
    can establish that both sides stopped under the same command and environment.
    """
    if not isinstance(run, Mapping):
        return None, "run_provenance_missing"
    if run.get("repository_sha") != expected_sha or not _SHA_RE.fullmatch(expected_sha):
        return None, "repository_sha_mismatch"
    workspace_identity = run.get("workspace_identity")
    if not isinstance(workspace_identity, str) or not _valid_digest(workspace_identity):
        return None, "workspace_identity_invalid"
    if expected_workspace_identity is not None and workspace_identity != expected_workspace_identity:
        return None, "candidate_workspace_identity_mismatch"
    contract = run.get("command_contract")
    environment = run.get("environment_identity")
    if not isinstance(contract, Mapping) or not isinstance(contract.get("argv"), list):
        return None, "command_contract_missing"
    argv = contract["argv"]
    expected_runner = argv[argv.index("-m") + 1] if "-m" in argv and argv.index("-m") + 1 < len(argv) else "direct"
    if contract.get("runner") != expected_runner:
        return None, "command_contract_runner_invalid"
    if not _valid_digest(run.get("command_contract_digest")) or not _valid_digest(run.get("environment_digest")):
        return None, "run_provenance_digest_invalid"
    if command_contract_digest(contract["argv"]) != run.get("command_contract_digest"):
        return None, "command_contract_digest_invalid"
    if not isinstance(environment, Mapping) or environment_digest(environment) != run.get("environment_digest"):
        return None, "environment_digest_invalid"
    rows, failure_error = _failure_rows(run)
    if rows is None:
        return None, failure_error
    return dict(run), None


def _incomplete_pair_classification(
    evidence: Mapping[str, Any],
    *,
    immutable_base_sha: str,
    candidate_sha: str,
    candidate_workspace_identity: str,
    expected_command_contract_digest: str | None,
    expected_environment_digest: str | None,
) -> dict[str, Any]:
    """Return typed incomplete evidence without promoting it to a passing result."""
    base_run, base_error = _validate_incomplete_run(
        evidence.get("base_run_provenance"), expected_sha=immutable_base_sha,
    )
    candidate_run, candidate_error = _validate_incomplete_run(
        evidence.get("candidate_run_provenance"), expected_sha=candidate_sha,
        expected_workspace_identity=candidate_workspace_identity,
    )
    if base_error or candidate_error:
        return {
            "status": STATUS_INCOMPLETE,
            "incomplete_classification": "unclassified",
            "reasons": [*([f"base:{base_error}"] if base_error else []), *([f"candidate:{candidate_error}"] if candidate_error else [])],
        }
    assert base_run is not None and candidate_run is not None
    if evidence.get("base_run_provenance_digest") != digest_json(base_run) or evidence.get("candidate_run_provenance_digest") != digest_json(candidate_run):
        return {"status": STATUS_INCOMPLETE, "incomplete_classification": "unclassified", "reasons": ["run_provenance_digest_invalid"]}
    base_tree = evidence.get("base_source_tree_sha")
    if not isinstance(base_tree, str) or not re.fullmatch(r"[0-9a-f]{40}", base_tree):
        return {"status": STATUS_BASE_INVALID, "reasons": ["base_source_tree_sha_invalid"]}
    if base_run.get("workspace_identity") != digest_json({"git_tree_sha": base_tree}):
        return {"status": STATUS_BASE_INVALID, "reasons": ["base_workspace_identity_mismatch"]}
    if base_run.get("command_contract_digest") != candidate_run.get("command_contract_digest"):
        return {"status": STATUS_COMMAND_MISMATCH, "reasons": ["base_candidate_command_contract_mismatch"]}
    if expected_command_contract_digest and base_run.get("command_contract_digest") != expected_command_contract_digest:
        return {"status": STATUS_COMMAND_MISMATCH, "reasons": ["expected_command_contract_mismatch"]}
    if base_run.get("environment_digest") != candidate_run.get("environment_digest"):
        return {"status": STATUS_ENVIRONMENT_MISMATCH, "reasons": ["base_candidate_environment_mismatch"]}
    if expected_environment_digest and base_run.get("environment_digest") != expected_environment_digest:
        return {"status": STATUS_ENVIRONMENT_MISMATCH, "reasons": ["expected_environment_mismatch"]}
    if evidence.get("command_contract_digest") != base_run.get("command_contract_digest"):
        return {"status": STATUS_INCOMPLETE, "incomplete_classification": "unclassified", "reasons": ["run_contract_binding_invalid"]}
    if evidence.get("environment_digest") != base_run.get("environment_digest"):
        return {"status": STATUS_INCOMPLETE, "incomplete_classification": "unclassified", "reasons": ["run_environment_binding_invalid"]}
    paired_timeout = all(
        run.get("complete") is False
        and run.get("exit_code") == 124
        and run.get("metrics_status") == "timed_out"
        and run.get("reporter_ok") is False
        for run in (base_run, candidate_run)
    )
    if paired_timeout:
        paired_timeout = (
            base_run.get("run_tests_timeout_seconds") == candidate_run.get("run_tests_timeout_seconds")
            and base_run.get("raw_stdout_tail") == candidate_run.get("raw_stdout_tail")
            and base_run.get("raw_stderr_tail") == candidate_run.get("raw_stderr_tail")
        )
    return {
        "status": STATUS_INCOMPLETE,
        "incomplete_classification": "paired_timeout" if paired_timeout else "unclassified",
        "comparison_digest": evidence.get("comparison_digest"),
        "immutable_base_sha": immutable_base_sha,
        "candidate_sha": candidate_sha,
        "candidate_workspace_identity": candidate_workspace_identity,
        "reasons": list(evidence.get("reasons", [])) or ["base_or_candidate_run_incomplete"],
        "command_contract_digest": base_run.get("command_contract_digest"),
        "environment_digest": base_run.get("environment_digest"),
        "base_run_provenance_digest": evidence.get("base_run_provenance_digest"),
        "candidate_run_provenance_digest": evidence.get("candidate_run_provenance_digest"),
    }


def compare_runs(
    *,
    immutable_base_sha: str,
    candidate_sha: str,
    candidate_workspace_identity: str,
    base_run: Mapping[str, Any],
    candidate_run: Mapping[str, Any],
) -> dict[str, Any]:
    """Build comparison evidence from two run provenance records."""
    base, base_error = _validate_run(base_run, expected_sha=immutable_base_sha)
    candidate, candidate_error = _validate_run(
        candidate_run,
        expected_sha=candidate_sha,
        expected_workspace_identity=candidate_workspace_identity,
    )
    incomplete_errors = {"run_incomplete", "run_tests_not_collected", "run_tests_not_executed"}
    status = (
        STATUS_INCOMPLETE if base_error in incomplete_errors or candidate_error in incomplete_errors
        else STATUS_BASE_INVALID if base_error
        else STATUS_CANDIDATE_INVALID if candidate_error
        else STATUS_INCOMPLETE
    )
    reasons: list[str] = []
    if base_error:
        reasons.append(f"base:{base_error}")
    if candidate_error:
        reasons.append(f"candidate:{candidate_error}")
    matched: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    retired: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    multiplicity: list[dict[str, Any]] = []
    command_digest = ""
    env_digest = ""
    if base is not None and candidate is not None:
        if base["command_contract_digest"] != candidate["command_contract_digest"]:
            status = STATUS_COMMAND_MISMATCH
            reasons.append("base_candidate_command_contract_mismatch")
        elif base["environment_digest"] != candidate["environment_digest"]:
            status = STATUS_ENVIRONMENT_MISMATCH
            reasons.append("base_candidate_environment_mismatch")
        else:
            command_digest = str(candidate["command_contract_digest"])
            env_digest = str(candidate["environment_digest"])
            base_rows = {row["signature"]: row for row in base["normalized_failure_multiset"]}
            candidate_rows = {row["signature"]: row for row in candidate["normalized_failure_multiset"]}
            for signature in sorted(set(base_rows) | set(candidate_rows)):
                before = base_rows.get(signature)
                after = candidate_rows.get(signature)
                if before and after:
                    common = min(before["count"], after["count"])
                    matched.append({"signature": signature, "nodeid": after["nodeid"], "count": common})
                    delta = after["count"] - before["count"]
                    if delta > 0:
                        item = {"signature": signature, "nodeid": after["nodeid"], "count": delta, "kind": "increased"}
                        new.append(item)
                        multiplicity.append({"signature": signature, "nodeid": after["nodeid"], "base_count": before["count"], "candidate_count": after["count"], "delta": delta})
                    elif delta < 0:
                        item = {"signature": signature, "nodeid": before["nodeid"], "count": -delta, "kind": "decreased"}
                        retired.append(item)
                        multiplicity.append({"signature": signature, "nodeid": before["nodeid"], "base_count": before["count"], "candidate_count": after["count"], "delta": delta})
                elif after:
                    new.append({"signature": signature, "nodeid": after["nodeid"], "count": after["count"], "kind": "new"})
                elif before:
                    retired.append({"signature": signature, "nodeid": before["nodeid"], "count": before["count"], "kind": "retired"})
            base_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
            candidate_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in base["normalized_failure_multiset"]:
                base_by_node[row["nodeid"]].append(row)
            for row in candidate["normalized_failure_multiset"]:
                candidate_by_node[row["nodeid"]].append(row)
            for nodeid in sorted(set(base_by_node) & set(candidate_by_node)):
                before_sigs = {row["signature"] for row in base_by_node[nodeid]}
                after_sigs = {row["signature"] for row in candidate_by_node[nodeid]}
                if before_sigs != after_sigs:
                    changed.append({"nodeid": nodeid, "base_signatures": sorted(before_sigs), "candidate_signatures": sorted(after_sigs)})
            status = STATUS_REGRESSION if new else STATUS_IMPROVED if retired else STATUS_NO_REGRESSION
    body: dict[str, Any] = {
        "schema_version": SCHEMA,
        "immutable_base_sha": immutable_base_sha,
        "candidate_sha": candidate_sha,
        "candidate_workspace_identity": candidate_workspace_identity,
        "command_contract_digest": command_digest or (base_run.get("command_contract_digest", "") if isinstance(base_run, Mapping) else ""),
        "environment_digest": env_digest or (base_run.get("environment_digest", "") if isinstance(base_run, Mapping) else ""),
        "base_run_provenance": dict(base_run),
        "candidate_run_provenance": dict(candidate_run),
        "base_run_provenance_digest": digest_json(base_run),
        "candidate_run_provenance_digest": digest_json(candidate_run),
        "base_failure_multiset": base.get("normalized_failure_multiset", []) if base else [],
        "candidate_failure_multiset": candidate.get("normalized_failure_multiset", []) if candidate else [],
        "matched_preexisting_failures": matched,
        "new_candidate_failures": new,
        "retired_or_improved_failures": retired,
        "changed_failure_signatures": changed,
        "failure_multiplicity_changes": multiplicity,
        "base_repository_health_status": "green" if base and base.get("exit_code") == 0 else "red" if base else "unknown",
        "candidate_repository_health_status": "green" if candidate and candidate.get("exit_code") == 0 else "red" if candidate else "unknown",
        "repository_health_status": "green" if candidate and candidate.get("exit_code") == 0 else "red" if candidate else "unknown",
        "status": status,
        "reasons": reasons,
    }
    body["comparison_digest"] = digest_json(body)
    return body


def verify_comparison(
    evidence: object,
    *,
    immutable_base_sha: str,
    candidate_sha: str,
    candidate_workspace_identity: str,
    expected_command_contract_digest: str | None = None,
    expected_environment_digest: str | None = None,
) -> dict[str, Any]:
    """Verify digest, immutable base, run lineage and comparability before use."""
    if not isinstance(evidence, Mapping) or evidence.get("schema_version") != SCHEMA:
        return {"status": STATUS_INCOMPLETE, "reasons": ["comparison_schema_invalid"]}
    raw = dict(evidence)
    digest = raw.pop("comparison_digest", None)
    if digest != digest_json(raw):
        return {"status": STATUS_INCOMPLETE, "reasons": ["comparison_digest_invalid"]}
    if evidence.get("immutable_base_sha") != immutable_base_sha:
        return {"status": STATUS_BASE_INVALID, "reasons": ["immutable_base_sha_mismatch"]}
    if evidence.get("candidate_sha") != candidate_sha:
        return {"status": STATUS_CANDIDATE_INVALID, "reasons": ["candidate_sha_mismatch"]}
    if evidence.get("candidate_workspace_identity") != candidate_workspace_identity:
        return {"status": STATUS_CANDIDATE_INVALID, "reasons": ["candidate_workspace_identity_mismatch"]}
    base_run, base_error = _validate_run(evidence.get("base_run_provenance"), expected_sha=immutable_base_sha)
    candidate_run, candidate_error = _validate_run(
        evidence.get("candidate_run_provenance"), expected_sha=candidate_sha,
        expected_workspace_identity=candidate_workspace_identity,
    )
    if base_error:
        if base_error == "run_incomplete" and evidence.get("status") == STATUS_INCOMPLETE:
            return _incomplete_pair_classification(
                evidence,
                immutable_base_sha=immutable_base_sha,
                candidate_sha=candidate_sha,
                candidate_workspace_identity=candidate_workspace_identity,
                expected_command_contract_digest=expected_command_contract_digest,
                expected_environment_digest=expected_environment_digest,
            )
        return {"status": STATUS_BASE_INVALID, "reasons": [f"base:{base_error}"]}
    if candidate_error:
        if candidate_error == "run_incomplete" and evidence.get("status") == STATUS_INCOMPLETE:
            return _incomplete_pair_classification(
                evidence,
                immutable_base_sha=immutable_base_sha,
                candidate_sha=candidate_sha,
                candidate_workspace_identity=candidate_workspace_identity,
                expected_command_contract_digest=expected_command_contract_digest,
                expected_environment_digest=expected_environment_digest,
            )
        return {"status": STATUS_CANDIDATE_INVALID, "reasons": [f"candidate:{candidate_error}"]}
    assert base_run is not None and candidate_run is not None
    if evidence.get("base_run_provenance_digest") != digest_json(base_run) or evidence.get("candidate_run_provenance_digest") != digest_json(candidate_run):
        return {"status": STATUS_INCOMPLETE, "reasons": ["run_provenance_digest_invalid"]}
    if evidence.get("base_failure_multiset") != base_run.get("normalized_failure_multiset") or evidence.get("candidate_failure_multiset") != candidate_run.get("normalized_failure_multiset"):
        return {"status": STATUS_INCOMPLETE, "reasons": ["failure_multiset_binding_invalid"]}
    if evidence.get("command_contract_digest") != base_run.get("command_contract_digest") or evidence.get("environment_digest") != base_run.get("environment_digest"):
        return {"status": STATUS_INCOMPLETE, "reasons": ["run_contract_binding_invalid"]}
    if base_run.get("command_contract_digest") != candidate_run.get("command_contract_digest"):
        return {"status": STATUS_COMMAND_MISMATCH, "reasons": ["base_candidate_command_contract_mismatch"]}
    if expected_command_contract_digest and evidence.get("command_contract_digest") != expected_command_contract_digest:
        return {"status": STATUS_COMMAND_MISMATCH, "reasons": ["expected_command_contract_mismatch"]}
    if base_run.get("environment_digest") != candidate_run.get("environment_digest"):
        return {"status": STATUS_ENVIRONMENT_MISMATCH, "reasons": ["base_candidate_environment_mismatch"]}
    if expected_environment_digest and evidence.get("environment_digest") != expected_environment_digest:
        return {"status": STATUS_ENVIRONMENT_MISMATCH, "reasons": ["expected_environment_mismatch"]}
    recomputed = compare_runs(
        immutable_base_sha=immutable_base_sha,
        candidate_sha=candidate_sha,
        candidate_workspace_identity=candidate_workspace_identity,
        base_run=base_run,
        candidate_run=candidate_run,
    )
    for key in (
        "status", "matched_preexisting_failures", "new_candidate_failures",
        "retired_or_improved_failures", "changed_failure_signatures",
        "failure_multiplicity_changes", "base_repository_health_status",
        "candidate_repository_health_status", "repository_health_status",
    ):
        if evidence.get(key) != recomputed.get(key):
            return {"status": STATUS_INCOMPLETE, "reasons": [f"comparison_{key}_inconsistent"]}
    if evidence.get("status") not in {STATUS_NO_REGRESSION, STATUS_IMPROVED, STATUS_REGRESSION}:
        return {"status": str(evidence.get("status", STATUS_INCOMPLETE)), "incomplete_classification": "unclassified", "reasons": list(evidence.get("reasons", []))}
    return {
        "status": str(evidence["status"]),
        "reasons": [],
        "comparison_digest": digest,
        "immutable_base_sha": immutable_base_sha,
        "candidate_sha": candidate_sha,
        "candidate_workspace_identity": candidate_workspace_identity,
        "command_contract_digest": evidence.get("command_contract_digest"),
        "environment_digest": evidence.get("environment_digest"),
        "base_run_provenance_digest": evidence.get("base_run_provenance_digest"),
        "candidate_run_provenance_digest": evidence.get("candidate_run_provenance_digest"),
        "matched_preexisting_failures": list(evidence.get("matched_preexisting_failures", [])),
        "new_candidate_failures": list(evidence.get("new_candidate_failures", [])),
        "retired_or_improved_failures": list(evidence.get("retired_or_improved_failures", [])),
        "changed_failure_signatures": list(evidence.get("changed_failure_signatures", [])),
        "failure_multiplicity_changes": list(evidence.get("failure_multiplicity_changes", [])),
        "base_repository_health_status": evidence.get("base_repository_health_status", "unknown"),
        "candidate_repository_health_status": evidence.get("candidate_repository_health_status", "unknown"),
        "repository_health_status": evidence.get("repository_health_status", "unknown"),
    }


def run_provenance_digest(run: Mapping[str, Any]) -> str:
    return digest_json(run)
