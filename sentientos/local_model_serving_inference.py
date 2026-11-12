"""Separately admitted inference against an opaque, current serving lifetime."""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Protocol

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .chat_response_grounding import corrected_gaming_output
from .control_plane_kernel import (
    AdmissionOutcome,
    AuthorityClass,
    ControlActionRequest,
    LifecyclePhase,
)
from .governed_local_model_invocation import (
    GovernedLocalModelInvoker,
    GovernedLocalModelResourceInvocationContext,
    LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
    MAX_INVOCATION_RECEIPT_BYTES,
    MAX_INVOCATION_RECEIPTS,
    validate_receipt,
)
from .local_model_authority import LocalModelAuthorityMap, build_local_model_authority_map, digest_payload
from .local_model_resource_profile import (
    LocalModelResourceProfileError,
    llama_cpp_resource_profile_digest,
    validate_llama_cpp_resource_profile,
)
from .installation_state import InstallationStateError
from .gaming_workload_policy import EffectiveWorkloadMode, GamingWorkloadPolicy, WorkloadMode
from .foreground_game_detection import (
    ForegroundGameDetector,
    ForegroundGameObservation,
    normalize_game_process_names,
)
from .chat_process_generation import (
    ChatProcessGenerationError,
    verify_current_chat_process_handoff,
    verify_stored_chat_process_handoff,
)
from .local_model_production_serving import (
    ProductionServingController,
    ProductionServingError,
    ServingSession,
    read_serving_operation_history,
)
from .host_resource_runtime import (
    HostResourceRuntimeCoordinator,
    validate_evaluation as validate_host_resource_evaluation,
)
from .host_resource_governor import ACTIONABLE_RESOURCE_PRESSURE_LABELS


class ProductionServingInferenceError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ForegroundGameObserver(Protocol):
    def observe(self, process_names: tuple[str, ...] | list[str]) -> ForegroundGameObservation: ...


def unavailable_chat_process_software_generation() -> dict[str, Any]:
    """Describe the unimplemented chat-process generation issuer without inferring one."""
    return {
        "status": "unavailable",
        "reason_code": "authenticated_chat_process_generation_issuer_not_composed",
        "generation_identity": None,
        "process_instance_id": None,
    }


class ProductionServingInferenceController:
    """Narrow bridge; callers provide an operation, never a model or its custody."""

    __slots__ = ("_serving", "_runtime_handoff_id", "_receipt_capacity_lock",
                 "_workload_lock", "_workload_mode", "_game_process_names",
                 "_foreground_game_detector", "_host_resource_observation_owner")

    def __init__(self, serving_controller: ProductionServingController, *,
                 runtime_handoff_id: str | None = None,
                 foreground_game_detector: ForegroundGameObserver | None = None,
                 host_resource_observation_owner: HostResourceRuntimeCoordinator | None = None) -> None:
        if not isinstance(serving_controller, ProductionServingController):
            raise ProductionServingInferenceError("production_serving_controller_required")
        if (host_resource_observation_owner is not None
                and type(host_resource_observation_owner) is not HostResourceRuntimeCoordinator):
            raise ProductionServingInferenceError("exact_host_resource_observation_owner_required")
        self._serving = serving_controller
        self._runtime_handoff_id = runtime_handoff_id
        self._receipt_capacity_lock = threading.Lock()
        self._workload_lock = threading.Lock()
        self._workload_mode: WorkloadMode = "normal"
        self._game_process_names: tuple[str, ...] = ()
        self._foreground_game_detector = foreground_game_detector or ForegroundGameDetector()
        self._host_resource_observation_owner = host_resource_observation_owner

    def _observe_host_resources(self, correlation_id: str, *,
                                observation_namespace: str = "local-chat-inference") -> dict[str, Any]:
        owner = self._host_resource_observation_owner
        observation_id = observation_namespace + "-" + hashlib.sha256(
            correlation_id.encode("utf-8")).hexdigest()[:32]
        if owner is None:
            return {"schema_version": "sentientos.production_chat_host_resource_observation:v1",
                    "status": "not_configured", "observation_correlation_id": observation_id,
                    "no_effect_authority": True}
        try:
            evaluation = owner.run_cycle(correlation_id=observation_id)
        except Exception as exc:
            return {"schema_version": "sentientos.production_chat_host_resource_observation:v1",
                    "status": "unavailable", "observation_correlation_id": observation_id,
                    "reason_code": "collector_owner_error_" + type(exc).__name__,
                    "no_effect_authority": True}
        if evaluation is None:
            return {"schema_version": "sentientos.production_chat_host_resource_observation:v1",
                    "status": "unavailable", "observation_correlation_id": observation_id,
                    "reason_code": "observation_not_admitted",
                    "no_effect_authority": True}
        validation = validate_host_resource_evaluation(evaluation)
        if not validation.ok or not evaluation.no_effect_authority:
            return {"schema_version": "sentientos.production_chat_host_resource_observation:v1",
                    "status": "invalid", "observation_correlation_id": observation_id,
                    "reason_code": "observation_validation_failed",
                    "no_effect_authority": True}
        return {
            "schema_version": "sentientos.production_chat_host_resource_observation:v1",
            "status": "current", "evaluation_id": evaluation.evaluation_id,
            "observation_correlation_id": evaluation.epoch.correlation_id,
            "epoch_id": evaluation.epoch.epoch_id, "snapshot_id": evaluation.snapshot.snapshot_id,
            "report_id": evaluation.pressure_report.report_id,
            "report_digest": evaluation.policy_decision.report_digest,
            "semantic_digest": evaluation.semantic_digest,
            "observed_at": evaluation.epoch.observed_at,
            "pressure_labels": list(evaluation.pressure_report.pressure_labels),
            "cpu_utilization_percent": evaluation.snapshot.cpu_utilization_percent,
            "ram_utilization_percent": evaluation.snapshot.ram_utilization_percent,
            "gpu_utilization_percent": evaluation.snapshot.gpu_utilization_percent,
            "vram_utilization_percent": evaluation.snapshot.vram_utilization_percent,
            "gpu_telemetry_sources": [
                {"collector_id": result.collector_id, "status": result.status,
                 "source": result.source[:128]}
                for result in evaluation.epoch.results
                if result.collector_id == "nvidia_gpu"
            ],
            "gpu_telemetry_available": (
                evaluation.snapshot.gpu_utilization_percent is not None
                or evaluation.snapshot.vram_utilization_percent is not None),
            "gpu_telemetry_complete": (
                evaluation.snapshot.gpu_utilization_percent is not None
                and evaluation.snapshot.vram_utilization_percent is not None),
            "no_effect_authority": True,
        }

    def set_workload_mode(self, mode: str,
                          game_process_names: tuple[str, ...] | list[str] = ()) -> WorkloadMode:
        """Set a process-local chat budget mode; this grants no host authority."""
        validated = GamingWorkloadPolicy.validate_mode(mode)
        names = (normalize_game_process_names(game_process_names)
                 if validated == "automatic" else ())
        with self._workload_lock:
            self._workload_mode = validated
            self._game_process_names = names
        return validated

    def current_workload_mode(self) -> WorkloadMode:
        with self._workload_lock:
            return self._workload_mode

    def current_workload_state(self) -> dict[str, Any]:
        with self._workload_lock:
            configured_mode = self._workload_mode
            names = self._game_process_names
        if configured_mode != "automatic":
            effective: EffectiveWorkloadMode = configured_mode
            evidence: dict[str, Any] = {
                "configured_mode": configured_mode,
                "mode_source": "operator_selected",
                "observation_status": "not_requested",
                "game_foreground": None,
                "process_name_digest": None,
                "observed_at": None,
                "transport_provenance": None,
            }
        else:
            observed = self._foreground_game_detector.observe(names)
            if observed.status == "available":
                if observed.game_foreground is True:
                    effective, source = "gaming", "foreground_allowlist_match"
                elif observed.game_process_running is True:
                    effective, source = "gaming", "allowlisted_game_process_running"
                elif observed.game_process_running is False:
                    effective, source = "normal", "foreground_allowlist_no_match"
                else:
                    effective, source = "gaming", "game_process_observation_unavailable_conservative_gaming"
            else:
                # If automatic detection is unavailable, keep the safer low-work profile.
                effective = "gaming"
                source = "foreground_observation_unavailable_conservative_gaming"
            evidence = {
                "configured_mode": "automatic", "mode_source": source,
                "observation_status": observed.status,
                "game_foreground": observed.game_foreground,
                "game_process_running": observed.game_process_running,
                "running_process_name_digests": (
                    list(observed.running_process_name_digests)
                    if observed.running_process_name_digests is not None else None),
                "process_name_digest": observed.process_name_digest,
                "observed_at": observed.observed_at,
                "transport_provenance": (dict(observed.transport_provenance)
                    if observed.transport_provenance is not None else None),
            }
        state = {"mode": configured_mode, "effective_mode": effective, **evidence}
        if configured_mode == "automatic":
            state["configured_game_process_names"] = list(names)
        return state

    def _software_generation_attribution(self) -> dict[str, Any]:
        if self._runtime_handoff_id is None:
            return unavailable_chat_process_software_generation()
        try:
            return verify_current_chat_process_handoff(
                handle=self._serving._handle, handoff_id=self._runtime_handoff_id)
        except ChatProcessGenerationError as exc:
            raise ProductionServingInferenceError("chat_process_generation_handoff_invalid") from exc

    def current_conversation_model_identity(self) -> Mapping[str, Any]:
        """Return stable activation/model provenance, never a worker-lifetime identity."""
        session = self._serving.current_session()
        if session is None:
            raise ProductionServingInferenceError("current_serving_session_required")
        binding = session.binding
        return {
            key: binding[key]
            for key in (
                "installation_identity", "activation_state_semantic_digest", "activation_generation",
                "activation_predecessor_state_digest",
                "activation_receipt_id", "activation_receipt_semantic_digest", "model_id",
                "observed_loaded_model_identity", "artifact_id", "artifact_sha256",
                "runtime_id", "authority_map_digest", "serving_receipt_id",
                "serving_receipt_semantic_digest", "serving_operation_attempt_id",
                "serving_operation_attempt_semantic_digest",
            )
        }

    @staticmethod
    def _authority(session: ServingSession) -> LocalModelAuthorityMap:
        binding = session.binding
        load = binding["load_configuration"]
        candidate_options: dict[str, Any] = {"gpu_layers": int(load["n_gpu_layers"])}
        profile = load.get("resource_profile")
        if profile is not None:
            try:
                profile = validate_llama_cpp_resource_profile(profile)
            except LocalModelResourceProfileError as exc:
                raise ProductionServingInferenceError("serving_resource_profile_invalid") from exc
            profile_digest = llama_cpp_resource_profile_digest(profile)
            if (load.get("resource_profile_digest") != profile_digest
                    or profile["n_ctx"] != int(load["n_ctx"])
                    or profile["n_gpu_layers"] != int(load["n_gpu_layers"])
                    or ("n_threads" in load and load["n_threads"] != profile["n_threads"])):
                raise ProductionServingInferenceError("serving_resource_profile_mismatch")
            candidate_options["resource_profile_digest"] = profile_digest
            for name in ("n_threads", "n_threads_batch", "n_batch", "n_ubatch"):
                if profile[name]:
                    candidate_options[name] = profile[name]
        config = ModelConfig(
            [ModelCandidate(Path(str(binding["artifact_path"])), "llama_cpp", str(binding["model_id"]),
                            candidate_options)],
            default_engine="llama_cpp",
            max_context_tokens=int(load["n_ctx"]),
            generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1),
        )
        authority = build_local_model_authority_map(
            config, allowed_roots=[Path(str(binding["artifact_path"])).parent],
            observed_at="1970-01-01T00:00:00+00:00")
        if authority.map_digest != binding["authority_map_digest"]:
            raise ProductionServingInferenceError("serving_authority_map_digest_mismatch")
        return authority

    def _release_after_host_pressure(
            self, session: ServingSession, model: Any,
            receipt: LocalModelInvocationReceipt | None,
            *, resource_observation: Mapping[str, Any] | None = None,
            workload_evidence: Mapping[str, Any] | None = None,
            trigger_correlation_id: str | None = None,
            trigger_kind: str = "deferred_inference") -> dict[str, Any] | None:
        """Release optional chat residency after exact game/profile and host evidence."""
        if receipt is not None:
            if (receipt.status != "deferred"
                    or not any(reason.endswith(
                        "deferred_local_model_inference_under_host_pressure_during_game")
                        for reason in receipt.reason_codes)):
                return None
            request_linkage = receipt.request.get("linkage")
            if not isinstance(request_linkage, Mapping):
                return None
            resource_observation = request_linkage.get("host_resource_observation")
            workload_evidence = request_linkage.get("workload_evidence")
            trigger_correlation_id = receipt.request.get("correlation_id")
            trigger_kind = "deferred_inference"
        if not isinstance(resource_observation, Mapping) or not isinstance(workload_evidence, Mapping):
            return None
        selected_gaming_profile = trigger_kind == "gaming_profile_resource_reconciliation"
        if selected_gaming_profile:
            if (workload_evidence.get("configured_mode") != "gaming"
                    or workload_evidence.get("mode_source") != "operator_selected"
                    or workload_evidence.get("observation_status") != "not_requested"):
                return None
            game_message_id = None
        else:
            provenance = workload_evidence.get("transport_provenance")
            if not isinstance(provenance, Mapping):
                return None
            game_message_id = provenance.get("message_id")
        labels = resource_observation.get("pressure_labels")
        if (resource_observation.get("status") != "current"
                or resource_observation.get("no_effect_authority") is not True
                or not isinstance(labels, (tuple, list))
                or not all(isinstance(label, str) for label in labels)
                or not set(labels).intersection(ACTIONABLE_RESOURCE_PRESSURE_LABELS)
                or (not selected_gaming_profile and (
                    workload_evidence.get("observation_status") != "available"
                    or (workload_evidence.get("game_foreground") is not True
                        and workload_evidence.get("game_process_running") is not True)
                    or not isinstance(game_message_id, str)))):
            return None
        if not isinstance(trigger_correlation_id, str) or not trigger_correlation_id:
            return None
        source_correlation = trigger_correlation_id
        release_correlation = "production-chat-resource-release-" + hashlib.sha256(
            (source_correlation if trigger_kind == "deferred_inference" else
             trigger_kind + ":" + source_correlation).encode("utf-8")).hexdigest()[:24]
        loaded_identity = getattr(model, "active_identity", None)
        if loaded_identity is None or not callable(getattr(loaded_identity, "to_dict", None)):
            return None
        host_release_evidence = {
            "schema_version": ("sentientos.production_gaming_profile_host_resource_release_evidence:v1"
                if selected_gaming_profile else
                "sentientos.production_game_host_resource_release_evidence:v1"),
            "trigger_kind": trigger_kind,
            "trigger_correlation_id": source_correlation,
            "observation_correlation_id": resource_observation.get(
                "observation_correlation_id"),
            "host_report_id": resource_observation.get("report_id"),
            "host_report_digest": resource_observation.get("report_digest"),
            "observed_at": resource_observation.get("observed_at"),
            "pressure_labels": list(labels),
        }
        if selected_gaming_profile:
            host_release_evidence.update({
                "workload_mode": "gaming",
                "workload_mode_source": "operator_selected",
                "workload_observation_status": "not_requested",
            })
        else:
            host_release_evidence["game_workload_message_id"] = game_message_id
        reason_code = ("selected_gaming_profile_host_pressure" if selected_gaming_profile
            else "verified_game_host_pressure")
        actor = ("production_chat_workload_resource_governor" if selected_gaming_profile
            else "production_chat_game_resource_governor")
        metadata = {
            "correlation_id": release_correlation,
            "purpose": "local_model_resource_release",
            "reason_code": reason_code,
            "target_subsystem": "production_chat",
            "model_identity_digest": digest_payload(loaded_identity.to_dict()),
            "resource_observation": host_release_evidence,
        }
        decision = self._serving._kernel.admit(ControlActionRequest(
            action_kind="local_model_resource_release",
            authority_class=AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE,
            actor=actor,
            target_subsystem="production_chat",
            requested_phase=LifecyclePhase.RUNTIME,
            metadata=metadata,
        ))
        decision_valid = (
            decision.allowed
            and decision.outcome == AdmissionOutcome.ALLOW
            and decision.authority_class == AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE
            and decision.action_kind == "local_model_resource_release"
            and decision.actor == actor
            and decision.target_subsystem == "production_chat"
            and decision.correlation_id == release_correlation
        )
        close_completed = False
        close_failure: str | None = None
        post_release_observation: dict[str, Any] | None = None
        resource_measurement_comparison: dict[str, Any] | None = None
        worker_exit_observed: bool | None = None
        if decision_valid:
            try:
                close_completed = self._serving.release_current_session_after_resource_admission(
                    session, reason=reason_code)
                worker = getattr(model, "_process", None)
                poll = getattr(worker, "poll", None)
                worker_exit_observed = (poll() is not None if callable(poll) else None)
                if close_completed:
                    post_release_observation = self._observe_host_resources(
                        source_correlation + ":resource-release-postflight")
                    before_gpu = resource_observation.get("gpu_utilization_percent")
                    before_vram = resource_observation.get("vram_utilization_percent")
                    after_gpu = post_release_observation.get("gpu_utilization_percent")
                    after_vram = post_release_observation.get("vram_utilization_percent")

                    def finite_percent(value: object) -> float | None:
                        if (isinstance(value, (int, float)) and not isinstance(value, bool)
                                and math.isfinite(float(value)) and 0 <= float(value) <= 100):
                            return float(value)
                        return None

                    before_gpu_value = finite_percent(before_gpu)
                    before_vram_value = finite_percent(before_vram)
                    after_gpu_value = finite_percent(after_gpu)
                    after_vram_value = finite_percent(after_vram)
                    gpu_delta = (after_gpu_value - before_gpu_value
                        if before_gpu_value is not None and after_gpu_value is not None else None)
                    vram_delta = (after_vram_value - before_vram_value
                        if before_vram_value is not None and after_vram_value is not None else None)
                    resource_measurement_comparison = {
                        "schema_version": "sentientos.resource_measurement_comparison:v1",
                        "status": ("comparable" if gpu_delta is not None or vram_delta is not None
                            else "insufficient_gpu_measurements"),
                        "before": {
                            "host_report_id": host_release_evidence["host_report_id"],
                            "observed_at": host_release_evidence["observed_at"],
                            "gpu_utilization_percent": before_gpu_value,
                            "vram_utilization_percent": before_vram_value,
                            "gpu_telemetry_sources": resource_observation.get(
                                "gpu_telemetry_sources", []),
                        },
                        "after": {
                            "host_report_id": post_release_observation.get("report_id"),
                            "observed_at": post_release_observation.get("observed_at"),
                            "gpu_utilization_percent": after_gpu_value,
                            "vram_utilization_percent": after_vram_value,
                            "gpu_telemetry_sources": post_release_observation.get(
                                "gpu_telemetry_sources", []),
                        },
                        "gpu_utilization_delta_percentage_points": gpu_delta,
                        "vram_utilization_delta_percentage_points": vram_delta,
                        "interpretation": "sample_delta_only; telemetry_does_not_establish_causation",
                    }
            except Exception as exc:
                close_failure = type(exc).__name__
        outcome = {
            "schema_version": "sentientos.production_chat_resource_release_receipt:v2",
            "status": ("worker_closed" if close_completed else
                "release_effect_unconfirmed" if decision_valid else "denied"),
            "trigger_kind": trigger_kind,
            "trigger_correlation_id": source_correlation,
            "source_inference_correlation_id": (source_correlation
                if trigger_kind == "deferred_inference" else None),
            "release_correlation_id": release_correlation,
            "serving_session_id": session.session_id,
            "serving_operation_id": session.binding.get("serving_operation_id"),
            "model_identity_digest": metadata["model_identity_digest"],
            "release_admission_decision_ref": decision.admission_decision_ref,
            "release_admission_outcome": decision.outcome.value,
            "release_reason_codes": list(decision.reason_codes),
            "resource_observation": {
                "observation_correlation_id": host_release_evidence[
                    "observation_correlation_id"],
                "host_report_id": host_release_evidence["host_report_id"],
                "pressure_labels": list(labels),
                **({"workload_mode": "gaming",
                    "workload_mode_source": "operator_selected"}
                    if selected_gaming_profile else
                    {"game_workload_message_id": game_message_id}),
            },
            "worker_exit_observed": worker_exit_observed,
            "close_failure": close_failure,
            "post_release_observation": post_release_observation,
            "resource_measurement_comparison": resource_measurement_comparison,
            "inference_performed": False,
            "host_mutation_performed": False,
        }
        encoded_body = json.dumps(outcome, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
        receipt_id = "serving-resource-release-" + hashlib.sha256(encoded_body).hexdigest()[:24]
        outcome["receipt_id"] = receipt_id
        outcome["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
            outcome, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False).encode("utf-8")).hexdigest()
        handle = self._serving._handle
        directory = handle.fixed_object("local-model/serving/resource-release-receipts")
        handle.ensure_directory(directory)
        target = directory.child(receipt_id + ".json")
        encoded = (json.dumps(outcome, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        try:
            handle.durable_create(target, encoded)
        except InstallationStateError as exc:
            if (exc.args != ("state_object_already_exists",)
                    or handle.read_regular_bounded(target, max_bytes=262_144) != encoded):
                raise ProductionServingInferenceError(
                    "resource_release_receipt_publication_failed") from exc
        return outcome

    def reconcile_idle_game_resource_state(self) -> dict[str, Any]:
        """Release an exact resident session on verified game/GPU pressure, without inference."""
        if not self._receipt_capacity_lock.acquire(blocking=False):
            return {"status": "skipped", "reason": "inference_or_release_in_progress"}
        try:
            workload = self.current_workload_state()
            selected_gaming_profile = workload.get("configured_mode") == "gaming"
            if workload.get("configured_mode") != "automatic" and not selected_gaming_profile:
                return {"status": "skipped", "reason": "gaming_workload_profile_required"}
            if not selected_gaming_profile:
                provenance = workload.get("transport_provenance")
                if (workload.get("observation_status") != "available"
                        or (workload.get("game_foreground") is not True
                            and workload.get("game_process_running") is not True)
                        or not isinstance(provenance, Mapping)
                        or not isinstance(provenance.get("message_id"), str)):
                    return {"status": "skipped", "reason": "fresh_verified_game_evidence_required"}
            session = self._serving.current_session()
            if session is None:
                return {"status": "skipped", "reason": "no_resident_serving_session"}
            try:
                model = self._serving._current_inference_model(session)
            except ProductionServingError:
                return {"status": "skipped", "reason": "current_serving_session_required"}
            frame_release = self._release_after_game_frame_pressure(
                session, model, workload)
            if frame_release is not None:
                return {"status": frame_release["status"],
                    "release_receipt_id": frame_release["receipt_id"],
                    "trigger_kind": "idle_game_frame_pressure_reconciliation",
                    "serving_session_id": session.session_id}
            load_configuration = session.binding.get("load_configuration")
            gpu_layers = (load_configuration.get("n_gpu_layers")
                if isinstance(load_configuration, Mapping) else None)
            if not selected_gaming_profile and type(gpu_layers) is int and 1 <= gpu_layers <= 256:
                residency_release = self._release_after_verified_game_gpu_model_residency(
                    session, model, workload)
                if residency_release is not None:
                    return {"status": residency_release["status"],
                        "release_receipt_id": residency_release["receipt_id"],
                        "trigger_kind": "idle_game_gpu_residency",
                        "serving_session_id": session.session_id}
            correlation_id = "idle-game-resource-reconcile-" + str(time.time_ns())
            observation = self._observe_host_resources(
                correlation_id, observation_namespace="local-chat-reconciliation")
            labels = observation.get("pressure_labels")
            if (observation.get("status") != "current"
                    or observation.get("no_effect_authority") is not True
                    or not isinstance(labels, (tuple, list))
                    or not all(isinstance(label, str) for label in labels)
                    or not set(labels).intersection(ACTIONABLE_RESOURCE_PRESSURE_LABELS)):
                return {"status": "skipped", "reason": "current_host_pressure_evidence_required",
                    "observation_correlation_id": observation.get("observation_correlation_id")}
            evidence = {key: workload.get(key) for key in (
                "configured_mode", "mode_source", "observation_status", "game_foreground",
                "process_name_digest", "game_process_running", "running_process_name_digests",
                "observed_at", "transport_provenance")}
            trigger_kind = ("gaming_profile_resource_reconciliation"
                if selected_gaming_profile else "idle_game_reconciliation")
            release_outcome = self._release_after_host_pressure(
                session, model, None, resource_observation=observation,
                workload_evidence=evidence, trigger_correlation_id=correlation_id,
                trigger_kind=trigger_kind)
            if release_outcome is None:
                return {"status": "skipped", "reason": "release_evidence_invalid"}
            return {"status": release_outcome["status"],
                "release_receipt_id": release_outcome["receipt_id"],
                "trigger_kind": trigger_kind,
                "observation_correlation_id": observation.get("observation_correlation_id"),
                "serving_session_id": session.session_id}
        finally:
            self._receipt_capacity_lock.release()

    def _release_after_game_frame_pressure(
            self, session: ServingSession, model: Any,
            workload: Mapping[str, Any]) -> dict[str, Any] | None:
        """Release the exact optional model when a fresh authenticated game sample shows hitches."""
        getter = getattr(self._serving._kernel,
            "current_verified_game_performance_evidence", None)
        if not callable(getter):
            return None
        try:
            performance = getter()
        except Exception:
            return None
        if not isinstance(performance, Mapping):
            return None
        p95 = performance.get("frame_time_p95_ms")
        hitches = performance.get("hitch_count_over_50ms")
        frame_pressure = (
            isinstance(p95, (int, float)) and not isinstance(p95, bool)
            and math.isfinite(float(p95)) and 50.0 <= float(p95) <= 10_000
        ) or (type(hitches) is int and hitches > 0)
        required = (
            "message_id", "payload_digest", "process_id_digest", "source_id",
            "generation_id", "sequence", "observed_at")
        if not frame_pressure or any(not performance.get(key) for key in required):
            return None
        process_name_digest = performance.get("process_name_digest")
        if (not isinstance(process_name_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", process_name_digest) is None):
            return None
        configured_mode = workload.get("configured_mode")
        workload_message_id = None
        if configured_mode == "automatic":
            provenance = workload.get("transport_provenance")
            workload_message_id = (provenance.get("message_id")
                if isinstance(provenance, Mapping) else None)
            if not isinstance(workload_message_id, str):
                return None
        elif configured_mode != "gaming":
            return None
        loaded_identity = getattr(model, "active_identity", None)
        if loaded_identity is None or not callable(getattr(loaded_identity, "to_dict", None)):
            return None
        trigger_correlation = "idle-game-frame-pressure-reconcile-" + str(time.time_ns())
        evidence = {
            "schema_version": "sentientos.production_game_frame_pressure_release_evidence:v3",
            "trigger_kind": "idle_game_frame_pressure_reconciliation",
            "trigger_correlation_id": trigger_correlation,
            "serving_session_id": session.session_id,
            "game_performance_message_id": performance["message_id"],
            "game_performance_payload_digest": performance["payload_digest"],
            "game_performance_process_id_digest": performance["process_id_digest"],
            "game_performance_process_name_digest": process_name_digest,
            "game_performance_source_id": performance["source_id"],
            "game_performance_generation_id": performance["generation_id"],
            "game_performance_sequence": performance["sequence"],
            "workload_mode": configured_mode,
            "game_workload_message_id": workload_message_id,
            "observed_at": performance["observed_at"],
            "frame_time_p95_ms": p95,
            "hitch_count_over_50ms": hitches,
        }
        release_correlation = "production-chat-resource-release-" + hashlib.sha256(
            ("idle_game_frame_pressure_reconciliation:" + trigger_correlation)
            .encode("utf-8")).hexdigest()[:24]
        decision = self._serving._kernel.admit(ControlActionRequest(
            action_kind="local_model_resource_release",
            authority_class=AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE,
            actor="production_chat_game_resource_governor",
            target_subsystem="production_chat", requested_phase=LifecyclePhase.RUNTIME,
            metadata={"correlation_id": release_correlation,
                "purpose": "local_model_resource_release",
                "reason_code": "verified_game_frame_pressure",
                "target_subsystem": "production_chat",
                "model_identity_digest": digest_payload(loaded_identity.to_dict()),
                "resource_observation": evidence},
        ))
        decision_valid = (decision.allowed
            and decision.outcome == AdmissionOutcome.ALLOW
            and decision.authority_class == AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE
            and decision.action_kind == "local_model_resource_release"
            and decision.actor == "production_chat_game_resource_governor"
            and decision.target_subsystem == "production_chat"
            and decision.correlation_id == release_correlation)
        closed = False
        close_failure: str | None = None
        worker_exit_observed: bool | None = None
        post_release_observation: dict[str, Any] | None = None
        if decision_valid:
            try:
                closed = self._serving.release_current_session_after_resource_admission(
                    session, reason="verified_game_frame_pressure")
                worker = getattr(model, "_process", None)
                poll = getattr(worker, "poll", None)
                worker_exit_observed = poll() is not None if callable(poll) else None
                if closed:
                    # Frame pressure is the fast path: collect telemetry only after
                    # the release so a bounded host observation cannot delay relief.
                    post_release_observation = self._observe_host_resources(
                        trigger_correlation + ":resource-release-postflight",
                        observation_namespace="local-chat-reconciliation")
            except Exception as exc:
                close_failure = type(exc).__name__
        outcome = {
            "schema_version": "sentientos.production_chat_resource_release_receipt:v2",
            "status": "worker_closed" if closed else
                "release_effect_unconfirmed" if decision_valid else "denied",
            "trigger_kind": "idle_game_frame_pressure_reconciliation",
            "trigger_correlation_id": trigger_correlation,
            "release_correlation_id": release_correlation,
            "serving_session_id": session.session_id,
            "serving_operation_id": session.binding.get("serving_operation_id"),
            "model_identity_digest": digest_payload(loaded_identity.to_dict()),
            "release_admission_decision_ref": decision.admission_decision_ref,
            "release_admission_outcome": decision.outcome.value,
            "release_reason_codes": list(decision.reason_codes),
            "resource_observation": evidence,
            "post_release_observation": post_release_observation,
            "post_release_measurement_interpretation": (
                "read_only_sample_after_worker_close; no pre-release sample; "
                "telemetry_does_not_establish_causation"
                if post_release_observation is not None else None),
            "worker_exit_observed": worker_exit_observed,
            "close_failure": close_failure,
            "inference_performed": False,
            "host_mutation_performed": False,
        }
        encoded_body = json.dumps(outcome, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
        receipt_id = "serving-resource-release-" + hashlib.sha256(encoded_body).hexdigest()[:24]
        outcome["receipt_id"] = receipt_id
        outcome["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
            outcome, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False).encode("utf-8")).hexdigest()
        handle = self._serving._handle
        directory = handle.fixed_object("local-model/serving/resource-release-receipts")
        handle.ensure_directory(directory)
        target = directory.child(receipt_id + ".json")
        encoded = (json.dumps(outcome, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        try:
            handle.durable_create(target, encoded)
        except InstallationStateError as exc:
            if (exc.args != ("state_object_already_exists",)
                    or handle.read_regular_bounded(target, max_bytes=262_144) != encoded):
                raise ProductionServingInferenceError(
                    "resource_release_receipt_publication_failed") from exc
        return outcome

    def _release_after_verified_game_gpu_model_residency(
            self, session: ServingSession, model: Any,
            workload: Mapping[str, Any]) -> dict[str, Any] | None:
        """Release only GPU-backed optional chat residency for a fresh verified game."""
        provenance = workload.get("transport_provenance")
        message_id = provenance.get("message_id") if isinstance(provenance, Mapping) else None
        observed_at = workload.get("observed_at")
        load_configuration = session.binding.get("load_configuration")
        gpu_layers = (load_configuration.get("n_gpu_layers")
            if isinstance(load_configuration, Mapping) else None)
        if (workload.get("configured_mode") != "automatic"
                or workload.get("observation_status") != "available"
                or (workload.get("game_foreground") is not True
                    and workload.get("game_process_running") is not True)
                or not isinstance(message_id, str)
                or not isinstance(observed_at, str)
                or type(gpu_layers) is not int or not 1 <= gpu_layers <= 256):
            return None
        loaded_identity = getattr(model, "active_identity", None)
        if loaded_identity is None or not callable(getattr(loaded_identity, "to_dict", None)):
            return None
        trigger_correlation = "idle-game-gpu-residency-" + str(time.time_ns())
        before_sample = self._observe_host_resources(trigger_correlation,
            observation_namespace="local-chat-reconciliation")
        release_correlation = "production-chat-resource-release-" + hashlib.sha256(
            ("idle_game_gpu_residency:" + trigger_correlation).encode("utf-8")).hexdigest()[:24]
        evidence = {
            "schema_version": "sentientos.production_game_gpu_residency_release_evidence:v1",
            "trigger_kind": "idle_game_gpu_residency",
            "trigger_correlation_id": trigger_correlation,
            "game_workload_message_id": message_id,
            "model_gpu_layers": gpu_layers,
            "serving_session_id": session.session_id,
            "observed_at": observed_at,
        }
        decision = self._serving._kernel.admit(ControlActionRequest(
            action_kind="local_model_resource_release",
            authority_class=AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE,
            actor="production_chat_game_resource_governor",
            target_subsystem="production_chat", requested_phase=LifecyclePhase.RUNTIME,
            metadata={"correlation_id": release_correlation,
                "purpose": "local_model_resource_release",
                "reason_code": "verified_game_gpu_model_residency",
                "target_subsystem": "production_chat",
                "model_identity_digest": digest_payload(loaded_identity.to_dict()),
                "resource_observation": evidence},
        ))
        decision_valid = (decision.allowed and decision.outcome == AdmissionOutcome.ALLOW
            and decision.authority_class == AuthorityClass.LOCAL_MODEL_RESOURCE_RELEASE
            and decision.action_kind == "local_model_resource_release"
            and decision.actor == "production_chat_game_resource_governor"
            and decision.target_subsystem == "production_chat"
            and decision.correlation_id == release_correlation)
        closed = False
        close_failure: str | None = None
        worker_exit_observed: bool | None = None
        if decision_valid:
            try:
                closed = self._serving.release_current_session_after_resource_admission(
                    session, reason="verified_game_gpu_model_residency")
                worker = getattr(model, "_process", None)
                poll = getattr(worker, "poll", None)
                worker_exit_observed = poll() is not None if callable(poll) else None
            except Exception as exc:
                close_failure = type(exc).__name__
        after_sample = (self._observe_host_resources(trigger_correlation + ":post-release",
            observation_namespace="local-chat-reconciliation") if closed else None)

        def sample_fields(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
            if value is None:
                return None
            return {key: value.get(key) for key in (
                "status", "report_id", "observed_at", "pressure_labels",
                "gpu_utilization_percent", "vram_utilization_percent",
                "gpu_telemetry_sources")}

        before_values = sample_fields(before_sample)
        after_values = sample_fields(after_sample)
        gpu_delta = (after_values["gpu_utilization_percent"]
            - before_values["gpu_utilization_percent"]
            if before_values is not None and after_values is not None
            and isinstance(before_values["gpu_utilization_percent"], (int, float))
            and isinstance(after_values["gpu_utilization_percent"], (int, float)) else None)
        vram_delta = (after_values["vram_utilization_percent"]
            - before_values["vram_utilization_percent"]
            if before_values is not None and after_values is not None
            and isinstance(before_values["vram_utilization_percent"], (int, float))
            and isinstance(after_values["vram_utilization_percent"], (int, float)) else None)
        outcome = {"schema_version": "sentientos.production_chat_resource_release_receipt:v2",
            "status": "worker_closed" if closed else
                "release_effect_unconfirmed" if decision_valid else "denied",
            "trigger_kind": "idle_game_gpu_residency",
            "trigger_correlation_id": trigger_correlation,
            "release_correlation_id": release_correlation,
            "serving_session_id": session.session_id,
            "serving_operation_id": session.binding.get("serving_operation_id"),
            "model_identity_digest": digest_payload(loaded_identity.to_dict()),
            "release_admission_decision_ref": decision.admission_decision_ref,
            "release_admission_outcome": decision.outcome.value,
            "release_reason_codes": list(decision.reason_codes),
            "worker_exit_observed": worker_exit_observed,
            "close_failure": close_failure,
            "resource_observation": {"game_workload_message_id": message_id,
                "model_gpu_layers": gpu_layers, "host_telemetry_used_for_admission": False},
            "resource_measurement_comparison": {
                "before": before_values, "after": after_values,
                "gpu_utilization_delta_percentage_points": gpu_delta,
                "vram_utilization_delta_percentage_points": vram_delta,
                "interpretation": "sample_delta_only; telemetry_does_not_establish_causation"},
            "inference_performed": False, "host_mutation_performed": False}
        body = json.dumps(outcome, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
        receipt_id = "serving-resource-release-" + hashlib.sha256(body).hexdigest()[:24]
        outcome["receipt_id"] = receipt_id
        outcome["receipt_semantic_digest"] = hashlib.sha256(json.dumps(
            outcome, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False).encode("utf-8")).hexdigest()
        handle = self._serving._handle
        directory = handle.fixed_object("local-model/serving/resource-release-receipts")
        handle.ensure_directory(directory)
        target = directory.child(receipt_id + ".json")
        encoded = (json.dumps(outcome, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        try:
            handle.durable_create(target, encoded)
        except InstallationStateError as exc:
            if (exc.args != ("state_object_already_exists",)
                    or handle.read_regular_bounded(target, max_bytes=262_144) != encoded):
                raise ProductionServingInferenceError(
                    "resource_release_receipt_publication_failed") from exc
        return outcome

    def reconcile_workload_state(self) -> dict[str, Any]:
        return self.reconcile_idle_game_resource_state()

    def generate(self, *, prompt: str, caller: str, correlation_id: str,
                 budget: LocalModelInvocationBudget | None = None,
                 caller_linkage: Mapping[str, Any] | None = None,
                 resource_context: GovernedLocalModelResourceInvocationContext | None = None,
                 ) -> LocalModelInvocationReceipt:
        session = self._serving.current_session()
        if session is None:
            raise ProductionServingInferenceError("current_serving_session_required")
        try:
            model = self._serving._current_inference_model(session)
        except ProductionServingError as exc:
            raise ProductionServingInferenceError(exc.code) from exc
        authority = self._authority(session)
        binding = session.binding
        identity = dict(binding["observed_loaded_model_identity"])
        record = authority.record_for_active_identity(model.active_identity, "local_user_chat")
        if record is None or model.active_identity.to_dict() != identity:
            raise ProductionServingInferenceError("exact_loaded_model_authority_record_required")
        software_generation_attribution = self._software_generation_attribution()
        configured_operation = software_generation_attribution.get("configured_serving_operation_id")
        if (configured_operation is not None
                and configured_operation != binding.get("serving_operation_id")):
            raise ProductionServingInferenceError("serving_operation_chat_handoff_mismatch")
        host_resource_observation = self._observe_host_resources(correlation_id)
        workload_state = self.current_workload_state()
        workload_mode = workload_state["effective_mode"]
        try:
            response_style = (caller_linkage.get("chat_response_style")
                if isinstance(caller_linkage, Mapping) else None)
            effective_prompt = GamingWorkloadPolicy.apply_chat_response_style(
                prompt, workload_mode,
                social_checkin=response_style == "social_checkin",
                screen_observation=response_style == "screen_observation")
        except ValueError as exc:
            raise ProductionServingInferenceError(str(exc)) from exc
        effective_budget, linkage = GamingWorkloadPolicy.apply_to_chat_invocation(
            workload_mode, budget or LocalModelInvocationBudget(), {
            "serving_session_id": session.session_id,
            "serving_receipt_id": binding.get("serving_receipt_id"),
            "serving_receipt_semantic_digest": binding.get("serving_receipt_semantic_digest"),
            "serving_operation_attempt_id": binding.get("serving_operation_attempt_id"),
            "serving_operation_attempt_semantic_digest": binding.get(
                "serving_operation_attempt_semantic_digest"),
            "serving_operation_id": binding["serving_operation_id"],
            "installation_identity": binding["installation_identity"],
            "activation_state_semantic_digest": binding["activation_state_semantic_digest"],
            "activation_generation": binding["activation_generation"],
            "activation_predecessor_state_digest": binding["activation_predecessor_state_digest"],
            "activation_receipt_id": binding["activation_receipt_id"],
            "activation_receipt_semantic_digest": binding["activation_receipt_semantic_digest"],
            "model_serving_admission_ref": binding["model_serving_admission_ref"],
            "authority_map_digest": binding["authority_map_digest"],
            "model_id": binding["model_id"],
            "observed_loaded_model_identity": identity,
            "host_resource_observation": host_resource_observation,
            "artifact_id": binding["artifact_id"],
            "artifact_sha256": binding["artifact_sha256"],
            "runtime_id": binding["runtime_id"],
            "caller_context": dict(caller_linkage or {}),
            "software_generation_attribution": software_generation_attribution,
        }, workload_evidence={key: workload_state.get(key) for key in (
            "configured_mode", "mode_source", "observation_status", "game_foreground",
            "process_name_digest", "game_process_running", "running_process_name_digests",
            "observed_at", "transport_provenance")})
        invoker = GovernedLocalModelInvoker(
            model=model, authority_map=authority, kernel=self._serving._kernel,
            runtime_root=self._serving._handle.root / "local-model" / "inference")
        handle = self._serving._handle
        receipt_directory = handle.fixed_object("local-model/inference/receipts")
        handle.ensure_directory(receipt_directory)

        def publish_receipt(value: Mapping[str, Any]) -> None:
            receipt_id = value.get("receipt_id")
            if (not isinstance(receipt_id, str) or len(receipt_id) != 30
                    or not receipt_id.startswith("lmrec-")
                    or any(character not in "0123456789abcdef" for character in receipt_id[6:])):
                raise ProductionServingInferenceError("invocation_receipt_identity_invalid")
            valid, findings = validate_receipt(value)
            if not valid:
                raise ProductionServingInferenceError("invocation_receipt_validation_failed:" + findings[0])
            target = receipt_directory.child(receipt_id + ".json")
            payload = (json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
            if len(payload) > MAX_INVOCATION_RECEIPT_BYTES:
                raise ProductionServingInferenceError("invocation_receipt_size_bound_exceeded")
            handle.durable_replace(target, payload)

        invoker.register_evidence_sink(publish_receipt)
        request = invoker.build_request(
            purpose="local_user_chat", prompt=effective_prompt, caller=caller,
            correlation_id=correlation_id, budget=effective_budget,
            upstream_evidence={"current_serving_lifetime": linkage}, linkage=linkage)
        request_receipt_bytes = json.dumps(request.to_receipt_request_dict(),
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False).encode("utf-8")
        # Leave bounded room for the receipt envelope and resource linkage,
        # which are added after backend entry.
        if len(request_receipt_bytes) + 8192 > MAX_INVOCATION_RECEIPT_BYTES:
            raise ProductionServingInferenceError(
                "invocation_request_receipt_size_bound_exceeded")

        def current() -> None:
            # Both guards use the chat child’s own launcher handoff, never the
            # maintenance daemon’s independently running software identity.
            # The post-effect guard ensures a completed receipt cannot span a
            # detected source-generation change during inference.
            try:
                self._serving._current_inference_model(session)
            except ProductionServingError as exc:
                raise ProductionServingInferenceError("serving_lifetime_not_current") from exc
            current_generation = self._software_generation_attribution()
            if current_generation != software_generation_attribution:
                raise ProductionServingInferenceError("chat_process_generation_changed_during_inference")

        def current_after() -> None:
            try:
                current()
            except ProductionServingInferenceError:
                self._serving._invalidate_inference_session(session, "currentness_changed_during_inference")
                raise

        # The read-only observer refuses more than this many receipts. Hold
        # one process-local slot across backend execution and durable receipt
        # publication so concurrent requests cannot exceed that source bound.
        with self._receipt_capacity_lock:
            try:
                receipt_names = handle.list_regular_names(
                    receipt_directory, max_entries=MAX_INVOCATION_RECEIPTS)
            except Exception as exc:
                raise ProductionServingInferenceError(
                    "invocation_receipt_capacity_observation_unavailable") from exc
            if len(receipt_names) >= MAX_INVOCATION_RECEIPTS:
                raise ProductionServingInferenceError(
                    "invocation_receipt_capacity_exhausted")
            receipt = invoker.invoke(
                request,
                pre_effect_guard=current,
                post_effect_guard=current_after,
                resource_context=resource_context,
            )
            if receipt.admission_decision_ref != binding["model_serving_admission_ref"]:
                self._release_after_host_pressure(session, model, receipt)
        if receipt.admission_decision_ref == binding["model_serving_admission_ref"]:
            raise ProductionServingInferenceError("inference_admission_not_independent")
        return receipt

    def verify_stored_chat_invocation(self, *, receipt_id: str, receipt_digest: str,
                                     session_id: str, user_turn_id: str,
                                     assistant_text: str | None = None,
                                     client_request_id_digest: str | None = None) -> Mapping[str, Any]:
        """Reconstruct one prior chat model identity from installation custody."""
        if (not isinstance(receipt_id, str) or len(receipt_id) != 30 or not receipt_id.startswith("lmrec-")
                or any(character not in "0123456789abcdef" for character in receipt_id[6:])):
            raise ProductionServingInferenceError("stored_invocation_identity_invalid")
        try:
            raw = self._serving._handle.read_regular_bounded(
                self._serving._handle.fixed_object(f"local-model/inference/receipts/{receipt_id}.json"),
                max_bytes=1_048_576)
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise ProductionServingInferenceError("stored_invocation_unavailable_or_invalid") from exc
        if (not isinstance(value, Mapping)
                or json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n" != raw
                or value.get("receipt_id") != receipt_id or value.get("receipt_digest") != receipt_digest):
            raise ProductionServingInferenceError("stored_invocation_identity_mismatch")
        valid, findings = validate_receipt(value)
        request = value.get("request")
        if not isinstance(request, Mapping):
            raise ProductionServingInferenceError("stored_invocation_request_invalid")
        request_semantic = {key: item for key, item in request.items()
            if key not in {"request_id", "request_digest", "raw_prompt_stored", "ephemeral_prompt_handling"}}
        request_digest = digest_payload(request_semantic)
        if (not valid or value.get("status") != "admitted_completed"
                or not isinstance(value.get("effects"), Mapping)
                or value["effects"].get("local_model_inference") is not True
                or not isinstance(value.get("output_digest"), str)
                or request.get("request_digest") != request_digest
                or request.get("request_id") != "lmreq-" + request_digest[:24]
                or request.get("caller") != "chat_service" or request.get("purpose") != "local_user_chat"):
            raise ProductionServingInferenceError("stored_invocation_not_completed_chat")
        upstream = request.get("upstream_evidence")
        linkage = request.get("linkage")
        lifetime = upstream.get("current_serving_lifetime") if isinstance(upstream, Mapping) else None
        if (not isinstance(lifetime, Mapping) or not isinstance(linkage, Mapping)
                or linkage != dict(lifetime)
                or dict(request.get("active_model_identity", {})) != dict(lifetime.get("observed_loaded_model_identity", {}))):
            raise ProductionServingInferenceError("stored_invocation_serving_binding_invalid")
        caller_context = lifetime.get("caller_context")
        if (not isinstance(caller_context, Mapping) or caller_context.get("session_id") != session_id
                or caller_context.get("user_turn_id") != user_turn_id):
            raise ProductionServingInferenceError("stored_invocation_conversation_binding_invalid")
        if client_request_id_digest is not None:
            if (not isinstance(client_request_id_digest, str) or len(client_request_id_digest) != 64
                    or any(character not in "0123456789abcdef" for character in client_request_id_digest)
                    or caller_context.get("client_request_id_digest") != client_request_id_digest):
                raise ProductionServingInferenceError("stored_invocation_client_request_binding_invalid")
        serving_reference_keys = ("serving_receipt_id", "serving_receipt_semantic_digest",
            "serving_operation_attempt_id", "serving_operation_attempt_semantic_digest")
        serving_reference_values = [lifetime.get(key) for key in serving_reference_keys]
        serving_receipt_lineage: dict[str, Any] = {"status": "historically_unbound"}
        if any(item is not None for item in serving_reference_values):
            if any(not isinstance(item, str) or not item for item in serving_reference_values):
                raise ProductionServingInferenceError("stored_invocation_serving_receipt_identity_incomplete")
            serving_receipt_id, serving_receipt_digest, serving_attempt_id, serving_attempt_digest = (
                serving_reference_values)
            try:
                serving_history = read_serving_operation_history(self._serving._handle)
            except ProductionServingError as exc:
                raise ProductionServingInferenceError("stored_invocation_serving_history_invalid") from exc
            matching_history = [item for item in serving_history
                if item.get("receipt_semantic_digest") == serving_receipt_digest
                and isinstance(item.get("receipt"), Mapping)
                and item["receipt"].get("receipt_id") == serving_receipt_id]
            if len(matching_history) != 1:
                raise ProductionServingInferenceError("stored_invocation_serving_receipt_unavailable")
            serving_history_item = matching_history[0]
            serving_receipt = serving_history_item["receipt"]
            serving_binding = serving_receipt.get("binding")
            serving_binding_fields = (
                "installation_identity", "serving_operation_id", "activation_state_semantic_digest",
                "activation_generation", "activation_predecessor_state_digest",
                "activation_receipt_id", "activation_receipt_semantic_digest",
                "model_serving_admission_ref", "authority_map_digest", "model_id",
                "artifact_id", "artifact_sha256", "runtime_id", "observed_loaded_model_identity",
            )
            if (serving_history_item.get("status") != "serving_receipt_verified"
                    or serving_receipt.get("session_id") != lifetime.get("serving_session_id")
                    or serving_history_item.get("attempt_semantic_digest") != serving_attempt_digest
                    or not isinstance(serving_history_item.get("attempt"), Mapping)
                    or serving_history_item["attempt"].get("attempt_id") != serving_attempt_id
                    or not isinstance(serving_binding, Mapping)
                    or any(lifetime.get(key) != serving_binding.get(key)
                        for key in serving_binding_fields)):
                raise ProductionServingInferenceError("stored_invocation_serving_receipt_lineage_mismatch")
            serving_receipt_lineage = {
                "status": "reservation_and_serving_receipt_verified",
                "serving_receipt_id": serving_receipt_id,
                "serving_receipt_semantic_digest": serving_receipt_digest,
                "serving_operation_attempt_id": serving_attempt_id,
                "serving_operation_attempt_semantic_digest": serving_attempt_digest,
            }
        software_generation = linkage.get("software_generation_attribution")
        if software_generation == unavailable_chat_process_software_generation():
            pass
        elif (isinstance(software_generation, Mapping)
                and software_generation.get("status") == "runtime_launcher_process_and_source_bound"):
            handoff_id = software_generation.get("handoff_id")
            handoff_digest = software_generation.get("handoff_digest")
            if not isinstance(handoff_id, str) or not isinstance(handoff_digest, str):
                raise ProductionServingInferenceError("stored_invocation_software_generation_posture_invalid")
            try:
                historical = verify_stored_chat_process_handoff(
                    handle=self._serving._handle, handoff_id=handoff_id,
                    expected_digest=handoff_digest)
            except ChatProcessGenerationError as exc:
                raise ProductionServingInferenceError("stored_invocation_software_generation_handoff_invalid") from exc
            if dict(historical) != dict(software_generation):
                raise ProductionServingInferenceError("stored_invocation_software_generation_handoff_mismatch")
            handoff_operation = historical.get("configured_serving_operation_id")
            serving_operation = lifetime.get("serving_operation_id")
            if (handoff_operation is not None and handoff_operation != serving_operation):
                raise ProductionServingInferenceError("stored_invocation_serving_operation_handoff_mismatch")
        else:
            raise ProductionServingInferenceError("stored_invocation_software_generation_posture_invalid")
        assistant_output_lineage = None
        if assistant_text is not None:
            if not isinstance(assistant_text, str) or not assistant_text:
                raise ProductionServingInferenceError("stored_invocation_transcript_text_invalid")
            transcript_text_digest = digest_payload({"text": assistant_text})
            if not value.get("output_truncated"):
                if digest_payload({"output": assistant_text}) == value.get("output_digest"):
                    output_posture = "exact_invocation_output_match"
                else:
                    original_output = value.get("output_text")
                    request_linkage = request.get("linkage")
                    serving_mode = lifetime.get("workload_mode")
                    expected_output, correction = corrected_gaming_output(
                        original_output if isinstance(original_output, str) else "",
                        workload_mode=str(serving_mode or "normal"),
                        screen_observation_provenance=(request_linkage.get("screen_observation_provenance")
                            if isinstance(request_linkage, Mapping) else None),
                        social_checkin=(isinstance(request_linkage, Mapping)
                            and request_linkage.get("chat_response_style") == "social_checkin"))
                    if (correction is None or expected_output != assistant_text
                            or digest_payload({"output": original_output}) != value.get("output_digest")):
                        raise ProductionServingInferenceError("stored_invocation_transcript_output_mismatch")
                    output_posture = "grounding_policy_fallback"
            else:
                output_posture = "truncated_transcript_original_output_relation_unknown"
            assistant_output_lineage = {
                "status": output_posture,
                "invocation_output_digest": value.get("output_digest"),
                "transcript_text_digest": transcript_text_digest,
                "invocation_output_text_sha256": hashlib.sha256(
                    str(value.get("output_text", "")).encode("utf-8")).hexdigest(),
                "transcript_text_sha256": hashlib.sha256(
                    assistant_text.encode("utf-8")).hexdigest(),
                "output_truncated": value.get("output_truncated"),
            }
            if output_posture == "grounding_policy_fallback":
                if correction is None:
                    raise ProductionServingInferenceError(
                        "stored_invocation_grounding_lineage_missing")
                assistant_output_lineage.update({
                    "policy_id": correction["policy_id"],
                    "reason_code": correction["reason_code"],
                })
        identity_keys: tuple[str, ...] = ("installation_identity", "activation_state_semantic_digest", "activation_generation",
            "activation_predecessor_state_digest", "activation_receipt_id", "activation_receipt_semantic_digest",
            "model_id", "observed_loaded_model_identity", "artifact_id", "artifact_sha256", "runtime_id",
            "authority_map_digest")
        identity_keys = identity_keys + tuple(key for key in serving_reference_keys if key in lifetime)
        if any(key not in lifetime for key in identity_keys):
            raise ProductionServingInferenceError("stored_invocation_serving_identity_incomplete")
        return {"serving_identity": {key: lifetime[key] for key in identity_keys},
                "loaded_model_identity": dict(request["active_model_identity"]),
                "request_id": request["request_id"], "receipt_id": receipt_id,
                "receipt_digest": receipt_digest, "status": value["status"],
                "software_generation_attribution": dict(software_generation),
                "caller_linkage": dict(caller_context),
                "serving_receipt_lineage": serving_receipt_lineage,
                "assistant_output_lineage": assistant_output_lineage}


    def inspect_interrupted_chat_invocation(self, *, session_id: str, user_turn_id: str,
                                             client_request_id_digest: str | None = None
                                             ) -> Mapping[str, Any]:
        """Classify matching receipt custody without recovering output or replaying inference."""
        if (not isinstance(session_id, str) or not session_id
                or not isinstance(user_turn_id, str)
                or re.fullmatch(r"turn-[0-9a-f]{24}", user_turn_id) is None):
            raise ProductionServingInferenceError("interrupted_chat_identity_invalid")
        if client_request_id_digest is not None and (
                not isinstance(client_request_id_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", client_request_id_digest) is None):
            raise ProductionServingInferenceError("interrupted_chat_request_digest_invalid")
        handle = self._serving._handle
        try:
            names = handle.list_regular_names(
                handle.fixed_object("local-model/inference/receipts"), max_entries=MAX_INVOCATION_RECEIPTS)
        except InstallationStateError as exc:
            if exc.code in {"state_directory_missing", "state_parent_missing"}:
                names = ()
            else:
                raise ProductionServingInferenceError(
                    "interrupted_chat_receipt_directory_invalid") from exc
        matches: list[Mapping[str, Any]] = []
        total_bytes = 0
        for name in names:
            if re.fullmatch(r"\.lmrec-[0-9a-f]{24}\.json\.[A-Za-z0-9_-]{1,64}\.tmp", name) is not None:
                continue
            if re.fullmatch(r"lmrec-[0-9a-f]{24}\.json", name) is None:
                raise ProductionServingInferenceError("interrupted_chat_receipt_name_invalid")
            receipt_id = name[:-5]
            try:
                raw = handle.read_regular_bounded(
                    handle.fixed_object(f"local-model/inference/receipts/{name}"),
                    max_bytes=MAX_INVOCATION_RECEIPT_BYTES)
                total_bytes += len(raw)
                if total_bytes > 16 * 1024 * 1024:
                    raise ProductionServingInferenceError(
                        "interrupted_chat_receipt_scan_retention_limit")
                value = json.loads(raw.decode("utf-8"))
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                raise ProductionServingInferenceError(
                    "interrupted_chat_receipt_unavailable_or_invalid") from exc
            if (not isinstance(value, Mapping)
                    or json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n" != raw
                    or value.get("receipt_id") != receipt_id):
                raise ProductionServingInferenceError("interrupted_chat_receipt_canonicality_invalid")
            valid, findings = validate_receipt(value)
            if not valid:
                raise ProductionServingInferenceError(
                    "interrupted_chat_receipt_invalid:" + findings[0])
            request = value.get("request")
            request_linkage = request.get("linkage") if isinstance(request, Mapping) else None
            caller_context = (request_linkage.get("caller_context")
                if isinstance(request_linkage, Mapping) else None)
            if (not isinstance(request, Mapping)
                    or request.get("caller") != "chat_service"
                    or request.get("purpose") != "local_user_chat"
                    or not isinstance(caller_context, Mapping)
                    or caller_context.get("session_id") != session_id
                    or caller_context.get("user_turn_id") != user_turn_id):
                continue
            if (client_request_id_digest is not None
                    and caller_context.get("client_request_id_digest")
                        != client_request_id_digest):
                continue
            matches.append(value)
        if len(matches) > 1:
            raise ProductionServingInferenceError(
                "interrupted_chat_multiple_matching_invocation_receipts")
        if not matches:
            return {"status": "no_matching_verified_invocation_receipt"}
        value = matches[0]
        complete = (value.get("status") == "admitted_completed"
            and isinstance(value.get("effects"), Mapping)
            and value["effects"].get("local_model_inference") is True
            and isinstance(value.get("output_digest"), str))
        return {
            "status": ("completed_response_body_not_retained" if complete
                else "matching_invocation_receipt_incomplete"),
            "receipt_id": value.get("receipt_id"),
            "receipt_digest": value.get("receipt_digest"),
            "request_id": (value.get("request", {}).get("request_id")
                if isinstance(value.get("request"), Mapping) else None),
            "invocation_status": value.get("status"),
            "output_digest": value.get("output_digest") if complete else None,
        }
