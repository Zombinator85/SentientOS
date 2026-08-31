import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.local_model_production_commissioning import (
    ProductionCommissioningError, activate, route_load_configuration, verify_compatibility,
)
from sentientos.local_runtime_provisioning import semantic_digest


def _chain(model: Path, interpreter: Path, family: str = "cpu") -> dict[str, object]:
    import hashlib
    data = model.read_bytes()
    return {"artifact_path": str(model), "artifact_sha256": hashlib.sha256(data).hexdigest(),
            "artifact_size_bytes": len(data), "interpreter_path": str(interpreter), "runtime_id": "rt",
            "backend_family": family, "model_id": "m", "artifact_id": "sha256:x", "route_id": family}


def test_route_configuration_is_explicit_and_ambient_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic")
    monkeypatch.setitem(__import__("sys").modules, "torch", object())
    assert route_load_configuration(_chain(model, Path("/python")))["n_gpu_layers"] == 0
    assert route_load_configuration(_chain(model, Path("/python"), "cuda"))["n_gpu_layers"] == 1


def test_compatibility_receipt_records_truthful_bounded_construction(tmp_path: Path) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic")
    def runner(*args: object, **kwargs: object) -> CompletedProcess[str]:
        payload = {"ok": True, "probe_mode": "bounded_model_construction_vocab_only", "semantic_generations": 0}
        return CompletedProcess([], 0, "SENTIENTOS_MODEL_COMPATIBILITY=" + json.dumps(payload), "")
    receipt = verify_compatibility(_chain(model, Path("/verified/python")), runner=runner)
    assert receipt["status"] == "local_model_compatibility_verified"
    assert receipt["model_construction_performed"] is True
    assert receipt["semantic_generations"] == 0


def test_activation_requires_valid_commissioning_and_current_bytes(tmp_path: Path) -> None:
    model = tmp_path / "m.gguf"; model.write_bytes(b"GGUFsynthetic")
    chain = _chain(model, Path("/verified/python"))
    receipt = {"schema_version": "sentientos.local_model_commissioning_receipt:v2", "status": "local_model_commissioned",
        "chain": chain, "load_configuration": route_load_configuration(chain), "authority_map": {}, "active_model_identity": {},
        "activated": False, "provider_network": False, "tool": False, "memory": False, "action": False,
        "adoption": False, "repository_mutation": False, "autonomous_invocation": False, "background_inference": False}
    receipt["receipt_semantic_digest"] = semantic_digest(receipt)
    activation = activate(receipt, tmp_path / "active.json")
    assert activation["status"] == "local_model_activated"
    model.write_bytes(b"changed")
    with pytest.raises(ProductionCommissioningError, match="commissioned_artifact_stale"):
        activate(receipt, tmp_path / "active2.json")
