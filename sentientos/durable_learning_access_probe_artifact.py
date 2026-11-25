"""Integrity checks for persisted paired AppContainer access-probe evidence."""
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PureWindowsPath
from typing import Any

from .local_model_authority import digest_payload


ARTIFACT_SCHEMA = "sentientos.durable_learning_access_probe_artifact:v1"
LEGACY_COMPLETION_SCHEMA = (
    "sentientos.windows_appcontainer_access_probe_completion:v1")
COMPLETION_SCHEMA = "sentientos.windows_appcontainer_access_probe_completion:v2"
COMPLETION_SCHEMA_V3 = (
    "sentientos.windows_appcontainer_access_probe_completion:v3")
SUPERVISOR_CHECK_SCHEMA = (
    "sentientos.windows_appcontainer_access_probe_supervisor_check:v1")
CONDITIONS = ("relevant_experience_available",
    "relevant_experience_withheld")
_HEX = re.compile(r"[0-9a-f]{64}")
_COMPLETION_FIELDS_V1 = {
    "schema_version", "protocol_id", "condition", "manifest_digest",
    "worker_process_id", "worker_process_creation_time_100ns",
    "worker_exit_confirmed_by_process_handle", "worker_exit_code",
    "worker_report_matches_expected_matrix",
    "process_identity_binding_verified", "sentinel_readback",
    "all_probe_checks_match", "process_isolation_verified",
    "filesystem_isolation_verified", "retention_contrast_eligible",
    "authority", "completion_digest"}
_COMPLETION_FIELDS_V2 = (_COMPLETION_FIELDS_V1
    | {"worker_response_result_digest", "expected_result_digest"})
_LAUNCH_OBSERVATION_FIELDS = {
    "process_id", "process_creation_time_100ns", "token_is_appcontainer",
    "appcontainer_sid", "enabled_capability_count",
    "inherited_handles_requested", "process_start_nonce",
    "environment_block_sha256", "requested_executable_sha256",
    "requested_capability_count", "job_object_bound",
    "job_active_process_limit", "isolation_verified", "authority"}
_COMPLETION_FIELDS_V3 = _COMPLETION_FIELDS_V2 | {
    "worker_launch_observation"}
_SUPERVISOR_FIELDS = {
    "schema_version", "protocol_id", "condition", "manifest_digest",
    "sentinels", "all_sentinel_identities_and_contents_match",
    "worker_exit_confirmed_by_caller", "process_isolation_verified",
    "filesystem_isolation_verified", "retention_contrast_eligible",
    "authority", "check_digest"}
_SENTINEL_FIELDS = {"opened_read_only", "identity_matched",
    "content_digest_matched", "end_of_file_verified", "winerror"}
_RUNTIME_SETUP_FIELDS = {"schema_version", "protocol_id",
    "profile_pair_digest", "runtime_roots", "grants_by_condition",
    "all_requested_grants_applied", "effective_access_verified",
    "peer_denial_verified", "filesystem_isolation_verified",
    "retention_contrast_eligible", "authority", "setup_digest"}


class DurableLearningAccessProbeArtifactError(ValueError):
    """Paired access-probe evidence failed its closed artifact contract."""


def verify_worker_access_probe_completion(value: Any, *, protocol_id: str,
        condition: str, expected_result_digest: str | None = None,
        expected_appcontainer_sid: str | None = None
        ) -> dict[str, Any]:
    """Verify one worker completion report and its post-exit sentinel readback."""
    schema_version = value.get("schema_version") if isinstance(value, Mapping) else None
    is_v2 = schema_version in {COMPLETION_SCHEMA, COMPLETION_SCHEMA_V3}
    is_v3 = schema_version == COMPLETION_SCHEMA_V3
    expected_fields = (_COMPLETION_FIELDS_V3 if is_v3 else
        _COMPLETION_FIELDS_V2 if is_v2 else _COMPLETION_FIELDS_V1)
    if (not isinstance(value, Mapping) or set(value) != expected_fields
            or not isinstance(schema_version, str)
            or schema_version not in {LEGACY_COMPLETION_SCHEMA,
                COMPLETION_SCHEMA, COMPLETION_SCHEMA_V3}
            or value.get("protocol_id") != protocol_id
            or condition not in CONDITIONS
            or value.get("condition") != condition
            or not isinstance(value.get("manifest_digest"), str)
            or _HEX.fullmatch(value["manifest_digest"]) is None
            or type(value.get("worker_process_id")) is not int
            or value["worker_process_id"] <= 0
            or type(value.get("worker_process_creation_time_100ns")) is not int
            or value["worker_process_creation_time_100ns"] <= 0
            or type(value.get("worker_exit_confirmed_by_process_handle")) is not bool
            or type(value.get("worker_report_matches_expected_matrix")) is not bool
            or type(value.get("process_identity_binding_verified")) is not bool
            or type(value.get("all_probe_checks_match")) is not bool
            or value.get("process_isolation_verified") is not False
            or value.get("filesystem_isolation_verified") is not False
            or value.get("retention_contrast_eligible") is not False
            or value.get("authority") is not False):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_completion_invalid")

    if is_v2:
        response_digest = value.get("worker_response_result_digest")
        bound_expected_digest = value.get("expected_result_digest")
        if (not isinstance(bound_expected_digest, str)
                or _HEX.fullmatch(bound_expected_digest) is None
                or bound_expected_digest != expected_result_digest
                or (response_digest is not None
                    and (not isinstance(response_digest, str)
                        or _HEX.fullmatch(response_digest) is None))
                or value.get("worker_report_matches_expected_matrix") is not
                    (response_digest == bound_expected_digest)):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_result_digest_binding_invalid")

    if is_v3:
        launch = value.get("worker_launch_observation")
        if (not isinstance(launch, Mapping)
                or set(launch) != _LAUNCH_OBSERVATION_FIELDS
                or launch.get("process_id") != value.get("worker_process_id")
                or launch.get("process_creation_time_100ns") !=
                    value.get("worker_process_creation_time_100ns")
                or launch.get("token_is_appcontainer") is not True
                or not isinstance(launch.get("appcontainer_sid"), str)
                or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+",
                    launch.get("appcontainer_sid", "")) is None
                or (expected_appcontainer_sid is not None
                    and launch.get("appcontainer_sid") !=
                        expected_appcontainer_sid)
                or type(launch.get("enabled_capability_count")) is not int
                or launch.get("enabled_capability_count") != 0
                or launch.get("inherited_handles_requested") is not False
                or not isinstance(launch.get("process_start_nonce"), str)
                or re.fullmatch(r"[0-9a-f]{32}",
                    launch.get("process_start_nonce", "")) is None
                or any(not isinstance(launch.get(field), str)
                    or _HEX.fullmatch(launch[field]) is None
                    for field in ("environment_block_sha256",
                        "requested_executable_sha256"))
                or type(launch.get("requested_capability_count")) is not int
                or launch.get("requested_capability_count") != 0
                or launch.get("job_object_bound") is not True
                or type(launch.get("job_active_process_limit")) is not int
                or launch.get("job_active_process_limit") != 1
                or launch.get("isolation_verified") is not False
                or launch.get("authority") is not False):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_launch_observation_invalid")

    exited = value["worker_exit_confirmed_by_process_handle"]
    exit_code = value.get("worker_exit_code")
    sentinel_check = value.get("sentinel_readback")
    sentinels_match = False
    if not exited:
        if (exit_code is not None or sentinel_check is not None
                or value["worker_report_matches_expected_matrix"]
                or value["process_identity_binding_verified"]
                or value["all_probe_checks_match"]):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_nonexit_result_invalid")
    else:
        if (type(exit_code) is not int or not 0 <= exit_code <= 0xFFFFFFFF
                or not isinstance(sentinel_check, Mapping)
                or set(sentinel_check) != _SUPERVISOR_FIELDS
                or sentinel_check.get("schema_version") != SUPERVISOR_CHECK_SCHEMA
                or sentinel_check.get("protocol_id") != protocol_id
                or sentinel_check.get("condition") != condition
                or sentinel_check.get("manifest_digest") !=
                    value.get("manifest_digest")
                or sentinel_check.get("worker_exit_confirmed_by_caller") is not True
                or sentinel_check.get("process_isolation_verified") is not False
                or sentinel_check.get("filesystem_isolation_verified") is not False
                or sentinel_check.get("retention_contrast_eligible") is not False
                or sentinel_check.get("authority") is not False):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_sentinel_check_invalid")
        sentinels = sentinel_check.get("sentinels")
        if (not isinstance(sentinels, Mapping)
                or set(sentinels) != {"own_sentinel", "peer_sentinel",
                    "scorer_sentinel"}):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_sentinel_matrix_invalid")
        per_target: list[bool] = []
        for observation in sentinels.values():
            if (not isinstance(observation, Mapping)
                    or set(observation) != _SENTINEL_FIELDS
                    or any(type(observation.get(field)) is not bool
                        for field in ("opened_read_only", "identity_matched",
                            "content_digest_matched", "end_of_file_verified"))
                    or (observation.get("opened_read_only") is True
                        and observation.get("winerror") is not None)
                    or (observation.get("opened_read_only") is False
                        and (type(observation.get("winerror")) is not int
                            or not 0 <= observation["winerror"] <= 0xFFFFFFFF
                            or observation.get("identity_matched") is not False
                            or observation.get("content_digest_matched") is not False
                            or observation.get("end_of_file_verified") is not False))):
                raise DurableLearningAccessProbeArtifactError(
                    "durable_learning_access_probe_sentinel_observation_invalid")
            per_target.append(all(observation[field] is True for field in (
                "opened_read_only", "identity_matched",
                "content_digest_matched", "end_of_file_verified")))
        sentinels_match = all(per_target)
        if (sentinel_check.get(
                "all_sentinel_identities_and_contents_match") is not sentinels_match):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_sentinel_aggregate_invalid")
        check_semantic = {key: item for key, item in sentinel_check.items()
            if key != "check_digest"}
        if (not isinstance(sentinel_check.get("check_digest"), str)
                or sentinel_check["check_digest"] != digest_payload(
                    check_semantic)):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_sentinel_digest_invalid")

    expected_complete = (exited and exit_code == 0
        and value["worker_report_matches_expected_matrix"]
        and value["process_identity_binding_verified"]
        and sentinels_match)
    if value["all_probe_checks_match"] is not expected_complete:
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_completion_aggregate_invalid")
    semantic = {key: item for key, item in value.items()
        if key != "completion_digest"}
    if (not isinstance(value.get("completion_digest"), str)
            or value["completion_digest"] != digest_payload(semantic)):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_completion_digest_invalid")
    return dict(value)


def verify_condition_worker_runtime_access_setup(value: Any, *,
        protocol_id: str, profile_pair: Mapping[str, Any],
        require_complete: bool = True) -> dict[str, Any]:
    """Check identity-bound runtime ACL setup evidence before worker launch."""
    if (not isinstance(value, Mapping)
            or not isinstance(profile_pair, Mapping)
            or set(value) != _RUNTIME_SETUP_FIELDS
            or value.get("schema_version") !=
                "sentientos.windows_appcontainer_runtime_access_setup:v1"
            or value.get("protocol_id") != protocol_id
            or value.get("profile_pair_digest") !=
                profile_pair.get("profile_pair_digest")
            or type(value.get("all_requested_grants_applied")) is not bool
            or (require_complete and
                value.get("all_requested_grants_applied") is not True)
            or value.get("effective_access_verified") is not False
            or value.get("peer_denial_verified") is not False
            or value.get("filesystem_isolation_verified") is not False
            or value.get("retention_contrast_eligible") is not False
            or value.get("authority") is not False
            or not isinstance(value.get("runtime_roots"), Mapping)
            or not value["runtime_roots"]
            or not isinstance(value.get("grants_by_condition"), Mapping)
            or set(value["grants_by_condition"]) != set(CONDITIONS)):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_runtime_setup_invalid")
    profiles = profile_pair.get("condition_profiles")
    roots = value["runtime_roots"]
    grants_by_condition = value["grants_by_condition"]
    if (not isinstance(profiles, Mapping)
            or set(profiles) != set(CONDITIONS)
            or any(not isinstance(profiles[condition], Mapping)
                for condition in CONDITIONS)):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_profile_pair_invalid")
    root_paths: list[tuple[str, ...]] = []
    for name, root in roots.items():
        if (not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name) is None
                or not isinstance(root, Mapping)
                or set(root) != {"path", "volume_serial", "file_id_hex"}
                or not isinstance(root.get("path"), str)
                or len(root["path"]) > 2048
                or not PureWindowsPath(root["path"]).is_absolute()
                or any(part in {".", ".."} for part in
                    PureWindowsPath(root["path"]).parts)
                or type(root.get("volume_serial")) is not int
                or not 0 <= root["volume_serial"] <= 0xFFFFFFFFFFFFFFFF
                or not isinstance(root.get("file_id_hex"), str)
                or re.fullmatch(r"[0-9a-f]{32}", root["file_id_hex"]) is None):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_runtime_root_invalid")
        root_paths.append(tuple(part.casefold() for part in
            root["path"].replace("/", "\\").split("\\") if part))
    for index, left in enumerate(root_paths):
        for right in root_paths[index + 1:]:
            if (left == right or left == right[:len(left)]
                    or right == left[:len(right)]):
                raise DurableLearningAccessProbeArtifactError(
                    "durable_learning_access_probe_runtime_roots_overlap")
    all_applied = True
    for condition in CONDITIONS:
        grants = grants_by_condition[condition]
        if not isinstance(grants, Mapping) or set(grants) != set(roots):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_runtime_grants_invalid")
        sid = profiles[condition].get("appcontainer_sid")
        for name, root in roots.items():
            grant_record = grants[name]
            if (isinstance(grant_record, Mapping)
                    and grant_record.get("status") == "failed"):
                all_applied = False
                if (require_complete
                        or set(grant_record) != {"status", "reason_code",
                            "mutation_state", "authority"}
                        or not isinstance(grant_record.get("reason_code"), str)
                        or not grant_record["reason_code"]
                        or grant_record.get("mutation_state") not in {
                            "not_attempted", "api_call_outcome_unknown",
                            "api_reported_failure", "api_succeeded_unverified",
                            "acl_verified"}
                        or grant_record.get("authority") is not False):
                    raise DurableLearningAccessProbeArtifactError(
                        "durable_learning_access_probe_runtime_grant_failure_invalid")
                continue
            grant = (grant_record.get("grant")
                if isinstance(grant_record, Mapping) else None)
            expected_identity = (root["volume_serial"], root["file_id_hex"])
            directory_identity = (grant.get("directory_identity")
                if isinstance(grant, Mapping) else None)
            actual_identity = (directory_identity.get("volume_serial"),
                directory_identity.get("file_id_hex")) \
                if isinstance(directory_identity, Mapping) else None
            if (not isinstance(grant_record, Mapping)
                    or set(grant_record) != {"status", "grant"}
                    or grant_record.get("status") != "applied"
                    or not isinstance(grant, Mapping)
                    or grant.get("schema_version") !=
                        "sentientos.windows_appcontainer_directory_acl:v1"
                    or actual_identity != expected_identity
                    or grant.get("package_sid") != sid
                    or grant.get("access_policy") != "runtime_read_execute"
                    or grant.get("directory_allow_ace_present") is not True
                    or grant.get("file_inherit_allow_ace_present") is not True
                    or grant.get("package_sid_deny_ace_present") is not False
                    or grant.get("effective_access_verified") is not False
                    or grant.get("peer_denial_verified") is not False
                    or grant.get("retention_contrast_eligible") is not False
                    or grant.get("authority") is not False):
                raise DurableLearningAccessProbeArtifactError(
                    "durable_learning_access_probe_runtime_grant_invalid")
    if value["all_requested_grants_applied"] is not all_applied:
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_runtime_setup_aggregate_invalid")
    semantic = {key: item for key, item in value.items()
        if key != "setup_digest"}
    if value.get("setup_digest") != digest_payload(semantic):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_runtime_setup_digest_invalid")
    return dict(value)


def verify_runtime_access_setup_attempt(value: Any, *,
        protocol: Mapping[str, Any], branch_preflight: Mapping[str, Any],
        profile_pair_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a durable partial ACL setup attempt, including its failed grants."""
    fields = {"schema_version", "protocol_id", "protocol_digest",
        "branch_preflight_id", "branch_preflight_digest",
        "profile_pair_artifact_id", "profile_pair_artifact_digest",
        "runtime_access_setup", "authority", "artifact_digest", "artifact_id"}
    if (not isinstance(value, Mapping)
            or not isinstance(protocol, Mapping)
            or not isinstance(branch_preflight, Mapping)
            or not isinstance(profile_pair_artifact, Mapping)
            or set(value) != fields
            or value.get("schema_version") !=
                "sentientos.durable_learning_runtime_access_attempt:v1"
            or value.get("protocol_id") != protocol.get("protocol_id")
            or value.get("protocol_digest") != protocol.get("protocol_digest")
            or value.get("branch_preflight_id") != branch_preflight.get("preflight_id")
            or value.get("branch_preflight_digest") !=
                branch_preflight.get("preflight_digest")
            or value.get("profile_pair_artifact_id") !=
                profile_pair_artifact.get("artifact_id")
            or value.get("profile_pair_artifact_digest") !=
                profile_pair_artifact.get("artifact_digest")
            or value.get("authority") is not False):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_runtime_access_attempt_invalid")
    profile_pair = profile_pair_artifact.get("profile_pair")
    if not isinstance(profile_pair, Mapping):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_runtime_access_attempt_profile_pair_invalid")
    setup = verify_condition_worker_runtime_access_setup(
        value.get("runtime_access_setup"), protocol_id=protocol["protocol_id"],
        profile_pair=profile_pair, require_complete=False)
    if setup.get("all_requested_grants_applied") is not False:
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_runtime_access_attempt_not_incomplete")
    semantic = {key: item for key, item in value.items()
        if key not in {"artifact_digest", "artifact_id"}}
    expected_digest = digest_payload(semantic)
    expected_id = "devexp-durable-learning-runtime-access-attempt-" + \
        protocol["protocol_id"][-24:] + "-" + expected_digest[:24]
    if (value.get("artifact_digest") != expected_digest
            or value.get("artifact_id") != expected_id):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_runtime_access_attempt_digest_invalid")
    return dict(value)


def verify_worker_access_probe_interruption(value: Any, *,
        protocol: Mapping[str, Any], branch_preflight: Mapping[str, Any],
        profile_pair_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a failed post-ACL worker launch and preserve its retry block."""
    fields = {"schema_version", "protocol_id", "protocol_digest",
        "branch_preflight_id", "branch_preflight_digest",
        "profile_pair_artifact_id", "profile_pair_artifact_digest",
        "runtime_access_setup", "failure_phase", "launch_call_started",
        "launch_call_returned", "worker_process_observations",
        "created_endpoint_conditions", "accepted_pipe_conditions",
        "cleanup_errors", "failure_type", "retry_blocked", "authority",
        "artifact_digest", "artifact_id"}
    if (not isinstance(value, Mapping)
            or not isinstance(protocol, Mapping)
            or not isinstance(branch_preflight, Mapping)
            or not isinstance(profile_pair_artifact, Mapping)
            or set(value) != fields
            or value.get("schema_version") !=
                "sentientos.durable_learning_worker_access_probe_interruption:v1"
            or value.get("protocol_id") != protocol.get("protocol_id")
            or value.get("protocol_digest") != protocol.get("protocol_digest")
            or value.get("branch_preflight_id") != branch_preflight.get("preflight_id")
            or value.get("branch_preflight_digest") !=
                branch_preflight.get("preflight_digest")
            or value.get("profile_pair_artifact_id") !=
                profile_pair_artifact.get("artifact_id")
            or value.get("profile_pair_artifact_digest") !=
                profile_pair_artifact.get("artifact_digest")
            or value.get("failure_phase") not in {"worker_pair_launch",
                "pipe_acceptance", "probe_rpc_and_record", "cleanup"}
            or value.get("launch_call_started") is not True
            or type(value.get("launch_call_returned")) is not bool
            or value.get("retry_blocked") is not True
            or value.get("authority") is not False
            or not isinstance(value.get("worker_process_observations"), Mapping)
            or not isinstance(value.get("created_endpoint_conditions"), list)
            or not isinstance(value.get("accepted_pipe_conditions"), list)
            or not isinstance(value.get("cleanup_errors"), list)
            or not isinstance(value.get("failure_type"), str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,95}",
                value["failure_type"]) is None):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_worker_access_probe_interruption_invalid")
    profile_pair = profile_pair_artifact.get("profile_pair")
    if not isinstance(profile_pair, Mapping):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_worker_access_probe_interruption_profile_pair_invalid")
    verify_condition_worker_runtime_access_setup(
        value.get("runtime_access_setup"), protocol_id=protocol["protocol_id"],
        profile_pair=profile_pair)
    observations = value["worker_process_observations"]
    for condition, observation in observations.items():
        if (condition not in CONDITIONS or not isinstance(observation, Mapping)
                or set(observation) != {"process_id",
                    "process_creation_time_100ns", "observation_digest"}
                or type(observation.get("process_id")) is not int
                or observation["process_id"] <= 0
                or type(observation.get("process_creation_time_100ns")) is not int
                or observation["process_creation_time_100ns"] <= 0
                or not isinstance(observation.get("observation_digest"), str)
                or _HEX.fullmatch(observation["observation_digest"]) is None):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_worker_access_probe_interruption_observation_invalid")
    for field in ("created_endpoint_conditions", "accepted_pipe_conditions"):
        entries = value[field]
        if (any(item not in CONDITIONS for item in entries)
                or len(set(entries)) != len(entries)
                or entries != [condition for condition in CONDITIONS
                    if condition in entries]):
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_worker_access_probe_interruption_condition_list_invalid")
    created_conditions = set(value["created_endpoint_conditions"])
    accepted_conditions = set(value["accepted_pipe_conditions"])
    if (not accepted_conditions.issubset(created_conditions)
            or not set(observations).issubset(created_conditions)
            or (value["launch_call_returned"] is True
                and created_conditions != set(CONDITIONS))
            or (value["launch_call_returned"] is False
                and accepted_conditions)):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_worker_access_probe_interruption_lifecycle_mismatch")
    cleanup_values = {"pipe_connection_close_failed",
        "pipe_endpoint_close_failed", "worker_process_cleanup_failed"}
    if (len(value["cleanup_errors"]) > 6
            or any(item not in cleanup_values for item in value["cleanup_errors"])):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_worker_access_probe_interruption_cleanup_invalid")
    semantic = {key: item for key, item in value.items()
        if key not in {"artifact_digest", "artifact_id"}}
    expected_digest = digest_payload(semantic)
    expected_id = "devexp-durable-learning-access-probe-interruption-" + \
        protocol["protocol_id"][-24:] + "-" + expected_digest[:24]
    if (value.get("artifact_digest") != expected_digest
            or value.get("artifact_id") != expected_id):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_worker_access_probe_interruption_digest_invalid")
    return dict(value)


def verify_paired_access_probe_artifact(value: Any, *, protocol: Mapping[str, Any],
        branch_preflight: Mapping[str, Any],
        profile_pair_artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Validate both condition reports and their immutable setup references."""
    if (not isinstance(value, Mapping)
            or not isinstance(protocol, Mapping)
            or not isinstance(branch_preflight, Mapping)
            or not isinstance(profile_pair_artifact, Mapping)
            or set(value) != {"schema_version", "protocol_id", "protocol_digest",
                "branch_preflight_id", "branch_preflight_digest",
                "profile_pair_artifact_id", "profile_pair_artifact_digest",
                "runtime_access_setup", "condition_access_probe_manifests",
                "condition_completions",
                "authority", "artifact_digest", "artifact_id"}
            or value.get("schema_version") != ARTIFACT_SCHEMA
            or value.get("protocol_id") != protocol.get("protocol_id")
            or value.get("protocol_digest") != protocol.get("protocol_digest")
            or value.get("branch_preflight_id") !=
                branch_preflight.get("preflight_id")
            or value.get("branch_preflight_digest") !=
                branch_preflight.get("preflight_digest")
            or value.get("profile_pair_artifact_id") !=
                profile_pair_artifact.get("artifact_id")
            or value.get("profile_pair_artifact_digest") !=
                profile_pair_artifact.get("artifact_digest")
            or value.get("authority") is not False
            or not isinstance(value.get("condition_completions"), Mapping)
            or set(value["condition_completions"]) != set(CONDITIONS)
            or not isinstance(value.get("condition_access_probe_manifests"), Mapping)
            or set(value["condition_access_probe_manifests"]) != set(CONDITIONS)):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_artifact_invalid")
    from .windows_appcontainer_access import (
        verify_condition_worker_access_probe_manifest)

    profile_pair = profile_pair_artifact.get("profile_pair")
    profiles = (profile_pair.get("condition_profiles")
        if isinstance(profile_pair, Mapping) else None)
    if (not isinstance(profiles, Mapping)
            or set(profiles) != set(CONDITIONS)
            or any(not isinstance(profiles[condition], Mapping)
                for condition in CONDITIONS)):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_profile_pair_invalid")
    verify_condition_worker_runtime_access_setup(
        value.get("runtime_access_setup"), protocol_id=protocol["protocol_id"],
        profile_pair=profile_pair)
    manifests: dict[str, dict[str, Any]] = {}
    for condition in CONDITIONS:
        profile = profiles[condition]
        sid = profile.get("appcontainer_sid") if isinstance(profile, Mapping) else None
        manifest = value["condition_access_probe_manifests"][condition]
        try:
            manifests[condition] = verify_condition_worker_access_probe_manifest(
                manifest, protocol_id=protocol["protocol_id"],
                condition=condition, appcontainer_sid=sid)
        except (TypeError, ValueError) as exc:
            raise DurableLearningAccessProbeArtifactError(
                "durable_learning_access_probe_manifest_invalid") from exc
    from .windows_appcontainer_access import (
        expected_condition_worker_access_probe_rpc_digest)
    completions = {}
    for condition in CONDITIONS:
        manifest = manifests[condition]
        expected_result_digest = expected_condition_worker_access_probe_rpc_digest(
            manifest)
        completions[condition] = verify_worker_access_probe_completion(
            value["condition_completions"][condition],
            protocol_id=protocol["protocol_id"], condition=condition,
            expected_result_digest=expected_result_digest,
            expected_appcontainer_sid=profiles[condition]["appcontainer_sid"])
    if any(completions[condition].get("manifest_digest") !=
            manifests[condition].get("manifest_digest")
            for condition in CONDITIONS):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_manifest_completion_mismatch")
    semantic = {key: item for key, item in value.items()
        if key not in {"artifact_id", "artifact_digest"}}
    expected_digest = digest_payload(semantic)
    expected_id = "devexp-durable-learning-access-probe-completion-" + \
        expected_digest[:24]
    if (value.get("artifact_digest") != expected_digest
            or value.get("artifact_id") != expected_id):
        raise DurableLearningAccessProbeArtifactError(
            "durable_learning_access_probe_artifact_digest_invalid")
    return {**dict(value), "condition_access_probe_manifests": manifests,
        "condition_completions": completions}
