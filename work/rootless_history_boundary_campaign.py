"""Pre-register and audit append-only history boundaries across rootless cycles.

The tool is offline. It binds an initial history snapshot to an ordered cycle
plan, then checks that each completed or incomplete cycle root retains every prior
developmental record and writeback receipt byte-for-byte. It establishes local
file continuity only; it does not establish independent timing, model use, or
learning.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.developmental_history_intervention_experiment import (  # noqa: E402
    _digest as _experiment_digest,
)
from sentientos.local_runtime_provisioning import semantic_digest as _runtime_digest  # noqa: E402
from sentientos.governed_local_model_invocation import (  # noqa: E402
    validate_receipt as _validate_inference_receipt,
)
from sentientos.developmental_model_replacement_experiment import (  # noqa: E402
    rootless_integer_affine_transfer_task_pair,
)
from sentientos.resident_developmental_cognition import (  # noqa: E402
    _task_family_history_examples,
    _task_family_history_probe_overlap,
)
from work.export_rootless_cycle_evidence_manifest import (  # noqa: E402
    _cycle_identity,
    _hash_regular_file,
    create_manifest,
    persist_manifest,
)

_CYCLE_ID = re.compile(r"rootless-cognition-cycle-[0-9a-f]{20}")
_CAMPAIGN_ID = re.compile(r"rootless-history-campaign-[0-9a-f]{20}")
_RUN_ID = re.compile(r"devexp-run-[0-9a-f]{24}")
_TASK_FAMILY = "rootless_integer_affine_transfer_low_range_v6"
_WIDE_TASK_FAMILY = "rootless_integer_affine_transfer_wide_range_v7"
_NOVEL_TASK_FAMILY = "rootless_integer_affine_transfer_novel_range_v8"
_RANGE_TASK_FAMILIES = frozenset({_WIDE_TASK_FAMILY, _NOVEL_TASK_FAMILY})
_SUPPORTED_TASK_FAMILIES = frozenset({_TASK_FAMILY, *_RANGE_TASK_FAMILIES})
_EMPTY_HISTORY_BOOTSTRAP_PROTOCOL = {
    "schema_version": "sentientos.initial_history_bootstrap_protocol:v1",
    "trigger": "verified_empty_resident_writeback_inventory",
    "condition_id": "durable-learning-history-withheld",
    "owner_comparison_enabled": False,
    "maximum_observations": 1,
    "verify_invocation_and_writeback_receipts": True,
    "require_zero_retrieved_prior_records": True,
    "require_single_new_record": True,
    "record_is_score_bound_task_family_evidence": False,
    "learning_established": False,
    "authority": False,
}
_CROSS_RANGE_HISTORY_ENABLED_COMPETENCE_PROTOCOL_V1 = {
    "schema_version": "sentientos.cross_range_history_enabled_competence_protocol:v1",
    "source_task_family_id": _TASK_FAMILY,
    "target_task_family_id": _WIDE_TASK_FAMILY,
    "conditions": ["history_present", "history_withheld", "history_restored"],
    "minimum_score_bound_correct_source_runs": 2,
    "minimum_distinct_correct_source_inputs": 3,
    "require_unique_correct_input_contribution_per_source_run": True,
    "require_zero_overlap_with_all_declared_history_families": True,
    "require_exact_source_record_receipts_present_restored": True,
    "minimum_planned_cycles": 2,
    "cross_cycle_history_posture": "append_only_campaign_history",
    "baseline_competence_required": False,
    "claim_scope": "history_conditioned_capability_pattern_only",
}
_CROSS_RANGE_HISTORY_ENABLED_COMPETENCE_PROTOCOL = {
    **_CROSS_RANGE_HISTORY_ENABLED_COMPETENCE_PROTOCOL_V1,
    "schema_version": "sentientos.cross_range_history_enabled_competence_protocol:v2",
    "per_probe_outcomes_required": True,
    "probe_outcome_schema_version":
        "sentientos.objective_probe_transition_summary:v1",
    "score_digest_binding_required": True,
    "answer_values_in_summary": False,
}
_LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL = {
    "schema_version": "sentientos.low_range_source_acquisition_protocol:v1",
    "task_family_id": _TASK_FAMILY,
    "minimum_score_bound_correct_source_runs": 2,
    "minimum_distinct_correct_source_inputs": 3,
    "require_unique_correct_input_contribution_per_source_run": True,
    "require_independent_oracle_scoring": True,
    "require_invocation_and_writeback_receipt_binding": True,
    # The low acquisition domain has only four inputs. Requiring two
    # three-probe runs to be disjoint is impossible, so eligibility counts
    # distinct correct inputs across the source set while preserving the
    # within-run acquisition/transfer separation checks below.
    "cross_cycle_probe_reuse_allowed": True,
    "learning_established": False,
    "authority": False,
}
_MAX_BOUNDARY_FILES = 50_000
_MAX_BOUNDARY_BYTES = 2 * 1024 * 1024 * 1024
_MAX_RECOVERY_STATE_BYTES = 64 * 1024 * 1024
_MODEL_IDENTITY_IMPLEMENTATION_FILES = (
    "sentientos/local_model.py",
    "sentientos/rootless_experimental_ollama_epistemic_session.py",
    "sentientos/rootless_experimental_local_model.py",
    "work/rootless_history_boundary_campaign.py",
)
_EXPERIMENT_IMPLEMENTATION_EXTRA_FILES = (
    "scripts/run_rootless_ollama_embodied_cognition_cycle.py",
    "scripts/preflight_resident_strategy_inclusion_pair.py",
    "work/rootless_history_boundary_campaign.py",
    "work/replay_planned_cycle_owner_preflight.py",
    "work/audit_history_transfer_preconditions.py",
    "work/strategy_inclusion_intervention.py",
    "semantic_embeddings.py",
    "docs/development/authenticated_observer_ingress_receipt.schema.json",
    "docs/development/observation_authentication_receipt_summary.schema.json",
    "docs/development/history_transfer_evidence_precondition.schema.json",
    "docs/development/history_transfer_precondition_audit.schema.json",
    "docs/development/rootless_history_boundary_campaign_plan.schema.json",
    "docs/development/rootless_novel_acquisition_transfer_probe_preflight.schema.json",
    "docs/development/rootless_history_boundary_campaign_audit.schema.json",
    "docs/development/rootless_planned_cycle_strategy_inclusion_ablation.schema.json",
    "docs/development/rootless_planned_cycle_historical_examples_ablation.schema.json",
    "docs/development/developmental_history_task_score_lineage_failure.schema.json",
    "docs/development/owner_cognition_feedback_cross_cycle_recall_protocol.json",
)
_EXPERIMENT_IMPLEMENTATION_ROOT_PACKAGES = (
    "agents", "codex", "control_plane", "daemon", "embodiment",
    "gp_plugins", "gui", "hf_intake", "privilege_lint", "witness",
)
_EXPERIMENT_IMPLEMENTATION_PATH = re.compile(
    r"(?:[A-Za-z_][A-Za-z0-9_]*\.py|sentientos/.+\.py|"
    r"scripts/.+\.py|work/.+\.py|[A-Za-z_][A-Za-z0-9_]*/.+\.py|"
    r"semantic_embeddings\.py|"
    r"docs/development/(?:owner_cognition_feedback_cross_cycle_recall_protocol\.json|"
    r"(?:authenticated_observer_ingress_receipt|"
    r"observation_authentication_receipt_summary|"
    r"history_transfer_evidence_precondition|"
    r"history_transfer_precondition_audit|"
    r"rootless_history_boundary_campaign_plan|"
    r"rootless_novel_acquisition_transfer_probe_preflight|"
    r"rootless_history_boundary_campaign_audit|"
    r"rootless_planned_cycle_strategy_inclusion_ablation|"
    r"rootless_planned_cycle_historical_examples_ablation|"
    r"developmental_history_task_score_lineage_failure)\.schema\.json))\Z")


def _model_identity_implementation_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative_path in _MODEL_IDENTITY_IMPLEMENTATION_FILES:
        path = REPO_ROOT / relative_path
        if path.is_symlink() or not path.is_file():
            raise ValueError("history_campaign_model_identity_implementation_missing")
        normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        hashes[relative_path] = hashlib.sha256(normalized).hexdigest()
    return hashes


def _experiment_implementation_hashes() -> dict[str, str]:
    """Pin cognition modules, repository-root helpers, and experiment entrypoints."""
    paths = {path.relative_to(REPO_ROOT).as_posix(): path
        for path in (REPO_ROOT / "sentientos").rglob("*.py")}
    # SentientOS modules import legacy repository-root Python modules directly
    # (for example, sentientos.codex_startup_guard imports policy_digest.py).
    # Pin every importable root module so a clean experiment source snapshot
    # cannot silently omit an unbound runtime dependency.
    paths.update({path.name: path for path in REPO_ROOT.glob("*.py")
        if path.name[:1].isidentifier() and not path.is_symlink()})
    # Runner and campaign modules import helpers from these two repository
    # subtrees; include the import closure, not just the initially visible
    # entrypoints.
    for source_dir in ("scripts", "work"):
        paths.update({path.relative_to(REPO_ROOT).as_posix(): path
            for path in (REPO_ROOT / source_dir).rglob("*.py")})
    for package_dir in _EXPERIMENT_IMPLEMENTATION_ROOT_PACKAGES:
        paths.update({path.relative_to(REPO_ROOT).as_posix(): path
            for path in (REPO_ROOT / package_dir).rglob("*.py")})
    for relative_path in _EXPERIMENT_IMPLEMENTATION_EXTRA_FILES:
        paths[relative_path] = REPO_ROOT / relative_path
    hashes: dict[str, str] = {}
    for relative_path, path in sorted(paths.items()):
        if path.is_symlink() or not path.is_file():
            raise ValueError("history_campaign_experiment_implementation_missing")
        normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        hashes[relative_path] = hashlib.sha256(normalized).hexdigest()
    return hashes


def verify_experiment_implementation(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Require the plan's pinned source tree to match the current worktree."""
    expected = plan.get("experiment_implementation_sha256")
    if (plan.get("schema_version") not in {
                "sentientos.rootless_history_boundary_campaign_plan:v8",
                "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13",
                "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}
            or not isinstance(expected, Mapping)):
        raise ValueError("history_campaign_experiment_implementation_unbound")
    current = _experiment_implementation_hashes()
    if dict(expected) != current:
        raise ValueError("history_campaign_experiment_implementation_mismatch")
    return {
        "experiment_implementation_source_count": len(current),
        "experiment_implementation_digest": digest_payload(current),
        "experiment_implementation_bound": True,
        "experiment_implementation_matches_current": True,
        "inference_performed": False,
    }


def _history_boundary(history_root: Path) -> dict[str, Any]:
    if history_root.is_symlink():
        raise ValueError("history_boundary_root_symlink")
    root = history_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("history_boundary_root_invalid")
    files: list[dict[str, Any]] = []
    total_bytes = 0
    for collection in ("records", "receipts"):
        collection_root = root / collection
        if collection_root.is_symlink() or not collection_root.is_dir():
            raise ValueError("history_boundary_collection_missing_or_invalid")
        for current, directories, names in os.walk(collection_root,
                topdown=True, followlinks=False):
            current_path = Path(current)
            directories.sort()
            names.sort()
            for name in directories:
                path = current_path / name
                if path.is_symlink() or not path.is_dir():
                    raise ValueError("history_boundary_directory_invalid")
            for name in names:
                path = current_path / name
                relative = path.relative_to(root).as_posix()
                if path.parent != collection_root:
                    raise ValueError("history_boundary_nested_store_path_invalid")
                identity_pattern = (r"devrec-[0-9a-f]{24}\.json"
                    if collection == "records" else
                    r"devreceipt-[0-9a-f]{24}\.json")
                if re.fullmatch(identity_pattern, path.name) is None:
                    raise ValueError("history_boundary_store_filename_invalid")
                if len(files) >= _MAX_BOUNDARY_FILES:
                    raise ValueError("history_boundary_file_count_over_bound")
                file_digest, size = _hash_regular_file(path)
                total_bytes += size
                if total_bytes > _MAX_BOUNDARY_BYTES:
                    raise ValueError("history_boundary_total_size_over_bound")
                files.append({"path": relative, "size_bytes": size,
                    "sha256": file_digest})
    files.sort(key=lambda row: row["path"])
    semantic = {"schema_version": "sentientos.rootless_history_boundary:v1",
        "file_count": len(files), "total_size_bytes": total_bytes,
        "files": files, "atomic_snapshot": False}
    return {**semantic, "boundary_digest": digest_payload(semantic)}


def _runtime_admission_boundary(history_root: Path,
        history_boundary: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Bind the sealed admission ledger needed to recover seeded records."""
    from sentientos.runtime_admission import AdmissionLedger
    from sentientos.resident_developmental_writeback import DevelopmentalHistoryStore

    boundary = dict(history_boundary or _history_boundary(history_root))
    ledger_path = history_root.parent / "state" / "runtime_admissions.json"
    if not ledger_path.exists() and not ledger_path.is_symlink():
        if boundary.get("file_count"):
            raise ValueError("history_campaign_runtime_admission_ledger_missing")
        return None
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise ValueError("history_campaign_runtime_admission_ledger_invalid")
    admissions, revocations = AdmissionLedger(ledger_path).load()
    admission_ids = {item.admission_id for item in admissions}
    records = DevelopmentalHistoryStore(history_root).records()
    if any(not record.admission_id or record.admission_id not in admission_ids
            for record in records):
        raise ValueError("history_campaign_record_admission_unbound")
    digest, size = _hash_regular_file(ledger_path)
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


def _cognition_recovery_state_boundary(state_root: Path) -> dict[str, Any] | None:
    """Bind the durable tick order and observations required to recover history."""
    if state_root.is_symlink():
        raise ValueError("history_campaign_recovery_state_root_invalid")
    if not state_root.exists():
        return None
    state_root = state_root.resolve(strict=True)
    composition_path = state_root / "composition_state.json"
    if composition_path.is_symlink() or not composition_path.is_file():
        return None
    try:
        composition_raw = composition_path.read_bytes()
        composition = json.loads(composition_raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("history_campaign_composition_state_invalid") from exc
    if (not isinstance(composition, Mapping)
            or json.dumps(composition, indent=2, sort_keys=True).encode("utf-8")
                + b"\n" != composition_raw):
        raise ValueError("history_campaign_composition_state_noncanonical")
    semantic = {key: value for key, value in composition.items()
        if key != "state_digest"}
    if composition.get("state_digest") != "sha256:" + digest_payload(semantic):
        raise ValueError("history_campaign_composition_state_digest_invalid")
    completed = composition.get("completed_ticks")
    incomplete = composition.get("incomplete_ticks")
    if (not isinstance(completed, list) or not isinstance(incomplete, list)
            or any(not isinstance(row, Mapping)
                or not isinstance(row.get("tick_id"), str)
                or not row.get("tick_id") for row in completed + incomplete)
            or len({row["tick_id"] for row in completed + incomplete})
                != len(completed) + len(incomplete)):
        raise ValueError("history_campaign_composition_state_shape_invalid")
    files: list[dict[str, Any]] = []
    total_bytes = 0
    composition_digest, composition_size = _hash_regular_file(composition_path)
    files.append({"path": "composition_state.json", "sha256": composition_digest,
        "size_bytes": composition_size})
    cycle_root = state_root.parent.parent
    receipt_files: dict[str, dict[str, Any]] = {}
    observations_root = state_root / "cognition_observations"
    if observations_root.exists() or observations_root.is_symlink():
        if observations_root.is_symlink() or not observations_root.is_dir():
            raise ValueError("history_campaign_observation_root_invalid")
        for current, directories, names in os.walk(observations_root,
                topdown=True, followlinks=False):
            directories.sort()
            names.sort()
            if directories:
                raise ValueError("history_campaign_observation_nested_directory_invalid")
            for name in names:
                path = Path(current) / name
                if re.fullmatch(r"devcog-[0-9a-f]{24}\.json", name) is None:
                    raise ValueError("history_campaign_observation_filename_invalid")
                file_digest, size = _hash_regular_file(path)
                files.append({"path": "cognition_observations/" + name,
                    "sha256": file_digest, "size_bytes": size})
                try:
                    observation_raw = path.read_bytes()
                    observation = json.loads(observation_raw.decode("utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        "history_campaign_observation_payload_invalid") from exc
                if (not isinstance(observation, Mapping)
                        or json.dumps(observation, indent=2, sort_keys=True).encode(
                            "utf-8") + b"\n" != observation_raw):
                    raise ValueError(
                        "history_campaign_observation_payload_noncanonical")
                receipt_id = observation.get("inference_receipt_id")
                if isinstance(receipt_id, str):
                    if re.fullmatch(r"lmrec-[0-9a-f]{24}", receipt_id) is None:
                        raise ValueError(
                            "history_campaign_observation_receipt_identity_invalid")
                    receipt_path = (cycle_root / "inference-custody" / "receipts"
                        / f"{receipt_id}.json")
                    try:
                        receipt_digest, receipt_size = _hash_regular_file(receipt_path)
                    except (OSError, ValueError) as exc:
                        raise ValueError(
                            "history_campaign_observation_receipt_missing") from exc
                    receipt_relative = f"inference-custody/receipts/{receipt_id}.json"
                    receipt_files[receipt_relative] = {"path": receipt_relative,
                        "sha256": receipt_digest, "size_bytes": receipt_size}
    files.extend(receipt_files.values())
    files.sort(key=lambda row: row["path"])
    total_bytes = sum(row["size_bytes"] for row in files)
    if total_bytes > _MAX_RECOVERY_STATE_BYTES:
        raise ValueError("history_campaign_recovery_state_over_bound")
    completed_bindings = [{"tick_id": row["tick_id"],
        "row_digest": digest_payload(dict(row))} for row in completed]
    incomplete_bindings = [{"tick_id": row["tick_id"],
        "status": row.get("status"),
        "row_digest_without_status": digest_payload({key: value
            for key, value in row.items() if key != "status"})}
        for row in incomplete]
    body = {"schema_version": "sentientos.rootless_cognition_recovery_state:v1",
        "files": files, "file_count": len(files),
        "total_size_bytes": total_bytes,
        "completed_tick_bindings": completed_bindings,
        "incomplete_tick_bindings": incomplete_bindings,
        "atomic_snapshot": False}
    return {**body, "boundary_digest": digest_payload(body)}


def _valid_cognition_recovery_state_boundary(value: Any) -> bool:
    if value is None:
        return True
    required = {"schema_version", "files", "file_count", "total_size_bytes",
        "completed_tick_bindings", "incomplete_tick_bindings", "atomic_snapshot",
        "boundary_digest"}
    if (not isinstance(value, Mapping) or set(value) != required
            or value.get("schema_version") !=
                "sentientos.rootless_cognition_recovery_state:v1"
            or value.get("atomic_snapshot") is not False
            or not isinstance(value.get("files"), list)
            or type(value.get("file_count")) is not int
            or value["file_count"] != len(value["files"])
            or type(value.get("total_size_bytes")) is not int
            or not 0 <= value["total_size_bytes"] <= _MAX_RECOVERY_STATE_BYTES
            or not isinstance(value.get("completed_tick_bindings"), list)
            or not isinstance(value.get("incomplete_tick_bindings"), list)
            or not isinstance(value.get("boundary_digest"), str)):
        return False
    names: list[str] = []
    total = 0
    for row in value["files"]:
        path = row.get("path") if isinstance(row, Mapping) else None
        if (not isinstance(row, Mapping)
                or set(row) != {"path", "sha256", "size_bytes"}
                or not isinstance(path, str)
                or (path != "composition_state.json"
                    and re.fullmatch(
                        r"(?:cognition_observations/devcog-[0-9a-f]{24}\.json|"
                        r"inference-custody/receipts/lmrec-[0-9a-f]{24}\.json)",
                        path) is None)
                or not isinstance(row.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None
                or type(row.get("size_bytes")) is not int
                or not 0 <= row["size_bytes"] <= _MAX_RECOVERY_STATE_BYTES):
            return False
        names.append(path)
        total += row["size_bytes"]
    if (names != sorted(set(names)) or total != value["total_size_bytes"]
            or "composition_state.json" not in names):
        return False
    for key, fields in (("completed_tick_bindings", {"tick_id", "row_digest"}),
            ("incomplete_tick_bindings", {"tick_id", "status",
                "row_digest_without_status"})):
        tick_ids = []
        for row in value[key]:
            if (not isinstance(row, Mapping) or set(row) != fields
                    or not isinstance(row.get("tick_id"), str)
                    or not row["tick_id"]
                    or not isinstance(row.get("row_digest" if key ==
                        "completed_tick_bindings" else "row_digest_without_status"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", row.get("row_digest" if key ==
                        "completed_tick_bindings" else "row_digest_without_status")) is None
                    or (key == "incomplete_tick_bindings"
                        and row.get("status") not in {"in_progress",
                            "interrupted_recovered", "incomplete_recovered"})):
                return False
            tick_ids.append(row["tick_id"])
        if len(set(tick_ids)) != len(tick_ids):
            return False
    body = {key: item for key, item in value.items()
        if key != "boundary_digest"}
    return value["boundary_digest"] == digest_payload(body)


def _cognition_recovery_state_preserves(previous: Mapping[str, Any] | None,
        current: Mapping[str, Any] | None) -> bool:
    if previous is None:
        return current is None or isinstance(current, Mapping)
    if not isinstance(current, Mapping):
        return False
    previous_files = {row.get("path"): row for row in previous.get("files", [])
        if isinstance(row, Mapping)}
    current_files = {row.get("path"): row for row in current.get("files", [])
        if isinstance(row, Mapping)}
    if any(current_files.get(path) != row for path, row in previous_files.items()
            if path != "composition_state.json"):
        return False
    previous_completed = {row.get("tick_id"): row.get("row_digest")
        for row in previous.get("completed_tick_bindings", [])
        if isinstance(row, Mapping)}
    current_completed = {row.get("tick_id"): row.get("row_digest")
        for row in current.get("completed_tick_bindings", [])
        if isinstance(row, Mapping)}
    if any(current_completed.get(tick_id) != row_digest
            for tick_id, row_digest in previous_completed.items()):
        return False
    previous_incomplete = {row.get("tick_id"): row
        for row in previous.get("incomplete_tick_bindings", [])
        if isinstance(row, Mapping)}
    current_incomplete = {row.get("tick_id"): row
        for row in current.get("incomplete_tick_bindings", [])
        if isinstance(row, Mapping)}
    for tick_id, row in previous_incomplete.items():
        observed = current_incomplete.get(tick_id)
        if not isinstance(observed, Mapping):
            return False
        if (observed.get("row_digest_without_status") !=
                row.get("row_digest_without_status")):
            return False
        prior_status = row.get("status")
        current_status = observed.get("status")
        if current_status != prior_status and not (
                prior_status == "in_progress"
                and current_status in {"interrupted_recovered", "incomplete_recovered"}):
            return False
    return True


def _read_manifest_bound_file(*, root: Path, manifest: Mapping[str, Any],
        relative_path: str) -> bytes:
    files = manifest.get("files")
    row = next((item for item in files if isinstance(item, Mapping)
        and item.get("path") == relative_path), None) if isinstance(files, list) else None
    if not isinstance(row, Mapping):
        raise ValueError("history_campaign_manifest_file_missing")
    path = root.joinpath(*relative_path.split("/"))
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or path.is_symlink()
            or before.st_nlink != 1 or before.st_size > 128 * 1024 * 1024):
        raise ValueError("history_campaign_manifest_file_invalid")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if ((opened.st_dev, opened.st_ino, opened.st_size) !=
                (before.st_dev, before.st_ino, before.st_size)
                or not stat.S_ISREG(opened.st_mode)):
            raise ValueError("history_campaign_manifest_file_changed_before_read")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(128 * 1024 * 1024 + 1)
        after = os.fstat(descriptor)
        path_after = path.lstat()
        if ((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or (opened.st_dev, opened.st_ino, opened.st_size) !=
                    (path_after.st_dev, path_after.st_ino, path_after.st_size)
                or not stat.S_ISREG(path_after.st_mode)
                or len(raw) != row.get("size_bytes")
                or hashlib.sha256(raw).hexdigest() != row.get("sha256")):
            raise ValueError("history_campaign_manifest_file_digest_mismatch")
        return raw
    finally:
        os.close(descriptor)


def _require_output_outside(output_path: Path, roots: list[Path]) -> None:
    output = output_path.resolve(strict=False)
    for root in roots:
        resolved_root = root.resolve(strict=True)
        try:
            output.relative_to(resolved_root)
        except ValueError:
            continue
        raise ValueError("history_campaign_output_inside_evidence_root")


def _persist_or_verify(value: Mapping[str, Any], output_path: Path, *,
        verify_existing: bool) -> str:
    if not verify_existing:
        persist_manifest(dict(value), output_path)
        return "created"
    if (output_path.is_symlink() or not output_path.is_file()
            or output_path.stat().st_size > 64 * 1024 * 1024):
        raise ValueError("history_campaign_existing_artifact_invalid")
    parent = output_path.parent.resolve(strict=True)
    if output_path.parent.absolute() != parent:
        raise ValueError("history_campaign_existing_artifact_parent_invalid")
    before = output_path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("history_campaign_existing_artifact_invalid")
    descriptor = os.open(output_path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if ((opened.st_dev, opened.st_ino, opened.st_size) !=
                (before.st_dev, before.st_ino, before.st_size)
                or not stat.S_ISREG(opened.st_mode)):
            raise ValueError("history_campaign_existing_artifact_changed")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(64 * 1024 * 1024 + 1)
        after = os.fstat(descriptor)
        path_after = output_path.lstat()
        if ((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or (opened.st_dev, opened.st_ino, opened.st_size) !=
                    (path_after.st_dev, path_after.st_ino, path_after.st_size)
                or not stat.S_ISREG(path_after.st_mode)):
            raise ValueError("history_campaign_existing_artifact_changed")
    finally:
        os.close(descriptor)
    expected = (json.dumps(dict(value), sort_keys=True,
        separators=(",", ":")) + "\n").encode("utf-8")
    if raw != expected:
        raise ValueError("history_campaign_existing_artifact_mismatch")
    return "verified"


def derive_model_identity_digests(*, manifest_path: Path, model_name: str,
        gpu_layers: int, backend_seeds: list[int]) -> list[str]:
    """Precompute seed-specific Ollama identities without loading a model."""
    from sentientos.local_model import (ActiveModelIdentity, GenerationConfig,
        ModelCandidate, ModelConfig, candidate_artifact_identity,
        candidate_configuration_digest)
    from sentientos.rootless_experimental_ollama_epistemic_session import (
        _rootless_ollama_model_options)
    from sentientos.local_model_authority import digest_payload
    from sentientos.rootless_experimental_local_model import (
        EXPERIMENT_ROOT, _no_symlink_path)

    if (not isinstance(model_name, str) or not model_name.strip()
            or type(gpu_layers) is not int or not 0 <= gpu_layers <= 128
            or not isinstance(backend_seeds, list)
            or any(type(seed) is not int or not 0 <= seed <= 2**31 - 1
                for seed in backend_seeds)):
        raise ValueError("history_campaign_model_identity_inputs_invalid")
    try:
        experiment_root = _no_symlink_path(EXPERIMENT_ROOT).resolve(strict=True)
        path = _no_symlink_path(manifest_path.expanduser()).resolve(strict=True)
        path.relative_to(experiment_root)
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError("history_campaign_model_manifest_outside_custody") from exc
    if not path.is_file():
        raise ValueError("history_campaign_model_manifest_invalid")
    manifest_digest, manifest_size = _hash_regular_file(path)
    if path.stem != manifest_digest:
        raise ValueError("history_campaign_model_manifest_digest_mismatch")
    identities: list[str] = []
    for seed in backend_seeds:
        options = _rootless_ollama_model_options(model_name=model_name,
            manifest_digest=manifest_digest, gpu_layers=gpu_layers)
        options["seed"] = seed
        candidate = ModelCandidate(path, "ollama", model_name, options)
        config = ModelConfig([candidate], default_engine="ollama",
            max_context_tokens=8192,
            generation=GenerationConfig(max_new_tokens=512, temperature=0,
                top_p=1))
        resolved, semantic, content_digest, size, sidecar_digest = (
            candidate_artifact_identity(candidate, {}))
        identity = ActiveModelIdentity(engine="ollama",
            resolved_artifact_path=resolved,
            semantic_artifact_identity=semantic,
            model_content_sha256=content_digest,
            artifact_size_bytes=size,
            sidecar_metadata_digest=sidecar_digest,
            configuration_digest=candidate_configuration_digest(candidate,
                config, "ollama"),
            candidate_index=0, posture="development_only", fallback=False)
        if (content_digest != manifest_digest or size != manifest_size
                or sidecar_digest != manifest_digest):
            raise ValueError("history_campaign_model_manifest_identity_invalid")
        identities.append(digest_payload({"identity": identity.to_dict()}))
    return identities


def build_model_identity_recipe(*, manifest_path: Path, model_name: str,
        gpu_layers: int) -> dict[str, Any]:
    """Persist the exact non-inference inputs that derive campaign model pins."""
    from sentientos.rootless_experimental_ollama_epistemic_session import (
        _rootless_ollama_model_options)
    from sentientos.rootless_experimental_local_model import (
        EXPERIMENT_ROOT, _no_symlink_path)
    try:
        experiment_root = _no_symlink_path(EXPERIMENT_ROOT).resolve(strict=True)
        path = _no_symlink_path(manifest_path.expanduser()).resolve(strict=True)
        path.relative_to(experiment_root)
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError("history_campaign_model_manifest_outside_custody") from exc
    manifest_digest, _ = _hash_regular_file(path)
    if (path.stem != manifest_digest or not isinstance(model_name, str)
            or not model_name.strip() or type(gpu_layers) is not int
            or not 0 <= gpu_layers <= 128):
        raise ValueError("history_campaign_model_identity_recipe_invalid")
    runtime_options = _rootless_ollama_model_options(
        model_name=model_name, manifest_digest=manifest_digest,
        gpu_layers=gpu_layers)
    runtime_options.pop("seed", None)
    return {
        "schema_version": "sentientos.rootless_history_model_identity_recipe:v1",
        "engine": "ollama",
        "resolved_manifest_path": str(path),
        "manifest_sha256": manifest_digest,
        "model_name": model_name,
        "gpu_layers": gpu_layers,
        "max_context_tokens": 8192,
        "identity_implementation_sha256":
            _model_identity_implementation_hashes(),
        "generation_config": {
            "max_new_tokens": 512,
            "temperature": 0,
            "top_p": 1,
        },
        "runtime_options": runtime_options,
    }


def _plan_model_identity_digests(plan: Mapping[str, Any]) -> list[str]:
    if plan.get("schema_version") in {
            "sentientos.rootless_history_boundary_campaign_plan:v3",
            "sentientos.rootless_history_boundary_campaign_plan:v4",
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
        values = plan.get("ordered_model_identity_digests")
        return list(values) if isinstance(values, list) else []
    value = plan.get("model_identity_digest")
    cycle_ids = plan.get("ordered_cycle_ids")
    return ([value] * len(cycle_ids) if isinstance(value, str)
        and isinstance(cycle_ids, list) else [])


def create_plan(*, history_root: Path, campaign_id: str,
        task_family_id: str, model_identity_digests: list[str],
        ordered_cycle_ids: list[str],
        task_generation_seeds: list[int], backend_seeds: list[int],
        model_identity_recipe: Mapping[str, Any] | None = None,
        cross_range_history_enabled_competence: bool = False,
        acquisition_probe_count: int = 3,
        transfer_probe_count: int = 3
        ) -> dict[str, Any]:
    if _CAMPAIGN_ID.fullmatch(campaign_id) is None:
        raise ValueError("history_campaign_id_invalid")
    if task_family_id not in _SUPPORTED_TASK_FAMILIES:
        raise ValueError("history_campaign_task_family_unsupported")
    if (not isinstance(ordered_cycle_ids, list)
            or not 2 <= len(ordered_cycle_ids) <= 32
            or any(not isinstance(value, str)
                or _CYCLE_ID.fullmatch(value) is None for value in ordered_cycle_ids)
            or len(set(ordered_cycle_ids)) != len(ordered_cycle_ids)):
        raise ValueError("history_campaign_cycle_order_invalid")
    if (not isinstance(task_generation_seeds, list)
            or not isinstance(backend_seeds, list)
            or any(len(values) != len(ordered_cycle_ids)
                for values in (task_generation_seeds, backend_seeds))
            or any(type(seed) is not int or not 1 <= seed <= 2**32 - 1
                for seed in task_generation_seeds)
            or any(type(seed) is not int or not 0 <= seed <= 2**31 - 1
                for seed in backend_seeds)
            or len(set(task_generation_seeds)) != len(task_generation_seeds)
            or len(set(backend_seeds)) != len(backend_seeds)):
        raise ValueError("history_campaign_seed_order_invalid")
    if (not isinstance(model_identity_digests, list)
            or len(model_identity_digests) != len(ordered_cycle_ids)
            or any(not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in model_identity_digests)):
        raise ValueError("history_campaign_model_identity_digest_invalid")
    boundary = _history_boundary(history_root)
    admission_boundary = _runtime_admission_boundary(history_root, boundary)
    recovery_state_boundary = _cognition_recovery_state_boundary(
        history_root.parent / "state")
    if boundary["file_count"] and recovery_state_boundary is None:
        raise ValueError("history_campaign_recovery_state_missing")
    if (model_identity_recipe is not None
            and task_family_id not in {_TASK_FAMILY, *_RANGE_TASK_FAMILIES}):
        raise ValueError("history_campaign_model_identity_recipe_family_invalid")
    if task_family_id == _NOVEL_TASK_FAMILY and model_identity_recipe is None:
        raise ValueError("history_campaign_novel_family_identity_recipe_required")
    if (type(cross_range_history_enabled_competence) is not bool
            or cross_range_history_enabled_competence
                and (task_family_id != _WIDE_TASK_FAMILY
                    or model_identity_recipe is None)):
        raise ValueError("history_campaign_cross_range_protocol_configuration_invalid")
    if (type(acquisition_probe_count) is not int
            or not 3 <= acquisition_probe_count <= 16
            or acquisition_probe_count > 3
                and task_family_id != _NOVEL_TASK_FAMILY):
        raise ValueError("history_campaign_acquisition_probe_count_invalid")
    if (type(transfer_probe_count) is not int
            or not 3 <= transfer_probe_count <= 16
            or transfer_probe_count != 3 and not (
                cross_range_history_enabled_competence
                or task_family_id == _NOVEL_TASK_FAMILY)):
        raise ValueError("history_campaign_transfer_probe_count_invalid")
    plan_schema = (
        "sentientos.rootless_history_boundary_campaign_plan:v15"
        if task_family_id == _TASK_FAMILY and model_identity_recipe is not None else
        "sentientos.rootless_history_boundary_campaign_plan:v14"
        if acquisition_probe_count > 3 else
        "sentientos.rootless_history_boundary_campaign_plan:v13"
        if task_family_id == _WIDE_TASK_FAMILY
            and cross_range_history_enabled_competence
            and transfer_probe_count > 3 else
        "sentientos.rootless_history_boundary_campaign_plan:v12"
        if task_family_id == _NOVEL_TASK_FAMILY and transfer_probe_count > 3 else
        "sentientos.rootless_history_boundary_campaign_plan:v10"
        if cross_range_history_enabled_competence and transfer_probe_count > 3 else
        "sentientos.rootless_history_boundary_campaign_plan:v9"
        if cross_range_history_enabled_competence else
        "sentientos.rootless_history_boundary_campaign_plan:v11"
        if task_family_id == _NOVEL_TASK_FAMILY else
        "sentientos.rootless_history_boundary_campaign_plan:v8"
        if task_family_id == _WIDE_TASK_FAMILY
            and model_identity_recipe is not None else
        "sentientos.rootless_history_boundary_campaign_plan:v6"
        if task_family_id == _WIDE_TASK_FAMILY else
        "sentientos.rootless_history_boundary_campaign_plan:v5")
    if task_family_id == _NOVEL_TASK_FAMILY:
        planned_probe_sets: list[set[int]] = []
        for seed in task_generation_seeds:
            acquisition_task, transfer_task = (
                rootless_integer_affine_transfer_task_pair(seed,
                    task_family_id=_NOVEL_TASK_FAMILY,
                    acquisition_probe_count=acquisition_probe_count,
                    transfer_probe_count=transfer_probe_count))
            acquisition_inputs = {acquisition_task.probe_input,
                *acquisition_task.additional_probe_inputs}
            transfer_inputs = {transfer_task.probe_input,
                *transfer_task.additional_probe_inputs}
            if acquisition_inputs & transfer_inputs:
                raise ValueError("history_campaign_novel_task_probe_sets_overlap")
            planned_probe_sets.append(acquisition_inputs | transfer_inputs)
        for index, probe_set in enumerate(planned_probe_sets):
            if any(probe_set & prior for prior in planned_probe_sets[:index]):
                raise ValueError("history_campaign_novel_cycle_probe_reuse")
    elif task_family_id in {_TASK_FAMILY, _WIDE_TASK_FAMILY}:
        planned_probe_sets = []
        for seed in task_generation_seeds:
            acquisition_task, transfer_task = (
                rootless_integer_affine_transfer_task_pair(seed,
                    task_family_id=task_family_id,
                    acquisition_probe_count=acquisition_probe_count,
                    transfer_probe_count=transfer_probe_count))
            acquisition_inputs = set(
                acquisition_task.specification()["probe_inputs"])
            transfer_inputs = set(transfer_task.specification()["probe_inputs"])
            if acquisition_inputs & transfer_inputs:
                raise ValueError("history_campaign_source_task_probe_overlap")
            probe_set = acquisition_inputs | transfer_inputs
            planned_probe_sets.append(probe_set)
        # Cross-cycle reuse is allowed for low-range acquisition sources;
        # exact inputs are deduplicated by the source-evidence eligibility gate.
    semantic = {
        "schema_version": plan_schema,
        "campaign_id": campaign_id,
        "task_family_id": task_family_id,
        "ordered_model_identity_digests": model_identity_digests,
        "ordered_cycle_ids": ordered_cycle_ids,
        "ordered_task_generation_seeds": task_generation_seeds,
        "ordered_backend_seeds": backend_seeds,
        "initial_history_boundary": boundary,
        "initial_runtime_admission_ledger": admission_boundary,
        "initial_cognition_recovery_state": recovery_state_boundary,
        "preregistration_timing_independently_attested": False,
        "authority": False,
    }
    if model_identity_recipe is not None:
        semantic["model_identity_recipe"] = dict(model_identity_recipe)
        semantic["experiment_implementation_sha256"] = (
            _experiment_implementation_hashes())
    if cross_range_history_enabled_competence:
        semantic["cross_range_history_enabled_competence"] = dict(
            _CROSS_RANGE_HISTORY_ENABLED_COMPETENCE_PROTOCOL)
    if plan_schema == "sentientos.rootless_history_boundary_campaign_plan:v15":
        semantic["low_range_source_acquisition_protocol"] = dict(
            _LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL)
    if (plan_schema in {
            "sentientos.rootless_history_boundary_campaign_plan:v13",
            "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}
            and task_family_id == _WIDE_TASK_FAMILY
            and cross_range_history_enabled_competence):
        semantic["initial_history_bootstrap"] = dict(
            _EMPTY_HISTORY_BOOTSTRAP_PROTOCOL)
    if acquisition_probe_count > 3:
        semantic["acquisition_probe_count"] = acquisition_probe_count
    if transfer_probe_count > 3:
        semantic["transfer_probe_count"] = transfer_probe_count
    return {**semantic, "plan_digest": digest_payload(semantic)}


def _load_plan(plan_path: Path) -> dict[str, Any]:
    if plan_path.is_symlink() or not plan_path.is_file():
        raise ValueError("history_campaign_plan_invalid")
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("history_campaign_plan_invalid") from exc
    if not isinstance(plan, dict):
        raise ValueError("history_campaign_plan_invalid")
    semantic = {key: value for key, value in plan.items()
        if key != "plan_digest"}
    schema_version = plan.get("schema_version")
    if (schema_version not in {
                "sentientos.rootless_history_boundary_campaign_plan:v2",
                "sentientos.rootless_history_boundary_campaign_plan:v3",
                "sentientos.rootless_history_boundary_campaign_plan:v4",
                "sentientos.rootless_history_boundary_campaign_plan:v5",
                "sentientos.rootless_history_boundary_campaign_plan:v6",
                "sentientos.rootless_history_boundary_campaign_plan:v7",
                "sentientos.rootless_history_boundary_campaign_plan:v8",
                "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13",
                "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}
            or plan.get("plan_digest") != digest_payload(semantic)
            or plan.get("authority") is not False
            or plan.get("preregistration_timing_independently_attested") is not False):
        raise ValueError("history_campaign_plan_binding_invalid")
    cycle_ids = plan.get("ordered_cycle_ids")
    task_seeds = plan.get("ordered_task_generation_seeds")
    backend_seeds = plan.get("ordered_backend_seeds")
    model_identity_digests = _plan_model_identity_digests(plan)
    if (not isinstance(plan.get("campaign_id"), str)
            or _CAMPAIGN_ID.fullmatch(plan["campaign_id"]) is None
            or plan.get("task_family_id") not in _SUPPORTED_TASK_FAMILIES
            or not isinstance(cycle_ids, list) or not 2 <= len(cycle_ids) <= 32
            or len(model_identity_digests) != len(cycle_ids)
            or any(not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
                for value in model_identity_digests)
            or any(not isinstance(value, str)
                or _CYCLE_ID.fullmatch(value) is None for value in cycle_ids)
            or len(set(cycle_ids)) != len(cycle_ids)
            or not isinstance(task_seeds, list)
            or not isinstance(backend_seeds, list)
            or any(len(values) != len(cycle_ids)
                for values in (task_seeds, backend_seeds))
            or any(type(seed) is not int or not 1 <= seed <= 2**32 - 1
                for seed in task_seeds)
            or any(type(seed) is not int or not 0 <= seed <= 2**31 - 1
                for seed in backend_seeds)
            or len(set(task_seeds)) != len(task_seeds)
            or len(set(backend_seeds)) != len(backend_seeds)):
        raise ValueError("history_campaign_plan_fields_invalid")
    if ((schema_version == "sentientos.rootless_history_boundary_campaign_plan:v5"
                and plan.get("task_family_id") != _TASK_FAMILY)
            or (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v6"
                and plan.get("task_family_id") != _WIDE_TASK_FAMILY)
            or (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v7"
                and plan.get("task_family_id") != _WIDE_TASK_FAMILY)
            or (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v8"
                and plan.get("task_family_id") != _WIDE_TASK_FAMILY)
            or (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v9"
                and plan.get("task_family_id") != _WIDE_TASK_FAMILY)
            or (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v10"
                and plan.get("task_family_id") != _WIDE_TASK_FAMILY)
            or (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v13"
                and plan.get("task_family_id") != _WIDE_TASK_FAMILY)
            or (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v14"
                and plan.get("task_family_id") != _NOVEL_TASK_FAMILY)
            or (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v15"
                and plan.get("task_family_id") != _TASK_FAMILY)
            or (schema_version in {
                    "sentientos.rootless_history_boundary_campaign_plan:v11",
                    "sentientos.rootless_history_boundary_campaign_plan:v12"}
                and plan.get("task_family_id") != _NOVEL_TASK_FAMILY)):
        raise ValueError("history_campaign_plan_family_version_mismatch")
    if (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v15"
            and plan.get("low_range_source_acquisition_protocol")
                != _LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL
            or schema_version != "sentientos.rootless_history_boundary_campaign_plan:v15"
                and "low_range_source_acquisition_protocol" in plan):
        raise ValueError("history_campaign_low_range_source_protocol_invalid")
    if (schema_version == "sentientos.rootless_history_boundary_campaign_plan:v13"
            and plan.get("initial_history_bootstrap")
                != _EMPTY_HISTORY_BOOTSTRAP_PROTOCOL
            or schema_version != "sentientos.rootless_history_boundary_campaign_plan:v13"
                and "initial_history_bootstrap" in plan):
        raise ValueError("history_campaign_initial_bootstrap_protocol_invalid")
    if schema_version in {"sentientos.rootless_history_boundary_campaign_plan:v10",
            "sentientos.rootless_history_boundary_campaign_plan:v12",
            "sentientos.rootless_history_boundary_campaign_plan:v13"}:
        if type(plan.get("transfer_probe_count")) is not int or not 4 <= plan["transfer_probe_count"] <= 16:
            raise ValueError("history_campaign_transfer_probe_count_invalid")
    elif schema_version == "sentientos.rootless_history_boundary_campaign_plan:v14":
        if "transfer_probe_count" in plan and (
                type(plan["transfer_probe_count"]) is not int
                or not 4 <= plan["transfer_probe_count"] <= 16):
            raise ValueError("history_campaign_transfer_probe_count_invalid")
    elif "transfer_probe_count" in plan:
        raise ValueError("history_campaign_transfer_probe_count_version_invalid")
    if schema_version == "sentientos.rootless_history_boundary_campaign_plan:v14":
        if type(plan.get("acquisition_probe_count")) is not int or not 4 <= plan["acquisition_probe_count"] <= 16:
            raise ValueError("history_campaign_acquisition_probe_count_invalid")
    elif "acquisition_probe_count" in plan:
        raise ValueError("history_campaign_acquisition_probe_count_version_invalid")
    if schema_version in {
            "sentientos.rootless_history_boundary_campaign_plan:v7",
            "sentientos.rootless_history_boundary_campaign_plan:v8",
            "sentientos.rootless_history_boundary_campaign_plan:v9",
            "sentientos.rootless_history_boundary_campaign_plan:v10",
            "sentientos.rootless_history_boundary_campaign_plan:v11",
            "sentientos.rootless_history_boundary_campaign_plan:v12",
            "sentientos.rootless_history_boundary_campaign_plan:v13",
            "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}:
        recipe = plan.get("model_identity_recipe")
        expected_recipe_keys = {
            "schema_version", "engine", "resolved_manifest_path",
            "manifest_sha256", "model_name", "gpu_layers",
            "max_context_tokens", "generation_config", "runtime_options",
            "identity_implementation_sha256"}
        generation = (recipe.get("generation_config")
            if isinstance(recipe, Mapping) else None)
        if (not isinstance(recipe, Mapping)
                or set(recipe) != expected_recipe_keys
                or recipe.get("schema_version") !=
                    "sentientos.rootless_history_model_identity_recipe:v1"
                or recipe.get("engine") != "ollama"
                or not isinstance(recipe.get("resolved_manifest_path"), str)
                or not (PurePosixPath(recipe["resolved_manifest_path"]).is_absolute()
                    or PureWindowsPath(recipe["resolved_manifest_path"]).is_absolute())
                or not isinstance(recipe.get("manifest_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}",
                    recipe["manifest_sha256"]) is None
                or not isinstance(recipe.get("model_name"), str)
                or not recipe["model_name"].strip()
                or type(recipe.get("gpu_layers")) is not int
                or not 0 <= recipe["gpu_layers"] <= 128
                or recipe.get("max_context_tokens") != 8192
                or not isinstance(recipe.get("identity_implementation_sha256"), Mapping)
                or not isinstance(generation, Mapping)
                or set(generation) != {"max_new_tokens", "temperature", "top_p"}
                or any(type(generation.get(key)) is not int
                    for key in ("max_new_tokens", "temperature", "top_p"))
                or dict(generation) != {"max_new_tokens": 512,
                    "temperature": 0, "top_p": 1}
                or not isinstance(recipe.get("runtime_options"), Mapping)
                or set(recipe["runtime_options"]) != {
                    "api_base", "model", "manifest_sha256", "num_gpu",
                    "num_thread", "keep_alive", "think", "timeout_seconds"}
                or recipe["runtime_options"].get("model") != recipe.get("model_name")
                or recipe["runtime_options"].get("manifest_sha256") !=
                    recipe.get("manifest_sha256")
                or not isinstance(recipe["runtime_options"].get("api_base"), str)
                or not isinstance(recipe["runtime_options"].get("keep_alive"), str)
                or recipe["runtime_options"].get("num_gpu") !=
                    recipe.get("gpu_layers")
                or type(recipe["runtime_options"].get("num_gpu")) is not int
                or type(recipe["runtime_options"].get("num_thread")) is not int
                or type(recipe["runtime_options"].get("timeout_seconds")) is not int
                or recipe["runtime_options"].get("think") is not False):
            raise ValueError("history_campaign_model_identity_recipe_invalid")
        if schema_version in {
                "sentientos.rootless_history_boundary_campaign_plan:v8",
                "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13",
                "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}:
            implementation = plan.get("experiment_implementation_sha256")
            if (not isinstance(implementation, Mapping)
                    or len(implementation) < 3
                    or any(not isinstance(path, str)
                        or _EXPERIMENT_IMPLEMENTATION_PATH.fullmatch(path) is None
                        or not isinstance(digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                        for path, digest in implementation.items())):
                raise ValueError(
                    "history_campaign_experiment_implementation_invalid")
            if schema_version in {"sentientos.rootless_history_boundary_campaign_plan:v9",
                    "sentientos.rootless_history_boundary_campaign_plan:v10",
                    "sentientos.rootless_history_boundary_campaign_plan:v13"}:
                if plan.get("cross_range_history_enabled_competence") not in (
                        _CROSS_RANGE_HISTORY_ENABLED_COMPETENCE_PROTOCOL_V1,
                        _CROSS_RANGE_HISTORY_ENABLED_COMPETENCE_PROTOCOL):
                    raise ValueError(
                        "history_campaign_cross_range_protocol_invalid")
            elif "cross_range_history_enabled_competence" in plan:
                raise ValueError(
                    "history_campaign_cross_range_protocol_version_invalid")
        elif "experiment_implementation_sha256" in plan:
            raise ValueError(
                "history_campaign_experiment_implementation_version_invalid")
    elif "experiment_implementation_sha256" in plan:
        raise ValueError("history_campaign_experiment_implementation_version_invalid")
    elif "model_identity_recipe" in plan:
        raise ValueError("history_campaign_model_identity_recipe_version_invalid")
    initial = plan.get("initial_history_boundary")
    if not isinstance(initial, Mapping):
        raise ValueError("history_campaign_initial_boundary_invalid")
    boundary_semantic = {key: value for key, value in initial.items()
        if key != "boundary_digest"}
    boundary_files = initial.get("files")
    if (not isinstance(boundary_files, list)
            or len(boundary_files) > _MAX_BOUNDARY_FILES
            or initial.get("file_count") != len(boundary_files)
            or type(initial.get("total_size_bytes")) is not int):
        raise ValueError("history_campaign_initial_boundary_inventory_invalid")
    expected_names: list[str] = []
    computed_total_size = 0
    for row in boundary_files:
        if not isinstance(row, Mapping):
            raise ValueError("history_campaign_initial_boundary_inventory_invalid")
        name = row.get("path")
        valid_name = (isinstance(name, str) and (
            re.fullmatch(r"records/devrec-[0-9a-f]{24}\.json", name)
            or re.fullmatch(r"receipts/devreceipt-[0-9a-f]{24}\.json", name)))
        if (not valid_name or type(row.get("size_bytes")) is not int
                or not 0 <= row["size_bytes"] <= 128 * 1024 * 1024
                or not isinstance(row.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None):
            raise ValueError("history_campaign_initial_boundary_inventory_invalid")
        expected_names.append(name)
        computed_total_size += row["size_bytes"]
    if (expected_names != sorted(expected_names)
            or len(set(expected_names)) != len(expected_names)
            or initial["total_size_bytes"] != computed_total_size
            or initial["total_size_bytes"] > _MAX_BOUNDARY_BYTES):
        raise ValueError("history_campaign_initial_boundary_inventory_invalid")
    if (initial.get("schema_version") != "sentientos.rootless_history_boundary:v1"
            or initial.get("boundary_digest") != digest_payload(boundary_semantic)
            or initial.get("atomic_snapshot") is not False
            or not isinstance(initial.get("files"), list)):
        raise ValueError("history_campaign_initial_boundary_binding_invalid")
    if schema_version in {
            "sentientos.rootless_history_boundary_campaign_plan:v4",
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
        admission = plan.get("initial_runtime_admission_ledger")
        if admission is not None and (
                not isinstance(admission, Mapping)
                or set(admission) != {"schema_version", "sha256", "size_bytes",
                    "admission_count", "revocation_count", "admission_bindings",
                    "revocation_bindings", "atomic_snapshot"}
                or admission.get("schema_version") !=
                    "sentientos.rootless_history_campaign_admission_boundary:v1"
                or not isinstance(admission.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", admission["sha256"]) is None
                or type(admission.get("size_bytes")) is not int
                or not 0 <= admission["size_bytes"] <= 4_194_304
                or type(admission.get("admission_count")) is not int
                or not 0 <= admission["admission_count"] <= 8192
                or type(admission.get("revocation_count")) is not int
                or not 0 <= admission["revocation_count"] <= 8192
                or not isinstance(admission.get("admission_bindings"), list)
                or len(admission["admission_bindings"])
                    != admission.get("admission_count")
                or not isinstance(admission.get("revocation_bindings"), list)
                or len(admission["revocation_bindings"])
                    != admission.get("revocation_count")
                or admission.get("atomic_snapshot") is not False):
            raise ValueError("history_campaign_initial_admission_boundary_invalid")
        if admission is not None:
            admission_rows = admission["admission_bindings"]
            revocation_rows = admission["revocation_bindings"]
            if (any(not isinstance(row, Mapping)
                    or set(row) != {"admission_id", "binding_digest", "issued_sequence"}
                    or not isinstance(row.get("admission_id"), str)
                    or not isinstance(row.get("binding_digest"), str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", row["binding_digest"]) is None
                    or type(row.get("issued_sequence")) is not int
                    or row["issued_sequence"] < 1 for row in admission_rows)
                    or any(not isinstance(row, Mapping)
                    or set(row) != {"revocation_id", "binding_digest", "sequence"}
                    or not isinstance(row.get("revocation_id"), str)
                    or not isinstance(row.get("binding_digest"), str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", row["binding_digest"]) is None
                    or type(row.get("sequence")) is not int
                    or row["sequence"] < 1 for row in revocation_rows)
                    or [row["admission_id"] for row in admission_rows]
                        != sorted({row["admission_id"] for row in admission_rows})
                    or [row["revocation_id"] for row in revocation_rows]
                        != sorted({row["revocation_id"] for row in revocation_rows})):
                raise ValueError("history_campaign_initial_admission_boundary_invalid")
        if initial.get("file_count", 0) and admission is None:
            raise ValueError("history_campaign_initial_admission_boundary_missing")
    if schema_version in {
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
        recovery_state = plan.get("initial_cognition_recovery_state")
        if (not _valid_cognition_recovery_state_boundary(recovery_state)
                or (initial.get("file_count", 0) and recovery_state is None)):
            raise ValueError("history_campaign_initial_recovery_state_invalid")
    return plan


def _cycle_history_files(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("history_campaign_cycle_manifest_invalid")
    result = {}
    for row in files:
        if not isinstance(row, Mapping):
            raise ValueError("history_campaign_cycle_manifest_invalid")
        path = row.get("path")
        if (isinstance(path, str)
                and (path.startswith("resident-cognition/history/records/")
                    or path.startswith("resident-cognition/history/receipts/"))):
            if path in result:
                raise ValueError("history_campaign_cycle_history_path_duplicate")
            basename = path.rsplit("/", 1)[-1]
            record_prefix = "resident-cognition/history/records/"
            receipt_prefix = "resident-cognition/history/receipts/"
            valid_path = (
                path == record_prefix + basename
                and re.fullmatch(r"devrec-[0-9a-f]{24}\.json", basename) is not None
                or path == receipt_prefix + basename
                and re.fullmatch(r"devreceipt-[0-9a-f]{24}\.json", basename) is not None)
            if (not valid_path or type(row.get("size_bytes")) is not int
                    or not isinstance(row.get("sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None):
                raise ValueError("history_campaign_cycle_history_entry_invalid")
            result[path] = {"path": path, "size_bytes": row.get("size_bytes"),
                "sha256": row.get("sha256")}
    return result


def verify_model_identity_recipe(plan: Mapping[str, Any], *,
        allow_recomputed_campaign_source_pin_mismatch: bool = False
        ) -> dict[str, Any]:
    """Recompute model pins from the plan-bound manifest and config recipe."""
    recipe = plan.get("model_identity_recipe")
    if (plan.get("schema_version") not in {
                "sentientos.rootless_history_boundary_campaign_plan:v7",
                "sentientos.rootless_history_boundary_campaign_plan:v8",
                "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13",
                "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}
            or not isinstance(recipe, Mapping)):
        raise ValueError("history_campaign_model_identity_recipe_missing")
    manifest_path = Path(recipe["resolved_manifest_path"])
    manifest_digest, _ = _hash_regular_file(manifest_path)
    if (manifest_digest != recipe["manifest_sha256"]
            or manifest_path.stem != manifest_digest):
        raise ValueError("history_campaign_model_identity_manifest_mismatch")
    from sentientos.rootless_experimental_ollama_epistemic_session import (
        _rootless_ollama_model_options)
    runtime_options = _rootless_ollama_model_options(
        model_name=recipe["model_name"], manifest_digest=manifest_digest,
        gpu_layers=recipe["gpu_layers"])
    runtime_options.pop("seed", None)
    if runtime_options != dict(recipe["runtime_options"]):
        raise ValueError("history_campaign_model_identity_runtime_options_mismatch")
    pinned_implementation = dict(recipe["identity_implementation_sha256"])
    current_implementation = _model_identity_implementation_hashes()
    implementation_pin_mismatch = pinned_implementation != current_implementation
    differing_paths = {path for path in set(pinned_implementation)
        | set(current_implementation)
        if pinned_implementation.get(path) != current_implementation.get(path)}
    if implementation_pin_mismatch and (
            not allow_recomputed_campaign_source_pin_mismatch
            or differing_paths not in {
                frozenset({"work/rootless_history_boundary_campaign.py"}),
                frozenset({
                    "work/rootless_history_boundary_campaign.py",
                    "sentientos/rootless_experimental_ollama_epistemic_session.py"})}):
        raise ValueError("history_campaign_model_identity_implementation_mismatch")
    recomputed = derive_model_identity_digests(
        manifest_path=manifest_path,
        model_name=recipe["model_name"],
        gpu_layers=recipe["gpu_layers"],
        backend_seeds=plan["ordered_backend_seeds"])
    expected = _plan_model_identity_digests(plan)
    if recomputed != expected:
        raise ValueError("history_campaign_model_identity_recipe_digest_mismatch")
    evidence = {
        "model_identity_recipe_digest": digest_payload(dict(recipe)),
        "manifest_sha256": manifest_digest,
        "identity_count": len(recomputed),
        "identity_digests_verified": True,
        "inference_performed": False,
    }
    evidence["implementation_pin_posture"] = (
        "campaign_source_pin_mismatch_replayed_against_current_identity_outputs"
        if implementation_pin_mismatch else "all_identity_source_pins_match")
    evidence["pinned_identity_implementation_sha256"] = pinned_implementation
    evidence["replay_identity_implementation_sha256"] = current_implementation
    return evidence


def _seed_source_boundary_digest(*, root: Path, manifest: Mapping[str, Any],
        previous: Mapping[str, Mapping[str, Any]]) -> tuple[str, int, int]:
    records = []
    receipts = []
    for path in sorted(previous):
        if not (path.startswith("resident-cognition/history/records/")
                or path.startswith("resident-cognition/history/receipts/")):
            raise ValueError("history_campaign_prior_boundary_path_invalid")
        raw = _read_manifest_bound_file(root=root, manifest=manifest,
            relative_path=path)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("history_campaign_prior_boundary_payload_invalid") from exc
        if (not isinstance(payload, Mapping)
                or json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
                    + b"\n" != raw):
            raise ValueError("history_campaign_prior_boundary_payload_noncanonical")
        name = path.rsplit("/", 1)[-1]
        if path.startswith("resident-cognition/history/records/"):
            record_id = payload.get("record_id")
            if (not isinstance(record_id, str) or record_id + ".json" != name
                    or not isinstance(payload.get("record_digest"), str)):
                raise ValueError("history_campaign_prior_record_identity_invalid")
            records.append({"record_id": record_id,
                "record_digest": payload["record_digest"]})
        else:
            receipt_id = payload.get("receipt_id")
            if (not isinstance(receipt_id, str) or receipt_id + ".json" != name
                    or not isinstance(payload.get("receipt_digest"), str)
                    or not isinstance(payload.get("record_id"), str)
                    or not isinstance(payload.get("record_digest"), str)):
                raise ValueError("history_campaign_prior_receipt_identity_invalid")
            receipts.append({"receipt_id": receipt_id,
                "receipt_digest": payload["receipt_digest"],
                "record_id": payload["record_id"],
                "record_digest": payload["record_digest"]})
    records.sort(key=lambda row: row["record_id"])
    receipts.sort(key=lambda row: row["receipt_id"])
    record_digests = {row["record_id"]: row["record_digest"] for row in records}
    if (len(record_digests) != len(records)
            or any(record_digests.get(row["record_id"]) != row["record_digest"]
                for row in receipts)
            or set(record_digests) - {row["record_id"] for row in receipts}):
        raise ValueError("history_campaign_prior_receipts_not_bound")
    boundary = {"records": records, "receipts": receipts}
    return digest_payload(boundary), len(records), len(receipts)


def _verify_seed_preregistration(*, root: Path, manifest: Mapping[str, Any],
        terminal: Mapping[str, Any], seed_evidence: Mapping[str, Any],
        cycle_id: str) -> bool:
    try:
        raw = _read_manifest_bound_file(root=root, manifest=manifest,
            relative_path="preregistration.json")
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return False
    if (not isinstance(payload, Mapping)
            or json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
                + b"\n" != raw):
        return False
    preregistration_digest = payload.get("preregistration_digest")
    semantic = {key: value for key, value in payload.items()
        if key != "preregistration_digest"}
    return (
        isinstance(preregistration_digest, str)
        and _runtime_digest(semantic) == preregistration_digest
        and terminal.get("run_preregistration_digest") == preregistration_digest
        and payload.get("run_id") == cycle_id
        and payload.get("external_protocol_digest")
            == terminal.get("external_preregistration_digest")
        and payload.get("owner_feedback_recall_protocol_digest")
            == terminal.get("owner_feedback_recall_protocol_digest")
        and isinstance(payload.get("external_protocol_digest"), str)
        and re.fullmatch(r"[0-9a-f]{64}", payload["external_protocol_digest"]) is not None
        and payload.get("model_manifest_digest") == terminal.get("model_manifest_digest")
        and payload.get("prior_developmental_history_seed") == dict(seed_evidence)
    )


def _load_initial_history_bundle(path: Path, *,
        plan: Mapping[str, Any]) -> tuple[dict[str, bytes], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("history_campaign_seed_bundle_invalid")
    try:
        raw = path.read_bytes()
        bundle = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("history_campaign_seed_bundle_invalid") from exc
    if (not isinstance(bundle, Mapping)
            or json.dumps(bundle, sort_keys=True, indent=2).encode("utf-8")
                + b"\n" != raw):
        raise ValueError("history_campaign_seed_bundle_noncanonical")
    semantic = {key: value for key, value in bundle.items()
        if key != "bundle_digest"}
    boundary = plan.get("initial_history_boundary")
    if (bundle.get("schema_version") !=
            "sentientos.rootless_history_campaign_seed_bundle:v1"
            or bundle.get("campaign_id") != plan.get("campaign_id")
            or bundle.get("plan_digest") != plan.get("plan_digest")
            or bundle.get("task_family_id") != plan.get("task_family_id")
            or bundle.get("source_snapshot_atomic") is not False
            or not isinstance(boundary, Mapping)
            or bundle.get("source_history_boundary_digest") !=
                boundary.get("boundary_digest")
            or bundle.get("bundle_digest") != digest_payload(semantic)):
        raise ValueError("history_campaign_seed_bundle_plan_binding_invalid")
    rows = bundle.get("files")
    if (not isinstance(rows, list)
            or type(bundle.get("source_history_file_count")) is not int
            or bundle.get("source_history_file_count") != len(rows)
            or type(bundle.get("source_history_total_size_bytes")) is not int):
        raise ValueError("history_campaign_seed_bundle_inventory_invalid")
    files: dict[str, bytes] = {}
    boundary_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("history_campaign_seed_bundle_file_invalid")
        relative_path = row.get("path")
        encoded = row.get("content_base64")
        size = row.get("size_bytes")
        expected_sha256 = row.get("sha256")
        if (not isinstance(relative_path, str)
                or re.fullmatch(r"(?:records/devrec-[0-9a-f]{24}|"
                    r"receipts/devreceipt-[0-9a-f]{24})\.json", relative_path,
                    flags=re.ASCII) is None
                or relative_path in files
                or not isinstance(encoded, str)
                or type(size) is not int or not 0 <= size <= 1_048_576
                or not isinstance(expected_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_sha256,
                    flags=re.ASCII) is None):
            raise ValueError("history_campaign_seed_bundle_file_invalid")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("history_campaign_seed_bundle_file_encoding_invalid") from exc
        if (len(content) != size
                or hashlib.sha256(content).hexdigest() != expected_sha256):
            raise ValueError("history_campaign_seed_bundle_file_digest_invalid")
        files[relative_path] = content
        boundary_rows.append({"path": relative_path,
            "size_bytes": size, "sha256": expected_sha256})
    boundary_rows.sort(key=lambda item: item["path"])
    boundary_semantic = {
        "schema_version": "sentientos.rootless_history_boundary:v1",
        "file_count": len(boundary_rows),
        "total_size_bytes": sum(row["size_bytes"] for row in boundary_rows),
        "files": boundary_rows,
        "atomic_snapshot": False,
    }
    if (list(files) != sorted(files)
            or boundary_semantic["total_size_bytes"] !=
                bundle.get("source_history_total_size_bytes")
            or len(boundary_rows) != boundary.get("file_count")
            or boundary_semantic["total_size_bytes"] !=
                boundary.get("total_size_bytes")):
        raise ValueError("history_campaign_seed_bundle_inventory_invalid")
    boundary_digest = digest_payload(boundary_semantic)
    if boundary_digest != boundary.get("boundary_digest"):
        raise ValueError("history_campaign_seed_bundle_boundary_mismatch")
    return files, str(bundle["bundle_digest"])


def _verify_transfer_probe_preflight(*, root: Path,
        manifest: Mapping[str, Any], terminal: Mapping[str, Any],
        plan: Mapping[str, Any], cycle_index: int,
        previous: Mapping[str, Mapping[str, Any]],
        initial_bundle_files: Mapping[str, bytes] | None = None
        ) -> tuple[dict[str, Any], bool] | None:
    """Independently recompute v7 probe overlap from the seeded file boundary."""
    if plan.get("task_family_id") not in _RANGE_TASK_FAMILIES:
        return None
    campaign_binding = terminal.get("history_campaign_binding")
    terminal_preflight = (campaign_binding.get("transfer_probe_preflight")
        if isinstance(campaign_binding, Mapping) else None)
    if terminal.get("status") == "incomplete":
        terminal_preflight = (terminal.get("wide_transfer_probe_preflight")
            or terminal_preflight)
    if not isinstance(terminal_preflight, Mapping):
        if terminal.get("status") == "incomplete":
            return None
        raise ValueError("history_campaign_transfer_probe_preflight_missing")
    cycle_id = plan["ordered_cycle_ids"][cycle_index]
    expected_boundary_files = [{**previous[path],
        "path": path.removeprefix("resident-cognition/history/")}
        for path in sorted(previous)]
    boundary_semantic = {
        "schema_version": "sentientos.rootless_history_boundary:v1",
        "file_count": len(previous),
        "total_size_bytes": sum(row["size_bytes"] for row in previous.values()),
        "files": expected_boundary_files,
        "atomic_snapshot": False,
    }
    expected_boundary_digest = digest_payload(boundary_semantic)
    task_family_id = str(plan["task_family_id"])
    acquisition, transfer = rootless_integer_affine_transfer_task_pair(
        plan["ordered_task_generation_seeds"][cycle_index],
        task_family_id=task_family_id,
        acquisition_probe_count=plan.get("acquisition_probe_count", 3),
        transfer_probe_count=plan.get("transfer_probe_count", 3))
    history_task_family_ids = (transfer.history_task_family_ids
        or (task_family_id,))
    if (task_family_id not in history_task_family_ids
            or len(set(history_task_family_ids)) !=
                len(history_task_family_ids)):
        raise ValueError("history_campaign_transfer_history_families_invalid")
    acquisition_inputs = [acquisition.probe_input,
        *acquisition.additional_probe_inputs]
    transfer_inputs = [transfer.probe_input, *transfer.additional_probe_inputs]
    overlap_recomputed = (terminal.get("status") == "completed"
        or cycle_index == 0 and initial_bundle_files is not None)
    packets: list[dict[str, Any]] = []
    projected_record_ids: list[str] = []
    acquisition_overlap: Mapping[str, Any] | None = None
    if overlap_recomputed:
        for path, row in sorted(previous.items()):
            if not path.startswith("resident-cognition/history/records/"):
                continue
            if (re.fullmatch(r"resident-cognition/history/records/"
                    r"devrec-[0-9a-f]{24}\.json", path, flags=re.ASCII) is None):
                raise ValueError("history_campaign_transfer_probe_record_path_invalid")
            try:
                bundle_path = path.removeprefix("resident-cognition/history/")
                raw = (_read_manifest_bound_file(root=root, manifest=manifest,
                    relative_path=path) if terminal.get("status") == "completed"
                    else initial_bundle_files[bundle_path])
                record_envelope = json.loads(raw.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError("history_campaign_transfer_probe_record_invalid") from exc
            if (not isinstance(record_envelope, Mapping)
                    or hashlib.sha256(raw).hexdigest() != row.get("sha256")
                    or len(raw) != row.get("size_bytes")
                    or json.dumps(record_envelope, sort_keys=True, indent=2).encode("utf-8")
                        + b"\n" != raw
                    or record_envelope.get("record_id") != Path(path).stem):
                raise ValueError("history_campaign_transfer_probe_record_invalid")
            candidate = record_envelope.get("candidate")
            if not isinstance(candidate, Mapping):
                continue
            projected: list[dict[str, Any]] = []
            for source_family_id in history_task_family_ids:
                projected.extend(_task_family_history_examples(candidate,
                    task_family_id=source_family_id))
            if projected:
                packets.append({"task_relevant_experience": projected})
                projected_record_ids.append(record_envelope["record_id"])
        overlap = _task_family_history_probe_overlap(packets,
            task_probe_inputs=transfer_inputs)
        acquisition_overlap = _task_family_history_probe_overlap(packets,
            task_probe_inputs=acquisition_inputs)
    else:
        semantic_claim = {key: value for key, value in terminal_preflight.items()
            if key != "preflight_digest"}
        overlap = terminal_preflight.get("historical_probe_overlap")
        acquisition_overlap = terminal_preflight.get(
            "acquisition_historical_probe_overlap")
        empty_overlap = _task_family_history_probe_overlap([],
            task_probe_inputs=transfer_inputs)
        projected_record_ids = terminal_preflight.get("projected_record_ids")
        overlap_count = (overlap.get("historical_probe_overlap_input_count")
            if isinstance(overlap, Mapping) else None)
        example_count = (overlap.get("historical_probe_overlap_example_count")
            if isinstance(overlap, Mapping) else None)
        measurement_complete = (overlap.get(
            "historical_probe_overlap_measurement_complete")
            if isinstance(overlap, Mapping) else None)
        overlap_posture = (overlap.get("historical_probe_overlap_posture")
            if isinstance(overlap, Mapping) else None)
        expected_overlap_posture = (
            "historical_probe_inputs_incomplete" if measurement_complete is False else
            "exact_historical_probe_overlap_present" if overlap_count else
            "no_exact_historical_probe_overlap")
        overlap_inputs_valid = (
            isinstance(overlap, Mapping)
            and overlap.get("task_probe_input_count") == len(transfer_inputs)
            and overlap.get("task_probe_input_digest")
                == empty_overlap["task_probe_input_digest"]
            and type(overlap_count) is int
            and 0 <= overlap_count <= len(transfer_inputs)
            and type(example_count) is int
            and overlap_count <= example_count
            and (overlap_count != 0 or example_count == 0)
            and type(measurement_complete) is bool
            and overlap_posture == expected_overlap_posture
            and overlap.get("historical_probe_overlap_scope") ==
                "selected_score_bound_correct_incorrect_and_abstained_examples"
            and isinstance(overlap.get(
                "historical_probe_overlap_input_digest"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", overlap[
                "historical_probe_overlap_input_digest"], flags=re.ASCII) is not None
            and (overlap_count != 0
                or overlap["historical_probe_overlap_input_digest"] ==
                    empty_overlap["historical_probe_overlap_input_digest"]))
        acquisition_overlap_valid = True
        if task_family_id == _NOVEL_TASK_FAMILY:
            empty_acquisition_overlap = _task_family_history_probe_overlap([],
                task_probe_inputs=acquisition_inputs)
            acquisition_count = (acquisition_overlap.get(
                "historical_probe_overlap_input_count")
                if isinstance(acquisition_overlap, Mapping) else None)
            acquisition_examples = (acquisition_overlap.get(
                "historical_probe_overlap_example_count")
                if isinstance(acquisition_overlap, Mapping) else None)
            acquisition_complete = (acquisition_overlap.get(
                "historical_probe_overlap_measurement_complete")
                if isinstance(acquisition_overlap, Mapping) else None)
            acquisition_posture = (acquisition_overlap.get(
                "historical_probe_overlap_posture")
                if isinstance(acquisition_overlap, Mapping) else None)
            expected_acquisition_posture = (
                "historical_probe_inputs_incomplete"
                if acquisition_complete is False else
                "exact_historical_probe_overlap_present" if acquisition_count else
                "no_exact_historical_probe_overlap")
            acquisition_qualified = (
                acquisition_complete is True and acquisition_count == 0)
            acquisition_overlap_valid = (
                terminal_preflight.get("schema_version") ==
                    "sentientos.rootless_campaign_transfer_probe_preflight:v3"
                and isinstance(acquisition_overlap, Mapping)
                and acquisition_overlap.get("task_probe_input_count")
                    == len(acquisition_inputs)
                and acquisition_overlap.get("task_probe_input_digest")
                    == empty_acquisition_overlap["task_probe_input_digest"]
                and type(acquisition_count) is int
                and 0 <= acquisition_count <= len(acquisition_inputs)
                and type(acquisition_examples) is int
                and acquisition_count <= acquisition_examples
                and (acquisition_count != 0 or acquisition_examples == 0)
                and type(acquisition_complete) is bool
                and acquisition_posture == expected_acquisition_posture
                and acquisition_overlap.get("historical_probe_overlap_scope")
                    == "selected_score_bound_correct_incorrect_and_abstained_examples"
                and isinstance(acquisition_overlap.get(
                    "historical_probe_overlap_input_digest"), str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}",
                    acquisition_overlap[
                        "historical_probe_overlap_input_digest"],
                    flags=re.ASCII) is not None
                and (acquisition_count != 0
                    or acquisition_overlap[
                        "historical_probe_overlap_input_digest"]
                        == empty_acquisition_overlap[
                            "historical_probe_overlap_input_digest"])
                and semantic_claim.get("novel_acquisition_qualified")
                    is acquisition_qualified)
        if (semantic_claim.get("cycle_id") != cycle_id
                or semantic_claim.get("seed") !=
                    plan["ordered_task_generation_seeds"][cycle_index]
                or semantic_claim.get("task_family_id") != task_family_id
                or semantic_claim.get("history_task_family_ids") !=
                    list(history_task_family_ids)
                or semantic_claim.get("prior_history_boundary_digest") !=
                    expected_boundary_digest
                or semantic_claim.get("acquisition_probe_inputs") != acquisition_inputs
                or semantic_claim.get("transfer_probe_inputs") != transfer_inputs
                or semantic_claim.get("inference_performed") is not False
                or semantic_claim.get("learning_claimed") is not False
                or semantic_claim.get("authority_granted") is not False
                or not isinstance(projected_record_ids, list)
                or any(not isinstance(item, str)
                    or re.fullmatch(r"devrec-[0-9a-f]{24}", item,
                        flags=re.ASCII) is None for item in projected_record_ids)
                or len(set(projected_record_ids)) != len(projected_record_ids)
                or semantic_claim.get("projected_record_set_digest") !=
                    digest_payload({"record_ids": projected_record_ids})
                or not overlap_inputs_valid
                or not acquisition_overlap_valid
                or semantic_claim.get("held_out_transfer_qualified") is not (
                    overlap["historical_probe_overlap_measurement_complete"]
                    and overlap["historical_probe_overlap_input_count"] == 0)
                or terminal_preflight.get("preflight_digest") !=
                    digest_payload(semantic_claim)):
            raise ValueError("history_campaign_transfer_probe_preflight_unverifiable")
        projected_record_ids = list(projected_record_ids)
    semantic = {
        "schema_version": (
            "sentientos.rootless_campaign_transfer_probe_preflight:v3"
            if task_family_id == _NOVEL_TASK_FAMILY else
            "sentientos.rootless_campaign_transfer_probe_preflight:v2"),
        "cycle_id": cycle_id,
        "seed": plan["ordered_task_generation_seeds"][cycle_index],
        "task_family_id": task_family_id,
        "history_task_family_ids": list(history_task_family_ids),
        "prior_history_boundary_digest": expected_boundary_digest,
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
    if task_family_id == _NOVEL_TASK_FAMILY:
        semantic["acquisition_historical_probe_overlap"] = dict(
            acquisition_overlap or {})
        semantic["novel_acquisition_qualified"] = (
            acquisition_overlap is not None
            and acquisition_overlap.get(
                "historical_probe_overlap_measurement_complete") is True
            and acquisition_overlap.get(
                "historical_probe_overlap_input_count") == 0)
    expected = {**semantic, "preflight_digest": digest_payload(semantic)}
    try:
        prereg_raw = _read_manifest_bound_file(root=root, manifest=manifest,
            relative_path="preregistration.json")
        preregistration = json.loads(prereg_raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        preregistration = None
    prereg_binding = (preregistration.get("history_campaign_binding")
        if isinstance(preregistration, Mapping) else None)
    prereg_preflight = (prereg_binding.get("transfer_probe_preflight")
        if isinstance(prereg_binding, Mapping) else None)
    nested_preflight = (campaign_binding.get("transfer_probe_preflight")
        if isinstance(campaign_binding, Mapping) else None)
    if terminal_preflight != expected:
        raise ValueError("history_campaign_transfer_probe_preflight_mismatch")
    if (nested_preflight is not None and nested_preflight != expected
            or terminal.get("status") == "incomplete"
                and terminal.get("wide_transfer_probe_preflight") is not None
                and terminal.get("wide_transfer_probe_preflight") != expected):
        raise ValueError("history_campaign_transfer_probe_duplicate_mismatch")
    if prereg_preflight is not None and prereg_preflight != expected:
        raise ValueError("history_campaign_transfer_probe_preregistration_mismatch")
    if terminal.get("status") == "completed" and prereg_preflight != expected:
        raise ValueError("history_campaign_transfer_probe_preregistration_missing")
    return expected, overlap_recomputed


def _admission_boundary_preserves(previous: Mapping[str, Any] | None,
        current: Mapping[str, Any] | None) -> bool:
    if previous is None:
        return current is None or isinstance(current, Mapping)
    if not isinstance(current, Mapping):
        return False
    previous_admissions = {row.get("admission_id"): row
        for row in previous.get("admission_bindings", [])
        if isinstance(row, Mapping)}
    previous_revocations = {row.get("revocation_id"): row
        for row in previous.get("revocation_bindings", [])
        if isinstance(row, Mapping)}
    current_admissions = {row.get("admission_id"): row
        for row in current.get("admission_bindings", [])
        if isinstance(row, Mapping)}
    current_revocations = {row.get("revocation_id"): row
        for row in current.get("revocation_bindings", [])
        if isinstance(row, Mapping)}
    return (all(current_admissions.get(key) == value
                for key, value in previous_admissions.items())
        and all(current_revocations.get(key) == value
                for key, value in previous_revocations.items()))


def _history_transfer_precondition_snapshot_binding(*, root: Path,
        manifest: Mapping[str, Any], terminal: Mapping[str, Any]
        ) -> dict[str, Any]:
    """Bind a completed decision precondition to the exact record in its manifest."""
    intervention = terminal.get("history_transfer_intervention")
    precondition = (intervention.get("history_evidence_precondition")
        if isinstance(intervention, Mapping) else None)
    if not isinstance(precondition, Mapping):
        return {"status": "precondition_not_present",
            "record_id": None, "record_digest": None, "verified": False}
    schema_version = precondition.get("schema_version")
    if schema_version != "sentientos.history_transfer_evidence_precondition:v3":
        # A skipped qualification can still persist a compact precondition
        # summary without a version or record snapshot. Do not mislabel that
        # state as a legacy schema: it means no action-consequence record was
        # available to bind, not that an older binding was attempted.
        if (schema_version is None
                and precondition.get("classification")
                    == "not_run_no_action_consequence_record"
                and precondition.get("reason_code")
                    == "no_new_action_consequence_record"
                and precondition.get("record_id") is None):
            return {"status": "precondition_not_run_no_action_consequence_record",
                "record_id": None, "record_digest": None, "verified": False}
        if schema_version is None:
            return {"status": "precondition_schema_unavailable",
                "record_id": precondition.get("record_id"),
                "record_digest": None, "verified": False}
        if schema_version not in {
                "sentientos.history_transfer_evidence_precondition:v1",
                "sentientos.history_transfer_evidence_precondition:v2"}:
            return {"status": "precondition_schema_unsupported",
                "record_id": precondition.get("record_id"),
                "record_digest": None, "verified": False}
        return {"status": "unbound_legacy_precondition",
            "record_id": precondition.get("record_id"),
            "record_digest": None, "verified": False}
    record_id = precondition.get("record_id")
    expected_digest = precondition.get("retained_record_digest")
    if (not isinstance(record_id, str)
            or re.fullmatch(r"devrec-[0-9a-f]{24}", record_id) is None
            or not isinstance(expected_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
            or precondition.get("retained_record_snapshot_binding_posture")
                != "digest_of_readiness_input"):
        return {"status": "record_snapshot_digest_unavailable_or_invalid",
            "record_id": record_id if isinstance(record_id, str) else None,
            "record_digest": expected_digest if isinstance(expected_digest, str)
                else None,
            "verified": False}
    relative_path = f"resident-cognition/history/records/{record_id}.json"
    try:
        raw = _read_manifest_bound_file(root=root, manifest=manifest,
            relative_path=relative_path)
        record = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {"status": "precondition_record_unavailable",
            "record_id": record_id, "record_digest": expected_digest,
            "verified": False}
    if not isinstance(record, Mapping) or record.get("record_id") != record_id:
        return {"status": "precondition_record_identity_mismatch",
            "record_id": record_id, "record_digest": expected_digest,
            "verified": False}
    if digest_payload(dict(record)) != expected_digest:
        return {"status": "record_snapshot_digest_mismatch",
            "record_id": record_id, "record_digest": expected_digest,
            "verified": False}
    return {"status": "exact_record_snapshot_match",
        "record_id": record_id, "record_digest": expected_digest,
        "verified": True}


def _low_range_source_correct_inputs(*, cycle_root: Path,
        manifest: Mapping[str, Any], source_run: Mapping[str, Any],
        acquisition: Mapping[str, Any], expected_probe_inputs: list[int]
        ) -> set[int]:
    """Reconcile score-bound source inputs across run, terminal, and writeback."""
    protocol = source_run.get("protocol")
    descriptor = (protocol.get("objective_task_descriptor")
        if isinstance(protocol, Mapping) else None)
    if (not isinstance(descriptor, Mapping)
            or descriptor.get("task_family_id") != _TASK_FAMILY
            or descriptor.get("probe_inputs") != expected_probe_inputs):
        raise ValueError("history_campaign_low_range_source_task_binding_invalid")
    binding = acquisition.get("history_score_binding")
    if (not isinstance(binding, Mapping)
            or binding.get("verified") is not True
            or binding.get("status") !=
                "verified_exact_source_run_score_to_history_binding"
            or binding.get("source_run_id") != source_run.get("run_id")):
        raise ValueError("history_campaign_low_range_source_writeback_unbound")
    scores = source_run.get("objective_scores")
    condition_order = (protocol.get("condition_order")
        if isinstance(protocol, Mapping) else None)
    if (not isinstance(scores, list) or not isinstance(condition_order, list)
            or len(scores) != len(condition_order)
            or [row.get("condition_id") if isinstance(row, Mapping) else None
                for row in scores] != condition_order):
        raise ValueError("history_campaign_low_range_source_scores_invalid")
    evaluation = source_run.get("objective_evaluation")
    if not isinstance(evaluation, Mapping):
        raise ValueError("history_campaign_low_range_source_evaluation_missing")
    score_by_condition: dict[str, Mapping[str, Any]] = {}
    for row in scores:
        score = row.get("score") if isinstance(row, Mapping) else None
        if (not isinstance(row, Mapping) or not isinstance(score, Mapping)
                or not isinstance(row.get("inference_receipt_id"), str)
                or not isinstance(row.get("inference_receipt_digest"), str)
                or not isinstance(row.get("invocation_output_digest"), str)
                or score.get("evaluator") !=
                    "deterministic_exact_integer_suite_oracle_v2"
                or score.get("task_digest") != descriptor.get("task_digest")
                or score.get("plan_digest") != evaluation.get("plan_digest")
                or score.get("output_digest") != row.get("invocation_output_digest")
                or type(score.get("correct_count")) is not int
                or type(score.get("probe_count")) is not int
                or not isinstance(score.get("score_digest"), str)
                or score.get("score_digest") != "sha256:" + digest_payload({
                    key: value for key, value in score.items()
                    if key != "score_digest"})
                or row["condition_id"] in score_by_condition):
            raise ValueError("history_campaign_low_range_source_score_unbound")
        receipt_id = row["inference_receipt_id"]
        if re.fullmatch(r"lmrec-[0-9a-f]{24}", receipt_id) is None:
            raise ValueError("history_campaign_low_range_source_receipt_identity_invalid")
        receipt_path = (cycle_root / "inference-custody" / "receipts"
            / f"{receipt_id}.json")
        try:
            receipt_raw = _read_manifest_bound_file(root=cycle_root,
                manifest=manifest, relative_path=receipt_path.relative_to(
                    cycle_root).as_posix())
            receipt = json.loads(receipt_raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                "history_campaign_low_range_source_receipt_unavailable") from exc
        request = receipt.get("request") if isinstance(receipt, Mapping) else None
        receipt_validation = (_validate_inference_receipt(receipt)
            if isinstance(receipt, Mapping) else (False, []))
        if (not isinstance(receipt, Mapping)
                or json.dumps(receipt, sort_keys=True, indent=2).encode("utf-8")
                    + b"\n" != receipt_raw
                or receipt_validation[0] is not True
                or receipt.get("receipt_id") != receipt_id
                or receipt.get("receipt_digest") != row["inference_receipt_digest"]
                or receipt.get("output_digest") != row["invocation_output_digest"]
                or receipt.get("status") != "admitted_completed"
                or not isinstance(request, Mapping)):
            raise ValueError("history_campaign_low_range_source_receipt_unbound")
        score_by_condition[row["condition_id"]] = score
    present = score_by_condition.get("history_present")
    if not isinstance(present, Mapping):
        raise ValueError("history_campaign_low_range_source_present_score_missing")
    receipt_binding = acquisition.get("history_score_binding")
    if (receipt_binding.get("expected_score_digest") != present.get("score_digest")
            or receipt_binding.get("observed_score_digests") !=
                [present.get("score_digest")]):
        raise ValueError("history_campaign_low_range_source_writeback_score_mismatch")
    summary = evaluation.get("probe_level_outcomes")
    outcome = acquisition.get("task_outcome")
    terminal_summary = (outcome.get("probe_level_outcomes")
        if isinstance(outcome, Mapping) else None)
    if not isinstance(summary, Mapping) or summary != terminal_summary:
        raise ValueError("history_campaign_low_range_source_outcome_unbound")
    digest_summary = summary.get("condition_score_digests")
    if (not isinstance(digest_summary, Mapping)
            or any(digest_summary.get(condition) != score_by_condition[
                condition].get("score_digest") for condition in condition_order)):
        raise ValueError("history_campaign_low_range_source_score_digest_mismatch")
    probe_rows = summary.get("probe_outcomes")
    score_rows = present.get("probe_results")
    if (not isinstance(probe_rows, list) or not isinstance(score_rows, list)
            or len(probe_rows) != len(expected_probe_inputs)
            or len(score_rows) != len(expected_probe_inputs)
            or type(present.get("probe_count")) is not int
            or present.get("probe_count") != len(expected_probe_inputs)):
        raise ValueError("history_campaign_low_range_source_probe_count_invalid")
    correct_inputs: set[int] = set()
    for expected_input, probe_row, score_row in zip(
            expected_probe_inputs, probe_rows, score_rows):
        correctness = (probe_row.get("correctness_by_condition")
            if isinstance(probe_row, Mapping) else None)
        abstention = (probe_row.get("abstention_by_condition")
            if isinstance(probe_row, Mapping) else None)
        if (not isinstance(probe_row, Mapping)
                or not isinstance(score_row, Mapping)
                or probe_row.get("probe_input") != expected_input
                or score_row.get("probe_input") != expected_input
                or not isinstance(correctness, Mapping)
                or not isinstance(abstention, Mapping)
                or type(abstention.get("history_present")) is not bool):
            raise ValueError("history_campaign_low_range_source_probe_score_mismatch")
        observed_correct = correctness.get("history_present")
        if abstention["history_present"]:
            if (observed_correct is not None
                    or score_row.get("correct") is not None
                    or score_row.get("abstained") is not True):
                raise ValueError(
                    "history_campaign_low_range_source_abstention_mismatch")
        elif (type(observed_correct) is not bool
                or score_row.get("correct") is not observed_correct
                or score_row.get("abstained") is True):
            raise ValueError("history_campaign_low_range_source_probe_score_mismatch")
        elif observed_correct:
            correct_inputs.add(expected_input)
    if (type(present.get("correct_count")) is not int
            or present.get("correct_count") != len(correct_inputs)
            or present.get("status") not in {"correct", "incorrect", "selective"}
            or ((present.get("status") == "correct") !=
                (len(correct_inputs) == len(expected_probe_inputs)))):
        raise ValueError("history_campaign_low_range_source_correct_count_mismatch")
    return correct_inputs


def verify_chain(*, plan_path: Path, cycle_roots: list[Path],
        initial_history_bundle_path: Path | None = None,
        allow_prefix: bool = False) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    initial_bundle_files: dict[str, bytes] | None = None
    initial_bundle_digest: str | None = None
    if initial_history_bundle_path is not None:
        if plan.get("task_family_id") not in _RANGE_TASK_FAMILIES:
            raise ValueError("history_campaign_seed_bundle_family_invalid")
        initial_bundle_files, initial_bundle_digest = _load_initial_history_bundle(
            initial_history_bundle_path, plan=plan)
    cycle_ids = plan["ordered_cycle_ids"]
    if (not cycle_roots or len(cycle_roots) > len(cycle_ids)
            or len(cycle_roots) != len(cycle_ids) and not allow_prefix):
        raise ValueError("history_campaign_cycle_root_count_mismatch")
    initial = plan["initial_history_boundary"]
    previous = {"resident-cognition/history/" + row["path"]: {
        "path": "resident-cognition/history/" + row["path"],
        "size_bytes": row["size_bytes"], "sha256": row["sha256"]}
        for row in initial["files"]}
    chain_rows = []
    append_only = True
    seed_boundary_chain_verified = True
    runtime_admission_chain_verified = plan.get("schema_version") in {
        "sentientos.rootless_history_boundary_campaign_plan:v5",
        "sentientos.rootless_history_boundary_campaign_plan:v6",
        "sentientos.rootless_history_boundary_campaign_plan:v7",
        "sentientos.rootless_history_boundary_campaign_plan:v8",
        "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13",
                "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}
    previous_admission_boundary = (plan.get("initial_runtime_admission_ledger")
        if runtime_admission_chain_verified else None)
    cognition_recovery_chain_verified = runtime_admission_chain_verified
    previous_recovery_state = (plan.get("initial_cognition_recovery_state")
        if cognition_recovery_chain_verified else None)
    completed_cycle_count = 0
    verified_source_run_ids: set[str] = set()
    low_range_source_run_ids: set[str] = set()
    low_range_correct_inputs: set[int] = set()
    low_range_contributing_source_runs: set[str] = set()
    for index, root in enumerate(cycle_roots):
        cycle_id, status, terminal_path = _cycle_identity(root)
        if cycle_id != cycle_ids[index]:
            raise ValueError("history_campaign_cycle_order_or_status_invalid")
        resolved = root.resolve(strict=True)
        manifest = create_manifest(cycle_root=resolved,
            output_path=resolved.parent / f".{cycle_id}.manifest-not-written.json")
        terminal_name = "cycle-result.json" if status == "completed" else "cycle-failure.json"
        try:
            terminal_raw = _read_manifest_bound_file(root=resolved,
                manifest=manifest, relative_path=terminal_name)
            terminal = json.loads(terminal_raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("history_campaign_cycle_terminal_invalid") from exc
        if (terminal_path != resolved / terminal_name
                or not isinstance(terminal, Mapping)
                or terminal.get("run_id") != cycle_id
                or terminal.get("status") != status):
            raise ValueError("history_campaign_cycle_terminal_path_invalid")
        current = _cycle_history_files(manifest)
        seed_evidence = terminal.get("prior_developmental_history_seed")
        try:
            current_admission_boundary = _runtime_admission_boundary(
                resolved / "resident-cognition" / "history")
        except (OSError, ValueError, RuntimeError):
            current_admission_boundary = None
        current_admission_boundary_verified = (
            terminal.get("runtime_admission_ledger") == current_admission_boundary)
        expected_seed_admission_boundary = previous_admission_boundary
        admission_seed_verified = (
            runtime_admission_chain_verified
            and isinstance(seed_evidence, Mapping)
            and seed_evidence.get("source_runtime_admission_ledger")
                == expected_seed_admission_boundary
            and seed_evidence.get("runtime_admission_ledger_copied")
                is (expected_seed_admission_boundary is not None)
            and current_admission_boundary_verified)
        admission_ledger_append_only = _admission_boundary_preserves(
            expected_seed_admission_boundary, current_admission_boundary)
        if not (admission_seed_verified and admission_ledger_append_only):
            runtime_admission_chain_verified = False
        try:
            current_recovery_state = _cognition_recovery_state_boundary(
                resolved / "resident-cognition" / "state")
        except (OSError, ValueError, RuntimeError):
            current_recovery_state = None
        current_recovery_state_verified = (
            terminal.get("cognition_recovery_state_boundary")
                == current_recovery_state)
        recovery_seed_verified = (
            cognition_recovery_chain_verified
            and isinstance(seed_evidence, Mapping)
            and seed_evidence.get("source_cognition_recovery_state")
                == previous_recovery_state
            and seed_evidence.get("cognition_recovery_state_copied")
                is (previous_recovery_state is not None)
            and current_recovery_state_verified)
        recovery_state_append_only = _cognition_recovery_state_preserves(
            previous_recovery_state, current_recovery_state)
        if not (recovery_seed_verified and recovery_state_append_only):
            cognition_recovery_chain_verified = False
        seed_boundary_verified = False
        seed_preregistration_verified = False
        prior_files_preserved = all(current.get(path) == row
            for path, row in previous.items())
        if isinstance(seed_evidence, Mapping):
            seed_status = seed_evidence.get("status")
            if seed_status == "not_configured":
                seed_boundary_verified = not previous
            elif (seed_status == "copied_and_reloaded_verified"
                    and prior_files_preserved):
                seed_preregistration_verified = _verify_seed_preregistration(
                    root=resolved, manifest=manifest, terminal=terminal,
                    seed_evidence=seed_evidence, cycle_id=cycle_id)
                expected_seed_digest, expected_record_count, expected_receipt_count = (
                    _seed_source_boundary_digest(root=resolved, manifest=manifest,
                        previous=previous))
                seed_boundary_verified = (
                    seed_evidence.get("source_boundary_digest") == expected_seed_digest
                    and type(seed_evidence.get("record_count")) is int
                    and seed_evidence.get("record_count") == expected_record_count
                    and type(seed_evidence.get("receipt_count")) is int
                    and seed_evidence.get("receipt_count") == expected_receipt_count
                    and seed_evidence.get("copied_into_run_store") is True
                    and seed_evidence.get("model_attention_verified") is False
                    and seed_preregistration_verified)
        if not seed_boundary_verified:
            seed_boundary_chain_verified = False
        source_run_digest = None
        acquired_record_id = None
        observed_source_run_id = None
        run_parameters_verified = False
        source_run_binding_verified = False
        expected_campaign_binding = {
            "campaign_id": plan["campaign_id"],
            "campaign_plan_digest": plan["plan_digest"],
            "cycle_index": index}
        transfer_preflight_result = _verify_transfer_probe_preflight(
            root=resolved, manifest=manifest, terminal=terminal,
            plan=plan, cycle_index=index, previous=previous,
            initial_bundle_files=(initial_bundle_files if index == 0 else None))
        transfer_preflight = (transfer_preflight_result[0]
            if transfer_preflight_result is not None else None)
        transfer_overlap_recomputed = (transfer_preflight_result[1]
            if transfer_preflight_result is not None else False)
        if transfer_preflight is not None:
            expected_campaign_binding["transfer_probe_preflight"] = transfer_preflight
        precondition_snapshot = _history_transfer_precondition_snapshot_binding(
            root=resolved, manifest=manifest, terminal=terminal)
        terminal_campaign_binding = terminal.get("history_campaign_binding")
        campaign_binding_verified = (
            terminal.get("external_preregistration_digest") == plan["plan_digest"]
            and (terminal_campaign_binding == expected_campaign_binding
                or status == "incomplete"
                    and terminal_campaign_binding is None
                    and transfer_preflight is not None))
        failure_stage = (terminal.get("stage") if status == "incomplete"
            and isinstance(terminal.get("stage"), str) else None)
        failure_code = (terminal.get("failure_code")
            if status == "incomplete"
                and isinstance(terminal.get("failure_code"), str) else None)
        if status == "completed":
            acquisition = terminal.get("objective_task_family_acquisition")
            active_identity = terminal.get("active_model_identity")
            observed_source_run_id = (acquisition.get("run_id")
                if isinstance(acquisition, Mapping) else None)
            if (not isinstance(observed_source_run_id, str)
                    or _RUN_ID.fullmatch(observed_source_run_id) is None):
                raise ValueError("history_campaign_source_run_identity_invalid")
            run_parameters_verified = (
                campaign_binding_verified
                and isinstance(acquisition, Mapping)
                and acquisition.get("task_family_id") == plan["task_family_id"]
                and type(terminal.get("task_generation_seed")) is int
                and terminal["task_generation_seed"]
                    == plan["ordered_task_generation_seeds"][index]
                and type(terminal.get("requested_backend_seed")) is int
                and terminal["requested_backend_seed"]
                    == plan["ordered_backend_seeds"][index]
                and isinstance(active_identity, Mapping)
                and digest_payload({"identity": dict(active_identity)})
                    == _plan_model_identity_digests(plan)[index])
            if not run_parameters_verified:
                raise ValueError("history_campaign_preregistered_run_binding_invalid")
            source_run_path = (resolved / "resident-cognition" / "state"
                / "developmental_experiments" / "runs"
                / f"{observed_source_run_id}.json")
            try:
                source_run_raw = _read_manifest_bound_file(root=resolved,
                    manifest=manifest, relative_path=source_run_path.relative_to(
                        resolved).as_posix())
                source_run = json.loads(source_run_raw.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("history_campaign_source_run_unavailable") from exc
            source_run_semantic = ({key: value for key, value in source_run.items()
                if key not in {"run_id", "run_digest"}}
                if isinstance(source_run, Mapping) else {})
            source_run_digest = _experiment_digest(source_run_semantic)
            protocol = (source_run.get("protocol")
                if isinstance(source_run, Mapping) else None)
            task_descriptor = (protocol.get("objective_task_descriptor")
                if isinstance(protocol, Mapping) else None)
            if (not isinstance(source_run, Mapping)
                    or source_run.get("run_id") != observed_source_run_id
                    or source_run.get("run_digest") != source_run_digest
                    or acquisition.get("run_digest") != source_run_digest
                    or not isinstance(task_descriptor, Mapping)
                    or task_descriptor.get("task_family_id") != plan["task_family_id"]):
                raise ValueError("history_campaign_source_run_binding_invalid")
            source_run_binding_verified = True
            if (plan.get("schema_version") ==
                    "sentientos.rootless_history_boundary_campaign_plan:v15"):
                acquisition_task, _ = rootless_integer_affine_transfer_task_pair(
                    plan["ordered_task_generation_seeds"][index],
                    task_family_id=_TASK_FAMILY,
                    acquisition_probe_count=plan.get("acquisition_probe_count", 3),
                    transfer_probe_count=plan.get("transfer_probe_count", 3))
                expected_inputs = [acquisition_task.probe_input,
                    *acquisition_task.additional_probe_inputs]
                correct_inputs = _low_range_source_correct_inputs(
                    cycle_root=resolved, manifest=manifest, source_run=source_run,
                    acquisition=acquisition, expected_probe_inputs=expected_inputs)
                low_range_source_run_ids.add(observed_source_run_id)
                if correct_inputs - low_range_correct_inputs:
                    low_range_contributing_source_runs.add(observed_source_run_id)
                low_range_correct_inputs.update(correct_inputs)
            acquired_record_id = acquisition.get("history_record_id")
            acquired_record_path = (f"resident-cognition/history/records/"
                f"{acquired_record_id}.json"
                if isinstance(acquired_record_id, str)
                    and re.fullmatch(r"devrec-[0-9a-f]{24}", acquired_record_id)
                else None)
            if acquired_record_path is None or acquired_record_path not in current:
                raise ValueError("history_campaign_acquisition_record_not_retained")
            completed_cycle_count += 1
            verified_source_run_ids.add(observed_source_run_id)
        changed = sorted(path for path, row in previous.items()
            if current.get(path) != row)
        if changed:
            append_only = False
        additions = sorted(set(current) - set(previous))
        boundary_files = [{**current[path], "path": path.removeprefix(
            "resident-cognition/history/")} for path in sorted(current)]
        semantic_boundary = {"schema_version": "sentientos.rootless_history_boundary:v1",
            "file_count": len(current),
            "total_size_bytes": sum(row["size_bytes"] for row in current.values()),
            "files": boundary_files,
            "atomic_snapshot": False}
        boundary_digest = digest_payload(semantic_boundary)
        cycle_audit_row = {
            "cycle_id": cycle_id,
            "expected_model_identity_digest":
                _plan_model_identity_digests(plan)[index],
            "terminal_status": status,
            "cycle_manifest_digest": manifest["manifest_digest"],
            "history_boundary_digest": boundary_digest,
            "history_file_count": len(current),
            "history_seed_boundary_verified": seed_boundary_verified,
            "expected_runtime_admission_ledger": expected_seed_admission_boundary,
            "runtime_admission_ledger": current_admission_boundary,
            "runtime_admission_seed_verified": admission_seed_verified,
            "runtime_admission_ledger_append_only": admission_ledger_append_only,
            "expected_cognition_recovery_state": previous_recovery_state,
            "cognition_recovery_state": current_recovery_state,
            "cognition_recovery_seed_verified": recovery_seed_verified,
            "cognition_recovery_state_append_only": recovery_state_append_only,
            "run_preregistration_binding_verified": seed_preregistration_verified,
            "campaign_binding_verified": campaign_binding_verified,
            "transfer_probe_preflight_verified": transfer_preflight is not None,
            "transfer_probe_overlap_recomputed": transfer_overlap_recomputed,
            "transfer_probe_preflight_digest": (transfer_preflight.get(
                "preflight_digest") if transfer_preflight is not None else None),
            "history_transfer_precondition_snapshot_status": (
                precondition_snapshot["status"]),
            "history_transfer_precondition_record_id": (
                precondition_snapshot["record_id"]),
            "history_transfer_precondition_record_digest": (
                precondition_snapshot["record_digest"]),
            "history_transfer_precondition_snapshot_verified": (
                precondition_snapshot["verified"]),
            "source_run_id": (observed_source_run_id
                if source_run_binding_verified else None),
            "source_run_digest": source_run_digest,
            "acquisition_history_record_id": acquired_record_id,
            "run_parameters_verified": run_parameters_verified,
            "source_run_binding_verified": source_run_binding_verified,
            "failure_stage": failure_stage,
            "failure_code": failure_code,
            "new_history_paths": additions,
            "changed_or_missing_prior_paths": changed,
            "append_only_from_prior_boundary": not changed,
        }
        if plan.get("task_family_id") == _NOVEL_TASK_FAMILY:
            acquisition_overlap = transfer_preflight.get(
                "acquisition_historical_probe_overlap")
            cycle_audit_row.update({
                "acquisition_probe_preflight_verified": (
                    isinstance(acquisition_overlap, Mapping)
                    and type(transfer_preflight.get(
                        "novel_acquisition_qualified")) is bool),
                "acquisition_probe_overlap_recomputed": (
                    transfer_overlap_recomputed),
                "acquisition_probe_overlap_input_count": (
                    acquisition_overlap.get(
                        "historical_probe_overlap_input_count")
                    if isinstance(acquisition_overlap, Mapping) else None),
                "acquisition_probe_overlap_measurement_complete": (
                    acquisition_overlap.get(
                        "historical_probe_overlap_measurement_complete")
                    if isinstance(acquisition_overlap, Mapping) else None),
                "novel_acquisition_qualified": (
                    transfer_preflight.get("novel_acquisition_qualified")
                    if isinstance(transfer_preflight, Mapping) else False),
            })
        chain_rows.append(cycle_audit_row)
        previous = current
        previous_admission_boundary = current_admission_boundary
        previous_recovery_state = current_recovery_state
    semantic = {
        "schema_version": (
            "sentientos.rootless_history_boundary_campaign_audit:v12"
            if plan.get("schema_version") ==
                "sentientos.rootless_history_boundary_campaign_plan:v15" else
            "sentientos.rootless_history_boundary_campaign_audit:v11"
            if plan.get("task_family_id") == _NOVEL_TASK_FAMILY else
            "sentientos.rootless_history_boundary_campaign_audit:v10"),
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "task_family_id": plan["task_family_id"],
        "ordered_model_identity_digests": _plan_model_identity_digests(plan),
        "planned_cycle_count": len(cycle_ids),
        "completed_cycle_count": completed_cycle_count,
        "incomplete_cycle_count": len(cycle_ids) - completed_cycle_count,
        "all_planned_cycles_completed": completed_cycle_count == len(cycle_ids),
        "source_run_count": len(verified_source_run_ids),
        "low_range_source_eligibility": ({
            "schema_version": _LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL["schema_version"],
            "verified_score_bound_source_run_count": len(low_range_source_run_ids),
            "source_run_count_with_unique_correct_input_contribution": len(
                low_range_contributing_source_runs),
            "distinct_score_bound_correct_input_count": len(low_range_correct_inputs),
            "minimum_source_run_count": _LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL[
                "minimum_score_bound_correct_source_runs"],
            "minimum_distinct_correct_input_count": _LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL[
                "minimum_distinct_correct_source_inputs"],
            "eligible": (
                len(low_range_contributing_source_runs) >=
                    _LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL[
                        "minimum_score_bound_correct_source_runs"]
                and len(low_range_correct_inputs) >=
                    _LOW_RANGE_SOURCE_ACQUISITION_PROTOCOL[
                        "minimum_distinct_correct_source_inputs"]),
            "correct_input_values_included": False,
            "learning_established": False,
            "authority": False,
        } if (plan.get("schema_version") ==
            "sentientos.rootless_history_boundary_campaign_plan:v15") else None),
        "history_transfer_precondition_snapshot_chain_verified": (
            completed_cycle_count > 0 and all(
                row["history_transfer_precondition_snapshot_verified"]
                for row in chain_rows if row["terminal_status"] == "completed")),
        "initial_history_boundary_digest": initial["boundary_digest"],
        "initial_history_seed_bundle_digest": initial_bundle_digest,
        "initial_history_seed_bundle_verified": initial_bundle_digest is not None,
        "cycle_boundaries": chain_rows,
        "atomic_snapshot": False,
        "file_append_only_history_chain_verified": append_only,
        "seed_boundary_chain_verified": seed_boundary_chain_verified,
        "runtime_admission_chain_verified": runtime_admission_chain_verified,
        "cognition_recovery_state_chain_verified":
            cognition_recovery_chain_verified,
        "append_only_history_chain_verified": (
            append_only and seed_boundary_chain_verified),
        "preregistration_timing_independently_attested": False,
        "model_attention_established": False,
        "learning_established": False,
        "authority": False,
    }
    return {**semantic, "audit_digest": digest_payload(semantic)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--history-root", type=Path, required=True)
    prepare.add_argument("--campaign-id", required=True)
    prepare.add_argument("--task-family-id", required=True)
    prepare.add_argument("--model-identity-digest", action="append")
    prepare.add_argument("--model-manifest-path", type=Path)
    prepare.add_argument("--model-name")
    prepare.add_argument("--gpu-layers", type=int, default=32)
    prepare.add_argument("--transfer-probe-count", type=int, default=3,
        help=("number of fixed transfer probes; 4-16 uses v10 for the v7 "
            "cross-range design and v12 for the v8 novel-range design"))
    prepare.add_argument("--acquisition-probe-count", type=int, default=3,
        help=("number of fixed acquisition probes; 4-16 is bound by plan v14 "
            "for the v8 novel-range family and keeps a two-thirds competence gate"))
    prepare.add_argument("--cross-range-history-enabled-competence",
        action="store_true",
        help="preregister the separate v6-history-enabled v7 competence outcome")
    prepare.add_argument("--cycle-id", action="append", required=True)
    prepare.add_argument("--task-generation-seed", action="append", type=int,
        required=True)
    prepare.add_argument("--backend-seed", action="append", type=int,
        required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--verify-existing", action="store_true",
        help="verify an existing plan without replacing it")
    verify = commands.add_parser("verify")
    verify.add_argument("--plan", type=Path, required=True)
    verify.add_argument("--cycle-root", type=Path, action="append", required=True)
    verify.add_argument("--initial-history-bundle", type=Path,
        help="verified seed bundle for recomputing first-cycle overlap")
    verify.add_argument("--output", type=Path, required=True)
    verify.add_argument("--verify-existing", action="store_true",
        help="verify an existing audit without replacing it")
    verify_plan = commands.add_parser("verify-plan",
        help="recompute source and model pins without loading a model")
    verify_plan.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        _require_output_outside(args.output, [args.history_root])
        if args.model_identity_digest is not None:
            if (args.model_manifest_path is not None or args.model_name is not None
                    or len(args.model_identity_digest) != len(args.cycle_id)):
                raise SystemExit("history_campaign_model_identity_inputs_invalid")
            identity_digests = args.model_identity_digest
        else:
            if args.model_manifest_path is None or not args.model_name:
                raise SystemExit("history_campaign_model_identity_inputs_invalid")
            identity_digests = derive_model_identity_digests(
                manifest_path=args.model_manifest_path,
                model_name=args.model_name, gpu_layers=args.gpu_layers,
                backend_seeds=args.backend_seed)
        identity_recipe = (build_model_identity_recipe(
                manifest_path=args.model_manifest_path,
                model_name=args.model_name, gpu_layers=args.gpu_layers)
            if args.model_identity_digest is None
                and args.task_family_id in {_TASK_FAMILY, *_RANGE_TASK_FAMILIES}
            else None)
        value = create_plan(history_root=args.history_root,
            campaign_id=args.campaign_id, task_family_id=args.task_family_id,
            model_identity_digests=identity_digests,
            ordered_cycle_ids=args.cycle_id,
            task_generation_seeds=args.task_generation_seed,
            backend_seeds=args.backend_seed,
            model_identity_recipe=identity_recipe,
            cross_range_history_enabled_competence=(
                args.cross_range_history_enabled_competence),
            acquisition_probe_count=args.acquisition_probe_count,
            transfer_probe_count=args.transfer_probe_count)
        operation = _persist_or_verify(value, args.output,
            verify_existing=args.verify_existing)
        print(json.dumps({"plan": str(args.output),
            "operation": operation,
            "plan_digest": value["plan_digest"],
            "initial_history_boundary_digest": value[
                "initial_history_boundary"]["boundary_digest"],
            "model_identity_recipe_digest": (
                digest_payload(dict(identity_recipe))
                if identity_recipe is not None else None),
            "preregistration_timing_independently_attested": False,
            "inference_performed": False, "authority": False}, sort_keys=True))
        return
    if args.command == "verify-plan":
        plan = _load_plan(args.plan)
        evidence = verify_model_identity_recipe(plan)
        if plan.get("schema_version") in {
                "sentientos.rootless_history_boundary_campaign_plan:v8",
                "sentientos.rootless_history_boundary_campaign_plan:v9",
                "sentientos.rootless_history_boundary_campaign_plan:v10",
                "sentientos.rootless_history_boundary_campaign_plan:v11",
                "sentientos.rootless_history_boundary_campaign_plan:v12",
                "sentientos.rootless_history_boundary_campaign_plan:v13",
                "sentientos.rootless_history_boundary_campaign_plan:v14", "sentientos.rootless_history_boundary_campaign_plan:v15"}:
            evidence.update(verify_experiment_implementation(plan))
        else:
            evidence.update({
                "experiment_implementation_bound": False,
                "experiment_implementation_matches_current": False,
            })
        print(json.dumps({"operation": "verified",
            "campaign_id": plan["campaign_id"],
            "plan_digest": plan["plan_digest"], **evidence}, sort_keys=True))
        return
    _require_output_outside(args.output, args.cycle_root)
    value = verify_chain(plan_path=args.plan, cycle_roots=args.cycle_root,
        initial_history_bundle_path=args.initial_history_bundle)
    operation = _persist_or_verify(value, args.output,
        verify_existing=args.verify_existing)
    print(json.dumps({"audit": str(args.output),
        "operation": operation,
        "audit_digest": value["audit_digest"],
        "append_only_history_chain_verified": value[
            "append_only_history_chain_verified"],
        "seed_boundary_chain_verified": value["seed_boundary_chain_verified"],
        "all_planned_cycles_completed": value["all_planned_cycles_completed"],
        "learning_established": False, "inference_performed": False,
        "authority": False}, sort_keys=True))


if __name__ == "__main__":
    main()
