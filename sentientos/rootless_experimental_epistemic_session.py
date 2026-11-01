"""Bounded rootless session for epistemic probes through the governed invoker.

This experimental adapter delegates every inference to the same local-model
authority and control-plane invoker used by the rootless smoke path. It loads
one verified CPU model, allows four unique calls, and grants no serving,
commissioning, provider, tool, memory, action, or production authority.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .control_plane_kernel import ControlPlaneKernel
from .governed_local_model_invocation import (
    GovernedLocalModelInvoker, LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
    validate_receipt,
)
from .local_model_authority import (
    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
    build_rootless_experimental_epistemic_authority_map, digest_payload,
)
from .local_runtime_provisioning import semantic_digest
from .local_model_runtime_worker import ExactRuntimeLocalModel
from .rootless_experimental_local_model import (
    EXPERIMENT_ROOT, MAX_RECORD_BYTES, RootlessExperimentalError,
    _no_symlink_path, _read_json, _rootless_governance_custody, _safe_child,
    validate_experiment_root, verify_model_manifest, verify_runtime_bundle,
)

MAX_CALLS = 4
MAX_CALL_TIMEOUT_SECONDS = 180
# The existing governed epistemic prompt is slightly over 8 KiB even for the
# smallest valid projection. Keep a fixed 16 KiB ceiling; the worker remains
# independently bounded to a 4,096-token context and 128 generated tokens.
MAX_PROMPT_CHARS = 16_384
MAX_OUTPUT_CHARS = 1024
MAX_NEW_TOKENS = 128
MAX_CONTEXT_TOKENS = 8192
MAX_CORRELATION_CHARS = 256
RECEIPT_ID_RE = re.compile(r"^lmrec-[0-9a-f]{24}$")


class RootlessExperimentalEpistemicSession:
    """Open one verified model and expose a four-call LocalModelInvoker."""

    def __init__(self, *, model_manifest_path: Path,
                 installation_receipt_path: Path, import_receipt_path: Path,
                 backend_receipt_path: Path, root: Path,
                 session_binding: Mapping[str, Any],
                 model_factory: Any = ExactRuntimeLocalModel,
                 kernel_factory: Any | None = None) -> None:
        self.root = validate_experiment_root(root)
        try:
            self.root.relative_to(EXPERIMENT_ROOT.resolve(strict=True))
        except (ValueError, OSError) as exc:
            raise RootlessExperimentalError(
                "epistemic_session_root_outside_rootless_experiment") from exc
        if (not isinstance(session_binding, Mapping)
                or session_binding.get("purpose")
                    != ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
                or session_binding.get("production_authority") is not False
                or session_binding.get("eligible_as_production_serving_evidence") is not False
                or session_binding.get("preregistration_digest") != "0" * 64
                or session_binding.get("active_model_identity_digest") != "0" * 64):
            raise RootlessExperimentalError("epistemic_session_binding_invalid")
        self.session_binding = dict(session_binding)
        manifest_path = _safe_child(EXPERIMENT_ROOT, Path(model_manifest_path))
        manifest = verify_model_manifest(_read_json(manifest_path),
            root=EXPERIMENT_ROOT)
        runtime = verify_runtime_bundle(
            installation_receipt_path=installation_receipt_path,
            import_receipt_path=import_receipt_path,
            backend_receipt_path=backend_receipt_path)
        artifact_path = Path(str(manifest["artifact_path"]))
        self.runtime_bundle_digest = semantic_digest({
            "runtime_id": runtime["runtime_id"],
            "runtime_receipt_digests": runtime["runtime_receipt_digests"],
            "interpreter_path": runtime["interpreter_path"]})
        if (manifest["manifest_digest"]
                != self.session_binding.get("model_manifest_digest")
                or self.runtime_bundle_digest
                    != self.session_binding.get("runtime_bundle_digest")):
            raise RootlessExperimentalError("epistemic_session_evidence_binding_mismatch")
        self.model_manifest = manifest
        self.runtime_bundle = runtime
        self.runtime_root = self.root / "inference-custody"
        _no_symlink_path(self.runtime_root)
        limits = {"n_ctx": MAX_CONTEXT_TOKENS, "n_gpu_layers": 0,
            "n_threads": 5, "max_new_tokens": MAX_NEW_TOKENS}
        model_config = ModelConfig(
            [ModelCandidate(artifact_path, "llama_cpp", manifest["model_id"],
                {"gpu_layers": 0, "n_threads": 5})],
            default_engine="llama_cpp", max_context_tokens=MAX_CONTEXT_TOKENS,
            generation=GenerationConfig(max_new_tokens=MAX_NEW_TOKENS,
                temperature=0, top_p=1))
        self.authority_map = build_rootless_experimental_epistemic_authority_map(
            model_config, allowed_roots=[artifact_path.parent])
        self.worker = model_factory({"model_id": manifest["model_id"],
            "artifact_path": str(artifact_path),
            "artifact_sha256": manifest["artifact_sha256"],
            "artifact_size_bytes": manifest["artifact_size_bytes"],
            "interpreter_path": runtime["interpreter_path"]}, limits,
            identity_posture="rootless_experimental")
        identity = self.worker.active_identity.to_dict()
        if (identity.get("posture") != "rootless_experimental"
                or identity.get("fallback") is not False
                or identity.get("model_content_sha256") != manifest["artifact_sha256"]
                or identity.get("artifact_size_bytes") != manifest["artifact_size_bytes"]
                or self.authority_map.record_for_active_identity(
                    self.worker.active_identity,
                    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE) is None):
            self.worker.close()
            raise RootlessExperimentalError("epistemic_session_model_identity_mismatch")
        self.active_model_identity = identity
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

    def bind_preregistration_digest(self, digest: str) -> Mapping[str, Any]:
        """Finalize the session binding after prompts and keys are sealed."""
        if (self._closed or self._correlations or self._preregistration_bound
                or not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise RootlessExperimentalError("epistemic_session_preregistration_binding_invalid")
        if self.session_binding.get("preregistration_digest") != "0" * 64:
            raise RootlessExperimentalError("epistemic_session_preregistration_already_set")
        preregistration = _read_json(self.root / "preregistration.json")
        claimed = preregistration.pop("preregistration_digest", None)
        if (claimed != digest or semantic_digest(preregistration) != digest
                or preregistration.get("run_id") != self.session_binding.get("run_id")
                or preregistration.get("session_id")
                    != self.session_binding.get("session_id")
                or preregistration.get("model_manifest_digest")
                    != self.session_binding.get("model_manifest_digest")
                or preregistration.get("runtime_bundle_digest")
                    != self.session_binding.get("runtime_bundle_digest")
                or preregistration.get("model_identity") != self.active_model_identity):
            raise RootlessExperimentalError(
                "epistemic_session_preregistration_record_mismatch")
        self.session_binding["preregistration_digest"] = digest
        self.session_binding["active_model_identity_digest"] = digest_payload(
            {"identity": self.active_model_identity})
        self._preregistration_bound = True
        return dict(self.session_binding)

    def build_request(self, **kwargs: Any) -> Any:
        purpose = kwargs.get("purpose")
        prompt = kwargs.get("prompt")
        caller = kwargs.get("caller")
        correlation_id = kwargs.get("correlation_id")
        lifecycle_phase = kwargs.get("lifecycle_phase", "runtime")
        expected_output_format = kwargs.get("expected_output_format", "text")
        budget = kwargs.get("budget")
        upstream_evidence = kwargs.get("upstream_evidence")
        linkage = kwargs.get("linkage")
        structured_output_schema = kwargs.get("structured_output_schema")
        if (self._closed or purpose != ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
                or not self._preregistration_bound
                or not isinstance(prompt, str) or len(prompt) > MAX_PROMPT_CHARS
                or (budget is not None and (
                    not isinstance(budget, LocalModelInvocationBudget)
                    or budget.max_input_chars > MAX_PROMPT_CHARS
                    or budget.max_output_chars > MAX_OUTPUT_CHARS
                    or budget.max_new_tokens > MAX_NEW_TOKENS
                    or budget.timeout_seconds > MAX_CALL_TIMEOUT_SECONDS
                    or budget.max_calls_per_correlation != 1))
                or not isinstance(caller, str)
                or not isinstance(correlation_id, str)
                or correlation_id in self._correlations
                or len(correlation_id) > MAX_CORRELATION_CHARS
                or not isinstance(linkage, Mapping)
                or linkage.get("rootless_experimental_session")
                    != self.session_binding):
            raise RootlessExperimentalError("epistemic_session_request_out_of_scope")
        if len(self._correlations) >= MAX_CALLS:
            raise RootlessExperimentalError("epistemic_session_call_budget_exhausted")
        return self.invoker.build_request(purpose=purpose, prompt=prompt,
            caller=caller, correlation_id=correlation_id,
            lifecycle_phase=lifecycle_phase,
            expected_output_format=expected_output_format, budget=budget,
            upstream_evidence={**dict(upstream_evidence or {}),
                "rootless_epistemic_session_id": self.session_binding["session_id"],
                "rootless_epistemic_preregistration_digest":
                    self.session_binding["preregistration_digest"],
                "rootless_epistemic_model_manifest_digest":
                    self.session_binding["model_manifest_digest"],
                "rootless_epistemic_runtime_bundle_digest":
                    self.session_binding["runtime_bundle_digest"]},
            linkage={**dict(linkage),
                "rootless_experimental_session": self.session_binding},
            structured_output_schema=structured_output_schema)

    def observed_current_model_identity(self) -> Mapping[str, Any]:
        """Return the identity bound by the loaded worker, without inference."""
        return dict(self.active_model_identity)

    def measured_process_resources(self) -> Mapping[str, Any]:
        """Report worker process totals; these are not per-call measurements."""
        peak_rss_kib = getattr(self.worker, "peak_rss_kib", None)
        return {"measurement_source":
                "llama-cpp-python worker resource.getrusage(RUSAGE_SELF)",
            "platform": "linux",
            "peak_rss_bytes": peak_rss_kib * 1024
                if type(peak_rss_kib) is int else None,
            "worker_user_cpu_seconds": getattr(self.worker,
                "user_cpu_seconds", None),
            "worker_system_cpu_seconds": getattr(self.worker,
                "system_cpu_seconds", None),
            "measurement_scope": "cumulative_loaded_session_not_per_invocation"}

    def invoke(self, request: Any, **kwargs: Any) -> LocalModelInvocationReceipt:
        if (self._closed
                or request.purpose != ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
                or request.linkage.get("rootless_experimental_session")
                    != self.session_binding
                or request.correlation_id in self._correlations
                or request.budget.max_calls_per_correlation != 1
                or request.budget.max_new_tokens > MAX_NEW_TOKENS
                or request.budget.max_input_chars > MAX_PROMPT_CHARS
                or request.budget.max_output_chars > MAX_OUTPUT_CHARS):
            raise RootlessExperimentalError("epistemic_session_invocation_out_of_scope")
        if len(self._correlations) >= MAX_CALLS:
            raise RootlessExperimentalError("epistemic_session_call_budget_exhausted")
        self._correlations.add(request.correlation_id)
        persist = kwargs.pop("persist", True)
        include_output = kwargs.pop("include_output_in_receipt", True)
        if persist is not True or include_output is not True:
            raise RootlessExperimentalError(
                "epistemic_session_receipt_custody_required")
        return self.invoker.invoke(request, persist=True,
            include_output_in_receipt=True, **kwargs)

    def verify_persisted_invocation_receipt(
            self, receipt_id: str, receipt_digest: str, **expected: Any) -> Mapping[str, Any]:
        if not isinstance(receipt_id, str) or not RECEIPT_ID_RE.fullmatch(receipt_id):
            raise RootlessExperimentalError("epistemic_receipt_identity_invalid")
        receipt_path = self.runtime_root / "receipts" / f"{receipt_id}.json"
        payload = _read_json(receipt_path, max_bytes=MAX_RECORD_BYTES)
        valid, reasons = validate_receipt(payload)
        request_payload = payload.get("request")
        if (not valid or payload.get("receipt_id") != receipt_id
                or payload.get("receipt_digest") != receipt_digest
                or not isinstance(request_payload, Mapping)
                or any(request_payload.get(key) != value for key, value in expected.items()
                    if key in {"request_id", "request_digest"})
                or request_payload.get("purpose")
                    != ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
                or request_payload.get("active_model_identity")
                    != self.active_model_identity
                or request_payload.get("linkage", {}).get(
                    "rootless_experimental_session") != self.session_binding):
            raise RootlessExperimentalError("epistemic_receipt_verification_failed")
        if (expected.get("expected_active_model_identity") is not None
                and expected["expected_active_model_identity"]
                    != self.active_model_identity):
            raise RootlessExperimentalError("epistemic_receipt_model_identity_mismatch")
        return payload

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.worker.close()
        finally:
            self._governance_context.__exit__(None, None, None)

    def __enter__(self) -> RootlessExperimentalEpistemicSession:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()
