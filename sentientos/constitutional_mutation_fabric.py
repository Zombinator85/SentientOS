from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from sentientos.control_plane_kernel import (
    AuthorityClass,
    ControlActionRequest,
    LifecyclePhase,
    get_control_plane_kernel,
)
from sentientos.event_stream import record_forge_event
from sentientos.protected_mutation_provenance import build_admission_provenance


@dataclass(frozen=True, slots=True)
class MutationProvenanceIntent:
    domains: tuple[str, ...]
    authority_classes: tuple[str, ...]
    invocation_path: str
    expect_forward_enforcement: bool = True

    def to_kernel_metadata(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "declared": True,
            "domains": sorted(set(self.domains)),
            "authority_classes": sorted(set(self.authority_classes)),
            "expect_forward_enforcement": self.expect_forward_enforcement,
            "invocation_path": self.invocation_path,
        }


@dataclass(frozen=True, slots=True)
class TypedMutationAction:
    action_id: str
    mutation_domain: str
    authority_class: AuthorityClass
    lifecycle_phase: LifecyclePhase
    correlation_id: str
    execution_owner: str
    execution_source: str
    target_subsystem: str
    action_kind: str
    provenance_intent: MutationProvenanceIntent
    payload: dict[str, Any] = field(default_factory=dict)
    advisory_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MutationActionRegistration:
    action_id: str
    mutation_domain: str
    authority_class: AuthorityClass
    lifecycle_phase: LifecyclePhase
    canonical_handler: str
    canonical_artifact_boundary: str
    provenance_expectation: str
    authority_of_judgment_applies: bool


@dataclass(frozen=True, slots=True)
class MutationExecutionResult:
    executed: bool
    decision_reason_codes: tuple[str, ...]
    correlation_id: str
    admission: dict[str, object] | None
    handler_result: Any | None
    registry: MutationActionRegistration


CanonicalMutationHandler = Callable[[TypedMutationAction, dict[str, object]], Any]


class ConstitutionalMutationRouter:
    """Shared typed mutation router for the scoped constitutional mutation slice."""

    def __init__(self, *, registry_path: Path | None = None) -> None:
        self._handlers: dict[str, CanonicalMutationHandler] = {}
        default_registry = Path(__file__).resolve().parents[1] / "glow/contracts/constitutional_execution_fabric_scoped_slice.json"
        self._registry_path = registry_path or default_registry
        self._registry = self._load_registry(self._registry_path)

    @staticmethod
    def _load_registry(path: Path) -> dict[str, MutationActionRegistration]:
        if not path.exists():
            return {}
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("actions") if isinstance(payload, Mapping) else None
        out: dict[str, MutationActionRegistration] = {}
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            try:
                registration = MutationActionRegistration(
                    action_id=str(row["action_id"]),
                    mutation_domain=str(row["domain"]),
                    authority_class=AuthorityClass(str(row["authority_class"])),
                    lifecycle_phase=LifecyclePhase(str(row["lifecycle_phase"])),
                    canonical_handler=str(row["canonical_handler"]),
                    canonical_artifact_boundary=str(row["canonical_artifact_boundary"]),
                    provenance_expectation=str(row["provenance_expectation"]),
                    authority_of_judgment_applies=bool(row["authority_of_judgment_applies"]),
                )
            except Exception:
                continue
            out[registration.action_id] = registration
        return out

    def register_handler(self, action_id: str, handler: CanonicalMutationHandler) -> None:
        self._handlers[action_id] = handler

    def execute(self, action: TypedMutationAction) -> MutationExecutionResult:
        registration = self._registry.get(action.action_id)
        if registration is None:
            raise ValueError(f"missing_action_registration:{action.action_id}")
        if action.action_id not in self._handlers:
            raise ValueError(f"missing_action_handler:{action.action_id}")
        if registration.mutation_domain != action.mutation_domain:
            raise ValueError(f"mismatched_domain:{action.action_id}")
        if registration.authority_class != action.authority_class:
            raise ValueError(f"mismatched_authority_class:{action.action_id}")
        if registration.lifecycle_phase != action.lifecycle_phase:
            raise ValueError(f"mismatched_lifecycle_phase:{action.action_id}")

        kernel = get_control_plane_kernel()
        kernel.set_phase(action.lifecycle_phase, actor="constitutional_mutation_router")
        decision = kernel.admit(
            ControlActionRequest(
                action_kind=action.action_kind,
                authority_class=action.authority_class,
                actor=action.execution_owner,
                target_subsystem=action.target_subsystem,
                requested_phase=action.lifecycle_phase,
                metadata={
                    "correlation_id": action.correlation_id,
                    "source": action.execution_source,
                    "mutation_domain": action.mutation_domain,
                    "typed_action_id": action.action_id,
                    "advisory_context": dict(action.advisory_context),
                    "protected_mutation_intent": action.provenance_intent.to_kernel_metadata(),
                    **dict(action.payload),
                },
            ),
        )
        handler_result = None
        if decision.allowed:
            admission = build_admission_provenance(decision)
            handler_result = self._handlers[action.action_id](action, admission)
        else:
            admission = None
        record_forge_event(
            {
                "event": "constitutional_mutation_router_execution",
                "typed_action_id": action.action_id,
                "mutation_domain": action.mutation_domain,
                "correlation_id": action.correlation_id,
                "final_disposition": decision.outcome.value,
                "reason_codes": list(decision.reason_codes),
                "canonical": True,
                "executed": decision.allowed,
                "admission_decision_ref": decision.admission_decision_ref,
            }
        )
        return MutationExecutionResult(
            executed=decision.allowed,
            decision_reason_codes=decision.reason_codes,
            correlation_id=decision.correlation_id,
            admission=admission,
            handler_result=handler_result,
            registry=registration,
        )


_ROUTER: ConstitutionalMutationRouter | None = None


def get_constitutional_mutation_router() -> ConstitutionalMutationRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = ConstitutionalMutationRouter()
    return _ROUTER
