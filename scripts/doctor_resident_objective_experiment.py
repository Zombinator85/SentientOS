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
from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionVerifier
from sentientos.platform_fcntl import FLOCK_SUPPORTED


def _custody_status(os_name: str, primitives: dict[str, bool]) -> str:
    if os_name != "posix":
        return "unsupported_by_current_experiment_custody"
    if all(primitives.values()):
        return "required_posix_primitives_available_filesystem_unverified"
    return "required_posix_primitive_missing"


def _next_operator_actions(findings: dict[str, Any], status: str) -> list[str]:
    """Return bounded actions that preserve the existing runtime gates."""
    actions: list[str] = []
    platform_finding = findings.get("request_custody_platform", {})
    if platform_finding.get("status") != "required_primitives_available":
        actions.append("Run the daemon and all experiment commands inside one supported POSIX installation; do not copy custody between Windows and WSL.")
    config = findings.get("resident_configuration", {})
    if config.get("status") != "enabled":
        actions.append("Resolve the explicitly selected resident-cognition configuration before staging any objective request.")
    history = findings.get("developmental_history", {})
    if history.get("status") == "awaiting_eligible_history":
        actions.append("Wait for an ordinary configured cognition tick to consume a real allowed World-State task/outcome fact; do not seed or hand-edit history.")
    elif history.get("status") == "invalid_custody":
        actions.append("Inspect the reported history custody reason; use only the existing owner recovery path for an interrupted write, and do not hand-edit records or receipts.")
    serving = findings.get("serving_installation", {})
    if serving.get("status") == "awaiting_explicit_serving_configuration":
        actions.append("Rerun the doctor with --serving-config pointing to the exact serving configuration used by this installation.")
    elif serving.get("status") != "installation_root_verified_read_only":
        actions.append("Resolve the exact selected serving installation identity/root; do not infer it from another process or copy installation state.")
    artifact = findings.get("explicit_model_artifact", {})
    if artifact.get("status") in {"awaiting_artifact", "invalid_custody", "runtime_incompatible"}:
        actions.append("Select an already available supported model artifact within the explicitly allowed root; the doctor will not download or load it.")
    if status == "ready_for_operator_review":
        actions.append("Review task/history contamination and the live tick, loaded model, generation budget, and per-call admission; only then consider the existing one-shot staging command under its independent gates.")
    return actions


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
            "history_custody": "ResidentDevelopmentalWritebackController.inspect_completed_records",
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
            "configured_history_root": str(config.history_root),
            "configured_state_root": str(config.state_root),
        }
        if not config.enabled or not config.comparison_enabled:
            findings["findings"]["resident_configuration"]["reason_code"] = "history_comparison_not_enabled"
        try:
            ledger = AdmissionLedger(config.state_root / "runtime_admissions.json")
            definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
                RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
            writeback = ResidentDevelopmentalWritebackController(
                history_root=config.history_root,
                admission_verifier=RuntimeAdmissionVerifier(
                    definitions=definitions, ledger=ledger),
                current_sequence=ledger.current_sequence)
            recovered = writeback.inspect_completed_records()
            records = tuple(record for record, _receipt in recovered)
            history_status = "eligible_history_present" if records else "awaiting_eligible_history"
            findings["findings"]["developmental_history"] = {
                "status": history_status, "verified_record_count": len(records),
                "maximum_reported_records": min(len(records), config.max_retrieved_records),
                "admission_validation": "verified_read_only",
                "runtime_recovery_validation": "verified_read_only_no_repair",
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
        installation_identity: str | None = None
        installation_state_root: Path | None = None
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
                installation_identity = identity.value
                installation_state_root = registry.state_root_for(identity)
                registry.open_read_only(identity)
                findings["findings"]["serving_installation"] = {
                    "status": "installation_root_verified_read_only",
                    "installation_identity": identity.value,
                    "installation_state_root": str(installation_state_root),
                    "installation_root_custody": "verified_read_only",
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
                **({"configured_installation_identity": installation_identity}
                    if installation_identity is not None else {}),
                **({"expected_installation_state_root": str(installation_state_root),
                    "installation_root_custody": "not_verified"}
                    if installation_state_root is not None else {}),
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
    history_ready = observed.get("developmental_history", {}).get("status") == \
        "eligible_history_present"
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
    findings["next_operator_actions"] = _next_operator_actions(observed, status)
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
