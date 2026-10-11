from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import sentientosd
from sentientos.causal_introspection import CausalIntrospectionRuntime, IntrospectionConfig


pytestmark = pytest.mark.no_legacy_skip


def _write_configs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    epistemic = tmp_path / "epistemic.json"
    epistemic.write_text(json.dumps({
        "schema": "sentientos.epistemic_runtime_config:v1",
        "custody_root": str((tmp_path / "epistemic").resolve()),
        "allowed_proposition_namespaces": ["test"],
        "max_cognitive_projection_count": 8,
        "cognitive_consumption_enabled": False,
    }))
    longitudinal = tmp_path / "longitudinal.json"
    longitudinal.write_text(json.dumps({
        "schema": "sentientos.longitudinal_self_model_runtime_config:v1",
        "enabled": True,
        "custody_root": str((tmp_path / "longitudinal").resolve()),
        "cognitive_consumption_enabled": False,
        "max_projection_claims": 8,
        "allowed_predicates": ["status"],
        "installation_id": "test-installation",
    }))
    introspection = tmp_path / "introspection.json"
    introspection.write_text(json.dumps({
        "schema": "sentientos.causal_introspection:v1",
        "enabled": True,
        "custody_root": str((tmp_path / "introspection").resolve()),
        "world_state_consumption_enabled": True,
        "max_projections": 8,
        "enabled_domains": ["runtime_supervision", "persistent_epistemics", "longitudinal_self_model"],
        "required_domains": ["runtime_supervision", "persistent_epistemics", "longitudinal_self_model"],
    }))
    monkeypatch.setenv(sentientosd.EPISTEMIC_STATE_CONFIG_ENV, str(epistemic))
    monkeypatch.setenv(sentientosd.LONGITUDINAL_SELF_MODEL_CONFIG_ENV, str(longitudinal))
    monkeypatch.setenv("SENTIENTOS_CAUSAL_INTROSPECTION_CONFIG", str(introspection))
    return tmp_path / "introspection"


def _patch_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sentientosd.CeremonialScript, "perform", lambda self: None)
    monkeypatch.setattr(sentientosd.FirstContact, "affirm_integrity", lambda self: None)
    monkeypatch.setattr(sentientosd.FirstContact, "invite_conversation", lambda self: None)
    monkeypatch.setattr(sentientosd, "build_boot_ceremony_link", lambda _emitter: SimpleNamespace(narrate=lambda: None))
    monkeypatch.setattr(sentientosd.LocalModel, "autoload", lambda: SimpleNamespace(describe=lambda: "test"))
    monkeypatch.setattr(sentientosd, "ForgeDaemon", lambda: SimpleNamespace(repo_root=tmp_path))
    monkeypatch.setattr(sentientosd, "ForgeMergeTrain", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(sentientosd, "ContractSentinel", lambda: SimpleNamespace())
    monkeypatch.setattr(sentientosd, "build_local_model_authority_map", lambda: {})
    monkeypatch.setattr(sentientosd, "GovernedLocalModelInvoker", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(sentientosd, "GenesisModelAdviceCoordinator", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(sentientosd, "resolve_improvement_evidence_sources", lambda _root: [])
    monkeypatch.setattr(sentientosd, "_start_maintenance_daemon_owners_after_resident_decision",
                        lambda *_args, **_kwargs: (None, None, None, False))
    monkeypatch.setattr(sentientosd, "_start_maintenance_continuity_auto_derivation",
                        lambda *_args, **_kwargs: (None, {"status": "disabled", "read_only": True}))
    monkeypatch.setattr(sentientosd, "get_control_plane_kernel",
                        lambda: SimpleNamespace(set_phase=lambda *_args, **_kwargs: None))


def test_run_loop_composes_three_live_owners_and_preserves_temporal_firewall(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custody = _write_configs(tmp_path, monkeypatch)
    _patch_startup(monkeypatch, tmp_path)
    shutdown = asyncio.Event()
    observed_subjects: list[set[str]] = []
    composed: list[CausalIntrospectionRuntime] = []

    def bounded_tick(*, runtime_surfaces, **_kwargs):
        runtime = runtime_surfaces._causal_introspection_runtime
        assert isinstance(runtime, CausalIntrospectionRuntime)
        composed.append(runtime)
        tick = f"2026-01-0{len(composed)}T00:00:00+00:00"
        if len(composed) == 2:
            runtime_surfaces._feedback["surfaces"]["dynamic-owner-state"] = {"status": "degraded"}
        runtime_surfaces.build_world_state_board(tick_id=tick)
        snapshot = runtime_surfaces.current_world_state_snapshot
        observed_subjects.append({entity.subject.subject_id for entity in snapshot.entities})
        runtime_surfaces.capture_causal_introspection(tick_id=tick)
        if len(composed) == 2:
            shutdown.set()

    monkeypatch.setattr(sentientosd, "_run_maintenance_tick", bounded_tick)
    asyncio.run(sentientosd.run_loop(shutdown, interval_seconds=0))

    assert {item.domain for item in composed[0].registrations} == {
        "runtime_supervision", "persistent_epistemics", "longitudinal_self_model"}
    assert observed_subjects[0].isdisjoint({"sentientosd-runtime", "persistent-epistemic-state", "longitudinal-self-model"})
    assert {"sentientosd-runtime", "persistent-epistemic-state", "longitudinal-self-model"} <= observed_subjects[1]
    reconstructed = CausalIntrospectionRuntime(composed[-1].config, composed[-1].registrations).reconstruct()
    assert [item.generation for item in reconstructed] == [1, 2]
    runtime_projections = [next(projection for projection in item.projections
        if projection.domain == "runtime_supervision") for item in reconstructed]
    degraded_counts = [next(observation.bounded_value for observation in projection.observations
        if observation.observation_key == "degraded_surface_count") for projection in runtime_projections]
    assert degraded_counts == [0, 1]
    epistemic_projections = [next(projection for projection in item.projections
        if projection.domain == "persistent_epistemics") for item in reconstructed]
    incomplete_counts = [next(observation.bounded_value for observation in projection.observations
        if observation.observation_key == "incomplete_admission_bound_transaction_count")
        for projection in epistemic_projections]
    assert incomplete_counts == [0, 0]
    recovery_statuses = [next(observation.bounded_value for observation in projection.observations
        if observation.observation_key == "mutation_recovery_status")
        for projection in epistemic_projections]
    assert recovery_statuses == ["not_composed", "not_composed"]
    pending_state_intents = [next(observation.bounded_value for observation in projection.observations
        if observation.observation_key == "pending_state_intent_count")
        for projection in epistemic_projections]
    assert pending_state_intents == [0, 0]
    assert len(list(custody.glob("generation-*.json"))) == 2


def test_run_loop_without_config_preserves_disabled_posture(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_startup(monkeypatch, tmp_path)
    monkeypatch.delenv("SENTIENTOS_CAUSAL_INTROSPECTION_CONFIG", raising=False)
    shutdown = asyncio.Event()

    def bounded_tick(*, runtime_surfaces, **_kwargs):
        assert runtime_surfaces._causal_introspection_runtime is None
        shutdown.set()

    monkeypatch.setattr(sentientosd, "_run_maintenance_tick", bounded_tick)
    asyncio.run(sentientosd.run_loop(shutdown, interval_seconds=0))
    assert not list(tmp_path.glob("**/generation-*.json"))


def test_run_loop_invalid_config_is_blocked_not_reinterpreted_as_absent(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_startup(monkeypatch, tmp_path)
    config = tmp_path / "invalid-introspection.json"
    config.write_text('{"schema":"wrong"}')
    monkeypatch.setenv("SENTIENTOS_CAUSAL_INTROSPECTION_CONFIG", str(config))
    shutdown = asyncio.Event()
    feedback: list[dict[str, object]] = []

    def bounded_tick(*, runtime_surfaces, **_kwargs):
        assert runtime_surfaces._causal_introspection_runtime is None
        feedback.append(runtime_surfaces._feedback["surfaces"]["causal_introspection"])
        shutdown.set()

    monkeypatch.setattr(sentientosd, "_run_maintenance_tick", bounded_tick)
    asyncio.run(sentientosd.run_loop(shutdown, interval_seconds=0))
    assert feedback[0]["status"] == "blocked"
    assert "unsupported_config_schema" in str(feedback[0]["reason"])


def test_serving_introspection_uses_non_invalidating_observation(tmp_path: Path) -> None:
    class Serving:
        current_calls = 0
        observed_calls = 0

        def health(self):
            return {"status": "stale", "read_only": True}

        def current_session(self):
            self.current_calls += 1
            raise AssertionError("introspection must not invalidate through current_session")

        def observed_current_session(self):
            self.observed_calls += 1
            return None

    serving = Serving()
    surfaces = SimpleNamespace(
        _epistemic_state_owner=None, _epistemic_development_runtime=None,
        _resource_observation_owner=None, _longitudinal_self_model_owner=None,
        _resident_developmental_owner=None, _resident_transition_runtime=None,
        _resident_transition_custody=None, _resident_cognitive_invoker=None,
        _resident_software_transition_controller=None,
        _resident_software_transition_config=None,
        governance_feedback=lambda: {"surfaces": {}},
    )
    config = IntrospectionConfig(
        enabled=True, custody_root=tmp_path / "introspection",
        world_state_consumption_enabled=True, max_projections=1,
        enabled_domains=("model_serving",), required_domains=("model_serving",))
    runtime = sentientosd._compose_causal_introspection(
        surfaces, resident_serving_controller=serving, config=config)

    snapshot = runtime.capture(sentientosd.CaptureContext(
        tick_id="2026-10-11T01:00:00Z", capture_posture="unknown"))

    projection = snapshot.projections[0]
    assert projection.domain == "model_serving"
    assert serving.current_calls == 0
    assert serving.observed_calls == 1
    assert next(item.bounded_value for item in projection.observations
        if item.observation_key == "session_present") is False


def test_causal_resource_allocation_identity_projection_is_bounded_and_digest_located() -> None:
    from sentientosd import _bounded_resource_allocation_identity_projection

    values = tuple({"allocation_digest": f"allocation-{index}"} for index in range(70))
    projection = _bounded_resource_allocation_identity_projection(values)

    assert len(projection["allocation_digests"]) == 64
    assert projection["allocation_digests"][0] == "allocation-6"
    assert projection["allocation_digests"][-1] == "allocation-69"
    assert projection["allocation_count"] == 70
    assert projection["omitted_allocation_count"] == 6
    assert projection["last_omitted_allocation_digest"] == "allocation-5"
    assert projection["first_retained_allocation_digest"] == "allocation-6"
    assert projection["allocation_retention_posture"] == "bounded_tail_incomplete"


def test_optional_introspection_recovery_failure_is_visible_and_bounded():
    class BrokenIntrospection:
        def reconstruct(self):
            raise RuntimeError("private path detail")

    records = _causal_introspection_world_state_records(
        BrokenIntrospection(), tick_id="2026-10-11T12:00:00+00:00")

    assert len(records) == 1
    record = records[0]
    assert record["source_kind"] == "owner_introspection"
    assert record["subject_kind"] == "causal_introspection_recovery"
    assert record["disposition"] == "incomplete"
    assert record["observed_at"] is None
    assert record["retrieved_at"] == "2026-10-11T12:00:00+00:00"
    assert record["staleness"] == "unknown"
    assert record["payload"]["error_class"] == "RuntimeError"
    assert "private path detail" not in repr(record)


def test_optional_introspection_prior_generation_is_composed_without_mutation():
    projected = [{"source_kind": "owner_introspection", "source_id": "prior-projection"}]

    class ExistingIntrospection:
        def __init__(self):
            self.requested_before_generation = None

        def reconstruct(self):
            return (object(), object())

        def world_state_records(self, *, before_generation):
            self.requested_before_generation = before_generation
            return projected

    runtime = ExistingIntrospection()
    assert _causal_introspection_world_state_records(
        runtime, tick_id="2026-10-11T12:00:00+00:00") == projected
    assert runtime.requested_before_generation == 3
