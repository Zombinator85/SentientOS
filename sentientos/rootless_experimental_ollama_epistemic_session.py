"""Bounded rootless experimental epistemic session over local Ollama.

This adapter keeps Ollama's development-only posture and grants one purpose:
the four-call epistemic revision probe. It is not production serving authority.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .control_plane_kernel import ControlPlaneKernel
from .governed_local_model_invocation import (
    GovernedLocalModelInvoker, validate_receipt,
)
from .local_model import LocalModel
from .local_model_authority import (
    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_PURPOSE,
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES,
    build_rootless_experimental_epistemic_authority_map,
    build_rootless_experimental_developmental_authority_map,
    stream_sha256,
)
from .local_runtime_provisioning import semantic_digest
from .rootless_experimental_epistemic_session import (
    MAX_CONTEXT_TOKENS, MAX_NEW_TOKENS, MAX_OUTPUT_CHARS, MAX_PROMPT_CHARS,
    MAX_CALL_TIMEOUT_SECONDS,
    RootlessExperimentalEpistemicSession,
)
from .rootless_experimental_local_model import (
    EXPERIMENT_ROOT, MAX_RECORD_BYTES, RootlessExperimentalError, _no_symlink_path,
    _read_json,
    _rootless_governance_custody, _safe_child, validate_experiment_root,
)


ROOTLESS_RECEIPT_ID_RE = re.compile(r"^lmrec-[0-9a-f]{24}$")
ROOTLESS_DEVELOPMENTAL_MAX_CALLS = 32
ROOTLESS_DEVELOPMENTAL_MAX_INPUT_CHARS = 48_000


class RootlessExperimentalOllamaEpistemicSession(
        RootlessExperimentalEpistemicSession):
    """Four-call session bound to one digest-pinned, numeric-loopback Ollama tag."""

    def __init__(self, *, model_manifest_path: Path, model_name: str,
                 root: Path, session_binding: Mapping[str, Any],
                 kernel_factory: Any | None = None,
                 developmental_cycle: bool = False) -> None:
        self.root = validate_experiment_root(root)
        self.experimental_profile = ("developmental_cognition_cycle"
            if developmental_cycle else "epistemic_revision")
        purpose = (ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_PURPOSE
            if developmental_cycle else ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE)
        # The developmental companion prompt carries current World-State,
        # typed history, provenance bindings, and a structured response schema.
        # Hermes advertises a 40k native context; use an 8k bounded window here
        # so the actual governed hosted-companion call can fit while keeping
        # the separate epistemic-revision profile at its existing bound.
        max_context_tokens = 8192 if developmental_cycle else MAX_CONTEXT_TOKENS
        max_new_tokens = 512 if developmental_cycle else MAX_NEW_TOKENS
        try:
            self.root.relative_to(EXPERIMENT_ROOT.resolve(strict=True))
        except (ValueError, OSError) as exc:
            raise RootlessExperimentalError(
                "epistemic_session_root_outside_rootless_experiment") from exc
        if (not isinstance(session_binding, Mapping)
                or session_binding.get("purpose") != purpose
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
            "think": False, "timeout_seconds": 120, "seed": 42}
        self.config = ModelConfig(
            [ModelCandidate(path, "ollama", model_name, options)],
            default_engine="ollama", max_context_tokens=max_context_tokens,
            generation=GenerationConfig(max_new_tokens=max_new_tokens,
                temperature=0, top_p=1))
        authority_builder = (build_rootless_experimental_developmental_authority_map
            if developmental_cycle else build_rootless_experimental_epistemic_authority_map)
        self.authority_map = authority_builder(self.config, allowed_roots=[path.parent])
        required_purposes = (ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES
            if developmental_cycle else (ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,))
        # Keep each session profile's purpose and resource envelope aligned
        # with the authority map used to construct its worker. The older
        # wrapper accidentally applied the developmental purpose set to the
        # epistemic-revision profile, so every real epistemic-series run was
        # denied before its first inference.
        self._allowed_purposes = frozenset(required_purposes)
        self._max_input_chars = (ROOTLESS_DEVELOPMENTAL_MAX_INPUT_CHARS
            if developmental_cycle else MAX_PROMPT_CHARS)
        self._max_output_chars = 4000 if developmental_cycle else MAX_OUTPUT_CHARS
        self._max_new_tokens = 512 if developmental_cycle else MAX_NEW_TOKENS
        self._max_timeout_seconds = 120 if developmental_cycle else MAX_CALL_TIMEOUT_SECONDS
        self._max_calls = (ROOTLESS_DEVELOPMENTAL_MAX_CALLS
            if developmental_cycle else 4)
        record = next((self.authority_map.eligible_record(item)
            for item in required_purposes
            if self.authority_map.eligible_record(item) is not None), None)
        if record is None or record.engine != "ollama":
            raise RootlessExperimentalError("ollama_experimental_authority_unavailable")
        self.worker = LocalModel.load_candidate(0, config=self.config)
        identity = self.worker.active_identity
        if (identity.engine != "ollama" or identity.posture != "development_only"
                or identity.fallback or identity.candidate_index != 0
                or identity.model_content_sha256 != manifest_digest
                or identity.artifact_size_bytes != manifest_size
                or not any(self.authority_map.record_for_active_identity(identity, item)
                    is not None for item in required_purposes)):
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

    def build_request(self, **kwargs: Any) -> Any:
        purpose = kwargs.get("purpose")
        prompt = kwargs.get("prompt")
        linkage = kwargs.get("linkage")
        budget = kwargs.get("budget")
        correlation = kwargs.get("correlation_id")
        if (self._closed
                or purpose not in self._allowed_purposes
                or not isinstance(prompt, str)
                or len(prompt) > self._max_input_chars
                or not isinstance(linkage, Mapping)
                or not isinstance(correlation, str) or not correlation
                or correlation in self._correlations
                or (budget is not None and (
                    budget.max_input_chars > self._max_input_chars
                    or budget.max_output_chars > self._max_output_chars
                    or budget.max_new_tokens > self._max_new_tokens
                    or budget.timeout_seconds > self._max_timeout_seconds
                    or budget.max_calls_per_correlation != 1))):
            raise RootlessExperimentalError("ollama_experimental_session_request_out_of_scope")
        return self.invoker.build_request(**{
            **kwargs,
            "linkage": {**dict(linkage),
                "rootless_experimental_session": self.session_binding},
        })

    def invoke(self, request: Any, **kwargs: Any) -> Any:
        if (self._closed
                or request.purpose not in self._allowed_purposes
                or request.linkage.get("rootless_experimental_session")
                    != self.session_binding
                or request.correlation_id in self._correlations
                or request.budget.max_calls_per_correlation != 1
                or request.budget.max_new_tokens > self._max_new_tokens
                or request.budget.max_input_chars > self._max_input_chars
                or request.budget.max_output_chars > self._max_output_chars
                or request.budget.timeout_seconds > self._max_timeout_seconds
                or len(self._correlations) >= self._max_calls):
            raise RootlessExperimentalError("ollama_experimental_session_invocation_out_of_scope")
        if kwargs.get("persist", True) is not True:
            raise RootlessExperimentalError("developmental_session_receipt_custody_required")
        self._correlations.add(request.correlation_id)
        return self.invoker.invoke(request, **kwargs)

    def verify_persisted_invocation_receipt(
            self, receipt_id: str, receipt_digest: str, **expected: Any) -> Mapping[str, Any]:
        if not isinstance(receipt_id, str) or not ROOTLESS_RECEIPT_ID_RE.fullmatch(receipt_id):
            raise RootlessExperimentalError("developmental_receipt_identity_invalid")
        payload = _read_json(self.runtime_root / "receipts" / f"{receipt_id}.json",
            max_bytes=MAX_RECORD_BYTES)
        valid, _reasons = validate_receipt(payload)
        request = payload.get("request")
        linkage = request.get("linkage") if isinstance(request, Mapping) else None
        if (not valid or payload.get("receipt_id") != receipt_id
                or payload.get("receipt_digest") != receipt_digest
                or not isinstance(request, Mapping)
                or request.get("purpose")
                    not in self._allowed_purposes
                or request.get("active_model_identity") != self.active_model_identity
                or not isinstance(linkage, Mapping)
                or linkage.get("rootless_experimental_session") != self.session_binding
                or request.get("request_id") != expected.get("expected_request_id",
                    request.get("request_id"))
                or request.get("request_digest") != expected.get(
                    "expected_request_digest", request.get("request_digest"))):
            raise RootlessExperimentalError("developmental_receipt_verification_failed")
        if (expected.get("expected_active_model_identity") is not None
                and expected["expected_active_model_identity"] != self.active_model_identity):
            raise RootlessExperimentalError("developmental_receipt_model_identity_mismatch")
        return payload

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
                    reason_code=("rootless_experimental_developmental_complete"
                        if self.experimental_profile == "developmental_cognition_cycle"
                        else "rootless_experimental_epistemic_complete"))
                if receipt.status != "released":
                    raise RootlessExperimentalError(
                        "ollama_governed_release_unconfirmed")
            elif resident is not False:
                raise RootlessExperimentalError(
                    "ollama_residency_observation_unavailable")
        finally:
            self._governance_context.__exit__(None, None, None)


class RootlessExperimentalOllamaDevelopmentalSession(
        RootlessExperimentalOllamaEpistemicSession):
    """Governed Ollama session restricted to resident developmental cognition purposes."""

    def __init__(self, *, model_manifest_path: Path, model_name: str,
                 root: Path, session_binding: Mapping[str, Any],
                 kernel_factory: Any | None = None) -> None:
        super().__init__(model_manifest_path=model_manifest_path, model_name=model_name,
            root=root, session_binding=session_binding, kernel_factory=kernel_factory,
            developmental_cycle=True)
