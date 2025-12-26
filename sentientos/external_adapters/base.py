from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, MutableMapping, Protocol, Sequence


ExternalEffects = Literal["yes", "no"]
Reversibility = Literal["guaranteed", "bounded", "none"]
AuthorityImpact = Literal["none", "local", "global"]


@dataclass(frozen=True)
class AdapterMetadata:
    adapter_id: str
    capabilities: Sequence[str]
    scope: str
    external_effects: ExternalEffects
    reversibility: Reversibility
    requires_privilege: bool
    allow_epr: bool = False


@dataclass(frozen=True)
class AdapterActionSpec:
    action: str
    capability: str
    authority_impact: AuthorityImpact
    external_effects: ExternalEffects
    reversibility: Reversibility
    requires_privilege: bool


@dataclass(frozen=True)
class AdapterActionResult:
    action: str
    outcome: Mapping[str, object]
    rollback_ref: Mapping[str, object] | None = None


@dataclass(frozen=True)
class AdapterRollbackResult:
    action: str
    success: bool
    detail: Mapping[str, object]


class ExecutionContext(Protocol):
    source: str
    task_id: str | None
    routine_id: str | None
    request_fingerprint: str
    authorization: object
    admission_token: object | None
    approved_privileges: Sequence[str]
    required_privileges: Sequence[str]

    def as_log_context(self) -> MutableMapping[str, object]:
        ...


class ExternalAdapter(Protocol):
    metadata: AdapterMetadata
    action_specs: Mapping[str, AdapterActionSpec]

    def probe(self) -> bool:
        ...

    def describe(self) -> AdapterMetadata:
        ...

    def execute(
        self,
        action: str,
        params: Mapping[str, object],
        context: ExecutionContext,
    ) -> AdapterActionResult:
        ...

    def rollback(
        self,
        ref: Mapping[str, object],
        context: ExecutionContext,
    ) -> AdapterRollbackResult:
        ...


__all__ = [
    "AdapterActionResult",
    "AdapterActionSpec",
    "AdapterMetadata",
    "AdapterRollbackResult",
    "AuthorityImpact",
    "ExecutionContext",
    "ExternalAdapter",
    "ExternalEffects",
    "Reversibility",
]
