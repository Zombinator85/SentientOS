"""Non-promoting acceptance of a reviewed durable-learning state boundary.

This contract is deliberately separate from the bounded sentinel-access review.
It verifies content-addressed inventories and reviewer disposition; it does not
enable worker mutation or establish process/filesystem isolation by itself.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping

from .local_model_authority import digest_payload

SCHEMA = "sentientos.durable_learning_boundary_acceptance:v1"
ARTIFACT_PREFIX = "devexp-durable-learning-boundary-acceptance-"
CONDITIONS = (
    "relevant_experience_available",
    "relevant_experience_withheld",
)
STATE_CATEGORIES = ("filesystem", "registry", "profile", "service", "recovery", "history")
CRITERIA = (
    "protocol_worker_host_binding", "process_pair_binding",
    "inherited_handle_completeness", "broker_capability_completeness",
    "persistent_state_completeness", "scorer_custody",
    "recovery_boundary", "independent_review",
)
CLAIM_LIMITS = {
    "process_isolation_verified": False,
    "filesystem_isolation_verified": False,
    "retention_contrast_eligible": False,
    "worker_mutation_eligible": False,
    "model_attention_established": False,
    "performance_improvement_established": False,
    "reviewer_identity_authenticated": False,
    "reviewer_independence_authenticated": False,
    "learning_established": False,
    "authority": False,
}
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX.fullmatch(value) is None:
        raise ValueError(code)
    return value


def _ref(value: Any) -> dict[str, str]:
    if (not isinstance(value, Mapping)
            or set(value) != {"artifact_id", "artifact_digest"}
            or not isinstance(value.get("artifact_id"), str)
            or not value["artifact_id"] or len(value["artifact_id"]) > 256):
        raise ValueError("durable_learning_boundary_artifact_ref_invalid")
    return {"artifact_id": value["artifact_id"],
        "artifact_digest": _digest(value.get("artifact_digest"),
            "durable_learning_boundary_artifact_digest_invalid")}


def _verify_source(ref_value: Any, sources: Mapping[str, Any], *,
        schema_version: str | None = None) -> Mapping[str, Any]:
    ref = _ref(ref_value)
    source = sources.get(ref["artifact_id"])
    if (not isinstance(source, Mapping)
            or source.get("artifact_id") != ref["artifact_id"]
            or source.get("artifact_digest") != ref["artifact_digest"]
            or (schema_version is not None
                and source.get("schema_version") != schema_version)):
        raise ValueError("durable_learning_boundary_source_artifact_missing_or_mismatched")
    semantic = {key: value for key, value in source.items()
        if key not in {"artifact_id", "artifact_digest"}}
    if digest_payload(semantic) != ref["artifact_digest"]:
        raise ValueError("durable_learning_boundary_source_artifact_digest_invalid")
    return source


def _closed_source(source: Mapping[str, Any], *,
        payload_fields: set[str], code: str) -> None:
    if set(source) != payload_fields | {
            "schema_version", "artifact_id", "artifact_digest"}:
        raise ValueError(code)


def _verify_protocol_source(ref_value: Any, sources: Mapping[str, Any]
        ) -> Mapping[str, Any]:
    """Reload a stored protocol and use its canonical owner verifier."""
    ref = _ref(ref_value)
    source = sources.get(ref["artifact_id"])
    if (not isinstance(source, Mapping)
            or source.get("protocol_id") != ref["artifact_id"]
            or source.get("protocol_digest") != ref["artifact_digest"]):
        raise ValueError("durable_learning_boundary_protocol_source_mismatch")
    from .durable_developmental_learning_experiment import (
        verify_durable_learning_protocol)
    verify_durable_learning_protocol(source)
    return source


def _condition_refs(value: Any, *, field: str) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != set(CONDITIONS):
        raise ValueError("durable_learning_boundary_condition_refs_invalid:" + field)
    return {condition: _ref(value[condition]) for condition in CONDITIONS}


def _referenced_artifact_ids(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        if set(value) == {"artifact_id", "artifact_digest"}:
            return {str(value["artifact_id"])}
        result: set[str] = set()
        for item in value.values():
            result.update(_referenced_artifact_ids(item))
        return result
    if isinstance(value, (list, tuple)):
        result: set[str] = set()
        for item in value:
            result.update(_referenced_artifact_ids(item))
        return result
    return set()


def _source_pointer_exists(source: Any, pointer: str) -> bool:
    if not pointer.startswith("/"):
        return False
    current = source
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and token in current:
            current = current[token]
        elif (isinstance(current, list) and token.isdigit()
                and int(token) < len(current)):
            current = current[int(token)]
        else:
            return False
    return True


def _verify_inventory(source: Mapping[str, Any], *, condition: str,
        expected_schema: str, protocol_digest: str,
        worker_digest: str | None = None, category: str | None = None) -> None:
    if (source.get("schema_version") != expected_schema
            or source.get("condition") != condition
            or source.get("protocol_digest") != protocol_digest
            or source.get("inventory_complete") is not True
            or type(source.get("unclassified_count")) is not int
            or source["unclassified_count"] != 0
            or not isinstance(source.get("entries"), list)
            or type(source.get("entry_count")) is not int
            or source["entry_count"] != len(source["entries"])
            or not isinstance(source.get("inventory_scope"), list)
            or not source["inventory_scope"]
            or any(not isinstance(item, str) or not item
                for item in source["inventory_scope"])
            or len(set(source["inventory_scope"])) !=
                len(source["inventory_scope"])
            or source["inventory_scope"] != sorted(source["inventory_scope"])
            or source.get("inventory_scope_digest") != digest_payload({
                "inventory_scope": source["inventory_scope"]})):
        raise ValueError("durable_learning_boundary_inventory_incomplete")
    entry_digests: list[str] = []
    for entry in source["entries"]:
        if (not isinstance(entry, Mapping)
                or set(entry) != {"entry_digest", "classification",
                    "cross_condition_reachable"}
                or not isinstance(entry.get("classification"), str)
                or not entry["classification"]
                or type(entry.get("cross_condition_reachable")) is not bool):
            raise ValueError("durable_learning_boundary_inventory_entry_invalid")
        entry_digests.append(_digest(entry.get("entry_digest"),
            "durable_learning_boundary_inventory_entry_digest_invalid"))
    if entry_digests != sorted(entry_digests) or len(set(entry_digests)) != len(entry_digests):
        raise ValueError("durable_learning_boundary_inventory_entry_order_invalid")
    if any(entry["cross_condition_reachable"] for entry in source["entries"]):
        raise ValueError("durable_learning_boundary_cross_condition_path_present")
    if "state_content_digest" in source and source["state_content_digest"] != digest_payload({
            "entries": [dict(entry) for entry in source["entries"]]}):
        raise ValueError("durable_learning_boundary_state_content_digest_mismatch")
    if worker_digest is not None and source.get("worker_executable_digest") != worker_digest:
        raise ValueError("durable_learning_boundary_worker_digest_mismatch")
    if category is not None and source.get("category") != category:
        raise ValueError("durable_learning_boundary_state_category_mismatch")


def _verify_semantic(value: Any, *, sources: Mapping[str, Any]
        ) -> dict[str, Any]:
    fields = {"schema_version", "protocol", "host", "condition_pair",
        "worker_executables", "process_launches", "inherited_handles",
        "broker_capabilities", "persistent_state", "scorer_custody",
        "bounded_access_review", "reviewer", "disposition", "criteria",
        "claim_limits", "summary", "authority"}
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema_version") != SCHEMA
            or value.get("authority") is not False):
        raise ValueError("durable_learning_boundary_shape_invalid")

    protocol_ref = _ref(value.get("protocol"))
    protocol = _verify_protocol_source(protocol_ref, sources)
    protocol_id = protocol_ref["artifact_id"]
    protocol_digest = protocol_ref["artifact_digest"]

    host = value.get("host")
    if (not isinstance(host, Mapping)
            or set(host) != {"host_identity", "os_build"}
            or any(not isinstance(host.get(k), str) or not host[k]
                or len(host[k]) > 256 for k in host)):
        raise ValueError("durable_learning_boundary_host_invalid")

    pair = value.get("condition_pair")
    if (not isinstance(pair, Mapping) or set(pair) != set(CONDITIONS)
            or any(not isinstance(pair[c], str) or not pair[c]
                or len(pair[c]) > 256 for c in CONDITIONS)
            or pair[CONDITIONS[0]] == pair[CONDITIONS[1]]):
        raise ValueError("durable_learning_boundary_condition_pair_invalid")
    if protocol.get("condition_contract", {}).get("condition_branch_ids") != dict(pair):
        raise ValueError("durable_learning_boundary_pair_not_preregistered")

    worker_refs = _condition_refs(value.get("worker_executables"),
        field="worker_executables")
    workers: dict[str, Mapping[str, Any]] = {}
    worker_digests: dict[str, str] = {}
    for condition in CONDITIONS:
        worker = _verify_source(worker_refs[condition], sources,
            schema_version="sentientos.durable_learning_worker_executable:v1")
        _closed_source(worker, payload_fields={"condition", "protocol_id",
            "protocol_digest", "executable_sha256", "artifact_size_bytes",
            "file_identity_digest"},
            code="durable_learning_boundary_worker_shape_invalid")
        digest = _digest(worker.get("executable_sha256"),
            "durable_learning_boundary_worker_digest_invalid")
        _digest(worker.get("file_identity_digest"),
            "durable_learning_boundary_worker_file_identity_invalid")
        if (worker.get("condition") != condition
                or type(worker.get("artifact_size_bytes")) is not int
                or worker["artifact_size_bytes"] <= 0):
            raise ValueError("durable_learning_boundary_worker_condition_mismatch")
        if (worker.get("protocol_id") != protocol_id
                or worker.get("protocol_digest") != protocol_digest):
            raise ValueError("durable_learning_boundary_worker_protocol_mismatch")
        worker_digests[condition] = digest
        workers[condition] = worker

    launch_refs = _condition_refs(value.get("process_launches"),
        field="process_launches")
    launches: dict[str, Mapping[str, Any]] = {}
    process_identities: set[tuple[Any, ...]] = set()
    for condition in CONDITIONS:
        launch = _verify_source(launch_refs[condition], sources,
            schema_version="sentientos.durable_learning_worker_process_observation:v1")
        _closed_source(launch, payload_fields={"condition", "protocol_id",
            "protocol_digest", "worker_executable_digest", "host_identity",
            "os_build", "branch_id", "launch_configuration_digest",
            "launch_configuration", "process_identity", "terminal_status",
            "process_exit_code", "inherited_handles_artifact_digest",
            "broker_capabilities_artifact_digest"},
            code="durable_learning_boundary_process_shape_invalid")
        identity = launch.get("process_identity")
        if (launch.get("condition") != condition
                or launch.get("protocol_id") != protocol_id
                or launch.get("protocol_digest") != protocol_digest
                or launch.get("worker_executable_digest") != worker_digests[condition]
                or launch.get("host_identity") != host["host_identity"]
                or launch.get("os_build") != host["os_build"]
                or launch.get("branch_id") != pair[condition]
                or not isinstance(launch.get("launch_configuration_digest"), str)
                or _HEX.fullmatch(launch["launch_configuration_digest"]) is None
                or not isinstance(launch.get("launch_configuration"), Mapping)
                or digest_payload(dict(launch["launch_configuration"])) !=
                    launch["launch_configuration_digest"]
                or launch.get("terminal_status") != "natural_zero_exit"
                or type(launch.get("process_exit_code")) is not int
                or launch.get("process_exit_code") != 0
                or not isinstance(identity, Mapping)
                or set(identity) != {"pid", "process_start_nonce", "image_digest"}
                or type(identity.get("pid")) is not int or identity["pid"] <= 0
                or not isinstance(identity.get("process_start_nonce"), str)
                or not identity["process_start_nonce"]
                or identity.get("image_digest") != worker_digests[condition]):
            raise ValueError("durable_learning_boundary_process_binding_invalid")
        identity_key = (identity["pid"], identity["process_start_nonce"])
        if identity_key in process_identities:
            raise ValueError("durable_learning_boundary_process_identity_reused")
        process_identities.add(identity_key)
        launches[condition] = launch

    capability_scope_digests: dict[str, str] = {}
    for field, schema in (
            ("inherited_handles", "sentientos.durable_learning_inherited_handle_inventory:v1"),
            ("broker_capabilities", "sentientos.durable_learning_broker_capability_inventory:v1")):
        refs = _condition_refs(value.get(field), field=field)
        for condition in CONDITIONS:
            inventory = _verify_source(refs[condition], sources, schema_version=schema)
            _closed_source(inventory, payload_fields={"condition", "protocol_digest",
                "worker_executable_digest", "host_identity", "os_build",
                "process_identity", "inventory_complete", "unclassified_count",
                "entries", "entry_count", "cross_condition_capability_count",
                "inventory_scope", "inventory_scope_digest"},
                code="durable_learning_boundary_capability_inventory_shape_invalid")
            _verify_inventory(inventory, condition=condition,
                expected_schema=schema, protocol_digest=protocol_digest,
                worker_digest=worker_digests[condition])
            scope_digest = _digest(inventory.get("inventory_scope_digest"),
                "durable_learning_boundary_capability_scope_digest_invalid")
            prior_scope_digest = capability_scope_digests.setdefault(
                field, scope_digest)
            if prior_scope_digest != scope_digest:
                raise ValueError(
                    "durable_learning_boundary_capability_scope_asymmetric")
            if (inventory.get("host_identity") != host["host_identity"]
                    or inventory.get("os_build") != host["os_build"]
                    or inventory.get("process_identity") !=
                        launches[condition]["process_identity"]
                    or launches[condition].get(
                        "inherited_handles_artifact_digest" if field == "inherited_handles"
                        else "broker_capabilities_artifact_digest") !=
                            refs[condition]["artifact_digest"]
                    or type(inventory.get("cross_condition_capability_count")) is not int
                    or inventory["cross_condition_capability_count"] != 0):
                raise ValueError("durable_learning_boundary_capability_inventory_invalid")

    state_refs = value.get("persistent_state")
    if not isinstance(state_refs, Mapping) or set(state_refs) != set(CONDITIONS):
        raise ValueError("durable_learning_boundary_state_refs_invalid")
    state_scope_digests: dict[str, str] = {}
    state_content_digests: dict[str, str] = {}
    history_baseline_record_digests: list[str] | None = None
    for condition in CONDITIONS:
        categories = state_refs[condition]
        if not isinstance(categories, Mapping) or set(categories) != set(STATE_CATEGORIES):
            raise ValueError("durable_learning_boundary_state_categories_incomplete")
        for category in STATE_CATEGORIES:
            inventory = _verify_source(categories[category], sources,
                schema_version="sentientos.durable_learning_persistent_state_inventory:v1")
            state_fields = {"condition", "protocol_digest",
                "worker_executable_digest", "host_identity", "os_build",
                "branch_id", "process_identity", "category", "inventory_complete",
                "unclassified_count", "entries", "entry_count",
                "inventory_scope", "inventory_scope_digest", "state_content_digest"}
            if category == "recovery":
                state_fields |= {"cross_condition_recovery_reference_count",
                    "unresolved_recovery_intent_count"}
            if category == "history":
                state_fields |= {"baseline_history_state_digest",
                    "preregistered_experience_digests",
                    "condition_experience_delta_digests",
                    "baseline_record_digests"}
            _closed_source(inventory, payload_fields=state_fields,
                code="durable_learning_boundary_state_inventory_shape_invalid")
            _verify_inventory(inventory, condition=condition,
                expected_schema="sentientos.durable_learning_persistent_state_inventory:v1",
                protocol_digest=protocol_digest, worker_digest=worker_digests[condition],
                category=category)
            if (inventory.get("host_identity") != host["host_identity"]
                    or inventory.get("os_build") != host["os_build"]
                    or inventory.get("branch_id") != pair[condition]
                    or inventory.get("process_identity") !=
                        launches[condition]["process_identity"]):
                raise ValueError("durable_learning_boundary_state_inventory_binding_invalid")
            if (category == "recovery"
                    and (type(inventory.get(
                            "cross_condition_recovery_reference_count")) is not int
                        or inventory["cross_condition_recovery_reference_count"] != 0
                        or type(inventory.get("unresolved_recovery_intent_count")) is not int
                        or inventory["unresolved_recovery_intent_count"] != 0)):
                raise ValueError("durable_learning_boundary_recovery_inventory_invalid")
            state_digest = _digest(inventory.get("state_content_digest"),
                "durable_learning_boundary_state_content_digest_invalid")
            scope_digest = _digest(inventory.get("inventory_scope_digest"),
                "durable_learning_boundary_state_scope_digest_invalid")
            prior_scope_digest = state_scope_digests.setdefault(category, scope_digest)
            if prior_scope_digest != scope_digest:
                raise ValueError("durable_learning_boundary_state_scope_asymmetric")
            if category == "history":
                expected_experiences = (list(protocol.get(
                    "acquisition_experience_digests", ()))
                    if condition == CONDITIONS[0] else [])
                observed_delta = inventory.get(
                    "condition_experience_delta_digests")
                baseline_records = inventory.get("baseline_record_digests")
                if (not isinstance(baseline_records, list)
                        or any(not isinstance(item, str)
                            or _HEX.fullmatch(item) is None
                            for item in baseline_records)
                        or baseline_records != sorted(set(baseline_records))):
                    raise ValueError(
                        "durable_learning_boundary_history_baseline_inventory_invalid")
                if history_baseline_record_digests is None:
                    history_baseline_record_digests = list(baseline_records)
                elif history_baseline_record_digests != baseline_records:
                    raise ValueError(
                        "durable_learning_boundary_history_baseline_asymmetric")
                baseline_entries = sorted(entry["entry_digest"] for entry in
                    inventory["entries"]
                    if entry["classification"] == "baseline_record")
                experience_entries = sorted(entry["entry_digest"] for entry in
                    inventory["entries"]
                    if entry["classification"] == "preregistered_experience")
                if any(entry["classification"] not in {
                        "baseline_record", "preregistered_experience"}
                        for entry in inventory["entries"]):
                    raise ValueError(
                        "durable_learning_boundary_history_entry_classification_invalid")
                if (inventory.get("baseline_history_state_digest") !=
                        protocol.get("baseline_history_state_digest")
                        or baseline_entries != baseline_records
                        or inventory.get("preregistered_experience_digests") !=
                            expected_experiences
                        or not isinstance(observed_delta, list)
                        or any(not isinstance(item, str)
                            or _HEX.fullmatch(item) is None
                            for item in observed_delta)
                        or observed_delta != expected_experiences):
                    raise ValueError(
                        "durable_learning_boundary_history_state_not_preregistered")
                if experience_entries != sorted(expected_experiences):
                    raise ValueError(
                        "durable_learning_boundary_history_delta_inventory_mismatch")
            else:
                prior_state_digest = state_content_digests.setdefault(
                    category, state_digest)
                if prior_state_digest != state_digest:
                    raise ValueError(
                        "durable_learning_boundary_state_content_asymmetric")

    scorer = _verify_source(value.get("scorer_custody"), sources,
        schema_version="sentientos.durable_learning_scorer_custody_inventory:v1")
    _closed_source(scorer, payload_fields={"protocol_id", "protocol_digest",
        "host_identity", "os_build", "inventory_complete", "unclassified_count",
        "answer_key_inaccessible_to_workers", "scorer_identity_distinct_from_workers",
        "condition_worker_can_reach_scorer"},
        code="durable_learning_boundary_scorer_inventory_shape_invalid")
    if (scorer.get("protocol_id") != protocol_id
            or scorer.get("protocol_digest") != protocol_digest
            or scorer.get("host_identity") != host["host_identity"]
            or scorer.get("os_build") != host["os_build"]
            or scorer.get("inventory_complete") is not True
            or type(scorer.get("unclassified_count")) is not int
            or scorer["unclassified_count"] != 0
            or scorer.get("answer_key_inaccessible_to_workers") is not True
            or scorer.get("scorer_identity_distinct_from_workers") is not True
            or scorer.get("condition_worker_can_reach_scorer") != {
                CONDITIONS[0]: False, CONDITIONS[1]: False}):
        raise ValueError("durable_learning_boundary_scorer_custody_invalid")

    access_review = _verify_source(value.get("bounded_access_review"), sources,
        schema_version="sentientos.durable_learning_host_acceptance_review:v1")
    from .durable_learning_host_acceptance_review import (
        verify_host_acceptance_review)
    access_review = verify_host_acceptance_review(access_review)
    if (access_review.get("disposition") != "accepted_bounded_access_observation"
            or access_review.get("bounded_access_observation_accepted") is not True
            or access_review.get("protocol") != protocol_ref
            or access_review.get("host", {}).get("host_identity") != host["host_identity"]
            or access_review.get("host", {}).get("os_build") != host["os_build"]):
        raise ValueError("durable_learning_boundary_access_review_insufficient")

    reviewer = value.get("reviewer")
    if (not isinstance(reviewer, Mapping)
            or set(reviewer) != {"identity", "role", "run_operator_identity",
                "independent_from_run_operator", "reviewed_at"}
            or any(not isinstance(reviewer.get(k), str) or not reviewer[k]
                or len(reviewer[k]) > 256 for k in ("identity", "role",
                    "run_operator_identity"))
            or reviewer.get("role") != "independent_boundary_reviewer"
            or reviewer.get("independent_from_run_operator") is not True
            or reviewer["identity"].strip().casefold() ==
                reviewer["run_operator_identity"].strip().casefold()
            or not isinstance(reviewer.get("reviewed_at"), str)
            or not reviewer["reviewed_at"]):
        raise ValueError("durable_learning_boundary_reviewer_invalid")
    try:
        review_time = datetime.fromisoformat(reviewer["reviewed_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("durable_learning_boundary_review_time_invalid") from exc
    if review_time.tzinfo is None or review_time.utcoffset() is None:
        raise ValueError("durable_learning_boundary_review_time_invalid")

    disposition = value.get("disposition")
    if disposition not in {"accepted_complete_boundary", "rejected", "insufficient_evidence"}:
        raise ValueError("durable_learning_boundary_disposition_invalid")
    criteria = value.get("criteria")
    if not isinstance(criteria, Mapping) or set(criteria) != set(CRITERIA):
        raise ValueError("durable_learning_boundary_criteria_invalid")
    checked_criteria: dict[str, dict[str, Any]] = {}
    for criterion in CRITERIA:
        row = criteria[criterion]
        if (not isinstance(row, Mapping) or set(row) != {"status", "evidence_refs", "finding"}
                or row.get("status") not in {"accepted", "rejected", "insufficient"}
                or not isinstance(row.get("evidence_refs"), list)
                or not 1 <= len(row["evidence_refs"]) <= 32
                or any(not isinstance(ref, str) or "#/" not in ref
                    or len(ref) > 512
                    or ref.split("#/", 1)[0] not in sources
                    or not _source_pointer_exists(
                        sources.get(ref.split("#/", 1)[0]), ref.split("#", 1)[1])
                    for ref in row["evidence_refs"])
                or not isinstance(row.get("finding"), str)
                or not row["finding"] or len(row["finding"]) > 2048):
            raise ValueError("durable_learning_boundary_criterion_invalid")
        checked_criteria[criterion] = {"status": row["status"],
            "evidence_refs": list(row["evidence_refs"]), "finding": row["finding"]}
    if disposition == "accepted_complete_boundary" and any(
            row["status"] != "accepted" for row in checked_criteria.values()):
        raise ValueError("durable_learning_boundary_acceptance_incomplete")
    if disposition in {"rejected", "insufficient_evidence"} and all(
            row["status"] == "accepted" for row in checked_criteria.values()):
        raise ValueError("durable_learning_boundary_disposition_inconsistent")
    referenced_ids = _referenced_artifact_ids({key: value[key]
        for key in ("protocol", "worker_executables", "process_launches",
            "inherited_handles", "broker_capabilities", "persistent_state",
            "scorer_custody", "bounded_access_review")})
    if referenced_ids != set(sources):
        raise ValueError("durable_learning_boundary_source_inventory_incomplete")
    if value.get("claim_limits") != CLAIM_LIMITS:
        raise ValueError("durable_learning_boundary_claim_limit_invalid")
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary or len(summary) > 4096:
        raise ValueError("durable_learning_boundary_summary_invalid")

    return {"schema_version": SCHEMA, "protocol": protocol_ref,
        "host": dict(host), "condition_pair": dict(pair),
        "worker_executables": worker_refs, "process_launches": launch_refs,
        "inherited_handles": _condition_refs(value["inherited_handles"], field="inherited_handles"),
        "broker_capabilities": _condition_refs(value["broker_capabilities"], field="broker_capabilities"),
        "persistent_state": {condition: {category: _ref(state_refs[condition][category])
            for category in STATE_CATEGORIES} for condition in CONDITIONS},
        "scorer_custody": _ref(value["scorer_custody"]),
        "bounded_access_review": _ref(value["bounded_access_review"]),
        "reviewer": dict(reviewer), "disposition": disposition,
        "criteria": checked_criteria, "claim_limits": dict(CLAIM_LIMITS),
        "summary": summary, "authority": False}


def create_boundary_acceptance(*, semantic: Mapping[str, Any],
        source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    """Create a review artifact only from reloaded, digest-valid source rows."""
    checked = _verify_semantic(semantic, sources=source_artifacts)
    artifact_digest = digest_payload(checked)
    return {**checked, "artifact_digest": artifact_digest,
        "artifact_id": ARTIFACT_PREFIX + artifact_digest[:24]}


def verify_boundary_acceptance(value: Any, *,
        source_artifacts: Mapping[str, Any],
        expected_protocol: Mapping[str, Any] | None = None,
        expected_worker_digests: Mapping[str, str] | None = None,
        expected_host_build: str | None = None,
        expected_condition_pair: Mapping[str, str] | None = None
        ) -> dict[str, Any]:
    """Reload and verify every cited source; never derive mutation authority."""
    fields = {"schema_version", "protocol", "host", "condition_pair",
        "worker_executables", "process_launches", "inherited_handles",
        "broker_capabilities", "persistent_state", "scorer_custody",
        "bounded_access_review", "reviewer", "disposition", "criteria",
        "claim_limits", "summary", "authority", "artifact_id", "artifact_digest"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("durable_learning_boundary_artifact_invalid")
    semantic = _verify_semantic({key: item for key, item in value.items()
        if key not in {"artifact_id", "artifact_digest"}}, sources=source_artifacts)
    digest = digest_payload(semantic)
    if (value.get("artifact_digest") != digest
            or value.get("artifact_id") != ARTIFACT_PREFIX + digest[:24]):
        raise ValueError("durable_learning_boundary_artifact_digest_invalid")
    if expected_protocol is not None and semantic["protocol"] != _ref(expected_protocol):
        raise ValueError("durable_learning_boundary_protocol_mismatch")
    if expected_host_build is not None and semantic["host"].get("os_build") != expected_host_build:
        raise ValueError("durable_learning_boundary_host_build_mismatch")
    if expected_condition_pair is not None and semantic["condition_pair"] != dict(expected_condition_pair):
        raise ValueError("durable_learning_boundary_condition_pair_mismatch")
    if expected_worker_digests is not None:
        if set(expected_worker_digests) != set(CONDITIONS):
            raise ValueError("durable_learning_boundary_expected_workers_invalid")
        for condition in CONDITIONS:
            ref = semantic["worker_executables"][condition]
            worker = _verify_source(ref, source_artifacts,
                schema_version="sentientos.durable_learning_worker_executable:v1")
            if worker.get("executable_sha256") != expected_worker_digests[condition]:
                raise ValueError("durable_learning_boundary_worker_mismatch")
    return {**semantic, "artifact_digest": digest,
        "artifact_id": ARTIFACT_PREFIX + digest[:24]}
