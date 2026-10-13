#!/usr/bin/env python3
"""Read-only prerequisite report for one staged resident history experiment.

This command inspects only operator-selected paths. It never invokes a model,
downloads an artifact, writes custody, admits a call, or activates serving.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.local_model_commissioning import inspect_artifact
from sentientos.resident_developmental_cognition import (
    ResidentDevelopmentalCognitionError,
    load_config as load_cognition_config,
)
from sentientos.resident_developmental_writeback import DevelopmentalHistoryStore


def inspect_readiness(config_path: Path, model_path: Path,
                      allowed_root: Path) -> dict[str, Any]:
    findings: dict[str, Any] = {
        "schema_version": "sentientos.resident_objective_experiment_readiness:v1",
        "readiness_scope": "read_only_preflight_not_execution_readiness",
        "source_contracts": {
            "resident_configuration": "sentientos.resident_developmental_cognition_config",
            "history_custody": "DevelopmentalHistoryStore.records",
            "artifact_inspection": "sentientos.local_model_commissioning.inspect_artifact",
        },
        "authority_effect_posture": {
            "model_generation": False, "model_download": False,
            "serving_activation": False, "inference_admission": False,
            "authority_granted": False,
        },
        "findings": {},
        "unobserved_runtime_gates": [
            "daemon_world_state_and_tick_not_observed",
            "resident_invoker_model_identity_not_observed",
            "per_call_local_model_inference_admission_not_requested",
            "objective_task_history_and_current_context_contamination_review_required",
            "effective_generation_budget_not_observed_at_daemon_runtime",
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
            records = DevelopmentalHistoryStore(config.history_root).records()
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
        "status": "supported" if os.name == "posix" else "unsupported",
        "reason_code": None if os.name == "posix" else "resident_request_publisher_posix_only",
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
    platform_ready = observed["request_custody_platform"]["status"] == "supported"
    if not config_ready or not history_ready or not platform_ready:
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
    args = parser.parse_args()
    result = inspect_readiness(args.config, args.model_path, args.allowed_root)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "ready_for_operator_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
