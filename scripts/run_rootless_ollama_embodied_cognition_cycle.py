"""Run one bounded Hermes trial through the resident developmental cognition owner.

The body and observer are synthetic fixtures. The developmental record, cognition
observations, history ablation, model identity, and local inference receipts use
the existing governed SentientOS owners. This is not production serving evidence.
Select a different installed Ollama model with SENTIENTOS_HERMES_MODEL and its
exact manifest file with SENTIENTOS_HERMES_MODEL_MANIFEST_PATH. The manifest
must live under the configured rootless experiment custody and its SHA-256 must
match its filename; the runner does not discover or substitute models. GPU
placement is explicit and bounded by SENTIENTOS_HERMES_GPU_LAYERS (default 32).
Longitudinal plans may preallocate the cycle identifier with
SENTIENTOS_HERMES_CYCLE_ID and bind the launch to a campaign plan with
SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH. Historical-example pair slots use the
separate SENTIENTOS_HERMES_HISTORICAL_PAIR_* variables documented in the
development experiment notes; they execute one frozen pair and do not claim a
full acquisition/transfer cycle.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence, cast


def _gpu_layers_from_environment() -> int:
    raw = os.environ.get("SENTIENTOS_HERMES_GPU_LAYERS", "32")
    if (not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal()):
        raise SystemExit("hermes_gpu_layers_invalid")
    value = int(raw)
    if not 1 <= value <= 128:
        raise SystemExit("hermes_gpu_layers_invalid")
    return value


GPU_LAYERS = _gpu_layers_from_environment()

if __name__ == "__main__" and len(sys.argv) > 1:
    # Parse before creating the private workspace or importing runtime owners.
    # In particular, `--help` must never fall through into a paid/resource-heavy
    # experimental run.
    argparse.ArgumentParser(description=__doc__).parse_args()

# Bind imports to this checkout even when WSL's login shell starts elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

workspace = Path(os.environ.get(
    "SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE",
    str(Path.home() / ".local/state/sentientos-hermes-epistemic")))
workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
if workspace.is_symlink():
    raise SystemExit("private_experiment_workspace_cannot_be_symlink")
os.chmod(workspace, 0o700)
os.environ["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = str(workspace)

# Isolate governance writes before importing RuntimeGovernor or its federated
# governance singleton. The runner is a one-shot process, so this scoped
# environment cannot redirect the live companion's or daemon's state.
RUN_ID = "rootless-cognition-cycle-" + uuid.uuid4().hex[:20]
_configured_cycle_id = os.environ.get("SENTIENTOS_HERMES_CYCLE_ID")
if _configured_cycle_id is not None:
    if (not isinstance(_configured_cycle_id, str)
            or re.fullmatch(r"rootless-cognition-cycle-[0-9a-f]{20}",
                _configured_cycle_id, flags=re.ASCII) is None):
        raise SystemExit("hermes_cycle_id_invalid")
    RUN_ID = _configured_cycle_id
RUN_ROOT = (workspace / "sentientos-data" / "rootless-experimental"
    / "developmental-cognition-cycles" / RUN_ID)
RUN_PREREGISTRATION_DIGEST: str | None = None
HISTORY_SEED_EVIDENCE: dict[str, Any] = {
    "schema_version": "sentientos.rootless_developmental_history_seed:v3",
    "status": "not_configured",
    "record_count": 0,
    "receipt_count": 0,
    "source_boundary_digest": None,
    "copied_into_run_store": False,
    "source_runtime_admission_ledger": None,
    "runtime_admission_ledger_copied": False,
    "source_cognition_recovery_state": None,
    "cognition_recovery_state_copied": False,
    "model_attention_verified": False,
}
ACTIVE_HISTORY_CAMPAIGN_BINDING: dict[str, Any] | None = None
WIDE_TRANSFER_PROBE_PREFLIGHT: dict[str, Any] | None = None
HISTORICAL_PAIR_MODEL_IDENTITY_PREFLIGHT_PATH: str | None = None
SOURCE_PROVENANCE_PREFLIGHT_EVIDENCE_PATH: str | None = None
governance_root = RUN_ROOT / "resource-governance"
os.environ["SENTIENTOS_GOVERNOR_ROOT"] = str(governance_root / "governor")
os.environ["SENTIENTOS_FEDERATION_ROOT"] = str(governance_root / "federation")
os.environ["SENTIENTOS_REPO_ROOT"] = str(Path(__file__).resolve().parents[1])

from sentientos.avatar_authoring import renderer_handoff
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.developmental_companion_bridge import ResidentDevelopmentalCompanionBridge
from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
    qualify_history_transfer_decision,
    qualify_restoration_stable_history_association,
    qualify_semantic_history_decision)
from sentientos.developmental_model_replacement_experiment import (
    ObjectivePredictionTask,
    ROOTLESS_INTEGER_AFFINE_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
    rootless_integer_affine_transfer_task_pair,
)
from sentientos.world_state_board import (
    WorldStateSnapshot, record_digest as world_state_record_digest)
from sentientos.embodiment_self_observation import (
    EmbodimentEvidenceOwner, EmbodimentObservation,
    make_synthetic_pre_action_proprioception_observation, semantic_digest)
from sentientos.embodied_consequence import (
    AuthenticatedBridgeIndependentObserver, ConsequenceStore,
    EmbodiedConsequenceError, SyntheticRenderer,
    evaluate_consequence, make_expectation, verify_consequence_attribution)
from sentientos.gaming_companion_bridge import (
    CompanionBridgeReceiver, encode_message)
from sentientos.gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient, CompanionBridgeLoopbackRuntime)
from sentientos.local_model_authority import (
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_PURPOSE, digest_payload, stream_sha256)
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.local_model import (
    ActiveModelIdentity, candidate_artifact_identity,
    candidate_configuration_digest,
    candidate_configuration_digest_from_payload,
    candidate_configuration_payload)
from sentientos.governed_local_model_invocation import validate_receipt
from sentientos.local_runtime_provisioning import semantic_digest as runtime_digest
from sentientos.resident_developmental_cognition import (
    MAX_RESIDENT_COGNITION_TIMEOUT_SECONDS,
    MAX_COGNITION_REQUEST_QUESTION_CHARS,
    TASK_FAMILY_NEGATIVE_EXAMPLE_GUIDANCE_SCHEMA,
    TASK_FAMILY_PRIOR_INCORRECT_EXAMPLE_INSTRUCTION,
    ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionOwner,
    ResidentDevelopmentalCognitionError,
    _task_family_history_examples, _task_family_history_probe_overlap,
    audit_task_family_history_projection, load_objective_request,
    objective_request_payload,
    objective_task_for_request, stage_objective_request)
from sentientos.resident_developmental_writeback import (
    DevelopmentalHistoryStore, DevelopmentalWritebackError,
    ResidentDevelopmentalWritebackController)
from sentientos.runtime_admission import (
    AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier)
from sentientos.rootless_experimental_local_model import (
    EXPERIMENT_ROOT, RootlessExperimentalError, _no_symlink_path)
from sentientos.rootless_experimental_ollama_epistemic_session import (
    ROOTLESS_EXPERIMENTAL_OLLAMA_BACKEND_SEED,
    RootlessExperimentalOllamaDevelopmentalSession,
    verify_rootless_historical_invocation_receipt,
    _rootless_ollama_model_options)
from sentientos.control_plane_kernel import ControlPlaneKernel
from sentientos.federated_enforcement_policy import resolve_policy
from sentientos.host_resource_runtime import (
    HostResourceRuntimeCoordinator, validate_evaluation)
from sentientos.runtime_governor import RuntimeGovernor
from sentientos.world_state_board import WorldStateBoardBuilder
from work.historical_examples_intervention import (
    HistoricalExamplesInterventionError,
    HistoricalExamplesPairJournal,
    build_resident_historical_examples_arm_executor,
    derive_historical_examples_objective_answer_key,
    execute_historical_examples_pair_once,
    make_historical_examples_pair_execution_terminal,
    make_historical_examples_pair_runner_binding,
    validate_historical_examples_pair_execution_plan,
    validate_historical_examples_pair_execution_slot,
)
from work.negative_guidance_intervention import (
    NegativeGuidanceInterventionError,
    NegativeGuidancePairJournal,
    bind_negative_guidance_runtime_preview,
    build_resident_negative_guidance_arm_executor,
    execute_negative_guidance_pair_once,
    prepare_negative_guidance_pair,
    validate_negative_guidance_protocol,
)
from work.strategy_inclusion_intervention import (
    StrategyInclusionInterventionError,
    _digest as _strategy_digest,
    build_resident_strategy_inclusion_arm_executor,
    canonical_strategy_invocation_request_digest,
    execute_and_persist_strategy_inclusion_pair,
    prepare_strategy_inclusion_pair,
    validate_strategy_inclusion_protocol,
)
from work.identity_neutral_history_binding import (
    IdentityNeutralHistoryBindingError,
    verify_identity_neutral_history_binding,
)


MODEL_NAME = os.environ.get("SENTIENTOS_HERMES_MODEL", "sentientos-hermes4:14b-q4km")
HISTORICAL_PAIR_PLAN_ENV = "SENTIENTOS_HERMES_HISTORICAL_PAIR_PLAN_PATH"
HISTORICAL_PAIR_COHORT_ENV = "SENTIENTOS_HERMES_HISTORICAL_PAIR_COHORT_PATH"
HISTORICAL_PAIR_ANALYSIS_ENV = "SENTIENTOS_HERMES_HISTORICAL_PAIR_ANALYSIS_PATH"
HISTORICAL_PAIR_JOURNAL_ENV = "SENTIENTOS_HERMES_HISTORICAL_PAIR_JOURNAL_ROOT"
HISTORICAL_PAIR_PARITY_AUDIT_ENV = (
    "SENTIENTOS_HERMES_HISTORICAL_PAIR_PARITY_AUDIT_PATH")
HISTORICAL_PAIR_ALLOWLIST_ENV = (
    "SENTIENTOS_HERMES_HISTORICAL_PAIR_ALLOWLIST_PATH")
HISTORICAL_PAIR_VERIFICATION_ENV = (
    "SENTIENTOS_HERMES_HISTORICAL_PAIR_VERIFICATION_PATH")
HISTORICAL_PAIR_LEFT_PREFLIGHT_ENV = (
    "SENTIENTOS_HERMES_HISTORICAL_PAIR_LEFT_PREFLIGHT_PATH")
HISTORICAL_PAIR_RIGHT_PREFLIGHT_ENV = (
    "SENTIENTOS_HERMES_HISTORICAL_PAIR_RIGHT_PREFLIGHT_PATH")
HISTORICAL_PAIR_LEFT_PREFLIGHT_VERIFICATION_ENV = (
    "SENTIENTOS_HERMES_HISTORICAL_PAIR_LEFT_PREFLIGHT_VERIFICATION_PATH")
HISTORICAL_PAIR_RIGHT_PREFLIGHT_VERIFICATION_ENV = (
    "SENTIENTOS_HERMES_HISTORICAL_PAIR_RIGHT_PREFLIGHT_VERIFICATION_PATH")
NEGATIVE_GUIDANCE_PREVIEW_ENV = "SENTIENTOS_HERMES_NEGATIVE_GUIDANCE_PREVIEW_PATH"
NEGATIVE_GUIDANCE_JOURNAL_ENV = "SENTIENTOS_HERMES_NEGATIVE_GUIDANCE_JOURNAL_ROOT"
STRATEGY_INCLUSION_PREVIEW_ENV = (
    "SENTIENTOS_HERMES_STRATEGY_INCLUSION_PREVIEW_PATH")
STRATEGY_INCLUSION_JOURNAL_ENV = (
    "SENTIENTOS_HERMES_STRATEGY_INCLUSION_JOURNAL_ROOT")
_MAX_EXPERIMENT_SEED = 2**32 - 1
_MIN_EXPERIMENT_DISK_FREE_BYTES = 2 * 1024**3
_MAX_STRATEGY_RECEIPT_RECOVERY_SCAN_FILES = 32_768
_SOURCE_PROVENANCE_GIT = (
    os.environ.get("SENTIENTOS_SOURCE_PROVENANCE_GIT", "git").strip()
    or "git")
_OBJECTIVE_TRANSFER_TASK_FAMILY = (
    ROOTLESS_INTEGER_AFFINE_TRANSFER_TASK_FAMILY)
_ACTIVE_OBJECTIVE_TRANSFER_TASK_FAMILY = _OBJECTIVE_TRANSFER_TASK_FAMILY
_ACTIVE_OBJECTIVE_TRANSFER_PROBE_COUNT = 3
_SUPPORTED_OBJECTIVE_TRANSFER_TASK_FAMILIES = frozenset({
    "rootless_integer_affine_transfer_low_range_v5",
    _OBJECTIVE_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
})

# Leave bounded space for receipt-backed evidence plus its prior-history packet.
# The model remains configured with an 8,192-token context; this separate
# character guard addresses the 16 KiB history-selection edge seen in replay.
ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT = 24_576
PRE_ACTION_DECISION_QUESTION = (
    "Use only current evidence supplied with this request; "
    "developmental history is withheld. The current scenario_fixture "
    "is a stipulated conditional input, not an observation about the "
    "external world. A separate sensor_observation reports the target "
    "visible and within reach; that reading is also a deterministic "
    "synthetic fixture, not a physical-world observation. Use the "
    "scenario_fixture for the initial pose, task objective, and "
    "transition table, "
    "cite the exact current sensor_observation fact ID for the target "
    "condition and the exact scenario_fixture fact ID for the objective "
    "and transition table. "
    "If the combined evidence supports a conditional proposal, put exactly "
    "one token in response: reach->reach, reach->idle, idle->reach, or "
    "idle->idle. Cite the exact current sensor_observation fact ID for "
    "the target condition and the exact scenario_fixture fact ID for "
    "initial pose, task objective, and transition. "
    "evidence_ids; never invent an ID. If it is missing or insufficient, "
    "abstain with empty evidence_ids. Do not cite history. A proposal "
    "has no action authority and does not claim that an action occurred.")


def _pre_action_clarification_question(ask_text: str) -> str:
    return (
        "This is one bounded clarification turn after your prior "
        "ask. Your prior ask is model-authored conversation context, "
        "not evidence: " + json.dumps(ask_text, ensure_ascii=True)
        + ". Fresh observation supplied; do not repeat it. Name different "
        "evidence or abstain. "
        "A new deterministic synthetic sensor "
        "acquisition returned a sensor_observation with target visible, "
        "within reach, and hazard_status clear. This is a conditional "
        "test fixture, not a physical-world observation. The current "
        "scenario_fixture stipulates initial pose idle, allowed poses "
        "idle and reach, objective reach_marked_target, and transition "
        "table reach->reach and idle->idle. Both inputs are synthetic; "
        "neither establishes physical-world observation. Use the "
        "sensor_observation for target condition and scenario_fixture "
        "for initial pose, objective, and transitions. Based only on these current "
        "inputs, you may now give one exact token "
        "reach->reach, reach->idle, idle->reach, or idle->idle, "
        "cite the exact fact IDs from both sources, ask for further "
        "information, or abstain if the evidence remains "
        "insufficient. Do not cite history or imply action authority.")
ROOTLESS_DEVELOPMENTAL_COGNITION_INFERENCE_TIMEOUT_SECONDS = (
    MAX_RESIDENT_COGNITION_TIMEOUT_SECONDS)


def _runtime_admission_ledger_boundary(path: Path) -> dict[str, Any] | None:
    _no_symlink_path(path)
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise RootlessExperimentalError(
            "history_campaign_runtime_admission_ledger_invalid")
    try:
        admissions, revocations = AdmissionLedger(path).load()
        digest, size = stream_sha256(path)
    except (OSError, ValueError, RuntimeError) as exc:
        raise RootlessExperimentalError(
            "history_campaign_runtime_admission_ledger_invalid") from exc
    return {
        "schema_version": "sentientos.rootless_history_campaign_admission_boundary:v1",
        "sha256": digest,
        "size_bytes": size,
        "admission_count": len(admissions),
        "revocation_count": len(revocations),
        "admission_bindings": [{"admission_id": item.admission_id,
            "binding_digest": item.binding_digest,
            "issued_sequence": item.issued_sequence}
            for item in sorted(admissions, key=lambda item: item.admission_id)],
        "revocation_bindings": [{"revocation_id": item.revocation_id,
            "binding_digest": item.binding_digest,
            "sequence": item.sequence}
            for item in sorted(revocations, key=lambda item: item.revocation_id)],
        "atomic_snapshot": False,
    }


def _validate_history_campaign_launch() -> tuple[
        dict[str, Any] | None, str | None, dict[str, Any] | None,
        dict[str, Any] | None]:
    global _ACTIVE_OBJECTIVE_TRANSFER_TASK_FAMILY
    global _ACTIVE_OBJECTIVE_TRANSFER_PROBE_COUNT
    global WIDE_TRANSFER_PROBE_PREFLIGHT
    WIDE_TRANSFER_PROBE_PREFLIGHT = None
    plan_raw = os.environ.get("SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH")
    prior_raw = os.environ.get("SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT")
    if plan_raw is None or not plan_raw.strip():
        if (prior_raw is not None and prior_raw.strip()
                and not os.environ.get(HISTORICAL_PAIR_PLAN_ENV)
                and not os.environ.get(NEGATIVE_GUIDANCE_PREVIEW_ENV)
                and not os.environ.get(STRATEGY_INCLUSION_PREVIEW_ENV)):
            raise RootlessExperimentalError(
                "history_seed_requires_preregistered_campaign_or_pair_plan")
        return None, None, None, None
    if prior_raw is None or not prior_raw.strip():
        raise RootlessExperimentalError(
            "history_campaign_plan_requires_prior_history_seed")
    plan_path = Path(plan_raw).expanduser()
    try:
        from work.rootless_history_boundary_campaign import (
            _cognition_recovery_state_boundary, _history_boundary, _load_plan,
            verify_experiment_implementation, verify_model_identity_recipe,
        )
        plan = _load_plan(plan_path)
        if plan.get("schema_version") in {
                "sentientos.rootless_history_boundary_campaign_plan:v7",
                "sentientos.rootless_history_boundary_campaign_plan:v8",
                "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13"}:
            verify_model_identity_recipe(plan)
            if plan.get("schema_version") in {
                    "sentientos.rootless_history_boundary_campaign_plan:v8",
                    "sentientos.rootless_history_boundary_campaign_plan:v9",
                    "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                    "sentientos.rootless_history_boundary_campaign_plan:v13"}:
                verify_experiment_implementation(plan)
    except (OSError, ValueError, RuntimeError) as exc:
        raise RootlessExperimentalError(
            "history_campaign_plan_invalid") from exc
    plan_digest = plan.get("plan_digest")
    task_family_id = plan.get("task_family_id")
    if (plan_digest != PREREGISTRATION_DIGEST
            or task_family_id not in _SUPPORTED_OBJECTIVE_TRANSFER_TASK_FAMILIES):
        raise RootlessExperimentalError(
            "history_campaign_plan_external_binding_mismatch")
    if (task_family_id in {ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
            ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY}
            and plan.get("schema_version") !=
                "sentientos.rootless_history_boundary_campaign_plan:v8"
            and plan.get("schema_version") !=
                "sentientos.rootless_history_boundary_campaign_plan:v9"
            and plan.get("schema_version") !=
                "sentientos.rootless_history_boundary_campaign_plan:v10"
            and plan.get("schema_version") !=
                "sentientos.rootless_history_boundary_campaign_plan:v13"
            and (task_family_id != ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY
                or plan.get("schema_version") not in {
                    "sentientos.rootless_history_boundary_campaign_plan:v11",
                    "sentientos.rootless_history_boundary_campaign_plan:v12",
                    "sentientos.rootless_history_boundary_campaign_plan:v13"})):
        raise RootlessExperimentalError(
            "history_campaign_experiment_implementation_unbound")
    model_recipe = plan.get("model_identity_recipe")
    if isinstance(model_recipe, Mapping):
        planned_model_name = model_recipe.get("model_name")
        if planned_model_name != MODEL_NAME:
            raise RootlessExperimentalError(
                "history_campaign_runtime_model_name_mismatch")
        planned_gpu_layers = model_recipe.get("gpu_layers")
        if (type(planned_gpu_layers) is not int
                or planned_gpu_layers != GPU_LAYERS):
            raise RootlessExperimentalError(
                "history_campaign_runtime_gpu_layers_mismatch")
    _ACTIVE_OBJECTIVE_TRANSFER_TASK_FAMILY = task_family_id
    _ACTIVE_OBJECTIVE_TRANSFER_PROBE_COUNT = plan.get("transfer_probe_count", 3)
    cycle_ids = plan.get("ordered_cycle_ids")
    if not isinstance(cycle_ids, list) or cycle_ids.count(RUN_ID) != 1:
        raise RootlessExperimentalError("history_campaign_cycle_not_preregistered")
    index = cycle_ids.index(RUN_ID)
    if (plan["ordered_task_generation_seeds"][index] != EXPERIMENT_SEED
            or plan["ordered_backend_seeds"][index] !=
                ROOTLESS_EXPERIMENTAL_OLLAMA_BACKEND_SEED):
        raise RootlessExperimentalError(
            "history_campaign_seed_binding_mismatch")
    prior_root = Path(prior_raw).expanduser()
    try:
        boundary = _history_boundary(prior_root)
        resolved_prior = prior_root.resolve(strict=True)
    except (OSError, ValueError, RuntimeError) as exc:
        raise RootlessExperimentalError(
            "history_campaign_prior_boundary_invalid") from exc
    if (resolved_prior.name != "history"
            or resolved_prior.parent.name != "resident-cognition"):
        raise RootlessExperimentalError(
            "history_campaign_prior_source_path_invalid")
    if index == 0:
        expected_boundary = plan.get("initial_history_boundary")
        if (not isinstance(expected_boundary, Mapping)
                or boundary.get("boundary_digest") !=
                    expected_boundary.get("boundary_digest")):
            raise RootlessExperimentalError(
                "history_campaign_initial_boundary_mismatch")
    elif resolved_prior.parent.parent.name != cycle_ids[index - 1]:
        raise RootlessExperimentalError(
            "history_campaign_previous_cycle_seed_mismatch")
    admission_path = resolved_prior.parent / "state" / "runtime_admissions.json"
    admission_boundary = _runtime_admission_ledger_boundary(admission_path)
    recovery_boundary = _cognition_recovery_state_boundary(
        resolved_prior.parent / "state")
    if plan.get("schema_version") in {
            "sentientos.rootless_history_boundary_campaign_plan:v5",
            "sentientos.rootless_history_boundary_campaign_plan:v6",
            "sentientos.rootless_history_boundary_campaign_plan:v7",
            "sentientos.rootless_history_boundary_campaign_plan:v8",
            "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13"}:
        if index == 0:
            expected_admission_boundary = plan.get(
                "initial_runtime_admission_ledger")
        else:
            prior_cycle_root = resolved_prior.parent.parent
            terminal_paths = [prior_cycle_root / "cycle-result.json",
                prior_cycle_root / "cycle-failure.json"]
            terminal_path = next((item for item in terminal_paths
                if item.is_file() and not item.is_symlink()), None)
            if terminal_path is None:
                raise RootlessExperimentalError(
                    "history_campaign_previous_cycle_terminal_missing")
            try:
                previous_terminal = json.loads(terminal_path.read_text(
                    encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RootlessExperimentalError(
                    "history_campaign_previous_cycle_terminal_invalid") from exc
            if (not isinstance(previous_terminal, Mapping)
                    or previous_terminal.get("run_id") != cycle_ids[index - 1]):
                raise RootlessExperimentalError(
                    "history_campaign_previous_cycle_terminal_invalid")
            expected_admission_boundary = previous_terminal.get(
                "runtime_admission_ledger")
        if admission_boundary != expected_admission_boundary:
            raise RootlessExperimentalError(
                "history_campaign_runtime_admission_boundary_mismatch")
        if index == 0:
            expected_recovery_boundary = plan.get(
                "initial_cognition_recovery_state")
        else:
            prior_cycle_root = resolved_prior.parent.parent
            terminal_paths = [prior_cycle_root / "cycle-result.json",
                prior_cycle_root / "cycle-failure.json"]
            terminal_path = next((item for item in terminal_paths
                if item.is_file() and not item.is_symlink()), None)
            if terminal_path is None:
                raise RootlessExperimentalError(
                    "history_campaign_previous_cycle_terminal_missing")
            try:
                previous_terminal = json.loads(terminal_path.read_text(
                    encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RootlessExperimentalError(
                    "history_campaign_previous_cycle_terminal_invalid") from exc
            if (not isinstance(previous_terminal, Mapping)
                    or previous_terminal.get("run_id") != cycle_ids[index - 1]):
                raise RootlessExperimentalError(
                    "history_campaign_previous_cycle_terminal_invalid")
            expected_recovery_boundary = previous_terminal.get(
                "cognition_recovery_state_boundary")
        if recovery_boundary != expected_recovery_boundary:
            raise RootlessExperimentalError(
                "history_campaign_recovery_state_boundary_mismatch")
    elif admission_boundary is not None:
        raise RootlessExperimentalError(
            "history_campaign_runtime_admission_boundary_unpinned")
    if task_family_id in {ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
            ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY}:
        acquisition, transfer = rootless_integer_affine_transfer_task_pair(
            EXPERIMENT_SEED, task_family_id=task_family_id,
            transfer_probe_count=plan.get("transfer_probe_count", 3))
        acquisition_inputs = [acquisition.probe_input,
            *acquisition.additional_probe_inputs]
        transfer_inputs = [transfer.probe_input, *transfer.additional_probe_inputs]
        history_task_family_ids = (transfer.history_task_family_ids
            or (task_family_id,))
        if (task_family_id not in history_task_family_ids
                or len(set(history_task_family_ids)) !=
                    len(history_task_family_ids)):
            raise RootlessExperimentalError(
                "history_campaign_transfer_history_families_invalid")
        if set(acquisition_inputs) & set(transfer_inputs):
            raise RootlessExperimentalError(
                "history_campaign_transfer_probe_plan_overlap")
        manifest_files = boundary.get("files")
        if not isinstance(manifest_files, list):
            raise RootlessExperimentalError(
                "history_campaign_transfer_probe_history_invalid")
        manifest_record_digests: dict[str, str] = {}
        for row in manifest_files:
            if not isinstance(row, Mapping):
                raise RootlessExperimentalError(
                    "history_campaign_transfer_probe_history_invalid")
            relative_path = row.get("path")
            if not isinstance(relative_path, str):
                raise RootlessExperimentalError(
                    "history_campaign_transfer_probe_history_invalid")
            if not relative_path.startswith("records/"):
                continue
            if (re.fullmatch(r"records/devrec-[0-9a-f]{24}\.json",
                    relative_path, flags=re.ASCII) is None
                    or not isinstance(row.get("sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", row["sha256"],
                        flags=re.ASCII) is None):
                raise RootlessExperimentalError(
                    "history_campaign_transfer_probe_history_invalid")
            manifest_record_id = (
                relative_path.removeprefix("records/").removesuffix(".json"))
            if manifest_record_id in manifest_record_digests:
                raise RootlessExperimentalError(
                    "history_campaign_transfer_probe_history_invalid")
            manifest_record_digests[manifest_record_id] = row["sha256"]
        try:
            stored_records = DevelopmentalHistoryStore(resolved_prior).records()
        except (OSError, ValueError, RuntimeError, DevelopmentalWritebackError) as exc:
            raise RootlessExperimentalError(
                "history_campaign_transfer_probe_history_invalid") from exc
        stored_record_ids = [record.record_id for record in stored_records]
        if (len(set(stored_record_ids)) != len(stored_record_ids)
                or sorted(manifest_record_digests) != sorted(stored_record_ids)):
            raise RootlessExperimentalError(
                "history_campaign_transfer_probe_history_invalid")
        packets: list[dict[str, Any]] = []
        projected_record_ids: list[str] = []
        for record in stored_records:
            candidate = asdict(record)
            record_id = record.record_id
            serialized_record = (json.dumps(candidate, sort_keys=True, indent=2)
                + "\n").encode("utf-8")
            if hashlib.sha256(serialized_record).hexdigest() != (
                    manifest_record_digests[record_id]):
                raise RootlessExperimentalError(
                    "history_campaign_transfer_probe_history_changed")
            # DevelopmentalHistoryStore persists a record envelope whose
            # cognition candidate is nested under `candidate`. Project that
            # payload, while keeping the envelope's record ID as the lineage
            # binding. Passing the envelope silently hid every retained
            # task-family example from the campaign overlap preflight.
            cognition_candidate = candidate.get("candidate")
            if not isinstance(cognition_candidate, Mapping):
                continue
            projected: list[dict[str, Any]] = []
            for source_family_id in history_task_family_ids:
                projected.extend(_task_family_history_examples(
                    cognition_candidate, task_family_id=source_family_id))
            if projected:
                packets.append({"task_relevant_experience": projected})
                projected_record_ids.append(record_id)
        overlap = _task_family_history_probe_overlap(packets,
            task_probe_inputs=transfer_inputs)
        novel_acquisition_qualified = None
        if task_family_id == ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY:
            acquisition_overlap = _task_family_history_probe_overlap(packets,
                task_probe_inputs=acquisition_inputs)
            novel_acquisition_qualified = (
                acquisition_overlap.get(
                    "historical_probe_overlap_measurement_complete") is True
                and acquisition_overlap.get(
                    "historical_probe_overlap_input_count") == 0)
        try:
            boundary_after = _history_boundary(prior_root)
        except (OSError, ValueError, RuntimeError) as exc:
            raise RootlessExperimentalError(
                "history_campaign_transfer_probe_history_invalid") from exc
        if boundary_after.get("boundary_digest") != boundary.get("boundary_digest"):
            raise RootlessExperimentalError(
                "history_campaign_transfer_probe_history_changed")
        semantic = {
            "schema_version": (
                "sentientos.rootless_campaign_transfer_probe_preflight:v3"
                if task_family_id == ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY
                else "sentientos.rootless_campaign_transfer_probe_preflight:v2"),
            "cycle_id": RUN_ID,
            "seed": EXPERIMENT_SEED,
            "task_family_id": task_family_id,
            "history_task_family_ids": list(history_task_family_ids),
            "prior_history_boundary_digest": boundary["boundary_digest"],
            "projected_record_ids": projected_record_ids,
            "projected_record_set_digest": digest_payload({
                "record_ids": projected_record_ids}),
            "acquisition_probe_inputs": acquisition_inputs,
            "transfer_probe_inputs": transfer_inputs,
            "historical_probe_overlap": overlap,
            "held_out_transfer_qualified": (
                overlap["historical_probe_overlap_measurement_complete"]
                and overlap["historical_probe_overlap_input_count"] == 0),
            "inference_performed": False,
            "learning_claimed": False,
            "authority_granted": False,
        }
        if task_family_id == ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY:
            semantic["acquisition_historical_probe_overlap"] = (
                acquisition_overlap)
            semantic["novel_acquisition_qualified"] = (
                novel_acquisition_qualified is True)
        WIDE_TRANSFER_PROBE_PREFLIGHT = {**semantic,
            "preflight_digest": digest_payload(semantic)}
        if (task_family_id == ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY
                and not semantic["novel_acquisition_qualified"]):
            raise RootlessExperimentalError(
                "history_campaign_acquisition_probe_reuse_in_prior_history")
        if not overlap["historical_probe_overlap_measurement_complete"]:
            raise RootlessExperimentalError(
                "history_campaign_transfer_probe_overlap_unmeasured")
        if overlap["historical_probe_overlap_input_count"]:
            raise RootlessExperimentalError(
                "history_campaign_transfer_probe_reuse_in_prior_history")
    return (dict(plan), str(boundary["boundary_digest"]), admission_boundary,
        recovery_boundary)


def _verify_history_campaign_seed_copy(*, source_root: Path,
        destination_root: Path, destination_state_root: Path,
        expected_boundary_digest: str,
        expected_admission_boundary: Mapping[str, Any] | None,
        expected_recovery_boundary: Mapping[str, Any] | None) -> None:
    from work.rootless_history_boundary_campaign import (
        _cognition_recovery_state_boundary, _history_boundary)

    source_boundary = _history_boundary(source_root)
    copied_boundary = _history_boundary(destination_root)
    if (source_boundary.get("boundary_digest") != expected_boundary_digest
            or copied_boundary.get("boundary_digest") != expected_boundary_digest):
        raise RootlessExperimentalError(
            "history_campaign_seed_copy_boundary_mismatch")
    source_admission = _runtime_admission_ledger_boundary(
        source_root.parent / "state" / "runtime_admissions.json")
    copied_admission = _runtime_admission_ledger_boundary(
        destination_state_root / "runtime_admissions.json")
    if (source_admission != expected_admission_boundary
            or copied_admission != expected_admission_boundary):
        raise RootlessExperimentalError(
            "history_campaign_seed_admission_copy_boundary_mismatch")
    source_recovery = _cognition_recovery_state_boundary(
        source_root.parent / "state")
    copied_recovery = _cognition_recovery_state_boundary(destination_state_root)
    if (source_recovery != expected_recovery_boundary
            or copied_recovery != expected_recovery_boundary):
        raise RootlessExperimentalError(
            "history_campaign_seed_recovery_state_copy_boundary_mismatch")


def _history_intervention_trial_index_from_environment() -> int | None:
    raw = os.environ.get("SENTIENTOS_HERMES_HISTORY_ORDER_TRIAL_INDEX")
    if raw is None:
        return None
    if (len(raw) > 10 or not raw.isascii() or not raw.isdecimal()
            or int(raw) > _MAX_EXPERIMENT_SEED):
        raise SystemExit("hermes_history_order_trial_index_invalid")
    return int(raw)


def _experiment_seed_from_environment() -> int:
    raw = os.environ.get("SENTIENTOS_HERMES_EXPERIMENT_SEED")
    if raw is None:
        return (uuid.uuid4().int & _MAX_EXPERIMENT_SEED) or 1
    if (len(raw) > 10 or not raw.isascii() or not raw.isdecimal()
            or not 0 < int(raw) <= _MAX_EXPERIMENT_SEED):
        raise SystemExit("hermes_experiment_seed_invalid")
    return int(raw)


def _preregistration_digest_from_environment() -> str:
    # Bind a pre-run protocol digest into every governed cycle receipt.
    raw = os.environ.get("SENTIENTOS_HERMES_PREREGISTRATION_DIGEST")
    if raw is None:
        return "0" * 64
    if (len(raw) != 64 or not raw.isascii()
            or any(character not in "0123456789abcdef" for character in raw)):
        raise SystemExit("hermes_preregistration_digest_invalid")
    return raw


def _read_historical_pair_json(path: Path, *, code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise RootlessExperimentalError(code + "_file_invalid")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise RootlessExperimentalError(code + "_duplicate_json_key")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise RootlessExperimentalError(code + "_invalid_json_constant:" + value)

    try:
        value = json.loads(path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RootlessExperimentalError(code + "_unreadable") from exc
    if not isinstance(value, dict):
        raise RootlessExperimentalError(code + "_object_required")
    return value


def _load_historical_pair_execution_context() -> dict[str, Any] | None:
    configured = {name: os.environ.get(name) for name in (
        HISTORICAL_PAIR_PLAN_ENV, HISTORICAL_PAIR_COHORT_ENV,
        HISTORICAL_PAIR_ANALYSIS_ENV, HISTORICAL_PAIR_JOURNAL_ENV,
        HISTORICAL_PAIR_PARITY_AUDIT_ENV, HISTORICAL_PAIR_ALLOWLIST_ENV,
        HISTORICAL_PAIR_VERIFICATION_ENV,
        HISTORICAL_PAIR_LEFT_PREFLIGHT_ENV,
        HISTORICAL_PAIR_RIGHT_PREFLIGHT_ENV,
        HISTORICAL_PAIR_LEFT_PREFLIGHT_VERIFICATION_ENV,
        HISTORICAL_PAIR_RIGHT_PREFLIGHT_VERIFICATION_ENV)}
    required = (HISTORICAL_PAIR_PLAN_ENV, HISTORICAL_PAIR_COHORT_ENV,
        HISTORICAL_PAIR_ANALYSIS_ENV, HISTORICAL_PAIR_JOURNAL_ENV)
    if all(configured[name] is None for name in required):
        if any(configured[name] is not None for name in (
                HISTORICAL_PAIR_PARITY_AUDIT_ENV,
                HISTORICAL_PAIR_ALLOWLIST_ENV,
                HISTORICAL_PAIR_VERIFICATION_ENV,
                HISTORICAL_PAIR_LEFT_PREFLIGHT_ENV,
                HISTORICAL_PAIR_RIGHT_PREFLIGHT_ENV,
                HISTORICAL_PAIR_LEFT_PREFLIGHT_VERIFICATION_ENV,
                HISTORICAL_PAIR_RIGHT_PREFLIGHT_VERIFICATION_ENV)):
            raise RootlessExperimentalError(
                "historical_examples_pair_execution_environment_incomplete")
        return None
    if (any(not isinstance(configured[name], str)
            or not configured[name].strip() for name in required)
            or any(configured[name] is not None and
                (not isinstance(configured[name], str)
                    or not configured[name].strip()) for name in (
                        HISTORICAL_PAIR_PARITY_AUDIT_ENV,
                        HISTORICAL_PAIR_ALLOWLIST_ENV,
                        HISTORICAL_PAIR_VERIFICATION_ENV,
                        HISTORICAL_PAIR_LEFT_PREFLIGHT_ENV,
                        HISTORICAL_PAIR_RIGHT_PREFLIGHT_ENV,
                        HISTORICAL_PAIR_LEFT_PREFLIGHT_VERIFICATION_ENV,
                        HISTORICAL_PAIR_RIGHT_PREFLIGHT_VERIFICATION_ENV))):
        raise RootlessExperimentalError(
            "historical_examples_pair_execution_environment_incomplete")
    plan = _read_historical_pair_json(Path(configured[HISTORICAL_PAIR_PLAN_ENV]),
        code="historical_examples_pair_plan")
    cohort = _read_historical_pair_json(Path(configured[HISTORICAL_PAIR_COHORT_ENV]),
        code="historical_examples_pair_cohort")
    analysis_plan = _read_historical_pair_json(
        Path(configured[HISTORICAL_PAIR_ANALYSIS_ENV]),
        code="historical_examples_pair_analysis")
    trials = plan.get("trials")
    if not isinstance(trials, list) or not trials:
        raise RootlessExperimentalError(
            "historical_examples_pair_plan_trials_invalid")
    try:
        runner_ids = [row["runner_cycle_id"] for row in trials]
        backend_seeds = {row["backend_seed"] for row in trials}
    except (KeyError, TypeError) as exc:
        raise RootlessExperimentalError(
            "historical_examples_pair_plan_roster_invalid") from exc
    if len(backend_seeds) != 1:
        raise RootlessExperimentalError(
            "historical_examples_pair_backend_seed_mismatch")
    backend_seed = next(iter(backend_seeds))
    try:
        plan = validate_historical_examples_pair_execution_plan(
            cohort=cohort, analysis_plan=analysis_plan,
            runner_cycle_ids=runner_ids, backend_seed=backend_seed, plan=plan)
    except HistoricalExamplesInterventionError as exc:
        raise RootlessExperimentalError(
            "historical_examples_pair_plan_verification_failed") from exc
    matches = [index for index, row in enumerate(plan["trials"])
        if row.get("runner_cycle_id") == RUN_ID]
    if len(matches) != 1:
        raise RootlessExperimentalError(
            "historical_examples_pair_runner_id_not_in_plan")
    trial_index = matches[0]
    slot = plan["trials"][trial_index]
    if (backend_seed != ROOTLESS_EXPERIMENTAL_OLLAMA_BACKEND_SEED
            or EXPERIMENT_SEED != slot.get("task_generation_seed")
            or PREREGISTRATION_DIGEST != plan[
                "execution_plan_digest"].removeprefix("sha256:")):
        raise RootlessExperimentalError(
            "historical_examples_pair_runtime_preregistration_mismatch")
    prior_history_root = os.environ.get(
        "SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT")
    if not isinstance(prior_history_root, str) or not prior_history_root.strip():
        raise RootlessExperimentalError(
            "historical_examples_pair_prior_history_root_required")
    source_history_root = Path(prior_history_root).expanduser()
    _no_symlink_path(source_history_root)
    try:
        source_history_resolved = source_history_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RootlessExperimentalError(
            "historical_examples_pair_prior_history_root_invalid") from exc
    if (source_history_resolved.name != "history"
            or source_history_resolved.parent.name != "resident-cognition"
            or source_history_resolved.parent.parent.name !=
                plan.get("source_cycle_root_id")):
        raise RootlessExperimentalError(
            "historical_examples_pair_prior_history_source_mismatch")
    source_cycle_root = source_history_resolved.parent.parent
    source_receipt_path = (source_cycle_root / "inference-custody" / "receipts"
        / (plan["source_receipt_id"] + ".json"))
    _no_symlink_path(source_receipt_path)
    source_receipt = _read_historical_pair_json(source_receipt_path,
        code="historical_examples_pair_source_receipt")
    receipt_valid, _receipt_reasons = validate_receipt(source_receipt)
    source_request = source_receipt.get("request")
    source_model_identity = (source_request.get("active_model_identity")
        if isinstance(source_request, Mapping) else None)
    if (not receipt_valid
            or source_receipt.get("receipt_id") != plan["source_receipt_id"]
            or source_receipt.get("receipt_digest")
                != plan["source_receipt_digest"]
            or source_receipt.get("status") != "admitted_completed"
            or not isinstance(source_model_identity, Mapping)):
        raise RootlessExperimentalError(
            "historical_examples_pair_source_model_identity_invalid")
    source_generation = source_receipt.get("generation_config")
    source_timeout = (source_generation.get("timeout_seconds")
        if isinstance(source_generation, Mapping) else None)
    source_input_limit = (source_generation.get("max_input_chars")
        if isinstance(source_generation, Mapping) else None)
    if (type(source_timeout) is not int or not 1 <= source_timeout <= 300
            or type(source_input_limit) is not int
            or not 1024 <= source_input_limit <= 48_000):
        raise RootlessExperimentalError(
            "historical_examples_pair_source_generation_bounds_invalid")
    source_linkage = source_request.get("linkage")
    source_session_binding = (source_linkage.get(
        "rootless_experimental_session")
        if isinstance(source_linkage, Mapping) else None)
    source_run_id = (source_session_binding.get("run_id")
        if isinstance(source_session_binding, Mapping) else None)
    source_preregistration_digest = (source_session_binding.get(
        "preregistration_digest")
        if isinstance(source_session_binding, Mapping) else None)
    if (not isinstance(source_run_id, str)
            or re.fullmatch(r"rootless-cognition-cycle-[0-9a-f]{20}",
                source_run_id) is None
            or not isinstance(source_preregistration_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}",
                source_preregistration_digest) is None):
        raise RootlessExperimentalError(
            "historical_examples_pair_source_preregistration_binding_invalid")
    source_preregistration_path = (source_cycle_root.parent / source_run_id
        / "preregistration.json")
    _no_symlink_path(source_preregistration_path)
    source_configuration_observation_status = (
        "source_preregistration_unavailable")
    source_model_configuration_observation: dict[str, Any] | None = None
    if source_preregistration_path.is_file():
        source_preregistration = _read_historical_pair_json(
            source_preregistration_path,
            code="historical_examples_pair_source_preregistration")
        saved_source_preregistration_digest = source_preregistration.get(
            "preregistration_digest")
        source_preregistration_body = dict(source_preregistration)
        source_preregistration_body.pop("preregistration_digest", None)
        if (saved_source_preregistration_digest
                != source_preregistration_digest
                or runtime_digest(source_preregistration_body)
                    != source_preregistration_digest
                or source_preregistration.get("run_id") != source_run_id
                or source_preregistration.get("model_identity")
                    != dict(source_model_identity)):
            raise RootlessExperimentalError(
                "historical_examples_pair_source_preregistration_mismatch")
        source_model_configuration = source_preregistration.get(
            "model_configuration_observation")
        if source_model_configuration is None:
            source_configuration_observation_status = (
                "source_preregistration_did_not_retain_configuration_payload")
        elif isinstance(source_model_configuration, Mapping):
            source_configuration_payload = source_model_configuration.get(
                "payload")
            try:
                source_configuration_digest = (
                    candidate_configuration_digest_from_payload(
                        source_configuration_payload))
            except (TypeError, ValueError) as exc:
                raise RootlessExperimentalError(
                    "historical_examples_pair_source_configuration_payload_invalid") from exc
            if (source_model_configuration.get("schema_version") !=
                    "sentientos.active_model_configuration_observation:v1"
                    or source_model_configuration.get("configuration_digest")
                        != source_model_identity.get("configuration_digest")
                    or source_configuration_digest
                        != source_model_identity.get("configuration_digest")):
                raise RootlessExperimentalError(
                    "historical_examples_pair_source_configuration_digest_mismatch")
            source_model_configuration_observation = dict(
                source_model_configuration)
            source_configuration_observation_status = (
                "source_configuration_payload_verified")
        else:
            raise RootlessExperimentalError(
                "historical_examples_pair_source_configuration_payload_invalid")
    journal_root = Path(configured[HISTORICAL_PAIR_JOURNAL_ENV]).expanduser()
    _no_symlink_path(journal_root)
    if not journal_root.is_dir():
        raise RootlessExperimentalError(
            "historical_examples_pair_journal_root_invalid")
    journal = HistoricalExamplesPairJournal(
        store=DevelopmentalExperimentStore(journal_root))
    protocol = journal.load_protocol(protocol_digest=slot["protocol_digest"])
    for arm in protocol["conditions"]:
        arm_history = journal.arm_execution_history(
            protocol_digest=slot["protocol_digest"], arm=arm)
        if arm_history["status"] != "not_started":
            raise RootlessExperimentalError(
                f"historical_examples_pair_slot_previously_claimed:{arm}:{arm_history['status']}")
    objective_task = journal.load_task_for_protocol(
        protocol_digest=slot["protocol_digest"])
    try:
        identity_neutral_history_binding = (
            verify_identity_neutral_history_binding(
                objective_task=objective_task, protocol=protocol,
                target_identity_digest=plan["target_model_identity_digest"],
                parity_audit_path=configured[HISTORICAL_PAIR_PARITY_AUDIT_ENV],
                allowlist_path=configured[HISTORICAL_PAIR_ALLOWLIST_ENV],
                pair_verification_path=configured[
                    HISTORICAL_PAIR_VERIFICATION_ENV],
                left_preflight_path=configured[
                    HISTORICAL_PAIR_LEFT_PREFLIGHT_ENV],
                right_preflight_path=configured[
                    HISTORICAL_PAIR_RIGHT_PREFLIGHT_ENV],
                left_preflight_verification_path=configured[
                    HISTORICAL_PAIR_LEFT_PREFLIGHT_VERIFICATION_ENV],
                right_preflight_verification_path=configured[
                    HISTORICAL_PAIR_RIGHT_PREFLIGHT_VERIFICATION_ENV],
                source_cycle_root=source_cycle_root))
    except IdentityNeutralHistoryBindingError as exc:
        raise RootlessExperimentalError(
            "historical_examples_pair_identity_neutral_history_binding_failed") from exc
    try:
        slot_binding = validate_historical_examples_pair_execution_slot(
            plan=plan, trial_index=trial_index, protocol=protocol,
            objective_task=objective_task, runner_cycle_id=RUN_ID,
            backend_seed=backend_seed)
    except HistoricalExamplesInterventionError as exc:
        raise RootlessExperimentalError(
            "historical_examples_pair_journal_slot_mismatch") from exc
    return {"plan": plan, "cohort": cohort,
        "mode": "historical_examples",
        "analysis_plan": analysis_plan, "trial_index": trial_index,
        "protocol": protocol, "objective_task": objective_task,
        "slot_binding": slot_binding, "journal": journal,
        "backend_seed": backend_seed,
        "identity_neutral_history_binding": identity_neutral_history_binding,
        "prior_history_root": source_history_resolved,
        "source_model_identity": dict(source_model_identity),
        "source_preregistration_digest": source_preregistration_digest,
        "source_configuration_observation_status":
            source_configuration_observation_status,
        "source_model_configuration_observation":
            source_model_configuration_observation,
        "source_timeout_seconds": source_timeout,
        "source_max_input_chars": source_input_limit}


def _load_negative_guidance_execution_context() -> dict[str, Any] | None:
    configured = {"preview": os.environ.get(NEGATIVE_GUIDANCE_PREVIEW_ENV),
        "journal": os.environ.get(NEGATIVE_GUIDANCE_JOURNAL_ENV)}
    if all(value is None for value in configured.values()):
        return None
    if any(not isinstance(value, str) or not value.strip()
            for value in configured.values()):
        raise RootlessExperimentalError(
            "negative_guidance_execution_environment_incomplete")
    report_path = Path(configured["preview"]).expanduser()
    _no_symlink_path(report_path)
    report = _read_historical_pair_json(report_path,
        code="negative_guidance_preview_report")
    protocol = report.get("negative_guidance_execution_protocol")
    preview = report.get("owner_pair_preview")
    if (report.get("schema_version") !=
            "sentientos.resident_negative_guidance_prompt_preview:v1"
            or report.get("model_loaded") is not False
            or report.get("model_invoked") is not False
            or report.get("inference_performed") is not False
            or not isinstance(protocol, Mapping)
            or not isinstance(preview, Mapping)):
        raise RootlessExperimentalError(
            "negative_guidance_preview_report_invalid")
    try:
        validate_negative_guidance_protocol(protocol)
        reconstructed = prepare_negative_guidance_pair(
            preview=preview,
            target_model_identity_digest=report[
                "source_model_identity_digest"],
            task_digest=report["task_digest"],
            private_task_plan_digest=report["private_task_plan_digest"],
            generation_config_digest=report["generation_config_digest"],
            answer_key_digest=report["answer_key_digest"],
            held_out_probe_overlap_audit=report[
                "held_out_probe_overlap_audit"],
            held_out_probe_overlap_audit_digest=protocol[
                "held_out_probe_overlap_audit_digest"],
            arm_order=protocol["conditions"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RootlessExperimentalError(
            "negative_guidance_preview_protocol_reconstruction_failed") from exc
    if reconstructed != dict(protocol):
        raise RootlessExperimentalError(
            "negative_guidance_preview_protocol_mismatch")
    if PREREGISTRATION_DIGEST != protocol["protocol_digest"].removeprefix(
            "sha256:"):
        raise RootlessExperimentalError(
            "negative_guidance_preregistration_digest_mismatch")
    journal_root = Path(configured["journal"]).expanduser()
    _no_symlink_path(journal_root)
    if not journal_root.is_dir():
        raise RootlessExperimentalError(
            "negative_guidance_journal_root_invalid")
    journal_store = DevelopmentalExperimentStore(journal_root)
    task_journal = HistoricalExamplesPairJournal(store=journal_store)
    objective_task = task_journal.load_private_task_plan(
        task_digest=protocol["task_digest"],
        task_plan_digest=protocol["private_task_plan_digest"])
    if objective_task.public_descriptor().get("task_digest") != report.get(
            "task_digest"):
        raise RootlessExperimentalError(
            "negative_guidance_private_task_binding_mismatch")
    cycle_root_id = report.get("cycle_root_id")
    source_receipt_id = report.get("source_receipt_id")
    source_receipt_digest = report.get("source_receipt_digest")
    if (not isinstance(cycle_root_id, str)
            or re.fullmatch(r"rootless-cognition-cycle-[0-9]{20}",
                cycle_root_id, flags=re.ASCII) is None
            or not isinstance(source_receipt_id, str)
            or not isinstance(source_receipt_digest, str)):
        raise RootlessExperimentalError(
            "negative_guidance_preview_source_binding_invalid")
    source_cycle_root = (workspace / "sentientos-data" /
        "rootless-experimental" / "developmental-cognition-cycles" /
        cycle_root_id)
    source_receipt_path = (source_cycle_root / "inference-custody" /
        "receipts" / (source_receipt_id + ".json"))
    _no_symlink_path(source_receipt_path)
    source_receipt = _read_historical_pair_json(source_receipt_path,
        code="negative_guidance_source_receipt")
    valid, _reasons = validate_receipt(source_receipt)
    request = source_receipt.get("request")
    source_identity = (request.get("active_model_identity")
        if isinstance(request, Mapping) else None)
    if (not valid or source_receipt.get("receipt_digest") !=
            source_receipt_digest or source_receipt.get("receipt_id") !=
            source_receipt_id or not isinstance(source_identity, Mapping)
            or "sha256:" + digest_payload(dict(source_identity)) !=
                protocol["target_model_identity_digest"]):
        raise RootlessExperimentalError(
            "negative_guidance_preview_source_receipt_mismatch")
    source_generation = source_receipt.get("generation_config")
    source_timeout = (source_generation.get("timeout_seconds")
        if isinstance(source_generation, Mapping) else None)
    source_input_limit = (source_generation.get("max_input_chars")
        if isinstance(source_generation, Mapping) else None)
    if (type(source_timeout) is not int or not 1 <= source_timeout <= 300
            or type(source_input_limit) is not int
            or not 1024 <= source_input_limit <= 48_000):
        raise RootlessExperimentalError(
            "negative_guidance_source_generation_bounds_invalid")
    prior_history_raw = os.environ.get("SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT")
    if not isinstance(prior_history_raw, str) or not prior_history_raw.strip():
        raise RootlessExperimentalError(
            "negative_guidance_prior_history_root_required")
    prior_history_root = Path(prior_history_raw).expanduser()
    _no_symlink_path(prior_history_root)
    prior_history_resolved = prior_history_root.resolve(strict=True)
    if (prior_history_resolved.name != "history"
            or prior_history_resolved.parent.name != "resident-cognition"
            or prior_history_resolved.parent.parent.name != cycle_root_id):
        raise RootlessExperimentalError(
            "negative_guidance_prior_history_source_mismatch")
    return {"mode": "negative_guidance", "report": report,
        "protocol": dict(protocol), "preview": dict(preview),
        "objective_task": objective_task,
        "journal": NegativeGuidancePairJournal(store=journal_store),
        "plan": {"target_model_identity_digest": protocol[
            "target_model_identity_digest"],
            "source_receipt_id": source_receipt_id,
            "source_receipt_digest": source_receipt_digest},
        "source_model_identity": dict(source_identity),
        "source_preregistration_digest": None,
        "source_configuration_observation_status":
            "source_receipt_identity_verified",
        "source_model_configuration_observation": None,
        "source_timeout_seconds": source_timeout,
        "source_max_input_chars": source_input_limit,
        "prior_history_root": prior_history_resolved}


def _load_strategy_inclusion_execution_context() -> dict[str, Any] | None:
    configured = {
        "preview": os.environ.get(STRATEGY_INCLUSION_PREVIEW_ENV),
        "journal": os.environ.get(STRATEGY_INCLUSION_JOURNAL_ENV),
    }
    if all(value is None for value in configured.values()):
        return None
    if any(not isinstance(value, str) or not value.strip()
            for value in configured.values()):
        raise RootlessExperimentalError(
            "strategy_inclusion_execution_environment_incomplete")
    report_path = Path(configured["preview"]).expanduser()
    _no_symlink_path(report_path)
    report = _read_historical_pair_json(report_path,
        code="strategy_inclusion_preview_report")
    protocol = report.get("strategy_pair_protocol")
    if (report.get("schema_version") !=
            "sentientos.resident_strategy_inclusion_cpu_preflight:v3"
            or report.get("model_loaded") is not False
            or report.get("model_invoked") is not False
            or report.get("learning_established") is not False
            or report.get("authority") is not False
            or report.get("private_task_plan_persisted") is not True
            or report.get("strategy_protocol_persisted") is not True
            or not isinstance(protocol, Mapping)
            or protocol.get("schema_version") !=
                "sentientos.strategy_inclusion_intervention_protocol:v6"):
        raise RootlessExperimentalError(
            "strategy_inclusion_preview_report_invalid")
    cycle_root_id = report.get("cycle_root_id")
    if (not isinstance(cycle_root_id, str)
            or re.fullmatch(r"rootless-cognition-cycle-[0-9]{20}",
                cycle_root_id, flags=re.ASCII) is None):
        raise RootlessExperimentalError(
            "strategy_inclusion_source_cycle_invalid")
    source_cycle_root = (workspace / "sentientos-data" /
        "rootless-experimental" / "developmental-cognition-cycles" /
        cycle_root_id)
    journal_root = Path(configured["journal"]).expanduser()
    _no_symlink_path(journal_root)
    if not journal_root.is_dir():
        raise RootlessExperimentalError(
            "strategy_inclusion_journal_root_invalid")
    try:
        from scripts.verify_resident_strategy_inclusion_preflight import (
            _verify_preflight,
        )
        verification = _verify_preflight(report_path=report_path,
            journal_root=journal_root,
            cycle_root=source_cycle_root)
        validate_strategy_inclusion_protocol(protocol=protocol,
            target_model_identity_digest=report.get(
                "source_model_identity_digest"),
            task_digest=report.get("task_digest"))
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
        raise RootlessExperimentalError(
            "strategy_inclusion_persisted_preflight_verification_failed") from exc
    if (verification.get("private_task_plan_reloaded") is not True
            or verification.get("strategy_protocol_reloaded") is not True
            or verification.get("answer_key_commitment_verified") is not True
            or verification.get("source_receipt_verified") is not True
            or verification.get("selected_history_records_verified") is not True):
        raise RootlessExperimentalError(
            "strategy_inclusion_persisted_preflight_incomplete")
    store = DevelopmentalExperimentStore(journal_root)
    task_journal = HistoricalExamplesPairJournal(store=store)
    task = task_journal.load_private_task_plan(
        task_digest=protocol["task_digest"],
        task_plan_digest=protocol["private_task_plan_digest"])
    descriptor = task.public_descriptor()
    specification = task.specification()
    probes = descriptor.get("probe_inputs")
    multiplier = specification.get("multiplier")
    offset = specification.get("offset")
    if (not isinstance(probes, (list, tuple)) or not probes
            or type(multiplier) is not int or type(offset) is not int):
        raise RootlessExperimentalError(
            "strategy_inclusion_private_answer_key_invalid")
    answer_key = {_strategy_digest({
        "schema_version": "sentientos.objective_probe_binding:v1",
        "task_digest": descriptor["task_digest"],
        "probe_index": index, "probe_input": probe,
    }): multiplier * probe + offset
        for index, probe in enumerate(probes)}
    if (_strategy_digest(answer_key) != protocol.get("answer_key_digest")
            or set(answer_key) != set(protocol.get("probe_binding_digests", ()))):
        raise RootlessExperimentalError(
            "strategy_inclusion_private_answer_key_commitment_mismatch")
    if PREREGISTRATION_DIGEST != protocol.get(
            "protocol_digest", "").removeprefix("sha256:"):
        raise RootlessExperimentalError(
            "strategy_inclusion_preregistration_digest_mismatch")
    source_receipt_path = (source_cycle_root / "inference-custody" /
        "receipts" / (str(report["source_receipt_id"]) + ".json"))
    _no_symlink_path(source_receipt_path)
    source_receipt = _read_historical_pair_json(source_receipt_path,
        code="strategy_inclusion_source_receipt")
    valid_receipt, reasons = validate_receipt(source_receipt)
    source_request = source_receipt.get("request")
    source_identity = (source_request.get("active_model_identity")
        if isinstance(source_request, Mapping) else None)
    source_generation = source_receipt.get("generation_config")
    source_timeout = (source_generation.get("timeout_seconds")
        if isinstance(source_generation, Mapping) else None)
    source_input_limit = (source_generation.get("max_input_chars")
        if isinstance(source_generation, Mapping) else None)
    if (not valid_receipt
            or source_receipt.get("receipt_id") != report.get("source_receipt_id")
            or source_receipt.get("receipt_digest") != report.get(
                "source_receipt_digest")
            or not isinstance(source_identity, Mapping)
            or "sha256:" + digest_payload(dict(source_identity)) !=
                protocol.get("target_model_identity_digest")
            or type(source_timeout) is not int
            or not 1 <= source_timeout <= 300
            or type(source_input_limit) is not int
            or not 1024 <= source_input_limit <= 48_000):
        raise RootlessExperimentalError(
            "strategy_inclusion_source_receipt_invalid:" +
            ",".join(reasons))
    prior_history_raw = os.environ.get(
        "SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT")
    if not isinstance(prior_history_raw, str) or not prior_history_raw.strip():
        raise RootlessExperimentalError(
            "strategy_inclusion_prior_history_root_required")
    prior_history_root = Path(prior_history_raw).expanduser()
    _no_symlink_path(prior_history_root)
    prior_history_resolved = prior_history_root.resolve(strict=True)
    expected_history_root = (source_cycle_root / "resident-cognition" / "history")
    if (prior_history_resolved != expected_history_root.resolve(strict=True)
            or descriptor.get("task_digest") != protocol.get("task_digest")):
        raise RootlessExperimentalError(
            "strategy_inclusion_prior_history_source_mismatch")
    return {
        "mode": "strategy_inclusion", "report": report,
        "protocol": dict(protocol), "objective_task": task,
        "answer_key": answer_key, "store": store,
        "source_model_identity": dict(source_identity),
        "plan": {"target_model_identity_digest": protocol[
            "target_model_identity_digest"],
            "source_receipt_id": report["source_receipt_id"],
            "source_receipt_digest": report["source_receipt_digest"]},
        "trial_index": None, "source_preregistration_digest": None,
        "source_configuration_observation_status":
            "source_receipt_identity_verified",
        "source_model_configuration_observation": None,
        "source_timeout_seconds": source_timeout,
        "source_max_input_chars": source_input_limit,
        "prior_history_root": prior_history_resolved,
    }


def _write_private_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    _no_symlink_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, sort_keys=True, indent=2,
                ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _persist_historical_pair_preload_binding(
        context: Mapping[str, Any]) -> str | None:
    binding = context.get("identity_neutral_history_binding")
    if binding is None:
        return None
    if not isinstance(binding, Mapping) or binding.get(
            "source_parity_reconstruction_verified") is not True:
        raise RootlessExperimentalError(
            "historical_pair_preload_binding_unverified")
    semantic = {
        "schema_version":
            "sentientos.historical_pair_identity_neutral_preload_binding:v1",
        "run_id": RUN_ID,
        "execution_plan_digest": context["plan"]["execution_plan_digest"],
        "protocol_digest": context["protocol"]["protocol_digest"],
        "target_model_identity_digest": context["plan"][
            "target_model_identity_digest"],
        "binding_evidence": dict(binding),
        "model_loaded": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    receipt = {**semantic,
        "receipt_digest": "sha256:" + digest_payload(semantic)}
    path = RUN_ROOT / "historical_pair_identity_neutral_preload_binding.json"
    _write_private_json_exclusive(path, receipt)
    context["identity_neutral_preload_binding_path"] = str(path)
    return receipt["receipt_digest"]


def _execute_historical_pair_slot(*, context: Mapping[str, Any],
        owner: ResidentDevelopmentalCognitionOwner, session: Any,
        history_seed_evidence: Mapping[str, Any],
        runtime_bundle_digest: str,
        resource_preflight_evidence: Mapping[str, Any],
        invocation_resource_evidence: list[dict[str, Any]],
        source_provenance_at_start: Mapping[str, Any]) -> dict[str, Any]:
    global RUN_SOURCE_PROVENANCE_AT_END, RUN_FAILURE_DIAGNOSTIC
    plan = context["plan"]
    protocol = context["protocol"]
    objective_task = context["objective_task"]
    trial_index = context["trial_index"]
    journal = context["journal"]
    if (history_seed_evidence.get("status") != "copied_and_reloaded_verified"
            or history_seed_evidence.get("copied_into_run_store") is not True):
        raise RootlessExperimentalError(
            "historical_examples_pair_history_seed_not_verified")
    model_identity_digest = "sha256:" + digest_payload(
        dict(session.active_model_identity))
    if model_identity_digest != plan.get("target_model_identity_digest"):
        raise RootlessExperimentalError(
            "historical_examples_pair_model_identity_mismatch")

    snapshot = WorldStateBoardBuilder(clock=lambda: datetime(
        2026, 11, 23, tzinfo=timezone.utc)).build((),
            manifest_id="resident-historical-examples-cpu-preflight")
    tick_ids = protocol.get("owner_execution_tick_ids")
    included_tick = (tick_ids.get("examples_included")
        if isinstance(tick_ids, Mapping) else None)
    omitted_tick = (tick_ids.get("examples_omitted")
        if isinstance(tick_ids, Mapping) else None)
    included_suffix = ":raw_examples-preview:examples_included"
    omitted_suffix = ":raw_examples-preview:examples_omitted"
    if (not isinstance(included_tick, str)
            or not included_tick.endswith(included_suffix)
            or not isinstance(omitted_tick, str)
            or not omitted_tick.endswith(omitted_suffix)
            or included_tick[:-len(included_suffix)] !=
                omitted_tick[:-len(omitted_suffix)]):
        raise RootlessExperimentalError(
            "historical_examples_pair_preview_tick_invalid")
    history_record_ids = protocol.get("history_record_ids")
    if (not isinstance(history_record_ids, (list, tuple))
            or not history_record_ids
            or any(not isinstance(record_id, str) or not record_id
                for record_id in history_record_ids)
            or len(set(history_record_ids)) != len(history_record_ids)):
        raise RootlessExperimentalError(
            "historical_examples_pair_history_allowlist_invalid")
    preview = owner.preview_objective_historical_examples_pair(
        snapshot=snapshot,
        tick_id=included_tick[:-len(included_suffix)],
        objective_task=objective_task,
        history_record_allowlist=tuple(history_record_ids))
    def _digest_body(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        body = value.removeprefix("sha256:")
        return body if re.fullmatch(r"[0-9a-f]{64}", body) else None

    owner_protocols = preview.get("owner_protocols")
    observed_owner_protocol_digests = ({arm: row.get("protocol_digest")
        for arm, row in owner_protocols.items() if isinstance(row, Mapping)}
        if isinstance(owner_protocols, Mapping) else None)
    observed_owner_task_plan_digests = ({arm: row.get(
        "objective_task_plan_digest") for arm, row in owner_protocols.items()
        if isinstance(row, Mapping)}
        if isinstance(owner_protocols, Mapping) else None)
    observed_owner_protocol_field_digests = ({
        arm: {
            str(key): "sha256:" + digest_payload(value)
            for key, value in row.get("protocol", {}).items()
            if isinstance(key, str) and not (
                row.get("protocol", {}).get("schema_version") ==
                    "sentientos.developmental_history_intervention_protocol:v15"
                and key == "authority_map_digest")
        }
        for arm, row in owner_protocols.items()
        if isinstance(row, Mapping)
        and isinstance(row.get("protocol"), Mapping)
    } if isinstance(owner_protocols, Mapping) else None)
    observed_authority_map_digests = ({
        arm: (row.get("protocol", {}).get("authority_map_policy_digest")
            or row.get("protocol", {}).get("authority_map_digest"))
        for arm, row in owner_protocols.items()
        if isinstance(row, Mapping)
        and isinstance(row.get("protocol"), Mapping)
    } if isinstance(owner_protocols, Mapping) else None)
    observed_authority_map_observation_digests = ({
        arm: row.get("protocol", {}).get("authority_map_digest")
        for arm, row in owner_protocols.items()
        if isinstance(row, Mapping)
        and isinstance(row.get("protocol"), Mapping)
    } if isinstance(owner_protocols, Mapping) else None)
    expected_owner_protocol_field_digests = protocol.get(
        "owner_protocol_field_digests_by_arm")
    owner_protocol_field_differences = None
    if (isinstance(expected_owner_protocol_field_digests, Mapping)
            and isinstance(observed_owner_protocol_field_digests, Mapping)):
        owner_protocol_field_differences = {
            arm: sorted(key for key in set(expected_owner_protocol_field_digests.get(
                arm, {})) | set(observed_owner_protocol_field_digests.get(arm, {}))
                if expected_owner_protocol_field_digests.get(arm, {}).get(key)
                    != observed_owner_protocol_field_digests.get(arm, {}).get(key))
            for arm in ("examples_included", "examples_omitted")}
    expected_authority_map_digests = protocol.get("owner_authority_map_digests")
    # Full governed request digests are regenerated per process and bind the
    # runtime authority-map snapshot and session linkage. Compare their stable
    # cognitive/owner bindings below; retain request digests as diagnostics.
    preview_bindings = {
        "snapshot_id_matches": preview.get("snapshot_id") ==
            protocol.get("snapshot_id"),
        "snapshot_digest_matches": _digest_body(preview.get(
            "snapshot_digest")) == _digest_body(protocol.get("snapshot_digest")),
        "target_model_identity_digest_matches": preview.get(
            "target_model_identity_digest") == model_identity_digest,
        "owner_protocol_digests_match": observed_owner_protocol_digests ==
            protocol.get("owner_protocol_digests"),
        "owner_task_plan_digests_match": observed_owner_task_plan_digests ==
            protocol.get("owner_task_plan_digests"),
        "owner_protocol_fields_match": (
            expected_owner_protocol_field_digests is None
            or observed_owner_protocol_field_digests ==
                expected_owner_protocol_field_digests),
        "owner_authority_map_digests_match": (
            expected_authority_map_digests is None
            or observed_authority_map_digests == expected_authority_map_digests),
        "history_record_ids_match": preview.get("history_record_ids") ==
            protocol.get("history_record_ids"),
        "history_record_digests_match": preview.get(
            "history_record_digests") == protocol.get("history_record_digests"),
        "invocation_prompt_digests_match": preview.get(
            "invocation_prompt_digests") == protocol.get(
                "invocation_prompt_digests"),
    }
    if not all(preview_bindings.values()):
        RUN_FAILURE_DIAGNOSTIC = {
            "schema_version":
                "sentientos.historical_examples_pair_preview_mismatch:v3",
            **preview_bindings,
            "expected_pair_preview_digest": protocol.get(
                "owner_prompt_pair_preview_digest"),
            "observed_pair_preview_digest": preview.get(
                "pair_preview_digest"),
            "expected_snapshot_id": protocol.get("snapshot_id"),
            "observed_snapshot_id": preview.get("snapshot_id"),
            "expected_snapshot_digest": protocol.get("snapshot_digest"),
            "observed_snapshot_digest": preview.get("snapshot_digest"),
            "expected_target_model_identity_digest": model_identity_digest,
            "observed_target_model_identity_digest": preview.get(
                "target_model_identity_digest"),
            "expected_preview_request_digests": protocol.get(
                "preview_request_digests"),
            "observed_preview_request_digests": preview.get(
                "preview_request_digests"),
            "expected_owner_protocol_digests": protocol.get(
                "owner_protocol_digests"),
            "observed_owner_protocol_digests":
                observed_owner_protocol_digests,
            "observed_owner_protocol_field_digests":
                observed_owner_protocol_field_digests,
            "expected_owner_protocol_field_digests":
                expected_owner_protocol_field_digests,
            "owner_protocol_field_differences":
                owner_protocol_field_differences,
            "expected_authority_map_digests": expected_authority_map_digests,
            "observed_authority_map_digests":
                observed_authority_map_digests,
            "observed_authority_map_observation_digests":
                observed_authority_map_observation_digests,
            "expected_owner_task_plan_digests": protocol.get(
                "owner_task_plan_digests"),
            "observed_owner_task_plan_digests":
                observed_owner_task_plan_digests,
            "expected_history_record_ids": protocol.get("history_record_ids"),
            "observed_history_record_ids": preview.get("history_record_ids"),
            "expected_history_record_digests": protocol.get(
                "history_record_digests"),
            "observed_history_record_digests": preview.get(
                "history_record_digests"),
            "expected_invocation_prompt_digests": protocol.get(
                "invocation_prompt_digests"),
            "observed_invocation_prompt_digests": preview.get(
                "invocation_prompt_digests"),
            "raw_prompts_or_outputs_included": False,
            "model_invoked": False,
            "learning_established": False,
            "authority": False,
        }
        raise RootlessExperimentalError(
            "historical_examples_pair_live_preview_mismatch")
    try:
        slot_binding = validate_historical_examples_pair_execution_slot(
            plan=plan, trial_index=trial_index, protocol=protocol,
            objective_task=objective_task, runner_cycle_id=RUN_ID,
            backend_seed=context["backend_seed"])
    except HistoricalExamplesInterventionError as exc:
        raise RootlessExperimentalError(
            "historical_examples_pair_live_slot_validation_failed") from exc

    history_store = owner.writeback.store
    records = tuple(sorted(history_store.records(), key=lambda item: item.record_id))
    receipts = tuple(sorted(history_store.receipts(), key=lambda item: item.receipt_id))
    records_by_id = {record.record_id: record.record_digest for record in records}
    receipt_record_ids = {receipt.record_id for receipt in receipts
        if records_by_id.get(receipt.record_id) == receipt.record_digest}
    selected_ids = protocol["history_record_ids"]
    selected_digests = protocol["history_record_digests"]
    source_boundary = {
        "records": [{"record_id": item.record_id,
            "record_digest": item.record_digest} for item in records],
        "receipts": [{"receipt_id": item.receipt_id,
            "receipt_digest": item.receipt_digest,
            "record_id": item.record_id,
            "record_digest": item.record_digest} for item in receipts],
    }
    if (len(records_by_id) != len(records)
            or len(receipt_record_ids) != len(receipts)
            or len(records) != history_seed_evidence.get("record_count")
            or len(receipts) != history_seed_evidence.get("receipt_count")
            or digest_payload(source_boundary) !=
                history_seed_evidence.get("source_boundary_digest")
            or any(records_by_id.get(record_id) != record_digest
                for record_id, record_digest in zip(
                    selected_ids, selected_digests, strict=True))
            or not set(selected_ids).issubset(receipt_record_ids)):
        raise RootlessExperimentalError(
            "historical_examples_pair_seed_inventory_mismatch")
    seed_semantic = {"history_seed_evidence": dict(history_seed_evidence),
        "source_boundary_digest": digest_payload(source_boundary),
        "selected_history_records": [{"record_id": record_id,
            "record_digest": record_digest}
            for record_id, record_digest in zip(
                selected_ids, selected_digests, strict=True)],
        "selected_history_receipts_present": True}
    source_history_seed_evidence_digest = "sha256:" + digest_payload(seed_semantic)

    _set_run_stage("historical_examples_pair_execution")
    execute_arm = build_resident_historical_examples_arm_executor(
        owner=owner, snapshot=snapshot, objective_task=objective_task)
    if RUN_PREREGISTRATION_DIGEST is None:
        raise RootlessExperimentalError("historical_examples_run_preregistration_missing")
    answer_key = derive_historical_examples_objective_answer_key(
        protocol=protocol, objective_task=objective_task)
    pair_result = execute_historical_examples_pair_once(
        protocol=protocol, answer_key=answer_key, execute_arm=execute_arm,
        journal=journal,
        fresh_run_binding=(RUN_ID, RUN_PREREGISTRATION_DIGEST))
    score = journal.load_score(protocol_digest=protocol["protocol_digest"])
    runtime_history_inventories = {}
    for arm in protocol["conditions"]:
        state = journal.arm_state(protocol_digest=protocol["protocol_digest"],
            arm=arm)
        inventory = state.get("runtime_history_inventory")
        if state.get("status") != "completed" or not isinstance(inventory, Mapping):
            raise RootlessExperimentalError(
                "historical_examples_pair_terminal_inventory_missing")
        runtime_history_inventories[arm] = dict(inventory)

    if (len(invocation_resource_evidence) != len(protocol["conditions"])
            or any(record.get("gate_status") != "passed"
                or not isinstance(record.get("invocation_started_at"), str)
                or not isinstance(record.get("invocation_finished_at"), str)
                for record in invocation_resource_evidence)):
        raise RootlessExperimentalError(
            "historical_examples_pair_resource_guard_evidence_incomplete")
    resource_evidence = {"preload_gate": dict(resource_preflight_evidence),
        **({"identity_neutral_history_binding": dict(context[
            "identity_neutral_history_binding"])}
            if context.get("identity_neutral_history_binding") is not None else {}),
        **({"identity_neutral_preload_binding_receipt_digest": context[
            "identity_neutral_preload_binding_digest"],
            "identity_neutral_preload_binding_receipt_path": context[
                "identity_neutral_preload_binding_path"]}
            if context.get("identity_neutral_preload_binding_digest") is not None
            else {}),
        "invocation_gates": [dict(item) for item in invocation_resource_evidence]}
    resource_guard_evidence_digest = "sha256:" + digest_payload(resource_evidence)
    runner_binding = make_historical_examples_pair_runner_binding(
        plan=plan, trial_index=trial_index,
        model_identity_digest=model_identity_digest,
        runtime_bundle_digest=(runtime_bundle_digest
            if runtime_bundle_digest.startswith("sha256:")
            else "sha256:" + runtime_bundle_digest),
        source_boundary_digest=plan["source_boundary_digest"],
        preregistration_digest=plan["execution_plan_digest"],
        source_history_seed_evidence_digest=source_history_seed_evidence_digest,
        resource_guard_evidence_digest=resource_guard_evidence_digest,
        source_history_seed_verified=True, resource_gate_passed=True)
    terminal = make_historical_examples_pair_execution_terminal(
        plan=plan, runner_binding=runner_binding, protocol=protocol,
        score=score, runtime_history_inventories=runtime_history_inventories)
    source_provenance_at_end = _source_provenance()
    if source_provenance_at_end != dict(source_provenance_at_start):
        raise RootlessExperimentalError(
            "source_provenance_changed_during_historical_pair")
    RUN_SOURCE_PROVENANCE_AT_END = dict(source_provenance_at_end)
    _set_run_stage("governed_model_release")
    session.close()
    residency_verification = _verify_model_released(MODEL_NAME)
    _set_run_stage("complete_result_persistence")
    _write_private_json_exclusive(RUN_ROOT / "historical_pair_slot_binding.json",
        slot_binding)
    _write_private_json_exclusive(RUN_ROOT / "historical_pair_runner_binding.json",
        runner_binding)
    _write_private_json_exclusive(RUN_ROOT / "historical_pair_resource_evidence.json",
        {**resource_evidence,
            "resource_guard_evidence_digest": resource_guard_evidence_digest})
    terminal_path = RUN_ROOT / "historical_examples_pair_execution_terminal.json"
    _write_private_json_exclusive(terminal_path, terminal)
    result = {"schema_version": "sentientos.historical_examples_pair_slot_result:v1",
        "status": "completed", "run_id": RUN_ID,
        "trial_index": trial_index,
        "execution_plan_digest": plan["execution_plan_digest"],
        "protocol_digest": protocol["protocol_digest"],
        "score_digest": pair_result["score_digest"],
        "runner_binding_digest": runner_binding["runner_binding_digest"],
        "terminal_digest": terminal["terminal_digest"],
        "terminal_path": str(terminal_path),
        **({"identity_neutral_preload_binding_digest": context[
            "identity_neutral_preload_binding_digest"]}
            if context.get("identity_neutral_preload_binding_digest") is not None
            else {}),
        **({"identity_neutral_preload_binding_path": context[
            "identity_neutral_preload_binding_path"]}
            if context.get("identity_neutral_preload_binding_path") is not None
            else {}),
        "governed_unload": "governed_release_completed",
        "residency_verification": residency_verification,
        "inference_performed": True, "learning_established": False,
        "authority": False}
    _write_private_json_exclusive(RUN_ROOT / "historical_pair_slot_result.json",
        result)
    return result


def _execute_negative_guidance_pair_slot(*, context: Mapping[str, Any],
        owner: ResidentDevelopmentalCognitionOwner, session: Any,
        history_seed_evidence: Mapping[str, Any], runtime_bundle_digest: str,
        resource_preflight_evidence: Mapping[str, Any],
        invocation_resource_evidence: list[dict[str, Any]],
        source_provenance_at_start: Mapping[str, Any]) -> dict[str, Any]:
    global RUN_SOURCE_PROVENANCE_AT_END
    protocol = context["protocol"]
    objective_task = context["objective_task"]
    if (history_seed_evidence.get("status") != "copied_and_reloaded_verified"
            or history_seed_evidence.get("copied_into_run_store") is not True):
        raise RootlessExperimentalError(
            "negative_guidance_history_seed_not_verified")
    identity_digest = "sha256:" + digest_payload(
        dict(session.active_model_identity))
    if identity_digest != protocol["target_model_identity_digest"]:
        raise RootlessExperimentalError(
            "negative_guidance_model_identity_mismatch")
    try:
        validate_negative_guidance_protocol(protocol,
            target_model_identity_digest=identity_digest,
            task_digest=objective_task.public_descriptor()["task_digest"])
    except NegativeGuidanceInterventionError as exc:
        raise RootlessExperimentalError(
            "negative_guidance_protocol_live_binding_invalid") from exc
    snapshot = WorldStateBoardBuilder(clock=lambda: datetime(
        2026, 11, 23, tzinfo=timezone.utc)).build((),
            manifest_id="resident-historical-examples-cpu-preflight")
    first_tick = protocol["owner_execution_tick_ids"][protocol["conditions"][0]]
    suffix = ":negative_guidance-preview:" + protocol["conditions"][0]
    if not first_tick.endswith(suffix):
        raise RootlessExperimentalError(
            "negative_guidance_execution_tick_invalid")
    live_preview = owner.preview_objective_historical_examples_pair(
        snapshot=snapshot, tick_id=first_tick[:-len(suffix)],
        objective_task=objective_task, ablation_target="negative_guidance")
    try:
        runtime_protocol = bind_negative_guidance_runtime_preview(
            protocol=protocol, runtime_preview=live_preview)
    except NegativeGuidanceInterventionError as exc:
        raise RootlessExperimentalError(
            "negative_guidance_live_owner_preview_mismatch") from exc
    _set_run_stage("negative_guidance_pair_execution")
    execute_arm = build_resident_negative_guidance_arm_executor(
        owner=owner, snapshot=snapshot, objective_task=objective_task)
    pair_result = execute_negative_guidance_pair_once(protocol=runtime_protocol,
        execute_arm=execute_arm, journal=context["journal"])
    if (len(invocation_resource_evidence) != len(protocol["conditions"])
            or any(record.get("gate_status") != "passed"
                or not isinstance(record.get("invocation_started_at"), str)
                or not isinstance(record.get("invocation_finished_at"), str)
                for record in invocation_resource_evidence)):
        raise RootlessExperimentalError(
            "negative_guidance_resource_guard_evidence_incomplete")
    resource_evidence = {"preload_gate": dict(resource_preflight_evidence),
        "invocation_gates": [dict(item) for item in invocation_resource_evidence]}
    resource_digest = "sha256:" + digest_payload(resource_evidence)
    history_seed_digest = "sha256:" + digest_payload(dict(history_seed_evidence))
    score = context["journal"].load_score(
        protocol_digest=runtime_protocol["protocol_digest"])
    terminal = context["journal"].load_terminal(
        protocol_digest=runtime_protocol["protocol_digest"])
    runner_binding_semantic = {
        "schema_version": "sentientos.negative_guidance_runner_binding:v1",
        "run_id": RUN_ID,
        "preflight_protocol_digest": protocol["protocol_digest"],
        "runtime_protocol_digest": runtime_protocol["protocol_digest"],
        "target_model_identity_digest": identity_digest,
        "runtime_bundle_digest": (runtime_bundle_digest
            if runtime_bundle_digest.startswith("sha256:")
            else "sha256:" + runtime_bundle_digest),
        "source_receipt_id": context["report"]["source_receipt_id"],
        "source_receipt_digest": context["report"]["source_receipt_digest"],
        "history_seed_evidence_digest": history_seed_digest,
        "resource_guard_evidence_digest": resource_digest,
        "history_seed_verified": True, "resource_gate_passed": True,
        "authority": False}
    runner_binding = {**runner_binding_semantic,
        "runner_binding_digest": "sha256:" +
            digest_payload(runner_binding_semantic)}
    source_provenance_at_end = _source_provenance()
    if source_provenance_at_end != dict(source_provenance_at_start):
        raise RootlessExperimentalError(
            "source_provenance_changed_during_negative_guidance_pair")
    RUN_SOURCE_PROVENANCE_AT_END = dict(source_provenance_at_end)
    _set_run_stage("governed_model_release")
    session.close()
    residency_verification = _verify_model_released(MODEL_NAME)
    _set_run_stage("complete_result_persistence")
    _write_private_json_exclusive(RUN_ROOT /
        "negative_guidance_runner_binding.json", runner_binding)
    _write_private_json_exclusive(RUN_ROOT /
        "negative_guidance_resource_evidence.json", {**resource_evidence,
            "resource_guard_evidence_digest": resource_digest})
    _write_private_json_exclusive(RUN_ROOT /
        "negative_guidance_history_seed_evidence.json",
        dict(history_seed_evidence))
    result = {"schema_version":
            "sentientos.negative_guidance_pair_slot_result:v1",
        "status": "completed", "run_id": RUN_ID,
        "preflight_protocol_digest": protocol["protocol_digest"],
        "runtime_protocol_digest": runtime_protocol["protocol_digest"],
        "score_digest": pair_result.score["score_digest"],
        "terminal_digest": "sha256:" + digest_payload(terminal),
        "runner_binding_digest": runner_binding["runner_binding_digest"],
        "governed_unload": "governed_release_completed",
        "residency_verification": residency_verification,
        "inference_performed": True, "learning_established": False,
        "improvement_established": False, "authority": False}
    _write_private_json_exclusive(RUN_ROOT /
        "negative_guidance_pair_slot_result.json", result)
    return result


def _execute_strategy_inclusion_pair_slot(*, context: Mapping[str, Any],
        owner: ResidentDevelopmentalCognitionOwner, session: Any,
        history_seed_evidence: Mapping[str, Any], runtime_bundle_digest: str,
        resource_preflight_evidence: Mapping[str, Any],
        invocation_resource_evidence: list[dict[str, Any]],
        source_provenance_at_start: Mapping[str, Any]) -> dict[str, Any]:
    global RUN_SOURCE_PROVENANCE_AT_END
    protocol = context["protocol"]
    objective_task = context["objective_task"]
    if (history_seed_evidence.get("status") != "copied_and_reloaded_verified"
            or history_seed_evidence.get("copied_into_run_store") is not True):
        raise RootlessExperimentalError(
            "strategy_inclusion_history_seed_not_verified")
    identity_digest = "sha256:" + digest_payload(
        dict(session.active_model_identity))
    if identity_digest != protocol.get("target_model_identity_digest"):
        raise RootlessExperimentalError(
            "strategy_inclusion_model_identity_mismatch")
    try:
        validate_strategy_inclusion_protocol(protocol=protocol,
            target_model_identity_digest=identity_digest,
            task_digest=objective_task.public_descriptor()["task_digest"])
    except StrategyInclusionInterventionError as exc:
        raise RootlessExperimentalError(
            "strategy_inclusion_protocol_live_binding_invalid") from exc
    tick_ids = protocol.get("owner_execution_tick_ids")
    suffix = ":strategy-preview:included"
    included_tick = (tick_ids.get("strategy_included")
        if isinstance(tick_ids, Mapping) else None)
    omitted_tick = (tick_ids.get("strategy_omitted")
        if isinstance(tick_ids, Mapping) else None)
    if (not isinstance(included_tick, str)
            or not included_tick.endswith(suffix)
            or not isinstance(omitted_tick, str)
            or omitted_tick != included_tick.removesuffix(
                "included") + "omitted"):
        raise RootlessExperimentalError(
            "strategy_inclusion_execution_tick_binding_invalid")
    base_tick = included_tick[:-len(suffix)]
    snapshot = WorldStateBoardBuilder(clock=lambda: datetime(
        2026, 11, 23, tzinfo=timezone.utc)).build((),
            manifest_id="resident-strategy-cpu-preflight")
    live_preview = owner.preview_objective_strategy_inclusion_pair(
        snapshot=snapshot, tick_id=base_tick, objective_task=objective_task,
        include_request_semantics=True)
    try:
        reconstructed = prepare_strategy_inclusion_pair(
            target_model_identity_digest=identity_digest,
            task_digest=objective_task.public_descriptor()["task_digest"],
            generation_config_digest=protocol["generation_config_digest"],
            owner_prompt_pair_preview=live_preview,
            private_task_plan_digest=protocol["private_task_plan_digest"],
            answer_key_digest=protocol["answer_key_digest"],
            arm_order=protocol["conditions"])["protocol"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RootlessExperimentalError(
            "strategy_inclusion_live_preview_reconstruction_failed") from exc
    runtime_only_fields = {"protocol_digest",
        "owner_prompt_pair_preview_digest", "preview_request_digests"}
    frozen_invariants = {key: value for key, value in protocol.items()
        if key not in runtime_only_fields}
    runtime_invariants = {key: value for key, value in reconstructed.items()
        if key not in runtime_only_fields}
    if runtime_invariants != frozen_invariants:
        raise RootlessExperimentalError(
            "strategy_inclusion_live_owner_preview_mismatch")

    request_ids_by_arm: dict[str, str] = {}
    request_digests_by_arm: dict[str, str] = {}
    for arm in ("strategy_included", "strategy_omitted"):
        request_id = "strategy-" + protocol["protocol_digest"][7:19] + ":" + arm
        request_ids_by_arm[arm] = request_id
        request_digests_by_arm[arm] = objective_request_payload(
            request_id=request_id, task=objective_task)["request_digest"]
    request_semantics_by_arm = live_preview.get(
        "request_semantics_by_arm")
    if (not isinstance(request_semantics_by_arm, Mapping)
            or set(request_semantics_by_arm) != {
                "strategy_included", "strategy_omitted"}
            or any(not isinstance(value, Mapping)
                for value in request_semantics_by_arm.values())):
        raise RootlessExperimentalError(
            "strategy_inclusion_live_request_semantics_unavailable")
    execute_arm = build_resident_strategy_inclusion_arm_executor(
        owner=owner, snapshot=snapshot, objective_task=objective_task,
        request_ids_by_arm=request_ids_by_arm,
        request_digests_by_arm=request_digests_by_arm,
        request_semantics_by_arm=request_semantics_by_arm)

    def historical_receipt_candidates(frozen_protocol: Mapping[str, Any], *,
            arm: str | None, expected_receipt_id: str | None = None,
            expected_receipt_digest: str | None = None
            ) -> list[Mapping[str, Any]]:
        request_bindings = frozen_protocol.get("preview_request_digests")
        if not isinstance(request_bindings, Mapping):
            raise RootlessExperimentalError(
                "strategy_inclusion_recovery_request_bindings_invalid")
        selected_arms = ((arm,) if arm is not None else
            tuple(frozen_protocol.get("conditions", ())))
        expected: dict[str, str] = {}
        for candidate_arm in selected_arms:
            request_digest = request_bindings.get(candidate_arm)
            if (not isinstance(candidate_arm, str)
                    or not isinstance(request_digest, str)
                    or not re.fullmatch(r"sha256:[0-9a-f]{64}", request_digest)):
                raise RootlessExperimentalError(
                    "strategy_inclusion_recovery_request_binding_invalid")
            expected[candidate_arm] = request_digest.removeprefix("sha256:")
        cycle_parent = (workspace / "sentientos-data" /
            "rootless-experimental" / "developmental-cognition-cycles")
        _no_symlink_path(cycle_parent)
        try:
            roots = [path for path in cycle_parent.iterdir()
                if re.fullmatch(r"rootless-cognition-cycle-[0-9a-f]{20}",
                    path.name, flags=re.ASCII)
                and not path.is_symlink() and path.is_dir()]
            roots.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
        except OSError as exc:
            raise RootlessExperimentalError(
                "strategy_inclusion_receipt_recovery_inventory_unavailable") from exc
        if len(roots) > 512:
            raise RootlessExperimentalError(
                "strategy_inclusion_receipt_recovery_cycle_limit_exceeded")
        matches: list[Mapping[str, Any]] = []
        examined = 0
        for cycle_root in roots:
            receipt_root = cycle_root / "inference-custody" / "receipts"
            if not receipt_root.exists():
                continue
            _no_symlink_path(receipt_root)
            try:
                names: list[str] = []
                for path in receipt_root.iterdir():
                    if (path.is_file() and not path.is_symlink()
                            and re.fullmatch(r"lmrec-[0-9a-f]{24}\.json",
                                path.name, flags=re.ASCII)):
                        names.append(path.name)
                        if len(names) > 16_384:
                            raise RootlessExperimentalError(
                                "strategy_inclusion_receipt_recovery_receipt_limit_exceeded")
                names.sort()
            except RootlessExperimentalError:
                raise
            except OSError as exc:
                raise RootlessExperimentalError(
                    "strategy_inclusion_receipt_recovery_inventory_unavailable") from exc
            for name in names:
                if (expected_receipt_id is not None
                        and name != expected_receipt_id + ".json"):
                    continue
                examined += 1
                if examined > _MAX_STRATEGY_RECEIPT_RECOVERY_SCAN_FILES:
                    raise RootlessExperimentalError(
                        "strategy_inclusion_receipt_recovery_receipt_limit_exceeded")
                path = receipt_root / name
                _no_symlink_path(path)
                receipt = _read_historical_pair_json(path,
                    code="strategy_inclusion_recovery_receipt")
                request = receipt.get("request")
                if not isinstance(request, Mapping):
                    continue
                actual_digest = request.get("request_digest")
                actual_request_id = request.get("request_id")
                if (not isinstance(actual_digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", actual_digest) is None
                        or actual_request_id != "lmreq-" + actual_digest[:24]):
                    continue
                request_semantic = {key: value for key, value in request.items()
                    if key not in {"request_id", "request_digest",
                        "raw_prompt_stored", "ephemeral_prompt_handling"}}
                try:
                    canonical_digest = (
                        canonical_strategy_invocation_request_digest(
                            request_semantic,
                            binding_posture=frozen_protocol.get(
                                "request_digest_binding_posture")))
                except StrategyInclusionInterventionError:
                    continue
                for candidate_arm, expected_digest in expected.items():
                    if canonical_digest != expected_digest:
                        continue
                    receipt_id = receipt.get("receipt_id")
                    receipt_digest = receipt.get("receipt_digest")
                    if (expected_receipt_id is not None
                            and receipt_id != expected_receipt_id
                            or expected_receipt_digest is not None
                            and receipt_digest != expected_receipt_digest):
                        continue
                    try:
                        verified = verify_rootless_historical_invocation_receipt(
                            cycle_root=cycle_root, receipt_id=receipt_id,
                            receipt_digest=receipt_digest,
                            expected_request_id=actual_request_id,
                            expected_request_digest=actual_digest,
                            expected_active_model_identity=
                                context["source_model_identity"])
                        from work.strategy_inclusion_intervention import (
                            verify_strategy_inclusion_arm_receipt,
                        )
                        verify_strategy_inclusion_arm_receipt(
                            protocol=frozen_protocol, arm=candidate_arm,
                            receipt=verified)
                    except (OSError, TypeError, ValueError, RuntimeError):
                        continue
                    matches.append(dict(verified))
        return matches

    def load_receipt(receipt_id: str, receipt_digest: str
            ) -> Mapping[str, Any]:
        matches = historical_receipt_candidates(protocol, arm=None,
            expected_receipt_id=receipt_id,
            expected_receipt_digest=receipt_digest)
        if len(matches) != 1:
            raise RootlessExperimentalError(
                "strategy_inclusion_receipt_recovery_ambiguous")
        return matches[0]

    def recover_claimed_arm(arm: str,
            frozen_protocol: Mapping[str, Any]
            ) -> Sequence[Mapping[str, Any]]:
        return historical_receipt_candidates(frozen_protocol, arm=arm)

    _set_run_stage("strategy_inclusion_pair_execution")
    try:
        pair_result = execute_and_persist_strategy_inclusion_pair(
            store=context["store"], protocol=protocol,
            answer_key=context["answer_key"], execute_arm=execute_arm,
            load_receipt=load_receipt,
            recover_claimed_arm=recover_claimed_arm)
    except StrategyInclusionInterventionError as exc:
        raise RootlessExperimentalError(
            "strategy_inclusion_pair_execution_failed") from exc
    if (len(invocation_resource_evidence) > len(protocol["conditions"])
            or any(record.get("gate_status") != "passed"
                or not isinstance(record.get("invocation_started_at"), str)
                or not isinstance(record.get("invocation_finished_at"), str)
                for record in invocation_resource_evidence)):
        raise RootlessExperimentalError(
            "strategy_inclusion_resource_guard_evidence_incomplete")
    resource_evidence = {"preload_gate": dict(resource_preflight_evidence),
        "invocation_gates": [dict(item)
            for item in invocation_resource_evidence]}
    resource_digest = "sha256:" + digest_payload(resource_evidence)
    history_seed_digest = "sha256:" + digest_payload(dict(history_seed_evidence))
    source_provenance_at_end = _source_provenance()
    if source_provenance_at_end != dict(source_provenance_at_start):
        raise RootlessExperimentalError(
            "source_provenance_changed_during_strategy_inclusion_pair")
    RUN_SOURCE_PROVENANCE_AT_END = dict(source_provenance_at_end)
    _set_run_stage("governed_model_release")
    session.close()
    residency_verification = _verify_model_released(MODEL_NAME)
    _set_run_stage("complete_result_persistence")
    runner_binding_semantic = {
        "schema_version": "sentientos.strategy_inclusion_runner_binding:v1",
        "run_id": RUN_ID,
        "preflight_protocol_digest": protocol["protocol_digest"],
        "runtime_protocol_digest": pair_result["protocol_digest"],
        "target_model_identity_digest": identity_digest,
        "runtime_bundle_digest": (runtime_bundle_digest
            if runtime_bundle_digest.startswith("sha256:")
            else "sha256:" + runtime_bundle_digest),
        "source_receipt_id": context["report"]["source_receipt_id"],
        "source_receipt_digest": context["report"]["source_receipt_digest"],
        "history_seed_evidence_digest": history_seed_digest,
        "resource_guard_evidence_digest": resource_digest,
        "history_seed_verified": True, "resource_gate_passed": True,
        "authority": False}
    runner_binding = {**runner_binding_semantic,
        "runner_binding_digest": "sha256:" +
            digest_payload(runner_binding_semantic)}
    _write_private_json_exclusive(RUN_ROOT /
        "strategy_inclusion_runner_binding.json", runner_binding)
    _write_private_json_exclusive(RUN_ROOT /
        "strategy_inclusion_resource_evidence.json", {**resource_evidence,
            "resource_guard_evidence_digest": resource_digest})
    result = {"schema_version":
            "sentientos.strategy_inclusion_pair_slot_result:v1",
        "status": "completed", "run_id": RUN_ID,
        "protocol_digest": pair_result["protocol_digest"],
        "score_digest": pair_result["score_digest"],
        "runner_binding_digest": runner_binding["runner_binding_digest"],
        "governed_unload": "governed_release_completed",
        "residency_verification": residency_verification,
        "inference_performed": True, "learning_established": False,
        "improvement_established": False, "authority": False}
    _write_private_json_exclusive(RUN_ROOT /
        "strategy_inclusion_pair_slot_result.json", result)
    return result


EXPERIMENT_SEED = _experiment_seed_from_environment()
PREREGISTRATION_DIGEST = _preregistration_digest_from_environment()
HISTORY_INTERVENTION_TRIAL_INDEX = (
    _history_intervention_trial_index_from_environment())


def _optional_preregistration_digest(value: Any) -> str | None:
    if (isinstance(value, str) and value != "0" * 64
            and re.fullmatch(r"[0-9a-f]{64}", value)):
        return value
    return None


def _request_preregistration_digest(request: Any) -> str | None:
    if not isinstance(request, Mapping):
        return None
    linkage = request.get("linkage")
    session = (linkage.get("rootless_experimental_session")
        if isinstance(linkage, Mapping) else None)
    if not isinstance(session, Mapping):
        return None
    return _optional_preregistration_digest(
        session.get("preregistration_digest"))


def _experiment_seed_provenance() -> dict[str, int]:
    """Keep task randomization distinct from the fixed inference seed."""
    return {
        "task_generation_seed": EXPERIMENT_SEED,
        "requested_backend_seed": ROOTLESS_EXPERIMENTAL_OLLAMA_BACKEND_SEED,
    }


def _objective_condition_score(condition: Mapping[str, Any]) -> Any:
    return condition.get("score")


def _objective_probe_transition_summary(
        evaluations: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare oracle correctness by probe while keeping answer values out."""
    expected_conditions = ("history_present", "history_withheld", "history_restored")
    if (len(evaluations) != len(expected_conditions)
            or tuple(item.get("condition_id") for item in evaluations)
                != expected_conditions):
        raise RootlessExperimentalError("objective_probe_conditions_incomplete")
    ordered_inputs: tuple[int, ...] | None = None
    correctness_by_condition: dict[str, list[bool | None] | None] = {}
    abstention_by_condition: dict[str, list[bool | None] | None] = {}
    unavailable_conditions: list[str] = []
    expected_probe_count: int | None = None
    task_digest: str | None = None
    score_digests: dict[str, str] = {}
    for item in evaluations:
        condition_id = str(item["condition_id"])
        score = item.get("score")
        probe_results = score.get("probe_results") if isinstance(score, Mapping) else None
        correct_count = score.get("correct_count") if isinstance(score, Mapping) else None
        probe_count = score.get("probe_count") if isinstance(score, Mapping) else None
        status = score.get("status") if isinstance(score, Mapping) else None
        score_schema = score.get("schema_version") if isinstance(score, Mapping) else None
        current_task_digest = score.get("task_digest") if isinstance(score, Mapping) else None
        score_digest = score.get("score_digest") if isinstance(score, Mapping) else None
        if (not isinstance(score, Mapping) or type(probe_count) is not int
                or probe_count < 1
                or not isinstance(current_task_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", current_task_digest) is None
                or not isinstance(score_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", score_digest) is None
                or (task_digest is not None and current_task_digest != task_digest)
                or (expected_probe_count is not None
                    and expected_probe_count != probe_count)):
            raise RootlessExperimentalError("objective_probe_scores_incomplete")
        score_semantic = {key: value for key, value in score.items()
            if key != "score_digest"}
        if score_digest != "sha256:" + digest_payload(score_semantic):
            raise RootlessExperimentalError("objective_probe_score_digest_mismatch")
        if score_schema is not None and score_schema not in {
                "sentientos.objective_task_score:v3",
                "sentientos.objective_task_score:v4",
                "sentientos.objective_task_score:v5",
                "sentientos.objective_task_score:v6"}:
            raise RootlessExperimentalError("objective_probe_score_schema_invalid")
        task_digest = current_task_digest
        score_digests[condition_id] = score_digest
        expected_probe_count = probe_count
        if status in {"invalid_answer", "output_truncated", "output_unavailable"}:
            invalid_answer = status == "invalid_answer"
            correct_count_matches_status = (
                type(correct_count) is int and correct_count == 0
                if invalid_answer else correct_count is None)
            if (probe_results != [] or not correct_count_matches_status
                    or (score_schema in {
                        "sentientos.objective_task_score:v4",
                        "sentientos.objective_task_score:v5",
                        "sentientos.objective_task_score:v6"}
                        and (score.get("answered_count") is not None
                            or score.get("abstained_count") is not None))):
                raise RootlessExperimentalError("objective_probe_score_row_invalid")
            correctness_by_condition[condition_id] = None
            abstention_by_condition[condition_id] = None
            unavailable_conditions.append(condition_id)
            continue
        if (status not in {"correct", "incorrect", "selective"}
                or not isinstance(probe_results, list)
                or probe_count != len(probe_results)
                or type(correct_count) is not int):
            raise RootlessExperimentalError("objective_probe_scores_incomplete")
        inputs: list[int] = []
        correctness: list[bool | None] = []
        abstentions: list[bool] = []
        for result in probe_results:
            # Older and non-selective score rows omit `abstained` for an
            # answered probe; omission is the canonical false value.
            abstained = result.get("abstained", False) if isinstance(result, Mapping) else None
            base_result_fields = {"probe_input", "observed_answer", "correct"}
            selective_schema = score_schema in {
                "sentientos.objective_task_score:v4",
                "sentientos.objective_task_score:v5",
                "sentientos.objective_task_score:v6"}
            calibrated_schema = score_schema == "sentientos.objective_task_score:v6"
            confidence_fields = {"confidence_basis_points"} if calibrated_schema else set()
            confidence = (result.get("confidence_basis_points")
                if isinstance(result, Mapping) else None)
            confidence_valid = (not calibrated_schema or
                (isinstance(result, Mapping)
                    and "confidence_basis_points" in result
                    and (confidence is None or type(confidence) is int
                        and 0 <= confidence <= 10_000)))
            answered_row = (isinstance(result, Mapping)
                and set(result) == base_result_fields | confidence_fields
                and type(result.get("observed_answer")) is int
                and type(result.get("correct")) is bool)
            abstained_row = (selective_schema
                and isinstance(result, Mapping)
                and set(result) == base_result_fields | confidence_fields | {"abstained"}
                and result.get("observed_answer") is None
                and result.get("correct") is None
                and result.get("abstained") is True)
            if (not isinstance(result, Mapping)
                    or not (answered_row or abstained_row)
                    or type(result.get("probe_input")) is not int
                    or not confidence_valid
                    or type(abstained) is not bool
                    or abstained != abstained_row):
                raise RootlessExperimentalError("objective_probe_score_row_invalid")
            inputs.append(result["probe_input"])
            correctness.append(result["correct"])
            abstentions.append(abstained)
        current_inputs = tuple(inputs)
        if (len(set(current_inputs)) != len(current_inputs)
                or sum(value is True for value in correctness) != correct_count
                or (ordered_inputs is not None and ordered_inputs != current_inputs)):
            raise RootlessExperimentalError("objective_probe_score_alignment_invalid")
        if score_schema == "sentientos.objective_task_score:v3":
            if (any(abstentions)
                    or status != ("correct" if correct_count == probe_count else "incorrect")):
                raise RootlessExperimentalError(
                    "objective_probe_score_status_mismatch")
        elif score_schema in {
                "sentientos.objective_task_score:v4",
                "sentientos.objective_task_score:v5",
                "sentientos.objective_task_score:v6"}:
            answered_count = score.get("answered_count")
            abstained_count = score.get("abstained_count")
            observed_abstained_count = sum(abstentions)
            if (type(answered_count) is not int
                    or type(abstained_count) is not int
                    or answered_count != probe_count - observed_abstained_count
                    or abstained_count != observed_abstained_count):
                raise RootlessExperimentalError(
                    "objective_probe_score_selective_counts_invalid")
            all_probes_correct = correct_count == probe_count
            if score_schema in {"sentientos.objective_task_score:v5",
                    "sentientos.objective_task_score:v6"}:
                status_matches_rows = (
                    status == "selective" if observed_abstained_count else
                    status == ("correct" if all_probes_correct else "incorrect"))
            else:
                status_matches_rows = status == (
                    "correct" if all_probes_correct and not observed_abstained_count
                    else "incorrect")
            if not status_matches_rows:
                raise RootlessExperimentalError(
                    "objective_probe_score_status_mismatch")
        ordered_inputs = current_inputs
        correctness_by_condition[condition_id] = correctness
        abstention_by_condition[condition_id] = abstentions
    if ordered_inputs is None:
        return {
            "condition_order": list(expected_conditions),
            "task_digest": task_digest,
            "condition_score_digests": score_digests,
            "probe_outcomes": [],
            "unscoreable_condition_ids": unavailable_conditions,
            "posture": "per_probe_outcomes_unavailable_no_scoreable_condition",
        }
    if expected_probe_count != len(ordered_inputs):
        raise RootlessExperimentalError("objective_probe_score_alignment_invalid")
    probe_outcomes: list[dict[str, Any]] = []
    for index, probe_input in enumerate(ordered_inputs):
        present, withheld, restored = (
            (correctness_by_condition[condition_id][index]
                if correctness_by_condition[condition_id] is not None else None)
            for condition_id in expected_conditions)
        if type(present) is not bool or type(withheld) is not bool:
            history_transition = "unscoreable"
        elif present == withheld:
            history_transition = "no_correctness_change"
        elif present:
            history_transition = "history_associated_correctness_gain"
        else:
            history_transition = "history_associated_correctness_cost"
        restoration = ("unscoreable" if type(present) is not bool
            or type(restored) is not bool else
            "matches_history_present" if restored == present
            else "differs_from_history_present")
        answerability_by_condition = {
            condition_id: (
                not abstention_by_condition[condition_id][index]
                if abstention_by_condition[condition_id] is not None else None)
            for condition_id in expected_conditions}
        present_answerable = answerability_by_condition["history_present"]
        withheld_answerable = answerability_by_condition["history_withheld"]
        restored_answerable = answerability_by_condition["history_restored"]
        answerability_transition = (
            "unscoreable" if type(present_answerable) is not bool
                or type(withheld_answerable) is not bool else
            "no_answerability_change"
                if present_answerable == withheld_answerable else
            "history_associated_answerability_gain" if present_answerable else
            "history_associated_answerability_cost")
        answerability_restoration = (
            "unscoreable" if type(present_answerable) is not bool
                or type(restored_answerable) is not bool else
            "matches_history_present"
                if restored_answerable == present_answerable else
            "differs_from_history_present")
        probe_outcomes.append({
            "probe_index": index,
            "probe_input": probe_input,
            "correctness_by_condition": {
                condition_id: (correctness_by_condition[condition_id][index]
                    if correctness_by_condition[condition_id] is not None else None)
                for condition_id in expected_conditions},
            "abstention_by_condition": {
                condition_id: (abstention_by_condition[condition_id][index]
                    if abstention_by_condition[condition_id] is not None else None)
                for condition_id in expected_conditions},
            "history_present_vs_withheld": history_transition,
            "restoration_vs_present": restoration,
            "answerability_by_condition": answerability_by_condition,
            "history_present_vs_withheld_answerability": answerability_transition,
            "restoration_answerability_vs_present": answerability_restoration,
        })
    return {
        "condition_order": list(expected_conditions),
        "task_digest": task_digest,
        "condition_score_digests": score_digests,
        "probe_outcomes": probe_outcomes,
        "unscoreable_condition_ids": unavailable_conditions,
        "posture": ("partial_per_probe_outcomes_unscoreable_conditions"
            if unavailable_conditions else
            "independent_oracle_correctness_only_answer_values_omitted"),
    }


_MIN_ACCURATE_EXAMPLES_FOR_AFFINE_TRANSFER = 2


def _objective_acquisition_summary(run: Mapping[str, Any]) -> dict[str, Any]:
    scores = run.get("objective_scores")
    expected_conditions = ("history_present", "history_withheld", "history_restored")
    if (not isinstance(scores, list) or len(scores) != len(expected_conditions)
            or any(not isinstance(item, Mapping) for item in scores)
            or tuple(item.get("condition_id") for item in scores) != expected_conditions):
        raise RootlessExperimentalError(
            "objective_family_acquisition_scores_incomplete")
    evaluation_values = [_objective_condition_score(item) for item in scores]
    if any(not isinstance(value, Mapping) for value in evaluation_values):
        raise RootlessExperimentalError(
            "objective_family_acquisition_score_invalid")
    evaluation_rows = [cast(Mapping[str, Any], value) for value in evaluation_values]
    condition_score_digests = [row.get("score_digest") for row in evaluation_rows]
    if any(not isinstance(value, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            for value in condition_score_digests):
        raise RootlessExperimentalError(
            "objective_family_acquisition_score_digest_invalid")
    present, withheld, restored = evaluation_rows
    # Rebuild probe-level comparisons from the three score artifacts every
    # time. A persisted summary is useful for display, but must not substitute
    # for validating score-row shape, probe alignment, and correct-count totals.
    recomputed_probe_outcomes = _objective_probe_transition_summary(scores)
    persisted_evaluation = run.get("objective_evaluation")
    persisted_probe_outcomes = (persisted_evaluation.get("probe_level_outcomes")
        if isinstance(persisted_evaluation, Mapping) else None)
    if (persisted_probe_outcomes is not None
            and (not isinstance(persisted_probe_outcomes, Mapping)
                or dict(persisted_probe_outcomes) != recomputed_probe_outcomes)):
        raise RootlessExperimentalError(
            "objective_family_acquisition_probe_outcomes_mismatch")
    probe_level_outcomes = recomputed_probe_outcomes
    probe_count: int | None = None
    condition_correct_counts: list[int | None] = []
    for evaluation in evaluation_rows:
        status = evaluation.get("status")
        count = evaluation.get("correct_count")
        current_probe_count = evaluation.get("probe_count")
        if (type(current_probe_count) is not int or current_probe_count < 1
                or (probe_count is not None and current_probe_count != probe_count)):
            raise RootlessExperimentalError(
                "objective_family_acquisition_score_invalid")
        probe_count = current_probe_count
        if status in {"correct", "incorrect", "selective"}:
            if type(count) is not int or not 0 <= count <= current_probe_count:
                raise RootlessExperimentalError(
                    "objective_family_acquisition_score_invalid")
            condition_correct_counts.append(count)
        elif status == "invalid_answer":
            if count != 0:
                raise RootlessExperimentalError(
                    "objective_family_acquisition_score_invalid")
            condition_correct_counts.append(0)
        elif status in {"output_truncated", "output_unavailable"}:
            if count is not None:
                raise RootlessExperimentalError(
                    "objective_family_acquisition_score_invalid")
            condition_correct_counts.append(None)
        else:
            raise RootlessExperimentalError(
                "objective_family_acquisition_score_invalid")
    if probe_count is None:
        raise RootlessExperimentalError("objective_family_acquisition_score_invalid")
    correct_count, withheld_correct_count, restored_correct_count = (
        condition_correct_counts)
    retained_examples = present.get("probe_results")
    retained_accurate_count = (sum(row.get("correct") is True for row in retained_examples
        if isinstance(row, Mapping)) if isinstance(retained_examples, list) else 0)
    retained_inaccurate_count = (sum(row.get("correct") is False for row in retained_examples
        if isinstance(row, Mapping)) if isinstance(retained_examples, list) else 0)
    retained_abstained_count = (sum(row.get("abstained") is True
        and row.get("observed_answer") is None
        and row.get("correct") is None for row in retained_examples
        if isinstance(row, Mapping)) if isinstance(retained_examples, list) else 0)
    baseline_qualified = (type(withheld_correct_count) is int
        and withheld_correct_count >= _MIN_ACCURATE_EXAMPLES_FOR_AFFINE_TRANSFER)
    if any(count is None for count in condition_correct_counts):
        baseline_classification = "one_or_more_condition_outcomes_unscoreable"
    elif not baseline_qualified:
        baseline_classification = "baseline_competence_not_demonstrated"
    elif restored_correct_count != correct_count:
        baseline_classification = "history_effect_not_restored"
    elif correct_count > withheld_correct_count:
        baseline_classification = "history_associated_acquisition_gain_restored"
    elif correct_count < withheld_correct_count:
        baseline_classification = "history_associated_acquisition_cost_restored"
    else:
        baseline_classification = "no_correct_count_difference"
    return {
        "condition_correct_counts": condition_correct_counts,
        "condition_score_digests": condition_score_digests,
        "history_present_score_digest": condition_score_digests[0],
        "probe_level_outcomes": probe_level_outcomes,
        "history_present_correct_count": correct_count,
        "history_withheld_baseline_correct_count": withheld_correct_count,
        "history_restored_correct_count": restored_correct_count,
        "probe_count": probe_count,
        "retained_accurate_example_count": retained_accurate_count,
        "retained_inaccurate_example_count": retained_inaccurate_count,
        "retained_abstained_example_count": retained_abstained_count,
        "acquisition_outcome_status": present.get("status"),
        "baseline_competence_qualified": baseline_qualified,
        "baseline_competence_threshold": _MIN_ACCURATE_EXAMPLES_FOR_AFFINE_TRANSFER,
        "history_present_minus_withheld_correct_count": (
            correct_count - withheld_correct_count
            if type(correct_count) is int and type(withheld_correct_count) is int else None),
        "restored_minus_present_correct_count": (
            restored_correct_count - correct_count
            if type(restored_correct_count) is int and type(correct_count) is int else None),
        "baseline_effect_classification": baseline_classification,
    }


def _objective_transfer_eligibility(acquisition_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Require baseline competence and enough verified examples for transfer."""
    accurate = acquisition_summary.get("retained_accurate_example_count")
    if type(accurate) is not int or accurate < 0:
        raise RootlessExperimentalError(
            "objective_family_acquisition_accuracy_count_invalid")
    required = _MIN_ACCURATE_EXAMPLES_FOR_AFFINE_TRANSFER
    baseline_qualified = acquisition_summary.get("baseline_competence_qualified")
    if type(baseline_qualified) is not bool:
        raise RootlessExperimentalError(
            "objective_family_acquisition_baseline_qualification_invalid")
    eligible = accurate >= required and baseline_qualified
    if not baseline_qualified:
        reason = ("history_withheld_baseline_outcome_unscoreable"
            if acquisition_summary.get("history_withheld_baseline_correct_count") is None
            else "history_withheld_baseline_competence_not_demonstrated")
    elif accurate < required:
        reason = "insufficient_accurate_acquisition_examples"
    else:
        reason = None
    return {
        "eligible": eligible,
        "status": "eligible" if eligible else f"skipped_{reason}",
        "reason": reason,
        "accurate_example_count": accurate,
        "required_accurate_example_count": required,
        "history_withheld_baseline_competence_qualified": baseline_qualified,
    }


def _cross_range_history_competence_eligibility(*, owner: Any,
        transfer_task: Any, source_task_family_id: str,
        target_model_identity: Mapping[str, Any]) -> dict[str, Any]:
    """Gate the separate history-enabled outcome on score-bound source anchors."""
    target_family_id = getattr(transfer_task, "task_family_id", None)
    declared_families = tuple(getattr(transfer_task,
        "history_task_family_ids", ()) or ())
    probe_inputs = (getattr(transfer_task, "probe_input", None),
        *tuple(getattr(transfer_task, "additional_probe_inputs", ())))
    if (target_family_id != ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY
            or source_task_family_id not in declared_families
            or target_family_id not in declared_families
            or len(set(declared_families)) != len(declared_families)
            or any(type(value) is not int for value in probe_inputs)
            or len(set(probe_inputs)) != len(probe_inputs)):
        return {"eligible": False, "status": "task_family_contract_mismatch",
            "source_task_family_id": source_task_family_id,
            "target_task_family_id": target_family_id,
            "source_record_ids": [], "authority": False}
    records = owner.writeback.store.records()
    source_candidates = [record.candidate for record in records
        if isinstance(getattr(record, "candidate", None), Mapping)
        and any(_task_family_history_examples(record.candidate,
            task_family_id=source_task_family_id))]
    source_projection = audit_task_family_history_projection(source_candidates,
        task_family_id=source_task_family_id,
        target_model_identity=target_model_identity)
    anchor_coverage = source_projection.get("independent_input_anchor_coverage")
    anchor_pair = (anchor_coverage.get("best_anchor_pair")
        if isinstance(anchor_coverage, Mapping) else None)
    run_digests = (anchor_pair.get("source_run_digests")
        if isinstance(anchor_pair, Mapping) else None)
    source_record_ids: list[str] = []
    if isinstance(run_digests, list) and len(run_digests) == 2:
        for run_digest in run_digests:
            match = next((record.record_id for record in records
                if any(example.get("source_run_digest") == run_digest
                    and example.get("task_family_id") == source_task_family_id
                    for example in _task_family_history_examples(
                        record.candidate,
                        task_family_id=source_task_family_id))), None)
            if isinstance(match, str) and match not in source_record_ids:
                source_record_ids.append(match)
    history_packets = []
    for record in records:
        experiences = [experience for family_id in declared_families
            for experience in _task_family_history_examples(
                record.candidate, task_family_id=family_id)]
        if experiences:
            history_packets.append({"task_relevant_experience": experiences})
    overlap = _task_family_history_probe_overlap(history_packets,
        task_probe_inputs=probe_inputs)
    source_anchors_available = (
        isinstance(anchor_coverage, Mapping)
        and anchor_coverage.get("status") ==
            "independent_correct_input_anchor_available"
        and len(source_record_ids) == 2)
    held_out = (
        overlap.get("historical_probe_overlap_measurement_complete") is True
        and overlap.get("historical_probe_overlap_input_count") == 0)
    eligible = source_anchors_available and held_out
    return {
        "eligible": eligible,
        "status": ("eligible" if eligible else
            "skipped_source_anchor_gate_not_met" if not source_anchors_available else
            "skipped_transfer_probes_overlap_or_history_incomplete"),
        "source_task_family_id": source_task_family_id,
        "target_task_family_id": target_family_id,
        "source_history_projection_audit": source_projection,
        "source_record_ids": source_record_ids,
        "all_family_probe_overlap": overlap,
        "held_out_transfer_qualified": held_out,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }


def _objective_transfer_observations(
        conditions: Any, required_history_record_ids: Sequence[str]
        ) -> dict[str, Mapping[str, Any]]:
    if (not isinstance(conditions, list) or len(conditions) != 3
            or any(not isinstance(item, Mapping) for item in conditions)
            or not isinstance(required_history_record_ids, (list, tuple))
            or not required_history_record_ids
            or any(not isinstance(item, str) or not item
                for item in required_history_record_ids)
            or len(set(required_history_record_ids)) !=
                len(required_history_record_ids)):
        raise RootlessExperimentalError(
            "objective_family_transfer_observation_lineage_incomplete")
    observations: dict[str, Mapping[str, Any]] = {}
    for item in conditions:
        condition_id = item.get("condition_id")
        if not isinstance(condition_id, str) or condition_id in observations:
            raise RootlessExperimentalError(
                "objective_family_transfer_observation_lineage_incomplete")
        observations[condition_id] = item
    if set(observations) != {
            "history_present", "history_withheld", "history_restored"}:
        raise RootlessExperimentalError(
            "objective_family_transfer_observation_lineage_incomplete")
    exposed_record_ids: list[str] = []
    for condition_id in ("history_present", "history_restored"):
        retrieved_ids = observations[condition_id].get("retrieved_record_ids", [])
        if (not isinstance(retrieved_ids, (list, tuple))
                or any(not isinstance(item, str) or not item
                    for item in retrieved_ids)
                or len(set(retrieved_ids)) != len(retrieved_ids)
                or any(record_id not in retrieved_ids
                    for record_id in required_history_record_ids)):
            raise RootlessExperimentalError(
                "objective_family_transfer_history_not_retrieved")
        exposed_record_ids.append(list(retrieved_ids))
    if exposed_record_ids[0] != exposed_record_ids[1]:
        raise RootlessExperimentalError(
            "objective_family_transfer_restoration_selection_mismatch")
    withheld_ids = observations["history_withheld"].get("retrieved_record_ids", [])
    if (not isinstance(withheld_ids, (list, tuple)) or withheld_ids):
        raise RootlessExperimentalError(
            "objective_family_transfer_withheld_history_leaked")
    return observations


def _answer_vector_comparison(conditions: Any, left: str, right: str) -> bool | None:
    """Compare exact scored answer vectors without copying answer values into the summary."""
    if not isinstance(conditions, list):
        return None
    rows = {row.get("condition_id"): row for row in conditions
        if isinstance(row, Mapping)}
    left_scope = rows.get(left, {}).get("answer_vector_scope_digest")
    right_scope = rows.get(right, {}).get("answer_vector_scope_digest")
    left_digest = rows.get(left, {}).get("answer_vector_digest")
    right_digest = rows.get(right, {}).get("answer_vector_digest")
    if (not isinstance(left_scope, str) or left_scope != right_scope
            or not isinstance(left_digest, str) or not isinstance(right_digest, str)):
        return None
    return left_digest != right_digest


def _answer_vector_match(conditions: Any, left: str, right: str) -> bool | None:
    difference = _answer_vector_comparison(conditions, left, right)
    return None if difference is None else not difference


def _objective_transfer_condition_summaries(
        scores: Any,
        observations: Mapping[str, Mapping[str, Any]],
        required_history_record_ids: Sequence[str],
        task_probe_inputs: Sequence[int],
        session: Any) -> list[dict[str, Any]]:
    """Keep each scored condition bound to its retrieved-history and receipt evidence."""
    expected_conditions = ("history_present", "history_withheld", "history_restored")
    if (not isinstance(scores, list)
            or len(scores) != len(expected_conditions)
            or any(not isinstance(item, Mapping) for item in scores)
            or tuple(item.get("condition_id") for item in scores) != expected_conditions
            or set(observations) != set(expected_conditions)):
        raise RootlessExperimentalError(
            "objective_family_transfer_report_conditions_incomplete")
    summaries: list[dict[str, Any]] = []
    for item, condition_id in zip(scores, expected_conditions):
        if not isinstance(item, Mapping) or item.get("condition_id") != condition_id:
            raise RootlessExperimentalError(
                "objective_family_transfer_report_conditions_incomplete")
        observation = observations[condition_id]
        receipt_id = item.get("inference_receipt_id")
        receipt_digest = item.get("inference_receipt_digest")
        output_digest = item.get("invocation_output_digest")
        score = item.get("score")
        score_mapping = score if isinstance(score, Mapping) else {}  # invariant-allow: score is report metadata only
        if (not isinstance(score, Mapping)  # invariant-allow: score is evaluation metadata only
                or score_mapping.get("output_digest") != output_digest
                or not isinstance(receipt_id, str) or not receipt_id
                or not isinstance(receipt_digest, str) or not receipt_digest
                or observation.get("inference_receipt_id") != receipt_id
                or observation.get("inference_receipt_digest") != receipt_digest
                or observation.get("output_digest") != output_digest):
            raise RootlessExperimentalError(
                "objective_family_transfer_report_lineage_invalid")
        retrieved_record_ids = observation.get("retrieved_record_ids", [])
        if (not isinstance(retrieved_record_ids, (list, tuple))
                or any(not isinstance(record_id, str) for record_id in retrieved_record_ids)):
            raise RootlessExperimentalError(
                "objective_family_transfer_report_lineage_invalid")
        try:
            persisted_receipt = session.verify_persisted_invocation_receipt(
                receipt_id, receipt_digest,
                expected_request_id=observation.get("request_id"),
                expected_request_digest=observation.get("request_digest"))
        except Exception as exc:
            raise RootlessExperimentalError(
                "objective_family_transfer_prompt_receipt_invalid") from exc
        prompt_delivery = _objective_task_family_prompt_delivery_evidence(
            persisted_receipt, observation, condition_id,
            required_history_record_ids=required_history_record_ids,
            task_probe_inputs=task_probe_inputs)
        probe_results = score_mapping.get("probe_results")
        answer_vector_digest = None
        answer_vector_scope_digest = None
        if (score_mapping.get("status") in {"correct", "incorrect", "selective"}
                and isinstance(probe_results, list)
                and len(probe_results) == score_mapping.get("probe_count")
                and type(score_mapping.get("probe_count")) is int
                and score_mapping["probe_count"] > 0
                and isinstance(score_mapping.get("task_digest"), str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}",
                    score_mapping["task_digest"]) is not None
                and all(isinstance(result, Mapping)
                    and type(result.get("probe_input")) is int
                    and type(result.get("observed_answer")) in {int, type(None)}
                    for result in probe_results)):
            scope = {
                "schema_version": "sentientos.objective_answer_vector_scope:v1",
                "task_digest": score_mapping["task_digest"],
                "probe_inputs": [result["probe_input"] for result in probe_results],
            }
            if len(set(scope["probe_inputs"])) == len(scope["probe_inputs"]):
                answer_vector_scope_digest = digest_payload(scope)
                answer_vector_digest = digest_payload({
                    "schema_version": "sentientos.objective_answer_vector:v1",
                    "scope_digest": answer_vector_scope_digest,
                    "answers": [result["observed_answer"] for result in probe_results],
                })
        summaries.append({
            "condition_id": condition_id,
            "correct_count": score_mapping.get("correct_count"),
            "probe_count": score_mapping.get("probe_count"),
            "score_status": score_mapping.get("status"),
            "answer_vector_scope_digest": answer_vector_scope_digest,
            "answer_vector_digest": answer_vector_digest,
            "output_digest": (score_mapping.get("output_digest")
                or item.get("invocation_output_digest")),
            "retrieved_record_ids": list(retrieved_record_ids),
            "task_family_history_record_id_retrieved": (
                required_history_record_ids[0] in retrieved_record_ids),
            "required_history_record_ids": list(required_history_record_ids),
            "required_history_record_ids_retrieved": all(
                record_id in retrieved_record_ids
                for record_id in required_history_record_ids),
            "task_family_prompt_delivery_evidence": prompt_delivery,
            "inference_receipt_id": item.get("inference_receipt_id"),
            "inference_receipt_digest": item.get("inference_receipt_digest"),
        })
    return summaries


def _objective_task_family_prompt_delivery_evidence(
        receipt_payload: Mapping[str, Any],
        observation: Mapping[str, Any], condition_id: str, *,
        required_history_record_ids: Sequence[str],
        task_probe_inputs: Sequence[int]) -> dict[str, Any]:
    """Verify answer-free task-history projection evidence in the exact receipt."""
    if (not isinstance(condition_id, str)
            or condition_id not in {"history_present", "history_withheld",
            "history_restored"}
            or not isinstance(required_history_record_ids, (list, tuple))
            or not required_history_record_ids
            or any(not isinstance(record_id, str) or not record_id
                for record_id in required_history_record_ids)
            or len(set(required_history_record_ids)) !=
                len(required_history_record_ids)
            or not isinstance(task_probe_inputs, (list, tuple))
            or not task_probe_inputs
            or any(type(value) is not int for value in task_probe_inputs)
            or len(set(task_probe_inputs)) != len(task_probe_inputs)):
        raise RootlessExperimentalError(
            "objective_family_transfer_prompt_condition_invalid")
    request = receipt_payload.get("request")
    upstream = (request.get("upstream_evidence")
        if isinstance(request, Mapping) else None)
    projection = (upstream.get("task_family_history_prompt_projection")
        if isinstance(upstream, Mapping) else None)
    if not isinstance(request, Mapping) or not isinstance(projection, Mapping):
        raise RootlessExperimentalError(
            "objective_family_transfer_prompt_projection_missing")
    projection_semantic = dict(projection)
    projection_digest = projection_semantic.pop("projection_digest", None)
    if (not isinstance(projection_digest, str)
            or projection_digest != "sha256:" + digest_payload(projection_semantic)
            or request.get("prompt_digest")
                != projection.get("governed_request_prompt_digest")
            or projection.get("prompt_binding_posture")
                != "exact_governed_request_prompt_digest"
            or projection.get("prompt_packet_binding_posture")
                != "canonical_selected_record_packet_substring_in_exact_prompt:v1"
            or projection.get("schema_version") not in {
                f"sentientos.task_family_history_prompt_projection:v{version}"
                for version in range(19, 36)}
            or projection.get("condition_id") != condition_id
            or projection.get("task_family_id") not in
                _SUPPORTED_OBJECTIVE_TRANSFER_TASK_FAMILIES
            or projection.get("historical_only") is not True
            or projection.get("current_truth") is not False
            or projection.get("authority") is not False):
        raise RootlessExperimentalError(
            "objective_family_transfer_prompt_projection_binding_invalid")
    accumulated_strategy = projection.get(
        "accumulated_candidate_integer_affine_strategy")
    accumulated_strategy_status = "no_candidate_in_projection"
    accumulated_strategy_digest = None
    accumulated_strategy_schema_version = None
    accumulated_strategy_anchor_run_digests = None
    accumulated_strategy_supporting_run_count = None
    accumulated_strategy_distinct_input_count = None
    accumulated_strategy_prompt_binding_posture = projection.get(
        "accumulated_candidate_prompt_binding_posture")
    strategy_omitted_by_ablation = (
        projection.get("schema_version") in {
            "sentientos.task_family_history_prompt_projection:v34",
            "sentientos.task_family_history_prompt_projection:v35"}
        and projection.get("accumulated_strategy_condition") == "omitted")
    if (projection.get("schema_version") in {
            "sentientos.task_family_history_prompt_projection:v34",
            "sentientos.task_family_history_prompt_projection:v35"}
            and not strategy_omitted_by_ablation):
        raise RootlessExperimentalError(
            "objective_family_transfer_strategy_ablation_binding_invalid")
    if accumulated_strategy is not None:
        if not isinstance(accumulated_strategy, Mapping):
            raise RootlessExperimentalError(
                "objective_family_transfer_accumulated_strategy_invalid")
        strategy_semantic = dict(accumulated_strategy)
        accumulated_strategy_digest = strategy_semantic.pop(
            "strategy_digest", None)
        accumulated_strategy_schema_version = accumulated_strategy.get(
            "schema_version")
        anchors = accumulated_strategy.get(
            "independent_input_anchor_run_digests")
        anchor_digest = accumulated_strategy.get(
            "independent_input_anchor_run_digests_digest")
        run_counts = accumulated_strategy.get("supporting_run_input_counts")
        supporting_run_count = accumulated_strategy.get("supporting_run_count")
        anchor_rows = ([row for row in run_counts if isinstance(row, Mapping)
                and row.get("independent_input_anchor") is True]
            if isinstance(run_counts, list) else [])
        compact_strategy_projection = projection.get("schema_version") in {
            "sentientos.task_family_history_prompt_projection:v32",
            "sentientos.task_family_history_prompt_projection:v33",
            "sentientos.task_family_history_prompt_projection:v34",
            "sentientos.task_family_history_prompt_projection:v35"}
        expected_accumulated_strategy_schema_version = (
            "sentientos.accumulated_integer_affine_strategy:v9"
            if compact_strategy_projection else
            "sentientos.accumulated_integer_affine_strategy:v8")
        if (projection.get("schema_version") not in {
                    "sentientos.task_family_history_prompt_projection:v26",
                    "sentientos.task_family_history_prompt_projection:v27",
                    "sentientos.task_family_history_prompt_projection:v28",
                    "sentientos.task_family_history_prompt_projection:v29",
                    "sentientos.task_family_history_prompt_projection:v30",
                    "sentientos.task_family_history_prompt_projection:v31",
                    "sentientos.task_family_history_prompt_projection:v32",
                    "sentientos.task_family_history_prompt_projection:v33",
                    "sentientos.task_family_history_prompt_projection:v34",
                    "sentientos.task_family_history_prompt_projection:v35"}
                or accumulated_strategy_schema_version !=
                    expected_accumulated_strategy_schema_version
                or not isinstance(accumulated_strategy_digest, str)
                or accumulated_strategy_digest != "sha256:" + digest_payload(
                    strategy_semantic)
                or accumulated_strategy.get("task_family_id")
                    != projection.get("task_family_id")
                or accumulated_strategy.get("historical_only") is not True
                or accumulated_strategy.get("current_truth") is not False
                or accumulated_strategy.get("authority") is not False
                or accumulated_strategy.get("learning_established") is not False
                or accumulated_strategy.get("performance_transfer_established") is not False
                or not isinstance(anchors, list) or len(anchors) != 2
                or any(not isinstance(value, str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                    for value in anchors)
                or len(set(anchors)) != 2
                or anchor_digest != "sha256:" + digest_payload(anchors)
                or type(accumulated_strategy.get(
                    "independent_input_anchor_run_count")) is not int
                or accumulated_strategy["independent_input_anchor_run_count"] != 2
                or type(supporting_run_count) is not int
                or supporting_run_count < 2
                or not isinstance(run_counts, list)
                or len(run_counts) != supporting_run_count
                or any(not isinstance(row, Mapping) for row in run_counts)
                or any(not isinstance(row.get("source_run_digest"), str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}",
                        row["source_run_digest"]) is None
                    or type(row.get("distinct_input_count")) is not int
                    or row["distinct_input_count"] < 1
                    or type(row.get("independent_input_anchor")) is not bool
                    for row in run_counts)
                or len({row["source_run_digest"] for row in run_counts})
                    != len(run_counts)
                or len(anchor_rows) != 2
                or sorted(row.get("source_run_digest") for row in anchor_rows)
                    != sorted(anchors)
                or any(type(row.get("distinct_input_count")) is not int
                    or row["distinct_input_count"] < 1 for row in anchor_rows)
                or type(accumulated_strategy.get(
                    "supporting_distinct_input_count")) is not int
                or accumulated_strategy["supporting_distinct_input_count"] < 3
                or (condition_id == "history_withheld")):
            raise RootlessExperimentalError(
                "objective_family_transfer_accumulated_strategy_invalid")
        if projection.get("schema_version") in {
                "sentientos.task_family_history_prompt_projection:v28",
                "sentientos.task_family_history_prompt_projection:v29",
                "sentientos.task_family_history_prompt_projection:v30",
                "sentientos.task_family_history_prompt_projection:v31",
                "sentientos.task_family_history_prompt_projection:v32",
                "sentientos.task_family_history_prompt_projection:v33",
                "sentientos.task_family_history_prompt_projection:v34",
                "sentientos.task_family_history_prompt_projection:v35"}:
            expected_prompt_posture = (
                "withheld_by_strategy_inclusion_ablation"
                if strategy_omitted_by_ablation else
                "canonical_compact_accumulated_strategy_substring_in_exact_prompt:v1"
                if projection.get("schema_version") in {
                    "sentientos.task_family_history_prompt_projection:v32",
                    "sentientos.task_family_history_prompt_projection:v33",
                    "sentientos.task_family_history_prompt_projection:v34",
                    "sentientos.task_family_history_prompt_projection:v35"}
                else "canonical_accumulated_strategy_substring_in_exact_prompt:v1")
            if accumulated_strategy_prompt_binding_posture != expected_prompt_posture:
                raise RootlessExperimentalError(
                    "objective_family_transfer_accumulated_strategy_prompt_binding_invalid")
            strategy_version = "v9" if compact_strategy_projection else "v8"
            accumulated_strategy_status = (
                "accumulated_strategy_omitted_by_ablation_condition"
                if strategy_omitted_by_ablation else
                f"{strategy_version}_candidate_substring_bound_to_owner_prompt")
        else:
            strategy_version = "v9" if compact_strategy_projection else "v8"
            accumulated_strategy_status = (
                f"{strategy_version}_candidate_projection_prompt_inclusion_unmeasured")
        accumulated_strategy_anchor_run_digests = list(anchors)
        accumulated_strategy_supporting_run_count = supporting_run_count
        accumulated_strategy_distinct_input_count = accumulated_strategy.get(
            "supporting_distinct_input_count")
    else:
        if strategy_omitted_by_ablation:
            raise RootlessExperimentalError(
                "objective_family_transfer_strategy_ablation_candidate_missing")
        if projection.get("schema_version") in {
                "sentientos.task_family_history_prompt_projection:v28",
                "sentientos.task_family_history_prompt_projection:v29",
                "sentientos.task_family_history_prompt_projection:v30",
                "sentientos.task_family_history_prompt_projection:v31",
                "sentientos.task_family_history_prompt_projection:v32",
                "sentientos.task_family_history_prompt_projection:v33",
                "sentientos.task_family_history_prompt_projection:v34",
                "sentientos.task_family_history_prompt_projection:v35"}:
            if accumulated_strategy_prompt_binding_posture != (
                    "no_accumulated_candidate_in_projection"):
                raise RootlessExperimentalError(
                    "objective_family_transfer_accumulated_strategy_prompt_binding_invalid")
        if condition_id == "history_withheld":
            accumulated_strategy_status = "withheld_condition_candidate_absent"
    negative_count = projection.get("prior_incorrect_example_count")
    negative_guidance = upstream.get(
        "task_family_negative_example_prompt_guidance")
    negative_guidance_verified = False
    negative_guidance_digest = None
    if negative_count is not None:
        if type(negative_count) is not int or negative_count < 0:
            raise RootlessExperimentalError(
                "objective_family_transfer_negative_example_count_invalid")
        if negative_count:
            if not isinstance(negative_guidance, Mapping):
                raise RootlessExperimentalError(
                    "objective_family_transfer_negative_example_guidance_missing")
            guidance_semantic = dict(negative_guidance)
            negative_guidance_digest = guidance_semantic.pop(
                "evidence_digest", None)
            expected_guidance = {
                "schema_version": TASK_FAMILY_NEGATIVE_EXAMPLE_GUIDANCE_SCHEMA,
                "posture": "instruction_substring_verified_in_governed_prompt",
                "prior_incorrect_example_count": negative_count,
                "instruction_digest": "sha256:" + digest_payload({"instruction":
                    TASK_FAMILY_PRIOR_INCORRECT_EXAMPLE_INSTRUCTION}),
                "governed_request_prompt_digest": request.get("prompt_digest"),
                "task_family_projection_digest": projection_digest,
                "model_attention_established": False,
                "learning_established": False,
                "authority": False,
            }
            if (guidance_semantic != expected_guidance
                    or not isinstance(negative_guidance_digest, str)
                    or negative_guidance_digest != "sha256:" + digest_payload(
                        expected_guidance)):
                raise RootlessExperimentalError(
                    "objective_family_transfer_negative_example_guidance_invalid")
            negative_guidance_verified = True
        elif negative_guidance is not None:
            raise RootlessExperimentalError(
                "objective_family_transfer_unexpected_negative_example_guidance")
    records = projection.get("records")
    if (not isinstance(records, list)
            or any(not isinstance(row, Mapping) for row in records)
            or any(type(row.get("experience_count")) is not int
                    or row["experience_count"] < 1
                    or type(row.get("example_count")) is not int
                    or row["example_count"] < 0
                    or not isinstance(row.get("prompt_packet_digest"), str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}",
                        row["prompt_packet_digest"]) is None
                    or row.get("prompt_packet_serialization_present") is not True
                    for row in records)):
        raise RootlessExperimentalError(
            "objective_family_transfer_prompt_projection_records_invalid")
    projected_record_ids = [row.get("record_id") for row in records]
    retrieved_record_ids = list(observation.get("retrieved_record_ids", ()))
    retrieved_record_digests = list(observation.get("retrieved_record_digests", ()))
    projected_record_digests = [row.get("record_digest") for row in records]
    expected_treatment = ("withheld" if condition_id == "history_withheld"
        else "present")
    task_relevant_example_count = sum(row["example_count"]
        for row in records)
    overlap_schema = projection.get("schema_version") in {
        "sentientos.task_family_history_prompt_projection:v24",
        "sentientos.task_family_history_prompt_projection:v25",
        "sentientos.task_family_history_prompt_projection:v26",
        "sentientos.task_family_history_prompt_projection:v27",
        "sentientos.task_family_history_prompt_projection:v28",
        "sentientos.task_family_history_prompt_projection:v29",
        "sentientos.task_family_history_prompt_projection:v30",
        "sentientos.task_family_history_prompt_projection:v31",
        "sentientos.task_family_history_prompt_projection:v32",
        "sentientos.task_family_history_prompt_projection:v33",
        "sentientos.task_family_history_prompt_projection:v34",
        "sentientos.task_family_history_prompt_projection:v35"}
    probe_overlap_count = projection.get(
        "historical_probe_overlap_input_count") if overlap_schema else None
    probe_overlap_posture = projection.get(
        "historical_probe_overlap_posture") if overlap_schema else (
            "legacy_overlap_unmeasured")
    overlap_example_count = projection.get(
        "historical_probe_overlap_example_count") if overlap_schema else None
    overlap_measurement_complete = projection.get(
        "historical_probe_overlap_measurement_complete") if overlap_schema else None
    probe_overlap_qualified = (not overlap_schema or (
        type(projection.get("task_probe_input_count")) is int
        and projection["task_probe_input_count"] == len(task_probe_inputs)
        and isinstance(projection.get("task_probe_input_digest"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}",
            projection["task_probe_input_digest"]) is not None
        and projection["task_probe_input_digest"] == "sha256:" + digest_payload({
            "probe_inputs": list(task_probe_inputs)})
        and isinstance(projection.get(
            "historical_probe_overlap_input_digest"), str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", projection[
            "historical_probe_overlap_input_digest"]) is not None
        and type(probe_overlap_count) is int
        and 0 <= probe_overlap_count <= projection["task_probe_input_count"]
        and type(overlap_example_count) is int
        and overlap_example_count >= probe_overlap_count
        and type(overlap_measurement_complete) is bool
        and projection.get("historical_probe_overlap_scope") ==
            "selected_score_bound_correct_incorrect_and_abstained_examples"
        and probe_overlap_posture in {
            "no_exact_historical_probe_overlap",
            "exact_historical_probe_overlap_present",
            "historical_probe_inputs_incomplete"}
        and ((not overlap_measurement_complete
                and probe_overlap_posture == "historical_probe_inputs_incomplete")
            or (overlap_measurement_complete
                and (probe_overlap_count == 0) == (
                    probe_overlap_posture == "no_exact_historical_probe_overlap")))
        and (probe_overlap_count == 0) == (overlap_example_count == 0)))
    if (projection.get("treatment") != expected_treatment
            or not probe_overlap_qualified
            or type(projection.get("selected_record_count")) is not int
            or projection.get("selected_record_count") != len(retrieved_record_ids)
            or type(projection.get("task_relevant_record_count")) is not int
            or projection.get("task_relevant_record_count") != len(records)
            or type(projection.get("task_relevant_example_count")) is not int
            or projection.get("task_relevant_example_count")
                != task_relevant_example_count
            or any(not isinstance(record_id, str) or not record_id
                or len(record_id) > 256
                for record_id in projected_record_ids)
            or any(not isinstance(record_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", record_digest) is None
                for record_digest in projected_record_digests)
            or any(not isinstance(record_id, str) or not record_id
                or len(record_id) > 256
                for record_id in retrieved_record_ids)
            or any(not isinstance(record_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", record_digest) is None
                for record_digest in retrieved_record_digests)
            or projected_record_ids != retrieved_record_ids
            or projected_record_digests != retrieved_record_digests
            or len(set(projected_record_ids)) != len(projected_record_ids)):
        raise RootlessExperimentalError(
            "objective_family_transfer_prompt_projection_history_mismatch")
    if condition_id == "history_withheld":
        if records or task_relevant_example_count:
            raise RootlessExperimentalError(
                "objective_family_transfer_withheld_prompt_history_leaked")
    elif (any(record_id not in projected_record_ids
            for record_id in required_history_record_ids)
            or not task_relevant_example_count):
        raise RootlessExperimentalError(
            "objective_family_transfer_prompt_history_not_projected")
    selection = observation.get("developmental_history_selection")
    selection_digest = (selection.get("selection_digest")
        if isinstance(selection, Mapping) else None)
    selected_records = (selection.get("selected_records")
        if isinstance(selection, Mapping) else None)
    selection_semantic = (dict(selection) if isinstance(selection, Mapping) else {})
    selection_semantic.pop("selection_digest", None)
    selected_record_ids = ([row.get("record_id") for row in selected_records]
        if isinstance(selected_records, (list, tuple))
        and all(isinstance(row, Mapping) for row in selected_records) else None)
    selected_record_digests = ([row.get("record_digest") for row in selected_records]
        if isinstance(selected_records, (list, tuple))
        and all(isinstance(row, Mapping) for row in selected_records) else None)
    if (not isinstance(selection_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", selection_digest) is None
            or selection_digest != "sha256:" + digest_payload(selection_semantic)
            or not isinstance(selected_records, (list, tuple))
            or selected_record_ids != retrieved_record_ids
            or selected_record_digests != retrieved_record_digests):
        raise RootlessExperimentalError(
            "objective_family_transfer_history_selection_binding_invalid")
    return {
        "schema_version": "sentientos.objective_task_family_prompt_delivery_evidence:v5",
        "status": "verified_projection_bound_to_governed_request",
        "condition_id": condition_id,
        "treatment": expected_treatment,
        "request_id": request.get("request_id"),
        "request_digest": request.get("request_digest"),
        "inference_prompt_digest": request.get("prompt_digest"),
        "projection_digest": projection_digest,
        "history_selection_digest": selection_digest,
        "history_selection_digest_recomputed": True,
        "selected_history_refs_match_observation": True,
        "selected_record_count": projection["selected_record_count"],
        "task_relevant_record_count": projection["task_relevant_record_count"],
        "task_relevant_example_count": task_relevant_example_count,
        "accumulated_strategy_delivery_status": accumulated_strategy_status,
        "accumulated_strategy_prompt_binding_posture": (
            accumulated_strategy_prompt_binding_posture),
        "accumulated_strategy_schema_version": accumulated_strategy_schema_version,
        "accumulated_strategy_digest": accumulated_strategy_digest,
        "accumulated_strategy_anchor_run_digests": (
            accumulated_strategy_anchor_run_digests),
        "accumulated_strategy_supporting_run_count": (
            accumulated_strategy_supporting_run_count),
        "accumulated_strategy_distinct_input_count": (
            accumulated_strategy_distinct_input_count),
        "task_probe_input_count": projection.get("task_probe_input_count"),
        "task_probe_input_digest": projection.get("task_probe_input_digest"),
        "historical_probe_overlap_input_digest": projection.get(
            "historical_probe_overlap_input_digest"),
        "historical_probe_overlap_example_count": overlap_example_count,
        "historical_probe_overlap_input_count": probe_overlap_count,
        "historical_probe_overlap_posture": probe_overlap_posture,
        "historical_probe_overlap_measurement_complete": (
            overlap_measurement_complete if overlap_schema else None),
        "historical_probe_overlap_measurement_posture": (
            ("owner_recomputed" if overlap_measurement_complete else
                "owner_recomputed_incomplete") if overlap_schema else
                "legacy_unmeasured"),
        "exact_probe_reuse_posture": (
            "exact_probe_reuse_detected" if overlap_schema
                and probe_overlap_count > 0 else
            "no_exact_probe_reuse_detected" if overlap_schema
                and overlap_measurement_complete is True else
            "exact_probe_reuse_measurement_incomplete" if overlap_schema else
            "exact_probe_reuse_legacy_unmeasured"),
        "negative_example_guidance_verified": negative_guidance_verified,
        "negative_example_guidance_digest": negative_guidance_digest,
        "task_relevant_record_ids": projected_record_ids,
        "task_relevant_record_prompt_packet_digests": [
            row["prompt_packet_digest"] for row in records],
        "task_relevant_record_prompt_packet_refs": [{
            "record_id": row["record_id"],
            "record_digest": row["record_digest"],
            "prompt_packet_digest": row["prompt_packet_digest"],
            "prompt_packet_serialization_present": True,
        } for row in records],
        "exact_task_family_packets_present_in_prompt": True,
        "prompt_packet_binding_posture": projection[
            "prompt_packet_binding_posture"],
        "owner_prompt_gate": "passed_before_governed_invocation",
        "answer_values_included": False,
        "raw_prompt_included": False,
        "claim_scope": "request_projection_binding_not_model_attention_or_learning",
    }


def _objective_task_pair(seed: int) -> tuple[ObjectivePredictionTask, ObjectivePredictionTask]:
    # A task family promises one stable mapping across its source runs. Earlier
    # v5 runs varied multiplier and offset under a shared family ID, which made
    # cross-run strategy accumulation unsound. The v6 family fixes the hidden
    # mapping while the seed varies disjoint acquisition and transfer probes.
    try:
        return rootless_integer_affine_transfer_task_pair(seed,
            task_family_id=_ACTIVE_OBJECTIVE_TRANSFER_TASK_FAMILY,
            transfer_probe_count=_ACTIVE_OBJECTIVE_TRANSFER_PROBE_COUNT)
    except ValueError as exc:
        raise RootlessExperimentalError(
            "hermes_experiment_seed_invalid") from exc


TRANSFER_DECISION_QUESTION = (
    "Controlled new-decision probe on a new synthetic task, not past recall. "
    "The current synthetic target is visible and within reach; its hazard status "
    "is unknown. Choose one action for it: INSPECT or REACH. Read the current "
    "World-State and eligible history. In each "
    "historical_embodiment_reports entry, compare "
    "reported_values.predicted_observation.pose with "
    "reported_values.observer_report_field.pose. If it records predicted "
    "reach followed by observer-reported idle, choose INSPECT before another "
    "reach as cautious information gathering, not proof of physical effect. "
    "Without that record, choose REACH from the current target. Treat past "
    "values as uncertain reports, never current truth. Return JSON "
    "disposition answer, evidence_ids with the exact current fact ID grounding "
    "the target, history_record_ids with the exact cited record ID supporting "
    "INSPECT (otherwise []), and response exactly INSPECT or REACH. If no "
    "current fact grounds the target, abstain with response "
    "HISTORY_UNAVAILABLE and no citations. This is a proposal only; do not "
    "claim action authority or execution.")


def _history_transfer_fact_source_binding_valid(
        fact: Mapping[str, Any]) -> bool:
    """Rebuild the producer envelope and bind it to its selected fact source."""
    source, subject, payload = (fact.get("source"), fact.get("subject"),
        fact.get("payload"))
    if not all(isinstance(value, Mapping) for value in (source, subject, payload)):
        return False
    assert isinstance(source, Mapping) and isinstance(subject, Mapping)
    assert isinstance(payload, Mapping)
    if (source.get("kind") != "embodiment"
            or source.get("finding") != "ok"
            or source.get("source_id") != payload.get("attribution_id")
            or source.get("schema_version") != payload.get("schema_version")
            or subject.get("subject_id") != payload.get("expectation_id")
            or subject.get("subject_kind") != "embodied_consequence_attribution"
            or fact.get("stage") != "observation"
            or fact.get("disposition") != payload.get("classification")
            or fact.get("effect_claimed") is not False
            or fact.get("effect_proven") is not False):
        return False
    producer_record = {
        "source_kind": source.get("kind"),
        "source_id": source.get("source_id"),
        "schema_version": source.get("schema_version"),
        "subject_id": subject.get("subject_id"),
        "subject_kind": subject.get("subject_kind"),
        "stage": fact.get("stage"),
        "disposition": fact.get("disposition"),
        "effect_claimed": fact.get("effect_claimed"),
        "effect_proven": fact.get("effect_proven"),
        "payload": dict(payload),
    }
    try:
        return (isinstance(source.get("digest"), str)
            and world_state_record_digest(producer_record) == source.get("digest"))
    except (TypeError, ValueError, RecursionError):
        return False


def _history_transfer_probe_readiness(record: Mapping[str, Any]) -> dict[str, Any]:
    """Require a matching retained event with authenticated observation lineage.

    Structural pattern matches are reported separately from eligible evidence:
    an unverified caller assertion must not satisfy the history-transfer gate.
    """
    try:
        retained_record_digest = digest_payload(dict(record))
    except (TypeError, ValueError, OverflowError, RecursionError):
        retained_record_digest = None
    if retained_record_digest is None:
        return {"schema_version": "sentientos.history_transfer_evidence_precondition:v3",
            "eligible": False,
            "reason_code": "retained_history_record_snapshot_digest_unavailable",
            "record_id": record.get("record_id"),
            "retained_record_digest": None,
            "retained_record_snapshot_binding_posture": "unavailable",
            "evidence_fact_ids": [], "pattern_match_fact_ids": [],
            "provenance_failure_codes": [
                "retained_history_record_snapshot_digest_unavailable"]}
    candidate = record.get("candidate")
    if not isinstance(candidate, Mapping):
        return {"schema_version": "sentientos.history_transfer_evidence_precondition:v3",
            "eligible": False,
            "reason_code": "retained_history_facts_unavailable",
            "record_id": record.get("record_id"),
            "retained_record_digest": retained_record_digest,
            "retained_record_snapshot_binding_posture": "digest_of_readiness_input",
            "evidence_fact_ids": [],
            "pattern_match_fact_ids": [], "provenance_failure_codes": []}
    facts = candidate.get("selected_facts")
    if not isinstance(facts, list):
        return {"schema_version": "sentientos.history_transfer_evidence_precondition:v3",
            "eligible": False,
            "reason_code": "retained_history_facts_unavailable",
            "record_id": record.get("record_id"),
            "retained_record_digest": retained_record_digest,
            "retained_record_snapshot_binding_posture": "digest_of_readiness_input",
            "evidence_fact_ids": [],
            "pattern_match_fact_ids": [], "provenance_failure_codes": []}
    matching_fact_ids: list[str] = []
    authenticated_fact_ids: list[str] = []
    provenance_failure_codes: set[str] = set()
    for fact in facts:
        if not isinstance(fact, Mapping):
            continue
        payload = fact.get("payload")
        source = fact.get("source")
        if not isinstance(payload, Mapping) or not isinstance(source, Mapping):
            continue
        schema = (payload.get("schema_version")
            or source.get("schema_version"))
        if schema not in {
                "sentientos.embodied_consequence_attribution:v1",
                "sentientos.embodied_consequence_attribution:v2"}:
            continue
        commanded = payload.get("commanded_value")
        predicted = payload.get("predicted_value")
        observed = payload.get("independently_observed_value")
        if (not isinstance(commanded, Mapping)
                or not isinstance(predicted, Mapping)
                or not isinstance(observed, Mapping)):
            continue
        if (commanded.get("pose") == "reach"
                and commanded.get("task_goal") == "reach_marked_target"
                and predicted.get("pose") == "reach"
                and observed.get("pose") == "idle"
                and observed.get("task_goal_met") is False):
            fact_id = fact.get("fact_id")
            if isinstance(fact_id, str) and fact_id:
                matching_fact_ids.append(fact_id)
                source_binding_valid = (
                    _history_transfer_fact_source_binding_valid(fact))
                receipt = payload.get("observation_authentication_receipt")
                try:
                    verify_consequence_attribution(payload)
                    attribution_valid = True
                except (EmbodiedConsequenceError, KeyError, TypeError,
                        ValueError, OverflowError):
                    attribution_valid = False
                if not source_binding_valid:
                    provenance_failure_codes.add(
                        "selected_history_fact_source_binding_invalid")
                elif schema != "sentientos.embodied_consequence_attribution:v2":
                    provenance_failure_codes.add(
                        "observation_attribution_schema_legacy_or_unsupported")
                elif (isinstance(receipt, Mapping)
                        and receipt.get("observer_fixture_posture")
                            == "same_process_synthetic_fixture"):
                    provenance_failure_codes.add(
                        "same_process_synthetic_observer_not_independent_history")
                elif (payload.get("observation_independence_posture")
                        != "authenticated_source_distinct_from_renderer_at_ingress"):
                    provenance_failure_codes.add(
                        "observation_independence_posture_unverified")
                elif not isinstance(receipt, Mapping) or not attribution_valid:
                    provenance_failure_codes.add(
                        "observation_authentication_receipt_invalid")
                else:
                    authenticated_fact_ids.append(fact_id)
    if authenticated_fact_ids:
        return {"schema_version": "sentientos.history_transfer_evidence_precondition:v3",
            "eligible": True,
            "reason_code": "retained_history_matches_probe_pattern",
            "record_id": record.get("record_id"),
            "retained_record_digest": retained_record_digest,
            "retained_record_snapshot_binding_posture": "digest_of_readiness_input",
            "evidence_fact_ids": sorted(set(authenticated_fact_ids)),
            "pattern_match_fact_ids": sorted(set(matching_fact_ids)),
            "provenance_failure_codes": []}
    if matching_fact_ids:
        return {"schema_version": "sentientos.history_transfer_evidence_precondition:v3",
            "eligible": False,
            "reason_code": "retained_history_observation_provenance_unverified",
            "record_id": record.get("record_id"),
            "retained_record_digest": retained_record_digest,
            "retained_record_snapshot_binding_posture": "digest_of_readiness_input",
            "evidence_fact_ids": [],
            "pattern_match_fact_ids": sorted(set(matching_fact_ids)),
            "provenance_failure_codes": sorted(provenance_failure_codes)}
    return {"schema_version": "sentientos.history_transfer_evidence_precondition:v3",
        "eligible": False,
        "reason_code": "retained_history_does_not_match_probe_pattern",
        "record_id": record.get("record_id"),
        "retained_record_digest": retained_record_digest,
        "retained_record_snapshot_binding_posture": "digest_of_readiness_input",
        "evidence_fact_ids": [],
        "pattern_match_fact_ids": [], "provenance_failure_codes": []}


DEFAULT_MANIFEST_PATH = EXPERIMENT_ROOT / "ollama-model-manifests" / (
    "f6a766d405cbb73f9ba64a59b8fb29a3418d0da0b6fad15a0ca70687413ce0ce.json")


def _configured_model_manifest_path() -> Path:
    """Select one exact Ollama manifest; no model discovery or fallback."""
    configured = os.environ.get("SENTIENTOS_HERMES_MODEL_MANIFEST_PATH")
    return Path(configured) if configured else DEFAULT_MANIFEST_PATH


MANIFEST_PATH = _configured_model_manifest_path()


def _resolve_pinned_model_manifest_path(path: Path | None = None) -> Path:
    """Require the selected manifest to be a regular file in experiment custody."""
    try:
        experiment_root = _no_symlink_path(EXPERIMENT_ROOT).resolve(strict=True)
        manifest_path = _no_symlink_path(path or MANIFEST_PATH).resolve(strict=True)
        manifest_path.relative_to(experiment_root)
    except (OSError, ValueError) as exc:
        raise RootlessExperimentalError(
            "pinned_hermes_manifest_outside_experimental_custody") from exc
    if not manifest_path.is_file():
        raise RootlessExperimentalError("pinned_hermes_manifest_missing")
    return manifest_path


def _persist_historical_pair_model_identity_preflight(
        evidence: Mapping[str, Any]) -> Path:
    report_root = (workspace / "sentientos-data" / "rootless-experimental"
        / "preflight-failures")
    _no_symlink_path(report_root)
    report_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(report_root, 0o700)
    report_path = report_root / (
        str(evidence["run_id"]) + "-model-identity-"
        + secrets.token_hex(8) + ".json")
    _write_private_json_exclusive(report_path, evidence)
    return report_path


def _persist_source_provenance_preflight(*, initial: Mapping[str, Any],
        observed: Mapping[str, Any]) -> Path:
    """Persist a bounded, non-promoting source-integrity preflight record."""
    global SOURCE_PROVENANCE_PREFLIGHT_EVIDENCE_PATH
    report_root = (workspace / "sentientos-data" / "rootless-experimental"
        / "preflight-failures")
    _no_symlink_path(report_root)
    report_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(report_root, 0o700)
    semantic = {
        "schema_version": "sentientos.source_provenance_preflight:v1",
        "run_id": RUN_ID,
        "initial_source_provenance": dict(initial),
        "observed_source_provenance": dict(observed),
        "source_provenance_stable": dict(initial) == dict(observed),
        "source_provenance_complete": (
            observed.get("observation_status") == "observed"
            and observed.get("worktree_content_status") == "complete"
            and isinstance(observed.get("worktree_content_digest"), str)),
        "model_loaded": False, "model_invoked": False,
        "inference_performed": False, "learning_established": False,
        "authority": False,
    }
    artifact_digest = "sha256:" + digest_payload(semantic)
    evidence = {**semantic, "artifact_digest": artifact_digest}
    report_path = report_root / (
        str(RUN_ID) + "-source-provenance-" + secrets.token_hex(8) + ".json")
    _write_private_json_exclusive(report_path, evidence)
    SOURCE_PROVENANCE_PREFLIGHT_EVIDENCE_PATH = str(report_path)
    return report_path


def _preflight_historical_pair_model_identity(*, context: Mapping[str, Any],
        manifest_path: Path, manifest_digest: str,
        manifest_size: int) -> dict[str, Any]:
    """Predict the pinned backend identity without loading or invoking Ollama."""
    global HISTORICAL_PAIR_MODEL_IDENTITY_PREFLIGHT_PATH
    options = _rootless_ollama_model_options(model_name=MODEL_NAME,
        manifest_digest=manifest_digest, gpu_layers=GPU_LAYERS)
    candidate = ModelCandidate(manifest_path, "ollama", MODEL_NAME, options)
    config = ModelConfig([candidate], default_engine="ollama",
        max_context_tokens=8192,
        generation=GenerationConfig(max_new_tokens=512, temperature=0,
            top_p=1))
    resolved, semantic, content, size, sidecar = candidate_artifact_identity(
        candidate, {})
    if (content != manifest_digest or size != manifest_size
            or resolved is None or semantic != "sha256:" + manifest_digest):
        raise RootlessExperimentalError(
            "historical_examples_pair_model_artifact_preflight_mismatch")
    identity = ActiveModelIdentity(engine="ollama",
        resolved_artifact_path=resolved,
        semantic_artifact_identity=semantic,
        model_content_sha256=content, artifact_size_bytes=size,
        sidecar_metadata_digest=sidecar,
        configuration_digest=candidate_configuration_digest(
            candidate, config, "ollama"),
        candidate_index=0, posture="development_only", fallback=False)
    configuration_observation = {
        "schema_version": "sentientos.active_model_configuration_observation:v1",
        "configuration_digest": identity.configuration_digest,
        "payload": candidate_configuration_payload(candidate, config, "ollama"),
    }
    identity_digest = "sha256:" + digest_payload(identity.to_dict())
    target_identity_digest = context["plan"].get(
        "target_model_identity_digest")
    source_identity = context.get("source_model_identity")
    if not isinstance(source_identity, Mapping):
        raise RootlessExperimentalError(
            "historical_examples_pair_source_model_identity_invalid")
    source_identity_payload = dict(source_identity)
    identity_difference_fields = sorted(key for key in set(
        source_identity_payload) | set(identity.to_dict())
        if source_identity_payload.get(key) != identity.to_dict().get(key))
    # The archived source identity is evidence about where history came from.
    # The frozen plan separately names the target identity for this run, so a
    # model transition must not be rejected merely because those identities differ.
    matched = identity_digest == target_identity_digest
    evidence = {
        "schema_version":
            "sentientos.historical_examples_pair_model_identity_preflight:v1",
        "status": ("matched_without_model_load" if matched
            else "rejected_identity_mismatch"),
        "run_id": RUN_ID,
        "trial_index": context.get("trial_index"),
        "execution_plan_digest": context["plan"].get(
            "execution_plan_digest"),
        "source_receipt_id": context["plan"].get("source_receipt_id"),
        "source_receipt_digest": context["plan"].get(
            "source_receipt_digest"),
        "source_preregistration_digest": context.get(
            "source_preregistration_digest"),
        "source_configuration_observation_status": context.get(
            "source_configuration_observation_status"),
        "source_active_model_identity": source_identity_payload,
        "target_model_identity_digest": target_identity_digest,
        "predicted_model_identity_digest": identity_digest,
        "predicted_model_configuration_observation":
            configuration_observation,
        **({"source_model_configuration_observation": dict(
            context["source_model_configuration_observation"])}
            if isinstance(context.get(
                "source_model_configuration_observation"), Mapping)
            else {}),
        "identity_difference_fields": identity_difference_fields,
        ("active_model_identity" if matched
            else "predicted_active_model_identity"): identity.to_dict(),
        "run_root_allocated": False,
        "model_loaded": False,
        "model_invoked": False,
    }
    HISTORICAL_PAIR_MODEL_IDENTITY_PREFLIGHT_PATH = str(
        _persist_historical_pair_model_identity_preflight(evidence))
    if not matched:
        raise RootlessExperimentalError(
            "historical_examples_pair_model_identity_preflight_mismatch")
    return evidence
RUN_STAGE = "startup"
RUN_STAGE_SEQUENCE = 0
PRE_ACTION_DECISION_EVIDENCE: dict[str, Any] | None = None
RUN_FAILURE_DIAGNOSTIC: dict[str, Any] | None = None
INITIAL_HISTORY_BOOTSTRAP_EVIDENCE: dict[str, Any] | None = None
RESOURCE_PREFLIGHT_EVIDENCE: list[dict[str, Any]] = []
RUN_SOURCE_PROVENANCE_AT_END: dict[str, Any] | None = None
# Retained experiment artifacts can make a development worktree large. Keep
# hashing the complete tree, with a finite bound, instead of omitting inputs.
_SOURCE_FINGERPRINT_MAX_BYTES = 512 * 1024 * 1024
_SOURCE_PROVENANCE_COMMAND_TIMEOUT_SECONDS = 180


def _source_provenance_git_environment(root: Path) -> dict[str, str]:
    """Resolve a Windows Git worktree pointer when this checkout runs in WSL."""
    environment = os.environ.copy()
    if environment.get("GIT_DIR") or os.name == "nt":
        return environment
    marker = root / ".git"
    try:
        if (marker.is_symlink() or not marker.is_file()
                or marker.stat().st_size > 4096):
            return environment
        raw = marker.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return environment
    match = re.fullmatch(r"gitdir:\s*([A-Za-z]):[\\/](.+)", raw)
    if match is None:
        return environment
    mount = Path("/mnt") / match.group(1).lower()
    git_directory = mount.joinpath(*re.split(r"[\\/]", match.group(2)))
    if git_directory.is_dir():
        environment["GIT_DIR"] = str(git_directory)
        environment["GIT_WORK_TREE"] = str(root)
    return environment


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_run_stage(stage: str) -> None:
    """Persist a bounded, write-once lifecycle checkpoint inside run custody."""
    global RUN_STAGE, RUN_STAGE_SEQUENCE
    if (not isinstance(stage, str)
            or re.fullmatch(r"[a-z0-9_]{1,64}", stage) is None):
        raise RootlessExperimentalError("cycle_stage_checkpoint_invalid")
    RUN_STAGE = stage
    if not RUN_ROOT.is_dir() or RUN_ROOT.is_symlink():
        return
    RUN_STAGE_SEQUENCE += 1
    checkpoint = {
        "schema_version": "sentientos.rootless_cycle_stage_checkpoint:v2",
        "run_id": RUN_ID,
        "stage_sequence": RUN_STAGE_SEQUENCE,
        "stage": stage,
        "checkpoint_kind": "stage_entered",
        "recorded_at_utc": _now(),
        "external_preregistration_digest": (
            _optional_preregistration_digest(PREREGISTRATION_DIGEST)),
        "run_preregistration_digest": RUN_PREREGISTRATION_DIGEST,
        "source_provenance": dict(RUN_SOURCE_PROVENANCE),
        "raw_prompts_and_model_output_excluded": True,
    }
    checkpoint["checkpoint_digest"] = digest_payload(checkpoint)
    target = RUN_ROOT / (
        f"stage-checkpoint-{RUN_STAGE_SEQUENCE:04d}-{stage}.json")
    _no_symlink_path(target)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(checkpoint, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    if os.name != "nt":
        directory_descriptor = os.open(RUN_ROOT, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)


def _summarize_run_stage_journal(run_root: Path | None = None) -> dict[str, Any]:
    """Verify bounded stage checkpoints without interpreting them as recovery."""
    root = run_root or RUN_ROOT
    base = {"schema_version": "sentientos.rootless_cycle_stage_journal_summary:v1",
        "run_id": RUN_ID, "checkpoint_count": 0,
        "last_entered_stage": None, "checkpoints": [],
        "integrity_status": "unavailable", "recovery_performed": False}
    if not root.is_dir() or root.is_symlink():
        return base
    try:
        paths = []
        for path in root.glob("stage-checkpoint-*.json"):
            paths.append(path)
            if len(paths) > 32:
                return {**base, "checkpoint_count": 33,
                    "integrity_status": "checkpoint_count_over_bound"}
        paths.sort()
    except OSError:
        return {**base, "integrity_status": "unreadable"}
    if not paths:
        return {**base, "integrity_status": "empty"}
    rows: list[dict[str, Any]] = []
    digest_bound = True
    invalid = False
    for path in paths:
        match = re.fullmatch(r"stage-checkpoint-(\d{4})-([a-z0-9_]{1,64})\.json",
            path.name)
        if path.is_symlink() or match is None:
            invalid = True
            continue
        try:
            if path.stat().st_size > 65_536:
                invalid = True
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
            invalid = True
            continue
        if not isinstance(payload, dict):
            invalid = True
            continue
        schema = payload.get("schema_version")
        checkpoint_fields = {"schema_version", "run_id", "stage_sequence",
            "stage", "checkpoint_kind", "recorded_at_utc",
            "external_preregistration_digest", "run_preregistration_digest",
            "source_provenance", "raw_prompts_and_model_output_excluded"}
        if schema == "sentientos.rootless_cycle_stage_checkpoint:v2":
            expected_fields = checkpoint_fields | {"checkpoint_digest"}
            semantic = {key: value for key, value in payload.items()
                if key != "checkpoint_digest"}
            try:
                checkpoint_digest_valid = (
                    isinstance(payload.get("checkpoint_digest"), str)
                    and payload["checkpoint_digest"] == digest_payload(semantic))
            except (TypeError, ValueError, RecursionError):
                checkpoint_digest_valid = False
            digest_bound = digest_bound and checkpoint_digest_valid
            if not checkpoint_digest_valid:
                invalid = True
        elif schema == "sentientos.rootless_cycle_stage_checkpoint:v1":
            expected_fields = checkpoint_fields
            checkpoint_digest_valid = False
            digest_bound = False
        else:
            invalid = True
            continue
        sequence = int(match.group(1))
        stage = match.group(2)
        if (set(payload) != expected_fields
                or payload.get("run_id") != RUN_ID
                or type(payload.get("stage_sequence")) is not int
                or payload.get("stage_sequence") != sequence
                or payload.get("stage") != stage
                or payload.get("checkpoint_kind") != "stage_entered"
                or not isinstance(payload.get("recorded_at_utc"), str)
                or payload.get("raw_prompts_and_model_output_excluded") is not True
                or not isinstance(payload.get("source_provenance"), Mapping)):
            invalid = True
            continue
        rows.append({"stage_sequence": sequence, "stage": stage,
            "checkpoint_digest": payload.get("checkpoint_digest"),
            "digest_verified": checkpoint_digest_valid})
    rows.sort(key=lambda item: item["stage_sequence"])
    sequences = [row["stage_sequence"] for row in rows]
    if sequences != list(range(1, len(rows) + 1)):
        invalid = True
    status = ("invalid" if invalid else
        "valid_digest_bound" if digest_bound else "valid_legacy_unhashed")
    return {**base, "checkpoint_count": len(paths),
        "last_entered_stage": rows[-1]["stage"] if rows else None,
        "checkpoints": rows, "integrity_status": status}


def _worktree_content_fingerprint(root: Path, *,
        git_environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Hash tracked diffs and bounded untracked file contents without retaining them."""
    unavailable = {"worktree_content_status": "unavailable",
        "worktree_content_digest": None,
        "worktree_content_digest_algorithm": None}
    try:
        diff = subprocess.run([_SOURCE_PROVENANCE_GIT, "diff", "--binary", "--no-ext-diff",
            "--no-textconv", "HEAD"], cwd=root, capture_output=True,
            env=git_environment, timeout=_SOURCE_PROVENANCE_COMMAND_TIMEOUT_SECONDS,
            check=True)
        untracked = subprocess.run([_SOURCE_PROVENANCE_GIT, "ls-files", "--others", "--exclude-standard",
            "-z"], cwd=root, capture_output=True, env=git_environment,
            timeout=_SOURCE_PROVENANCE_COMMAND_TIMEOUT_SECONDS, check=True)
        indexed = subprocess.run([_SOURCE_PROVENANCE_GIT, "ls-files", "--stage", "-z"],
            cwd=root, capture_output=True, env=git_environment,
            timeout=_SOURCE_PROVENANCE_COMMAND_TIMEOUT_SECONDS, check=True)
        flags = subprocess.run([_SOURCE_PROVENANCE_GIT, "ls-files", "-v", "-z"], cwd=root,
            capture_output=True, env=git_environment,
            timeout=_SOURCE_PROVENANCE_COMMAND_TIMEOUT_SECONDS, check=True)
        diff_raw = diff.stdout
        untracked_raw = untracked.stdout
        indexed_raw = indexed.stdout
        flags_raw = flags.stdout
        diff_bytes = diff_raw if isinstance(diff_raw, bytes) else str(
            diff_raw).encode("utf-8")
        untracked_bytes = untracked_raw if isinstance(untracked_raw, bytes) else str(
            untracked_raw).encode("utf-8")
        indexed_bytes = indexed_raw if isinstance(indexed_raw, bytes) else str(
            indexed_raw).encode("utf-8")
        flags_bytes = flags_raw if isinstance(flags_raw, bytes) else str(
            flags_raw).encode("utf-8")
        if any(entry[:1] in {b"h", b"s", b"S"}
                for entry in flags_bytes.split(b"\0") if entry):
            return {"worktree_content_status": "tracked_index_worktree_flags_present",
                "worktree_content_digest": None,
                "worktree_content_digest_algorithm": None}
        if any(entry.startswith(b"160000 ")
                for entry in indexed_bytes.split(b"\0") if entry):
            return {"worktree_content_status": "submodule_content_unverified",
                "worktree_content_digest": None,
                "worktree_content_digest_algorithm": None}
        if len(diff_bytes) > _SOURCE_FINGERPRINT_MAX_BYTES:
            return {"worktree_content_status": "size_limit_exceeded",
                "worktree_content_digest": None,
                "worktree_content_digest_algorithm": None}
        untracked_paths = sorted(item for item in untracked_bytes.split(b"\0")
            if item)
        if len(untracked_paths) > 4096:
            return {"worktree_content_status": "entry_limit_exceeded",
                "worktree_content_digest": None,
                "worktree_content_digest_algorithm": None}
        digest = hashlib.sha256()
        digest.update(b"sentientos.source_worktree_fingerprint:v3\0")

        def add_frame(label: bytes, content: bytes) -> None:
            digest.update(len(label).to_bytes(8, "big"))
            digest.update(label)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)

        total_bytes = len(diff_bytes)
        add_frame(b"tracked_git_diff", diff_bytes)
        for raw_path in untracked_paths:
            relative_name = os.fsdecode(raw_path)
            relative_path = Path(relative_name)
            if (relative_path.is_absolute() or relative_path.drive
                    or relative_path.root
                    or not relative_path.parts
                    or any(part in {"", ".", ".."} for part in relative_path.parts)):
                return {"worktree_content_status": "untracked_path_invalid",
                    "worktree_content_digest": None,
                    "worktree_content_digest_algorithm": None}
            candidate = root
            symlink_target: bytes | None = None
            try:
                for index, part in enumerate(relative_path.parts):
                    candidate = candidate / part
                    metadata = os.lstat(candidate)
                    if stat.S_ISLNK(metadata.st_mode):
                        # Hash the literal final link target without following
                        # it. Intermediate links remain rejected so a path can
                        # never redirect reads outside the checkout.
                        if index != len(relative_path.parts) - 1:
                            return {"worktree_content_status":
                                "untracked_symlink_ancestor_present",
                                "worktree_content_digest": None,
                                "worktree_content_digest_algorithm": None}
                        target = os.readlink(candidate)
                        symlink_target = os.fsencode(target)
                        after_link = os.lstat(candidate)
                        if (not stat.S_ISLNK(after_link.st_mode)
                                or after_link.st_dev != metadata.st_dev
                                or after_link.st_ino != metadata.st_ino
                                or after_link.st_size != metadata.st_size
                                or after_link.st_mtime_ns != metadata.st_mtime_ns
                                or after_link.st_ctime_ns != metadata.st_ctime_ns
                                or after_link.st_mode != metadata.st_mode):
                            return {"worktree_content_status":
                                "untracked_symlink_changed_during_fingerprint",
                                "worktree_content_digest": None,
                                "worktree_content_digest_algorithm": None}
                        break
                    final_component = index == len(relative_path.parts) - 1
                    if (not final_component and not stat.S_ISDIR(metadata.st_mode)
                            or final_component and not stat.S_ISREG(metadata.st_mode)):
                        return {"worktree_content_status": "untracked_entry_not_regular_file",
                            "worktree_content_digest": None,
                            "worktree_content_digest_algorithm": None}
                if symlink_target is not None:
                    if (len(symlink_target) > _SOURCE_FINGERPRINT_MAX_BYTES
                            or total_bytes + len(symlink_target) + len(raw_path)
                                > _SOURCE_FINGERPRINT_MAX_BYTES):
                        return {"worktree_content_status": "size_limit_exceeded",
                            "worktree_content_digest": None,
                            "worktree_content_digest_algorithm": None}
                    add_frame(b"untracked_path", raw_path)
                    add_frame(b"untracked_symlink_target", symlink_target)
                    digest.update((metadata.st_mode & 0o7777).to_bytes(4, "big"))
                    total_bytes += len(symlink_target) + len(raw_path)
                    continue
                # The fingerprint hashes exact file bytes. Windows C-runtime
                # descriptors can otherwise translate CRLF during os.read.
                flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_BINARY", 0))
                descriptor = os.open(candidate, flags)
                try:
                    opened = os.fstat(descriptor)
                    if not stat.S_ISREG(opened.st_mode):
                        return {"worktree_content_status": "untracked_entry_not_regular_file",
                            "worktree_content_digest": None,
                            "worktree_content_digest_algorithm": None}
                    # NTFS path stat and handle stat can report different
                    # change-time values for the same file. Keep the stable
                    # identity, size, write-time, and mode comparison here;
                    # the repeated handle stat below still checks change time.
                    if (opened.st_dev != metadata.st_dev
                            or opened.st_ino != metadata.st_ino
                            or opened.st_size != metadata.st_size
                            or opened.st_mtime_ns != metadata.st_mtime_ns
                            or opened.st_mode != metadata.st_mode):
                        return {"worktree_content_status": "untracked_file_changed_during_fingerprint",
                            "worktree_content_digest": None,
                            "worktree_content_digest_algorithm": None}
                    if (opened.st_size > _SOURCE_FINGERPRINT_MAX_BYTES
                            or total_bytes + opened.st_size + len(raw_path)
                                > _SOURCE_FINGERPRINT_MAX_BYTES):
                        return {"worktree_content_status": "size_limit_exceeded",
                            "worktree_content_digest": None,
                            "worktree_content_digest_algorithm": None}
                    add_frame(b"untracked_path", raw_path)
                    digest.update((opened.st_mode & 0o7777).to_bytes(4, "big"))
                    digest.update(opened.st_size.to_bytes(8, "big"))
                    remaining = opened.st_size
                    while remaining:
                        chunk = os.read(descriptor, min(65_536, remaining))
                        if not chunk:
                            return {"worktree_content_status": "untracked_file_changed_during_fingerprint",
                                "worktree_content_digest": None,
                                "worktree_content_digest_algorithm": None}
                        digest.update(chunk)
                        remaining -= len(chunk)
                    after = os.fstat(descriptor)
                    if (after.st_size != opened.st_size
                            or after.st_mtime_ns != opened.st_mtime_ns
                            or after.st_ctime_ns != opened.st_ctime_ns
                            or after.st_mode != opened.st_mode):
                        return {"worktree_content_status": "untracked_file_changed_during_fingerprint",
                            "worktree_content_digest": None,
                            "worktree_content_digest_algorithm": None}
                    total_bytes += opened.st_size + len(raw_path)
                finally:
                    os.close(descriptor)
            except (OSError, UnicodeError, OverflowError):
                return unavailable
        return {"worktree_content_status": "complete",
            "worktree_content_digest": digest.hexdigest(),
            "worktree_content_digest_algorithm": (
                "sha256_framed_tracked_git_diff_and_untracked_file_tree_v3")}
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return unavailable


def _source_provenance(repo_root: Path | None = None) -> dict[str, Any]:
    """Bind experiment evidence to a revision without retaining local paths."""
    root = (Path(__file__).resolve().parents[1] if repo_root is None
        else Path(repo_root).resolve())
    unavailable = {
        "schema_version": "sentientos.source_revision_provenance:v2",
        "observation_status": "unavailable",
        "repository_revision": None,
        "worktree_clean": None,
        "worktree_status_entry_count": None,
        "worktree_status_digest": None,
        "worktree_content_status": "unavailable",
        "worktree_content_digest": None,
        "worktree_content_digest_algorithm": None,
        "worktree_paths_retained": False,
    }
    try:
        git_environment = _source_provenance_git_environment(root)
        revision_result = subprocess.run([_SOURCE_PROVENANCE_GIT, "rev-parse", "--verify", "HEAD"],
            cwd=root, capture_output=True, env=git_environment,
            timeout=_SOURCE_PROVENANCE_COMMAND_TIMEOUT_SECONDS, check=True)
        revision_raw = revision_result.stdout
        revision = (revision_raw.decode("ascii", errors="strict").strip()
            if isinstance(revision_raw, bytes) else str(revision_raw).strip())
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) is None:
            return unavailable
        status_result = subprocess.run([_SOURCE_PROVENANCE_GIT, "status", "--porcelain=v1", "-z",
            "--untracked-files=all"], cwd=root, capture_output=True,
            env=git_environment,
            timeout=_SOURCE_PROVENANCE_COMMAND_TIMEOUT_SECONDS,
            check=True)
        status_raw = status_result.stdout
        status_bytes = (status_raw if isinstance(status_raw, bytes)
            else str(status_raw).encode("utf-8"))
        entries = [item for item in status_bytes.split(b"\0") if item]
        content_provenance = _worktree_content_fingerprint(root,
            git_environment=git_environment)
        return {
            **unavailable,
            "observation_status": "observed",
            "repository_revision": revision,
            "worktree_clean": not entries,
            "worktree_status_entry_count": len(entries),
            "worktree_status_digest": hashlib.sha256(status_bytes).hexdigest(),
            **content_provenance,
        }
    except (OSError, UnicodeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired):
        return unavailable


RUN_SOURCE_PROVENANCE = _source_provenance()


def _runtime_observation(model_digest: str) -> tuple[dict[str, Any], str]:
    request = urllib.request.Request("http://127.0.0.1:11434/api/version", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        payload = json.loads(response.read(4096).decode("utf-8"))
    observed = {"backend": "ollama-loopback",
        "version": str(payload.get("version", "unknown")),
        "model_manifest_digest": model_digest,
        "runtime_attestation": "local_observation_only"}
    return observed, runtime_digest(observed)


def _gpu_snapshot() -> dict[str, Any] | None:
    executable = shutil.which("nvidia-smi")
    telemetry_source = "nvidia-smi"
    if executable is None and Path("/usr/lib/wsl/lib/nvidia-smi").is_file():
        executable = "/usr/lib/wsl/lib/nvidia-smi"
    if executable is None:
        # WSL may expose the host utility only through Windows interop. Keep
        # these measurements explicitly host-wide; they are a gate, not
        # attribution to the SentientOS process.
        executable = shutil.which("nvidia-smi.exe")
        if executable is not None:
            telemetry_source = "nvidia-smi-windows-host"
    if executable is None:
        return None
    try:
        result = subprocess.run([executable,
            "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits"], capture_output=True, text=True,
            timeout=5, check=True)
        rows = [line.strip().split(",") for line in result.stdout.splitlines()
            if line.strip()]
        if len(rows) != 1 or len(rows[0]) != 6:
            return None
        name, total, used, free, utilization, temperature = (
            item.strip() for item in rows[0])
        total_mib, used_mib, free_mib = int(total), int(used), int(free)
        utilization_percent = int(utilization)
        temperature_celsius = float(temperature)
        if (not name or min(total_mib, used_mib, free_mib) < 0
                or total_mib <= 0 or used_mib > total_mib or free_mib > total_mib
                or not 0 <= utilization_percent <= 100
                or not 0 <= temperature_celsius <= 120
                or abs(total_mib - used_mib - free_mib) > 512):
            return None
        return {"name": name[:128], "memory_total_mib": total_mib,
            "memory_used_mib": used_mib, "memory_free_mib": free_mib,
            "gpu_utilization_percent": utilization_percent,
            "temperature_celsius": temperature_celsius,
            "sampled_at": _now(), "source": telemetry_source,
            "scope": "host_wide_invocation_boundary_sample_not_process_attributed"}
    except Exception:
        return None


_GPU_RUNTIME_RESERVE_BYTES = 2 * 1024**3
_GPU_RESIDENT_INFERENCE_RESERVE_BYTES = 1 * 1024**3
# This is an experiment-quality gate, not a system-wide resource policy. A
# history comparison should not begin while another workload is already using
# a substantial share of the GPU; WSL cannot reliably attribute Windows GPU
# clients to their owning application.
_MAX_PREINFERENCE_GPU_UTILIZATION_PERCENT = 25.0
_MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS = 82
_MAX_PREINFERENCE_GPU_ATTEMPTS = 3
_PREINFERENCE_GPU_RETRY_INTERVAL_SECONDS = 1.0
_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS = 1.0
_MAX_DURING_INFERENCE_GPU_SAMPLES = 512
_GPU_OWNER_AVAILABILITY_CONFIRMATION_ENV = (
    "SENTIENTOS_HERMES_GPU_AVAILABLE_FOR_CYCLE")


def _require_gpu_owner_availability_confirmation() -> dict[str, Any]:
    """Require a per-cycle operator confirmation before a model run is allocated.

    Telemetry measures device load, not whether the owner has reserved the GPU
    for another application. The environment value is an explicit operator
    assertion and is deliberately bound to this one-shot cycle ID.
    """
    confirmation = os.environ.get(_GPU_OWNER_AVAILABILITY_CONFIRMATION_ENV)
    if confirmation != RUN_ID:
        raise RootlessExperimentalError(
            "gpu_owner_availability_confirmation_missing_or_mismatched")
    return {
        "schema_version": "sentientos.gpu_owner_availability_confirmation:v1",
        "status": "operator_confirmed_available_for_cycle",
        "cycle_id": RUN_ID,
        "confirmation_source": "per_cycle_environment_assertion",
        "telemetry_substitutes_for_confirmation": False,
        "confirmed_at": _now(),
    }


def _model_weight_bytes(manifest_path: Path) -> int:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RootlessExperimentalError("pinned_hermes_manifest_unreadable") from exc
    layers = manifest.get("layers") if isinstance(manifest, dict) else None
    if not isinstance(layers, list):
        raise RootlessExperimentalError("pinned_hermes_model_layers_unavailable")
    weights = [item.get("size") for item in layers
        if isinstance(item, dict)
        and item.get("mediaType") == "application/vnd.ollama.image.model"]
    if (len(weights) != 1 or type(weights[0]) is not int
            or weights[0] <= 0 or weights[0] > 64 * 1024**3):
        raise RootlessExperimentalError("pinned_hermes_model_size_invalid")
    return weights[0]


def _require_gpu_headroom(snapshot: Mapping[str, Any] | None,
        model_weight_bytes: int, *, model_resident: bool = False
        ) -> Mapping[str, Any]:
    if snapshot is None or type(snapshot.get("memory_free_mib")) is not int:
        raise RootlessExperimentalError("gpu_memory_telemetry_unavailable")
    if (not isinstance(snapshot.get("temperature_celsius"), (int, float))
            or isinstance(snapshot.get("temperature_celsius"), bool)):
        raise RootlessExperimentalError("gpu_temperature_telemetry_unavailable")
    if snapshot["temperature_celsius"] > _MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS:
        raise RootlessExperimentalError("gpu_temperature_limit_exceeded")
    required_bytes = (_GPU_RESIDENT_INFERENCE_RESERVE_BYTES if model_resident
        else model_weight_bytes + _GPU_RUNTIME_RESERVE_BYTES)
    free_bytes = int(snapshot["memory_free_mib"]) * 1024**2
    if free_bytes < required_bytes:
        raise RootlessExperimentalError("gpu_memory_headroom_insufficient")
    return snapshot


def _enforcing_resource_runtime() -> tuple[ControlPlaneKernel,
        HostResourceRuntimeCoordinator]:
    # The experiment must not inherit the repository's default shadow posture.
    key = "SENTIENTOS_ENFORCEMENT_RUNTIME_GOVERNOR"
    previous = os.environ.get(key)
    os.environ[key] = "enforce"
    try:
        if resolve_policy().runtime_governor != "enforce":
            raise RootlessExperimentalError("runtime_governor_enforcement_unavailable")
        governor = RuntimeGovernor()
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=RUN_ROOT / "resource-governance" / "kernel_decisions.jsonl")
    coordinator = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=RUN_ROOT / "resource-observations")
    return kernel, coordinator


def _refresh_resource_evidence(coordinator: HostResourceRuntimeCoordinator,
        *, correlation_id: str) -> dict[str, Any]:
    evaluation = coordinator.run_cycle(correlation_id=correlation_id)
    if evaluation is None or not validate_evaluation(evaluation).ok:
        raise RootlessExperimentalError("host_resource_evidence_unavailable")
    snapshot = evaluation.snapshot
    if snapshot.cpu_utilization_percent is None or snapshot.ram_utilization_percent is None:
        raise RootlessExperimentalError("host_resource_evidence_incomplete")
    if type(snapshot.disk_free_bytes) is not int or snapshot.disk_free_bytes < 0:
        raise RootlessExperimentalError("host_disk_evidence_incomplete")
    if snapshot.disk_free_bytes < _MIN_EXPERIMENT_DISK_FREE_BYTES:
        raise RootlessExperimentalError("host_disk_headroom_insufficient")
    return {"evaluation_id": evaluation.evaluation_id,
        "observed_at": evaluation.epoch.observed_at,
        "pressure_labels": list(evaluation.pressure_report.pressure_labels),
        "cpu_utilization_percent": snapshot.cpu_utilization_percent,
        "ram_utilization_percent": snapshot.ram_utilization_percent,
        "disk_free_bytes": snapshot.disk_free_bytes,
        "disk_utilization_percent": snapshot.disk_utilization_percent,
        "gpu_utilization_percent": snapshot.gpu_utilization_percent,
        "vram_utilization_percent": snapshot.vram_utilization_percent}


class _ResourceGuardedInvoker:
    """Refresh host evidence and VRAM headroom before every governed inference."""

    def __init__(self, delegate: Any, coordinator: HostResourceRuntimeCoordinator,
            model_weight_bytes: int,
            evidence_records: list[dict[str, Any]] | None = None,
            model_name: str | None = None, gpu_layers: int = GPU_LAYERS) -> None:
        self._delegate = delegate
        self._coordinator = coordinator
        self._model_weight_bytes = model_weight_bytes
        self._evidence_records = evidence_records if evidence_records is not None else []
        self._model_name = model_name
        self._gpu_layers = gpu_layers
        self._sequence = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def invoke(self, request: Any, **kwargs: Any) -> Any:
        self._sequence += 1
        resource_record: dict[str, Any] = {
            "inference_sequence": self._sequence,
            "gpu_layers_requested": self._gpu_layers,
            "gate_status": "blocked",
        }

        preflight_samples: list[dict[str, Any]] = []

        def blocked(reason: str) -> NoReturn:
            resource_record["gate_reason"] = reason
            resource_record["preinference_gpu_samples"] = list(preflight_samples)
            self._evidence_records.append(dict(resource_record))
            raise RootlessExperimentalError(reason)

        fresh_resource: dict[str, Any] | None = None
        gpu_snapshot: Mapping[str, Any] | None = None
        for attempt in range(1, _MAX_PREINFERENCE_GPU_ATTEMPTS + 1):
            try:
                fresh_resource = _refresh_resource_evidence(self._coordinator,
                    correlation_id=f"{RUN_ID}-inference-{self._sequence}-preflight-{attempt}")
            except Exception as exc:
                resource_record["gate_reason"] = _failure_code(exc)
                resource_record["preinference_gpu_samples"] = preflight_samples
                self._evidence_records.append(dict(resource_record))
                raise
            gpu_sample = _gpu_snapshot()
            host_util = fresh_resource.get("gpu_utilization_percent")
            direct_util = (gpu_sample.get("gpu_utilization_percent")
                if isinstance(gpu_sample, Mapping) else None)
            preflight_samples.append({
                "attempt": attempt,
                "host_gpu_utilization_percent": host_util,
                "direct_gpu_utilization_percent": direct_util,
                "memory_free_mib": (gpu_sample.get("memory_free_mib")
                    if isinstance(gpu_sample, Mapping) else None),
                "temperature_celsius": (gpu_sample.get("temperature_celsius")
                    if isinstance(gpu_sample, Mapping) else None),
                "sampled_at": (gpu_sample.get("sampled_at")
                    if isinstance(gpu_sample, Mapping) else None),
                "source": (gpu_sample.get("source")
                    if isinstance(gpu_sample, Mapping) else None),
            })
            if not isinstance(gpu_sample, Mapping):
                blocked("gpu_utilization_telemetry_unavailable")
            gpu_snapshot = gpu_sample
            resource_record["gpu_memory_free_mib"] = gpu_sample.get("memory_free_mib")
            resource_record["gpu_memory_total_mib"] = gpu_sample.get("memory_total_mib")
            resource_record["nvidia_smi_gpu_utilization_percent"] = direct_util
            resource_record["gpu_sampled_at"] = gpu_sample.get("sampled_at")
            resource_record["gpu_utilization_sample_source"] = gpu_sample.get("source")
            resource_record["gpu_utilization_sample_scope"] = gpu_sample.get("scope")
            if (not isinstance(gpu_sample.get("temperature_celsius"), (int, float))
                    or isinstance(gpu_sample.get("temperature_celsius"), bool)):
                blocked("gpu_temperature_telemetry_unavailable")
            resource_record["gpu_temperature_celsius"] = gpu_sample["temperature_celsius"]
            resource_record["gpu_temperature_limit_celsius"] = (
                _MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS)
            if gpu_sample["temperature_celsius"] > _MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS:
                blocked("gpu_temperature_limit_exceeded")
            if (host_util is not None
                    and (not isinstance(host_util, (int, float))
                        or isinstance(host_util, bool)
                        or not 0 <= host_util <= 100)):
                blocked("host_gpu_utilization_telemetry_invalid")
            if (type(direct_util) is not int or not 0 <= direct_util <= 100):
                blocked("gpu_utilization_telemetry_unavailable")
            resource_record["host_gpu_utilization_telemetry_missing"] = (
                host_util is None)
            effective_gpu_util = max(
                float(host_util) if host_util is not None else 0.0,
                float(direct_util))
            preflight_samples[-1]["effective_gpu_utilization_percent"] = effective_gpu_util
            if effective_gpu_util <= _MAX_PREINFERENCE_GPU_UTILIZATION_PERCENT:
                break
            if attempt < _MAX_PREINFERENCE_GPU_ATTEMPTS:
                time.sleep(_PREINFERENCE_GPU_RETRY_INTERVAL_SECONDS)
        else:
            resource_record["preinference_gpu_samples"] = preflight_samples
            blocked("gpu_utilization_preflight_busy")

        assert fresh_resource is not None and gpu_snapshot is not None
        resource_record.update(fresh_resource)
        resource_record["preinference_gpu_samples"] = preflight_samples
        resource_record["gpu_memory_free_mib"] = gpu_snapshot.get("memory_free_mib")
        resource_record["gpu_memory_total_mib"] = gpu_snapshot.get("memory_total_mib")
        resource_record["gpu_memory_sample_source"] = gpu_snapshot.get("source")
        resource_record["gpu_memory_sample_scope"] = gpu_snapshot.get("scope")
        resource_record["nvidia_smi_gpu_utilization_percent"] = (
            gpu_snapshot.get("gpu_utilization_percent"))
        resource_record["gpu_sampled_at"] = gpu_snapshot.get("sampled_at")
        resource_record["gpu_utilization_sample_source"] = gpu_snapshot.get("source")
        resource_record["gpu_utilization_sample_scope"] = gpu_snapshot.get("scope")
        model_resident = False
        if self._model_name is not None:
            observed_residency = _model_residency_observed(self._model_name)
            if observed_residency is None:
                blocked("model_residency_telemetry_unavailable")
            model_resident = observed_residency
        resource_record["model_resident_at_preflight"] = model_resident
        try:
            gpu = _require_gpu_headroom(gpu_snapshot, self._model_weight_bytes,
                model_resident=model_resident)
        except RootlessExperimentalError as exc:
            blocked(_failure_code(exc))
        resource_record["gpu_memory_free_mib"] = gpu["memory_free_mib"]
        resource_record["gpu_memory_total_mib"] = gpu["memory_total_mib"]
        resource_record["required_gpu_headroom_bytes"] = (
            _GPU_RESIDENT_INFERENCE_RESERVE_BYTES if model_resident
            else self._model_weight_bytes + _GPU_RUNTIME_RESERVE_BYTES)
        resource_record["preinference_gpu_utilization_limit_percent"] = (
            _MAX_PREINFERENCE_GPU_UTILIZATION_PERCENT)
        resource_record["effective_preinference_gpu_utilization_percent"] = (
            max(float(fresh_resource["gpu_utilization_percent"])
                if isinstance(fresh_resource.get("gpu_utilization_percent"), (int, float))
                    and not isinstance(fresh_resource.get("gpu_utilization_percent"), bool)
                else 0.0,
                float(gpu_snapshot["gpu_utilization_percent"])))
        resource_record["gate_status"] = "passed"
        evidence_index = len(self._evidence_records)
        self._evidence_records.append(dict(resource_record))
        resource_record["invocation_started_at"] = _now()
        stop_sampling = threading.Event()
        during_samples: list[dict[str, Any]] = []
        model_placement_samples: list[dict[str, Any]] = []
        sample_failures = 0
        sample_attempts = 0
        model_placement_failures = 0
        thermal_hot_streak = 0
        low_memory_streak = 0
        cpu_fallback_detected = threading.Event()
        model_stop_attempted = threading.Event()
        model_stop_result: dict[str, Any] | None = None

        def sample_during_inference() -> None:
            nonlocal sample_attempts, sample_failures, model_placement_failures
            nonlocal thermal_hot_streak, low_memory_streak, model_stop_result
            while sample_attempts < _MAX_DURING_INFERENCE_GPU_SAMPLES:
                if stop_sampling.wait(_INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS):
                    return
                sample_attempts += 1
                if self._model_name is not None:
                    placement = _model_gpu_placement_observed(self._model_name)
                    if placement is None:
                        model_placement_failures += 1
                    else:
                        if len(model_placement_samples) < _MAX_DURING_INFERENCE_GPU_SAMPLES:
                            model_placement_samples.append(dict(placement))
                        if placement.get("status") == "cpu_only":
                            cpu_fallback_detected.set()
                            if not model_stop_attempted.is_set():
                                model_stop_attempted.set()
                                model_stop_result = _stop_ollama_model(self._model_name)
                            return
                try:
                    sample = _gpu_snapshot()
                except Exception:
                    sample = None
                if not isinstance(sample, Mapping):
                    sample_failures += 1
                    continue
                temperature = sample.get("temperature_celsius")
                if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
                    sample_failures += 1
                elif temperature > _MAX_EXPERIMENT_GPU_TEMPERATURE_CELSIUS:
                    thermal_hot_streak += 1
                else:
                    thermal_hot_streak = 0
                free_mib = sample.get("memory_free_mib")
                if type(free_mib) is not int:
                    sample_failures += 1
                elif free_mib < _GPU_RESIDENT_INFERENCE_RESERVE_BYTES // 1024**2:
                    low_memory_streak += 1
                else:
                    low_memory_streak = 0
                if len(during_samples) < _MAX_DURING_INFERENCE_GPU_SAMPLES:
                    during_samples.append(dict(sample))
                else:
                    sample_failures += 1

        sampler = threading.Thread(
            target=sample_during_inference,
            name="sentientos-inference-gpu-sampler",
            daemon=True)
        sampler.start()
        result: Any = None
        invocation_error: BaseException | None = None
        try:
            result = self._delegate.invoke(request, **kwargs)
        except BaseException as exc:
            invocation_error = exc
        finally:
            stop_sampling.set()
            # Placement requests can take 5 seconds and the scoped model stop can
            # take 10. Wait for both bounded operations before sealing evidence.
            sampler.join(timeout=16.0)
            final_placement = (_model_gpu_placement_observed(self._model_name)
                if self._model_name is not None else None)
            if final_placement is not None:
                if len(model_placement_samples) < _MAX_DURING_INFERENCE_GPU_SAMPLES:
                    model_placement_samples.append(dict(final_placement))
                if (self._model_name is not None
                        and final_placement.get("status") == "cpu_only"):
                    cpu_fallback_detected.set()
                    if not model_stop_attempted.is_set():
                        model_stop_attempted.set()
                        model_stop_result = _stop_ollama_model(self._model_name)
            resource_record["invocation_finished_at"] = _now()
            resource_record["during_inference_gpu_samples"] = list(during_samples)
            resource_record["during_inference_model_placement_samples"] = list(
                model_placement_samples)
            resource_record["model_placement_sample_failures"] = (
                model_placement_failures)
            resource_record["model_stop_attempted"] = model_stop_attempted.is_set()
            if model_stop_result is not None:
                resource_record["model_stop_result"] = dict(model_stop_result)
            resource_record["model_gpu_placement_status"] = (
                "cpu_fallback_detected" if cpu_fallback_detected.is_set()
                else "gpu_offload_observed" if any(
                    item.get("status") == "gpu_offloaded"
                    for item in model_placement_samples)
                else "unverified" if self._model_name is not None
                else "not_required")
            resource_record["during_inference_gpu_sample_failures_or_omissions"] = (
                sample_failures)
            resource_record["during_inference_gpu_sample_attempt_count"] = (
                sample_attempts)
            resource_record["during_inference_gpu_sampling_interval_seconds"] = (
                _INFERENCE_GPU_SAMPLE_INTERVAL_SECONDS)
            resource_record["during_inference_gpu_sampling_status"] = (
                "sampler_join_timeout" if sampler.is_alive()
                else "sampling_window_exhausted"
                    if sample_attempts >= _MAX_DURING_INFERENCE_GPU_SAMPLES
                else "sampled" if during_samples
                else "no_intermediate_sample")
            resource_record["post_inference_gpu_sample"] = _gpu_snapshot()
            resource_record["thermal_abort_after_call"] = thermal_hot_streak >= 2
            resource_record["thermal_hot_sample_streak"] = thermal_hot_streak
            resource_record["low_memory_abort_after_call"] = low_memory_streak >= 2
            resource_record["low_memory_sample_streak"] = low_memory_streak
            self._evidence_records[evidence_index] = dict(resource_record)
            if thermal_hot_streak >= 2:
                raise RootlessExperimentalError("gpu_temperature_limit_sustained")
            if low_memory_streak >= 2:
                raise RootlessExperimentalError("gpu_memory_headroom_lost_during_inference")
            if cpu_fallback_detected.is_set():
                failure = RootlessExperimentalError("gpu_model_cpu_fallback")
                if invocation_error is not None:
                    raise failure from invocation_error
                raise failure
            if (self._model_name is not None
                    and not any(item.get("status") == "gpu_offloaded"
                        for item in model_placement_samples)):
                failure = RootlessExperimentalError("gpu_model_placement_unverified")
                if invocation_error is not None:
                    raise invocation_error
                raise failure
        if invocation_error is not None:
            raise invocation_error
        return result


def _model_residency_observed(model_name: str) -> bool | None:
    request = urllib.request.Request("http://127.0.0.1:11434/api/ps", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as response:
            payload = json.loads(response.read(65_536).decode("utf-8"))
    except Exception:
        return None
    models = payload.get("models") if isinstance(payload, dict) else None
    if (not isinstance(models, list) or len(models) > 64
            or any(not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or len(item["name"]) > 128 for item in models)):
        return None
    return any(item["name"] == model_name for item in models)


def _model_gpu_placement_observed(model_name: str) -> dict[str, Any] | None:
    """Read exact Ollama API placement for one already-loaded model."""
    request = urllib.request.Request("http://127.0.0.1:11434/api/ps", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as response:
            payload = json.loads(response.read(65_536).decode("utf-8"))
    except Exception:
        return None
    models = payload.get("models") if isinstance(payload, dict) else None
    if (not isinstance(models, list) or len(models) > 64
            or any(not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or len(item["name"]) > 128 for item in models)):
        return None
    model = next((item for item in models if item["name"] == model_name), None)
    if model is None:
        return {"status": "not_resident", "model_name": model_name}
    size = model.get("size")
    size_vram = model.get("size_vram")
    if (type(size) is not int or size <= 0
            or type(size_vram) is not int or not 0 <= size_vram <= size):
        return None
    return {"status": "cpu_only" if size_vram == 0 else "gpu_offloaded",
        "model_name": model_name, "size_bytes": size,
        "size_vram_bytes": size_vram}


def _stop_ollama_model(model_name: str) -> dict[str, Any]:
    """Stop only the experiment's exact target model after CPU fallback."""
    executable = shutil.which("ollama")
    if executable is None:
        return {"status": "ollama_cli_unavailable"}
    try:
        completed = subprocess.run([executable, "stop", model_name], check=False,
            capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return {"status": "stop_failed"}
    return {"status": "stop_requested" if completed.returncode == 0
        else "stop_failed", "return_code": int(completed.returncode)}


def _verify_model_released(model_name: str, *, timeout_seconds: float = 20.0
        ) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    checks = 0
    while True:
        resident = _model_residency_observed(model_name)
        checks += 1
        if resident is None:
            return {"status": "residency_observation_unavailable", "checks": checks}
        if not resident:
            return {"status": "target_model_not_resident", "checks": checks}
        if time.monotonic() >= deadline:
            return {"status": "target_model_still_resident", "checks": checks}
        time.sleep(0.5)


def _bounded_failure_code(exc: Exception) -> str | None:
    """Extract a safe validator code without retaining dynamic error detail."""
    for attribute in ("code", "reason_code", "reason"):
        value = getattr(exc, attribute, None)
        if isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,120}", value):
            return value
    message = str(exc).strip()
    if re.fullmatch(r"[a-z0-9_]{1,120}", message):
        return message
    if isinstance(exc, EmbodiedConsequenceError):
        prefix = message.partition(":")[0]
        if re.fullmatch(r"[a-z0-9_]{1,120}", prefix):
            return prefix
    return None


def _failure_code(exc: Exception) -> str:
    code = _bounded_failure_code(exc)
    if code is not None:
        return code
    return type(exc).__name__


def _failure_cause_code(exc: Exception) -> str | None:
    """Return only a bounded machine code from a short nested cause chain."""
    cause = exc.__cause__ or exc.__context__
    for _ in range(8):
        if cause is None:
            return None
        code = _bounded_failure_code(cause)
        if code is not None:
            return code
        cause = cause.__cause__ or cause.__context__
    return None


def _bounded_python_failure_diagnostic(exc: Exception) -> dict[str, Any] | None:
    """Keep actionable NameError location metadata without exception text."""
    if not isinstance(exc, NameError):
        return None
    missing_name = getattr(exc, "name", None)
    if (not isinstance(missing_name, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", missing_name) is None):
        missing_name = None
    traceback_node = exc.__traceback__
    while traceback_node is not None and traceback_node.tb_next is not None:
        traceback_node = traceback_node.tb_next
    frame = traceback_node.tb_frame if traceback_node is not None else None
    module_name = frame.f_globals.get("__name__") if frame is not None else None
    function_name = frame.f_code.co_name if frame is not None else None
    line_number = traceback_node.tb_lineno if traceback_node is not None else None
    if (not isinstance(module_name, str)
            or re.fullmatch(r"[A-Za-z0-9_.]{1,200}", module_name) is None):
        module_name = None
    if (not isinstance(function_name, str)
            or re.fullmatch(r"[A-Za-z0-9_<>.]{1,128}", function_name) is None):
        function_name = None
    if type(line_number) is not int or line_number < 1:
        line_number = None
    return {
        "schema_version": "sentientos.rootless_python_failure_diagnostic:v1",
        "failure_kind": "name_resolution_failure",
        "unresolved_identifier": missing_name,
        "module": module_name,
        "function": function_name,
        "line": line_number,
        "exception_message_included": False,
        "source_line_included": False,
        "authority": False,
    }


def _bounded_task_score_lineage_failure_diagnostic(
        exc: Exception) -> dict[str, Any] | None:
    """Recover only the categorical lineage diagnostic through wrapped errors."""
    allowed_checks = {
        "lineage_field_shape_invalid",
        "score_schema_unsupported",
        "evaluator_unrecognized",
        "task_digest_mismatch",
        "output_digest_mismatch",
        "lineage_digest_format_invalid",
        "output_digest_format_invalid",
    }
    cause: BaseException | None = exc
    for _ in range(8):
        if cause is None:
            return None
        diagnostic = getattr(cause, "diagnostic", None)
        if (isinstance(diagnostic, Mapping)
                and diagnostic.get("schema_version")
                    == "sentientos.developmental_history_task_score_lineage_failure:v1"):
            failed_checks = diagnostic.get("failed_checks")
            if (not isinstance(failed_checks, (list, tuple))
                    or not failed_checks or len(failed_checks) > len(allowed_checks)
                    or any(not isinstance(item, str) or item not in allowed_checks
                        for item in failed_checks)
                    or len(set(failed_checks)) != len(failed_checks)):
                return None
            return {
                "schema_version": (
                    "sentientos.developmental_history_task_score_lineage_failure:v1"),
                "failed_checks": list(failed_checks),
            }
        cause = cause.__cause__ or cause.__context__
    return None


def _incomplete_task_family_prompt_projection_evidence(
        request: Any) -> dict[str, Any] | None:
    """Summarize receipt-local prompt binding without claiming full verification."""
    if not isinstance(request, Mapping):
        return None
    upstream = request.get("upstream_evidence")
    projection = (upstream.get("task_family_history_prompt_projection")
        if isinstance(upstream, Mapping) else None)
    if not isinstance(upstream, Mapping) or not isinstance(projection, Mapping):
        return None
    projection_semantic = dict(projection)
    projection_digest = projection_semantic.pop("projection_digest", None)
    request_prompt_digest = request.get("prompt_digest")
    projection_digest_valid = (isinstance(projection_digest, str)
        and projection_digest == "sha256:" + digest_payload(projection_semantic))
    prompt_digest_bound = (isinstance(request_prompt_digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", request_prompt_digest) is not None
        and request_prompt_digest == projection.get("governed_request_prompt_digest")
        and projection.get("prompt_binding_posture")
            == "exact_governed_request_prompt_digest")
    condition_id = projection.get("condition_id")
    expected_treatment = ("withheld" if condition_id == "history_withheld"
        else "present" if isinstance(condition_id, str) and condition_id in {
            "history_present", "history_restored"} else None)
    records = projection.get("records")
    records_valid = (isinstance(records, list) and len(records) <= 256
        and all(isinstance(row, Mapping)
            and isinstance(row.get("record_id"), str)
            and 1 <= len(row["record_id"]) <= 256
            and isinstance(row.get("record_digest"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", row["record_digest"])
                is not None
            and type(row.get("example_count")) is int
            and row["example_count"] >= 0
            and isinstance(row.get("prompt_packet_digest"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}",
                row["prompt_packet_digest"]) is not None
            and row.get("prompt_packet_serialization_present") is True
            for row in records))
    if records_valid:
        records_valid = len({row["record_id"] for row in records}) == len(records)
        records_valid = (records_valid
            and type(projection.get("selected_record_count")) is int
            and projection["selected_record_count"] >= 0
            and type(projection.get("task_relevant_record_count")) is int
            and projection["task_relevant_record_count"] == len(records)
            and type(projection.get("task_relevant_example_count")) is int
            and projection["task_relevant_example_count"] == sum(
                row["example_count"] for row in records))
    if not records_valid:
        records = []
    selection = upstream.get("developmental_history_selection")
    selection_semantic = (dict(selection) if isinstance(selection, Mapping) else {})
    selection_digest = selection_semantic.pop("selection_digest", None)
    selection_digest_valid = (isinstance(selection_digest, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", selection_digest) is not None
        and selection_digest == "sha256:" + digest_payload(selection_semantic))
    selected = (selection.get("selected_records")
        if isinstance(selection, Mapping) else None)
    selected_refs_valid = (isinstance(selected, (list, tuple))
        and len(selected) <= 256
        and all(isinstance(row, Mapping)
            and set(row) == {"record_id", "record_digest"}
            and isinstance(row.get("record_id"), str)
            and 1 <= len(row["record_id"]) <= 256
            and isinstance(row.get("record_digest"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", row["record_digest"])
                is not None
            for row in selected)
        and isinstance(upstream.get("record_ids"), list)
        and isinstance(upstream.get("record_digests"), list)
        and len(upstream["record_ids"]) <= 256
        and len(upstream["record_digests"]) <= 256
        and all(isinstance(record_id, str)
            for record_id in upstream["record_ids"])
        and all(isinstance(record_digest, str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", record_digest) is not None
            for record_digest in upstream["record_digests"])
        and len({row["record_id"] for row in selected}) == len(selected)
        and [row["record_id"] for row in selected] == upstream["record_ids"]
        and [row["record_digest"] for row in selected]
            == upstream["record_digests"])
    selected_ref_pairs = ({(row.get("record_id"), row.get("record_digest"))
        for row in selected if isinstance(row, Mapping)
            and isinstance(row.get("record_id"), str)
            and isinstance(row.get("record_digest"), str)}
        if isinstance(selected, (list, tuple)) else set())
    projection_refs_selected = (records_valid and all(
        (row["record_id"], row["record_digest"]) in selected_ref_pairs
        for row in records))
    treatment_matches = (expected_treatment is not None
        and projection.get("treatment") == expected_treatment)
    projection_contract_matches = (
        projection.get("schema_version") in {
            f"sentientos.task_family_history_prompt_projection:v{version}"
            for version in range(19, 36)}
        and projection.get("prompt_packet_binding_posture")
            == "canonical_selected_record_packet_substring_in_exact_prompt:v1"
        and projection.get("task_family_id") in
            _SUPPORTED_OBJECTIVE_TRANSFER_TASK_FAMILIES)
    selected_count_matches = (isinstance(upstream.get("record_ids"), list)
        and type(projection.get("selected_record_count")) is int
        and projection["selected_record_count"] == len(upstream["record_ids"]))
    withheld_policy_matches = (condition_id != "history_withheld"
        or (records_valid and not records
            and projection.get("task_relevant_example_count") == 0))
    binding_consistent = all((projection_digest_valid, prompt_digest_bound,
        selection_digest_valid, selected_refs_valid, projection_refs_selected,
        treatment_matches, records_valid, projection_contract_matches,
        selected_count_matches, withheld_policy_matches))
    safe_condition_id = (condition_id if isinstance(condition_id, str)
        and condition_id in {
        "history_present", "history_withheld", "history_restored"} else None)
    return {
        "schema_version": "sentientos.incomplete_task_family_prompt_projection_evidence:v2",
        "status": ("receipt_local_projection_binding_consistent"
            if binding_consistent else "receipt_local_projection_binding_inconsistent"),
        "condition_id": safe_condition_id,
        "treatment": (projection.get("treatment")
            if isinstance(projection.get("treatment"), str)
                and projection.get("treatment") in {"present", "withheld"}
            else None),
        "task_family_id": (projection.get("task_family_id")
            if isinstance(projection.get("task_family_id"), str)
                and len(projection["task_family_id"]) <= 96 else None),
        "projection_digest": (projection_digest
            if isinstance(projection_digest, str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}", projection_digest)
                    is not None else None),
        "projection_digest_recomputed": projection_digest_valid,
        "request_prompt_digest": (request_prompt_digest
            if isinstance(request_prompt_digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", request_prompt_digest)
                    is not None else None),
        "request_prompt_digest_matches_projection": prompt_digest_bound,
        "history_selection_digest": (selection_digest
            if isinstance(selection_digest, str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}", selection_digest)
                    is not None else None),
        "history_selection_digest_recomputed": selection_digest_valid,
        "selection_refs_match_request_inventory": selected_refs_valid,
        "projection_refs_are_selected_history": projection_refs_selected,
        "expected_treatment_matches_condition": treatment_matches,
        "registered_projection_contract_matches": projection_contract_matches,
        "exact_task_family_packets_present_in_prompt": (records_valid
            and projection.get("prompt_packet_binding_posture")
                == "canonical_selected_record_packet_substring_in_exact_prompt:v1"),
        "selected_count_matches_request_inventory": selected_count_matches,
        "withheld_treatment_has_no_projected_examples": withheld_policy_matches,
        "records_well_formed": records_valid,
        "selected_record_count": (projection.get("selected_record_count")
            if type(projection.get("selected_record_count")) is int
                and projection["selected_record_count"] >= 0 else None),
        "task_relevant_record_count": (projection.get("task_relevant_record_count")
            if type(projection.get("task_relevant_record_count")) is int
                and projection["task_relevant_record_count"] >= 0 else None),
        "task_relevant_example_count": (projection.get("task_relevant_example_count")
            if type(projection.get("task_relevant_example_count")) is int
                and projection["task_relevant_example_count"] >= 0 else None),
        "task_relevant_record_refs": ([{"record_id": row["record_id"],
            "record_digest": row["record_digest"],
            "prompt_packet_digest": row["prompt_packet_digest"],
            "prompt_packet_serialization_present": True} for row in records]
            if records_valid else []),
        "raw_prompt_and_answer_values_included": False,
        "governed_receipt_verification_performed": False,
        "scope": "receipt_file_projection_binding_observation_not_receipt_verification_or_model_attention",
    }


def _persist_incomplete_run(exc: Exception) -> Path | None:
    """Record a bounded failure summary without copying prompts or model text."""
    global RUN_SOURCE_PROVENANCE_AT_END
    if not RUN_ROOT.is_dir() or RUN_ROOT.is_symlink():
        return None
    RUN_SOURCE_PROVENANCE_AT_END = _source_provenance()
    receipts: list[dict[str, Any]] = []
    receipt_root = RUN_ROOT / "inference-custody" / "receipts"
    if receipt_root.is_dir() and not receipt_root.is_symlink():
        for path in sorted(receipt_root.glob("lmrec-*.json")):
            if path.is_symlink():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            request = payload.get("request") if isinstance(payload, dict) else None
            output_text = payload.get("output_text") if isinstance(payload, dict) else None
            decoded = None
            if isinstance(output_text, str) and len(output_text) <= 4000:
                try:
                    decoded = json.loads(output_text)
                except json.JSONDecodeError:
                    decoded = None
            upstream = request.get("upstream_evidence") if isinstance(request, dict) else None
            preregistration_digest = _request_preregistration_digest(request)
            retrieved_record_ids = (upstream.get("record_ids", [])
                if isinstance(upstream, dict) else [])
            cited_record_ids = (decoded.get("history_record_ids", [])
                if isinstance(decoded, dict) else [])
            citation_is_bound = (isinstance(cited_record_ids, list)
                and bool(cited_record_ids)
                and all(isinstance(item, str) for item in cited_record_ids)
                and isinstance(retrieved_record_ids, list)
                and all(isinstance(item, str) for item in retrieved_record_ids)
                and set(cited_record_ids).issubset(retrieved_record_ids))
            response_value = (decoded.get("response")
                if isinstance(decoded, dict) else None)
            response_text = (response_value.strip().lower()
                if isinstance(response_value, str) else "")
            pre_action_correlation = (
                "companion-interaction-" + hashlib.sha256(
                    (RUN_ID + ":pre-action-decision").encode("utf-8")).hexdigest()[:32]
                + ":resident_developmental_cognition:companion-interaction")
            is_pre_action_decision = (isinstance(request, dict)
                and request.get("correlation_id") == pre_action_correlation)
            pose_decision = (_pose_decision_from_response(response_value)
                if is_pre_action_decision and isinstance(response_value, str) else None)
            if not is_pre_action_decision:
                pre_action_decision_classification = None
            elif pose_decision is None and payload.get("output_digest") is None:
                pre_action_decision_classification = "no_completed_model_output"
            elif pose_decision is None:
                pre_action_decision_classification = "completed_output_not_validated"
            elif pose_decision["predicted_pose"] != pose_decision["requested_pose"]:
                pre_action_decision_classification = "prediction_inconsistent_with_fixture"
            elif pose_decision["requested_pose"] != "reach":
                pre_action_decision_classification = "exact_pair_goal_not_met"
            else:
                pre_action_decision_classification = "exact_pair_goal_met"
            try:
                prompt_projection_evidence = (
                    _incomplete_task_family_prompt_projection_evidence(request))
            except Exception:
                # Failure-reporting must survive a malformed receipt projection;
                # preserve the original run error and record this audit as unavailable.
                prompt_projection_evidence = {
                    "schema_version": (
                        "sentientos.incomplete_task_family_prompt_projection_evidence:v2"),
                    "status": "receipt_local_projection_audit_unavailable",
                    "raw_prompt_and_answer_values_included": False,
                    "governed_receipt_verification_performed": False,
                }
            receipts.append({
                "receipt_id": payload.get("receipt_id"),
                "receipt_digest": payload.get("receipt_digest"),
                "purpose": payload.get("purpose"),
                "correlation_id": request.get("correlation_id")
                    if isinstance(request, dict) else None,
                "run_preregistration_digest": preregistration_digest,
                "output_digest": payload.get("output_digest"),
                "task_family_prompt_projection_evidence": prompt_projection_evidence,
                "reason_codes": payload.get("reason_codes", []),
                "disposition": decoded.get("disposition")
                    if isinstance(decoded, dict) else None,
                "evidence_ids": decoded.get("evidence_ids", [])
                    if isinstance(decoded, dict) else [],
                "history_record_ids": decoded.get("history_record_ids", [])
                    if isinstance(decoded, dict) else [],
                "history_citation_classification": (
                    "bound_to_retrieved_record" if citation_is_bound else
                    "unbound_or_absent" if cited_record_ids else "not_present"),
                "response_classification": (
                    "exact_idle_value_with_bound_history"
                    if response_text == "idle" and citation_is_bound else
                    "target_value_idle_with_bound_history"
                    if "idle" in response_text and citation_is_bound else
                    "other_or_unvalidated"),
                "model_output_text_excluded": True,
                "pre_action_decision_classification": pre_action_decision_classification,
                "pre_action_requested_pose": (pose_decision["requested_pose"]
                    if pose_decision is not None else None),
                "pre_action_predicted_pose": (pose_decision["predicted_pose"]
                    if pose_decision is not None else None),
                "pre_action_prediction_consistent": (
                    pose_decision["predicted_pose"] == pose_decision["requested_pose"]
                    if pose_decision is not None else None),
            })
    records: list[dict[str, Any]] = []
    record_root = RUN_ROOT / "resident-cognition" / "history" / "records"
    if record_root.is_dir() and not record_root.is_symlink():
        for path in sorted(record_root.glob("*.json")):
            if path.is_symlink():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append({"record_id": payload.get("record_id"),
                    "record_digest": payload.get("record_digest"),
                    "current_truth": payload.get("current_truth"),
                    "authority": payload.get("authority")})
    hosted_deliveries: list[dict[str, Any]] = []
    conversation_root = RUN_ROOT / "hosted-chat" / "conversations"
    if conversation_root.is_dir() and not conversation_root.is_symlink():
        for path in sorted(conversation_root.glob("*.json")):
            if path.is_symlink():
                continue
            try:
                conversation = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            turns = conversation.get("turns", []) if isinstance(conversation, dict) else []
            if not isinstance(turns, list):
                continue
            for turn in turns:
                if not isinstance(turn, dict) or turn.get("role") != "assistant":
                    continue
                linkage = turn.get("linkage")
                if (not isinstance(linkage, dict)
                        or linkage.get("response_origin")
                            != "resident_developmental_cognition"):
                    continue
                retrieved = linkage.get("cognition_prior_record_ids", [])
                cited = linkage.get("cognition_history_record_ids", [])
                citation_bound = (isinstance(retrieved, list)
                    and isinstance(cited, list)
                    and all(isinstance(item, str) for item in retrieved + cited)
                    and bool(cited) and set(cited).issubset(retrieved))
                response = turn.get("text", "")
                normalized_response = response.casefold() if isinstance(response, str) else ""
                target_value = (
                    "observer_reported_idle_with_bound_history"
                    if citation_bound and "idle" in normalized_response
                        and "reported_values.observer_report_field.pose"
                            in normalized_response else
                    "other_or_unvalidated")
                hosted_deliveries.append({
                    "assistant_turn_id": turn.get("turn_id"),
                    "response_origin": linkage.get("response_origin"),
                    "cognition_observation_id": linkage.get("cognition_observation_id"),
                    "inference_receipt_id": linkage.get("inference_receipt_id"),
                    "inference_receipt_digest": linkage.get("inference_receipt_digest"),
                    "response_digest": linkage.get("response_digest"),
                    "retrieved_record_ids": retrieved if isinstance(retrieved, list) else [],
                    "history_record_ids": cited if isinstance(cited, list) else [],
                    "history_citation_bound": citation_bound,
                    "target_value_classification": target_value,
                    "raw_question_and_response_excluded": True,
                })
    failure_diagnostic = _bounded_task_score_lineage_failure_diagnostic(exc)
    if not isinstance(failure_diagnostic, Mapping):
        failure_diagnostic = getattr(exc, "diagnostic", None)
    if (not isinstance(failure_diagnostic, Mapping)
            and isinstance(RUN_FAILURE_DIAGNOSTIC, Mapping)):
        failure_diagnostic = dict(RUN_FAILURE_DIAGNOSTIC)
    if not isinstance(failure_diagnostic, Mapping):
        failure_diagnostic = _bounded_python_failure_diagnostic(exc)
    try:
        runtime_admission_ledger = _runtime_admission_ledger_boundary(
            RUN_ROOT / "resident-cognition" / "state" / "runtime_admissions.json")
    except (OSError, ValueError, RuntimeError, RootlessExperimentalError):
        runtime_admission_ledger = None
    try:
        from work.rootless_history_boundary_campaign import (
            _cognition_recovery_state_boundary)
        cognition_recovery_state_boundary = _cognition_recovery_state_boundary(
            RUN_ROOT / "resident-cognition" / "state")
    except (OSError, ValueError, RuntimeError, RootlessExperimentalError):
        cognition_recovery_state_boundary = None
    artifact = {
        "schema_version": "sentientos.rootless_ollama_embodied_cognition_failure:v9",
        "run_id": RUN_ID,
        "status": "incomplete",
        "execution_posture": "rootless_experimental_nonproduction",
        "source_provenance": dict(RUN_SOURCE_PROVENANCE),
        "source_provenance_at_failure": dict(RUN_SOURCE_PROVENANCE_AT_END),
        "source_provenance_stable_for_run": (
            RUN_SOURCE_PROVENANCE_AT_END == RUN_SOURCE_PROVENANCE),
        "source_provenance_fingerprint_complete": (
            RUN_SOURCE_PROVENANCE.get("observation_status") == "observed"
            and RUN_SOURCE_PROVENANCE.get("worktree_content_status") == "complete"
            and isinstance(RUN_SOURCE_PROVENANCE.get(
                "worktree_content_digest"), str)),
        "model_id": MODEL_NAME,
        "model_manifest_digest": MANIFEST_PATH.stem,
        "gpu_layers_requested": GPU_LAYERS,
        "prior_developmental_history_seed": dict(HISTORY_SEED_EVIDENCE),
        "runtime_admission_ledger": runtime_admission_ledger,
        "cognition_recovery_state_boundary": cognition_recovery_state_boundary,
        "history_campaign_binding": (dict(ACTIVE_HISTORY_CAMPAIGN_BINDING)
            if ACTIVE_HISTORY_CAMPAIGN_BINDING is not None else None),
        "wide_transfer_probe_preflight": (dict(WIDE_TRANSFER_PROBE_PREFLIGHT)
            if WIDE_TRANSFER_PROBE_PREFLIGHT is not None else None),
        "external_preregistration_digest": _optional_preregistration_digest(
            PREREGISTRATION_DIGEST),
        "run_preregistration_digest": RUN_PREREGISTRATION_DIGEST,
        "stage": RUN_STAGE,
        "resource_preflight_samples": [dict(item)
            for item in RESOURCE_PREFLIGHT_EVIDENCE],
        "resource_preflight_sample_scope": (
            "host snapshots immediately before each inference; no during-inference "
            "process attribution"),
        "failure_type": type(exc).__name__,
        "failure_code": _failure_code(exc),
        "failure_cause_code": _failure_cause_code(exc),
        "failure_diagnostic": (dict(failure_diagnostic)
            if isinstance(failure_diagnostic, Mapping) else None),
        "stage_journal": _summarize_run_stage_journal(),
        "inference_receipts": receipts,
        "governed_developmental_records": records,
        "hosted_companion_deliveries": hosted_deliveries,
        "pre_action_decision_evidence": (
            dict(PRE_ACTION_DECISION_EVIDENCE)
            if PRE_ACTION_DECISION_EVIDENCE is not None else None),
        "initial_history_bootstrap": (
            dict(INITIAL_HISTORY_BOOTSTRAP_EVIDENCE)
            if INITIAL_HISTORY_BOOTSTRAP_EVIDENCE is not None else None),
        "governed_unload": _verify_model_released(MODEL_NAME),
        "gpu_after": _gpu_snapshot(),
        "raw_frames_or_user_conversation_copied": False,
        "causal_or_learning_claim_made": False,
    }
    target = RUN_ROOT / "cycle-failure.json"
    _no_symlink_path(target)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(artifact, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return target


def _pose_decision_from_response(value: Any) -> dict[str, str] | None:
    """Accept only an exact bounded action/prediction token; prose is unscored."""
    if not isinstance(value, str):
        return None
    poses = {"reach", "idle"}
    parts = value.split("->")
    if (len(parts) != 2 or any(part not in poses for part in parts)):
        return None
    return {"requested_pose": parts[0], "predicted_pose": parts[1]}


def _verified_companion_replay(bridge: Any, owner: Any, *,
        screen_observation: dict[str, Any] | None = None, request_id: str,
        question: str, withhold_developmental_history: bool = False
        ) -> dict[str, Any]:
    try:
        interaction = bridge.respond(request_id=request_id, question=question,
            screen_observation=screen_observation,
            withhold_developmental_history=withhold_developmental_history)
    except ResidentDevelopmentalCognitionError as exc:
        # Preserve an authenticated completion even when the owner rejects its
        # evidence-bound answer contract; rejected outputs are never shown.
        tick_id = "companion-interaction-" + hashlib.sha256(
            request_id.encode("utf-8")).hexdigest()[:32]
        correlation = (tick_id
            + ":resident_developmental_cognition:companion-interaction")
        runtime_root = getattr(owner.invoker, "runtime_root", None)
        if not isinstance(runtime_root, Path):
            raise
        matching = []
        for path in runtime_root.joinpath("receipts").glob("lmrec-*.json"):
            if path.is_symlink():
                continue
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            request = candidate.get("request") if isinstance(candidate, dict) else None
            if (isinstance(request, dict)
                    and request.get("correlation_id") == correlation):
                matching.append(candidate)
        if len(matching) != 1:
            raise
        candidate = matching[0]
        receipt = owner.invoker.verify_persisted_invocation_receipt(
            candidate.get("receipt_id"), candidate.get("receipt_digest"))
        request = receipt.get("request")
        generation_config = receipt.get("generation_config")
        upstream = request.get("upstream_evidence") if isinstance(request, dict) else None
        prompt_digest = request.get("prompt_digest") if isinstance(request, dict) else None
        if (not isinstance(prompt_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", prompt_digest) is None
                or not isinstance(generation_config, dict)
                or not isinstance(upstream, dict)):
            raise RootlessExperimentalError("rejected_replay_receipt_unverified") from exc
        rejection_diagnostic = _bounded_companion_rejection_diagnostic(exc)
        return {
            "status": "owner_rejected_completed_inference",
            # Keep the error contract tokenized; an exception message may
            # accidentally include model output and must never enter artifacts.
            "failure_code": _failure_code(exc),
            "prompt_digest": prompt_digest,
            "generation_config": generation_config,
            "active_model_identity": dict(request.get("active_model_identity", {})),
            "snapshot_digest": upstream.get("snapshot_digest"),
            "current_projection_digest": upstream.get("current_projection_digest"),
            "current_fact_ids": list(upstream.get("current_fact_ids", ())),
            "retrieved_record_ids": list(upstream.get("record_ids", ())),
            "output_digest": receipt.get("output_digest"),
            "response_digest": None,
            "rejection_diagnostic": rejection_diagnostic,
        }
    observation = owner.verified_cognition_observation(
        interaction.cognition_observation_id,
        interaction.cognition_observation_digest)
    receipt = owner._verify_observation_invocation(observation)
    request = receipt.get("request") if isinstance(receipt, dict) else None
    generation_config = receipt.get("generation_config") if isinstance(receipt, dict) else None
    prompt_digest = request.get("prompt_digest") if isinstance(request, dict) else None
    if (not isinstance(prompt_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", prompt_digest) is None
            or not isinstance(generation_config, dict)
            or interaction.status != "admitted_completed"):
        raise RootlessExperimentalError("companion_replay_receipt_unverified")
    lineage = {
        "status": "resident_cognition_interaction",
        "cognition_observation_id": interaction.cognition_observation_id,
        "cognition_observation_digest": interaction.cognition_observation_digest,
        "inference_receipt_id": interaction.inference_receipt_id,
        "inference_receipt_digest": interaction.inference_receipt_digest,
        "invocation_output_digest": interaction.invocation_output_digest,
        "response_digest": interaction.response_digest,
    }
    linkage = {
        "response_origin": "resident_developmental_cognition",
        "cognition_observation_id": interaction.cognition_observation_id,
        "cognition_observation_digest": interaction.cognition_observation_digest,
        "cognition_snapshot_id": interaction.snapshot_id,
        "cognition_snapshot_digest": interaction.snapshot_digest,
        "inference_receipt_id": interaction.inference_receipt_id,
        "inference_receipt_digest": interaction.inference_receipt_digest,
        "invocation_output_digest": interaction.invocation_output_digest,
        "response_digest": interaction.response_digest,
        "assistant_output_lineage": lineage,
        "cognition_evidence_ids": list(interaction.evidence_ids),
        "cognition_history_record_ids": list(interaction.history_record_ids),
        "cognition_prior_record_ids": list(interaction.prior_record_ids),
        "cognition_model_id": interaction.model_id,
        "cognition_model_artifact_digest": interaction.model_artifact_digest,
        "self_model_projection_id": interaction.self_model_projection_id,
        "self_model_projection_digest": interaction.self_model_projection_digest,
        "epistemic_projection_id": interaction.epistemic_projection_id,
        "epistemic_projection_digest": interaction.epistemic_projection_digest,
    }
    return {
        "status": "admitted_completed",
        "prompt_digest": prompt_digest,
        "generation_config": generation_config,
        "active_model_identity": dict(observation.get("active_model_identity", {})),
        "snapshot_id": observation.get("current_snapshot_id"),
        "snapshot_digest": observation.get("current_snapshot_digest"),
        "current_projection_digest": observation.get("current_projection_digest"),
        "current_fact_ids": list(observation.get("current_fact_ids", ())),
        "retrieved_record_ids": list(observation.get("retrieved_record_ids", ())),
        "output_digest": interaction.invocation_output_digest,
        "response_digest": interaction.response_digest,
        "disposition": interaction.disposition,
        "evidence_ids": list(interaction.evidence_ids),
        "history_record_ids": list(interaction.history_record_ids),
        "validated_response": interaction.response,
        "prompt_digest": prompt_digest,
        "output_digest": interaction.invocation_output_digest,
        "cognition_observation_id": interaction.cognition_observation_id,
        "cognition_observation_digest": interaction.cognition_observation_digest,
        "inference_receipt_id": interaction.inference_receipt_id,
        "inference_receipt_digest": interaction.inference_receipt_digest,
        "response_lineage_verified": bridge.verify_committed_response(
            linkage=linkage, response_text=interaction.response,
            request_id=request_id),
    }


def _bounded_companion_rejection_diagnostic(
        exc: Exception) -> dict[str, Any] | None:
    """Retain only categorical validation metadata, never model text."""
    diagnostic = getattr(exc, "diagnostic", None)
    if not isinstance(diagnostic, Mapping):
        return None
    validation_code = diagnostic.get("validation_error")
    output_digest = diagnostic.get("output_digest")
    if (not isinstance(validation_code, str)
            or re.fullmatch(r"[a-z0-9_]{1,120}", validation_code) is None
            or not isinstance(output_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", output_digest) is None):
        return None
    condition_id = diagnostic.get("condition_id")
    if (not isinstance(condition_id, str)
            or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", condition_id) is None):
        condition_id = None
    protocol_id = diagnostic.get("protocol_id")
    if (not isinstance(protocol_id, str)
            or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", protocol_id) is None):
        protocol_id = None
    return {
        "schema_version": "sentientos.companion_rejection_diagnostic:v1",
        "validation_error_code": validation_code,
        "output_digest": output_digest,
        "condition_id": condition_id,
        "protocol_id": protocol_id,
        "raw_model_output_included": False,
        "exception_message_included": False,
        "authority": False,
    }


def _bounded_pre_action_decision_diagnostic(
        decision: Mapping[str, Any]) -> dict[str, Any] | None:
    """Record a non-answer outcome without copying response text."""
    disposition = decision.get("disposition")
    status = decision.get("status")
    response_digest = decision.get("response_digest")
    evidence_ids = decision.get("evidence_ids")
    history_ids = decision.get("history_record_ids")
    current_fact_ids = decision.get("current_fact_ids")
    if (disposition not in {"answer", "ask", "abstain"}
            or not isinstance(status, str)
            or re.fullmatch(r"[a-z0-9_]{1,80}", status) is None
            or decision.get("response_lineage_verified") is not True
            or not isinstance(response_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", response_digest) is None
            or not isinstance(evidence_ids, (list, tuple))
            or len(evidence_ids) > 32
            or any(not isinstance(item, str) or len(item) > 256
                for item in evidence_ids)
            or not isinstance(history_ids, (list, tuple))
            or len(history_ids) > 16
            or any(not isinstance(item, str)
                or re.fullmatch(r"devrec-[0-9a-f]{24}", item) is None
                for item in history_ids)
            or not isinstance(current_fact_ids, (list, tuple))
            or len(current_fact_ids) > 32
            or any(not isinstance(item, str) or len(item) > 256
                for item in current_fact_ids)):
        return None
    optional_digests: dict[str, str | None] = {}
    for key in ("prompt_digest", "output_digest",
            "inference_receipt_digest", "cognition_observation_digest"):
        value = decision.get(key)
        optional_digests[key] = (value if isinstance(value, str)
            and re.fullmatch(r"[0-9a-f]{64}", value) is not None else None)
    receipt_id = decision.get("inference_receipt_id")
    if (not isinstance(receipt_id, str)
            or re.fullmatch(r"lmrec-[0-9a-f]{24}", receipt_id) is None):
        receipt_id = None
    current_projection_digest = decision.get("current_projection_digest")
    if (not isinstance(current_projection_digest, str)
            or re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}",
                current_projection_digest) is None):
        current_projection_digest = None
    snapshot_digest = decision.get("snapshot_digest")
    if (not isinstance(snapshot_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", snapshot_digest) is None):
        snapshot_digest = None
    snapshot_id = decision.get("snapshot_id")
    if (not isinstance(snapshot_id, str)
            or re.fullmatch(r"world-state-[0-9a-f]{16}", snapshot_id) is None):
        snapshot_id = None
    return {
        "schema_version": "sentientos.pre_action_decision_diagnostic:v2",
        "status": status,
        "disposition": disposition,
        "response_digest": response_digest,
        **optional_digests,
        "inference_receipt_id": receipt_id,
        "response_lineage_verified": True,
        "evidence_ids": list(evidence_ids),
        "current_fact_ids": list(current_fact_ids),
        "current_projection_digest": current_projection_digest,
        "snapshot_id": snapshot_id,
        "snapshot_digest": snapshot_digest,
        "history_record_ids": list(history_ids),
        "raw_response_included": False,
        "authority": False,
    }


def _bounded_pre_action_ask_capture(
        decision: Mapping[str, Any]) -> dict[str, Any] | None:
    """Persist only a bounded, lineage-verified model-authored clarification."""
    diagnostic = _bounded_pre_action_decision_diagnostic(decision)
    response = decision.get("validated_response")
    if (diagnostic is None or diagnostic.get("status") != "admitted_completed"
            or diagnostic.get("disposition") != "ask"
            or not isinstance(response, str) or not response.strip()):
        return None
    try:
        response_size = len(response.encode("utf-8"))
    except UnicodeEncodeError:
        return None
    if (response_size > 1024
            or digest_payload({"text": response})
                != diagnostic.get("response_digest")):
        return None
    return {
        "schema_version": "sentientos.pre_action_ask_capture:v1",
        "model_authored_question": response,
        "question_text_untrusted": True,
        "question_size_bytes": response_size,
        "response_digest": diagnostic["response_digest"],
        "prompt_digest": diagnostic.get("prompt_digest"),
        "output_digest": diagnostic.get("output_digest"),
        "inference_receipt_id": diagnostic.get("inference_receipt_id"),
        "inference_receipt_digest": diagnostic.get(
            "inference_receipt_digest"),
        "evidence_ids": list(diagnostic["evidence_ids"]),
        "history_record_ids": list(diagnostic["history_record_ids"]),
        "raw_answer_text_included": False,
        "authority": False,
        "action_executed": False,
        "synthetic_action_simulated": False,
    }


def _pre_action_source(*, pose: str = "idle",
        include_current_target: bool = False
        ) -> tuple[WorldStateSnapshot, EmbodimentObservation]:
    """Build the synthetic body's pre-action state for a governed proposal."""
    if pose not in {"idle", "reach"}:
        raise RootlessExperimentalError("synthetic_pose_invalid")
    self_report = make_synthetic_pre_action_proprioception_observation(
        run_id=RUN_ID, pose=pose)
    records = EmbodimentEvidenceOwner([self_report]).world_state_records()
    if include_current_target:
        records.append(_synthetic_current_target_record())
    return WorldStateBoardBuilder().build(records), self_report


def _objective_task_source() -> WorldStateSnapshot:
    """Use a matched current body-state observation for abstract task probes.

    The task-family acquisition and transfer comparisons already bind their
    task descriptor and retained history separately. Reusing the preceding
    consequence snapshot injects a large, unrelated evidence chain into every
    condition and can exceed the configured model context window. Keep one fresh,
    deterministic proprioception observation as matched current context.
    """
    snapshot, _ = _pre_action_source(pose="idle")
    return snapshot


def _authenticated_synthetic_observation(*, expectation: Any,
        handoff: Mapping[str, Any], renderer_report: Any,
        observed: Mapping[str, Any], observed_at: str
        ) -> tuple[AuthenticatedBridgeIndependentObserver, Any]:
    """Pass a synthetic observer fixture through the signed loopback path.

    This rehearses authenticated source binding only. The key is ephemeral and
    held by this experiment process; it does not establish an external observer,
    a correct measurement of reality, or a physical consequence.
    """
    observer_id = RUN_ID + ":synthetic-observer"
    acknowledgment_id = RUN_ID + ":synthetic-observer-ack"
    generation_id = RUN_ID
    session_id = RUN_ID + ":synthetic-observer-session"
    observer_key = secrets.token_bytes(32)
    acknowledgment_key = secrets.token_bytes(32)
    receiver = CompanionBridgeReceiver(
        source_keys={observer_id: observer_key},
        expected_generations={observer_id: generation_id})
    runtime = CompanionBridgeLoopbackRuntime(
        receiver=receiver,
        acknowledgment_source_id=acknowledgment_id,
        acknowledgment_generation_id=generation_id,
        acknowledgment_key=acknowledgment_key)
    port = runtime.start()
    try:
        acknowledgment_receiver = CompanionBridgeReceiver(
            source_keys={acknowledgment_id: acknowledgment_key},
            expected_generations={acknowledgment_id: generation_id})
        client = CompanionBridgeLoopbackClient(
            port=port, acknowledgment_receiver=acknowledgment_receiver)
        payload = {
            "schema_version": "sentientos.bridge_consequence_observation:v1",
            "expectation_id": expectation.expectation_id,
            "expectation_digest": expectation.expectation_digest,
            "handoff_id": handoff["handoff_id"],
            "handoff_digest": handoff["handoff_digest"],
            "renderer_report_id": renderer_report.report_id,
            "renderer_report_digest": renderer_report.report_digest,
            "correlation_id": expectation.correlation_id,
            "body_generation": expectation.body_generation,
            "observed": dict(observed),
            "observed_at": observed_at,
            "confidence": "medium",
            "quality": "usable",
        }
        encoded = encode_message(kind="consequence", source_id=observer_id,
            session_id=session_id, generation_id=generation_id, sequence=1,
            payload=payload, key=observer_key, created_at=observed_at)
        client.send(encoded)
        observer = AuthenticatedBridgeIndependentObserver(
            runtime=runtime, observer_id=observer_id,
            generation_id=generation_id,
            observer_fixture_posture="same_process_synthetic_fixture")
        observation = observer.observe(expectation=expectation,
            handoff=handoff, report=renderer_report)
        return observer, observation
    finally:
        runtime.close()


def _embodied_source(*, requested_pose: str, predicted_pose: str
        ) -> tuple[WorldStateSnapshot, dict[str, Any], EmbodimentObservation]:
    commanded_at = (datetime.now(timezone.utc) - timedelta(seconds=8)).isoformat()
    renderer_completed_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    observed_at = (datetime.now(timezone.utc) - timedelta(seconds=4)).isoformat()
    body = {"installation_identity": "synthetic-installation",
        "body_identity": "synthetic-avatar-body", "body_generation": 1,
        "artifact_sha256": "sha256:" + "a" * 64,
        "manifest_digest": "sha256:" + "b" * 64,
        "pointer_digest": "sha256:" + "c" * 64}
    handoff = renderer_handoff(body, renderer_interface_id="renderer:synthetic:v1",
        requested_pose=requested_pose, requested_expression="neutral",
        correlation_id=RUN_ID + ":action", commanded_at=commanded_at)
    task_goal = "reach_marked_target"
    expectation = make_expectation(
        installation_body_id="synthetic-installation", body_id="synthetic-avatar-body",
        body_generation=1, body_manifest_digest=body["manifest_digest"],
        handoff_id=handoff["handoff_id"], handoff_digest=handoff["handoff_digest"],
        renderer_interface_id="renderer:synthetic:v1",
        requested={"pose": requested_pose, "task_goal": task_goal},
        predicted_observables={"pose": predicted_pose,
            "task_goal_met": predicted_pose == "reach"},
        observable_fields=("pose", "task_goal_met"),
        comparison_policy={"pose": {"kind": "exact"},
            "task_goal_met": {"kind": "exact"}},
        expected_observation_source_class="authenticated_bridge_observer",
        correlation_id=RUN_ID + ":action", causal_principal_binding_digest=None,
        created_at=commanded_at,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    renderer_report = SyntheticRenderer(applied={"pose": requested_pose},
        started_at=commanded_at, completed_at=renderer_completed_at).render_test(handoff)
    # A synthetic observer fixture reports the environment result through a
    # source-distinct signed bridge. The experiment process creates the
    # ephemeral fixture key, so this is protocol rehearsal, not an independent
    # measurement of a physical environment.
    observed_pose = "idle"
    observer_owner, observation = _authenticated_synthetic_observation(
        expectation=expectation, handoff=handoff,
        renderer_report=renderer_report,
        observed={"pose": observed_pose,
            "task_goal_met": observed_pose == "reach"},
        observed_at=observed_at)
    attribution, comparison = evaluate_consequence(
        expectation=expectation, handoff=handoff, current_body=body,
        renderer_report=renderer_report, observation=observation,
        evaluated_at=observed_at,
        independent_observer_owner=observer_owner)
    consequence_store = ConsequenceStore(RUN_ROOT / "consequence-store")
    consequence_chain = consequence_store.put_consequence_chain(
        expectation=expectation, handoff=handoff, renderer_report=renderer_report,
        observation=observation, attribution=attribution, comparison=comparison)
    consequence_records = consequence_store.world_state_records(
        consequence_chain_ids=(consequence_chain["chain_id"],))

    self_report = EmbodimentObservation(
        source_id=RUN_ID + ":synthetic-proprioception",
        source_schema="sentientos.synthetic_proprioception_observation:v1",
        source_digest=semantic_digest({"requested_pose": requested_pose,
            "encoder_pose": requested_pose,
            "joint_state": {"arm": 0.75 if requested_pose == "reach" else 0.0},
            "source_posture": "synthetic_test"}),
        observed_at=renderer_completed_at,
        provenance_class="deterministic_synthetic_fixture", freshness="current",
        posture="synthetic_test", evidence_class="sensor_observation",
        subject_id="synthetic-avatar-body", subject_kind="robot_body",
        payload={"requested_pose": requested_pose, "encoder_pose": requested_pose,
            "joint_state": {"arm": 0.75 if requested_pose == "reach" else 0.0},
            "sampled_at": renderer_completed_at})
    proprioception_records = EmbodimentEvidenceOwner([self_report]).world_state_records()
    # Preserve the complete auditable chain and proprioception. No screen capture
    # is fabricated for this synthetic experiment; the exact eight-fact evidence
    # shape has a narrowly bounded writeback allowance.
    selected_records = consequence_records + proprioception_records
    snapshot = WorldStateBoardBuilder().build(selected_records)
    evidence_summary = {
        "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
        "source_kinds": sorted({row["source_kind"]
            for row in consequence_records + proprioception_records}),
        "proprioception_posture": "synthetic_test_unverified_self_report",
        "consequence_classification": attribution["classification"],
        "effect_proven": attribution["effect_proven"],
        "requested_pose": requested_pose,
        "predicted_pose": predicted_pose,
        "task_goal": task_goal,
        "task_goal_met": observation.observed.get("task_goal_met") is True,
        "task_goal_evaluation_posture": (
            "synthetic_fixture_relation_of_observed_pose_to_task_goal"),
        "renderer_report_pose": dict(renderer_report.applied),
        "independent_observation_pose": dict(observation.observed),
        "renderer_and_observer_referenced_separately": True,
        "observation_independence_posture": attribution[
            "observation_independence_posture"],
        "observer_fixture_posture": "signed_loopback_same_process_synthetic_fixture",
        "observer_key_custody_posture": "ephemeral_experiment_process_test_key",
        "physical_observation_established": False,
        "action_execution_posture": "synthetic_fixture_only",
    }
    return snapshot, evidence_summary, self_report


def _synthetic_current_target_observation() -> EmbodimentObservation:
    """Create a fresh, explicitly synthetic sensor reading for the target."""
    observed_at = datetime.now(timezone.utc).isoformat()
    payload = {"visible": True, "distance": "within_reach",
        "hazard_status": "unknown", "fixture_posture": "synthetic_test"}
    observation = EmbodimentObservation(
        source_id=RUN_ID + ":synthetic-current-target",
        source_schema="sentientos.synthetic_environment_target_observation:v1",
        source_digest=semantic_digest(payload),
        observed_at=observed_at,
        provenance_class="deterministic_synthetic_fixture",
        freshness="current", posture="synthetic_test",
        evidence_class="sensor_observation",
        subject_id="synthetic-target-1", subject_kind="target_object",
        payload={**payload, "sampled_at": observed_at})
    return observation


def _synthetic_current_target_refresh_observation(*, observed_at: str
        ) -> EmbodimentObservation:
    """Return a second synthetic sample acquired only after an owner ask."""
    payload = {
        "visible": True,
        "distance": "within_reach",
        "hazard_status": "clear",
        "fixture_posture": "synthetic_test",
        "sample_index": 2,
        "acquisition_trigger": "after_owner_admitted_ask",
    }
    return EmbodimentObservation(
        source_id=RUN_ID + ":synthetic-current-target-refresh-2",
        source_schema="sentientos.synthetic_environment_target_observation:v2",
        source_digest=semantic_digest(payload),
        observed_at=observed_at,
        provenance_class="deterministic_synthetic_fixture",
        freshness="current", posture="synthetic_test",
        evidence_class="sensor_observation",
        subject_id="synthetic-target-1", subject_kind="target_object",
        payload={**payload, "sampled_at": observed_at})


def _synthetic_current_target_record() -> dict[str, Any]:
    """Project the synthetic target reading into the later task snapshot."""
    records: list[dict[str, Any]] = EmbodimentEvidenceOwner(
        [_synthetic_current_target_observation()]).world_state_records()
    return records[0]


def _synthetic_pre_action_scenario_observation() -> EmbodimentObservation:
    """Expose stipulated task premises as citable, non-world fixture input."""
    observed_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "fixture_type": "synthetic_pre_action_pose_choice",
        "initial_pose": "idle",
        "allowed_poses": ["idle", "reach"],
        "task_objective": "reach_marked_target",
        "target": {"visibility": "visible",
            "location": "directly_in_front", "distance": "within_reach"},
        "transition_table": {
            "reach": {"predicted_pose": "reach"},
            "idle": {"predicted_pose": "idle"}},
        "interpretation_posture": "stipulated_conditional_fixture_input",
        "external_world_observation": False,
    }
    return EmbodimentObservation(
        source_id=RUN_ID + ":pre-action-scenario-fixture",
        source_schema="sentientos.rootless_pre_action_scenario:v1",
        source_digest=semantic_digest(payload),
        observed_at=observed_at,
        provenance_class="deterministic_synthetic_fixture",
        freshness="current", posture="synthetic_test",
        evidence_class="scenario_fixture",
        subject_id=RUN_ID + ":synthetic-planning-scenario",
        subject_kind="synthetic_planning_scenario",
        payload=payload)


def _objective_family_acquisition_readiness(run_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Reject invalid or incomplete typed outputs as developmental examples."""
    protocol = run_payload.get("protocol")
    descriptor = (protocol.get("objective_task_descriptor")
        if isinstance(protocol, Mapping) else None)
    probes = descriptor.get("probe_inputs") if isinstance(descriptor, Mapping) else None
    required = len(probes) if isinstance(probes, list) else 0
    scores = run_payload.get("objective_scores")
    present = next((row for row in scores if isinstance(row, Mapping)
        and row.get("condition_id") == "history_present"), None) \
        if isinstance(scores, list) else None
    evaluation = present.get("score") if isinstance(present, Mapping) else None
    results = evaluation.get("probe_results") if isinstance(evaluation, Mapping) else None
    status = evaluation.get("status") if isinstance(evaluation, Mapping) else None
    score_schema = (evaluation.get("schema_version")
        if isinstance(evaluation, Mapping) else None)
    selective_schema = score_schema in {
        "sentientos.objective_task_score:v4",
        "sentientos.objective_task_score:v5",
        "sentientos.objective_task_score:v6"}
    typed_count = 0
    abstained_count = 0
    rows_valid = (isinstance(probes, list) and isinstance(results, list)
        and required > 0 and len(results) == required)
    if rows_valid:
        for index, item in enumerate(results):
            if (not isinstance(item, Mapping)
                    or type(item.get("probe_input")) is not int
                    or item.get("probe_input") != probes[index]):
                rows_valid = False
                break
            answer, correct = item.get("observed_answer"), item.get("correct")
            if type(answer) is int and type(correct) is bool and "abstained" not in item:
                typed_count += 1
            elif (selective_schema and answer is None and correct is None
                    and item.get("abstained") is True
                    and set(item) == ({"probe_input", "observed_answer", "correct",
                        "confidence_basis_points", "abstained"}
                        if score_schema == "sentientos.objective_task_score:v6"
                        else {"probe_input", "observed_answer", "correct", "abstained"})
                    and (score_schema != "sentientos.objective_task_score:v6"
                        or item.get("confidence_basis_points") is None)):
                abstained_count += 1
            else:
                rows_valid = False
                break
    row_outcomes_valid = False
    if isinstance(evaluation, Mapping) and rows_valid:
        observed_correct = sum(item.get("correct") is True for item in results)
        row_outcomes_valid = (
            evaluation.get("probe_count") == required
            and type(evaluation.get("correct_count")) is int
            and evaluation["correct_count"] == observed_correct
            and ((status in {"correct", "incorrect"} and abstained_count == 0
                    and (status == "correct") == (observed_correct == required))
                or (status == "selective" and selective_schema
                    and abstained_count > 0
                    and type(evaluation.get("answered_count")) is int
                    and type(evaluation.get("abstained_count")) is int
                    and evaluation.get("answered_count") == typed_count
                    and evaluation.get("abstained_count") == abstained_count)))
    eligible = (isinstance(evaluation, Mapping) and rows_valid
        and row_outcomes_valid and typed_count + abstained_count == required)
    return {
        "eligible": eligible,
        "classification": ("complete_score_bound_acquisition_examples"
            if eligible else "acquisition_output_not_eligible_for_task_family_history"),
        "score_status": status if status in {
            "correct", "incorrect", "selective", "invalid_answer", "output_truncated",
            "output_unavailable"} else "unknown",
        "probe_result_count": len(results) if isinstance(results, list) else 0,
        "required_probe_count": required,
    }


def _objective_family_acquisition_readiness_diagnostics(
        run_payload: Mapping[str, Any], readiness: Mapping[str, Any]) -> dict[str, Any]:
    """Explain acquisition writeback gating without retaining model answers."""
    required = readiness.get("required_probe_count")
    scores = run_payload.get("objective_scores")
    present = next((row for row in scores if isinstance(row, Mapping)
        and row.get("condition_id") == "history_present"), None) \
        if isinstance(scores, list) else None
    score = present.get("score") if isinstance(present, Mapping) else None
    results = score.get("probe_results") if isinstance(score, Mapping) else None
    rows = results if isinstance(results, list) else []
    protocol = run_payload.get("protocol")
    descriptor = (protocol.get("objective_task_descriptor")
        if isinstance(protocol, Mapping) else None)
    probes = (descriptor.get("probe_inputs")
        if isinstance(descriptor, Mapping) else None)
    probes = probes if isinstance(probes, list) else []
    aligned = 0
    typed_answers = 0
    explicit_abstentions = 0
    malformed = 0
    for index, row in enumerate(rows):
        if (not isinstance(row, Mapping) or index >= len(probes)
                or type(row.get("probe_input")) is not int
                or row.get("probe_input") != probes[index]):
            malformed += 1
            continue
        aligned += 1
        answer = row.get("observed_answer")
        correct = row.get("correct")
        if type(answer) is int and type(correct) is bool:
            typed_answers += 1
        elif (answer is None and correct is None
                and row.get("abstained") is True):
            explicit_abstentions += 1
        else:
            malformed += 1
    blockers: list[str] = []
    if readiness.get("score_status") not in {"correct", "incorrect", "selective"}:
        blockers.append("score_status_not_writeback_eligible")
    if type(required) is not int or required <= 0 or len(rows) != required:
        blockers.append("probe_rows_incomplete")
    if aligned != len(rows):
        blockers.append("probe_input_alignment_invalid")
    if typed_answers + explicit_abstentions != required or malformed:
        blockers.append("probe_rows_not_fully_score_bound")
    if isinstance(score, Mapping) and score.get("probe_count") != required:
        blockers.append("score_probe_count_mismatch")
    if readiness.get("eligible") is not True and not blockers:
        blockers.append("score_row_bindings_invalid")
    return {
        "schema_version": "sentientos.objective_acquisition_readiness_diagnostics:v1",
        "score_status": readiness.get("score_status", "unknown"),
        "required_probe_count": required,
        "probe_result_count": len(rows),
        "aligned_probe_count": aligned,
        "typed_answer_count": typed_answers,
        "explicit_abstention_count": explicit_abstentions,
        "malformed_or_misaligned_row_count": malformed,
        "writeback_eligible": readiness.get("eligible") is True,
        "blocker_codes": blockers,
        "raw_answers_retained": False,
        "authority": False,
    }


def _require_experiment_runtime_dependencies() -> None:
    """Fail before model loading when telemetry or later scoring deps are absent."""
    for module_name in ("psutil", "pydantic"):
        try:
            available = importlib.util.find_spec(module_name) is not None
        except (ImportError, ValueError):
            available = False
        if not available:
            raise RootlessExperimentalError(
                f"experimental_runtime_dependency_missing:{module_name}")


def _prepare_resident_cognition_roots(run_root: Path) -> tuple[Path, Path]:
    """Create isolated history and state roots with the run's private custody."""
    if os.name == "nt":
        from sentientos.windows_handle_custody import ensure_private_child_directory
        cognition_root = ensure_private_child_directory(
            run_root, "resident-cognition")
        history_root = ensure_private_child_directory(cognition_root, "history")
        # Even a valid empty seed has both store collections. Initialize them
        # before verifying the copied boundary so empty-history campaigns use
        # the same on-disk shape as histories populated by writeback.
        ensure_private_child_directory(history_root, "records")
        ensure_private_child_directory(history_root, "receipts")
        state_root = ensure_private_child_directory(cognition_root, "state")
        return history_root, state_root
    cognition_root = run_root / "resident-cognition"
    cognition_root.mkdir(mode=0o700, exist_ok=False)
    history_root, state_root = cognition_root / "history", cognition_root / "state"
    history_root.mkdir(mode=0o700, exist_ok=False)
    (history_root / "records").mkdir(mode=0o700, exist_ok=False)
    (history_root / "receipts").mkdir(mode=0o700, exist_ok=False)
    state_root.mkdir(mode=0o700, exist_ok=False)
    return history_root, state_root


def _copy_cognition_recovery_state(source_state_root: Path,
        destination_state_root: Path,
        expected_boundary: Mapping[str, Any] | None) -> bool:
    from work.rootless_history_boundary_campaign import (
        _cognition_recovery_state_boundary)

    source_boundary = _cognition_recovery_state_boundary(source_state_root)
    if source_boundary != expected_boundary:
        raise RootlessExperimentalError(
            "prior_cognition_recovery_state_boundary_mismatch")
    if expected_boundary is None:
        return False
    for row in expected_boundary["files"]:
        relative = Path(row["path"])
        if (relative.is_absolute() or ".." in relative.parts
                or not relative.parts):
            raise RootlessExperimentalError(
                "prior_cognition_recovery_state_path_invalid")
        if relative.parts[0] == "inference-custody":
            source = source_state_root.parent.parent / relative
            destination = destination_state_root.parent.parent / relative
        else:
            source = source_state_root / relative
            destination = destination_state_root / relative
        _no_symlink_path(source)
        _no_symlink_path(destination.parent)
        try:
            raw = source.read_bytes()
        except OSError as exc:
            raise RootlessExperimentalError(
                "prior_cognition_recovery_state_read_failed") from exc
        if (len(raw) != row["size_bytes"]
                or hashlib.sha256(raw).hexdigest() != row["sha256"]):
            raise RootlessExperimentalError(
                "prior_cognition_recovery_state_changed_during_copy")
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                view = memoryview(raw)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("short cognition recovery state write")
                    view = view[written:]
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise RootlessExperimentalError(
                "prior_cognition_recovery_state_copy_failed") from exc
    if _cognition_recovery_state_boundary(destination_state_root) != expected_boundary:
        raise RootlessExperimentalError(
            "prior_cognition_recovery_state_copy_mismatch")
    return True


def _seed_resident_developmental_history(history_root: Path, state_root: Path,
        expected_admission_boundary: Mapping[str, Any] | None,
        expected_recovery_boundary: Mapping[str, Any] | None
        ) -> dict[str, Any]:
    """Copy an explicitly selected, owner-verified history store into this run."""
    configured = os.environ.get("SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT")
    evidence = {
        "schema_version": "sentientos.rootless_developmental_history_seed:v3",
        "status": "not_configured",
        "record_count": 0,
        "receipt_count": 0,
        "source_boundary_digest": None,
        "copied_into_run_store": False,
        "source_runtime_admission_ledger": None,
        "runtime_admission_ledger_copied": False,
        "source_cognition_recovery_state": None,
        "cognition_recovery_state_copied": False,
        "model_attention_verified": False,
    }
    if configured is None or not configured.strip():
        return evidence
    if PREREGISTRATION_DIGEST == "0" * 64:
        raise RootlessExperimentalError(
            "prior_developmental_history_requires_external_preregistration")
    source_root = Path(configured).expanduser()
    _no_symlink_path(source_root)
    try:
        source_resolved = source_root.resolve(strict=True)
        destination_resolved = history_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RootlessExperimentalError(
            "prior_developmental_history_root_invalid") from exc
    if (not source_resolved.is_dir()
            or source_resolved == destination_resolved
            or source_resolved in destination_resolved.parents
            or destination_resolved in source_resolved.parents):
        raise RootlessExperimentalError("prior_developmental_history_root_invalid")
    if any(not (source_root / name).is_dir()
            or (source_root / name).is_symlink()
            for name in ("records", "receipts")):
        raise RootlessExperimentalError("prior_developmental_history_collections_missing")
    source_store = DevelopmentalHistoryStore(source_root)
    records = source_store.records()
    receipts = source_store.receipts()
    records = tuple(sorted(records, key=lambda item: item.record_id))
    receipts = tuple(sorted(receipts, key=lambda item: item.receipt_id))
    records_by_id = {record.record_id: record for record in records}
    if len(records_by_id) != len(records):
        raise RootlessExperimentalError("prior_developmental_history_record_identity_duplicate")
    for receipt in receipts:
        record = records_by_id.get(receipt.record_id)
        if record is None or record.record_digest != receipt.record_digest:
            raise RootlessExperimentalError("prior_developmental_history_receipt_unbound")
    receipt_record_ids = {receipt.record_id for receipt in receipts}
    if set(records_by_id) - receipt_record_ids:
        raise RootlessExperimentalError("prior_developmental_history_record_without_receipt")
    source_boundary = {
        "records": [{"record_id": item.record_id,
            "record_digest": item.record_digest} for item in records],
        "receipts": [{"receipt_id": item.receipt_id,
            "receipt_digest": item.receipt_digest,
            "record_id": item.record_id,
            "record_digest": item.record_digest} for item in receipts],
    }
    source_digest = digest_payload(source_boundary)
    source_admission_path = source_root.parent / "state" / "runtime_admissions.json"
    source_admission_boundary = _runtime_admission_ledger_boundary(
        source_admission_path)
    if source_admission_boundary != expected_admission_boundary:
        raise RootlessExperimentalError(
            "prior_developmental_history_admission_boundary_mismatch")
    admission_copied = False
    if source_admission_boundary is not None:
        try:
            source_admissions, source_revocations = AdmissionLedger(
                source_admission_path).load()
            admission_ids = {item.admission_id for item in source_admissions}
            if any(not record.admission_id
                    or record.admission_id not in admission_ids for record in records):
                raise RootlessExperimentalError(
                    "prior_developmental_history_admission_missing")
            destination_admission_path = state_root / "runtime_admissions.json"
            if destination_admission_path.exists() or destination_admission_path.is_symlink():
                raise RootlessExperimentalError(
                    "prior_developmental_history_admission_destination_not_empty")
            destination_ledger = AdmissionLedger(destination_admission_path)
            destination_ledger.save(source_admissions, source_revocations)
            copied_admissions, copied_revocations = destination_ledger.load()
            if ((copied_admissions, copied_revocations)
                    != (source_admissions, source_revocations)
                    or _runtime_admission_ledger_boundary(
                        destination_admission_path) != source_admission_boundary):
                raise RootlessExperimentalError(
                    "prior_developmental_history_admission_copy_mismatch")
            admission_copied = True
        except RootlessExperimentalError:
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            raise RootlessExperimentalError(
                "prior_developmental_history_admission_copy_failed") from exc
    elif records:
        raise RootlessExperimentalError(
            "prior_developmental_history_admission_ledger_missing")
    from work.rootless_history_boundary_campaign import (
        _cognition_recovery_state_boundary)
    source_recovery_boundary = _cognition_recovery_state_boundary(
        source_root.parent / "state")
    if source_recovery_boundary != expected_recovery_boundary:
        raise RootlessExperimentalError(
            "prior_developmental_history_recovery_state_boundary_mismatch")
    recovery_state_copied = _copy_cognition_recovery_state(
        source_root.parent / "state", state_root, expected_recovery_boundary)
    if records and not recovery_state_copied:
        raise RootlessExperimentalError(
            "prior_developmental_history_recovery_state_missing")
    destination_store = DevelopmentalHistoryStore(history_root)
    try:
        for record in records:
            destination_store.append(record)
        for receipt in receipts:
            destination_store.write_receipt(receipt)
    except DevelopmentalWritebackError as exc:
        raise RootlessExperimentalError(
            "prior_developmental_history_copy_failed") from exc
    copied_records = destination_store.records()
    copied_receipts = destination_store.receipts()
    copied_records = tuple(sorted(copied_records, key=lambda item: item.record_id))
    copied_receipts = tuple(sorted(copied_receipts, key=lambda item: item.receipt_id))
    copied_boundary = {
        "records": [{"record_id": item.record_id,
            "record_digest": item.record_digest} for item in copied_records],
        "receipts": [{"receipt_id": item.receipt_id,
            "receipt_digest": item.receipt_digest,
            "record_id": item.record_id,
            "record_digest": item.record_digest} for item in copied_receipts],
    }
    if digest_payload(copied_boundary) != source_digest:
        raise RootlessExperimentalError("prior_developmental_history_copy_mismatch")
    return {
        "schema_version": "sentientos.rootless_developmental_history_seed:v3",
        "status": "copied_and_reloaded_verified",
        "record_count": len(records),
        "receipt_count": len(receipts),
        "source_boundary_digest": source_digest,
        "copied_into_run_store": True,
        "source_runtime_admission_ledger": source_admission_boundary,
        "runtime_admission_ledger_copied": admission_copied,
        "source_cognition_recovery_state": source_recovery_boundary,
        "cognition_recovery_state_copied": recovery_state_copied,
        "model_attention_verified": False,
    }


def run() -> dict[str, Any]:
    global RUN_STAGE, PRE_ACTION_DECISION_EVIDENCE, RUN_FAILURE_DIAGNOSTIC
    global INITIAL_HISTORY_BOOTSTRAP_EVIDENCE
    global RUN_PREREGISTRATION_DIGEST
    global RUN_SOURCE_PROVENANCE_AT_END, HISTORY_SEED_EVIDENCE
    global ACTIVE_HISTORY_CAMPAIGN_BINDING
    PRE_ACTION_DECISION_EVIDENCE = None
    RUN_FAILURE_DIAGNOSTIC = None
    INITIAL_HISTORY_BOOTSTRAP_EVIDENCE = None
    RUN_PREREGISTRATION_DIGEST = None
    RUN_SOURCE_PROVENANCE_AT_END = None
    ACTIVE_HISTORY_CAMPAIGN_BINDING = None
    historical_pair_context = _load_historical_pair_execution_context()
    negative_guidance_context = _load_negative_guidance_execution_context()
    strategy_inclusion_context = _load_strategy_inclusion_execution_context()
    configured_pair_modes = [context for context in (
        historical_pair_context, negative_guidance_context,
        strategy_inclusion_context) if context is not None]
    if len(configured_pair_modes) > 1:
        raise RootlessExperimentalError(
            "multiple_pair_execution_modes_configured")
    pair_execution_context = (configured_pair_modes[0]
        if configured_pair_modes else None)
    if (pair_execution_context is not None
            and os.environ.get("SENTIENTOS_HERMES_CAMPAIGN_PLAN_PATH")):
        raise RootlessExperimentalError(
            "historical_examples_pair_cannot_mix_campaign_cycle_mode")
    if (RUN_SOURCE_PROVENANCE.get("observation_status") != "observed"
            or RUN_SOURCE_PROVENANCE.get("worktree_content_status") != "complete"
            or not isinstance(RUN_SOURCE_PROVENANCE.get(
                "worktree_content_digest"), str)):
        RUN_SOURCE_PROVENANCE_AT_END = dict(RUN_SOURCE_PROVENANCE)
        _persist_source_provenance_preflight(
            initial=RUN_SOURCE_PROVENANCE,
            observed=RUN_SOURCE_PROVENANCE)
        raise RootlessExperimentalError(
            "source_provenance_incomplete_before_run_allocation")
    _set_run_stage("model_and_runtime_preflight")
    (campaign_plan, campaign_prior_boundary_digest,
        campaign_prior_admission_boundary, campaign_prior_recovery_boundary) = (
            _validate_history_campaign_launch())
    if pair_execution_context is not None:
        from work.rootless_history_boundary_campaign import (
            _cognition_recovery_state_boundary,
        )
        prior_state_root = pair_execution_context[
            "prior_history_root"].parent / "state"
        campaign_prior_admission_boundary = _runtime_admission_ledger_boundary(
            prior_state_root / "runtime_admissions.json")
        campaign_prior_recovery_boundary = (
            _cognition_recovery_state_boundary(prior_state_root))
    if campaign_plan is not None:
        ACTIVE_HISTORY_CAMPAIGN_BINDING = {
            "campaign_id": campaign_plan["campaign_id"],
            "campaign_plan_digest": campaign_plan["plan_digest"],
            "cycle_index": campaign_plan["ordered_cycle_ids"].index(RUN_ID),
        }
        if isinstance(campaign_plan.get(
                "cross_range_history_enabled_competence"), Mapping):
            ACTIVE_HISTORY_CAMPAIGN_BINDING[
                "cross_range_history_enabled_competence"] = dict(
                    campaign_plan["cross_range_history_enabled_competence"])
        if WIDE_TRANSFER_PROBE_PREFLIGHT is not None:
            ACTIVE_HISTORY_CAMPAIGN_BINDING["transfer_probe_preflight"] = dict(
                WIDE_TRANSFER_PROBE_PREFLIGHT)
    manifest_path = _resolve_pinned_model_manifest_path()
    preexisting_residency = _model_residency_observed(MODEL_NAME)
    if preexisting_residency is None:
        raise RootlessExperimentalError("ollama_model_residency_unavailable")
    if preexisting_residency:
        raise RootlessExperimentalError("pinned_hermes_already_resident")
    manifest_digest, manifest_size = stream_sha256(manifest_path)
    model_weight_bytes = _model_weight_bytes(manifest_path)
    if manifest_digest != manifest_path.stem:
        raise RootlessExperimentalError("pinned_hermes_manifest_digest_mismatch")
    gpu_owner_availability = _require_gpu_owner_availability_confirmation()
    if pair_execution_context is not None:
        _preflight_historical_pair_model_identity(
            context=pair_execution_context, manifest_path=manifest_path,
            manifest_digest=manifest_digest, manifest_size=manifest_size)
        # A planned slot must remain reusable if the GPU is unavailable or
        # already busy. This direct check runs before creating its one-shot
        # run root; the governed coordinator and per-call guard still repeat
        # the authoritative resource checks before any inference.
        scheduling_snapshot = _gpu_snapshot()
        _require_gpu_headroom(scheduling_snapshot, model_weight_bytes)
        utilization = (scheduling_snapshot.get("gpu_utilization_percent")
            if isinstance(scheduling_snapshot, Mapping) else None)
        if (type(utilization) is not int
                or utilization > _MAX_PREINFERENCE_GPU_UTILIZATION_PERCENT):
            raise RootlessExperimentalError(
                "historical_examples_pair_gpu_busy_before_slot_allocation")
    # Resolve all no-load pinning and scheduling evidence before optional
    # runtime dependencies. A missing telemetry/scoring package must not hide
    # a stale model identity; dependency enforcement still precedes run-root
    # allocation and every model load.
    _require_experiment_runtime_dependencies()
    source_provenance_at_start = _source_provenance()
    if (source_provenance_at_start != RUN_SOURCE_PROVENANCE
            or source_provenance_at_start.get("observation_status") != "observed"
            or source_provenance_at_start.get("worktree_content_status") != "complete"
            or not isinstance(source_provenance_at_start.get(
                "worktree_content_digest"), str)):
        RUN_SOURCE_PROVENANCE_AT_END = source_provenance_at_start
        _persist_source_provenance_preflight(
            initial=RUN_SOURCE_PROVENANCE, observed=source_provenance_at_start)
        raise RootlessExperimentalError(
            "source_provenance_incomplete_or_changed_before_run_allocation")
    RUN_ROOT.mkdir(parents=True, exist_ok=False, mode=0o700)
    _no_symlink_path(RUN_ROOT)
    if historical_pair_context is not None:
        preload_binding_digest = _persist_historical_pair_preload_binding(
            historical_pair_context)
        if preload_binding_digest is not None:
            historical_pair_context["identity_neutral_preload_binding_digest"] = (
                preload_binding_digest)
    history_root, state_root = _prepare_resident_cognition_roots(RUN_ROOT)
    HISTORY_SEED_EVIDENCE = {
        "schema_version": "sentientos.rootless_developmental_history_seed:v3",
        "status": "configured_seed_incomplete",
        "record_count": 0,
        "receipt_count": 0,
        "source_boundary_digest": None,
        "copied_into_run_store": False,
        "source_runtime_admission_ledger": None,
        "runtime_admission_ledger_copied": False,
        "source_cognition_recovery_state": None,
        "cognition_recovery_state_copied": False,
        "model_attention_verified": False,
    }
    HISTORY_SEED_EVIDENCE = _seed_resident_developmental_history(
        history_root, state_root, campaign_prior_admission_boundary,
        campaign_prior_recovery_boundary)
    if campaign_plan is not None:
        prior_history_raw = os.environ.get(
            "SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT")
        if (not isinstance(prior_history_raw, str)
                or campaign_prior_boundary_digest is None):
            raise RootlessExperimentalError(
                "history_campaign_seed_copy_binding_unavailable")
        _verify_history_campaign_seed_copy(
            source_root=Path(prior_history_raw).expanduser(),
            destination_root=history_root, destination_state_root=state_root,
            expected_boundary_digest=campaign_prior_boundary_digest,
            expected_admission_boundary=campaign_prior_admission_boundary,
            expected_recovery_boundary=campaign_prior_recovery_boundary)
    _set_run_stage(RUN_STAGE)
    try:
        ConsequenceStore._require_secure_platform()
    except EmbodiedConsequenceError as exc:
        raise RootlessExperimentalError(
            "synthetic_consequence_store_secure_platform_unavailable") from exc
    runtime, runtime_sha = _runtime_observation(manifest_digest)
    binding = {"schema_version": "sentientos.rootless_experimental_cognition_session:v1",
        "session_id": "rootless-cognition-session-" + uuid.uuid4().hex[:20],
        "run_id": RUN_ID, "preregistration_digest": "0" * 64,
        "model_manifest_digest": manifest_digest,
        "runtime_bundle_digest": runtime_sha,
        "active_model_identity_digest": "0" * 64,
        "purpose": ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_PURPOSE,
        "production_authority": False,
        "eligible_as_production_serving_evidence": False}
    before_gpu = _require_gpu_headroom(_gpu_snapshot(), model_weight_bytes)
    kernel, resource_coordinator = _enforcing_resource_runtime()
    initial_resource_evidence = _refresh_resource_evidence(resource_coordinator,
        correlation_id=f"{RUN_ID}-initial-preflight")
    initial_resource_evidence["gpu_owner_availability_confirmation"] = (
        gpu_owner_availability)
    initial_resource_evidence["gpu_layers_requested"] = GPU_LAYERS
    initial_gpu = _require_gpu_headroom(_gpu_snapshot(), model_weight_bytes)
    initial_resource_evidence["gpu_memory_free_mib"] = initial_gpu["memory_free_mib"]
    initial_resource_evidence["gpu_memory_total_mib"] = initial_gpu["memory_total_mib"]
    inference_resource_evidence = RESOURCE_PREFLIGHT_EVIDENCE
    session = RootlessExperimentalOllamaDevelopmentalSession(
        model_manifest_path=manifest_path, model_name=MODEL_NAME,
        root=RUN_ROOT, session_binding=binding,
        kernel_factory=lambda _: kernel, gpu_layers=GPU_LAYERS)
    session.invoker = cast(Any, _ResourceGuardedInvoker(
        session.invoker, resource_coordinator, model_weight_bytes,
        inference_resource_evidence, model_name=MODEL_NAME,
        gpu_layers=GPU_LAYERS))
    # Bind the actual execution to the fixed external protocol before its first
    # inference. The session owner computes and verifies its run-specific digest.
    if PREREGISTRATION_DIGEST != "0" * 64:
        preregistration = {
            "schema_version": "sentientos.rootless_hermes_cycle_preregistration:v1",
            "external_protocol_digest": PREREGISTRATION_DIGEST,
            "experiment_seed": EXPERIMENT_SEED,
            "history_order_trial_index": HISTORY_INTERVENTION_TRIAL_INDEX,
            "run_id": RUN_ID,
            "session_id": binding["session_id"],
            "model_manifest_digest": manifest_digest,
            "gpu_layers_requested": GPU_LAYERS,
            "runtime_bundle_digest": runtime_sha,
            "model_identity": session.active_model_identity,
            "model_configuration_observation":
                session.active_model_configuration_observation,
            "source_provenance": RUN_SOURCE_PROVENANCE,
            "prior_developmental_history_seed": dict(HISTORY_SEED_EVIDENCE),
            "history_campaign_binding": ({
                "campaign_id": campaign_plan["campaign_id"],
                "campaign_plan_digest": campaign_plan["plan_digest"],
                "cycle_index": campaign_plan["ordered_cycle_ids"].index(RUN_ID),
                **({"transfer_probe_preflight": dict(
                    WIDE_TRANSFER_PROBE_PREFLIGHT)}
                    if WIDE_TRANSFER_PROBE_PREFLIGHT is not None else {}),
            } if campaign_plan is not None else None),
        }
        preregistration["preregistration_digest"] = runtime_digest(preregistration)
        preregistration_path = RUN_ROOT / "preregistration.json"
        _no_symlink_path(preregistration_path)
        preregistration_flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0))
        preregistration_descriptor = os.open(preregistration_path,
            preregistration_flags, 0o600)
        with os.fdopen(preregistration_descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(preregistration, sort_keys=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        session.bind_preregistration_digest(preregistration["preregistration_digest"])
        RUN_PREREGISTRATION_DIGEST = preregistration["preregistration_digest"]
    else:
        # Bind the session to the identity actually loaded by the governed worker.
        session.session_binding["active_model_identity_digest"] = digest_payload(
            {"identity": session.active_model_identity})
    try:
        if campaign_plan is not None:
            cycle_index = campaign_plan["ordered_cycle_ids"].index(RUN_ID)
            expected_identity_digest = (
                campaign_plan["ordered_model_identity_digests"][cycle_index]
                if campaign_plan.get("schema_version") in {
                    "sentientos.rootless_history_boundary_campaign_plan:v5",
                    "sentientos.rootless_history_boundary_campaign_plan:v6",
                    "sentientos.rootless_history_boundary_campaign_plan:v7",
                    "sentientos.rootless_history_boundary_campaign_plan:v8",
                    "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13"}
                else campaign_plan["model_identity_digest"])
            if (digest_payload({"identity": session.active_model_identity})
                    != expected_identity_digest):
                raise RootlessExperimentalError(
                    "history_campaign_model_identity_mismatch")
        _set_run_stage("synthetic_pre_action_cognition")
        ledger = AdmissionLedger(state_root / "runtime_admissions.json")

        def current_sequence() -> int:
            admissions, _ = ledger.load()
            return max((item.issued_sequence for item in admissions), default=0)

        def next_sequence() -> int:
            admissions, revocations = ledger.load()
            return max([item.issued_sequence for item in admissions]
                + [item.sequence for item in revocations], default=0) + 1

        definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
            RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
        writeback = ResidentDevelopmentalWritebackController(
            history_root=history_root,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions=definitions, ledger=ledger),
            current_sequence=current_sequence)
        if pair_execution_context is not None:
            from scripts.preflight_resident_strategy_inclusion_pair import (
                _source_kinds_from_history,
            )
            allowed_source_kinds = _source_kinds_from_history(history_root)
            selected_fact_limit, retrieved_record_limit = 32, 8
            history_order_trial_index = None
            cognition_timeout = pair_execution_context["source_timeout_seconds"]
            cognition_input_limit = pair_execution_context[
                "source_max_input_chars"]
        else:
            allowed_source_kinds = ("embodiment",)
            selected_fact_limit, retrieved_record_limit = 16, 4
            history_order_trial_index = HISTORY_INTERVENTION_TRIAL_INDEX
            cognition_timeout = (
                ROOTLESS_DEVELOPMENTAL_COGNITION_INFERENCE_TIMEOUT_SECONDS)
            cognition_input_limit = ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT
        owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root, state_root, allowed_source_kinds,
                selected_fact_limit, retrieved_record_limit, True,
                max_inference_input_chars=cognition_input_limit,
                max_inference_timeout_seconds=cognition_timeout,
                objective_history_order_trial_index=history_order_trial_index),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)
        if pair_execution_context is not None:
            if pair_execution_context.get("mode") == "negative_guidance":
                return _execute_negative_guidance_pair_slot(
                    context=pair_execution_context, owner=owner, session=session,
                    history_seed_evidence=HISTORY_SEED_EVIDENCE,
                    runtime_bundle_digest=runtime_sha,
                    resource_preflight_evidence=initial_resource_evidence,
                    invocation_resource_evidence=inference_resource_evidence,
                    source_provenance_at_start=source_provenance_at_start)
            if pair_execution_context.get("mode") == "strategy_inclusion":
                return _execute_strategy_inclusion_pair_slot(
                    context=pair_execution_context, owner=owner, session=session,
                    history_seed_evidence=HISTORY_SEED_EVIDENCE,
                    runtime_bundle_digest=runtime_sha,
                    resource_preflight_evidence=initial_resource_evidence,
                    invocation_resource_evidence=inference_resource_evidence,
                    source_provenance_at_start=source_provenance_at_start)
            return _execute_historical_pair_slot(
                context=pair_execution_context, owner=owner, session=session,
                history_seed_evidence=HISTORY_SEED_EVIDENCE,
                runtime_bundle_digest=runtime_sha,
                resource_preflight_evidence=initial_resource_evidence,
                invocation_resource_evidence=inference_resource_evidence,
                source_provenance_at_start=source_provenance_at_start)
        # The model produces a bounded proposal and predicted observation from
        # pre-action proprioception. A separate synthetic actor consumes that
        # proposal; the model itself still has no action authority.
        pre_action_snapshot, pre_action_proprioception = _pre_action_source()
        pre_action_scenario_fixture = (
            _synthetic_pre_action_scenario_observation())
        pre_action_target_observation = (
            _synthetic_current_target_observation())
        pre_action_snapshot = WorldStateBoardBuilder().build(
            EmbodimentEvidenceOwner([pre_action_proprioception,
                pre_action_scenario_fixture,
                pre_action_target_observation]).world_state_records())
        pre_action_at = datetime.now(timezone.utc)
        decision_owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root, state_root, ("embodiment",), 16, 4, False,
                max_inference_input_chars=(
                    ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT),
                max_inference_timeout_seconds=(
                    ROOTLESS_DEVELOPMENTAL_COGNITION_INFERENCE_TIMEOUT_SECONDS)),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)
        decision_bridge = ResidentDevelopmentalCompanionBridge(
            decision_owner,
            proprioception_provider=lambda: (pre_action_scenario_fixture,
                pre_action_target_observation),
            clock=lambda: pre_action_at)
        cognitive_decision = _verified_companion_replay(
            decision_bridge, decision_owner,
            request_id=RUN_ID + ":pre-action-decision",
            question=PRE_ACTION_DECISION_QUESTION,
            withhold_developmental_history=True)
        continue_after_no_action = False
        clarification_attempt: dict[str, Any] | None = None
        if (cognitive_decision.get("status") == "admitted_completed"
                and cognitive_decision.get("response_lineage_verified") is True
                and cognitive_decision.get("disposition") == "ask"):
            ask_text = cognitive_decision.get("validated_response")
            initial_ask = _bounded_pre_action_decision_diagnostic(
                cognitive_decision)
            ask_text_size = None
            if isinstance(ask_text, str):
                try:
                    ask_text_size = len(ask_text.encode("utf-8"))
                except UnicodeEncodeError:
                    pass
            clarification_attempt = {
                "schema_version": "sentientos.pre_action_clarification_attempt:v2",
                "status": "not_run",
                "initial_ask": initial_ask,
                "initial_ask_capture": _bounded_pre_action_ask_capture(
                    cognitive_decision),
                "ask_text_capture_is_bounded_and_untrusted": True,
                "authority": False,
            }
            if (isinstance(ask_text, str) and ask_text.strip()
                    and ask_text_size is not None and ask_text_size <= 1024):
                clarification_question = (
                    _pre_action_clarification_question(ask_text))
                clarification_question_chars = len(clarification_question)
                clarification_attempt[
                    "clarification_question_chars"] = clarification_question_chars
                if clarification_question_chars <= (
                        MAX_COGNITION_REQUEST_QUESTION_CHARS):
                    refresh_at = datetime.now(timezone.utc)
                    refresh_observation = (
                        _synthetic_current_target_refresh_observation(
                            observed_at=refresh_at.isoformat()))
                    refresh_bridge = ResidentDevelopmentalCompanionBridge(
                        decision_owner,
                        proprioception_provider=lambda: (
                            pre_action_scenario_fixture, refresh_observation),
                        clock=lambda: refresh_at)
                    clarification_attempt["sensor_refresh"] = {
                        "schema_version": (
                            "sentientos.synthetic_sensor_refresh:v1"),
                        "source_id": refresh_observation.source_id,
                        "source_schema": refresh_observation.source_schema,
                        "source_digest": refresh_observation.source_digest,
                        "observed_at": refresh_observation.observed_at,
                        "provenance_class": (
                            refresh_observation.provenance_class),
                        "evidence_class": refresh_observation.evidence_class,
                        "synthetic": True,
                        "physical_world_observation": False,
                        "authority": False,
                    }
                    followup_decision = _verified_companion_replay(
                        refresh_bridge, decision_owner,
                        request_id=RUN_ID + ":pre-action-clarification",
                        question=clarification_question,
                        withhold_developmental_history=True)
                    followup_diagnostic = (
                        _bounded_pre_action_decision_diagnostic(
                            followup_decision))
                    initial_projection = (
                        initial_ask.get("current_projection_digest")
                        if isinstance(initial_ask, Mapping) else None)
                    followup_projection = (
                        followup_diagnostic.get("current_projection_digest")
                        if isinstance(followup_diagnostic, Mapping) else None)
                    projection_changed = (
                        initial_projection != followup_projection
                        if isinstance(initial_projection, str)
                        and isinstance(followup_projection, str) else None)
                    response_unchanged = (
                        initial_ask.get("response_digest")
                            == followup_diagnostic.get("response_digest")
                        if isinstance(initial_ask, Mapping)
                        and isinstance(followup_diagnostic, Mapping) else None)
                    if (followup_decision.get("disposition") == "ask"
                            and projection_changed is True
                            and response_unchanged is True):
                        followup_outcome = (
                            "repeated_ask_after_new_current_projection")
                    elif (followup_decision.get("disposition") == "ask"
                            and projection_changed is True):
                        followup_outcome = "new_ask_after_current_projection"
                    elif followup_decision.get("disposition") == "ask":
                        followup_outcome = "ask_without_verified_projection_change"
                    elif followup_decision.get("disposition") == "answer":
                        followup_outcome = "answer_after_refresh"
                    elif followup_decision.get("disposition") == "abstain":
                        followup_outcome = "abstain_after_refresh"
                    else:
                        followup_outcome = "followup_unverified"
                    clarification_attempt.update({
                        "status": "attempted",
                        "followup_decision": followup_diagnostic,
                        "followup_ask_capture": (
                            _bounded_pre_action_ask_capture(followup_decision)),
                        "followup_outcome": followup_outcome,
                        "current_projection_changed": projection_changed,
                        "response_digest_unchanged": response_unchanged,
                    })
                    cognitive_decision = followup_decision
                else:
                    clarification_attempt["status"] = (
                        "not_run_clarification_question_over_owner_limit")
            else:
                clarification_attempt["status"] = (
                    "not_run_ask_text_missing_or_over_bound")
        if (cognitive_decision.get("status") != "admitted_completed"
                or cognitive_decision.get("response_lineage_verified") is not True
                or cognitive_decision.get("disposition") != "answer"
                or not cognitive_decision.get("evidence_ids")):
            rejection_diagnostic = cognitive_decision.get(
                "rejection_diagnostic")
            if isinstance(rejection_diagnostic, Mapping):
                RUN_FAILURE_DIAGNOSTIC = dict(rejection_diagnostic)
            else:
                RUN_FAILURE_DIAGNOSTIC = (
                    _bounded_pre_action_decision_diagnostic(
                        cognitive_decision))
            bounded_decision = (RUN_FAILURE_DIAGNOSTIC
                if isinstance(RUN_FAILURE_DIAGNOSTIC, Mapping) else {})
            decision_disposition = bounded_decision.get("disposition")
            decision_status = bounded_decision.get("status")
            if (decision_status == "admitted_completed"
                    and bounded_decision.get("response_lineage_verified") is True
                    and decision_disposition in {"ask", "abstain"}):
                decision_classification = (
                    "owner_admitted_ask_no_action"
                    if decision_disposition == "ask" else
                    "owner_admitted_abstain_no_action")
            elif decision_status == "admitted_completed":
                decision_classification = "owner_admitted_decision_unusable"
            else:
                decision_classification = "decision_not_verified_no_action"
            PRE_ACTION_DECISION_EVIDENCE = {
                "schema_version": "sentientos.pre_action_decision_evidence:v5",
                "classification": decision_classification,
                "interaction_status": decision_status,
                "disposition": decision_disposition,
                "response_digest": bounded_decision.get("response_digest"),
                "response_lineage_verified": (
                    bounded_decision.get("response_lineage_verified") is True),
                "evidence_ids": (list(bounded_decision.get("evidence_ids", []))
                    if isinstance(bounded_decision.get("evidence_ids"), list)
                    else []),
                "history_record_ids": list(
                    bounded_decision.get("history_record_ids", [])
                    if isinstance(bounded_decision.get(
                        "history_record_ids", []), list) else []),
                "clarification_attempt": clarification_attempt,
                "authority": False,
                "action_executed": False,
                "synthetic_action_simulated": False,
            }
            can_continue_without_action = (
                decision_status == "admitted_completed"
                and bounded_decision.get("response_lineage_verified") is True
                and decision_disposition in {"ask", "abstain"})
            if can_continue_without_action:
                continue_after_no_action = True
                RUN_FAILURE_DIAGNOSTIC = None
            else:
                raise RootlessExperimentalError(
                    "pre_action_cognition_proposal_unverified: "
                    + json.dumps({
                        "status": cognitive_decision.get("status"),
                        "owner_rejection_code": cognitive_decision.get(
                            "failure_code"),
                        "lineage": cognitive_decision.get(
                            "response_lineage_verified"),
                        "disposition": cognitive_decision.get("disposition"),
                        "evidence_ids": cognitive_decision.get("evidence_ids"),
                        "history_record_ids": cognitive_decision.get(
                            "history_record_ids"),
                        "response_digest": cognitive_decision.get(
                            "response_digest"),
                        "raw_response_included": False,
                    }, sort_keys=True))
        first = None
        durable = None
        if continue_after_no_action:
            decision_response = None
            proposal = None
            prediction_consistent = None
            evidence = {
                "schema_version": "sentientos.no_action_cognition_continuation_evidence:v1",
                "classification": "owner_ask_or_abstention_no_action",
                "pre_action_decision_classification": (
                    PRE_ACTION_DECISION_EVIDENCE.get("classification")),
                "clarification_outcome": (
                    PRE_ACTION_DECISION_EVIDENCE.get(
                        "clarification_attempt", {}).get("followup_outcome")
                    if isinstance(PRE_ACTION_DECISION_EVIDENCE.get(
                        "clarification_attempt"), Mapping) else None),
                "action_executed": False,
                "synthetic_action_simulated": False,
                "physical_observation_established": False,
                "authority": False,
            }
            PRE_ACTION_DECISION_EVIDENCE["non_actuating_cognition_continuation"] = {
                "status": "continued_to_independent_objective_task_family",
                "objective_task_action_authority": False,
                "action_gate_remained_closed": True,
                "consequence_record_created": False,
            }
        else:
            decision_response = cognitive_decision.get("validated_response")
            proposal = _pose_decision_from_response(decision_response)
            prediction_consistent = None
            if proposal is not None:
                expected_prediction = {"reach": "reach", "idle": "idle"}[
                    proposal["requested_pose"]]
                prediction_consistent = (
                    proposal["predicted_pose"] == expected_prediction)
            if proposal is None:
                decision_classification = "invalid_or_noncanonical_token"
            elif prediction_consistent is not True:
                decision_classification = "prediction_inconsistent_with_fixture"
            elif proposal["requested_pose"] != "reach":
                decision_classification = "goal_not_met"
            else:
                decision_classification = "goal_met_ready_for_synthetic_action"
            PRE_ACTION_DECISION_EVIDENCE = {
                    "schema_version": "sentientos.pre_action_decision_evidence:v5",
                "classification": decision_classification,
                "response_digest": cognitive_decision.get("response_digest"),
                "response_size_bytes": (
                    len(decision_response.encode("utf-8"))
                    if isinstance(decision_response, str) else None),
                "requested_pose": (proposal["requested_pose"]
                    if proposal is not None else None),
                "predicted_pose": (proposal["predicted_pose"]
                    if proposal is not None else None),
                "prediction_consistent": prediction_consistent,
                "response_lineage_verified": True,
                "developmental_history_posture": (
                    "explicitly_withheld_for_synthetic_preaction_decision"),
                "evidence_ids": list(cognitive_decision["evidence_ids"]),
                "history_record_ids": list(cognitive_decision.get(
                    "history_record_ids", [])),
                "clarification_attempt": clarification_attempt,
                "authority": False,
                "action_executed": False,
                "synthetic_action_simulated": False,
            }
            if proposal is None:
                raise RootlessExperimentalError("pre_action_cognition_proposal_invalid")
            if prediction_consistent is not True:
                raise RootlessExperimentalError(
                    "pre_action_prediction_inconsistent_with_deterministic_fixture")
            snapshot, evidence, proprioception = _embodied_source(
                requested_pose=proposal["requested_pose"],
                predicted_pose=proposal["predicted_pose"])
            PRE_ACTION_DECISION_EVIDENCE["synthetic_action_simulated"] = True
            PRE_ACTION_DECISION_EVIDENCE["task_goal"] = evidence["task_goal"]
            PRE_ACTION_DECISION_EVIDENCE["task_goal_met"] = evidence["task_goal_met"]
            PRE_ACTION_DECISION_EVIDENCE["task_goal_evaluation_posture"] = (
                evidence["task_goal_evaluation_posture"])
            PRE_ACTION_DECISION_EVIDENCE["observer_fixture_posture"] = (
                evidence["observer_fixture_posture"])
            PRE_ACTION_DECISION_EVIDENCE["observer_key_custody_posture"] = (
                evidence["observer_key_custody_posture"])
            PRE_ACTION_DECISION_EVIDENCE["physical_observation_established"] = (
                evidence["physical_observation_established"])
            _set_run_stage("governed_developmental_writeback")
            first = owner.run_tick(snapshot=snapshot, tick_id=RUN_ID + ":consequence")
            if first.status == "writeback_deferred":
                raise RootlessExperimentalError(
                    "governed_developmental_writeback_deferred_under_host_pressure")
            if not first.written_record_id:
                raise RootlessExperimentalError("governed_developmental_writeback_not_created")
            durable = owner.writeback.store.get(first.written_record_id)
        # Follow the hand-written decision probe with the resident owner's
        # preregistered exact-scored task-family path. This keeps the model's
        # later transfer decision tied to retained, oracle-scored history
        # rather than treating a plausible conversational difference as
        # evidence of improved performance.
        _set_run_stage("objective_task_family_acquisition")
        later_pre_action_snapshot = _objective_task_source()
        existing_history = owner.writeback.inspect_completed_records()
        INITIAL_HISTORY_BOOTSTRAP_EVIDENCE = {
            "schema_version": "sentientos.initial_history_bootstrap_evidence:v1",
            "status": "skipped_existing_history" if existing_history else "pending",
            "existing_record_count": len(existing_history),
            "created_record_id": None,
            "created_record_digest": None,
            "snapshot_digest": later_pre_action_snapshot.digest,
            "writeback_receipt_id": None,
            "writeback_receipt_digest": None,
            "cognition_observation_id": None,
            "cognition_observation_digest": None,
            "prior_history_withheld": None,
            "score_bound": False,
            "learning_established": False,
            "authority": False,
        }
        if not existing_history:
            # A clean history store otherwise cannot enter the exact-scored
            # acquisition path: its generic objective guard requires at least
            # one eligible record. Seed only from an explicitly history-free
            # developmental observation, then let the separate scored task
            # produce the first task-family record.
            _set_run_stage("initial_history_bootstrap")
            bootstrap = decision_owner.run_tick(
                snapshot=later_pre_action_snapshot,
                tick_id=RUN_ID + ":initial-history-bootstrap",
                withhold_developmental_history=True,
                durable_learning_no_history_observation=True)
            bootstrap_records = owner.writeback.inspect_completed_records()
            bootstrap_record_pair = next((pair for pair in bootstrap_records
                if pair[0].record_id == bootstrap.written_record_id), None)
            bootstrap_observation = (
                decision_owner.verified_cognition_observation(
                    bootstrap.cognition_observation_ids[0])
                if len(bootstrap.cognition_observation_ids) == 1 else None)
            bootstrap_receipt = (
                decision_owner.verified_cognition_invocation_receipt(
                    bootstrap.cognition_observation_ids[0],
                    bootstrap_observation.get("observation_digest"))
                if isinstance(bootstrap_observation, Mapping) else None)
            if (bootstrap.status != "completed"
                    or not isinstance(bootstrap.written_record_id, str)
                    or not isinstance(bootstrap.writeback_receipt_id, str)
                    or len(bootstrap.cognition_observation_ids) != 1
                    or bootstrap_record_pair is None
                    or bootstrap_record_pair[1].receipt_id
                        != bootstrap.writeback_receipt_id
                    or not isinstance(bootstrap_observation, Mapping)
                    or bootstrap_observation.get("condition_id")
                        != "durable-learning-history-withheld"
                    or bootstrap_observation.get("retrieved_record_ids") != []
                    or bootstrap_observation.get("current_snapshot_digest")
                        != later_pre_action_snapshot.digest
                    or bootstrap_observation.get(
                        "developmental_projection_present") is not False
                    or not isinstance(bootstrap_receipt, Mapping)
                    or bootstrap_receipt.get("receipt_id")
                        != bootstrap_observation.get("inference_receipt_id")
                    or len(bootstrap_records) != 1):
                INITIAL_HISTORY_BOOTSTRAP_EVIDENCE.update({
                    "status": "failed_verification",
                    "observed_record_count": len(bootstrap_records),
                    "prior_history_withheld": True,
                })
                RUN_FAILURE_DIAGNOSTIC = {
                    "stage": "initial_history_bootstrap",
                    "bootstrap_status": bootstrap.status,
                    "observed_record_count": len(bootstrap_records),
                    "cognition_observation_count": len(
                        bootstrap.cognition_observation_ids),
                    "raw_model_output_included": False,
                    "learning_established": False,
                    "authority": False,
                }
                raise RootlessExperimentalError(
                    "initial_history_bootstrap_not_verified")
            bootstrap_record, bootstrap_writeback_receipt = bootstrap_record_pair
            INITIAL_HISTORY_BOOTSTRAP_EVIDENCE.update({
                "status": "created_verified_history_free_seed",
                "observed_record_count": len(bootstrap_records),
                "created_record_id": bootstrap_record.record_id,
                "created_record_digest": bootstrap_record.record_digest,
                "selected_fact_count": len(bootstrap.selected_fact_ids),
                "retrieved_prior_record_count": len(
                    bootstrap_observation.get("retrieved_record_ids", ())),
                "writeback_receipt_id": bootstrap_writeback_receipt.receipt_id,
                "writeback_receipt_digest": (
                    bootstrap_writeback_receipt.receipt_digest),
                "cognition_observation_id": bootstrap_observation.get(
                    "observation_id"),
                "cognition_observation_digest": bootstrap_observation.get(
                    "observation_digest"),
                "inference_receipt_id": bootstrap_receipt.get("receipt_id"),
                "inference_receipt_digest": bootstrap_receipt.get(
                    "receipt_digest"),
                "prior_history_withheld": True,
            })
        _set_run_stage("objective_task_family_acquisition")
        objective_family = _ACTIVE_OBJECTIVE_TRANSFER_TASK_FAMILY
        acquisition_task, transfer_task = _objective_task_pair(EXPERIMENT_SEED)
        acquisition_request_id = RUN_ID + ":objective-family-acquisition"
        stage_objective_request(
            state_root, request_id=acquisition_request_id, task=acquisition_task)
        acquisition_request = load_objective_request(state_root)
        if acquisition_request is None:
            raise RootlessExperimentalError("objective_family_acquisition_request_missing")
        acquisition_result = owner.run_objective_intervention_once(
            snapshot=later_pre_action_snapshot,
            tick_id=RUN_ID + ":objective-family-acquisition",
            objective_task=acquisition_task,
            request_id=acquisition_request_id,
            request_digest=acquisition_request["request_digest"])
        if (acquisition_result.status != "objective_intervention_completed"
                or not acquisition_result.changed_cognition_measurement_id):
            # Preserve the owner's bounded terminal status in the failure
            # artifact. In particular, an empty developmental store blocks
            # this history-required acquisition before inference; a generic
            # runner error otherwise hides that bootstrap deadlock.
            RUN_FAILURE_DIAGNOSTIC = {
                "stage": "objective_task_family_acquisition",
                "owner_status": acquisition_result.status,
                "prior_record_count": len(
                    acquisition_result.prior_record_ids),
                "measurement_created": bool(
                    acquisition_result.changed_cognition_measurement_id),
                "raw_model_output_included": False,
                "learning_established": False,
                "authority": False,
            }
            raise RootlessExperimentalError("objective_family_acquisition_incomplete")
        acquisition_run = owner.experiments.load_run(
            acquisition_result.changed_cognition_measurement_id)
        acquisition_readiness = _objective_family_acquisition_readiness(acquisition_run)
        acquisition_readiness_diagnostics = (
            _objective_family_acquisition_readiness_diagnostics(
                acquisition_run, acquisition_readiness))
        cross_range_protocol = (ACTIVE_HISTORY_CAMPAIGN_BINDING.get(
            "cross_range_history_enabled_competence")
            if isinstance(ACTIVE_HISTORY_CAMPAIGN_BINDING, Mapping) else None)
        cross_range_eligibility: dict[str, Any] = {
            "eligible": False,
            "status": ("not_preregistered" if cross_range_protocol is None
                else "not_assessed"),
            "inference_performed": False,
            "learning_established": False,
            "authority": False,
        }
        objective_cross_range_history_probe: dict[str, Any] = {
            "status": cross_range_eligibility["status"],
            "protocol": (dict(cross_range_protocol)
                if isinstance(cross_range_protocol, Mapping) else None),
            "eligibility": dict(cross_range_eligibility),
            "inference_performed": False,
            "capability_evaluated": False,
            "learning_established": False,
            "causal_claim_made": False,
            "authority": False,
        }
        if isinstance(cross_range_protocol, Mapping):
            cross_range_eligibility = (
                _cross_range_history_competence_eligibility(
                    owner=owner, transfer_task=transfer_task,
                    source_task_family_id=cross_range_protocol[
                        "source_task_family_id"],
                    target_model_identity=session.active_model_identity))
            objective_cross_range_history_probe.update({
                "status": cross_range_eligibility["status"],
                "eligibility": dict(cross_range_eligibility),
            })
        objective_transfer_evaluation: dict[str, Any] = {
            "assessment": "not_run_no_eligible_acquisition_examples",
            "history_correct_probe_delta": None,
            "restoration_correct_probe_delta": None,
            "condition_correct_counts": None,
            "probe_count": acquisition_readiness["required_probe_count"],
        }
        objective_transfer_history_selection_preflight: dict[str, Any] = {
            "status": "not_run_no_eligible_acquisition_examples",
            "inference_performed": False,
            "learning_established": False,
            "authority": False,
        }
        objective_transfer_history: dict[str, Any] = {
            "status": "skipped_acquisition_outputs_unusable",
            "task_family_id": objective_family,
            "acquisition_history_projection_audit": None,
            "acquisition_measurement_id": acquisition_result.changed_cognition_measurement_id,
            "acquisition_score_status": acquisition_readiness["score_status"],
            "acquisition_readiness_classification": acquisition_readiness["classification"],
            "acquisition_probe_result_count": acquisition_readiness["probe_result_count"],
            "required_probe_count": acquisition_readiness["required_probe_count"],
            "acquisition_readiness_diagnostics": acquisition_readiness_diagnostics,
            "acquisition_history_record_id": None,
            "transfer_history_record_id": None,
            "longitudinal_progression_status": "not_run_no_eligible_acquisition_examples",
            "longitudinal_episode_count": 0,
            "history_correct_probe_delta": None,
            "restoration_correct_probe_delta": None,
            "condition_correct_counts": None,
            "task_family_history_lineage_verified": False,
            "conditions": [],
            "authority": False,
            "action_executed": False,
            "performance_improvement_established": False,
            "scope": "single_model_synthetic_exact_scored_task_family_transfer",
        }
        acquisition_history_record = None
        acquisition_summary: dict[str, Any] | None = None
        acquisition_history_projection_audit: dict[str, Any] | None = None
        acquisition_history_score_binding: dict[str, Any] | None = None
        if acquisition_readiness["eligible"]:
            acquisition_summary = _objective_acquisition_summary(acquisition_run)
            acquisition_records = owner.experiments.world_state_records(run_refs=((
                acquisition_run["run_id"], acquisition_run["run_digest"]),))
            if len(acquisition_records) != 1:
                raise RootlessExperimentalError("objective_family_acquisition_projection_invalid")
            acquisition_world = WorldStateBoardBuilder().build(acquisition_records)
            acquisition_writeback = owner.run_tick(snapshot=acquisition_world,
                tick_id=RUN_ID + ":objective-family-acquisition-writeback")
            if not acquisition_writeback.written_record_id:
                raise RootlessExperimentalError("objective_family_acquisition_writeback_missing")
            acquisition_history_record = owner.writeback.store.get(
                acquisition_writeback.written_record_id)
            if not any(isinstance(fact, Mapping)
                    and isinstance(fact.get("payload"), Mapping)
                    and fact["payload"].get("objective_task_family") == objective_family
                    for fact in acquisition_history_record.candidate.get("selected_facts", [])):
                raise RootlessExperimentalError("objective_family_history_not_retained")
            acquisition_history_projection_audit = (
                audit_task_family_history_projection(
                    acquisition_history_record.candidate,
                    task_family_id=objective_family,
                    target_model_identity=session.active_model_identity,
                    source_run_id=acquisition_run["run_id"]))
            source_projection = acquisition_history_projection_audit.get(
                "source_run_score_projection")
            expected_score_digest = acquisition_summary.get(
                "history_present_score_digest")
            expected_counts = {
                "example_count": acquisition_summary.get("probe_count"),
                "correct_example_count": acquisition_summary.get(
                    "retained_accurate_example_count"),
                "incorrect_example_count": acquisition_summary.get(
                    "retained_inaccurate_example_count"),
                "abstained_example_count": acquisition_summary.get(
                    "retained_abstained_example_count"),
                "outcome_unknown_count": 0,
            }
            observed_counts = ({key: source_projection.get(key)
                for key in expected_counts} if isinstance(source_projection, Mapping)
                else {})
            observed_score_digests = (source_projection.get("source_score_digests")
                if isinstance(source_projection, Mapping) else None)
            source_binding_matches = (
                isinstance(source_projection, Mapping)
                and source_projection.get("source_run_id") == acquisition_run.get("run_id")
                and source_projection.get("projectable_experience_count") == 1
                and observed_counts == expected_counts
                and observed_score_digests == [expected_score_digest])
            if not source_binding_matches:
                raise RootlessExperimentalError(
                    "objective_family_acquisition_history_score_binding_mismatch")
            acquisition_history_score_binding = {
                "status": "verified_exact_source_run_score_to_history_binding",
                "source_run_id": acquisition_run["run_id"],
                "expected_score_digest": expected_score_digest,
                "observed_score_digests": observed_score_digests,
                "expected_counts": expected_counts,
                "observed_counts": observed_counts,
                "verified": True,
                "learning_established": False,
                "authority": False,
            }

            transfer_eligibility = _objective_transfer_eligibility(acquisition_summary)
            if (transfer_eligibility["eligible"]
                    or cross_range_eligibility["eligible"]):
                cross_range_only = not transfer_eligibility["eligible"]
                required_history_record_ids = (
                    list(cross_range_eligibility.get("source_record_ids", ()))
                    if cross_range_eligibility["eligible"] else [])
                if transfer_eligibility["eligible"]:
                    required_history_record_ids.insert(
                        0, acquisition_history_record.record_id)
                if not required_history_record_ids:
                    raise RootlessExperimentalError(
                        "objective_family_transfer_required_history_records_missing")
                # The real owner composes all three history conditions without
                # invoking the model. Refuse to spend inference calls if its
                # selected history omits a preregistered acquisition/source
                # record; the previous post-inference check discovered this
                # retrieval miss only after completing a transfer run.
                transfer_history_preview = owner.preview_objective_history_conditions(
                    snapshot=later_pre_action_snapshot,
                    tick_id=RUN_ID + ":objective-family-transfer-history-preflight",
                    objective_task=transfer_task,
                    history_record_allowlist=tuple(
                        required_history_record_ids))
                preview_conditions = transfer_history_preview.get("conditions")
                present_preview = (preview_conditions.get("history_present")
                    if isinstance(preview_conditions, Mapping) else None)
                restored_preview = (preview_conditions.get("history_restored")
                    if isinstance(preview_conditions, Mapping) else None)
                selected_history_ids = (present_preview.get("selected_record_ids")
                    if isinstance(present_preview, Mapping) else None)
                selected_history_digests = (
                    present_preview.get("selected_record_digests")
                    if isinstance(present_preview, Mapping) else None)
                restored_history_ids = (restored_preview.get("selected_record_ids")
                    if isinstance(restored_preview, Mapping) else None)
                restored_history_digests = (
                    restored_preview.get("selected_record_digests")
                    if isinstance(restored_preview, Mapping) else None)
                present_prompt_digest = (present_preview.get("prompt_digest")
                    if isinstance(present_preview, Mapping) else None)
                restored_prompt_digest = (restored_preview.get("prompt_digest")
                    if isinstance(restored_preview, Mapping) else None)
                if (not isinstance(selected_history_ids, list)
                        or any(not isinstance(value, str) or not value
                            for value in selected_history_ids)
                        or not isinstance(selected_history_digests, list)
                        or len(selected_history_digests) != len(selected_history_ids)
                        or any(not isinstance(value, str)
                            or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                            for value in selected_history_digests)
                        or not isinstance(restored_history_ids, list)
                        or not isinstance(restored_history_digests, list)
                        or len(restored_history_digests) != len(restored_history_ids)
                        or any(not isinstance(value, str)
                            or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                            for value in restored_history_digests)):
                    raise RootlessExperimentalError(
                        "objective_family_transfer_history_preflight_invalid")
                required_history_record_digests = [
                    owner.writeback.store.get(record_id).record_digest
                    for record_id in required_history_record_ids]
                present_prompt_chars = (present_preview.get("prompt_chars")
                    if isinstance(present_preview, Mapping) else None)
                present_prompt_utf8_bytes = (
                    present_preview.get("prompt_utf8_bytes")
                    if isinstance(present_preview, Mapping) else None)
                restored_prompt_chars = (
                    restored_preview.get("prompt_chars")
                    if isinstance(restored_preview, Mapping) else None)
                restored_prompt_utf8_bytes = (
                    restored_preview.get("prompt_utf8_bytes")
                    if isinstance(restored_preview, Mapping) else None)
                if (any(not isinstance(value, str)
                        or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                        for value in required_history_record_digests)
                        or not isinstance(present_prompt_digest, str)
                        or re.fullmatch(r"sha256:[0-9a-f]{64}",
                            present_prompt_digest) is None
                        or restored_prompt_digest != present_prompt_digest
                        or type(present_prompt_chars) is not int
                        or type(restored_prompt_chars) is not int
                        or type(present_prompt_utf8_bytes) is not int
                        or type(restored_prompt_utf8_bytes) is not int
                        or present_prompt_chars <= 0
                        or restored_prompt_chars <= 0
                        or present_prompt_utf8_bytes < present_prompt_chars
                        or restored_prompt_utf8_bytes < restored_prompt_chars):
                    raise RootlessExperimentalError(
                        "objective_family_transfer_history_preflight_invalid")
                missing_present_history_ids = [record_id
                    for record_id in required_history_record_ids
                    if record_id not in selected_history_ids]
                missing_restored_history_ids = [record_id
                    for record_id in required_history_record_ids
                    if record_id not in restored_history_ids]
                missing_required_history_ids = [record_id
                    for record_id in required_history_record_ids
                    if (record_id in missing_present_history_ids
                        or record_id in missing_restored_history_ids)]
                required_digest_by_id = dict(zip(required_history_record_ids,
                    required_history_record_digests))
                history_selection_binding_verified = (
                    selected_history_ids == required_history_record_ids
                    and selected_history_digests ==
                        required_history_record_digests
                    and restored_history_ids == required_history_record_ids
                    and restored_history_digests ==
                        required_history_record_digests
                    and present_prompt_digest == restored_prompt_digest)
                objective_transfer_history_selection_preflight = {
                    "status": ("required_history_retrievable" if
                        history_selection_binding_verified else
                        "required_history_not_retrievable"),
                    "required_history_record_ids": list(required_history_record_ids),
                    "required_history_record_digests": (
                        required_history_record_digests),
                    "selected_history_record_ids": list(selected_history_ids),
                    "selected_history_record_digests": (
                        selected_history_digests),
                    "restored_history_record_ids": list(restored_history_ids),
                    "restored_history_record_digests": (
                        restored_history_digests),
                    "missing_required_history_record_ids": (
                        missing_required_history_ids),
                    "missing_present_history_record_ids": (
                        missing_present_history_ids),
                    "missing_present_history_record_digests": [
                        required_digest_by_id[record_id]
                        for record_id in missing_present_history_ids],
                    "missing_restored_history_record_ids": (
                        missing_restored_history_ids),
                    "missing_restored_history_record_digests": [
                        required_digest_by_id[record_id]
                        for record_id in missing_restored_history_ids],
                    "history_present_prompt_digest": present_prompt_digest,
                    "history_restored_prompt_digest": restored_prompt_digest,
                    "history_selection_binding_verified": (
                        history_selection_binding_verified),
                    "inference_performed": False,
                    "learning_established": False,
                    "authority": False,
                }
                if not history_selection_binding_verified:
                    # Preserve enough answer-free lineage to explain why the
                    # governed owner refused the transfer before inference.
                    # The failure artifact already records this bounded global
                    # diagnostic; never attach the prompt or model output.
                    RUN_FAILURE_DIAGNOSTIC = {
                        "schema_version": (
                            "sentientos.objective_task_family_transfer_history_preflight_diagnostic:v2"),
                        "failure_kind": (
                            "required_history_selection_not_retrievable_or_restorable"),
                        "required_history_record_ids": list(
                            required_history_record_ids),
                        "required_history_record_digests": list(
                            required_history_record_digests),
                        "selected_history_record_ids": list(
                            selected_history_ids),
                        "selected_history_record_digests": list(
                            selected_history_digests),
                        "restored_history_record_ids": list(
                            restored_history_ids),
                        "restored_history_record_digests": list(
                            restored_history_digests),
                        "missing_required_history_record_ids": list(
                            missing_required_history_ids),
                        "missing_present_history_record_ids": list(
                            missing_present_history_ids),
                        "missing_present_history_record_digests": [
                            required_digest_by_id[record_id]
                            for record_id in missing_present_history_ids],
                        "missing_restored_history_record_ids": list(
                            missing_restored_history_ids),
                        "missing_restored_history_record_digests": [
                            required_digest_by_id[record_id]
                            for record_id in missing_restored_history_ids],
                        "history_present_prompt_digest": present_prompt_digest,
                        "history_restored_prompt_digest": restored_prompt_digest,
                        "history_present_prompt_chars": present_preview.get(
                            "prompt_chars"),
                        "history_present_prompt_utf8_bytes": present_preview.get(
                            "prompt_utf8_bytes"),
                        "history_restored_prompt_chars": restored_preview.get(
                            "prompt_chars"),
                        "history_restored_prompt_utf8_bytes": restored_preview.get(
                            "prompt_utf8_bytes"),
                        "prompt_limit_chars": owner.max_inference_input_chars,
                        "history_present_prompt_over_limit_chars": max(0,
                            present_prompt_chars
                            - owner.max_inference_input_chars),
                        "history_restored_prompt_over_limit_chars": max(0,
                            restored_prompt_chars
                            - owner.max_inference_input_chars),
                        "history_selection_binding_verified": False,
                        "inference_performed": False,
                        "learning_established": False,
                        "authority": False,
                    }
                    raise RootlessExperimentalError(
                        "objective_family_transfer_history_not_retrievable_preinference")
                _set_run_stage("objective_cross_range_history_enabled_competence"
                    if cross_range_only else "objective_task_family_transfer")
                transfer_request_id = RUN_ID + (
                    ":objective-cross-range-history-enabled"
                    if cross_range_only else ":objective-family-transfer")
                stage_objective_request(
                    state_root, request_id=transfer_request_id, task=transfer_task)
                transfer_request = load_objective_request(state_root)
                if transfer_request is None:
                    raise RootlessExperimentalError("objective_family_transfer_request_missing")
                transfer_objective_task = objective_task_for_request(transfer_request)
                objective_transfer_result = owner.run_objective_intervention_once(
                    snapshot=later_pre_action_snapshot,
                    tick_id=RUN_ID + ":objective-family-transfer",
                    objective_task=transfer_objective_task,
                    request_id=transfer_request_id,
                    request_digest=transfer_request["request_digest"],
                    history_record_allowlist=tuple(
                        required_history_record_ids))
                if (objective_transfer_result.status != "objective_intervention_completed"
                        or not objective_transfer_result.changed_cognition_measurement_id):
                    raise RootlessExperimentalError("objective_family_transfer_incomplete")
                objective_transfer_run = owner.experiments.load_run(
                    objective_transfer_result.changed_cognition_measurement_id)
                transfer_protocol = objective_transfer_run.get("protocol")
                transfer_task_descriptor = (transfer_protocol.get(
                    "objective_task_descriptor")
                    if isinstance(transfer_protocol, Mapping) else None)
                transfer_probe_inputs = (transfer_task_descriptor.get("probe_inputs")
                    if isinstance(transfer_task_descriptor, Mapping) else None)
                if (not isinstance(transfer_probe_inputs, (list, tuple))
                        or not transfer_probe_inputs
                        or any(type(value) is not int
                            for value in transfer_probe_inputs)
                        or len(set(transfer_probe_inputs)) !=
                            len(transfer_probe_inputs)):
                    raise RootlessExperimentalError(
                        "objective_family_transfer_probe_binding_invalid")
                objective_transfer_conditions = objective_transfer_run.get("conditions", [])
                objective_transfer_scores = objective_transfer_run.get("objective_scores", [])
                if len(objective_transfer_conditions) != 3 or len(objective_transfer_scores) != 3:
                    raise RootlessExperimentalError("objective_family_transfer_conditions_incomplete")
                objective_transfer_observations = _objective_transfer_observations(
                    objective_transfer_conditions, required_history_record_ids)
                objective_transfer_evaluation = objective_transfer_run.get(
                    "objective_evaluation", {})
                transfer_records = owner.experiments.world_state_records(run_refs=((
                    objective_transfer_run["run_id"], objective_transfer_run["run_digest"]),))
                if len(transfer_records) != 1:
                    raise RootlessExperimentalError("objective_family_transfer_projection_invalid")
                transfer_world = WorldStateBoardBuilder().build(transfer_records)
                _set_run_stage(
                    "objective_cross_range_history_enabled_competence_writeback"
                    if cross_range_only else
                    "objective_task_family_transfer_writeback")
                transfer_writeback = owner.run_tick(snapshot=transfer_world,
                    tick_id=RUN_ID + ":objective-family-transfer-writeback")
                if not transfer_writeback.written_record_id:
                    raise RootlessExperimentalError("objective_family_transfer_writeback_missing")
                transfer_progression = ({
                    "status": "not_evaluated_cross_range_history_enabled_outcome",
                    "episodes": [],
                } if cross_range_only else
                    owner.verified_objective_task_family_progression(
                        request_refs=((acquisition_request_id,
                                acquisition_request["request_digest"]),
                            (transfer_request_id, transfer_request["request_digest"]))))
                if (not cross_range_only
                        and (transfer_progression.get("status")
                            != "comparable_scored_episodes"
                            or len(transfer_progression.get("episodes", [])) != 2)):
                    # Preserve only the bounded, derived gate results. A
                    # terminal cycle failure must explain which progression
                    # invariant failed without copying prompts or model output.
                    RUN_FAILURE_DIAGNOSTIC = {
                        "schema_version": (
                            "sentientos.objective_task_family_progression_failure:v1"),
                        "progression_status": transfer_progression.get("status"),
                        "episode_count": len(transfer_progression.get("episodes", [])),
                        "same_model_generation_settings_excluding_task_output_schema": (
                            transfer_progression.get(
                                "same_model_generation_settings_excluding_task_output_schema")),
                        "distinct_task_instances": transfer_progression.get(
                            "distinct_task_instances"),
                        "distinct_probe_sets": transfer_progression.get(
                            "distinct_probe_sets"),
                        "all_episodes_scoreable": transfer_progression.get(
                            "all_episodes_scoreable"),
                        "learning_established": False,
                        "authority": False,
                        "raw_prompts_or_model_outputs_included": False,
                    }
                    raise RootlessExperimentalError(
                        "objective_family_progression_unverified")
                transfer_condition_summaries = (
                    _objective_transfer_condition_summaries(
                        objective_transfer_scores, objective_transfer_observations,
                        required_history_record_ids,
                        transfer_probe_inputs, session))
                transfer_probe_overlap_evidence = [
                    row["task_family_prompt_delivery_evidence"]
                    for row in transfer_condition_summaries
                    if row.get("condition_id") in {
                        "history_present", "history_restored"}]
                if any(type(row.get(
                        "historical_probe_overlap_input_count")) is int
                        and row["historical_probe_overlap_input_count"] > 0
                        for row in transfer_probe_overlap_evidence):
                    exact_probe_reuse_posture = "exact_probe_reuse_detected"
                elif (len(transfer_probe_overlap_evidence) == 2
                        and all(row.get(
                            "historical_probe_overlap_measurement_complete") is True
                            and row.get("historical_probe_overlap_input_count") == 0
                            for row in transfer_probe_overlap_evidence)):
                    exact_probe_reuse_posture = "no_exact_probe_reuse_detected"
                else:
                    exact_probe_reuse_posture = (
                        "exact_probe_reuse_measurement_incomplete_or_legacy")
                if transfer_eligibility["eligible"]:
                    objective_transfer_history = {
                    "status": "completed_scored_intervention",
                    "experiment_seed": EXPERIMENT_SEED,
                    "acquisition_task_outcome": acquisition_summary,
                    "measurement_id": objective_transfer_result.changed_cognition_measurement_id,
                    "run_id": objective_transfer_run.get("run_id"),
                    "run_digest": objective_transfer_run.get("run_digest"),
                    "task_family_id": objective_family,
                    "acquisition_history_record_id": acquisition_history_record.record_id,
                    "transfer_history_record_id": transfer_writeback.written_record_id,
                    "acquisition_request_digest": acquisition_request["request_digest"],
                    "transfer_request_digest": transfer_request["request_digest"],
                    "longitudinal_progression_status": transfer_progression.get("status"),
                    "longitudinal_episode_count": len(transfer_progression.get("episodes", [])),
                    "history_correct_probe_delta": objective_transfer_evaluation.get(
                        "history_correct_probe_delta"),
                    "restoration_correct_probe_delta": objective_transfer_evaluation.get(
                        "restoration_correct_probe_delta"),
                    "condition_correct_counts": objective_transfer_evaluation.get(
                        "condition_correct_counts"),
                    "task_family_history_lineage_verified": True,
                    "conditions": transfer_condition_summaries,
                    "exact_probe_reuse_posture": exact_probe_reuse_posture,
                    "probe_level_outcomes": dict(
                        objective_transfer_evaluation["probe_level_outcomes"])
                        if isinstance(objective_transfer_evaluation.get(
                            "probe_level_outcomes"), Mapping) else
                        _objective_probe_transition_summary(objective_transfer_scores),
                    "authority": False,
                    "action_executed": False,
                    "performance_improvement_established": False,
                    "scope": "single_model_synthetic_exact_scored_task_family_transfer",
                    }
                else:
                    objective_transfer_history = {
                        "status": transfer_eligibility["status"],
                        "experiment_seed": EXPERIMENT_SEED,
                        "acquisition_task_outcome": acquisition_summary,
                        "transfer_eligibility": transfer_eligibility,
                        "measurement_id": None,
                        "run_id": None,
                        "run_digest": None,
                        "task_family_id": objective_family,
                        "acquisition_history_record_id": (
                            acquisition_history_record.record_id),
                        "transfer_history_record_id": None,
                        "acquisition_request_digest": acquisition_request[
                            "request_digest"],
                        "transfer_request_digest": None,
                        "longitudinal_progression_status": "not_run",
                        "longitudinal_episode_count": 1,
                        "history_correct_probe_delta": None,
                        "restoration_correct_probe_delta": None,
                        "condition_correct_counts": None,
                        "task_family_history_lineage_verified": False,
                        "conditions": [],
                        "authority": False,
                        "action_executed": False,
                        "performance_improvement_established": False,
                        "scope": "single_model_synthetic_exact_scored_task_family_transfer",
                    }
                if cross_range_eligibility["eligible"]:
                    probe_level_outcomes = objective_transfer_evaluation.get(
                        "probe_level_outcomes")
                    score_digests_by_condition = {
                        item["condition_id"]: item["score"]["score_digest"]
                        for item in objective_transfer_scores
                        if isinstance(item, Mapping)
                        and isinstance(item.get("condition_id"), str)
                        and isinstance(item.get("score"), Mapping)
                        and isinstance(item["score"].get("score_digest"), str)}
                    if (not isinstance(probe_level_outcomes, Mapping)
                            or probe_level_outcomes.get("condition_order") != [
                                "history_present", "history_withheld",
                                "history_restored"]
                            or probe_level_outcomes.get(
                                "condition_score_digests")
                                != score_digests_by_condition
                            or probe_level_outcomes.get("posture") not in {
                                "independent_oracle_correctness_only_answer_values_omitted",
                                "partial_per_probe_outcomes_unscoreable_conditions",
                                "per_probe_outcomes_unavailable_no_scoreable_condition"}):
                        raise RootlessExperimentalError(
                            "cross_range_probe_level_score_binding_invalid")
                    objective_cross_range_history_probe = {
                        "schema_version": (
                            "sentientos.cross_range_history_enabled_competence_outcome:v1"),
                        "status": "completed_scored_history_enabled_competence_intervention",
                        "protocol": dict(cross_range_protocol),
                        "measurement_relation": (
                            "shared_with_baseline_gated_transfer"
                            if transfer_eligibility["eligible"] else
                            "separate_probe_invoked_without_baseline_competence"),
                        "task_family_id": objective_family,
                        "source_task_family_id": cross_range_eligibility[
                            "source_task_family_id"],
                        "source_record_ids": list(cross_range_eligibility[
                            "source_record_ids"]),
                        "source_history_projection_audit": cross_range_eligibility[
                            "source_history_projection_audit"],
                        "all_family_probe_overlap": cross_range_eligibility[
                            "all_family_probe_overlap"],
                        "baseline_competence_required": False,
                        "baseline_competence_demonstrated": (
                            acquisition_summary.get(
                                "baseline_competence_qualified")
                            if isinstance(acquisition_summary, Mapping) else None),
                        "measurement_id": objective_transfer_result.changed_cognition_measurement_id,
                        "run_id": objective_transfer_run.get("run_id"),
                        "run_digest": objective_transfer_run.get("run_digest"),
                        "writeback_record_id": transfer_writeback.written_record_id,
                        "condition_correct_counts": objective_transfer_evaluation.get(
                            "condition_correct_counts"),
                        "condition_score_digests": score_digests_by_condition,
                        "conditions": transfer_condition_summaries,
                        "probe_level_outcomes": dict(probe_level_outcomes),
                        "probe_level_outcomes_digest": "sha256:" + digest_payload(
                            dict(probe_level_outcomes)),
                        "exact_source_record_receipts_verified": all(
                            row.get("required_history_record_ids_retrieved") is True
                            for row in transfer_condition_summaries
                            if row.get("condition_id") in {
                                "history_present", "history_restored"}),
                        "inference_performed": True,
                        "capability_evaluated": True,
                        "learning_established": False,
                        "causal_claim_made": False,
                        "authority": False,
                    }
                    if (objective_cross_range_history_probe[
                            "exact_source_record_receipts_verified"] is not True):
                        raise RootlessExperimentalError(
                            "cross_range_source_history_receipt_lineage_incomplete")
            else:
                objective_transfer_history = {
                    "status": transfer_eligibility["status"],
                    "experiment_seed": EXPERIMENT_SEED,
                    "acquisition_task_outcome": acquisition_summary,
                    "transfer_eligibility": transfer_eligibility,
                    "measurement_id": None,
                    "run_id": None,
                    "run_digest": None,
                    "task_family_id": objective_family,
                    "acquisition_history_record_id": acquisition_history_record.record_id,
                    "transfer_history_record_id": None,
                    "acquisition_request_digest": acquisition_request["request_digest"],
                    "transfer_request_digest": None,
                    "longitudinal_progression_status": "not_run",
                    "longitudinal_episode_count": 1,
                    "history_correct_probe_delta": None,
                    "restoration_correct_probe_delta": None,
                    "condition_correct_counts": None,
                    "task_family_history_lineage_verified": False,
                    "conditions": [],
                    "authority": False,
                    "action_executed": False,
                    "performance_improvement_established": False,
                    "scope": "single_model_synthetic_exact_scored_task_family_transfer",
                }
            objective_transfer_history.update({
                "acquisition_score_status": acquisition_readiness["score_status"],
                "acquisition_readiness_classification": acquisition_readiness["classification"],
                "acquisition_probe_result_count": acquisition_readiness["probe_result_count"],
                "required_probe_count": acquisition_readiness["required_probe_count"],
                "acquisition_readiness_diagnostics": acquisition_readiness_diagnostics,
                "acquisition_history_projection_audit": (
                    acquisition_history_projection_audit),
                "acquisition_history_score_binding": acquisition_history_score_binding,
            })
        intervention_owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root, state_root, ("embodiment",), 16, 4, True,
                max_inference_input_chars=(
                    ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT),
                max_inference_timeout_seconds=(
                    ROOTLESS_DEVELOPMENTAL_COGNITION_INFERENCE_TIMEOUT_SECONDS)),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)
        later_pre_action_snapshot, _ = _pre_action_source(pose="reach")
        history_decision_question = (
            "Controlled history-use probe. Read ONLY the exact typed historical "
            "field historical_embodiment_reports[*].reported_values.observer_report_field.pose. "
            "If that retrieved past field equals idle, set response to the exact token "
            "PAST_OBSERVER_REPORTED_IDLE. If it equals reach, use "
            "PAST_OBSERVER_REPORTED_REACH. If no such typed field is present in retrieved "
            "history, set response to HISTORY_UNAVAILABLE and disposition to abstain. "
            "The current World-State encoder pose is reach; it is not the past observer "
            "report and must not determine this classification. Ignore renderer, predicted, "
            "and proprioception fields. When a typed past field is present, set disposition "
            "to answer, evidence_ids to [], and cite its exact containing record_id in "
            "history_record_ids. When unavailable, cite no history. Treat the past report as "
            "unverified, not as current truth. Return the standard JSON response with the "
            "response exactly one token from the three uppercase choices above.")
        replay_owner = ResidentDevelopmentalCognitionOwner(
            config=ResidentDevelopmentalCognitionConfig(
                history_root, state_root, ("embodiment",), 16, 4, False,
                max_inference_input_chars=(
                    ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT),
                max_inference_timeout_seconds=(
                    ROOTLESS_DEVELOPMENTAL_COGNITION_INFERENCE_TIMEOUT_SECONDS)),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=session, current_sequence=next_sequence)
        history_recall_at = datetime.now(timezone.utc)
        _, history_recall_proprioception = _pre_action_source(pose="reach")
        from sentientos.canonical_memory import CanonicalMemoryStore
        from sentientos.chat_service import (
            DevelopmentLocalChatInference, PersistentConversationService,
        )
        from sentientos.conversation_session import ConversationSessionStore

        hosted_chat_root = RUN_ROOT / "hosted-chat"
        hosted_chat_root.mkdir(mode=0o700, exist_ok=False)
        hosted_inference = DevelopmentLocalChatInference(invoker=session.invoker)
        history_recall_bridge = ResidentDevelopmentalCompanionBridge(
            replay_owner,
            proprioception_provider=lambda: (history_recall_proprioception,),
            cognition_inference_gate=hosted_inference.cognition_inference_context,
            cognition_available=hosted_inference.cognition_available,
            clock=lambda: history_recall_at)
        hosted_companion = PersistentConversationService(
            inference=hosted_inference,
            session_store=ConversationSessionStore(
                hosted_chat_root / "conversations"),
            memory_store=CanonicalMemoryStore(hosted_chat_root / "memory"),
            resident_cognition_bridge=history_recall_bridge)
        hosted_session_id = hosted_companion.create_session()
        history_recall_response = hosted_companion.chat(
            ("Use retrieved developmental history only. Read exactly "
                "historical_embodiment_reports[*].reported_values.observer_report_field.pose. "
                "If its value is idle, set response exactly to "
                "PAST_OBSERVER_REPORTED_IDLE. If its value is reach, set response exactly "
                "to PAST_OBSERVER_REPORTED_REACH. If the typed field is unavailable, set "
                "response to HISTORY_UNAVAILABLE and disposition to abstain. Do not use "
                "prior self-model, current evidence, renderer_report.pose, "
                "predicted_observation.pose, or body_proprioception_report.encoder_pose. "
                "For a found field, set disposition to answer, evidence_ids to [], and cite "
                "the exact containing record_id in history_record_ids (not an inner fact_id). "
                "Treat it only as an unverified past report."),
            session_id=hosted_session_id,
            request_id=RUN_ID + ":historical-companion-recall",
            observe_screen=False)
        hosted_turns = hosted_companion.sessions.load(hosted_session_id)["turns"]
        hosted_assistant_turn = hosted_turns[-1]
        hosted_linkage = hosted_assistant_turn.get("linkage", {})
        history_recall = {
            "status": ("admitted_completed"
                if history_recall_response.context.get("response_origin")
                    == "resident_developmental_cognition" else "not_routed_to_cognition"),
            "disposition": history_recall_response.context.get("cognition_disposition"),
            "response": history_recall_response.response,
            "evidence_ids": history_recall_response.context.get(
                "cognition_evidence_ids", []),
            "history_record_ids": history_recall_response.context.get(
                "cognition_history_record_ids", []),
            "prior_record_ids": history_recall_response.context.get(
                "cognition_prior_record_ids", []),
            "retrieved_record_ids": history_recall_response.context.get(
                "cognition_prior_record_ids", []),
            "current_pose": "reach",
            "cited_current_fact_ids": history_recall_response.context.get(
                "cognition_evidence_ids", []),
            "snapshot_id": history_recall_response.context.get(
                "cognition_snapshot_id"),
            "snapshot_digest": history_recall_response.context.get(
                "cognition_snapshot_digest"),
            "cognition_observation_id": history_recall_response.context.get(
                "cognition_observation_id"),
            "inference_receipt_id": history_recall_response.context.get(
                "inference_receipt_id"),
            "response_lineage_verified": history_recall_bridge.verify_committed_response(
                linkage=hosted_linkage,
                response_text=history_recall_response.response,
                request_id=(f"{hosted_session_id}:"
                    f"{hosted_turns[-2]['turn_id']}")),
            "history_citation_delivery_verified": (
                hosted_linkage.get("cognition_history_record_ids")
                == history_recall_response.context.get(
                    "cognition_history_record_ids")),
            "screen_observation_requested": False,
        }
        if (history_recall["status"] != "admitted_completed"
                or history_recall["response_lineage_verified"] is not True
                or history_recall["history_citation_delivery_verified"] is not True):
            raise RootlessExperimentalError("hosted_cognition_delivery_unverified")
        _set_run_stage("controlled_history_intervention")
        companion_intervention = (
            intervention_owner.run_companion_history_intervention(
                snapshot=later_pre_action_snapshot,
                tick_id=RUN_ID + ":later-companion-decision",
                question=history_decision_question,
                trial_index=HISTORY_INTERVENTION_TRIAL_INDEX))
        if (companion_intervention.status != "completed_controlled_intervention"
                or not companion_intervention.changed_cognition_measurement_id):
            raise RootlessExperimentalError("history_intervention_measurement_missing")
        run_payload = intervention_owner.experiments.load_run(
            companion_intervention.changed_cognition_measurement_id)
        conditions = run_payload.get("conditions", [])
        persisted_decisions = run_payload.get("companion_intervention_decisions")
        summary = run_payload.get("summary", {})
        intervention_conditions = list(companion_intervention.conditions)
        if (not isinstance(conditions, list) or len(conditions) != 3
                or any(not isinstance(row, Mapping) for row in conditions)
                or not isinstance(persisted_decisions, list)
                or len(persisted_decisions) != 3
                or any(not isinstance(row, Mapping)
                    for row in persisted_decisions)
                or len(intervention_conditions) != 3
                or any(not isinstance(row, Mapping)
                    for row in intervention_conditions)):
            raise RootlessExperimentalError(
                "history_intervention_persisted_conditions_invalid")
        if any(not isinstance(row.get("condition_id"), str)
                or not isinstance(row.get("cognition_observation_id"), str)
                for row in intervention_conditions):
            raise RootlessExperimentalError(
                "history_intervention_capture_identity_invalid")
        expected_condition_ids = {
            "history_present", "history_withheld", "history_restored"}
        capture_condition_ids = [row.get("condition_id")
            for row in intervention_conditions]
        if (len(set(capture_condition_ids)) != len(intervention_conditions)
                or set(capture_condition_ids) != expected_condition_ids):
            raise RootlessExperimentalError(
                "history_intervention_capture_conditions_incomplete")
        persisted_by_observation = {
            row.get("observation_id"): row for row in conditions}
        if len(persisted_by_observation) != len(conditions):
            raise RootlessExperimentalError(
                "history_intervention_observation_identity_duplicate")
        decisions_by_condition = {
            row.get("condition_id"): row for row in persisted_decisions}
        if len(decisions_by_condition) != len(persisted_decisions):
            raise RootlessExperimentalError(
                "history_intervention_decision_identity_duplicate")
        for item in intervention_conditions:
            condition_id = item.get("condition_id")
            persisted = persisted_by_observation.get(
                item.get("cognition_observation_id"))
            decision = decisions_by_condition.get(condition_id)
            if (persisted is None
                    or decision is None
                    or persisted.get("condition_id") != condition_id
                    or persisted.get("observation_digest") != item.get(
                        "cognition_observation_digest")
                    or persisted.get("retrieved_record_ids") != item.get(
                        "retrieved_record_ids")
                    or persisted.get("retrieved_record_digests") != item.get(
                        "retrieved_record_digests")
                    or persisted.get("inference_receipt_id") != item.get(
                        "inference_receipt_id")
                    or persisted.get("inference_receipt_digest") != item.get(
                        "inference_receipt_digest")
                    or persisted.get("output_digest") != item.get("output_digest")
                    or persisted.get("epistemic_prompt_digest") != item.get(
                        "prompt_digest")
                    or persisted.get("generation_config") != item.get(
                        "generation_config")
                    or persisted.get("active_model_identity") != item.get(
                        "active_model_identity")
                    or persisted.get("current_snapshot_digest") != item.get(
                        "snapshot_digest")
                    or not isinstance(item.get("current_fact_ids"), (list, tuple))
                    or list(persisted.get("current_fact_ids", ())) != list(
                        item.get("current_fact_ids", ()))
                    or decision.get("observation_id") != item.get(
                        "cognition_observation_id")
                    or decision.get("observation_digest") != item.get(
                        "cognition_observation_digest")
                    or decision.get("inference_receipt_id") != item.get(
                        "inference_receipt_id")
                    or decision.get("inference_receipt_digest") != item.get(
                        "inference_receipt_digest")
                    or decision.get("output_digest") != item.get("output_digest")
                    or decision.get("response_digest") != item.get(
                        "response_digest")
                    or not isinstance(item.get("response"), str)
                    or digest_payload({"text": item["response"]}) != decision.get(
                        "response_digest")
                    or decision.get("disposition") != item.get("disposition")
                    or decision.get("model_disposition") != item.get(
                        "model_disposition")
                    or decision.get("disposition_normalization") != item.get(
                        "disposition_normalization")
                    or decision.get("decision_validation_status", "validated")
                        != item.get("decision_validation_status", "validated")
                    or decision.get("decision_validation_error_code") != item.get(
                        "decision_validation_error_code")
                    or not isinstance(item.get("evidence_ids"), (list, tuple))
                    or decision.get("evidence_ids") != list(
                        item.get("evidence_ids", ()))
                    or not isinstance(item.get("history_record_ids"), (list, tuple))
                    or decision.get("history_record_ids") != list(
                        item.get("history_record_ids", ()))):
                raise RootlessExperimentalError(
                    "history_intervention_persisted_decision_binding_mismatch")
        replay_first = intervention_conditions[0] if len(intervention_conditions) == 3 else {}
        replay_second = intervention_conditions[2] if len(intervention_conditions) == 3 else {}
        replay_controls = (
            "prompt_digest", "generation_config", "active_model_identity",
            "snapshot_digest", "current_fact_ids", "retrieved_record_ids")
        present_restoration_delivery_replay = {
            "control_basis": "history_present_vs_history_restored_conditions",
            "independent_repeatability_control_performed": False,
            "conditions": [replay_first, replay_second],
            "input_controls_match": all(replay_first.get(key) == replay_second.get(key)
                for key in replay_controls),
            "output_digest_matches": (
                replay_first.get("output_digest") == replay_second.get("output_digest")),
            "response_digest_matches": (
                replay_first.get("response_digest") == replay_second.get("response_digest")),
            "all_decisions_valid": all(
                item.get("decision_validation_status", "validated") == "validated"
                for item in (replay_first, replay_second)),
            "all_responses_admitted": all(
                item.get("inference_status") == "admitted_completed"
                for item in (replay_first, replay_second)),
            "cognition_receipt_output_binding_verified": all(
                item.get("cognition_receipt_output_binding_verified") is True
                for item in (replay_first, replay_second)),
        }
        present, withheld, restored = (intervention_conditions
            if len(intervention_conditions) == 3 else (None, None, None))
        def _mentions_past_idle(item: Any) -> bool:
            text = str(item.get("response", "")).strip().lower() if isinstance(item, Mapping) else ""
            return text == "past_observer_reported_idle" or (
                "idle" in text and ("observer report" in text
                    or "observer_report_field" in text or "observer reported" in text))
        def _reports_exact_past_idle(item: Any) -> bool:
            return (isinstance(item, Mapping)
                and item.get("disposition") == "answer"
                and str(item.get("response", "")).strip()
                    == "PAST_OBSERVER_REPORTED_IDLE")
        def _reports_history_unavailable(item: Any) -> bool:
            return (isinstance(item, Mapping)
                and item.get("disposition") == "abstain"
                and str(item.get("response", "")).strip() == "HISTORY_UNAVAILABLE"
                and not item.get("history_record_ids"))
        def _valid_record_id_sequence(value: Any) -> bool:
            return (isinstance(value, (list, tuple))
                and all(isinstance(record_id, str) and record_id
                    for record_id in value)
                and len(set(value)) == len(value))
        def _reports_past_idle(item: Any) -> bool:
            if not isinstance(item, Mapping) or item.get("disposition") != "answer":
                return False
            if not _history_citation_bound(item):
                return False
            prior_record_ids = item.get("prior_record_ids", ())
            if not _valid_record_id_sequence(prior_record_ids):
                return False
            cited_prior_record = bool(set(item["history_record_ids"])
                & set(prior_record_ids))
            if not cited_prior_record:
                return False
            response = str(item.get("response", "")).strip().lower()
            return (response == "past_observer_reported_idle"
                or _mentions_past_idle(item) or response == "idle")
        def _history_citation_bound(item: Any) -> bool:
            if not isinstance(item, Mapping):
                return False
            history_record_ids = item.get("history_record_ids", ())
            retrieved_record_ids = item.get("retrieved_record_ids", ())
            retrieved_record_digests = item.get("retrieved_record_digests", ())
            return (_valid_record_id_sequence(history_record_ids)
                and bool(history_record_ids)
                and _valid_record_id_sequence(retrieved_record_ids)
                and isinstance(retrieved_record_digests, (list, tuple))
                and len(retrieved_record_digests) == len(retrieved_record_ids)
                and all(isinstance(value, str)
                    and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
                    for value in retrieved_record_digests)
                and set(history_record_ids).issubset(retrieved_record_ids))
        intervention_inputs_match = (present is not None and restored is not None
            and withheld is not None
            and present.get("current_fact_ids") == withheld.get("current_fact_ids")
            == restored.get("current_fact_ids")
            and present.get("snapshot_digest") == withheld.get("snapshot_digest")
            == restored.get("snapshot_digest")
            and present.get("generation_config") == withheld.get("generation_config")
            == restored.get("generation_config")
            and present.get("active_model_identity") == withheld.get("active_model_identity")
            == restored.get("active_model_identity"))
        if (intervention_inputs_match and _reports_exact_past_idle(present)
                and _reports_exact_past_idle(restored)
                and _history_citation_bound(present)
                and _history_citation_bound(restored)
                and _reports_history_unavailable(withheld)):
            historical_answer_classification = "history_present_exactly_retrieved_withheld_abstained"
        elif (intervention_inputs_match and _mentions_past_idle(present)
                and _mentions_past_idle(restored)
                and _history_citation_bound(present)
                and _history_citation_bound(restored)
                and _reports_history_unavailable(withheld)):
            historical_answer_classification = (
                "history_associated_content_difference_but_answer_not_exact")
        else:
            historical_answer_classification = "no_validated_history_effect"
        def _validation_failure_domain(error_code: Any) -> str:
            if not isinstance(error_code, str):
                return "unknown_validation_failure"
            if "history" in error_code:
                return "history_binding"
            if "evidence" in error_code:
                return "current_evidence_binding"
            if "memory" in error_code:
                return "memory_binding"
            if "self_model" in error_code:
                return "self_model_binding"
            if "epistemic" in error_code:
                return "epistemic_binding"
            if "json" in error_code or "shape" in error_code:
                return "response_format"
            return "interaction_validation"
        semantic_decisions = [{"condition_id": item.get("condition_id"),
            "disposition": item.get("disposition"),
            "decision_validation_status": item.get(
                "decision_validation_status", "validated"),
            "decision_validation_error_code": item.get(
                "decision_validation_error_code"),
            "mentions_past_idle": _mentions_past_idle(item),
            "answers_with_past_idle": _reports_past_idle(item),
            "answers_with_exact_past_idle_token": _reports_exact_past_idle(item),
            "abstains_for_unavailable_history": _reports_history_unavailable(item),
            "history_citation_bound": _history_citation_bound(item),
            "rejected_raw_response_digest": (
                item.get("rejected_output_diagnostic", {}).get(
                    "raw_response_digest")
                if isinstance(item.get("rejected_output_diagnostic"), Mapping)
                else None)}
            for item in intervention_conditions]
        present_response_digest = (present.get("response_digest")
            if isinstance(present, Mapping) else None)
        restored_response_digest = (restored.get("response_digest")
            if isinstance(restored, Mapping) else None)
        rejected_decision_diagnostics = [{
            "condition_id": item.get("condition_id"),
            "validation_error_code": item.get(
                "decision_validation_error_code"),
            "validation_failure_domain": _validation_failure_domain(
                item.get("decision_validation_error_code")),
            "output_digest": item.get("output_digest"),
            "raw_diagnostic_status": (
                item.get("rejected_output_diagnostic", {}).get("status")
                if isinstance(item.get("rejected_output_diagnostic"), Mapping)
                else None),
            "output_text_integrity": (
                item.get("rejected_output_diagnostic", {}).get(
                    "output_text_integrity")
                if isinstance(item.get("rejected_output_diagnostic"), Mapping)
                else None),
            "raw_model_disposition": (
                item.get("rejected_output_diagnostic", {}).get(
                    "raw_model_disposition")
                if isinstance(item.get("rejected_output_diagnostic"), Mapping)
                else None),
            "raw_response_digest": (
                item.get("rejected_output_diagnostic", {}).get(
                    "raw_response_digest")
                if isinstance(item.get("rejected_output_diagnostic"), Mapping)
                else None),
            "raw_response_digest_matches_history_present": (
                item.get("rejected_output_diagnostic", {}).get(
                    "raw_response_digest") == present_response_digest
                if isinstance(item.get("rejected_output_diagnostic"), Mapping)
                    and isinstance(present_response_digest, str) else None),
            "raw_response_digest_matches_history_restored": (
                item.get("rejected_output_diagnostic", {}).get(
                    "raw_response_digest") == restored_response_digest
                if isinstance(item.get("rejected_output_diagnostic"), Mapping)
                    and isinstance(restored_response_digest, str) else None),
            "raw_history_citation_count": (
                item.get("rejected_output_diagnostic", {}).get(
                    "raw_history_citation_count")
                if isinstance(item.get("rejected_output_diagnostic"), Mapping)
                else None),
            "raw_history_citations_condition_compatible": (
                item.get("rejected_output_diagnostic", {}).get(
                    "raw_history_citations_condition_compatible")
                if isinstance(item.get("rejected_output_diagnostic"), Mapping)
                else None),
            "decision_qualified": False,
            "interpretation_posture": "verified_output_diagnostic_only_no_decision_qualification",
        } for item in intervention_conditions
            if item.get("decision_validation_status") == "rejected_invalid_output"]
        semantic_decision_classification = (
            "invalid_condition_response_rejected"
            if any(item.get("decision_validation_status")
                == "rejected_invalid_output" for item in intervention_conditions)
            else historical_answer_classification)
        records = [asdict(durable)] if durable is not None else []
        source_ids = ({fact.get("source", {}).get("source_id")
            for fact in records[0]["candidate"].get("selected_facts", [])
            if isinstance(fact, dict)} if records else set())
        same_history_replay = {
            "prompt_digest_matches": (
                len(conditions) == 3
                and conditions[0].get("epistemic_prompt_digest")
                    == conditions[2].get("epistemic_prompt_digest")),
            "generation_config_matches": (
                len(conditions) == 3
                and conditions[0].get("generation_config")
                    == conditions[2].get("generation_config")),
            "active_model_identity_matches": (
                len(conditions) == 3
                and conditions[0].get("active_model_identity")
                    == conditions[2].get("active_model_identity")),
            "output_digest_matches": (
                len(conditions) == 3
                and conditions[0].get("output_digest")
                    == conditions[2].get("output_digest")),
        }
        restoration_stability_qualification = (
            qualify_restoration_stable_history_association(
                validity=run_payload.get("validity"),
                history_summary=summary,
                same_history_replay=same_history_replay,
                present_restoration_delivery_replay=present_restoration_delivery_replay))
        semantic_history_decision_qualification = qualify_semantic_history_decision(
            semantic_decisions=semantic_decisions,
            controlled_inputs_match=intervention_inputs_match,
            restored_prompt_matches=companion_intervention.restored_prompt_matches,
            restoration_stable_association_qualified=(
                restoration_stability_qualification.get(
                    "restoration_stable_association_qualified")))
        semantic_history_changed = semantic_history_decision_qualification[
            "history_changed_cognition"]
        # Keep a direct new-action decision probe distinct from historical
        # recall. It uses the same existing resident history-intervention owner,
        # the same current World-State snapshot, and a fresh experiment tick.
        # This synthetic record can only support a decision probe when its
        # retained action and outcome match the probe's explicit antecedent.
        # Even then, it is not evidence of a physical effect.
        transfer_question = TRANSFER_DECISION_QUESTION
        transfer_readiness = (
            _history_transfer_probe_readiness(asdict(durable))
            if durable is not None else {
                "eligible": False,
                "reason_code": "no_new_action_consequence_record",
                "classification": "not_run_no_action_consequence_record",
            })
        transfer_conditions: list[Mapping[str, Any]] = []
        if transfer_readiness["eligible"]:
            # Ground only the new action-choice comparison in a current synthetic
            # target observation. Acquisition and historical recall keep their
            # existing evidence sets and limits.
            later_action_decision_snapshot, _ = _pre_action_source(
                pose="reach", include_current_target=True)
            target_fact_ids = tuple(fact.fact_id
                for fact in later_action_decision_snapshot.facts
                if fact.subject.subject_id == "synthetic-target-1")
            if len(target_fact_ids) != 1:
                raise RootlessExperimentalError(
                    "later_action_target_fact_identity_invalid")
            transfer_intervention = (
                intervention_owner.run_companion_history_intervention(
                    snapshot=later_action_decision_snapshot,
                    tick_id=RUN_ID + ":later-transfer-decision",
                    question=transfer_question,
                    history_record_allowlist=(first.written_record_id,),
                    trial_index=HISTORY_INTERVENTION_TRIAL_INDEX))
            if (transfer_intervention.status != "completed_controlled_intervention"
                    or not transfer_intervention.changed_cognition_measurement_id):
                raise RootlessExperimentalError(
                    "history_transfer_intervention_measurement_missing")
            transfer_conditions = list(transfer_intervention.conditions)
            transfer_qualification = qualify_history_transfer_decision(
                conditions=transfer_conditions,
                expected_history_record_id=first.written_record_id,
                expected_current_fact_id=target_fact_ids[0],
                present_response="INSPECT", withheld_response="REACH",
                restored_response="INSPECT",
                restored_prompt_matches=transfer_intervention.restored_prompt_matches)
            transfer_status = transfer_intervention.status
            transfer_question_digest = transfer_intervention.question_digest
            transfer_measurement_id = (
                transfer_intervention.changed_cognition_measurement_id)
            transfer_response_text_classification = (
                transfer_intervention.response_text_classification)
            transfer_restored_prompt_matches = (
                transfer_intervention.restored_prompt_matches)
            transfer_authority = transfer_intervention.authority
            transfer_action_authority = transfer_intervention.action_authority
        else:
            # Do not spend three inferences on a question whose stated historical
            # antecedent is absent from the retained experience.
            transfer_qualification = {
                "schema_version": "sentientos.history_transfer_decision_qualification:v5",
                "measurement_scope": "new_action_proposal_not_executed",
                "classification": "history_evidence_precondition_not_met",
                "controlled_inputs_match": False,
                "matched_non_history_inputs_bound": False,
                "restored_prompt_exact_match": False,
                "target_evidence_cited": False,
                "expected_history_cited": False,
                "history_treatment_bound": False,
                "restoration_stable": False,
                "response_difference_observed": False,
                "restored_response_matches_present": False,
                "history_conditioned_response_difference_observed_under_matched_controls": False,
                "history_changed_new_decision": False,
                "response_text_digest_binding_verified": False,
                "decision_outputs_validated": False,
                "qualification_failure_codes": [
                    transfer_readiness["reason_code"]],
                "action_executed": False,
                "performance_improvement_established": False,
            }
            transfer_status = "skipped_history_evidence_precondition_not_met"
            transfer_question_digest = digest_payload(
                {"question": transfer_question})
            transfer_measurement_id = None
            transfer_response_text_classification = "not_run"
            transfer_restored_prompt_matches = False
            transfer_authority = False
            transfer_action_authority = False
        transfer_controls_match = transfer_qualification["controlled_inputs_match"]
        transfer_history_cited = transfer_qualification["expected_history_cited"]
        transfer_restoration_stable = transfer_qualification["restoration_stable"]
        transfer_history_changed_new_decision = transfer_qualification[
            "history_changed_new_decision"]
        transfer_classification = transfer_qualification["classification"]
        from work.rootless_history_boundary_campaign import (
            _cognition_recovery_state_boundary)
        cognition_recovery_state_boundary = _cognition_recovery_state_boundary(
            state_root)
        result = {
            "schema_version": "sentientos.rootless_ollama_embodied_cognition_cycle:v19",
            "run_id": RUN_ID, "status": "completed",
            "execution_posture": "rootless_experimental_nonproduction",
            "source_provenance": dict(RUN_SOURCE_PROVENANCE),
            "external_preregistration_digest": _optional_preregistration_digest(
                PREREGISTRATION_DIGEST),
            "run_preregistration_digest": RUN_PREREGISTRATION_DIGEST,
            "model_id": MODEL_NAME, "model_manifest_digest": manifest_digest,
            "gpu_layers_requested": GPU_LAYERS,
            "model_configuration_observation":
                session.active_model_configuration_observation,
            "prior_developmental_history_seed": dict(HISTORY_SEED_EVIDENCE),
            "runtime_admission_ledger": _runtime_admission_ledger_boundary(
                state_root / "runtime_admissions.json"),
            "cognition_recovery_state_boundary": cognition_recovery_state_boundary,
            "history_campaign_binding": ({
                "campaign_id": campaign_plan["campaign_id"],
                "campaign_plan_digest": campaign_plan["plan_digest"],
                "cycle_index": campaign_plan["ordered_cycle_ids"].index(RUN_ID),
                **({"transfer_probe_preflight": dict(
                    WIDE_TRANSFER_PROBE_PREFLIGHT)}
                    if WIDE_TRANSFER_PROBE_PREFLIGHT is not None else {}),
            } if campaign_plan is not None else None),
            **_experiment_seed_provenance(),
            "history_order_trial_index": HISTORY_INTERVENTION_TRIAL_INDEX,
            "model_artifact_size_bytes": manifest_size,
            "runtime_observation": runtime, "runtime_observation_digest": runtime_sha,
            "active_model_identity": session.active_model_identity,
            "authority_map_digest": session.authority_map.map_digest,
            "authority_scope": {
                "allowed_invocation_purposes": [
                    "resident_developmental_interpretation",
                    "resident_developmental_retrieval_cognition",
                    "resident_developmental_history_intervention_experiment"],
                "ordinary_chat_allowed": False, "production_authority": False,
                "tool_or_action_authority": False},
            "body_and_observer_posture": "synthetic_rehearsal_not_live_hardware",
            "resource_preflight": {
                "governor_mode": "enforce",
                "host_evidence_refreshed_before_each_inference": True,
                "required_gpu_free_bytes": model_weight_bytes + _GPU_RUNTIME_RESERVE_BYTES,
                "samples": [initial_resource_evidence, *inference_resource_evidence],
                "telemetry_scope": "host_sample_not_per_invocation"},
            "model_proposal_before_synthetic_action": {
                **(dict(PRE_ACTION_DECISION_EVIDENCE)
                    if PRE_ACTION_DECISION_EVIDENCE is not None else {}),
                "status": ("verified_governed_companion_proposal"
                    if proposal is not None else
                    "owner_admitted_ask_or_abstain_no_action"),
                "requested_pose": (proposal["requested_pose"]
                    if proposal is not None else None),
                "predicted_pose": (proposal["predicted_pose"]
                    if proposal is not None else None),
                "pre_action_proprioception_snapshot_id": (
                    cognitive_decision.get("snapshot_id")
                    or pre_action_snapshot.snapshot_id),
                "pre_action_proprioception_snapshot_digest": (
                    cognitive_decision.get("snapshot_digest")
                    or pre_action_snapshot.digest),
                "evidence_ids": list(cognitive_decision["evidence_ids"]),
                "retrieved_record_ids": list(
                    cognitive_decision.get("retrieved_record_ids", [])),
                "current_fact_ids": list(
                    cognitive_decision.get("current_fact_ids", [])),
                "snapshot_digest": cognitive_decision.get("snapshot_digest"),
                "prompt_digest": cognitive_decision.get("prompt_digest"),
                "output_digest": cognitive_decision.get("output_digest"),
                "response_digest": cognitive_decision.get("response_digest"),
                "generation_config": cognitive_decision.get("generation_config"),
                "active_model_identity": cognitive_decision.get(
                    "active_model_identity"),
                "cognition_observation_id": cognitive_decision.get(
                    "cognition_observation_id"),
                "cognition_observation_digest": cognitive_decision.get(
                    "cognition_observation_digest"),
                "inference_receipt_id": cognitive_decision.get("inference_receipt_id"),
                "inference_receipt_digest": cognitive_decision.get(
                    "inference_receipt_digest"),
                "request_id": RUN_ID + ":pre-action-decision",
                "response_lineage_verified": True,
                "action_authority": False,
                "executor_posture": "separate_synthetic_fixture_only",
            },
            "source_evidence": evidence,
            "initial_tick": ({"status": first.status,
                "cognition_observation_ids": list(first.cognition_observation_ids),
                "written_record_id": first.written_record_id,
                "writeback_receipt_id": first.writeback_receipt_id,
                "record_current_truth": durable.current_truth,
                "record_authority": durable.authority,
                "record_epistemic_posture": durable.epistemic_posture,
                "selected_source_ids": sorted(item for item in source_ids if item)}
                if first is not None and durable is not None else {
                    "status": "not_run_no_action_after_ask_or_abstain",
                    "cognition_observation_ids": [],
                    "written_record_id": None,
                    "writeback_receipt_id": None,
                    "record_current_truth": None,
                    "record_authority": False,
                    "record_epistemic_posture": "no_consequence_record_created",
                    "selected_source_ids": [],
                }),
            "initial_history_bootstrap": (
                dict(INITIAL_HISTORY_BOOTSTRAP_EVIDENCE)
                if INITIAL_HISTORY_BOOTSTRAP_EVIDENCE is not None else None),
            "later_tick": {"status": companion_intervention.status,
                "prior_record_ids": list(present.get("retrieved_record_ids", ()))
                    if present is not None else [],
                "changed_cognition_measurement_id":
                    companion_intervention.changed_cognition_measurement_id,
                "cognition_observation_ids": [item.get("cognition_observation_id")
                    for item in intervention_conditions
                    if item.get("cognition_observation_id")]},
            "developmental_outcome_assessment": {
                "schema_version": "sentientos.developmental_outcome_assessment:v1",
                "developmental_cycle_executed": True,
                "cycle_scope": "rootless_synthetic_rehearsal",
                "history_associated_decision_difference_observed":
                    semantic_history_decision_qualification[
                        "history_associated_decision_difference_observed"],
                "history_changed_cognition": semantic_history_changed,
                "history_change_classification":
                    semantic_history_decision_qualification["classification"],
                "history_change_measurement": semantic_history_decision_qualification,
                "history_changed_new_action_decision":
                    transfer_history_changed_new_decision,
                "new_action_decision_classification": transfer_classification,
                "performance_improvement_established": False,
                "real_operator_observation_demonstrated": False,
                "real_action_consequence_demonstrated": False,
            },
            "objective_task_family_acquisition": {
                "status": acquisition_result.status,
                "measurement_id": acquisition_result.changed_cognition_measurement_id,
                "run_id": acquisition_run.get("run_id"),
                "run_digest": acquisition_run.get("run_digest"),
                "request_digest": acquisition_request.get("request_digest"),
                "task_family_id": objective_family,
                "score_status": acquisition_readiness["score_status"],
                "readiness_classification": acquisition_readiness["classification"],
                "probe_result_count": acquisition_readiness["probe_result_count"],
                "required_probe_count": acquisition_readiness["required_probe_count"],
                "task_outcome": acquisition_summary,
                "history_record_id": (acquisition_history_record.record_id
                    if acquisition_history_record is not None else None),
                "history_projection_audit": acquisition_history_projection_audit,
                "history_score_binding": acquisition_history_score_binding,
                "raw_answer_values_included": False,
                "performance_improvement_established": False,
                "learning_established": False,
                "authority": False,
            },
            "later_companion_decision_intervention": {
                "measurement_scope": "direct_historical_retrieval_not_new_action_transfer",
                "status": companion_intervention.status,
                "question_digest": companion_intervention.question_digest,
                "changed_cognition_measurement_id":
                    companion_intervention.changed_cognition_measurement_id,
                "response_text_classification": companion_intervention.response_text_classification,
                "semantic_decisions": semantic_decisions,
                "semantic_decision_classification": semantic_decision_classification,
                "rejected_decision_diagnostics": rejected_decision_diagnostics,
                "history_changed_cognition": semantic_history_changed,
                "performance_improvement_established": False,
                "controlled_inputs_match": intervention_inputs_match,
                "restored_prompt_matches": companion_intervention.restored_prompt_matches,
                "conditions": [{
                    "condition_id": item.get("condition_id"),
                    "response": item.get("response"),
                    "disposition": item.get("disposition"),
                    "model_disposition": item.get("model_disposition"),
                    "decision_validation_status": item.get(
                        "decision_validation_status", "validated"),
                    "decision_validation_error_code": item.get(
                        "decision_validation_error_code"),
                    "disposition_normalization": item.get(
                        "disposition_normalization"),
                    "rejected_output_diagnostic": item.get(
                        "rejected_output_diagnostic"),
                    "response_digest": item.get("response_digest"),
                    "output_digest": item.get("output_digest"),
                    "prompt_digest": item.get("prompt_digest"),
                    "generation_config": item.get("generation_config"),
                    "active_model_identity": item.get("active_model_identity"),
                    "snapshot_id": item.get("snapshot_id"),
                    "snapshot_digest": item.get("snapshot_digest"),
                    "matched_control_inputs": item.get("matched_control_inputs"),
                    "matched_control_inputs_digest": item.get(
                        "matched_control_inputs_digest"),
                    "current_fact_ids": item.get("current_fact_ids"),
                    "evidence_ids": list(item.get("evidence_ids", ())),
                    "retrieved_record_ids": item.get("retrieved_record_ids"),
                    "retrieved_record_digests": item.get(
                        "retrieved_record_digests"),
                    "history_record_ids": list(item.get("history_record_ids", ())),
                    "cognition_observation_id": item.get(
                        "cognition_observation_id"),
                    "cognition_observation_digest": item.get(
                        "cognition_observation_digest"),
                    "inference_receipt_id": item.get("inference_receipt_id"),
                    "inference_receipt_digest": item.get("inference_receipt_digest"),
                    "inference_status": item.get("inference_status"),
                    "cognition_receipt_output_binding_verified":
                        item.get("cognition_receipt_output_binding_verified"),
                } for item in companion_intervention.conditions],
                "authority": companion_intervention.authority,
                "action_authority": companion_intervention.action_authority,
                "canonical_explicit_user_retention_mutated":
                    companion_intervention.canonical_explicit_user_retention_mutated,
                "causal_or_learning_claim_made": False},
            "history_transfer_intervention": {
                **transfer_qualification,
                "measurement_scope": "new_action_proposal_not_execution",
                "status": transfer_status,
                "history_evidence_precondition": transfer_readiness,
                "question_digest": transfer_question_digest,
                "changed_cognition_measurement_id": transfer_measurement_id,
                "response_text_classification":
                    transfer_response_text_classification,
                "history_changed_new_action_decision":
                    transfer_history_changed_new_decision,
                "classification": transfer_classification,
                "controlled_inputs_match": transfer_controls_match,
                "restored_prompt_matches": transfer_restored_prompt_matches,
                "present_restored_output_digest_matches":
                    transfer_restoration_stable,
                "history_citation_bound": transfer_history_cited,
                "target_evidence_cited": transfer_qualification[
                    "target_evidence_cited"],
                "response_difference_observed": transfer_qualification[
                    "response_difference_observed"],
                "history_conditioned_response_difference_observed_under_matched_controls": (
                    transfer_qualification[
                        "history_conditioned_response_difference_observed_under_matched_controls"]),
                "history_treatment_bound": transfer_qualification[
                    "history_treatment_bound"],
                "grounded_new_decision_qualified": transfer_history_changed_new_decision,
                "qualification_failure_codes": transfer_qualification[
                    "qualification_failure_codes"],
                "conditions": [{
                    "condition_id": item.get("condition_id"),
                    "response": item.get("response"),
                    "disposition": item.get("disposition"),
                    "model_disposition": item.get("model_disposition"),
                    "decision_validation_status": item.get(
                        "decision_validation_status", "validated"),
                    "decision_validation_error_code": item.get(
                        "decision_validation_error_code"),
                    "disposition_normalization": item.get(
                        "disposition_normalization"),
                    "response_digest": item.get("response_digest"),
                    "output_digest": item.get("output_digest"),
                    "prompt_digest": item.get("prompt_digest"),
                    "snapshot_id": item.get("snapshot_id"),
                    "snapshot_digest": item.get("snapshot_digest"),
                    "matched_control_inputs": item.get("matched_control_inputs"),
                    "matched_control_inputs_digest": item.get(
                        "matched_control_inputs_digest"),
                    "current_fact_ids": item.get("current_fact_ids"),
                    "evidence_ids": list(item.get("evidence_ids", ())),
                    "retrieved_record_ids": item.get("retrieved_record_ids"),
                    "retrieved_record_digests": item.get(
                        "retrieved_record_digests"),
                    "history_record_ids": list(item.get("history_record_ids", ())),
                    "active_model_identity": item.get("active_model_identity"),
                    "generation_config": item.get("generation_config"),
                    "cognition_observation_id": item.get(
                        "cognition_observation_id"),
                    "cognition_observation_digest": item.get(
                        "cognition_observation_digest"),
                    "inference_receipt_id": item.get("inference_receipt_id"),
                    "inference_receipt_digest": item.get(
                        "inference_receipt_digest"),
                    "inference_status": item.get("inference_status"),
                    "cognition_receipt_output_binding_verified":
                        item.get("cognition_receipt_output_binding_verified"),
                } for item in transfer_conditions],
                "authority": transfer_authority,
                "action_authority": transfer_action_authority,
                "action_executed": False,
                "performance_improvement_established": False,
                "causal_or_learning_claim_made": False},
            "objective_task_family_transfer": {
                **objective_transfer_history,
                "history_selection_preflight": (
                    objective_transfer_history_selection_preflight),
                "history_condition_difference_observed": (
                    objective_transfer_evaluation.get(
                        "history_correct_probe_delta") not in (None, 0)
                    if objective_transfer_history.get("status")
                        == "completed_scored_intervention" else None),
                "history_answer_vector_difference_observed": (
                    _answer_vector_comparison(
                        objective_transfer_history.get("conditions"),
                        "history_present", "history_withheld")
                    if objective_transfer_history.get("status")
                        == "completed_scored_intervention" else None),
                "restored_answer_vector_matches_present": (
                    _answer_vector_match(
                        objective_transfer_history.get("conditions"),
                        "history_present", "history_restored")
                    if objective_transfer_history.get("status")
                        == "completed_scored_intervention" else None),
                "restoration_matches_present": (
                    objective_transfer_evaluation.get(
                        "restoration_correct_probe_delta") == 0
                    if objective_transfer_history.get("status")
                        == "completed_scored_intervention" else None),
                "causal_or_learning_claim_made": False,
                "interpretation": (
                    "one preregistered same-model exact-scored transfer episode; "
                    "not a general learning or real-world performance claim")},
            "objective_cross_range_history_enabled_competence": (
                objective_cross_range_history_probe),
            "historical_companion_recall": {
                "status": history_recall.get("status"),
                "response": history_recall.get("response"),
                "disposition": history_recall.get("disposition"),
                "history_record_ids": history_recall.get("history_record_ids", []),
                "prior_record_ids": history_recall.get("retrieved_record_ids", []),
                "cited_current_fact_ids": history_recall.get("cited_current_fact_ids", []),
                "snapshot_id": history_recall.get("snapshot_id"),
                "current_snapshot_digest": history_recall.get("snapshot_digest"),
                "response_lineage_verified": history_recall.get(
                    "response_lineage_verified") is True,
                "history_citation_bound": bool(history_recall.get("history_record_ids"))
                    and set(history_recall.get("history_record_ids", ())).issubset(
                        history_recall.get("retrieved_record_ids", ())),
                "historical_truth_claim_made": False,
                "reports_past_idle": _reports_past_idle(history_recall),
                "demonstrated_history_use": (_reports_past_idle(history_recall)
                    and _history_citation_bound(history_recall)
                    and history_recall.get("response_lineage_verified") is True),
            },
            "present_restoration_delivery_replay": present_restoration_delivery_replay,
            "history_intervention": {"validity": run_payload.get("validity"),
                "conditions": [{"condition_id": item.get("condition_id"),
                    "output_digest": item.get("output_digest"),
                    "prompt_digest": item.get("epistemic_prompt_digest"),
                    "generation_config": item.get("generation_config"),
                    "active_model_identity": item.get("active_model_identity"),
                    "retrieved_record_ids": item.get("retrieved_record_ids"),
                    "developmental_projection_present": item.get(
                        "developmental_projection_present")}
                    for item in conditions],
                "same_history_replay": same_history_replay,
                "restoration_stability_qualification": restoration_stability_qualification,
                "summary": summary,
                "causal_claim_made": False,
                "interpretation": "controlled history presence/withholding association only"},
            "gpu_before": before_gpu, "gpu_after": _gpu_snapshot(),
            "governed_unload": "pending",
        }
        session.close()
        result["governed_unload"] = "governed_release_completed"
        result["residency_verification"] = _verify_model_released(MODEL_NAME)
        result["gpu_after"] = _gpu_snapshot()
        _set_run_stage("source_provenance_finalization")
        RUN_SOURCE_PROVENANCE_AT_END = _source_provenance()
        if (RUN_SOURCE_PROVENANCE_AT_END != RUN_SOURCE_PROVENANCE
                or RUN_SOURCE_PROVENANCE_AT_END.get(
                    "worktree_content_status") != "complete"):
            raise RootlessExperimentalError(
                "source_provenance_changed_during_experiment")
        result["source_provenance_at_completion"] = dict(
            RUN_SOURCE_PROVENANCE_AT_END)
        result["source_provenance_stable_for_run"] = True
        result["source_provenance_fingerprint_complete"] = True
        _set_run_stage("complete_result_persistence")
        out = RUN_ROOT / "cycle-result.json"
        result["evidence_path"] = str(out)
        out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(out, 0o600)
        return result
    finally:
        session.close()


if __name__ == "__main__":
    try:
        result = run()
    except Exception as exc:
        python_failure_diagnostic = _bounded_python_failure_diagnostic(exc)
        failure_artifact = None
        try:
            failure_artifact = _persist_incomplete_run(exc)
        except Exception:
            # Evidence persistence must not hide the original experiment failure.
            pass
        print(json.dumps({"status": "incomplete", "run_id": RUN_ID,
            "stage": RUN_STAGE, "failure_type": type(exc).__name__,
            "failure_code": _failure_code(exc),
            "python_failure_diagnostic": python_failure_diagnostic,
            "source_provenance_preflight_evidence_path": (
                SOURCE_PROVENANCE_PREFLIGHT_EVIDENCE_PATH),
            "model_identity_preflight_evidence_path":
                HISTORICAL_PAIR_MODEL_IDENTITY_PREFLIGHT_PATH,
            "failure_artifact": str(failure_artifact) if failure_artifact else None,
            "causal_or_learning_claim_made": False}, sort_keys=True, indent=2))
        raise
    print(json.dumps(result, sort_keys=True, indent=2))
