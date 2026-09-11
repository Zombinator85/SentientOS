from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.no_legacy_skip

import scripts.local_model_commissioning as cli
from sentientos.local_model_production_commissioning import (
    ProductionCommissioningError,
    prepare_commissioning_intent,
)
from sentientos.local_model_production_commissioning_authority import (
    EFFECTS,
    INTENT_SCHEMA,
    CommissioningAuthorityError,
    build_intent,
)
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.capability_registry import build_default_capability_registry


def _evidence() -> tuple[dict[str, object], Any, dict[str, object]]:
    handle = SimpleNamespace(identity=SimpleNamespace(value="machine-one"), root=Path("/custody"))
    proof: dict[str, object] = {
        "installation_identity": "machine-one", "custody_identity": "catalog:machine-one",
        "authoritative_catalog_semantic_digest": "d" * 64, "proof_semantic_digest": "e" * 64,
        "deployment_receipt_id": "deployment-one", "deployment_receipt_semantic_digest": "f" * 64,
    }
    plan = {
        "acquisition_plan_digest": "a" * 64, "installation_identity": "machine-one",
        "catalog_custody_identity": "catalog:machine-one", "local_model_catalog_digest": "d" * 64,
        "authoritative_catalog_proof_digest": "e" * 64, "deployment_receipt_id": "deployment-one",
        "deployment_receipt_semantic_digest": "f" * 64,
    }
    receipt = {
        "schema_version": "sentientos.local_model_artifact_acquisition_receipt:v2",
        "receipt_semantic_digest": "b" * 64,
    }
    chain: dict[str, object] = {
        "authoritative_evidence": {"acquisition_plan": plan, "acquisition_receipt": receipt},
        "model_id": "model-one", "artifact_id": "artifact-one", "artifact_sha256": "c" * 64,
        "artifact_size_bytes": 7, "artifact_path": "/custody/model.gguf", "route_id": "route-one",
        "engine": "llama_cpp", "backend_family": "cpu", "runtime_id": "runtime-one",
        "interpreter_path": "/runtime/python",
    }
    return chain, handle, proof


def _authority_stubs(monkeypatch: pytest.MonkeyPatch, proof: dict[str, object]) -> None:
    monkeypatch.setattr("sentientos.local_model_production_commissioning.revalidate_chain", lambda value: dict(value))
    monkeypatch.setattr("sentientos.local_model_production_commissioning_authority.current_proof", lambda handle, plan: proof)
    monkeypatch.setattr("sentientos.local_model_artifact_acquisition.verify_acquisition_receipt", lambda receipt, plan: True)
    monkeypatch.setattr("sentientos.local_model_production_commissioning_authority.commissioning_custody", lambda handle: {
        "commissioning_output_custody_identity": "installation-local-model-commissioning:machine-one",
        "commissioning_domain": "local-model/commissioning", "receipt_directory": "local-model/commissioning/receipts",
        "smoke_directory": "local-model/commissioning/smoke",
    })


def test_cli_intent_equals_canonical_build_intent_and_is_deterministic(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    chain, handle, proof = _evidence(); _authority_stubs(monkeypatch, proof)
    opened: list[object] = []
    def open_handle(identity: object) -> Any:
        opened.append(identity)
        return handle
    registry = SimpleNamespace(open=open_handle)
    monkeypatch.setattr(cli, "_production_chain", lambda root: chain)
    monkeypatch.setattr("scripts.local_model_commissioning.InstallationStateRegistry.system", lambda: registry)
    monkeypatch.setattr(sys, "argv", ["local_model_commissioning.py", "intent", "--evidence-root", "/evidence",
        "--installation-identity", "machine-one", "--correlation-id", "commissioning-one"])
    assert cli.main() == 0
    first = capsys.readouterr().out
    emitted = json.loads(first)
    expected = dict(build_intent(chain, handle, correlation_id="commissioning-one"))
    assert emitted == expected
    assert emitted["schema_version"] == INTENT_SCHEMA
    assert emitted["effects"] == sorted(EFFECTS)
    digest = emitted.pop("intent_semantic_digest")
    assert digest == semantic_digest(emitted)
    emitted["intent_semantic_digest"] = digest
    assert getattr(opened[0], "value") == "machine-one"
    assert cli.main() == 0
    assert capsys.readouterr().out == first


def test_cli_intent_is_zero_effect_and_uses_no_effectful_commission_path(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    chain, handle, proof = _evidence(); _authority_stubs(monkeypatch, proof)
    monkeypatch.setattr(cli, "_production_chain", lambda root: chain)
    monkeypatch.setattr("scripts.local_model_commissioning.InstallationStateRegistry.system",
                        lambda: SimpleNamespace(open=lambda identity: handle))
    monkeypatch.setattr(cli, "commission_production", lambda *a, **k: pytest.fail("effectful commission called"))
    monkeypatch.setattr(cli, "get_control_plane_kernel", lambda: pytest.fail("admission requested"))
    monkeypatch.setattr(sys, "argv", ["local_model_commissioning.py", "intent", "--evidence-root", "/evidence",
        "--installation-identity", "machine-one", "--correlation-id", "commissioning-one"])
    assert cli.main() == 0
    intent = json.loads(capsys.readouterr().out)
    assert intent["activation_performed"] is False
    assert intent["serving_authority_granted"] is False


@pytest.mark.parametrize("failure", ["missing", "malformed", "stale", "receipt"])  # type: ignore[untyped-decorator]
def test_cli_intent_evidence_failures_are_closed(monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str], tmp_path: Path, failure: str) -> None:
    chain, handle, proof = _evidence(); _authority_stubs(monkeypatch, proof)
    monkeypatch.setattr("scripts.local_model_commissioning.InstallationStateRegistry.system",
                        lambda: SimpleNamespace(open=lambda identity: handle))
    if failure == "missing":
        root = tmp_path
    elif failure == "malformed":
        root = tmp_path
        (root / "selection.json").write_text("{")
    else:
        root = Path("/evidence")
        monkeypatch.setattr(cli, "_production_chain", lambda value: chain)
        if failure == "stale":
            monkeypatch.setattr("sentientos.local_model_production_commissioning_authority.current_proof",
                                lambda handle, plan: (_ for _ in ()).throw(CommissioningAuthorityError("stale_acquisition_catalog_provenance")))
        else:
            monkeypatch.setattr("sentientos.local_model_artifact_acquisition.verify_acquisition_receipt", lambda receipt, plan: False)
    monkeypatch.setattr(sys, "argv", ["local_model_commissioning.py", "intent", "--evidence-root", str(root),
        "--installation-identity", "machine-one", "--correlation-id", "commissioning-one"])
    assert cli.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


@pytest.mark.parametrize("correlation", ["", "placeholder", "contains*wildcard"])  # type: ignore[untyped-decorator]
def test_intent_rejects_invalid_correlation(monkeypatch: pytest.MonkeyPatch, correlation: str) -> None:
    chain, handle, proof = _evidence(); _authority_stubs(monkeypatch, proof)
    with pytest.raises(ProductionCommissioningError, match="commissioning_correlation_id_invalid"):
        prepare_commissioning_intent(chain, installation_handle=handle, correlation_id=correlation)


def test_intent_parser_exposes_no_production_identity_overrides() -> None:
    source = Path(cli.__file__).read_text()
    intent_section = source[source.index('intent = sub.add_parser("intent")'):source.index('status = sub.add_parser("status")')]
    for option in ("--state-root", "--model-path", "--artifact-path", "--runtime-path", "--catalog-path",
                   "--acquisition-receipt-path", "--authority-map", "--allow-root", "--simulation", "--autoload"):
        assert option not in intent_section


def test_capability_truth_remains_partial_and_separates_downstream_authority() -> None:
    record = build_default_capability_registry().by_id()["local_model_production_commissioning"]
    assert record.status == "partial"
    assert "canonical zero-effect production commissioning intent emission for external approval" in record.implemented_surfaces
    assert "genuine real-world commissioning approval actuator/event" in record.deferred_surfaces
    assert "first genuine production commissioning event" in record.deferred_surfaces
    assert "activated-model consumer implementation" not in record.deferred_surfaces
    assert "serving and boot-load lifecycle hardening" not in record.deferred_surfaces
    assert "commissioning is activation" in record.forbidden_implications
    assert "commissioning receipt grants unrestricted serving authority" in record.forbidden_implications
