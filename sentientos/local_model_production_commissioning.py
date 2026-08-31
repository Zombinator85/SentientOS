"""Production custody bridge from acquired GGUF to governed local chat.

The acquisition organ remains byte custody only.  This module reconstructs that
entire chain, performs a zero-generation compatibility construction, requires a
digest-bound operator authorization, and keeps activation separate.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget
from .local_model import LocalModel
from .local_model_artifact_acquisition import compose_acquisition_plan, verify_acquisition_receipt
from .local_model_authority import build_local_model_authority_map
from .local_runtime_backend_verification import compose_verification_plan as compose_backend_plan
from .local_runtime_provisioning import semantic_digest

COMPATIBILITY_SCHEMA = "sentientos.local_model_compatibility_receipt:v1"
PLAN_SCHEMA = "sentientos.local_model_commissioning_plan:v2"
AUTHORIZATION_SCHEMA = "sentientos.local_model_commissioning_authorization:v2"
RECEIPT_SCHEMA = "sentientos.local_model_commissioning_receipt:v2"
ACTIVATION_SCHEMA = "sentientos.local_model_activation:v1"
SMOKE_PROMPT_ID = "sentientos.local_model_commissioning_smoke:v1"
SMOKE_PROMPT = "Reply with one short confirmation token."
DENIED = {key: False for key in ("provider_network", "tool", "memory", "action", "adoption", "repository_mutation", "autonomous_invocation", "background_inference")}


class ProductionCommissioningError(RuntimeError):
    pass


def _digest_file(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk); size += len(chunk)
    return digest.hexdigest(), size


def _validate_digest(value: Mapping[str, Any], key: str, code: str) -> None:
    copy = dict(value); claimed = copy.pop(key, None)
    if claimed != semantic_digest(copy):
        raise ProductionCommissioningError(code)


def reconstruct_chain(*, selection: Mapping[str, Any], runtime_provisioning: Mapping[str, Any],
        installation_plan: Mapping[str, Any], installation_receipt: Mapping[str, Any],
        import_plan: Mapping[str, Any], import_receipt: Mapping[str, Any],
        backend_plan: Mapping[str, Any], backend_receipt: Mapping[str, Any],
        catalog: Mapping[str, Any], acquisition_plan: Mapping[str, Any],
        acquisition_receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Recompose canonical APIs instead of trusting receipt summary fields."""
    expected_backend = compose_backend_plan(runtime_provisioning, installation_plan,
        installation_receipt, import_plan, import_receipt, backend_plan["verification_receipt_root"])
    if dict(backend_plan) != expected_backend:
        raise ProductionCommissioningError("backend_plan_substituted")
    expected_acquisition = compose_acquisition_plan(selection, runtime_provisioning,
        backend_receipt, catalog, acquisition_plan["escrow_root"])
    if dict(acquisition_plan) != expected_acquisition or not verify_acquisition_receipt(acquisition_receipt, expected_acquisition):
        raise ProductionCommissioningError("acquisition_chain_invalid")
    _validate_digest(backend_receipt, "receipt_semantic_digest", "backend_receipt_tampered")
    artifact = (Path(str(acquisition_plan["escrow_root"])) /
                str(acquisition_plan["final_relative_escrow_path"]) /
                str(acquisition_plan["artifact_filename"])).resolve(strict=True)
    digest, size = _digest_file(artifact)
    if digest != acquisition_plan["artifact_sha256"] or size != acquisition_plan["artifact_size_bytes"]:
        raise ProductionCommissioningError("acquired_artifact_stale")
    return {
        "catalog_digest": acquisition_plan["local_model_catalog_digest"],
        "selection_digest": acquisition_plan["selection_plan_digest"],
        "provisioning_digest": runtime_provisioning["provisioning_plan_digest"],
        "installation_plan_digest": installation_plan["installation_plan_digest"],
        "installation_receipt_digest": installation_receipt["receipt_semantic_digest"],
        "import_plan_digest": import_plan["runtime_import_verification_plan_digest"],
        "import_receipt_digest": import_receipt["receipt_semantic_digest"],
        "backend_plan_digest": backend_plan["runtime_backend_verification_plan_digest"],
        "backend_receipt_digest": backend_receipt["receipt_semantic_digest"],
        "acquisition_plan_digest": acquisition_plan["acquisition_plan_digest"],
        "acquisition_receipt_digest": acquisition_receipt["receipt_semantic_digest"],
        "model_id": acquisition_plan["model_id"], "artifact_id": acquisition_plan["artifact_id"],
        "route_id": acquisition_plan["route_id"], "engine": acquisition_plan["engine"],
        "backend_family": acquisition_plan["backend_family"], "runtime_id": acquisition_plan["runtime_id"],
        "interpreter_path": import_plan["venv_interpreter_path"], "artifact_path": str(artifact),
        "artifact_sha256": digest, "artifact_size_bytes": size,
    }


_PROBE = r'''import json,sys
P="SENTIENTOS_MODEL_COMPATIBILITY="
try:
 from llama_cpp import Llama
 m=Llama(model_path=sys.argv[1],vocab_only=True,n_ctx=64,n_gpu_layers=int(sys.argv[2]),verbose=False)
 del m
 out={"ok":True,"probe_mode":"bounded_model_construction_vocab_only","semantic_generations":0}
except Exception as e: out={"ok":False,"error_type":type(e).__name__,"diagnostic":str(e)[:512]}
print(P+json.dumps(out,sort_keys=True,separators=(",",":")))'''


def route_load_configuration(chain: Mapping[str, Any]) -> dict[str, Any]:
    family = str(chain["backend_family"])
    # A conservative accelerated load proves runtime availability, not full offload.
    layers = 0 if family == "cpu" else 1
    return {"engine": "llama_cpp", "n_ctx": 512, "n_gpu_layers": layers,
            "offload_claim": "cpu_only" if layers == 0 else "conservative_accelerator_layer",
            "ambient_accelerator_detection": False}


def verify_compatibility(chain: Mapping[str, Any], *, timeout_seconds: float = 60,
                         runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> dict[str, Any]:
    digest, size = _digest_file(Path(str(chain["artifact_path"])))
    if (digest, size) != (chain["artifact_sha256"], chain["artifact_size_bytes"]):
        raise ProductionCommissioningError("acquired_artifact_stale")
    config = route_load_configuration(chain)
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "VIRTUAL_ENV", "CONDA_PREFIX"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"; env["NO_PROXY"] = "*"
    with tempfile.TemporaryDirectory(prefix="sentientos-model-compat-") as cwd:
        try:
            result = runner([str(chain["interpreter_path"]), "-I", "-c", _PROBE,
                str(chain["artifact_path"]), str(config["n_gpu_layers"])], cwd=cwd, env=env,
                text=True, capture_output=True, timeout=timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ProductionCommissioningError("compatibility_timeout") from exc
    lines = [x.split("=", 1)[1] for x in result.stdout[-8192:].splitlines() if x.startswith("SENTIENTOS_MODEL_COMPATIBILITY=")]
    if result.returncode or len(lines) != 1:
        raise ProductionCommissioningError("compatibility_probe_failed")
    try: payload = json.loads(lines[0])
    except json.JSONDecodeError as exc: raise ProductionCommissioningError("compatibility_protocol_invalid") from exc
    if payload.get("ok") is not True or payload.get("semantic_generations") != 0:
        raise ProductionCommissioningError("gguf_runtime_incompatible")
    receipt = {"schema_version": COMPATIBILITY_SCHEMA, "status": "local_model_compatibility_verified",
        "chain_digest": semantic_digest(chain), "artifact_sha256": digest, "artifact_size_bytes": size,
        "interpreter_path": chain["interpreter_path"], "runtime_id": chain["runtime_id"],
        "load_configuration": config, "probe_mode": payload["probe_mode"],
        "model_construction_performed": True, "semantic_generations": 0,
        "commissioning_performed": False, "authority_granted": False, **DENIED}
    receipt["receipt_semantic_digest"] = semantic_digest(receipt)
    return receipt


def compose_commissioning_plan(chain: Mapping[str, Any], compatibility: Mapping[str, Any], output_root: Path | str) -> dict[str, Any]:
    _validate_digest(compatibility, "receipt_semantic_digest", "compatibility_receipt_invalid")
    if compatibility.get("chain_digest") != semantic_digest(chain):
        raise ProductionCommissioningError("compatibility_chain_mismatch")
    value = {"schema_version": PLAN_SCHEMA, "status": "local_model_commissioning_planned",
        "chain": dict(chain), "compatibility_receipt_digest": compatibility["receipt_semantic_digest"],
        "load_configuration": route_load_configuration(chain), "output_root": str(Path(output_root).absolute()),
        "smoke_contract": {"prompt_id": SMOKE_PROMPT_ID, "prompt_digest": semantic_digest({"prompt": SMOKE_PROMPT}),
            "max_calls": 1, "max_input_chars": 128, "max_output_chars": 128, "max_new_tokens": 8, "timeout_seconds": 20},
        "allowed_effects": {"model_load": True, "local_model_inference": True, "commissioning_receipt_write": True},
        "activation_performed": False, **DENIED}
    value["commissioning_plan_digest"] = semantic_digest(value)
    return value


def authorization_for(plan: Mapping[str, Any], *, operator_confirmed_plan_digest: str) -> dict[str, Any]:
    value = {"schema_version": AUTHORIZATION_SCHEMA, "action": "commission_exact_local_model",
        "commissioning_plan_digest": plan.get("commissioning_plan_digest"),
        "operator_confirmed_plan_digest": operator_confirmed_plan_digest,
        "model_id": plan.get("chain", {}).get("model_id"), "artifact_id": plan.get("chain", {}).get("artifact_id"),
        "route_id": plan.get("chain", {}).get("route_id"), "output_root": plan.get("output_root")}
    value["authorization_digest"] = semantic_digest(value); return value


def _config(plan: Mapping[str, Any]) -> ModelConfig:
    chain, load = plan["chain"], plan["load_configuration"]
    return ModelConfig([ModelCandidate(Path(chain["artifact_path"]), "llama_cpp", str(chain["model_id"]),
        {"gpu_layers": int(load["n_gpu_layers"])})], default_engine="llama_cpp", max_context_tokens=int(load["n_ctx"]),
        generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1))


def commission(plan: Mapping[str, Any], compatibility: Mapping[str, Any], authorization: Mapping[str, Any], *,
               model_factory: Callable[[ModelConfig], Any] | None = None,
               invoker_factory: Callable[..., GovernedLocalModelInvoker] = GovernedLocalModelInvoker) -> dict[str, Any]:
    _validate_digest(plan, "commissioning_plan_digest", "commissioning_plan_invalid")
    if authorization != authorization_for(plan, operator_confirmed_plan_digest=str(plan["commissioning_plan_digest"])):
        raise ProductionCommissioningError("commissioning_authorization_invalid")
    if compatibility.get("receipt_semantic_digest") != plan["compatibility_receipt_digest"]:
        raise ProductionCommissioningError("compatibility_receipt_substituted")
    chain = plan["chain"]; digest, size = _digest_file(Path(chain["artifact_path"]))
    if (digest, size) != (chain["artifact_sha256"], chain["artifact_size_bytes"]): raise ProductionCommissioningError("artifact_changed_before_load")
    config = _config(plan)
    if model_factory is None:
        backend, metadata = LocalModel._initialise_backend(config.candidates[0], config)
        identity = LocalModel._identity_for(config.candidates[0], config, backend, metadata, 0)
        model = LocalModel(backend, metadata, config, backend, identity)
    else: model = model_factory(config)
    identity = model.active_identity
    if identity.fallback or identity.posture != "production" or identity.engine != "llama_cpp" or identity.model_content_sha256 != digest or identity.artifact_size_bytes != size:
        raise ProductionCommissioningError("active_model_identity_mismatch")
    authority = build_local_model_authority_map(config, allowed_roots=[Path(chain["artifact_path"]).parent], observed_at="1970-01-01T00:00:00+00:00")
    invoker = invoker_factory(model=model, authority_map=authority, runtime_root=Path(plan["output_root"]) / "smoke")
    budget = LocalModelInvocationBudget(128, 128, 8, 20, 1)
    request = invoker.build_request(purpose="local_model_commissioning_smoke", prompt=SMOKE_PROMPT,
        caller="local_model_commissioning", correlation_id="commission:" + plan["commissioning_plan_digest"][:24], budget=budget,
        upstream_evidence={"commissioning_plan_digest": plan["commissioning_plan_digest"]}, linkage={"smoke_prompt_id": SMOKE_PROMPT_ID})
    smoke = invoker.invoke(request, persist=True).to_dict()
    if smoke["status"] != "admitted_completed" or smoke["fallback_occurred"] or not smoke["output_digest"] or smoke["output_size_bytes"] > 128:
        raise ProductionCommissioningError("commissioning_smoke_failed")
    receipt = {"schema_version": RECEIPT_SCHEMA, "status": "local_model_commissioned", "chain": dict(chain),
        "compatibility_receipt_digest": compatibility["receipt_semantic_digest"], "commissioning_plan_digest": plan["commissioning_plan_digest"],
        "operator_authorization_digest": authorization["authorization_digest"], "load_configuration": dict(plan["load_configuration"]),
        "active_model_identity": identity.to_dict(), "authority_map": authority.to_dict(),
        "smoke_request_digest": request.request_digest, "smoke_receipt_digest": smoke["receipt_digest"],
        "smoke_prompt_id": SMOKE_PROMPT_ID, "smoke_inference_count": 1, "activated": False, **DENIED}
    receipt["receipt_semantic_digest"] = semantic_digest(receipt)
    root = Path(plan["output_root"]); root.mkdir(parents=True, exist_ok=True)
    (root / "commissioning-receipt.json").write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
    return receipt


def activate(receipt: Mapping[str, Any], activation_path: Path | str) -> dict[str, Any]:
    _validate_digest(receipt, "receipt_semantic_digest", "commissioning_receipt_invalid")
    if receipt.get("schema_version") != RECEIPT_SCHEMA or receipt.get("status") != "local_model_commissioned":
        raise ProductionCommissioningError("production_commissioning_required")
    chain = receipt["chain"]; digest, size = _digest_file(Path(chain["artifact_path"]))
    if (digest, size) != (chain["artifact_sha256"], chain["artifact_size_bytes"]): raise ProductionCommissioningError("commissioned_artifact_stale")
    value = {"schema_version": ACTIVATION_SCHEMA, "status": "local_model_activated",
        "commissioning_receipt": dict(receipt), "commissioning_receipt_digest": receipt["receipt_semantic_digest"],
        "model_id": chain["model_id"], "artifact_id": chain["artifact_id"], "route_id": chain["route_id"],
        "artifact_path": chain["artifact_path"], "artifact_sha256": digest, "artifact_size_bytes": size,
        "runtime_id": chain["runtime_id"], "interpreter_path": chain["interpreter_path"],
        "load_configuration": dict(receipt["load_configuration"]), "authority_map": dict(receipt["authority_map"]),
        "serving_grant": "already_governed_local_invocation_only", **DENIED}
    value["activation_digest"] = semantic_digest(value)
    target = Path(activation_path); target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".activation-", dir=target.parent)
    try:
        with os.fdopen(fd, "w") as stream: json.dump(value, stream, sort_keys=True, separators=(",", ":")); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return value


def load_activation(path: Path | str) -> tuple[LocalModel, Any]:
    value = json.loads(Path(path).read_text())
    copy = dict(value); claimed = copy.pop("activation_digest", None)
    if claimed != semantic_digest(copy): raise ProductionCommissioningError("activation_invalid")
    receipt = value["commissioning_receipt"]; _validate_digest(receipt, "receipt_semantic_digest", "commissioning_receipt_invalid")
    if receipt["receipt_semantic_digest"] != value["commissioning_receipt_digest"]: raise ProductionCommissioningError("activation_commissioning_mismatch")
    chain = receipt["chain"]; digest, size = _digest_file(Path(chain["artifact_path"]))
    if (digest, size) != (value["artifact_sha256"], value["artifact_size_bytes"]): raise ProductionCommissioningError("activated_artifact_stale")
    plan = {"chain": chain, "load_configuration": value["load_configuration"]}; config = _config(plan)
    backend, metadata = LocalModel._initialise_backend(config.candidates[0], config)
    identity = LocalModel._identity_for(config.candidates[0], config, backend, metadata, 0)
    if identity.to_dict() != receipt["active_model_identity"]: raise ProductionCommissioningError("activated_identity_mismatch")
    model = LocalModel(backend, metadata, config, backend, identity)
    authority = build_local_model_authority_map(config, allowed_roots=[Path(chain["artifact_path"]).parent], observed_at="1970-01-01T00:00:00+00:00")
    if authority.to_dict() != value["authority_map"]: raise ProductionCommissioningError("activated_authority_mismatch")
    return model, authority
