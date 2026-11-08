"""Bounded rootless experimental epistemic session over local Ollama.

This adapter keeps Ollama's development-only posture and grants one purpose:
the four-call epistemic revision probe. It is not production serving authority.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .control_plane_kernel import ControlPlaneKernel
from .governed_local_model_invocation import GovernedLocalModelInvoker
from .local_model import LocalModel
from .local_model_authority import (
    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
    build_rootless_experimental_epistemic_authority_map,
    stream_sha256,
)
from .local_runtime_provisioning import semantic_digest
from .rootless_experimental_epistemic_session import (
    MAX_CONTEXT_TOKENS, MAX_NEW_TOKENS,
    RootlessExperimentalEpistemicSession,
)
from .rootless_experimental_local_model import (
    EXPERIMENT_ROOT, RootlessExperimentalError, _no_symlink_path,
    _rootless_governance_custody, _safe_child, validate_experiment_root,
)


class RootlessExperimentalOllamaEpistemicSession(
        RootlessExperimentalEpistemicSession):
    """Four-call session bound to one digest-pinned, numeric-loopback Ollama tag."""

    def __init__(self, *, model_manifest_path: Path, model_name: str,
                 root: Path, session_binding: Mapping[str, Any],
                 kernel_factory: Any | None = None) -> None:
        self.root = validate_experiment_root(root)
        try:
            self.root.relative_to(EXPERIMENT_ROOT.resolve(strict=True))
        except (ValueError, OSError) as exc:
            raise RootlessExperimentalError(
                "epistemic_session_root_outside_rootless_experiment") from exc
        if (not isinstance(session_binding, Mapping)
                or session_binding.get("purpose") != ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
                or session_binding.get("production_authority") is not False
                or session_binding.get("eligible_as_production_serving_evidence") is not False
                or session_binding.get("preregistration_digest") != "0" * 64
                or session_binding.get("active_model_identity_digest") != "0" * 64):
            raise RootlessExperimentalError("epistemic_session_binding_invalid")
        self.session_binding = dict(session_binding)
        path = _safe_child(EXPERIMENT_ROOT, Path(model_manifest_path)).resolve(strict=True)
        manifest_digest, manifest_size = stream_sha256(path)
        if (not isinstance(model_name, str) or not model_name
                or len(model_name) > 128):
            raise RootlessExperimentalError("ollama_experimental_model_binding_invalid")
        options = {"api_base": "http://127.0.0.1:11434", "model": model_name,
            "manifest_sha256": manifest_digest, "num_gpu": 99, "keep_alive": "15m",
            "think": False, "timeout_seconds": 120}
        self.config = ModelConfig(
            [ModelCandidate(path, "ollama", model_name, options)],
            default_engine="ollama", max_context_tokens=MAX_CONTEXT_TOKENS,
            generation=GenerationConfig(max_new_tokens=MAX_NEW_TOKENS,
                temperature=0, top_p=1))
        self.authority_map = build_rootless_experimental_epistemic_authority_map(
            self.config, allowed_roots=[path.parent])
        record = self.authority_map.eligible_record(
            ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE)
        if record is None or record.engine != "ollama":
            raise RootlessExperimentalError("ollama_experimental_authority_unavailable")
        self.worker = LocalModel.load_candidate(0, config=self.config)
        identity = self.worker.active_identity
        if (identity.engine != "ollama" or identity.posture != "development_only"
                or identity.fallback or identity.candidate_index != 0
                or identity.model_content_sha256 != manifest_digest
                or identity.artifact_size_bytes != manifest_size
                or self.authority_map.record_for_active_identity(
                    identity, ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE) is None):
            raise RootlessExperimentalError("epistemic_session_model_identity_mismatch")
        self.active_model_identity = identity.to_dict()
        self.model_manifest = {
            "manifest_digest": manifest_digest, "artifact_sha256": manifest_digest,
            "artifact_size_bytes": manifest_size, "artifact_path": str(path),
            "model_id": model_name,
            "schema_version": "sentientos.ollama_local_manifest_observation:v1"}
        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/version", method="GET")
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=5) as response:
                payload = json.loads(response.read(4096).decode("utf-8"))
        except Exception as exc:
            raise RootlessExperimentalError(
                "ollama_runtime_observation_failed") from exc
        self.runtime_bundle = {
            "backend": "ollama-loopback",
            "version": str(payload.get("version", "unknown")),
            "model_manifest_digest": manifest_digest,
            "runtime_attestation": "local_observation_only"}
        self.runtime_bundle_digest = semantic_digest(self.runtime_bundle)
        if (self.session_binding.get("model_manifest_digest") != manifest_digest
                or self.session_binding.get("runtime_bundle_digest")
                    != self.runtime_bundle_digest):
            raise RootlessExperimentalError(
                "epistemic_session_evidence_binding_mismatch")
        self.runtime_root = self.root / "inference-custody"
        _no_symlink_path(self.runtime_root)
        self._preregistration_bound = False
        self._governance_context = _rootless_governance_custody(self.root)
        self._governance_context.__enter__()
        if kernel_factory is None:
            from .runtime_governor import RuntimeGovernor
            kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
                decisions_path=self.root / "control-plane" / "decisions.jsonl")
        else:
            kernel = kernel_factory(self.root)
        self.invoker = GovernedLocalModelInvoker(model=self.worker,
            authority_map=self.authority_map, kernel=kernel,
            runtime_root=self.runtime_root)
        self._correlations: set[str] = set()
        self._closed = False

    def measured_process_resources(self) -> Mapping[str, Any]:
        return {"measurement_source":
            "Ollama process telemetry not sampled per invocation",
            "platform": "linux", "peak_rss_bytes": None,
            "worker_user_cpu_seconds": None, "worker_system_cpu_seconds": None,
            "measurement_scope": "external_model_server_not_per_invocation"}

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            resident = self.worker.is_resident()
            if resident is True:
                receipt = self.invoker.release_model_residency(
                    reason_code="rootless_experimental_epistemic_complete")
                if receipt.status != "released":
                    raise RootlessExperimentalError(
                        "ollama_governed_release_unconfirmed")
            elif resident is not False:
                raise RootlessExperimentalError(
                    "ollama_residency_observation_unavailable")
        finally:
            self._governance_context.__exit__(None, None, None)

