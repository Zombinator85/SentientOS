"""Deterministic embodied consequence evidence and developmental experiments.

Every record in this module is evidence or a proposal.  Nothing here performs an
embodied action, adopts a body, grants authority, or promotes interpretation to
current truth.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast
from .windows_handle_custody import (WindowsHandleCustodyError,
    read_regular_files, verify_explicit_directory)

try:
    import fcntl as _fcntl
except ImportError:  # Windows hosted development has no POSIX fcntl module.
    _fcntl = None

EXPECTATION_SCHEMA = "sentientos.embodied_action_expectation:v1"
HANDOFF_SCHEMA = "sentientos.avatar_renderer_handoff:v1"
REPORT_SCHEMA = "sentientos.avatar_renderer_report:v1"
OBSERVATION_SCHEMA = "sentientos.avatar_independent_observation:v1"
ATTRIBUTION_SCHEMA = "sentientos.embodied_consequence_attribution:v1"
COMPARISON_SCHEMA = "sentientos.embodied_prediction_comparison:v1"
STRATEGY_SCHEMA = "sentientos.embodied_strategy_proposal:v1"
EXPERIMENT_SCHEMA = "sentientos.embodied_strategy_experiment:v1"
LEGACY_EXPERIMENT_RESULT_SCHEMA = "sentientos.embodied_strategy_experiment_result:v1"
EXPERIMENT_RESULT_SCHEMA = "sentientos.embodied_strategy_experiment_result:v2"
STRATEGY_CONDITION_START_SCHEMA = "sentientos.embodied_strategy_condition_start:v1"
STRATEGY_CONDITION_RESULT_SCHEMA = "sentientos.embodied_strategy_condition_result:v1"
CONSEQUENCE_CHAIN_SCHEMA = "sentientos.embodied_consequence_chain:v1"
WORLD_STATE_PROJECTION_CONFIG_SCHEMA = "sentientos.embodied_consequence_world_state_projection_config:v1"
WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V2 = "sentientos.embodied_consequence_world_state_projection_config:v2"
WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V3 = "sentientos.embodied_consequence_world_state_projection_config:v3"
WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V4 = "sentientos.embodied_consequence_world_state_projection_config:v4"
MAX_STRATEGY_CONTEXT_BYTES = 1_048_576
MAX_CONSEQUENCE_ARTIFACT_BYTES = 2_097_152
MAX_CONSEQUENCE_ARTIFACTS_PER_KIND = 4096
MAX_WORLD_STATE_PROJECTION_RECORDS = 48
MAX_WORLD_STATE_PROJECTION_RECORD_BYTES = 32_768
_CONSEQUENCE_KINDS = {"expectations", "reports", "observations", "attributions", "comparisons",
    "strategy-experiments", "strategy-experiment-starts", "strategy-experiment-conditions",
    "consequence-chains"}
_CONSEQUENCE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}:[0-9a-f]{24}\Z")
_ARTIFACT_IDENTITIES = {
    "expectations": ("expectation_id", "expectation_digest", "expectation"),
    "reports": ("report_id", "report_digest", "renderer-report"),
    "observations": ("observation_id", "observation_digest", "independent-observation"),
    "attributions": ("attribution_id", "attribution_digest", "consequence"),
    "comparisons": ("comparison_id", "comparison_digest", "prediction-comparison"),
    "strategy-experiments": ("experiment_result_id", "experiment_result_digest", "strategy-experiment"),
    "consequence-chains": ("chain_id", "chain_digest", "consequence-chain"),
}
FALSE_AUTHORITY = {"effect_authority": False, "adoption_authority": False,
                   "observation_authority": False, "goal_authority": False,
                   "authoring_authority": False, "execution_authority": False}
HANDOFF_NO_AUTHORITY = {"decision_authority": False, "admission_authority": False,
                        "execution_authority": False, "adoption_authority": False,
                        "renderer_authority": False, "observation_authority": False}
ATTRIBUTION_RESULTS = frozenset({"expectation_satisfied", "expectation_partially_satisfied",
    "expectation_contradicted", "observation_missing", "renderer_report_only", "indeterminate",
    "execution_failed", "body_generation_mismatch", "correlation_mismatch"})
CAUSAL_POSTURES = frozenset({"self_command_correlated", "renderer_internal_only",
    "independent_environment_observation", "external_interference_possible",
    "causal_attribution_insufficient"})
POSTURES = frozenset({"synthetic_test", "rehearsal", "production"})


class EmbodiedConsequenceError(ValueError):
    """Fail-closed contract or provenance error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise EmbodiedConsequenceError("timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise EmbodiedConsequenceError("timestamp_timezone_required")
    return parsed


def _identity(prefix: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    dg = digest(payload)
    return f"{prefix}:{dg[7:31]}", dg


def _validate_authority(authority: Mapping[str, bool]) -> None:
    if dict(authority) != FALSE_AUTHORITY:
        raise EmbodiedConsequenceError("authority_must_be_all_false")


@dataclass(frozen=True)
class EmbodiedActionExpectation:
    expectation_id: str
    expectation_digest: str
    installation_body_id: str
    body_id: str
    body_generation: int
    body_manifest_digest: str
    handoff_id: str
    handoff_digest: str
    renderer_interface_id: str
    requested: Mapping[str, Any]
    predicted_observables: Mapping[str, Any]
    observable_fields: tuple[str, ...]
    comparison_policy: Mapping[str, Mapping[str, Any]]
    expected_observation_source_class: str
    correlation_id: str
    causal_principal_binding_digest: str | None
    created_at: str
    expires_at: str
    authority: Mapping[str, bool]
    schema_version: str = EXPECTATION_SCHEMA

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("expectation_id"); value.pop("expectation_digest"); return value


def make_expectation(**kwargs: Any) -> EmbodiedActionExpectation:
    raw = EmbodiedActionExpectation("", "", authority=dict(FALSE_AUTHORITY), **kwargs)
    verify_expectation(raw, identity_required=False)
    eid, dg = _identity("expectation", raw.semantic_payload())
    return replace(raw, expectation_id=eid, expectation_digest=dg)


def verify_expectation(value: EmbodiedActionExpectation, *, identity_required: bool = True) -> None:
    if value.schema_version != EXPECTATION_SCHEMA or value.body_generation < 1:
        raise EmbodiedConsequenceError("expectation_shape_invalid")
    _validate_authority(value.authority)
    if (not value.observable_fields or len(value.observable_fields) != len(set(value.observable_fields))
            or set(value.observable_fields) != set(value.predicted_observables)
            or set(value.observable_fields) != set(value.comparison_policy)):
        raise EmbodiedConsequenceError("expectation_observable_contract_invalid")
    if _time(value.expires_at) <= _time(value.created_at):
        raise EmbodiedConsequenceError("expectation_freshness_invalid")
    for field, policy in value.comparison_policy.items():
        if set(policy) - {"kind", "tolerance"} or policy.get("kind") not in {"exact", "numeric_tolerance"}:
            raise EmbodiedConsequenceError("comparison_policy_invalid")
        if policy["kind"] == "numeric_tolerance":
            tolerance = policy.get("tolerance")
            try:
                tolerance_float = float(tolerance)
            except (OverflowError, TypeError, ValueError):
                tolerance_float = math.inf
            if (type(tolerance) not in (int, float) or tolerance < 0
                    or not math.isfinite(tolerance_float)):
                raise EmbodiedConsequenceError("comparison_tolerance_invalid")
    if identity_required and (value.expectation_id, value.expectation_digest) != _identity("expectation", value.semantic_payload()):
        raise EmbodiedConsequenceError("expectation_digest_mismatch")


def verify_re