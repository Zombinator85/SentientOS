"""Evidence custody and comparison kernel for preregistered task strategies.

This evaluator is independent of the history-exposure experiment. It requires
an exact-scope resource-owner projection, verifies invocation and receipt-chain
bindings, and grants no authority. Campaign bundles preserve inputs and allow
deterministic report reconstruction and validate a full resource-ledger image
through its read-only owner validator.
"""
from __future__ import annotations

import json
import math
import os
import re
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .local_model_authority import digest_payload

PROTOCOL_SCHEMA = "sentientos.resource_strategy_comparison_protocol:v2"
REPORT_SCHEMA = "sentientos.resource_strategy_comparison_report:v4"
LEGACY_REPORT_SCHEMA = "sentientos.resource_strategy_comparison_report:v3"
EVALUATOR = "deterministic_exact_integer_suite_oracle_v2"
INVOCATION_PURPOSE = "resource_strategy_comparison_experiment"
MAX_STRATEGIES = 8
MAX_INVOCATIONS_PER_STRATEGY = 16
MAX_RECEIPTS = MAX_INVOCATIONS_PER_STRATEGY * 3
MAX_TRIALS = 16
MAX_CAMPAIGN_OUTCOMES = MAX_STRATEGIES * MAX_TRIALS
MAX_CAMPAIGN_INVOCATIONS = 96
MAX_STRATEGY_INPUT_CHARS = 8_000
MAX_STRATEGY_OUTPUT_CHARS = 4_000
MAX_STRATEGY_NEW_TOKENS = 512
MAX_STRATEGY_TIMEOUT_SECONDS = 120
CAMPAIGN_BUNDLE_SCHEMA = "sentientos.resource_strategy_comparison_campaign_bundle:v5"
LEGACY_CAMPAIGN_BUNDLE_SCHEMA = "sentientos.resource_strategy_comparison_campaign_bundle:v4"
SCORE_ATTESTATION_SCHEMA = (
    "sentientos.resource_strategy_comparison_score_attestation:v1")
SCORE_ATTESTATION_SCORER = (
    "sentientos.resource_strategy_comparison._recompute_private_plan_score:v1")
PREREGISTRATION_SCHEMA = "sentientos.resource_strategy_comparison_preregistration:v1"
OWNER_LEDGER_SNAPSHOT_SCHEMA = (
    "sentientos.resource_strategy_comparison_owner_ledger_snapshot:v1")
MAX_CAMPAIGN_BUNDLE_BYTES = 52 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


class ResourceStrategyComparisonError(ValueError):
    """A preregistration or evidence bundle violates its closed contract."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")


def _utc_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _campaign_bundle_path(root: str | Path, comparison_id: str) -> Path:
    if (not isinstance(comparison_id, str)
            or re.fullmatch(r"rscmp-[a-z0-9][a-z0-9-]{7,63}", comparison_id) is None):
        raise ResourceStrategyComparisonError("campaign_id_invalid")
    return Path(root) / f"{comparison_id}.json"


def _preregistration_path(root: str | Path, comparison_id: str) -> Path:
    _campaign_bundle_path(root, comparison_id)
    return Path(root) / f"{comparison_id}.protocol.json"


def _preregistration_body_is_valid(value: object) -> bool:
    if (not isinstance(value, Mapping)
            or set(value) != {"schema_version", "comparison_id", "protocol",
                "protocol_digest", "recorded_at", "custody_digest"}
            or value.get("schema_version") != PREREGISTRATION_SCHEMA
            or not isinstance(value.get("comparison_id"), str)
            or not isinstance(value.get("protocol"), Mapping)
            or value.get("protocol_digest") != value["protocol"].get("digest")
            or not isinstance(value.get("recorded_at"), str)
            or not isinstance(value.get("custody_digest"), str)):
        return False
    try:
        if not _protocol_is_valid(value["protocol"]):
            return False
        recorded = _utc_datetime(value["recorded_at"])
        if recorded is None:
            return False
        canonical_time = recorded.isoformat(
            timespec="seconds").replace("+00:00", "Z")
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        return False
    semantic = {key: item for key, item in value.items() if key != "custody_digest"}
    return (canonical_time == value["recorded_at"]
        and value["comparison_id"] == value["protocol"].get("comparison_id")
        and value["custody_digest"] == digest_payload(semantic))


def persist_resource_strategy_comparison_protocol(*, root: str | Path,
        protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Custody the frozen protocol before any trial evidence is collected."""
    if not _protocol_is_valid(protocol):
        raise ResourceStrategyComparisonError("preregistration_protocol_invalid")
    body = {"schema_version": PREREGISTRATION_SCHEMA,
        "comparison_id": protocol["comparison_id"], "protocol": dict(protocol),
        "protocol_digest": protocol["digest"],
        "recorded_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds").replace("+00:00", "Z")}
    record = {**body, "custody_digest": digest_payload(body)}
    if not _preregistration_body_is_valid(record):
        raise ResourceStrategyComparisonError("preregistration_record_invalid")
    encoded = _canonical_bytes(record)
    if len(encoded) > 196608:
        raise ResourceStrategyComparisonError("preregistration_size_limit_exceeded")
    path = _preregistration_path(root, protocol["comparison_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".pending", dir=str(path.parent))
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, path)
    except FileExistsError:
        existing = load_resource_strategy_comparison_protocol(root=root,
            comparison_id=protocol["comparison_id"])
        if existing.get("protocol") != dict(protocol):
            raise ResourceStrategyComparisonError("preregistration_identity_collision")
        return existing
    except OSError as exc:
        raise ResourceStrategyComparisonError("preregistration_publication_failed") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
    return record


def load_resource_strategy_comparison_protocol(*, root: str | Path,
        comparison_id: str) -> dict[str, Any]:
    """Load a digest-checked write-once protocol custody record."""
    path = _preregistration_path(root, comparison_id)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ResourceStrategyComparisonError("preregistration_not_regular_file")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode)
                    or opened.st_dev != before.st_dev
                    or opened.st_ino != before.st_ino):
                raise ResourceStrategyComparisonError("preregistration_identity_changed")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                encoded = stream.read(196609)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if len(encoded) > 196608:
            raise ResourceStrategyComparisonError("preregistration_size_limit_exceeded")
        record = json.loads(encoded.decode("utf-8"))
    except ResourceStrategyComparisonError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ResourceStrategyComparisonError("preregistration_unavailable_or_invalid") from exc
    if (not _preregistration_body_is_valid(record)
            or record.get("comparison_id") != comparison_id
            or _canonical_bytes(record) != encoded):
        raise ResourceStrategyComparisonError("preregistration_record_invalid")
    return dict(record)


def _validate_owner_ledger_snapshot(value: object) -> dict[str, Any] | None:
    from .governed_local_model_resource_allocation import (
        GovernedLocalModelResourceLedger, MAX_LEDGER_BYTES)

    fields = {"schema_version", "ledger_schema", "ledger_digest",
        "allocations", "attempts", "receipts"}
    if (not isinstance(value, Mapping) or set(value) != fields
            or value.get("schema_version") != OWNER_LEDGER_SNAPSHOT_SCHEMA
            or not isinstance(value.get("ledger_schema"), str)
            or not isinstance(value.get("ledger_digest"), str)
            or not _HEX.fullmatch(value["ledger_digest"])
            or not isinstance(value.get("allocations"), Mapping)
            or not isinstance(value.get("attempts"), Mapping)
            or not isinstance(value.get("receipts"), (list, tuple))):
        return None
    body = {"schema": value["ledger_schema"],
        "allocations": dict(value["allocations"]),
        "attempts": dict(value["attempts"]),
        "receipts": list(value["receipts"])}
    raw_mapping = {**body, "ledger_digest": value["ledger_digest"]}
    try:
        raw = (json.dumps(raw_mapping, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
        if len(raw) > MAX_LEDGER_BYTES:
            return None
        validated = GovernedLocalModelResourceLedger.read_only_snapshot(
            raw, max_bytes=MAX_LEDGER_BYTES).observation_snapshot()
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        return None
    if (validated.get("ledger_digest") != value["ledger_digest"]
            or validated.get("schema") != value["ledger_schema"]):
        return None
    allocations_by_id = {str(row["allocation_id"]): dict(row)
        for row in validated["allocations"]}
    return {"ledger_schema": value["ledger_schema"],
        "ledger_digest": value["ledger_digest"],
        "allocations_by_id": allocations_by_id,
        "allocations_by_digest": {str(row["allocation_digest"]): dict(row)
            for row in validated["allocations"]},
        "attempts_by_id": {str(row["attempt_id"]): dict(row)
            for row in validated["attempts"]},
        "receipts": [dict(row) for row in validated["receipts"]]}


def persist_resource_strategy_comparison_campaign(*, root: str | Path,
        protocol: Mapping[str, Any], outcomes: Sequence[Mapping[str, Any]],
        owner_ledger_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Write an immutable, replayable comparison bundle; never invokes models."""
    try:
        if not _protocol_is_valid(protocol):
            raise ResourceStrategyComparisonError("campaign_protocol_invalid")
        preregistration = load_resource_strategy_comparison_protocol(root=root,
            comparison_id=protocol["comparison_id"])
        if preregistration.get("protocol") != dict(protocol):
            raise ResourceStrategyComparisonError("campaign_not_preregistered_protocol")
        copied_outcomes = json.loads(json.dumps(outcomes, sort_keys=True,
            ensure_ascii=True, allow_nan=False))
        if not isinstance(copied_outcomes, list):
            raise ResourceStrategyComparisonError("campaign_outcomes_invalid")
        if _validate_owner_ledger_snapshot(owner_ledger_snapshot) is None:
            raise ResourceStrategyComparisonError("campaign_owner_ledger_snapshot_invalid")
        report = evaluate_resource_strategy_comparison(protocol, copied_outcomes,
            owner_ledger_snapshot=owner_ledger_snapshot,
            preregistration_record=preregistration)
        semantic = {"schema_version": CAMPAIGN_BUNDLE_SCHEMA,
            "comparison_id": protocol["comparison_id"], "protocol": dict(protocol),
            "preregistration_record": preregistration,
            "outcomes": copied_outcomes,
            "owner_ledger_snapshot": dict(owner_ledger_snapshot), "report": report}
        bundle = {**semantic, "artifact_digest": digest_payload(semantic)}
        encoded = _canonical_bytes(bundle)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        if isinstance(exc, ResourceStrategyComparisonError):
            raise
        raise ResourceStrategyComparisonError("campaign_bundle_not_serializable") from exc
    if len(encoded) > MAX_CAMPAIGN_BUNDLE_BYTES:
        raise ResourceStrategyComparisonError("campaign_bundle_size_limit_exceeded")
    path = _campaign_bundle_path(root, protocol["comparison_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".pending", dir=str(path.parent))
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, path)
    except FileExistsError:
        existing = load_resource_strategy_comparison_campaign(root=root,
            comparison_id=protocol["comparison_id"])
        if _canonical_bytes(existing) != encoded:
            raise ResourceStrategyComparisonError("campaign_identity_collision")
    except OSError as exc:
        raise ResourceStrategyComparisonError("campaign_bundle_publication_failed") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
    return bundle


def load_resource_strategy_comparison_campaign(*, root: str | Path,
        comparison_id: str) -> dict[str, Any]:
    """Load and deterministically reconstruct an immutable campaign bundle."""
    path = _campaign_bundle_path(root, comparison_id)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ResourceStrategyComparisonError("campaign_bundle_not_regular_file")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode)
                    or opened.st_dev != before.st_dev
                    or opened.st_ino != before.st_ino):
                raise ResourceStrategyComparisonError("campaign_bundle_identity_changed")
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                encoded = stream.read(MAX_CAMPAIGN_BUNDLE_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if len(encoded) > MAX_CAMPAIGN_BUNDLE_BYTES:
            raise ResourceStrategyComparisonError("campaign_bundle_size_limit_exceeded")
        bundle = json.loads(encoded.decode("utf-8"))
    except ResourceStrategyComparisonError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ResourceStrategyComparisonError("campaign_bundle_unavailable_or_invalid") from exc
    expected_fields = {"schema_version", "comparison_id", "protocol",
        "preregistration_record", "outcomes", "owner_ledger_snapshot", "report",
        "artifact_digest"}
    if (not isinstance(bundle, dict) or set(bundle) != expected_fields
            or bundle.get("schema_version") not in {
                LEGACY_CAMPAIGN_BUNDLE_SCHEMA, CAMPAIGN_BUNDLE_SCHEMA}
            or bundle.get("comparison_id") != comparison_id
            or not isinstance(bundle.get("protocol"), Mapping)
            or not isinstance(bundle.get("preregistration_record"), Mapping)
            or not isinstance(bundle.get("outcomes"), list)
            or not isinstance(bundle.get("owner_ledger_snapshot"), Mapping)
            or not isinstance(bundle.get("report"), Mapping)):
        raise ResourceStrategyComparisonError("campaign_bundle_shape_invalid")
    semantic = {key: value for key, value in bundle.items() if key != "artifact_digest"}
    try:
        if digest_payload(semantic) != bundle.get("artifact_digest"):
            raise ResourceStrategyComparisonError("campaign_bundle_digest_mismatch")
        if not _protocol_is_valid(bundle["protocol"]):
            raise ResourceStrategyComparisonError("campaign_protocol_invalid")
        preregistration = bundle["preregistration_record"]
        if (not _preregistration_body_is_valid(preregistration)
                or preregistration.get("comparison_id") != comparison_id
                or preregistration.get("protocol") != bundle["protocol"]
                or load_resource_strategy_comparison_protocol(root=root,
                    comparison_id=comparison_id) != dict(preregistration)):
            raise ResourceStrategyComparisonError("campaign_preregistration_mismatch")
        reconstructed = _evaluate_resource_strategy_comparison(bundle["protocol"],
            bundle["outcomes"],
            owner_ledger_snapshot=bundle["owner_ledger_snapshot"],
            preregistration_record=bundle["preregistration_record"],
            require_score_attestation=(bundle["schema_version"] ==
                CAMPAIGN_BUNDLE_SCHEMA))
    except ResourceStrategyComparisonError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ResourceStrategyComparisonError(
            "campaign_report_reconstruction_failed") from exc
    if dict(reconstructed) != dict(bundle["report"]):
        raise ResourceStrategyComparisonError("campaign_report_reconstruction_mismatch")
    if _canonical_bytes(bundle) != encoded:
        raise ResourceStrategyComparisonError("campaign_bundle_encoding_noncanonical")
    return bundle


def _bounded_json(value: Mapping[str, Any], limit: int) -> bool:
    try:
        return len(json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode("utf-8")) <= limit
    except (TypeError, ValueError, OverflowError, RecursionError):
        return False


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and bool(
        _HEX.fullmatch(value) or _SHA256.fullmatch(value))


def _invocation_budget_is_bounded(value: object) -> bool:
    """Enforce a fixed resource ceiling before a future runner can invoke."""
    fields = {"max_input_chars", "max_output_chars", "max_new_tokens",
        "timeout_seconds", "max_calls_per_correlation"}
    if not isinstance(value, Mapping) or set(value) != fields:
        return False
    for name, maximum in (("max_input_chars", MAX_STRATEGY_INPUT_CHARS),
            ("max_output_chars", MAX_STRATEGY_OUTPUT_CHARS),
            ("max_new_tokens", MAX_STRATEGY_NEW_TOKENS)):
        if type(value.get(name)) is not int or not 1 <= value[name] <= maximum:
            return False
    timeout = value.get("timeout_seconds")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not 0 < timeout <= MAX_STRATEGY_TIMEOUT_SECONDS):
        return False
    try:
        if not math.isfinite(float(timeout)):
            return False
    except (OverflowError, TypeError, ValueError):
        return False
    return value.get("max_calls_per_correlation") == 1 and type(
        value.get("max_calls_per_correlation")) is int


def _seal(body: Mapping[str, Any]) -> dict[str, Any]:
    semantic = dict(body)
    return {**semantic, "digest": digest_payload(semantic)}


def build_resource_strategy_comparison_protocol(*, comparison_id: str,
        task_descriptor: Mapping[str, Any], probe_count: int,
        minimum_correct_count: int, model_identity: Mapping[str, Any],
        model_id: str, authority_map_digest: str,
        invocation_budget: Mapping[str, Any],
        generation_configuration: Mapping[str, Any],
        strategies: Sequence[Mapping[str, Any]],
        trial_count: int | None = None) -> dict[str, Any]:
    """Freeze task, model, scoring bar, and explicit strategy alternatives."""
    if (not isinstance(comparison_id, str)
            or re.fullmatch(r"rscmp-[a-z0-9][a-z0-9-]{7,63}", comparison_id) is None
            or not isinstance(task_descriptor, Mapping) or not task_descriptor
            or type(probe_count) is not int or not 2 <= probe_count <= 16
            or type(minimum_correct_count) is not int
                or not 1 <= minimum_correct_count <= probe_count
            or (task_descriptor.get("probe_count") is not None
                and (type(task_descriptor.get("probe_count")) is not int
                    or task_descriptor.get("probe_count") != probe_count))
            or not isinstance(task_descriptor.get("probe_inputs"), (list, tuple))
            or len(task_descriptor["probe_inputs"]) != probe_count
            or any(type(value) is not int or abs(value) > 1_000_000
                for value in task_descriptor["probe_inputs"])
            or len(set(task_descriptor["probe_inputs"])) != probe_count
            or (task_descriptor.get("task_digest") is not None
                and not _valid_digest(task_descriptor.get("task_digest")))
            or not isinstance(model_identity, Mapping) or not model_identity
            or not _valid_digest(model_identity.get("model_content_sha256"))
            or not isinstance(model_id, str) or not model_id or len(model_id) > 128
            or not _valid_digest(authority_map_digest)
            or not _invocation_budget_is_bounded(invocation_budget)
            or not isinstance(generation_configuration, Mapping)
                or not generation_configuration
            or not _bounded_json(task_descriptor, 32768)
            or not _bounded_json(model_identity, 8192)
            or not _bounded_json(invocation_budget, 8192)
            or not _bounded_json(generation_configuration, 8192)
            or not isinstance(strategies, (list, tuple))
                or not 2 <= len(strategies) <= MAX_STRATEGIES):
        raise ResourceStrategyComparisonError("protocol_inputs_invalid")
    normalized_strategies: list[dict[str, str]] = []
    for strategy in strategies:
        if (not isinstance(strategy, Mapping)
                or set(strategy) != {"strategy_id", "descriptor"}
                or not isinstance(strategy.get("strategy_id"), str)
                or re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,63}",
                    str(strategy.get("strategy_id"))) is None
                or not isinstance(strategy.get("descriptor"), Mapping)
                or not strategy["descriptor"]
                or not _bounded_json(strategy["descriptor"], 8192)):
            raise ResourceStrategyComparisonError("strategy_descriptor_invalid")
        call_bounds = strategy["descriptor"]
        if (type(call_bounds.get("minimum_invocations")) is not int
                or type(call_bounds.get("maximum_invocations")) is not int
                or not 1 <= call_bounds["minimum_invocations"]
                    <= call_bounds["maximum_invocations"]
                    <= MAX_INVOCATIONS_PER_STRATEGY
                or call_bounds.get("scored_output_policy")
                    != "last_invocation_output"):
            raise ResourceStrategyComparisonError("strategy_invocation_bounds_invalid")
        normalized_strategies.append({
            "strategy_id": str(strategy["strategy_id"]),
            "descriptor": dict(strategy["descriptor"]),
            "descriptor_digest": digest_payload(dict(strategy["descriptor"])),
        })
    if len({item["strategy_id"] for item in normalized_strategies}) != len(
            normalized_strategies):
        raise ResourceStrategyComparisonError("strategy_ids_duplicate")
    selected_trial_count = (len(normalized_strategies)
        if trial_count is None else trial_count)
    if (type(selected_trial_count) is not int
            or selected_trial_count < len(normalized_strategies)
            or selected_trial_count > MAX_TRIALS
            or selected_trial_count % len(normalized_strategies) != 0):
        raise ResourceStrategyComparisonError("trial_count_not_counterbalanced")
    maximum_campaign_calls = selected_trial_count * sum(
        item["descriptor"]["maximum_invocations"] for item in normalized_strategies)
    if maximum_campaign_calls > MAX_CAMPAIGN_INVOCATIONS:
        raise ResourceStrategyComparisonError("campaign_invocation_bound_exceeded")
    ordered_ids = [item["strategy_id"] for item in normalized_strategies]
    trial_schedule = []
    for trial_index in range(selected_trial_count):
        order = ordered_ids[trial_index % len(ordered_ids):] + ordered_ids[:
            trial_index % len(ordered_ids)]
        trial_body = {"comparison_id": comparison_id, "trial_index": trial_index,
            "task_digest": (task_descriptor.get("task_digest")
                if isinstance(task_descriptor.get("task_digest"), str)
                else digest_payload(dict(task_descriptor))), "strategy_order": order}
        trial_schedule.append({**trial_body,
            "trial_digest": digest_payload(trial_body)})
    return _seal({
        "schema_version": PROTOCOL_SCHEMA,
        "comparison_id": comparison_id,
        "task_descriptor": dict(task_descriptor),
        "task_descriptor_digest": digest_payload(dict(task_descriptor)),
        "task_digest": (task_descriptor.get("task_digest")
            if isinstance(task_descriptor.get("task_digest"), str)
            else digest_payload(dict(task_descriptor))),
        "probe_count": probe_count,
        "minimum_correct_count": minimum_correct_count,
        "evaluator": EVALUATOR,
        "model_identity": dict(model_identity),
        "model_identity_digest": digest_payload(dict(model_identity)),
        "model_id": model_id,
        "authority_map_digest": authority_map_digest,
        "invocation_budget": dict(invocation_budget),
        "invocation_budget_digest": digest_payload(dict(invocation_budget)),
        "generation_configuration": dict(generation_configuration),
        "generation_configuration_digest": digest_payload(
            dict(generation_configuration)),
        "strategies": normalized_strategies,
        "trial_count": selected_trial_count,
        "trial_schedule": trial_schedule,
        "aggregation_rule": "all_trials_meet_quality_then_total_correct_then_total_reconciled_call_units:v1",
        "invocation_purpose": INVOCATION_PURPOSE,
        "max_invocations_per_strategy": MAX_INVOCATIONS_PER_STRATEGY,
        "selection_order": ["all_trials_meet_full_suite_correctness", "maximize_total_correct_count",
            "minimize_reconciled_call_units"],
        "history_condition_labels_are_strategies": False,
        "authority": False,
        "current_truth": False,
    })


def _protocol_is_valid(protocol: Mapping[str, Any]) -> bool:
    expected_fields = {"schema_version", "comparison_id", "task_descriptor",
        "task_descriptor_digest", "task_digest", "probe_count", "minimum_correct_count", "evaluator",
        "model_identity", "model_identity_digest", "generation_configuration",
        "model_id", "authority_map_digest", "invocation_budget",
        "invocation_budget_digest", "generation_configuration_digest",
        "strategies", "trial_count", "trial_schedule", "aggregation_rule",
        "invocation_purpose",
        "max_invocations_per_strategy", "selection_order",
        "history_condition_labels_are_strategies", "authority", "current_truth",
        "digest"}
    if (not _bounded_json(protocol, 131072)
            or protocol.get("schema_version") != PROTOCOL_SCHEMA
            or set(protocol) != expected_fields
            or not isinstance(protocol.get("comparison_id"), str)
            or re.fullmatch(r"rscmp-[a-z0-9][a-z0-9-]{7,63}",
                protocol["comparison_id"]) is None
            or not isinstance(protocol.get("task_descriptor"), Mapping)
            or not _bounded_json(protocol["task_descriptor"], 32768)
            or not isinstance(protocol.get("model_identity"), Mapping)
            or not _bounded_json(protocol["model_identity"], 8192)
            or not _valid_digest(protocol.get("model_identity", {}).get(
                "model_content_sha256"))
            or not isinstance(protocol.get("model_id"), str)
            or not protocol["model_id"] or len(protocol["model_id"]) > 128
            or not _valid_digest(protocol.get("authority_map_digest"))
            or not _invocation_budget_is_bounded(protocol.get("invocation_budget"))
            or not _bounded_json(protocol["invocation_budget"], 8192)
            or not isinstance(protocol.get("generation_configuration"), Mapping)
            or not _bounded_json(protocol["generation_configuration"], 8192)
            or type(protocol.get("probe_count")) is not int
            or not 2 <= protocol["probe_count"] <= 16
            or type(protocol.get("minimum_correct_count")) is not int
            or not 1 <= protocol["minimum_correct_count"] <= protocol["probe_count"]):
        return False
    semantic = {key: value for key, value in protocol.items() if key != "digest"}
    if protocol.get("digest") != digest_payload(semantic):
        return False
    strategies = protocol.get("strategies")
    base_valid = (isinstance(strategies, (list, tuple))
        and 2 <= len(strategies) <= MAX_STRATEGIES
        and type(protocol.get("trial_count")) is int
        and len(strategies) <= protocol["trial_count"] <= MAX_TRIALS
        and protocol["trial_count"] % len(strategies) == 0
        and len({item.get("strategy_id") for item in strategies
            if isinstance(item, Mapping)}) == len(strategies)
        and all(isinstance(item, Mapping)
            and isinstance(item.get("strategy_id"), str)
            and re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{0,63}",
                item["strategy_id"]) is not None
            and isinstance(item.get("descriptor"), Mapping)
            and _bounded_json(item["descriptor"], 8192)
            and item.get("descriptor_digest") == digest_payload(item["descriptor"])
            and type(item["descriptor"].get("minimum_invocations")) is int
            and type(item["descriptor"].get("maximum_invocations")) is int
            and 1 <= item["descriptor"]["minimum_invocations"]
                <= item["descriptor"]["maximum_invocations"]
                <= MAX_INVOCATIONS_PER_STRATEGY
            and item["descriptor"].get("scored_output_policy")
                == "last_invocation_output"
            for item in strategies)
        and protocol["trial_count"] * sum(item["descriptor"][
            "maximum_invocations"] for item in strategies)
                <= MAX_CAMPAIGN_INVOCATIONS
        and protocol.get("task_descriptor_digest") == digest_payload(
            protocol.get("task_descriptor"))
        and (protocol["task_descriptor"].get("probe_count") is None
            or protocol["task_descriptor"].get("probe_count") == protocol["probe_count"])
        and isinstance(protocol["task_descriptor"].get("probe_inputs"), (list, tuple))
        and len(protocol["task_descriptor"]["probe_inputs"]) == protocol["probe_count"]
        and all(type(value) is int and abs(value) <= 1_000_000
            for value in protocol["task_descriptor"]["probe_inputs"])
        and len(set(protocol["task_descriptor"]["probe_inputs"])) ==
            protocol["probe_count"]
        and _valid_digest(protocol.get("task_digest"))
        and (protocol["task_descriptor"].get("task_digest") is None
            or protocol.get("task_digest") == protocol["task_descriptor"].get("task_digest"))
        and protocol.get("model_identity_digest") == digest_payload(
            protocol.get("model_identity"))
        and protocol.get("invocation_budget_digest") == digest_payload(
            protocol.get("invocation_budget"))
        and protocol.get("generation_configuration_digest") == digest_payload(
            protocol.get("generation_configuration"))
        and protocol.get("evaluator") == EVALUATOR
        and protocol.get("invocation_purpose") == INVOCATION_PURPOSE
        and protocol.get("max_invocations_per_strategy") == MAX_INVOCATIONS_PER_STRATEGY
        and protocol.get("aggregation_rule") ==
            "all_trials_meet_quality_then_total_correct_then_total_reconciled_call_units:v1"
        and protocol.get("selection_order") == [
            "all_trials_meet_full_suite_correctness", "maximize_total_correct_count",
            "minimize_reconciled_call_units"]
        and protocol.get("history_condition_labels_are_strategies") is False
        and protocol.get("authority") is False
        and protocol.get("current_truth") is False)
    schedule = protocol.get("trial_schedule")
    if (not base_valid or not isinstance(schedule, (list, tuple))
            or len(schedule) != protocol["trial_count"]):
        return False
    ordered_ids = [item["strategy_id"] for item in strategies]
    for index, row in enumerate(schedule):
        if not isinstance(row, Mapping):
            return False
        order = ordered_ids[index % len(ordered_ids):] + ordered_ids[:
            index % len(ordered_ids)]
        body = {"comparison_id": protocol["comparison_id"],
            "trial_index": index, "task_digest": protocol["task_digest"],
            "strategy_order": order}
        if (dict(row) != {**body, "trial_digest": digest_payload(body)}):
            return False
    return True


def _invocation_bindings(receipts: object, *, protocol: Mapping[str, Any],
        strategy_id: str, trial_index: int, trial_digest: str,
        preregistration_recorded_at: str
        ) -> tuple[list[dict[str, Any]], str | None]:
    from .governed_local_model_invocation import validate_receipt

    if (not isinstance(receipts, (list, tuple)) or not receipts
            or len(receipts) > MAX_INVOCATIONS_PER_STRATEGY):
        return [], "incomparable_invocation_receipt_set_invalid"
    strategy = next((item for item in protocol.get("strategies", ())
        if isinstance(item, Mapping) and item.get("strategy_id") == strategy_id), None)
    descriptor = strategy.get("descriptor") if isinstance(strategy, Mapping) else None
    if (not isinstance(descriptor, Mapping)
            or not descriptor.get("minimum_invocations") <= len(receipts)
            <= descriptor.get("maximum_invocations")):
        return [], "incomparable_invocation_count_outside_preregistered_bounds"
    bindings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_digests: set[str] = set()
    seen_correlation_digests: set[str] = set()
    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, Mapping) or not _bounded_json(receipt, 262144):
            return [], "incomparable_invocation_receipt_invalid"
        try:
            valid, _findings = validate_receipt(receipt)
        except (KeyError, TypeError, ValueError, OverflowError):
            return [], "incomparable_invocation_receipt_invalid"
        request = receipt.get("request")
        linkage = request.get("linkage") if isinstance(request, Mapping) else None
        request_id = request.get("request_id") if isinstance(request, Mapping) else None
        correlation_id = request.get("correlation_id") if isinstance(
            request, Mapping) else None
        correlation_digest = (digest_payload({"correlation_id": correlation_id})
            if isinstance(correlation_id, str) and correlation_id else None)
        receipt_id = receipt.get("receipt_id")
        receipt_digest = receipt.get("receipt_digest")
        output_digest = receipt.get("output_digest")
        observed_at = receipt.get("observed_at")
        invocation_time = _utc_datetime(observed_at)
        preregistration_time = _utc_datetime(preregistration_recorded_at)
        if invocation_time is None or preregistration_time is None:
            return [], "incomparable_invocation_or_preregistration_time_invalid"
        if invocation_time < preregistration_time:
            return [], "incomparable_invocation_precedes_preregistration"
        resource_attempt_id = receipt.get("resource_attempt_id")
        resource_allocation_digest = receipt.get("resource_allocation_digest")
        resource_receipt_digests = receipt.get(
            "resource_consumption_receipt_digests")
        if (not valid or receipt.get("purpose") != INVOCATION_PURPOSE
                or receipt.get("status") != "admitted_completed"
                or receipt.get("output_truncated") is not False
                or receipt.get("fallback_occurred") is not False
                or not isinstance(receipt.get("effects"), Mapping)
                or receipt["effects"].get("local_model_inference") is not True
                or not isinstance(request_id, str) or not request_id
                or not isinstance(receipt_id, str) or not receipt_id
                or not isinstance(receipt_digest, str) or not _HEX.fullmatch(receipt_digest)
                or not isinstance(output_digest, str) or not _valid_digest(output_digest)
                or not isinstance(resource_attempt_id, str) or not resource_attempt_id
                or not isinstance(resource_allocation_digest, str)
                or not _HEX.fullmatch(resource_allocation_digest)
                or not isinstance(resource_receipt_digests, (list, tuple))
                or len(resource_receipt_digests) != 2
                or any(not isinstance(value, str) or not _HEX.fullmatch(value)
                    for value in resource_receipt_digests)
                or len(set(resource_receipt_digests)) != 2
                or not isinstance(request, Mapping)
                or not isinstance(correlation_id, str)
                or not 1 <= len(correlation_id) <= 128
                or request.get("purpose") != INVOCATION_PURPOSE
                or request.get("model_id") != protocol.get("model_id")
                or request.get("authority_map_digest") != protocol.get(
                    "authority_map_digest")
                or request.get("budget") != protocol.get("invocation_budget")
                or request.get("active_model_identity") != protocol.get("model_identity")
                or request.get("model_artifact_digest") != protocol.get(
                    "model_identity", {}).get("model_content_sha256")
                or receipt.get("generation_config") != protocol.get(
                    "generation_configuration")
                or not isinstance(linkage, Mapping)
                or linkage.get("resource_strategy_comparison_id") != protocol.get(
                    "comparison_id")
                or linkage.get("resource_strategy_task_digest") != protocol.get(
                    "task_digest")
                or linkage.get("resource_strategy_id") != strategy_id
                or linkage.get("resource_strategy_trial_index") != trial_index
                or linkage.get("resource_strategy_trial_digest") != trial_digest
                or linkage.get("resource_strategy_descriptor_digest") != strategy.get(
                    "descriptor_digest")
                or linkage.get("strategy_call_index") != index):
            return [], "incomparable_invocation_binding_mismatch"
        if (receipt_id in seen_ids or receipt_digest in seen_digests):
            return [], "incomparable_duplicate_invocation_receipt"
        if correlation_digest in seen_correlation_digests:
            return [], "incomparable_correlation_reused_within_trial"
        seen_ids.add(receipt_id)
        seen_digests.add(receipt_digest)
        seen_correlation_digests.add(correlation_digest)
        bindings.append({"receipt_id": receipt_id, "request_id": request_id,
            "receipt_digest": receipt_digest, "output_digest": output_digest,
            "correlation_id_digest": correlation_digest,
            "call_index": index, "trial_index": trial_index,
            "trial_digest": trial_digest, "observed_at": observed_at,
            "resource_attempt_id": resource_attempt_id,
            "resource_allocation_digest": resource_allocation_digest,
            "resource_consumption_receipt_digests": list(resource_receipt_digests)})
    return bindings, None


def _resource_attempts(receipts: object, *,
        invocation_bindings: Sequence[Mapping[str, Any]]) -> tuple[
            list[dict[str, Any]], str | None]:
    from .governed_local_model_resource_allocation import (
        GovernedLocalModelResourceConsumptionReceipt)

    if (not isinstance(receipts, (list, tuple))
            or len(receipts) != len(invocation_bindings) * 3
            or len(receipts) > MAX_RECEIPTS):
        return [], "incomparable_resource_receipt_set_incomplete"
    chains: dict[str, list[dict[str, Any]]] = {}
    seen_receipt_ids: set[str] = set()
    seen_receipt_digests: set[str] = set()
    try:
        for raw in receipts:
            if not isinstance(raw, Mapping) or not _bounded_json(raw, 16384):
                return [], "incomparable_resource_receipt_invalid"
            receipt = GovernedLocalModelResourceConsumptionReceipt.from_mapping(raw)
            if (receipt.receipt_id in seen_receipt_ids
                    or receipt.receipt_digest in seen_receipt_digests):
                return [], "incomparable_duplicate_resource_receipt"
            seen_receipt_ids.add(receipt.receipt_id)
            seen_receipt_digests.add(receipt.receipt_digest)
            chains.setdefault(receipt.attempt_id, []).append(dict(raw))
    except (KeyError, TypeError, ValueError):
        return [], "incomparable_resource_receipt_digest_invalid"
    if len(chains) != len(invocation_bindings):
        return [], "incomparable_resource_attempt_count_mismatch"
    by_effect: dict[str, list[dict[str, Any]]] = {}
    for binding in invocation_bindings:
        by_effect[binding["receipt_digest"]] = []
    for attempt_rows in chains.values():
        if len(attempt_rows) != 3:
            return [], "incomparable_resource_attempt_chain_incomplete"
        attempt_rows.sort(key=lambda row: {"attempt_begun": 0,
            "measured_completed": 1, "reconciled": 2}.get(row.get("state"), 3))
        begun, measured, reconciled = attempt_rows
        effect_digest = reconciled.get("effect_receipt_digest")
        measured_values = measured.get("resource_specific_measurement")
        reconciled_values = reconciled.get("resource_specific_measurement")
        begun_values = begun.get("resource_specific_measurement")
        if (begun.get("state") != "attempt_begun"
                or measured.get("state") != "measured_completed"
                or reconciled.get("state") != "reconciled"
                or any(row.get("attempt_id") != begun.get("attempt_id")
                    or row.get("allocation_digest") != begun.get("allocation_digest")
                    or row.get("principal_binding_digest") != begun.get(
                        "principal_binding_digest")
                    for row in attempt_rows)
                or begun.get("previous_receipt_digest") is not None
                or begun.get("effect_receipt_digest") is not None
                or measured.get("previous_receipt_digest") != begun.get("receipt_digest")
                or measured.get("effect_receipt_digest") is not None
                or reconciled.get("previous_receipt_digest") != measured.get("receipt_digest")
                or reconciled.get("effect_receipt_digest") != effect_digest
                or not isinstance(begun_values, Mapping)
                or not isinstance(measured_values, Mapping)
                or not isinstance(reconciled_values, Mapping)
                or dict(measured_values) != dict(reconciled_values)
                or any(row["resource_specific_measurement"].get(
                    "generation_attempted") is not True
                    or row["resource_specific_measurement"].get(
                        "call_units_consumed") != 1 for row in attempt_rows)
                or measured_values.get("generation_attempted") is not True
                or measured_values.get("call_units_consumed") != 1
                or effect_digest not in by_effect or by_effect[effect_digest]):
            return [], "incomparable_resource_attempt_chain_mismatch"
        by_effect[effect_digest] = attempt_rows
    if any(not rows for rows in by_effect.values()):
        return [], "incomparable_invocation_resource_join_missing"
    verified: list[dict[str, Any]] = []
    for binding in invocation_bindings:
        rows = by_effect[binding["receipt_digest"]]
        reconciled = next(row for row in rows if row["state"] == "reconciled")
        measured_and_reconciled = [row for row in rows
            if row["state"] != "attempt_begun"]
        if (reconciled.get("attempt_id") != binding["resource_attempt_id"]
                or reconciled.get("allocation_digest") != binding[
                    "resource_allocation_digest"]
                or {row["receipt_digest"] for row in measured_and_reconciled}
                    != set(binding["resource_consumption_receipt_digests"])
                or len(measured_and_reconciled) != len(
                    binding["resource_consumption_receipt_digests"])):
            return [], "incomparable_invocation_resource_linkage_mismatch"
        verified.append({"invocation_receipt_digest": binding["receipt_digest"],
            "attempt_id": reconciled["attempt_id"],
            "receipt_ids": [row["receipt_id"] for row in rows],
            "receipt_digests": [row["receipt_digest"] for row in rows],
            "call_units_consumed": reconciled["resource_specific_measurement"][
                "call_units_consumed"]})
    return verified, None


def _score_rows_bind_frozen_suite(score: Mapping[str, Any], *,
        protocol: Mapping[str, Any]) -> bool:
    """Check score rows cover the frozen probes and agree with score aggregates.

    The private oracle remains with the scorer; this check validates suite
    coverage and internal score consistency without claiming to recompute truth.
    """
    probe_inputs = protocol["task_descriptor"].get("probe_inputs")
    results = score.get("probe_results")
    answer = score.get("answer")
    selective_schema = score.get("schema_version") == "sentientos.objective_task_score:v5"
    if (not isinstance(probe_inputs, (list, tuple))
            or not isinstance(results, (list, tuple))
            or not isinstance(answer, (list, tuple))
            or len(probe_inputs) != protocol["probe_count"]
            or len(results) != protocol["probe_count"]
            or len(answer) != protocol["probe_count"]):
        return False
    correct_count = 0
    answered_count = 0
    for probe_input, result, answer_value in zip(probe_inputs, results, answer):
        if (not isinstance(result, Mapping)
                or type(result.get("probe_input")) is not int
                or result.get("probe_input") != probe_input):
            return False
        observed = result.get("observed_answer")
        correct = result.get("correct")
        if observed != answer_value:
            return False
        if selective_schema and observed is None:
            if (set(result) != {"probe_input", "observed_answer", "correct", "abstained"}
                    or correct is not None or result.get("abstained") is not True):
                return False
        elif (type(observed) is not int or type(correct) is not bool
                or set(result) != {"probe_input", "observed_answer", "correct"}):
            return False
        else:
            answered_count += 1
            correct_count += int(correct)
    if score.get("correct_count") != correct_count:
        return False
    if selective_schema:
        abstained_count = protocol["probe_count"] - answered_count
        if (score.get("answered_count") != answered_count
                or score.get("abstained_count") != abstained_count
                or (score.get("status") == "selective") != (abstained_count > 0)):
            return False
    elif answered_count != protocol["probe_count"]:
        return False
    return True


def _recompute_private_plan_score(*, objective_task_plan: Mapping[str, Any],
        output_text: str, output_digest: str) -> dict[str, Any]:
    """Independently parse and score one bounded affine task-family response."""
    task = objective_task_plan.get("task")
    if (not isinstance(task, Mapping)
            or task.get("schema_version") not in {
                "sentientos.affine_prediction_task_family_suite:v3",
                "sentientos.affine_prediction_task_family_suite:v4"}):
        raise ResourceStrategyComparisonError("score_attestation_task_family_invalid")
    probes = task.get("probe_inputs")
    multiplier = task.get("multiplier")
    offset = task.get("offset")
    if (not isinstance(probes, list) or not 2 <= len(probes) <= 16
            or any(type(value) is not int for value in probes)
            or type(multiplier) is not int or type(offset) is not int
            or not isinstance(output_text, str)
            or len(output_text.encode("utf-8")) > 1024):
        raise ResourceStrategyComparisonError("score_attestation_task_or_output_invalid")
    actual_output_digest = digest_payload({"output": output_text})
    if output_digest not in {actual_output_digest, "sha256:" + actual_output_digest}:
        raise ResourceStrategyComparisonError("score_attestation_output_digest_mismatch")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError("duplicate_answer_key")
            parsed[key] = value
        return parsed

    try:
        parsed = json.loads(output_text, object_pairs_hook=unique_object)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ResourceStrategyComparisonError("score_attestation_output_invalid") from exc
    selective_task = task.get("schema_version") == (
        "sentientos.affine_prediction_task_family_suite:v4")
    if (not isinstance(parsed, Mapping) or set(parsed) != {"answers"}
            or not isinstance(parsed.get("answers"), list)
            or len(parsed["answers"]) != len(probes)
            or any(type(value) is not int and not (selective_task and value is None)
                for value in parsed["answers"])):
        raise ResourceStrategyComparisonError("score_attestation_output_shape_invalid")
    answers = list(parsed["answers"])
    targets = [multiplier * probe + offset for probe in probes]
    correct_count = sum(type(answer) is int and answer == target
        for answer, target in zip(answers, targets))
    answered_count = sum(type(answer) is int for answer in answers)
    abstained_count = len(answers) - answered_count
    status = ("selective" if selective_task and abstained_count else
        "correct" if correct_count == len(probes) else "incorrect")
    semantic: dict[str, Any] = {
        "schema_version": ("sentientos.objective_task_score:v5" if selective_task
            else "sentientos.objective_task_score:v3"),
        "plan_digest": objective_task_plan["plan_digest"],
        "task_digest": objective_task_plan["task_descriptor"]["task_digest"],
        "output_digest": output_digest,
        "output_retention_posture": "live_bytes_digest_verified_not_retained",
        "status": status, "answer": answers,
        "correct": None if status == "selective" else status == "correct",
        "evaluator": "deterministic_exact_integer_suite_oracle_v2",
        "probe_count": len(probes), "correct_count": correct_count,
        "probe_results": [{"probe_input": probe,
            "observed_answer": answer,
            "correct": answer == target if type(answer) is int else None,
            **({"abstained": True} if selective_task and answer is None else {})}
            for probe, answer, target in zip(probes, answers, targets)]}
    if selective_task:
        semantic["answered_count"] = answered_count
        semantic["abstained_count"] = abstained_count
    return {**semantic, "score_digest": "sha256:" + digest_payload(semantic)}


def build_resource_strategy_score_attestation(*, protocol: Mapping[str, Any],
        objective_task_plan: Mapping[str, Any], score: Mapping[str, Any],
        final_invocation_receipt: Mapping[str, Any],
        output_truncated: bool = False) -> dict[str, Any]:
    """Recompute an objective score and bind it to its frozen plan and final call.

    The plan is private campaign evidence and must never be added to a model
    prompt. This receipt is deterministic evidence, not a digital signature;
    restart verification recomputes it from the plan, score, and invocation.
    """
    from .developmental_model_replacement_experiment import CONDITION_ORDER
    from .resident_developmental_cognition import _objective_task_from_specification

    expected_fields = {"schema_version", "protocol_id", "protocol_digest",
        "causal_context_digest", "task", "task_commitment_nonce",
        "task_descriptor", "condition_order", "rubric", "authority",
        "plan_digest"}
    if (not _protocol_is_valid(protocol)
            or not isinstance(objective_task_plan, Mapping)
            or not isinstance(score, Mapping)
            or not isinstance(final_invocation_receipt, Mapping)
            or set(objective_task_plan) != expected_fields
            or objective_task_plan.get("schema_version")
                != "sentientos.objective_task_plan:v2"
            or objective_task_plan.get("authority") is not False
            or objective_task_plan.get("task_descriptor")
                != dict(protocol.get("task_descriptor", {}))
            or objective_task_plan.get("condition_order") != list(CONDITION_ORDER)
            or not isinstance(objective_task_plan.get("task"), Mapping)
            or not isinstance(objective_task_plan.get("task_commitment_nonce"), str)
            or not _valid_digest(objective_task_plan.get("protocol_digest"))
            or not _valid_digest(objective_task_plan.get("causal_context_digest"))):
        raise ResourceStrategyComparisonError("score_attestation_task_plan_invalid")
    plan_semantic = {key: value for key, value in objective_task_plan.items()
        if key not in {"task", "task_commitment_nonce", "plan_digest"}}
    plan_digest = objective_task_plan.get("plan_digest")
    if (not _valid_digest(plan_digest)
            or plan_digest != "sha256:" + digest_payload(plan_semantic)):
        raise ResourceStrategyComparisonError("score_attestation_task_plan_digest_invalid")
    try:
        task = _objective_task_from_specification(
            objective_task_plan["task"], objective_task_plan["task_commitment_nonce"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ResourceStrategyComparisonError(
            "score_attestation_task_oracle_invalid") from exc
    if task.public_descriptor() != dict(objective_task_plan["task_descriptor"]):
        raise ResourceStrategyComparisonError("score_attestation_task_commitment_mismatch")
    expected_rubric = ("selective_integer_answer_suite_v1"
        if task.specification().get("schema_version") ==
            "sentientos.affine_prediction_task_family_suite:v4"
        else "exact_integer_answer_suite_v2"
        if task.specification().get("schema_version") in {
            "sentientos.affine_prediction_task_family_suite:v3",
            "sentientos.affine_prediction_task_family_suite:v4"}
        else None)
    if (expected_rubric is None
            or objective_task_plan.get("rubric") != expected_rubric):
        raise ResourceStrategyComparisonError("score_attestation_rubric_invalid")
    receipt_id = final_invocation_receipt.get("receipt_id")
    receipt_digest = final_invocation_receipt.get("receipt_digest")
    output_digest = final_invocation_receipt.get("output_digest")
    output_text = final_invocation_receipt.get("output_text")
    output_size = final_invocation_receipt.get("output_size_bytes")
    if (not isinstance(receipt_id, str) or not receipt_id or len(receipt_id) > 128
            or not isinstance(receipt_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", receipt_digest) is None
            or not isinstance(output_digest, str) or not _valid_digest(output_digest)
            or not isinstance(output_text, str)
            or type(output_size) is not int
            or output_size != len(output_text.encode("utf-8"))
            or final_invocation_receipt.get("output_truncated") is not False
            or type(output_truncated) is not bool):
        raise ResourceStrategyComparisonError("score_attestation_invocation_invalid")
    try:
        verified_score = _recompute_private_plan_score(
            objective_task_plan=objective_task_plan,
            output_text=output_text, output_digest=output_digest)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ResourceStrategyComparisonError("score_attestation_score_invalid") from exc
    if (output_truncated is not False
            or verified_score != dict(score)
            or verified_score.get("task_digest") != protocol.get("task_digest")
            or verified_score.get("output_digest") != output_digest
            or not isinstance(verified_score.get("probe_results"), (list, tuple))
            or len(verified_score["probe_results"]) != protocol.get("probe_count")):
        raise ResourceStrategyComparisonError("score_attestation_score_scope_mismatch")
    body = {"schema_version": SCORE_ATTESTATION_SCHEMA,
        "comparison_protocol_digest": protocol["digest"],
        "frozen_task_plan_digest": plan_digest,
        "final_invocation_receipt_id": receipt_id,
        "final_invocation_receipt_digest": receipt_digest,
        "output_digest": output_digest,
        "scorer_identity": SCORE_ATTESTATION_SCORER,
        "score_object_digest": verified_score["score_digest"],
        "probe_inputs_digest": digest_payload(list(
            protocol["task_descriptor"]["probe_inputs"])),
        "probe_coverage_count": protocol["probe_count"],
        "probe_coverage_digest": digest_payload(list(
            protocol["task_descriptor"]["probe_inputs"]))}
    return _seal(body)


def build_resource_strategy_trial_outcome(*, protocol: Mapping[str, Any],
        strategy_id: str, trial_index: int,
        invocation_receipts: Sequence[Mapping[str, Any]],
        preregistration_recorded_at: str,
        objective_task_plan: Mapping[str, Any],
        resource_owner_projection: Mapping[str, Any],
        resource_receipts: Sequence[Mapping[str, Any]] | None = None
        ) -> dict[str, Any]:
    """Build one scored outcome from completed calls and owner evidence.

    The final receipt must include output text (normally obtained with
    ``to_dict(include_output=True)``). This helper performs no model calls and
    does not admit or publish a campaign.
    """
    if (not _protocol_is_valid(protocol)
            or not isinstance(strategy_id, str)
            or type(trial_index) is not int
            or not 0 <= trial_index < protocol.get("trial_count", 0)):
        raise ResourceStrategyComparisonError("trial_outcome_identity_invalid")
    schedule_row = protocol["trial_schedule"][trial_index]
    if strategy_id not in schedule_row["strategy_order"]:
        raise ResourceStrategyComparisonError("trial_outcome_schedule_mismatch")
    strategy = next((item for item in protocol["strategies"]
        if item["strategy_id"] == strategy_id), None)
    if (not isinstance(strategy, Mapping)
            or not isinstance(invocation_receipts, (list, tuple))
            or not strategy["descriptor"]["minimum_invocations"]
                <= len(invocation_receipts)
                <= strategy["descriptor"]["maximum_invocations"]
            or any(not isinstance(item, Mapping) or not _bounded_json(item, 262144)
                for item in invocation_receipts)
            or not isinstance(objective_task_plan, Mapping)
            or not isinstance(resource_owner_projection, Mapping)
            or (resource_receipts is not None and (
                not isinstance(resource_receipts, (list, tuple))
                or any(not isinstance(item, Mapping) or not _bounded_json(item, 262144)
                    for item in resource_receipts)))):
        raise ResourceStrategyComparisonError("trial_outcome_evidence_invalid")
    _bindings, invocation_error = _invocation_bindings(
        invocation_receipts, protocol=protocol, strategy_id=strategy_id,
        trial_index=trial_index, trial_digest=schedule_row["trial_digest"],
        preregistration_recorded_at=preregistration_recorded_at)
    if invocation_error is not None:
        raise ResourceStrategyComparisonError("trial_outcome_invocation_invalid")
    final_receipt = invocation_receipts[-1]
    output_text = final_receipt.get("output_text")
    output_digest = final_receipt.get("output_digest")
    if (not isinstance(output_text, str)
            or not isinstance(output_digest, str)
            or final_receipt.get("output_truncated") is not False):
        raise ResourceStrategyComparisonError("trial_outcome_final_output_unavailable")
    score = _recompute_private_plan_score(objective_task_plan=objective_task_plan,
        output_text=output_text, output_digest=output_digest)
    score_attestation = build_resource_strategy_score_attestation(
        protocol=protocol, objective_task_plan=objective_task_plan, score=score,
        final_invocation_receipt=final_receipt,
        output_truncated=final_receipt.get("output_truncated"))
    outcome: dict[str, Any] = {
        "strategy_id": strategy_id,
        "strategy_digest": strategy["descriptor_digest"],
        "trial_index": trial_index,
        "trial_digest": schedule_row["trial_digest"],
        "objective_task_plan": dict(objective_task_plan),
        "score": score,
        "score_attestation": score_attestation,
        "invocation_receipts": [dict(item) for item in invocation_receipts],
        "resource_owner_projection": dict(resource_owner_projection),
    }
    if resource_receipts is not None:
        outcome["resource_receipts"] = [dict(item) for item in resource_receipts]
    return outcome


def _evaluate_resource_strategy_comparison(protocol: Mapping[str, Any],
        outcomes: Sequence[Mapping[str, Any]], *,
        owner_ledger_snapshot: Mapping[str, Any],
        preregistration_record: Mapping[str, Any],
        require_score_attestation: bool = True) -> dict[str, Any]:
    """Compare preregistered strategies across counterbalanced repeated trials."""
    if type(require_score_attestation) is not bool:
        raise ResourceStrategyComparisonError("score_attestation_posture_invalid")
    report_schema = REPORT_SCHEMA if require_score_attestation else LEGACY_REPORT_SCHEMA
    score_posture = ("private_plan_score_attestation_not_verified"
        if require_score_attestation else
        "score_digest_and_output_bound_execution_not_independently_attested")
    if not isinstance(protocol, Mapping):
        raise ResourceStrategyComparisonError("protocol_invalid")
    try:
        valid_protocol = _protocol_is_valid(protocol)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        valid_protocol = False
    if not valid_protocol:
        raise ResourceStrategyComparisonError("protocol_invalid")
    if (not _preregistration_body_is_valid(preregistration_record)
            or preregistration_record.get("protocol") != dict(protocol)):
        return _seal({"schema_version": report_schema,
            "comparison_id": protocol["comparison_id"], "protocol_digest": protocol[
                "digest"], "posture": "incomparable_preregistration_missing_or_mismatched",
            "candidate_strategies": [], "trial_count": protocol["trial_count"],
            "recommendation": None, "selection_reason": None,
            "correctness_equivalent_receipt_chain_cost_variation_observed": False,
            "score_posture": score_posture,
            "resource_owner_reconciliation_posture": "not_verified",
            "preregistration_posture": "not_verified",
            "learning_established": False, "historical_only": True,
            "authority": False, "current_truth": False})
    validated_ledger = _validate_owner_ledger_snapshot(owner_ledger_snapshot)
    if validated_ledger is None:
        return _seal({"schema_version": report_schema,
            "comparison_id": protocol["comparison_id"], "protocol_digest": protocol[
                "digest"], "posture": "incomparable_owner_ledger_snapshot_invalid",
            "candidate_strategies": [], "trial_count": protocol["trial_count"],
            "recommendation": None, "selection_reason": None,
            "correctness_equivalent_receipt_chain_cost_variation_observed": False,
            "score_posture": score_posture,
            "resource_owner_reconciliation_posture": "not_verified",
            "owner_ledger_snapshot_reconstruction_posture": "failed",
            "learning_established": False, "historical_only": True,
            "authority": False, "current_truth": False})
    expected = {item["strategy_id"]: item for item in protocol["strategies"]}
    schedule = protocol["trial_schedule"]
    expected_outcomes = [(trial["trial_index"], strategy_id, trial["trial_digest"])
        for trial in schedule for strategy_id in trial["strategy_order"]]
    if (len(expected_outcomes) > MAX_CAMPAIGN_OUTCOMES
            or not isinstance(outcomes, (list, tuple))
            or len(outcomes) != len(expected_outcomes)):
        return _seal({"schema_version": report_schema,
            "comparison_id": protocol["comparison_id"], "protocol_digest": protocol[
                "digest"], "posture": "incomparable_missing_trial_outcomes",
            "candidate_strategies": [], "trial_count": protocol["trial_count"],
            "recommendation": None, "selection_reason": None,
            "correctness_equivalent_receipt_chain_cost_variation_observed": False,
            "score_posture": score_posture,
            "resource_owner_reconciliation_posture": "not_performed",
            "owner_ledger_snapshot_digest": validated_ledger["ledger_digest"],
            "owner_ledger_snapshot_reconstruction_posture": "verified_full_snapshot",
            "preregistration_digest": preregistration_record["custody_digest"],
            "preregistration_posture": "protocol_custody_recorded",
            "preregistration_time_posture": "local_wall_clock_claim_not_independently_attested",
            "learning_established": False, "historical_only": True,
            "authority": False, "current_truth": False})
    posture = "comparable"
    score_attestations_verified = require_score_attestation
    trial_rows: dict[str, list[dict[str, Any]]] = {key: [] for key in expected}
    seen_invocation_ids: set[str] = set()
    seen_invocation_digests: set[str] = set()
    seen_correlation_digests: set[str] = set()
    seen_resource_ids: set[str] = set()
    seen_resource_digests: set[str] = set()
    seen_attempt_ids: set[str] = set()
    for outcome, (trial_index, strategy_id, trial_digest) in zip(
            outcomes, expected_outcomes):
        strategy = expected[strategy_id]
        if (not isinstance(outcome, Mapping)
                or outcome.get("strategy_id") != strategy_id
                or outcome.get("trial_index") != trial_index
                or outcome.get("trial_digest") != trial_digest
                or outcome.get("strategy_digest") != strategy["descriptor_digest"]):
            posture = "incomparable_trial_schedule_or_strategy_binding_mismatch"
            score_attestations_verified = False
            break
        score = outcome.get("score")
        raw_invocation_receipts = outcome.get("invocation_receipts")
        final_invocation_receipt = (raw_invocation_receipts[-1]
            if isinstance(raw_invocation_receipts, (list, tuple))
                and raw_invocation_receipts
                and isinstance(raw_invocation_receipts[-1], Mapping) else None)
        if require_score_attestation:
            objective_task_plan = outcome.get("objective_task_plan")
            if (not isinstance(objective_task_plan, Mapping)
                    or not isinstance(score, Mapping)
                    or not isinstance(final_invocation_receipt, Mapping)):
                posture = "incomparable_score_attestation_invalid"
                score_attestations_verified = False
                break
            try:
                expected_score_attestation = build_resource_strategy_score_attestation(
                    protocol=protocol,
                    objective_task_plan=objective_task_plan,
                    score=score,
                    final_invocation_receipt=final_invocation_receipt,
                    output_truncated=outcome.get("output_truncated", False))
            except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
                posture = "incomparable_score_attestation_invalid"
                score_attestations_verified = False
                break
            if outcome.get("score_attestation") != expected_score_attestation:
                posture = "incomparable_score_attestation_mismatch"
                score_attestations_verified = False
                break
        if (not isinstance(score, Mapping)
                or not isinstance(final_invocation_receipt, Mapping)
                or not _bounded_json(score, 65536)
                or score.get("task_digest") != protocol["task_digest"]
                or score.get("evaluator") != EVALUATOR
                or not _valid_digest(score.get("score_digest"))
                or score.get("schema_version") not in {
                    "sentientos.objective_task_score:v3",
                    "sentientos.objective_task_score:v4",
                    "sentientos.objective_task_score:v5"}
                or type(score.get("correct_count")) is not int
                or type(score.get("probe_count")) is not int
                or score.get("probe_count") != protocol["probe_count"]
                or not 0 <= score["correct_count"] <= protocol["probe_count"]
                or score.get("status") not in {"correct", "incorrect", "selective"}
                or (score.get("status") == "correct"
                    and (score["correct_count"] != protocol["probe_count"]
                        or score.get("correct") is not True))
                or (score.get("status") == "incorrect"
                    and (score["correct_count"] >= protocol["probe_count"]
                        or score.get("correct") is not False))
                or (score.get("status") == "selective"
                    and (score.get("schema_version") !=
                            "sentientos.objective_task_score:v5"
                        or score.get("correct") is not None
                        or type(score.get("answered_count")) is not int
                        or type(score.get("abstained_count")) is not int
                        or score["answered_count"] + score["abstained_count"]
                            != protocol["probe_count"]
                        or score["correct_count"] > score["answered_count"]))
                or not _valid_digest(score.get("output_digest"))
                or score.get("output_digest") != final_invocation_receipt.get(
                    "output_digest")
                or score.get("score_digest") != "sha256:" + digest_payload({
                    key: value for key, value in score.items()
                    if key != "score_digest"})
                or not _score_rows_bind_frozen_suite(score, protocol=protocol)):
            posture = "incomparable_score_or_strategy_binding_invalid"
            score_attestations_verified = False
            break
        invocation_bindings, invocation_error = _invocation_bindings(
            outcome.get("invocation_receipts"), protocol=protocol,
            strategy_id=strategy_id, trial_index=trial_index,
            trial_digest=trial_digest,
            preregistration_recorded_at=preregistration_record["recorded_at"])
        if invocation_error:
            posture = invocation_error
            break
        owner_projection_value = outcome.get("resource_owner_projection")
        owner_projection = (owner_projection_value
            if isinstance(owner_projection_value, Mapping) else None)
        try:
            from .world_state_board import record_digest
            projection_valid = (isinstance(owner_projection, Mapping)
                and owner_projection.get("digest") == record_digest({
                    key: value for key, value in owner_projection.items()
                    if key != "digest"}))
        except (KeyError, TypeError, ValueError):
            projection_valid = False
        projection_payload = (owner_projection.get("payload")
            if isinstance(owner_projection, Mapping) else None)
        expected_scope_ids = [item["receipt_id"] for item in invocation_bindings]
        projected_chains = (projection_payload.get("chains")
            if isinstance(projection_payload, Mapping) else None)
        if (not projection_valid or not isinstance(owner_projection, Mapping)
                or not isinstance(projection_payload, Mapping)):
            posture = "incomparable_resource_owner_projection_invalid"
            break
        if (owner_projection.get("schema_version") !=
                    "sentientos.resource_consumption_world_state_record:v2"
                or owner_projection.get("subject_kind") != "causal_resource_consumption"
                or owner_projection.get("source_id") !=
                    "governed_local_model_resource_consumption"
                or owner_projection.get("disposition") != "recorded"
                or owner_projection.get("evidence_strength") != "receipt_bound"
                or not isinstance(projection_payload.get("ledger_digest"), str)
                or not _HEX.fullmatch(projection_payload["ledger_digest"])
                or owner_projection.get("subject_id") != projection_payload.get(
                    "ledger_digest")
                or projection_payload.get("ledger_digest") !=
                    validated_ledger["ledger_digest"]
                or projection_payload.get("ledger_schema") !=
                    validated_ledger["ledger_schema"]
                or projection_payload.get("selection_scope") != "exact_invocation_attempts"
                or projection_payload.get("selected_invocation_receipt_ids") != expected_scope_ids
                or projection_payload.get("lineage_posture") != "verified"
                or projection_payload.get("retention_posture") != "complete"
                or projection_payload.get("recovery_posture") != "reconciled_or_restored"
                or not isinstance(projected_chains, (list, tuple))
                or len(projected_chains) != len(invocation_bindings)):
            posture = "incomparable_resource_owner_projection_invalid"
            break
        projected_by_invocation = {item.get("invocation_receipt_id"): item
            for item in projected_chains if isinstance(item, Mapping)}
        if (len(projected_by_invocation) != len(projected_chains)
                or set(projected_by_invocation) != set(expected_scope_ids)):
            posture = "incomparable_resource_owner_scope_mismatch"
            break
        owner_receipts: list[dict[str, Any]] = []
        for binding in invocation_bindings:
            chain = projected_by_invocation[binding["receipt_id"]]
            if (chain.get("invocation_receipt_digest") != binding["receipt_digest"]
                    or not isinstance(chain.get("consumption_receipts"), (list, tuple))):
                owner_receipts = []
                break
            attempt_id = chain.get("attempt_id")
            allocation = validated_ledger["allocations_by_digest"].get(
                str(chain.get("allocation_digest")))
            attempt = validated_ledger["attempts_by_id"].get(str(attempt_id))
            expected_chain_receipts = [dict(row) for row in validated_ledger["receipts"]
                if row.get("attempt_id") == attempt_id]
            if (allocation is None or attempt is None
                    or dict(chain.get("allocation", {})) != allocation
                    or dict(chain.get("attempt", {})) != attempt
                    or list(chain["consumption_receipts"]) != expected_chain_receipts):
                owner_receipts = []
                break
            owner_receipts.extend(dict(item) for item in chain["consumption_receipts"]
                if isinstance(item, Mapping))
        if not owner_receipts:
            posture = "incomparable_resource_owner_chain_invalid"
            break
        supplied_receipts = outcome.get("resource_receipts")
        if supplied_receipts is not None and list(supplied_receipts) != owner_receipts:
            posture = "incomparable_resource_owner_receipt_mismatch"
            break
        resource_attempts, resource_error = _resource_attempts(
            owner_receipts, invocation_bindings=invocation_bindings)
        if resource_error:
            posture = resource_error
            break
        invocation_ids = {item["receipt_id"] for item in invocation_bindings}
        invocation_digests = {item["receipt_digest"] for item in invocation_bindings}
        correlation_digests = {item["correlation_id_digest"]
            for item in invocation_bindings}
        resource_ids = {receipt_id for attempt in resource_attempts
            for receipt_id in attempt["receipt_ids"]}
        resource_digests = {receipt_digest for attempt in resource_attempts
            for receipt_digest in attempt["receipt_digests"]}
        attempt_ids = {item["attempt_id"] for item in resource_attempts}
        if (seen_correlation_digests & correlation_digests):
            posture = "incomparable_correlation_reused_across_campaign"
            break
        if (seen_invocation_ids & invocation_ids
                or seen_invocation_digests & invocation_digests
                or seen_resource_ids & resource_ids
                or seen_resource_digests & resource_digests
                or seen_attempt_ids & attempt_ids):
            posture = "incomparable_receipt_reused_across_trials_or_strategies"
            break
        seen_invocation_ids.update(invocation_ids)
        seen_invocation_digests.update(invocation_digests)
        seen_correlation_digests.update(correlation_digests)
        seen_resource_ids.update(resource_ids)
        seen_resource_digests.update(resource_digests)
        seen_attempt_ids.update(attempt_ids)
        trial_rows[strategy_id].append({"trial_index": trial_index,
            "trial_digest": trial_digest, "score_digest": score["score_digest"],
            "correct_count": score["correct_count"],
            "probe_count": score["probe_count"], "invocations": invocation_bindings,
            "resource_attempts": resource_attempts,
            "total_receipt_chain_call_units": sum(
                row["call_units_consumed"] for row in resource_attempts)})
    candidates: list[dict[str, Any]] = []
    if posture == "comparable":
        for strategy in protocol["strategies"]:
            rows = trial_rows[strategy["strategy_id"]]
            if len(rows) != protocol["trial_count"]:
                posture = "incomparable_missing_strategy_trial"
                candidates = []
                break
            meets_each_trial = all(row["correct_count"]
                >= protocol["minimum_correct_count"] for row in rows)
            candidates.append({"strategy_id": strategy["strategy_id"],
                "strategy_digest": strategy["descriptor_digest"],
                "trial_count": len(rows), "trials": rows,
                "meets_quality_requirement": meets_each_trial,
                "correct_count": sum(row["correct_count"] for row in rows),
                "probe_count": sum(row["probe_count"] for row in rows),
                "total_receipt_chain_call_units": sum(
                    row["total_receipt_chain_call_units"] for row in rows)})
    eligible = [item for item in candidates
        if item["meets_quality_requirement"]]
    recommendation: dict[str, Any] | None = None
    selection_reason: str | None = None
    if posture == "comparable" and eligible:
        best_quality = max(item["correct_count"] for item in eligible)
        quality_ties = [item for item in eligible
            if item["correct_count"] == best_quality]
        best_cost = min(item["total_receipt_chain_call_units"] for item in quality_ties)
        winners = [item for item in quality_ties
            if item["total_receipt_chain_call_units"] == best_cost]
        if len(winners) == 1:
            recommendation = winners[0]
            selection_reason = ("highest_total_correct_count" if len(quality_ties) == 1
                else "lowest_receipt_chain_call_units_among_equal_quality_strategies")
            posture = "bounded_receipt_chain_strategy_comparison"
        else:
            posture = "incomparable_equivalent_strategies"
    elif posture == "comparable":
        posture = "no_strategy_meets_preregistered_quality_requirement"
    comparable_quality_cost_variation = any(
        left["correct_count"] == right["correct_count"]
        and left["total_receipt_chain_call_units"]
            != right["total_receipt_chain_call_units"]
        for index, left in enumerate(eligible)
        for right in eligible[index + 1:])
    owner_reconciliation_posture = ("verified_from_reconstructed_owner_ledger_snapshot"
        if posture in {"bounded_receipt_chain_strategy_comparison",
            "no_strategy_meets_preregistered_quality_requirement",
            "incomparable_equivalent_strategies"}
        else "not_verified")
    reported_score_posture = ("private_plan_score_recomputed_and_final_invocation_bound"
        if score_attestations_verified else score_posture)
    return _seal({"schema_version": report_schema,
        "comparison_id": protocol["comparison_id"],
        "protocol_digest": protocol["digest"], "posture": posture,
        "trial_count": protocol["trial_count"],
        "candidate_strategies": candidates, "recommendation": recommendation,
        "selection_reason": selection_reason,
        "correctness_equivalent_receipt_chain_cost_variation_observed": (
            comparable_quality_cost_variation),
        "score_posture": reported_score_posture,
        "resource_owner_reconciliation_posture": owner_reconciliation_posture,
        "owner_ledger_snapshot_digest": validated_ledger["ledger_digest"],
        "owner_ledger_snapshot_reconstruction_posture": "verified_full_snapshot",
        "preregistration_digest": preregistration_record["custody_digest"],
        "preregistration_posture": "protocol_custody_recorded",
        "preregistration_time_posture": "local_wall_clock_claim_not_independently_attested",
        "learning_established": False, "historical_only": True,
        "authority": False, "current_truth": False})


def evaluate_resource_strategy_comparison(protocol: Mapping[str, Any],
        outcomes: Sequence[Mapping[str, Any]], *,
        owner_ledger_snapshot: Mapping[str, Any],
        preregistration_record: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a new campaign with private-plan score attestation required."""
    return _evaluate_resource_strategy_comparison(protocol, outcomes,
        owner_ledger_snapshot=owner_ledger_snapshot,
        preregistration_record=preregistration_record,
        require_score_attestation=True)
