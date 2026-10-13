#!/usr/bin/env python3
"""Read-only prerequisite report for one staged resident history experiment.

This command inspects only operator-selected paths. It never invokes a model,
downloads an artifact, writes custody, admits a call, or activates serving.
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.local_model_commissioning import inspect_artifact
from sentientos.installation_state import (
    InstallationIdentity, InstallationStateError, InstallationStateRegistry,
)
from sentientos.resident_cognitive_model_serving import (
    ResidentCognitiveModelServingError,
    load_config as load_serving_config,
)
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionError,
    load_config as load_cognition_config,
)
from sentientos.resident_developmental_writeback import DevelopmentalHistoryStore
from sentientos.resident_developmental_writeback import WritebackReceipt, _identity
from sentientos.platform_fcntl import FLOCK_SUPPORTED


def _custody_status(os_name: str, primitives: dict[str, bool]) -> str:
    if os_name != "posix":
        return "unsupported_by_current_experiment_custody"
    if all(primitives.values()):
        return "required_posix_primitives_available_filesystem_unverified"
    return "required_posix_primitive_missing"


def _receipt_linked_history(store: DevelopmentalHistoryStore) -> tuple[Any, ...]:
    """Read records and receipts without repairing an interrupted publication.

    A content-valid record alone is not evidence that its separate writeback
    receipt reached durable custody. The cognition owner can recover that
    publication, but this preflight must remain read-only and must not predict
    that recovery will succeed.
    """
    records = store.records()
    receipts = store.receipts()
    records_by_id = {record.record_id: record for record in records}
    if len(records_by_id) != len(records):
        raise ValueError("durable_record_identity_collision")
    receipts_by_record: dict[str, Any] = {}
    for receipt in receipts:
        record = records_by_id.get(receipt.record_id)
        if record is None:
            raise ValueError("durable_receipt_orphaned")
        candidate_id = record.candidate.get("candidate_id")
        candidate_digest = record.candidate.get("candidate_digest")
        if not isinstance(candidate_id, str) or not isinstance(candidate_digest, str):
            raise ValueError("durable_receipt_candidate_identity_invalid")
        expected = WritebackReceipt("", "", record.record_id, record.record_digest,
            candidate_id, candidate_digest, record.admission_id,
            record.admission_binding_digest, record.principal, record.operation_id, True)
        receipt_id, receipt_digest = _identity("devreceipt", expected.semantic_payload())
        expected = WritebackReceipt(receipt_id, receipt_digest, record.record_id,
            record.record_digest, candidate_id, candidate_digest, record.admission_id,
            record.admission_binding_digest, record.principal, record.operation_id, True)
        if receipt != expected or record.record_id in receipts_by_record:
            raise ValueError("durable_receipt_record_lineage_mismatch")
        receipts_by_record[record.record_id] = receipt
    if records and len(receipts_by_record) != len(records):
        raise ValueError("durable_history_receipt_recovery_required")
    return records


def inspect_host_runtime() -> dict[str, Any]:
    """Report runtime prerequisites without importing or starting a model.

    The custody result describes Python's exposed POSIX primitives only. It
    does not prove the selected filesystem, WSL GPU path, or daemon admission
    will work. In particular, presence of ``llama_cpp`` is not CUDA evidence.
    """
    dir_fd: set[Any] = getattr(os, "supports_dir_fd", set())
    try:
        replace_signature = inspect.signature(os.replace)
        replace_dir_fd = {"src_dir_fd", "dst_dir_fd"}.issubset(replace_signature.parameters)
    except (TypeError, ValueError):
        replace_dir_fd = False
    required = {
        "open_dir_fd": os.open in dir_fd,
        "mkdir_dir_fd": os.mkdir in dir_fd,
        "link_dir_fd": os.link in dir_fd,
        # CPython exposes os.replace's dir_fd keywords even though it is not
        # itself listed in supports_dir_fd (os.rename is listed separately).
        "replace_dir_fd": replace_dir_fd,
        "no_follow": hasattr(os, "O_NOFOLLOW"),
        "directory_open": hasattr(os, "O_DIRECTORY"),
        "file_and_directory_fsync": callable(getattr(os, "fsync", None)),
        "cross_process_flock": FLOCK_SUPPORTED,
    }
    system = platform.system()
    release = platform.release()
    wsl_indicated = bool(system == "Linux" and (
        "microsoft" in release.lower() or os.environ.get("WSL_INTEROP")
        or os.environ.get("WSL_DISTRO_NAME")))
    try:
        backend_available = importlib.util.find_spec("llama_cpp") is not None
    except (ImportError, ValueError):
        backend_available = False
    custody_status = _custody_status(os.name, required)
    return {
        "platform": {
            "system": system,
            "release": release[:160],
            "machine": platform.machine()[:80],
            "wsl_indicated": wsl_indicated,
            "wsl_gpu_status": "not_observed",
        },
        "python": {
            "implementation": sys.implementation.name,
            "version": platform.python_version(),
            "executable": sys.executable,
            "project_requires_python": ">=3.8",
        },
        "local_backend": {
            "engine": "llama_cpp",
            "python_package_available": backend_available,
            "cuda_or_gpu_offload_status": "not_observed",
        },
        "experiment_custody": {
            "status": custody_status,
            "posix_primitives": required,
            "filesystem_crash_durability": "not_observed",
            "serving_and_inference_admission": "not_observed",
        },
    }


def inspect_readiness(config_path: Path, model_path: Path,
                      allowed_root: Path, *, serving_config_path: Path | None = None,
                      installation_registry: InstallationStateRegistry | None = None
                      ) -> dict[str, Any]:
    host_runtime = inspect_host_runtime()
    findings: dict[str, Any] = {
        "schema_version": "sentientos.resident_objective_experiment_readiness:v1",
        "readiness_scope": "read_only_preflight_not_execution_readiness",
        "source_contracts": {
            "resident_configuration": "sentientos.resident_developmental_cognition_config",
            "history_custody": "DevelopmentalHistoryStore.records",
            "artifact_inspection": "sentientos.local_model_commissioning.inspect_artifact",
            "serving_installation": "InstallationStateRegistry.open_read_only",
        },
        "authority_effect_posture": {
            "model_generation": False, "model_download": False,
            "serving_activation": False, "inference_admission": False,
            "authority_granted": False,
        },
        "findings": {},
        "host_runtime": host_runtime,
        "unobserved_runtime_gates": [
            "daemon_world_state_and_tick_not_observed",
            "resident_invoker_model_identity_not_observed",
            "per_call_local_model_inference_admission_not_requested",
            "objective_task_history_and_current_context_contamination_review_required",
            "effective_generation_budget_not_observed_at_daemon_runtime",
            "current_resident_serving_session_not_observed",
        ],
    }
    try:
        config = load_cognition_config(config_path)
        findings["findings"]["resident_configuration"] = {
            "status": "enabled" if config.enabled and config.comparison_enabled else "disabled_or_ineligible",
            "enabled": config.enabled,
            "history_comparison_enabled": config.comparison_enabled,
            "configured_source_kind_count": len(config.allowed_source_kinds),
        }
        if not config.enabled or not config.comparison_enabled:
            findings["findings"]["resident_configuration"]["reason_code"] = "history_comparison_not_enabled"
        try:
            records = _receipt_linked_history(DevelopmentalHistoryStore(config.history_root))
            history_status = "eligible_history_present" if records else "awaiting_eligible_history"
            findings["findings"]["developmental_history"] = {
                "status": history_status, "verified_record_count": len(records),
                "maximum_reported_records": min(len(records), config.max_retrieved_records),
                "reason_code": None if records else "no_verified_developmental_history_records",
            }
        except Exception as exc:
            findings["findings"]["developmental_history"] = {
                "status": "invalid_custody", "reason_code": str(exc)[:160],
            }
    except (ResidentDevelopmentalCognitionError, OSError, ValueError) as exc:
        findings["findings"]["resident_configuration"] = {
            "status": "invalid_custody", "reason_code": str(exc)[:160],
        }
        findings["findings"]["developmental_history"] = {
            "status": "not_checked", "reason_code": "resident_configuration_unavailable",
        }

    findings["findings"]["request_custody_platform"] = {
        "status": ("required_primitives_available" if host_runtime["experiment_custody"]["status"]
            == "required_posix_primitives_available_filesystem_unverified" else "unsupported"),
        "reason_code": (None if host_runtime["experiment_custody"]["status"]
            == "required_posix_primitives_available_filesystem_unverified" else
            ("resident_request_publisher_posix_only" if os.name != "posix"
                else "required_posix_custody_primitive_missing")),
        "filesystem_durability": "not_observed",
    }
    if serving_config_path is None:
        findings["findings"]["serving_installation"] = {
            "status": "awaiting_explicit_serving_configuration",
            "reason_code": "serving_configuration_not_supplied",
            "active_session_status": "not_observed",
        }
    else:
        try:
            serving = load_serving_config(str(serving_config_path))
            if not serving.enabled or not serving.installation_identity:
                findings["findings"]["serving_installation"] = {
                    "status": "disabled", "reason_code": "serving_configuration_disabled",
                    "active_session_status": "not_observed",
                }
            else:
                identity = InstallationIdentity.parse(serving.installation_identity)
                registry = installation_registry or InstallationStateRegistry.system()
                registry.open_read_only(identity)
                findings["findings"]["serving_installation"] = {
                    "status": "installation_root_verified_read_only",
                    "installation_identity": identity.value,
                    "configuration_digest": serving.config_digest,
                    "active_session_status": "not_observed",
                    "inference_admission_status": "not_observed",
                }
        except (ResidentCognitiveModelServingError, InstallationStateError,
                OSError, TypeError, ValueError) as exc:
            code = str(getattr(exc, "code", "") or str(exc))[:160]
            findings["findings"]["serving_installation"] = {
                "status": "invalid_or_unavailable",
                "reason_code": code,
                "active_session_status": "not_observed",
            }
    try:
        artifact = inspect_artifact(model_path, allowed_root=allowed_root)
        findings["findings"]["explicit_model_artifact"] = {
            "status": "verified_local_candidate",
            "identity_scope": "operator_selected_file_not_resident_loaded_model",
            "artifact_size_bytes": artifact["artifact_size_bytes"],
            "model_content_sha256": artifact["model_content_sha256"],
            "semantic_artifact_identity": artifact["semantic_artifact_identity"],
            "configuration_digest": artifact["configuration_digest"],
            "configuration_scope": "artifact_inspection_defaults_not_daemon_runtime_configuration",
            "backend_dependency_available": artifact["llama_cpp_dependency_available"],
        }
        if not artifact["llama_cpp_dependency_available"]:
            findings["findings"]["explicit_model_artifact"]["status"] = "runtime_incompatible"
            findings["findings"]["explicit_model_artifact"]["reason_code"] = "llama_cpp_dependency_unavailable"
    except (OSError, ValueError) as exc:
        reason = str(exc)[:160]
        findings["findings"]["explicit_model_artifact"] = {
            "status": "awaiting_artifact" if reason in {"artifact_unavailable", "artifact_unreadable"}
                else "invalid_custody",
            "reason_code": reason,
        }

    observed = findings["findings"]
    config_ready = observed.get("resident_configuration", {}).get("status") == "enabled"
    history_ready = observed.get("developmental_history", {}).get("status") == "eligible_history_present"
    artifact_ready = observed.get("explicit_model_artifact", {}).get("status") == "verified_local_candidate"
    platform_ready = observed["request_custody_platform"]["status"] == "required_primitives_available"
    installation_ready = observed.get("serving_installation", {}).get("status") == \
        "installation_root_verified_read_only"
    if not config_ready or not history_ready or not platform_ready or not installation_ready:
        status = "preflight_blocked"
    elif not artifact_ready:
        status = observed.get("explicit_model_artifact", {}).get("status", "awaiting_artifact")
    else:
        status = "ready_for_operator_review"
    findings["status"] = status
    findings["trial_execution_ready"] = False
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path,
        help="exact resident cognition configuration file")
    parser.add_argument("--model-path", required=True, type=Path,
        help="one exact operator-selected local GGUF file")
    parser.add_argument("--allowed-root", required=True, type=Path,
        help="explicit root authorized for the selected artifact")
    parser.add_argument("--serving-config", type=Path,
        help="explicit serving config used to validate the installation identity/root")
    args = parser.parse_args()
    result = inspect_readiness(args.config, args.model_path, args.allowed_root,
        serving_config_path=args.serving_config)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ready_for_operator_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
