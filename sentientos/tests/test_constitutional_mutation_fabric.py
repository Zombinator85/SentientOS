from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sentientos.constitutional_mutation_fabric import (
    ConstitutionalMutationRouter,
    MutationProvenanceIntent,
    TypedMutationAction,
)
from sentientos.control_plane_kernel import (
    AdmissionOutcome,
    AuthorityClass,
    ControlActionDecision,
    ControlPlaneKernel,
    LifecyclePhase,
)


def _registry(path: Path, *, action_id: str = "sentientos.test.slice") -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "actions": [
                    {
                        "action_id": action_id,
                        "domain": "immutable_manifest_identity_writes",
                        "authority_class": "manifest_or_identity_mutation",
                        "lifecycle_phase": "maintenance",
                        "canonical_handler": "tests.handler",
                        "canonical_artifact_boundary": "vow/immutable_manifest.json",
                        "provenance_expectation": "kernel_admission",
                        "authority_of_judgment_applies": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _action(action_id: str = "sentientos.test.slice") -> TypedMutationAction:
    return TypedMutationAction(
        action_id=action_id,
        mutation_domain="immutable_manifest_identity_writes",
        authority_class=AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION,
        lifecycle_phase=LifecyclePhase.MAINTENANCE,
        correlation_id="test:1",
        execution_owner="pytest",
        execution_source="sentientos.tests",
        target_subsystem="vow/immutable_manifest.json",
        action_kind="generate_immutable_manifest",
        provenance_intent=MutationProvenanceIntent(
            domains=("immutable_manifest_identity_writes",),
            authority_classes=(AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION.value,),
            invocation_path="sentientos.tests.test_constitutional_mutation_fabric",
        ),
    )


def test_router_fails_closed_for_missing_registration(tmp_path: Path) -> None:
    router = ConstitutionalMutationRouter(registry_path=tmp_path / "missing.json")
    router.register_handler("sentientos.test.slice", lambda _action, _admission: {"ok": True})
    try:
        router.execute(_action())
    except ValueError as exc:
        assert "missing_action_registration" in str(exc)
    else:
        raise AssertionError("expected fail-closed missing registration")


def test_typed_action_kernel_handler_and_provenance_linkage(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    registry = _registry(tmp_path / "registry.json")
    decisions_path = tmp_path / "glow/control_plane/kernel_decisions.jsonl"
    kernel = ControlPlaneKernel(decisions_path=decisions_path)
    monkeypatch.setattr("sentientos.constitutional_mutation_fabric.get_control_plane_kernel", lambda: kernel)

    side_effect = tmp_path / "result.json"
    router = ConstitutionalMutationRouter(registry_path=registry)
    router.register_handler(
        "sentientos.test.slice",
        lambda _action, admission: side_effect.write_text(json.dumps({"admission": admission}), encoding="utf-8"),
    )

    result = router.execute(_action())

    assert result.executed is True
    assert result.admission is not None
    assert side_effect.exists()
    payload = json.loads(side_effect.read_text(encoding="utf-8"))
    assert payload["admission"]["admission_decision_ref"] == "kernel_decision:test:1"

    decision_rows = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(row.get("action_kind") == "generate_immutable_manifest" for row in decision_rows)


@dataclass
class _DeniedKernel:
    def set_phase(self, _phase: LifecyclePhase, *, actor: str = "") -> None:
        _ = actor

    def admit(self, _request):  # type: ignore[no-untyped-def]
        return ControlActionDecision(
            outcome=AdmissionOutcome.DENY,
            reason_codes=("runtime_governor:denied",),
            current_phase=LifecyclePhase.MAINTENANCE,
            requested_phase=LifecyclePhase.MAINTENANCE,
            authority_class=AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION,
            action_kind="generate_immutable_manifest",
            actor="pytest",
            target_subsystem="vow/immutable_manifest.json",
            delegated_outcomes={},
            correlation_id="test:1",
        )


def test_kernel_denial_prevents_side_effect(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    registry = _registry(tmp_path / "registry.json")
    side_effect = tmp_path / "blocked.txt"
    router = ConstitutionalMutationRouter(registry_path=registry)
    router.register_handler("sentientos.test.slice", lambda _action, _admission: side_effect.write_text("mutated", encoding="utf-8"))
    monkeypatch.setattr("sentientos.constitutional_mutation_fabric.get_control_plane_kernel", lambda: _DeniedKernel())

    result = router.execute(_action())
    assert result.executed is False
    assert result.admission is None
    assert not side_effect.exists()
