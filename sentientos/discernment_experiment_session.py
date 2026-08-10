from __future__ import annotations

"""Fail-closed custody for one explicitly operated live discernment experiment."""

from importlib.util import find_spec
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from .discernment_calibration import (
    DiscernmentCalibrationRunner,
    calibration_doctor,
    canonical_calibration_corpus,
    validate_calibration_artifacts,
)
from .discernment_participant import live_discernment_readiness
from .governed_local_model_invocation import GovernedLocalModelInvoker
from .local_model import LocalModel, ModelLoadError
from .local_model_authority import LocalModelAuthorityMap, digest_payload
from .local_model_commissioning import FILES as COMMISSIONING_FILES
from .local_model_commissioning import _config_from_mapping, _preview, verify_bundle

SCHEMA = "sentientos.discernment_experiment_session:v1"
PURPOSE = "discernment_judgment"
FILES = {
    "manifest": "session-manifest.json",
    "commissioning": "commissioning-binding.json",
    "load": "load-verification-binding.json",
    "readiness": "readiness-report.json",
    "calibration": "calibration-binding.json",
    "summary": "session-summary.json",
    "handoff": "trial-handoff.json",
}
NO_AUTHORITY = {key: False for key in (
    "provider_network_invocation", "tool_execution", "memory_mutation", "goal_mutation",
    "action_execution", "repository_mutation", "git_mutation", "trial_creation",
    "trial_enrollment", "participant_registration", "trial_judgment_submission",
    "adoption", "authority_grant",
)}


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode()


def _digest(value: Any) -> str:
    result: str = digest_payload(value)
    return result


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("artifact_object_required")
    return value


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_canonical(value))


def _external_root(root: Path) -> Path:
    repo = Path(__file__).resolve().parents[1]
    target = root.absolute()
    if target == repo or repo in target.parents:
        raise ValueError("session_state_inside_repository")
    if target.exists() and (target.is_symlink() or not target.is_dir()):
        raise ValueError("session_state_root_unsafe")
    return target


def _commissioning_values(root: Path) -> dict[str, dict[str, Any]]:
    return {key: _read(root / name) for key, name in COMMISSIONING_FILES.items()}


def _blocked(status: str, *reasons: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA + ".result", "status": status,
            "reason_codes": sorted(set(reasons)), "semantic_model_generations": 0,
            "calibration_cases_run": 0, "authority_effect_posture": dict(NO_AUTHORITY)}


def plan_session(commissioning_root: Path, session_root: Path, calibration_root: Path,
                 *, intended_purpose: str = PURPOSE,
                 corpus: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Bind a verified commissioning bundle without loading or generating."""
    root = _external_root(session_root)
    calibration = _external_root(calibration_root)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError("session_state_no_clobber")
    verified = verify_bundle(commissioning_root)
    if verified.get("bundle_valid") is not True:
        return _blocked("commissioning_blocked", *verified.get("reason_codes", ["commissioning_invalid"]))
    values = _commissioning_values(commissioning_root)
    artifact, authority, handoff = values["artifact"], values["authority"], values["handoff"]
    corpus_value = canonical_calibration_corpus((corpus or {}).get("cases") if corpus else None)
    identity_fields = {
        "session_schema_version": SCHEMA,
        "commissioning_manifest_digest": values["manifest"]["manifest_digest"],
        "model_content_sha256": artifact["model_content_sha256"],
        "artifact_size_bytes": artifact["artifact_size_bytes"],
        "sidecar_metadata_digest": artifact["sidecar_metadata_digest"],
        "configuration_digest": artifact["configuration_digest"],
        "model_id": authority["record"]["model_id"],
        "authority_map_digest": authority["map_digest"],
        "candidate_index": authority["record"]["observed_metadata"]["candidate_index"],
        "resolved_artifact_path": artifact["resolved_path"],
        "intended_invocation_purpose": intended_purpose,
        "calibration_corpus_schema": corpus_value["schema_version"],
        "calibration_corpus_digest": corpus_value["corpus_digest"],
        "production_posture": "production" if authority["record"]["disposition"] == "production_candidate" else "ineligible",
        "fallback": authority["record"]["disposition"] != "production_candidate",
    }
    if intended_purpose != PURPOSE or identity_fields["candidate_index"] != 0:
        return _blocked("commissioning_blocked", "calibration_target_or_candidate_mismatch")
    if identity_fields["fallback"] or identity_fields["production_posture"] != "production":
        return _blocked("commissioning_blocked", "production_non_fallback_identity_required")
    session_id = _digest(identity_fields)
    manifest = {"schema_version": SCHEMA + ".manifest", "session_id": session_id,
                "identity_fields": identity_fields, "commissioning_root": str(commissioning_root.absolute()),
                "calibration_root": str(calibration), "model_bytes_copied": False,
                "authority_effect_posture": dict(NO_AUTHORITY)}
    manifest["manifest_digest"] = _digest(manifest)
    binding = {"schema_version": SCHEMA + ".commissioning-binding", "session_id": session_id,
               "commissioning_manifest_digest": values["manifest"]["manifest_digest"],
               "commissioning_artifact_digests": values["manifest"]["artifact_digests"],
               "commissioning_handoff_digest": handoff["handoff_digest"],
               "configuration_digest": artifact["configuration_digest"],
               "authority_map_digest": authority["map_digest"], "verified": True,
               "authority_effect_posture": dict(NO_AUTHORITY)}
    binding["binding_digest"] = _digest(binding)
    root.mkdir(mode=0o700, parents=True)
    _write_once(root / FILES["manifest"], manifest)
    _write_once(root / FILES["commissioning"], binding)
    return {"status": "planned", "session_id": session_id, "session_root": str(root),
            "semantic_model_generations": 0, "calibration_cases_run": 0,
            "authority_effect_posture": dict(NO_AUTHORITY)}


def _reconstruct(session_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], Any, LocalModelAuthorityMap]:
    root = _external_root(session_root)
    manifest = _read(root / FILES["manifest"])
    supplied = manifest.get("manifest_digest")
    if supplied != _digest({k: v for k, v in manifest.items() if k != "manifest_digest"}):
        raise ValueError("session_manifest_digest_mismatch")
    if manifest.get("session_id") != _digest(manifest.get("identity_fields")):
        raise ValueError("session_identity_mismatch")
    commissioning_root = Path(str(manifest["commissioning_root"]))
    verified = verify_bundle(commissioning_root)
    if verified.get("bundle_valid") is not True:
        raise ValueError("commissioning_bundle_no_longer_valid")
    values = _commissioning_values(commissioning_root)
    binding = _read(root / FILES["commissioning"])
    if binding.get("binding_digest") != _digest({k: v for k, v in binding.items() if k != "binding_digest"}):
        raise ValueError("commissioning_binding_digest_mismatch")
    fields = manifest["identity_fields"]
    artifact, preview = values["artifact"], values["authority"]
    checks = {
        "commissioning_manifest_digest": values["manifest"]["manifest_digest"],
        "model_content_sha256": artifact["model_content_sha256"],
        "artifact_size_bytes": artifact["artifact_size_bytes"],
        "sidecar_metadata_digest": artifact["sidecar_metadata_digest"],
        "configuration_digest": artifact["configuration_digest"], "model_id": preview["record"]["model_id"],
        "authority_map_digest": preview["map_digest"],
        "candidate_index": preview["record"]["observed_metadata"]["candidate_index"],
        "resolved_artifact_path": artifact["resolved_path"],
        "production_posture": "production" if preview["record"]["disposition"] == "production_candidate" else "ineligible",
        "fallback": preview["record"]["disposition"] != "production_candidate",
    }
    if any(fields.get(key) != value for key, value in checks.items()):
        raise ValueError("session_commissioning_identity_mismatch")
    config = _config_from_mapping(values["config"])
    authority, expected_preview = _preview(config, Path(str(artifact["authorized_root"])))
    if expected_preview != preview:
        raise ValueError("authority_preview_mismatch")
    return manifest, values, config, authority


def _load_exact(config: Any, authority: LocalModelAuthorityMap) -> tuple[LocalModel | None, dict[str, Any]]:
    if find_spec("llama_cpp") is None:
        return None, _blocked("external_prerequisite_unavailable", "llama_cpp_dependency_unavailable")
    try:
        candidate = config.candidates[0]
        backend, metadata = LocalModel._initialise_backend(candidate, config)
        identity = LocalModel._identity_for(candidate, config, backend, metadata, 0)
        model = LocalModel(backend, backend.metadata, config, backend, identity)
        record = authority.record_for_active_identity(model.active_identity, PURPOSE)
    except (ModelLoadError, OSError) as exc:
        return None, _blocked("external_prerequisite_unavailable", str(exc))
    if record is None:
        return None, _blocked("commissioning_blocked", "active_identity_authority_mismatch")
    proof = {"schema_version": SCHEMA + ".load-verification-binding",
             "status": "load_verified", "process_real": True,
             "active_model_identity": identity.to_dict(), "authority_record": record.to_dict(),
             "authority_map_digest": authority.map_digest,
             "configuration_digest": identity.configuration_digest,
             "model_content_sha256": identity.model_content_sha256,
             "resolved_artifact_path": identity.resolved_artifact_path,
             "candidate_index": identity.candidate_index, "production_posture": identity.posture,
             "fallback": identity.fallback, "verification_result": "exact_match",
             "semantic_model_generations": 0, "authority_effect_posture": dict(NO_AUTHORITY)}
    proof["proof_digest"] = _digest(proof)
    return model, proof


def verify_load(session_root: Path) -> dict[str, Any]:
    """Create a durable process-real load receipt through ``LocalModel``; no generation."""
    root = _external_root(session_root)
    try:
        _, _, config, authority = _reconstruct(root)
        if (root / FILES["load"]).exists():
            return verify_session(root)
        _, proof = _load_exact(config, authority)
        if proof.get("status") != "load_verified":
            return proof
        _write_once(root / FILES["load"], proof)
        return proof
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return _blocked("commissioning_blocked", str(exc))


def _verified_loaded_model(session_root: Path) -> tuple[LocalModel, dict[str, Any], LocalModelAuthorityMap]:
    manifest, _, config, authority = _reconstruct(session_root)
    receipt = _read(session_root / FILES["load"])
    if receipt.get("proof_digest") != _digest({k: v for k, v in receipt.items() if k != "proof_digest"}):
        raise ValueError("load_proof_digest_mismatch")
    model, fresh = _load_exact(config, authority)
    if model is None or fresh.get("status") != "load_verified":
        raise ValueError("process_real_load_no_longer_available")
    for key in ("active_model_identity", "authority_record", "authority_map_digest", "configuration_digest",
                "model_content_sha256", "resolved_artifact_path", "candidate_index", "production_posture", "fallback"):
        if receipt.get(key) != fresh.get(key):
            raise ValueError("load_proof_identity_mismatch")
    return model, manifest, authority


def doctor(session_root: Path) -> dict[str, Any]:
    """Evaluate every live gate without running a calibration case or generation."""
    root = _external_root(session_root)
    try:
        model, manifest, authority = _verified_loaded_model(root)
        calibration_root = Path(str(manifest["calibration_root"]))
        calibration_report = calibration_doctor(model=model, authority_map=authority,
                                                runtime_root=calibration_root)
        readiness = live_discernment_readiness(model, authority)
        gates = {
            "commissioning_bundle_valid": True, "model_artifact_still_identical": True,
            "configuration_still_identical": True, "authority_preview_eligible": True,
            "llama_cpp_dependency_present": True, "process_real_load_verification_available_and_exact": True,
            "active_model_identity_matches_authority_record": readiness["matching_authority_record"] is not None,
            "live_discernment_readiness_succeeds": readiness["ready_for_live_discernment"],
            "calibration_handoff_valid": True,
            "eligible_for_explicit_live_calibration": calibration_report["live_calibration_could_begin"],
        }
        report = {"schema_version": SCHEMA + ".readiness", "status": "calibration_eligible" if all(gates.values()) else "commissioning_blocked",
                  "session_id": manifest["session_id"], "gates": gates,
                  "participant_readiness": readiness, "calibration_doctor": calibration_report,
                  "semantic_model_generations": 0, "calibration_cases_run": 0,
                  "authority_effect_posture": dict(NO_AUTHORITY)}
        report["report_digest"] = _digest(report)
        if not (root / FILES["readiness"]).exists():
            _write_once(root / FILES["readiness"], report)
        elif _read(root / FILES["readiness"]) != report:
            return _blocked("commissioning_blocked", "readiness_receipt_changed")
        return report
    except FileNotFoundError as exc:
        status = "external_prerequisite_unavailable" if not (root / FILES["load"]).exists() else "commissioning_blocked"
        return _blocked(status, str(exc))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return _blocked("commissioning_blocked", str(exc))


def _calibration_artifacts(calibration_root: Path) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    runs = sorted(path for path in calibration_root.glob("calibration-*") if path.is_dir())
    if len(runs) != 1:
        raise ValueError("calibration_custody_missing_or_ambiguous")
    run = runs[0]
    required = (run / "manifest.json", run / "corpus.json", run / "handoff.json", run / "validation.json")
    if not all(path.is_file() for path in required):
        raise ValueError("calibration_custody_partial_or_corrupt")
    manifest, corpus, handoff, saved_validation = (_read(path) for path in required)
    validation = validate_calibration_artifacts(manifest, corpus, handoff)
    if not validation.get("valid") or saved_validation != validation:
        raise ValueError("calibration_validation_failed")
    return run, manifest, handoff, validation


def _bind_calibration(root: Path, session_manifest: Mapping[str, Any]) -> dict[str, Any]:
    run, manifest, handoff, validation = _calibration_artifacts(Path(str(session_manifest["calibration_root"])))
    fields = session_manifest["identity_fields"]
    if manifest.get("evidence_mode") != "live" or manifest.get("active_model_identity", {}).get("configuration_digest") != fields["configuration_digest"]:
        raise ValueError("calibration_session_identity_mismatch")
    if manifest.get("authority_map_digest") != fields["authority_map_digest"] or manifest.get("corpus_identity", {}).get("corpus_digest") != fields["calibration_corpus_digest"]:
        raise ValueError("calibration_authority_or_corpus_mismatch")
    binding = {"schema_version": SCHEMA + ".calibration-binding", "session_id": session_manifest["session_id"],
               "calibration_run_path": str(run), "calibration_run_id": manifest["manifest_digest"],
               "calibration_run_digest": _digest(manifest), "corpus_identity": manifest["corpus_identity"],
               "active_model_identity": manifest["active_model_identity"],
               "authority_map_digest": manifest["authority_map_digest"], "summary_counts": manifest["summary"],
               "repeat_semantics": {"comparison_count": manifest["summary"]["deterministic_repeat_comparison_count"],
                                    "match_count": manifest["summary"]["repeat_semantic_match_count"],
                                    "mismatch_count": manifest["summary"]["repeat_semantic_mismatch_count"]},
               "readiness_classification": manifest["summary"]["readiness_classification"],
               "validation_report_digest": _digest(validation), "calibration_handoff_digest": handoff["handoff_digest"],
               "authority_effect_posture": dict(NO_AUTHORITY)}
    binding["binding_digest"] = _digest(binding)
    if (root / FILES["calibration"]).exists():
        if _read(root / FILES["calibration"]) != binding:
            raise ValueError("calibration_binding_changed")
    else:
        _write_once(root / FILES["calibration"], binding)
    return binding


def calibrate(session_root: Path, *, repo_root: Path,
              runner_factory: Callable[..., DiscernmentCalibrationRunner] = DiscernmentCalibrationRunner) -> dict[str, Any]:
    """Run the canonical calibration runner only after an explicit operator action."""
    root = _external_root(session_root)
    try:
        manifest = _read(root / FILES["manifest"])
        calibration_root = Path(str(manifest["calibration_root"]))
        if list(calibration_root.glob("calibration-*")):
            binding = _bind_calibration(root, manifest)
            return {"status": binding["readiness_classification"], "resumed_without_generation": True,
                    "calibration_binding": binding, "authority_effect_posture": dict(NO_AUTHORITY)}
        readiness = doctor(root)
        if readiness.get("status") != "calibration_eligible":
            return _blocked(str(readiness.get("status", "commissioning_blocked")), "pre_calibration_gates_not_satisfied")
        model, manifest, authority = _verified_loaded_model(root)
        invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
                                            runtime_root=calibration_root / "invocations")
        runner = runner_factory(repo_root, calibration_root, model, authority, invoker)
        runner.run(corpus=canonical_calibration_corpus())
        binding = _bind_calibration(root, manifest)
        return {"status": binding["readiness_classification"], "resumed_without_generation": False,
                "calibration_binding": binding, "authority_effect_posture": dict(NO_AUTHORITY)}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, FileExistsError) as exc:
        return _blocked("calibration_blocked", str(exc))


def verify_session(session_root: Path) -> dict[str, Any]:
    """Reconstruct state from evidence; never loads or generates."""
    root = _external_root(session_root)
    try:
        manifest, _, _, _ = _reconstruct(root)
        state = "planned"
        if (root / FILES["load"]).exists():
            receipt = _read(root / FILES["load"])
            if receipt.get("proof_digest") != _digest({k: v for k, v in receipt.items() if k != "proof_digest"}):
                raise ValueError("load_proof_digest_mismatch")
            state = "load_verified"
        if (root / FILES["readiness"]).exists():
            readiness = _read(root / FILES["readiness"])
            if readiness.get("report_digest") != _digest({k: v for k, v in readiness.items() if k != "report_digest"}):
                raise ValueError("readiness_report_digest_mismatch")
            state = str(readiness["status"])
        if Path(str(manifest["calibration_root"])).exists() and list(Path(str(manifest["calibration_root"])).glob("calibration-*")):
            binding = _bind_calibration(root, manifest)
            state = str(binding["readiness_classification"])
        result = {"schema_version": SCHEMA + ".summary", "status": state,
                  "session_id": manifest["session_id"], "evidence_files": sorted(path.name for path in root.iterdir()),
                  "semantic_model_generations": 0, "calibration_cases_run": 0,
                  "authority_effect_posture": dict(NO_AUTHORITY)}
        result["summary_digest"] = _digest(result)
        if state in {"calibration_ready", "calibration_degraded", "calibration_blocked", "calibration_unavailable"} and not (root / FILES["summary"]).exists():
            _write_once(root / FILES["summary"], result)
        return result
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return _blocked("commissioning_blocked", str(exc))


def trial_handoff(session_root: Path) -> dict[str, Any]:
    """Emit review metadata only; never calls ``BlindTrialCustody``."""
    root = _external_root(session_root)
    try:
        manifest = _read(root / FILES["manifest"])
        binding = _bind_calibration(root, manifest)
        if binding["readiness_classification"] != "calibration_ready":
            return _blocked(str(binding["readiness_classification"]), "validated_calibration_ready_required")
        handoff = {"schema_version": SCHEMA + ".trial-handoff", "status": "trial_handoff_ready",
                   "session_id": manifest["session_id"], "model_id": manifest["identity_fields"]["model_id"],
                   "active_model_identity": binding["active_model_identity"],
                   "calibration_binding_digest": binding["binding_digest"],
                   "operator_consideration_only": True, "blind_trial_custody_action_required": True,
                   "authority_effect_posture": dict(NO_AUTHORITY)}
        handoff["handoff_digest"] = _digest(handoff)
        if (root / FILES["handoff"]).exists():
            if _read(root / FILES["handoff"]) != handoff:
                raise ValueError("trial_handoff_changed")
        else:
            _write_once(root / FILES["handoff"], handoff)
        return handoff
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return _blocked("calibration_blocked", str(exc))


__all__ = ["FILES", "NO_AUTHORITY", "SCHEMA", "plan_session", "verify_load", "doctor",
           "calibrate", "verify_session", "trial_handoff"]
