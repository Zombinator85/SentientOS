"""One-shot, explicitly non-production local-model inference in writable workspace custody."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .control_plane_kernel import ControlPlaneKernel
from .governed_local_model_invocation import (
    GovernedLocalModelInvoker, LocalModelInvocationBudget, LocalModelInvocationReceipt,
    validate_receipt,
)
from .local_model_authority import (
    ROOTLESS_EXPERIMENTAL_PURPOSE, build_rootless_experimental_model_authority_map,
    digest_payload,
)
from .local_model_runtime_worker import ExactRuntimeLocalModel
from .local_runtime_provisioning import semantic_digest

WORKSPACE_ROOT = Path("/workspace")
EXPERIMENT_ROOT = WORKSPACE_ROOT / "sentientos-data" / "rootless-experimental"
MODEL_MANIFEST_SCHEMA = "sentientos.rootless_experimental_model_artifact:v1"
INTENT_SCHEMA = "sentientos.rootless_experimental_inference_intent:v1"
RECEIPT_SCHEMA = "sentientos.rootless_experimental_inference_receipt:v1"
PRINCIPAL = "deterministic_rootless_experimental_local_model_controller"
MAX_CONTEXT_TOKENS = 512
MAX_NEW_TOKENS = 16
MAX_PROMPT_CHARS = 2048
MAX_OUTPUT_CHARS = 1024
MAX_MODEL_BYTES = 8 * 1024 * 1024 * 1024
MAX_RECORD_BYTES = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


class RootlessExperimentalError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _digest_file(path: Path, *, max_bytes: int = MAX_MODEL_BYTES) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise RootlessExperimentalError("artifact_exceeds_size_bound")
            digest.update(chunk)
    return digest.hexdigest(), size


def _no_symlink_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            if current.is_symlink():
                raise RootlessExperimentalError("symlinked_experimental_path")
        except OSError as exc:
            raise RootlessExperimentalError("experimental_path_unavailable") from exc
    return absolute


def validate_experiment_root(root: Path, *, workspace_root: Path | None = None) -> Path:
    base = _no_symlink_path(workspace_root or WORKSPACE_ROOT).resolve(strict=True)
    candidate = _no_symlink_path(root)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise RootlessExperimentalError("experimental_root_outside_workspace") from exc
    if candidate == base:
        raise RootlessExperimentalError("experimental_root_must_be_dedicated")
    return candidate


def _safe_child(root: Path, path: Path) -> Path:
    candidate = _no_symlink_path(path)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RootlessExperimentalError("experimental_path_escape") from exc
    return candidate


def _read_json(path: Path, *, max_bytes: int = MAX_RECORD_BYTES) -> dict[str, Any]:
    try:
        if path.is_symlink() or path.stat().st_size > max_bytes:
            raise RootlessExperimentalError("evidence_file_invalid")
        value = json.loads(path.read_text(encoding="utf-8"))
    except RootlessExperimentalError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RootlessExperimentalError("evidence_file_unavailable") from exc
    if not isinstance(value, dict):
        raise RootlessExperimentalError("evidence_must_be_object")
    return value


def _exclusive_json(path: Path, value: Mapping[str, Any], *, root: Path) -> None:
    target = _safe_child(root, path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _no_symlink_path(target.parent)
    payload = _canonical(value)
    if len(payload) > MAX_RECORD_BYTES:
        raise RootlessExperimentalError("evidence_record_over_bound")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise RootlessExperimentalError("one_shot_evidence_already_exists") from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def verify_model_manifest(manifest: Mapping[str, Any], *, root: Path) -> dict[str, Any]:
    value = dict(manifest)
    claimed = value.pop("manifest_digest", None)
    if claimed != semantic_digest(value):
        raise RootlessExperimentalError("model_manifest_digest_invalid")
    value["manifest_digest"] = claimed
    required = {
        "schema_version", "model_id", "repo_id", "repo_revision", "file_revision", "filename",
        "artifact_path", "source_url", "model_card_url", "model_card_path", "model_card_sha256",
        "license_id", "license_url", "license_file_path", "license_file_sha256", "artifact_sha256",
        "artifact_size_bytes", "retrieved_at", "retrieval_final_host", "huggingface_lfs_oid", "manifest_digest",
    }
    if set(value) != required or value.get("schema_version") != MODEL_MANIFEST_SCHEMA:
        raise RootlessExperimentalError("model_manifest_schema_invalid")
    if (not isinstance(value.get("model_id"), str) or not value["model_id"].strip()
            or not isinstance(value.get("repo_id"), str) or "/" not in value["repo_id"]
            or not REVISION_RE.fullmatch(str(value.get("repo_revision", "")))
            or not REVISION_RE.fullmatch(str(value.get("file_revision", "")))
            or not isinstance(value.get("filename"), str) or Path(value["filename"]).name != value["filename"]
            or not SHA256_RE.fullmatch(str(value.get("artifact_sha256", "")))
            or value.get("huggingface_lfs_oid") != value.get("artifact_sha256")
            or type(value.get("artifact_size_bytes")) is not int
            or not 1 <= value["artifact_size_bytes"] <= MAX_MODEL_BYTES
            or value.get("license_id") not in {"apache-2.0", "mit"}):
        raise RootlessExperimentalError("model_manifest_identity_invalid")
    repo = str(value["repo_id"])
    revision = str(value["repo_revision"])
    filename = str(value["filename"])
    expected_source = f"https://huggingface.co/{repo}/resolve/{revision}/{filename}"
    expected_license = f"https://huggingface.co/{repo}/blob/{revision}/LICENSE"
    if value.get("source_url") != expected_source or value.get("license_url") != expected_license:
        raise RootlessExperimentalError("model_manifest_source_binding_invalid")
    expected_card = f"https://huggingface.co/{repo}/resolve/{revision}/README.md"
    if value.get("model_card_url") != expected_card:
        raise RootlessExperimentalError("model_manifest_card_source_invalid")
    try:
        retrieved = datetime.fromisoformat(str(value.get("retrieved_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RootlessExperimentalError("model_manifest_timestamp_invalid") from exc
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise RootlessExperimentalError("model_manifest_timestamp_invalid")
    artifact = _safe_child(root, Path(str(value["artifact_path"])))
    if artifact.name != filename or not artifact.is_file():
        raise RootlessExperimentalError("model_artifact_unavailable")
    digest, size = _digest_file(artifact)
    if digest != value["artifact_sha256"] or size != value["artifact_size_bytes"]:
        raise RootlessExperimentalError("model_artifact_integrity_mismatch")
    license_path = _safe_child(root, Path(str(value["license_file_path"])))
    card_path = _safe_child(root, Path(str(value["model_card_path"])))
    try:
        license_bytes = license_path.read_bytes()
        card_bytes = card_path.read_bytes()
    except OSError as exc:
        raise RootlessExperimentalError("model_license_or_card_unavailable") from exc
    if (hashlib.sha256(license_bytes).hexdigest() != value["license_file_sha256"]
            or hashlib.sha256(card_bytes).hexdigest() != value["model_card_sha256"]):
        raise RootlessExperimentalError("model_license_or_card_digest_mismatch")
    license_text = license_bytes.decode("utf-8", "replace")
    card_text = card_bytes.decode("utf-8", "replace").lower()
    if (value["license_id"] == "apache-2.0"
            and ("apache license" not in license_text.lower() or "version 2.0" not in license_text.lower())):
        raise RootlessExperimentalError("model_license_text_mismatch")
    if f"license: {value['license_id']}" not in card_text:
        raise RootlessExperimentalError("model_card_license_mismatch")
    return {**value, "artifact_path": str(artifact), "verified_artifact_sha256": digest,
        "verified_artifact_size_bytes": size}


def _verify_runtime_receipt(path: Path, schema: str, *, root: Path) -> dict[str, Any]:
    receipt_path = _no_symlink_path(path)
    if not receipt_path.is_file():
        raise RootlessExperimentalError("runtime_receipt_unavailable")
    receipt = _read_json(receipt_path)
    if receipt.get("schema_version") != schema:
        raise RootlessExperimentalError("runtime_receipt_schema_invalid")
    claimed = receipt.get("receipt_semantic_digest")
    body = {key: value for key, value in receipt.items() if key != "receipt_semantic_digest"}
    if claimed != semantic_digest(body):
        raise RootlessExperimentalError("runtime_receipt_digest_invalid")
    return receipt


def verify_runtime_bundle(*, installation_receipt_path: Path, import_receipt_path: Path,
                          backend_receipt_path: Path) -> dict[str, Any]:
    installed = _verify_runtime_receipt(installation_receipt_path,
        "sentientos.local_runtime_installation_receipt:v1", root=WORKSPACE_ROOT)
    imported = _verify_runtime_receipt(import_receipt_path,
        "sentientos.local_runtime_import_verification_receipt:v1", root=WORKSPACE_ROOT)
    backend = _verify_runtime_receipt(backend_receipt_path,
        "sentientos.local_runtime_backend_verification_receipt:v1", root=WORKSPACE_ROOT)
    if (installed.get("status") != "installed_verified" or installed.get("runtime_installed") is not True
            or installed.get("engine") != "llama_cpp" or installed.get("backend_family") != "cpu"
            or installed.get("runtime_id") != "llama-cpp-python-0.3.35-cpu-linux-x86_64"
            or not any(isinstance(item, Mapping) and item.get("package") == "llama-cpp-python"
                and item.get("version") == "0.3.35" for item in installed.get("artifacts", []))
            or installed.get("model_load_performed") is not False
            or installed.get("commissioning_performed") is not False
            or installed.get("runtime_execution_authority_granted") is not False
            or imported.get("status") != "runtime_import_verified"
            or imported.get("runtime_available_for_import") is not True
            or imported.get("runtime_import_performed") is not True
            or imported.get("model_load_performed") is not False
            or imported.get("commissioning_performed") is not False
            or imported.get("installation_receipt_semantic_digest") != installed.get("receipt_semantic_digest")
            or backend.get("status") != "runtime_backend_verified"
            or backend.get("selected_backend") != "CPU"
            or backend.get("selected_backend_verified") is not True
            or backend.get("native_runtime_library_loaded") is not True
            or backend.get("inference_performed") is not False
            or backend.get("model_load_performed") is not False
            or backend.get("commissioning_performed") is not False
            or backend.get("runtime_execution_authority_granted") is not False
            or backend.get("installation_receipt_semantic_digest") != installed["receipt_semantic_digest"]
            or backend.get("runtime_import_verification_receipt_semantic_digest") != imported["receipt_semantic_digest"]):
        raise RootlessExperimentalError("runtime_evidence_chain_invalid")
    interpreter = installed.get("venv_interpreter_identity", {}).get("executable")
    if not isinstance(interpreter, str) or not Path(interpreter).is_file() or not os.access(interpreter, os.X_OK):
        raise RootlessExperimentalError("runtime_interpreter_unavailable")
    paths = {"installation_receipt_path": str(_no_symlink_path(installation_receipt_path)),
        "import_receipt_path": str(_no_symlink_path(import_receipt_path)),
        "backend_receipt_path": str(_no_symlink_path(backend_receipt_path))}
    for path in paths.values():
        _no_symlink_path(Path(path)).relative_to(WORKSPACE_ROOT.resolve(strict=True))
    return {"installation_receipt": installed, "import_receipt": imported,
        "backend_receipt": backend, "interpreter_path": str(Path(interpreter).resolve(strict=True)),
        "paths": paths, "runtime_id": installed["runtime_id"],
        "runtime_receipt_digests": {"installation": installed["receipt_semantic_digest"],
            "import": imported["receipt_semantic_digest"], "backend": backend["receipt_semantic_digest"]}}


def _runtime_bundle_digest(bundle: Mapping[str, Any]) -> str:
    return semantic_digest({"runtime_id": bundle["runtime_id"],
        "runtime_receipt_digests": dict(bundle["runtime_receipt_digests"]),
        "interpreter_path": bundle["interpreter_path"]})


def prepare_intent(*, model_manifest_path: Path, installation_receipt_path: Path,
                   import_receipt_path: Path, backend_receipt_path: Path, prompt: str,
                   root: Path = EXPERIMENT_ROOT, correlation_id: str | None = None) -> dict[str, Any]:
    root = validate_experiment_root(root)
    manifest_path = _safe_child(root, model_manifest_path)
    manifest = verify_model_manifest(_read_json(manifest_path), root=root)
    runtime = verify_runtime_bundle(installation_receipt_path=installation_receipt_path,
        import_receipt_path=import_receipt_path, backend_receipt_path=backend_receipt_path)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        raise RootlessExperimentalError("prompt_out_of_bounds")
    correlation = correlation_id or "rootless-experiment-" + uuid.uuid4().hex
    if not re.fullmatch(r"rootless-experiment-[0-9a-f]{32}", correlation):
        raise RootlessExperimentalError("correlation_id_invalid")
    limits = {"n_ctx": MAX_CONTEXT_TOKENS, "n_gpu_layers": 0, "n_threads": 5,
        "max_new_tokens": MAX_NEW_TOKENS, "max_input_chars": MAX_PROMPT_CHARS,
        "max_output_chars": MAX_OUTPUT_CHARS, "timeout_seconds": 90.0,
        "max_calls_per_correlation": 1, "temperature": 0.0, "top_p": 1.0}
    body: dict[str, Any] = {"schema_version": INTENT_SCHEMA, "status": "rootless_experimental_intent_prepared",
        "intent_id": "rootless-experimental-intent-" + uuid.uuid4().hex[:24],
        "correlation_id": correlation, "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": ROOTLESS_EXPERIMENTAL_PURPOSE,
        "operator_authorization_basis": "explicit user instruction in Codex task; no cryptographic identity asserted",
        "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "model_manifest_path": str(manifest_path), "model_manifest_digest": manifest["manifest_digest"],
        "model_id": manifest["model_id"], "artifact_path": manifest["artifact_path"],
        "artifact_sha256": manifest["artifact_sha256"], "artifact_size_bytes": manifest["artifact_size_bytes"],
        "license_id": manifest["license_id"], "source_url": manifest["source_url"],
        "runtime_bundle": {"runtime_id": runtime["runtime_id"],
            "runtime_receipt_digests": runtime["runtime_receipt_digests"],
            "interpreter_path": runtime["interpreter_path"],
            "receipt_paths": runtime["paths"]},
        "limits": limits, "production_authority": False, "experimental_rootless": True,
        "ephemeral_environment": True, "eligible_as_production_commissioning_evidence": False,
        "eligible_as_production_serving_evidence": False, "eligible_as_native_subagent_evidence": False,
        "eligible_as_astra_evidence": False}
    body["intent_digest"] = semantic_digest(body)
    intent_path = root / "intents" / f"{body['intent_id']}.json"
    _exclusive_json(intent_path, body, root=root)
    return body


def verify_intent(value: Mapping[str, Any], *, root: Path) -> dict[str, Any]:
    body = dict(value)
    claimed = body.pop("intent_digest", None)
    if claimed != semantic_digest(body):
        raise RootlessExperimentalError("intent_digest_invalid")
    body["intent_digest"] = claimed
    limits = body.get("limits")
    if (body.get("schema_version") != INTENT_SCHEMA or body.get("status") != "rootless_experimental_intent_prepared"
            or body.get("purpose") != ROOTLESS_EXPERIMENTAL_PURPOSE
            or body.get("production_authority") is not False
            or body.get("experimental_rootless") is not True
            or body.get("ephemeral_environment") is not True
            or body.get("eligible_as_production_commissioning_evidence") is not False
            or body.get("eligible_as_production_serving_evidence") is not False
            or body.get("eligible_as_native_subagent_evidence") is not False
            or body.get("eligible_as_astra_evidence") is not False
            or not isinstance(limits, Mapping)
            or limits.get("n_ctx") != MAX_CONTEXT_TOKENS or limits.get("n_gpu_layers") != 0
            or limits.get("n_threads") != 5 or limits.get("max_new_tokens") != MAX_NEW_TOKENS
            or limits.get("max_calls_per_correlation") != 1 or limits.get("temperature") != 0.0
            or limits.get("top_p") != 1.0):
        raise RootlessExperimentalError("intent_scope_or_limit_invalid")
    return body


@contextmanager
def _rootless_governance_custody(run_root: Path) -> Iterator[None]:
    """Route governance runtime state into this run without changing policy."""
    values = {
        "SENTIENTOS_GOVERNOR_ROOT": str(run_root / "governor"),
        "SENTIENTOS_FEDERATION_ROOT": str(run_root / "federation"),
        "PULSE_TRUST_EPOCH_ROOT": str(run_root / "pulse-trust-epoch"),
        "PULSE_TRUST_EPOCH_STATE": str(run_root / "pulse-trust-epoch" / "epoch_state.json"),
    }
    prior = {key: os.environ.get(key) for key in values}
    # These singleton helpers capture their roots at construction. Rebind them
    # only for this one-shot scope, then restore the controller's prior objects.
    import sentientos.federated_governance as federation_module
    import sentientos.trust_ledger as trust_ledger_module

    prior_controller = federation_module.get_controller()
    prior_ledger = trust_ledger_module.get_trust_ledger()
    os.environ.update(values)
    federation_module.reset_controller()
    trust_ledger_module.reset_trust_ledger()
    try:
        yield
    finally:
        federation_module._CONTROLLER = prior_controller
        trust_ledger_module._LEDGER = prior_ledger
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _resource_governed_kernel(run_root: Path) -> ControlPlaneKernel:
    from .runtime_governor import RuntimeGovernor
    governor = RuntimeGovernor()
    return ControlPlaneKernel(runtime_governor=governor,
        decisions_path=run_root / "control-plane" / "decisions.jsonl")


def execute_intent(*, intent_path: Path, confirm_intent_digest: str,
                   model_manifest_path: Path, installation_receipt_path: Path,
                   import_receipt_path: Path, backend_receipt_path: Path,
                   root: Path = EXPERIMENT_ROOT,
                   model_factory: Callable[..., Any] = ExactRuntimeLocalModel,
                   kernel_factory: Callable[[Path], Any] = _resource_governed_kernel) -> dict[str, Any]:
    root = validate_experiment_root(root)
    intent_file = _safe_child(root, intent_path)
    intent = verify_intent(_read_json(intent_file), root=root)
    if confirm_intent_digest != intent["intent_digest"]:
        raise RootlessExperimentalError("intent_confirmation_mismatch")
    manifest_file = _safe_child(root, model_manifest_path)
    manifest = verify_model_manifest(_read_json(manifest_file), root=root)
    runtime = verify_runtime_bundle(installation_receipt_path=installation_receipt_path,
        import_receipt_path=import_receipt_path, backend_receipt_path=backend_receipt_path)
    if (manifest["manifest_digest"] != intent["model_manifest_digest"]
            or manifest["artifact_sha256"] != intent["artifact_sha256"]
            or _runtime_bundle_digest(runtime) != semantic_digest({
                "runtime_id": intent["runtime_bundle"]["runtime_id"],
                "runtime_receipt_digests": intent["runtime_bundle"]["runtime_receipt_digests"],
                "interpreter_path": intent["runtime_bundle"]["interpreter_path"]})
            or runtime["runtime_receipt_digests"] != intent["runtime_bundle"]["runtime_receipt_digests"]
            or runtime["interpreter_path"] != intent["runtime_bundle"]["interpreter_path"]):
        raise RootlessExperimentalError("intent_evidence_changed")
    run_root = root / "runs" / intent["intent_id"]
    run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _no_symlink_path(run_root)
    attempt_path = run_root / "inference-attempt.json"
    _exclusive_json(attempt_path, {"schema_version": "sentientos.rootless_experimental_attempt:v1",
        "intent_id": intent["intent_id"], "intent_digest": intent["intent_digest"],
        "started_at": datetime.now(timezone.utc).isoformat(), "inference_attempted": True}, root=root)
    chain = {"model_id": intent["model_id"], "artifact_path": intent["artifact_path"],
        "artifact_sha256": intent["artifact_sha256"], "artifact_size_bytes": intent["artifact_size_bytes"],
        "interpreter_path": runtime["interpreter_path"]}
    limits = dict(intent["limits"])
    load = {key: limits[key] for key in ("n_ctx", "n_gpu_layers", "n_threads", "max_new_tokens")}
    worker = None
    started = datetime.now(timezone.utc)
    failure: str | None = None
    invocation: LocalModelInvocationReceipt | None = None
    invocation_payload: dict[str, Any] | None = None
    observed_identity: dict[str, Any] | None = None
    resource_measurement: dict[str, Any] = {}
    try:
        worker = model_factory(chain, load, identity_posture="rootless_experimental")
        observed_identity = worker.active_identity.to_dict()
        model_config = ModelConfig(
            [ModelCandidate(Path(intent["artifact_path"]), "llama_cpp", intent["model_id"],
                {"gpu_layers": limits["n_gpu_layers"], "n_threads": limits["n_threads"]})],
            default_engine="llama_cpp", max_context_tokens=limits["n_ctx"],
            generation=GenerationConfig(max_new_tokens=limits["max_new_tokens"], temperature=0, top_p=1))
        authority = build_rootless_experimental_model_authority_map(
            model_config, allowed_roots=[Path(intent["artifact_path"]).parent])
        authority_record = authority.record_for_active_identity(worker.active_identity,
            ROOTLESS_EXPERIMENTAL_PURPOSE)
        if (authority_record is None or observed_identity.get("posture") != "rootless_experimental"
                or observed_identity.get("fallback") is not False
                or observed_identity.get("model_content_sha256") != intent["artifact_sha256"]
                or observed_identity.get("artifact_size_bytes") != intent["artifact_size_bytes"]):
            raise RootlessExperimentalError("loaded_model_identity_mismatch")
        with _rootless_governance_custody(run_root):
            invoker = GovernedLocalModelInvoker(model=worker, authority_map=authority,
                kernel=kernel_factory(run_root), runtime_root=run_root / "inference-custody")
            request = invoker.build_request(purpose=ROOTLESS_EXPERIMENTAL_PURPOSE,
                prompt=intent["prompt"], caller=PRINCIPAL, correlation_id=intent["correlation_id"],
                budget=LocalModelInvocationBudget(max_input_chars=limits["max_input_chars"],
                    max_output_chars=limits["max_output_chars"], max_new_tokens=limits["max_new_tokens"],
                    timeout_seconds=limits["timeout_seconds"], max_calls_per_correlation=1),
                upstream_evidence={"rootless_experimental_intent_id": intent["intent_id"],
                    "rootless_experimental_intent_digest": intent["intent_digest"],
                    "model_manifest_digest": manifest["manifest_digest"],
                    "runtime_bundle_digest": _runtime_bundle_digest(runtime)},
                linkage={"experimental_rootless": True,
                    "eligible_as_production_commissioning_evidence": False})
            invocation = invoker.invoke(request, persist=True, include_output_in_receipt=True)
        invocation_payload = invocation.to_dict(include_output=True)
        valid_invocation, reasons = validate_receipt(invocation_payload)
        if not valid_invocation:
            raise RootlessExperimentalError("inference_receipt_invalid:" + ",".join(reasons))
        resource_measurement = {
            "measurement_source": "llama-cpp-python worker resource.getrusage(RUSAGE_SELF)",
            "platform": "linux", "peak_rss_bytes": (worker.peak_rss_kib * 1024
                if type(worker.peak_rss_kib) is int else None),
            "worker_user_cpu_seconds": worker.user_cpu_seconds,
            "worker_system_cpu_seconds": worker.system_cpu_seconds,
            "inference_latency_ms": invocation.latency_ms,
        }
        atomic_invocation_path = run_root / "sentientos-invocation-receipt.json"
        _exclusive_json(atomic_invocation_path, invocation_payload, root=root)
        if (invocation.status != "admitted_completed" or invocation.fallback_occurred
                or invocation.effects.get("local_model_inference") is not True
                or any(bool(invocation.effects.get(name)) for name in
                    ("provider_network", "tool", "memory", "action", "adoption", "repository_mutation"))
                or not invocation.output_text):
            failure = "inference_not_completed"
    except Exception as exc:
        failure = getattr(exc, "code", None) or type(exc).__name__
    finally:
        if worker is not None:
            try:
                worker.close()
            except Exception:
                failure = failure or "worker_close_failed"
    ended = datetime.now(timezone.utc)
    if invocation is not None and not resource_measurement:
        resource_measurement = {"measurement_source": "llama-cpp-python worker resource.getrusage(RUSAGE_SELF)",
            "platform": "linux", "peak_rss_bytes": (worker.peak_rss_kib * 1024
                if worker is not None and type(getattr(worker, "peak_rss_kib", None)) is int else None),
            "worker_user_cpu_seconds": getattr(worker, "user_cpu_seconds", None),
            "worker_system_cpu_seconds": getattr(worker, "system_cpu_seconds", None),
            "inference_latency_ms": invocation.latency_ms}
    output_text = invocation.output_text if invocation is not None else None
    if invocation is not None:
        invocation_payload = invocation.to_dict(include_output=True)
    body: dict[str, Any] = {"schema_version": RECEIPT_SCHEMA,
        "status": "rootless_experimental_inference_completed" if failure is None else "rootless_experimental_inference_blocked",
        "failure_code": failure, "intent_id": intent["intent_id"], "intent_digest": intent["intent_digest"],
        "correlation_id": intent["correlation_id"], "purpose": ROOTLESS_EXPERIMENTAL_PURPOSE,
        "operator_authorization_basis": intent["operator_authorization_basis"],
        "model_id": intent["model_id"], "model_manifest_path": intent["model_manifest_path"],
        "model_manifest_digest": manifest["manifest_digest"],
        "model_source": {key: manifest[key] for key in ("repo_id", "repo_revision", "file_revision",
            "filename", "source_url", "license_id", "license_url", "artifact_sha256", "artifact_size_bytes")},
        "runtime_id": runtime["runtime_id"], "runtime_bundle_digest": _runtime_bundle_digest(runtime),
        "runtime_receipt_digests": runtime["runtime_receipt_digests"],
        "runtime_interpreter_path": runtime["interpreter_path"],
        "worker_identity": observed_identity,
        "prompt": intent["prompt"], "prompt_sha256": intent["prompt_sha256"],
        "raw_response": output_text,
        "raw_response_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest()
            if output_text is not None else None,
        "inference_receipt": invocation_payload,
        "resource_measurements": resource_measurement,
        "started_at": started.isoformat(), "ended_at": ended.isoformat(),
        "execution_budget": limits, "inference_attempted": True,
        "worker_unloaded": True,
        "production_authority": False, "experimental_rootless": True,
        "ephemeral_environment": True,
        "eligible_as_production_commissioning_evidence": False,
        "eligible_as_production_serving_evidence": False,
        "eligible_as_native_subagent_evidence": False, "eligible_as_astra_evidence": False}
    body["receipt_digest"] = semantic_digest(body)
    receipt_path = run_root / "rootless-experimental-inference-receipt.json"
    _exclusive_json(receipt_path, body, root=root)
    return body


def verify_rootless_receipt(receipt: Mapping[str, Any], *, root: Path) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    body = dict(receipt)
    claimed = body.pop("receipt_digest", None)
    if claimed != semantic_digest(body):
        reasons.append("receipt_digest_mismatch")
    if (receipt.get("schema_version") != RECEIPT_SCHEMA
            or receipt.get("production_authority") is not False
            or receipt.get("experimental_rootless") is not True
            or receipt.get("ephemeral_environment") is not True
            or receipt.get("eligible_as_production_commissioning_evidence") is not False
            or receipt.get("eligible_as_production_serving_evidence") is not False
            or receipt.get("eligible_as_native_subagent_evidence") is not False
            or receipt.get("eligible_as_astra_evidence") is not False):
        reasons.append("receipt_scope_invalid")
    try:
        root = validate_experiment_root(root)
        manifest_path = _safe_child(root, Path(str(receipt["model_manifest_path"])))
        manifest = verify_model_manifest(_read_json(manifest_path), root=root)
        if manifest["manifest_digest"] != receipt.get("model_manifest_digest"):
            reasons.append("receipt_model_manifest_mismatch")
    except (KeyError, RootlessExperimentalError):
        reasons.append("receipt_model_manifest_invalid")
    response = receipt.get("raw_response")
    if response is not None and hashlib.sha256(str(response).encode("utf-8")).hexdigest() != receipt.get("raw_response_sha256"):
        reasons.append("response_digest_mismatch")
    inference = receipt.get("inference_receipt")
    if isinstance(inference, Mapping):
        valid, inference_reasons = validate_receipt(inference)
        if not valid:
            reasons.extend("inference_" + item for item in inference_reasons)
        if inference.get("output_text") != response:
            reasons.append("response_invocation_mismatch")
        if inference.get("status") == "admitted_completed" and inference.get("effects", {}).get("local_model_inference") is not True:
            reasons.append("inference_effect_missing")
    else:
        reasons.append("inference_receipt_missing")
    return not reasons, reasons
