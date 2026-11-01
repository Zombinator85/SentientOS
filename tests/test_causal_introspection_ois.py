from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.causal_introspection import (
    SCHEMA_VERSION,
    CausalIntrospectionRuntime,
    CausalReference,
    CaptureContext,
    IntrospectionConfig,
    MappingMetadataProvider,
    OwnerObservation,
    ProviderRegistration,
)
from sentientos.cli import ois_cli
from sentientos.ois import build_causal_introspection_overview


def _write_config(tmp_path: Path, monkeypatch) -> Path:
    config_path = tmp_path / "causal-introspection.json"
    config_path.write_text(json.dumps({
        "schema": SCHEMA_VERSION,
        "enabled": True,
        "custody_root": str(tmp_path / "snapshots"),
        "world_state_consumption_enabled": True,
        "enabled_domains": ["model_serving"],
        "required_domains": ["model_serving"],
    }), encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_CAUSAL_INTROSPECTION_CONFIG", str(config_path))
    return config_path


def _capture(tmp_path: Path) -> CausalIntrospectionRuntime:
    reference = CausalReference(
        "model", "model-serving:fixture", "a" * 64, "describes", "model-serving-owner"
    )
    provider = MappingMetadataProvider(
        provider_id="provider:model-serving",
        owner_id="model-serving-owner",
        owner_kind="model_serving_owner",
        domain="model_serving",
        references=(reference,),
        observations=(OwnerObservation(
            "private_fixture_value", "PRIVATE_OBSERVATION_VALUE", "identity",
            (reference.reference_id,), production_posture="synthetic_test",
        ),),
    )
    config = IntrospectionConfig(
        True, tmp_path / "snapshots", True, 4, ("model_serving",), ("model_serving",)
    )
    runtime = CausalIntrospectionRuntime(
        config, (ProviderRegistration("model-serving-owner", "model_serving", provider),)
    )
    runtime.capture(CaptureContext("tick-1", capture_posture="synthetic_test"))
    return runtime


def test_operator_view_reports_unconfigured_state_without_inventing_capture(monkeypatch):
    monkeypatch.delenv("SENTIENTOS_CAUSAL_INTROSPECTION_CONFIG", raising=False)

    result = build_causal_introspection_overview()

    assert result["configuration_posture"] == "not_configured"
    assert result["verification_posture"] == "not_run"
    assert result["latest"] is None
    assert result["read_only"] is True
    assert result["authority"] is False
    assert result["current_truth"] is False
    assert result["coverage"]


def test_operator_view_verifies_chain_and_omits_observation_values(tmp_path, monkeypatch, capsys):
    _write_config(tmp_path, monkeypatch)
    runtime = _capture(tmp_path)
    runtime.capture(CaptureContext("tick-2", capture_posture="synthetic_test"))
    access_events: list[tuple[str, dict[str, object] | None]] = []
    monkeypatch.setattr(
        ois_cli, "log_introspection_access",
        lambda view, *, detail=None: access_events.append((view, detail)),
    )

    assert ois_cli.main(["introspection", "--history-limit", "1"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["verification_posture"] == "verified"
    assert output["generation_count"] == 2
    assert output["omitted_older_generation_count"] == 1
    assert output["configuration"]["world_state_consumption_enabled"] is True
    assert output["latest"]["generation"] == 2
    assert output["latest"]["domain_projection_counts"] == {"model_serving": 1}
    assert output["latest"]["owners"][0]["observation_count"] == 1
    assert output["value_disclosure"] == "observation_values_omitted"
    assert "PRIVATE_OBSERVATION_VALUE" not in json.dumps(output)
    assert access_events == [("causal_introspection", {"history_limit": 1})]


def test_operator_view_reports_integrity_block_without_snapshot_payload(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch)
    runtime = _capture(tmp_path)
    snapshot_path = tmp_path / "snapshots" / "generation-00000000000000000001.json"
    snapshot_path.write_text(
        snapshot_path.read_text(encoding="utf-8").replace('"capture_tick":"tick-1"', '"capture_tick":"tick-x"'),
        encoding="utf-8",
    )

    result = build_causal_introspection_overview()

    assert result["verification_posture"] == "blocked"
    assert result["error_code"] == "projection_digest_mismatch"
    assert result["latest"] is None
    assert "PRIVATE_OBSERVATION_VALUE" not in json.dumps(result)


def test_operator_view_rejects_unbounded_history_request(monkeypatch):
    monkeypatch.delenv("SENTIENTOS_CAUSAL_INTROSPECTION_CONFIG", raising=False)

    try:
        ois_cli.main(["introspection", "--history-limit", "101"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("unbounded history request should be rejected")

