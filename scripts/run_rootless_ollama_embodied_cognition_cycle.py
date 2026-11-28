Warning: truncated output (original token count: 121727)
Total output lines: 8740

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
    OWNER_COGNITION_FEEDBACK_INTERPRETATION,
    OWNER_COGNITION_FEEDBACK_PROVENANCE_KIND,
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
_ACTIVE_OBJECTIVE_ACQUISITION_PROBE_COUNT = 3
_ACTIVE_OBJECTIVE_TRANSFER_PROBE_COUNT = 3
_SUPPORTED_OBJECTIVE_TRANSFER_TASK_FAMILIES = frozenset({
    "rootless_integer_affine_transfer_low_range_v5",
    _OBJECTIVE_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
    ROOTLESS_INTEGER_AFFINE_NOVEL_TRANSFER_TASK_FAMILY,
})

# Leave bounded space for receipt-backed evidence plus its prior-history packet.
# The model remains configured with an 8,192-token context. CPU-side packet
# measurement found that the held-out transfer's three required, compact,
# score-bound records need about 26.6K prompt characters; retain a bounded
# margin; the model's configured 8,192-token context remains unchanged.
ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT = 28_672
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
    global _ACTIVE_OBJECTIVE_ACQUISITION_PROBE_COUNT
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
        if OWNER_FEEDBACK_PROTOCOL_DIGEST != "0" * 64:
            if OWNER_FEEDBACK_PROTOCOL_DIGEST != (
                    _owner_feedback_recall_protocol_digest()):
                raise RootlessExperimentalError(
                    "owner_feedback_protocol_preregistration_mismatch")
        if plan.get("schema_version") in {
                "sentientos.rootless_history_boundary_campaign_plan:v7",
                "sentientos.rootless_history_boundary_campaign_plan:v8",
                "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13",
                "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}:
            verify_model_identity_recipe(plan)
            if plan.get("schema_version") in {
                    "sentientos.rootless_history_boundary_campaign_plan:v8",
                    "sentientos.rootless_history_boundary_campaign_plan:v9",
                    "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                    "sentientos.rootless_history_boundary_campaign_plan:v13",
                    "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}:
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
                    "sentientos.rootless_history_boundary_campaign_plan:v13",
                    "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"})):
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
    _ACTIVE_OBJECTIVE_ACQUISITION_PROBE_COUNT = plan.get(
        "acquisition_probe_count", 3)
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
                "sentientos.rootless_history_boundary_campaign_plan:v13",
                "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}:
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
            acquisition_probe_count=plan.get("acquisition_probe_count", 3),
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


def _owner_feedback_protocol_digest_from_environment() -> str:
    # This is distinct from the campaign-plan preregistration digest above.
    raw = os.environ.get("SENTIENTOS_HERMES_OWNER_FEEDBACK_PROTOCOL_DIGEST")
    if raw is None:
        return "0" * 64
    if (len(raw) != 64 or not raw.isascii()
            or any(character not in "0123456789abcdef" for character in raw)):
        raise SystemExit("hermes_owner_feedback_protocol_digest_invalid")
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
    live_p…71727 tokens truncated…capability_evaluated": False,
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
                    "missing_required_history_record_digests": [
                        required_digest_by_id[record_id]
                        for record_id in missing_required_history_ids],
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
                        "missing_required_history_record_digests": [
                            required_digest_by_id[record_id]
                            for record_id in missing_required_history_ids],
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
                "schema_version": "sentientos.history_transfer_evidence_precondition:v3",
                "eligible": False,
                "reason_code": "no_new_action_consequence_record",
                "record_id": None,
                "retained_record_digest": None,
                "retained_record_snapshot_binding_posture": "unavailable",
                "evidence_fact_ids": [],
                "pattern_match_fact_ids": [],
                "provenance_failure_codes": [],
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
        cross_cycle_owner_feedback_recall = (
            _run_cross_cycle_owner_feedback_recall(
                owner=intervention_owner, snapshot=later_pre_action_snapshot,
                tick_id=RUN_ID + ":cross-cycle-owner-feedback-recall",
                trial_index=HISTORY_INTERVENTION_TRIAL_INDEX,
                preregistered=(campaign_plan is not None
                    and campaign_cycle_index > 0
                    and RUN_PREREGISTRATION_DIGEST is not None
                    and prior_feedback_reference.get("status") in {
                        "prior_cycle_feedback_reference_bound",
                        "previous_cycle_created_no_owner_feedback_record"}),
                cycle_index=(campaign_cycle_index
                    if campaign_plan is not None else -1),
                prior_feedback_reference=(prior_feedback_reference
                    if campaign_plan is not None else {
                        "status": "not_preregistered_cross_cycle_campaign"})))
        from work.rootless_history_boundary_campaign import (
            _cognition_recovery_state_boundary)
        cognition_recovery_state_boundary = _cognition_recovery_state_boundary(
            state_root)
        result = {
            "schema_version": "sentientos.rootless_ollama_embodied_cognition_cycle:v21",
            "run_id": RUN_ID, "status": "completed",
            "execution_posture": "rootless_experimental_nonproduction",
            "source_provenance": dict(RUN_SOURCE_PROVENANCE),
            "external_preregistration_digest": _optional_preregistration_digest(
                PREREGISTRATION_DIGEST),
            "owner_feedback_recall_protocol_digest": (
                _optional_preregistration_digest(
                    OWNER_FEEDBACK_PROTOCOL_DIGEST)),
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
            "cross_cycle_owner_feedback_recall": (
                cross_cycle_owner_feedback_recall),
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
                "owner_feedback_record_id":
                    companion_intervention.feedback_record_id,
                "owner_feedback_writeback_receipt_id":
                    companion_intervention.feedback_writeback_receipt_id,
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
