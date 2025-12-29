from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping
from uuid import uuid4

from log_utils import append_json, read_json
from logging_config import get_log_path
from sentientos.diagnostics import (
    DiagnosticError,
    ErrorClass,
    FailedPhase,
    build_error_frame,
)
from sentientos.introspection.spine import EventType, emit_introspection_event

from .contracts import SignalDirection, SignalType


class OperatorRole(str, Enum):
    OBSERVER = "OBSERVER"
    OPERATOR = "OPERATOR"
    STEWARD = "STEWARD"
    OWNER = "OWNER"


@dataclass(frozen=True)
class ConsentScope:
    signal_types: tuple[SignalType, ...]
    duration_seconds: int
    context: str

    def to_dict(self) -> dict[str, object]:
        return {
            "signal_types": [signal_type.value for signal_type in self.signal_types],
            "duration_seconds": self.duration_seconds,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ConsentScope":
        raw_types = payload.get("signal_types", ())
        signal_types: list[SignalType] = []
        if isinstance(raw_types, Iterable) and not isinstance(raw_types, (str, bytes)):
            for raw in raw_types:
                try:
                    signal_types.append(SignalType(str(raw)))
                except ValueError:
                    continue
        raw_duration = payload.get("duration_seconds", 0)
        try:
            duration = int(raw_duration)
        except (TypeError, ValueError):
            duration = 0
        return cls(
            signal_types=tuple(signal_types),
            duration_seconds=duration,
            context=str(payload.get("context", "")),
        )


@dataclass(frozen=True)
class ConsentContract:
    contract_id: str
    operator_role_required: OperatorRole
    scope: ConsentScope
    expiration: datetime
    revocable: bool = True
    simulation_only: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_id": self.contract_id,
            "operator_role_required": self.operator_role_required.value,
            "scope": self.scope.to_dict(),
            "expiration": _format_timestamp(self.expiration),
            "revocable": self.revocable,
            "simulation_only": self.simulation_only,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ConsentContract":
        expiration = _parse_timestamp(str(payload.get("expiration", "")))
        operator_value = str(payload.get("operator_role_required", "OBSERVER"))
        try:
            operator_role = OperatorRole(operator_value)
        except ValueError:
            operator_role = OperatorRole.OBSERVER
        scope_payload = payload.get("scope", {})
        scope = ConsentScope.from_dict(scope_payload if isinstance(scope_payload, Mapping) else {})
        return cls(
            contract_id=str(payload.get("contract_id", "")),
            operator_role_required=operator_role,
            scope=scope,
            expiration=expiration,
            revocable=bool(payload.get("revocable", True)),
            simulation_only=bool(payload.get("simulation_only", True)),
        )


@dataclass(frozen=True)
class ConsentContractRecord:
    contract: ConsentContract
    status: str
    revoked_at: datetime | None
    revocation_reason: str | None

    def to_dict(self) -> dict[str, object]:
        payload = {
            **self.contract.to_dict(),
            "status": self.status,
            "revoked_at": _format_timestamp(self.revoked_at) if self.revoked_at else None,
            "revocation_reason": self.revocation_reason,
        }
        return payload


@dataclass(frozen=True)
class ConsentEvaluation:
    approved: bool
    reason: str
    contract: ConsentContract | None


class ConsentLedger:
    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or get_log_path("consent_contracts.jsonl", "CONSENT_CONTRACT_LOG")

    def grant_contract(
        self,
        *,
        operator_role: OperatorRole,
        signal_types: Iterable[SignalType],
        context: str,
        duration_seconds: int,
        issued_at: datetime | None = None,
    ) -> ConsentContract:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        issued_at = issued_at or datetime.now(timezone.utc)
        expiration = issued_at + timedelta(seconds=duration_seconds)
        scope = ConsentScope(
            signal_types=tuple(signal_types),
            duration_seconds=duration_seconds,
            context=context,
        )
        contract = ConsentContract(
            contract_id=str(uuid4()),
            operator_role_required=operator_role,
            scope=scope,
            expiration=expiration,
            revocable=True,
            simulation_only=True,
        )
        append_json(
            Path(self.log_path),
            {
                "event": "consent_grant",
                "issued_at": _format_timestamp(issued_at),
                "contract": contract.to_dict(),
            },
        )
        return contract

    def revoke_contract(
        self,
        contract_id: str,
        *,
        reason: str | None = None,
        revoked_at: datetime | None = None,
    ) -> dict[str, object]:
        revoked_at = revoked_at or datetime.now(timezone.utc)
        entry = {
            "event": "consent_revoke",
            "contract_id": contract_id,
            "reason": reason or "operator_revocation",
            "revoked_at": _format_timestamp(revoked_at),
        }
        append_json(Path(self.log_path), entry)
        return entry

    def list_records(self, *, current_time: datetime | None = None) -> list[ConsentContractRecord]:
        current_time = current_time or datetime.now(timezone.utc)
        entries = read_json(Path(self.log_path))
        contracts: dict[str, ConsentContract] = {}
        revocations: dict[str, dict[str, object]] = {}
        for entry in entries:
            if entry.get("event") == "consent_grant":
                contract_payload = entry.get("contract")
                if isinstance(contract_payload, Mapping):
                    contract = ConsentContract.from_dict(contract_payload)
                    contracts[contract.contract_id] = contract
            if entry.get("event") == "consent_revoke":
                contract_id = str(entry.get("contract_id", ""))
                revocations[contract_id] = {
                    "revoked_at": _parse_timestamp(str(entry.get("revoked_at", ""))),
                    "reason": entry.get("reason"),
                }
        records: list[ConsentContractRecord] = []
        for contract in contracts.values():
            revoked = revocations.get(contract.contract_id)
            if revoked:
                status = "revoked"
                revoked_at = revoked.get("revoked_at")
                if not isinstance(revoked_at, datetime):
                    revoked_at = None
                records.append(
                    ConsentContractRecord(
                        contract=contract,
                        status=status,
                        revoked_at=revoked_at,
                        revocation_reason=str(revoked.get("reason")) if revoked.get("reason") else None,
                    )
                )
                continue
            if current_time >= contract.expiration:
                status = "expired"
            else:
                status = "active"
            records.append(
                ConsentContractRecord(
                    contract=contract,
                    status=status,
                    revoked_at=None,
                    revocation_reason=None,
                )
            )
        records.sort(key=lambda record: record.contract.contract_id)
        return records

    def evaluate(
        self,
        *,
        direction: SignalDirection,
        signal_type: SignalType,
        context: str,
        required_role: OperatorRole,
        current_time: datetime | None = None,
    ) -> ConsentEvaluation:
        if direction != SignalDirection.EGRESS:
            return ConsentEvaluation(approved=True, reason="ingress", contract=None)
        current_time = current_time or datetime.now(timezone.utc)
        records = self.list_records(current_time=current_time)
        normalized_context = context.strip().lower()
        matching = []
        for record in records:
            contract = record.contract
            if not contract.simulation_only:
                continue
            if contract.operator_role_required != required_role:
                continue
            if signal_type not in contract.scope.signal_types:
                continue
            if contract.scope.context.strip().lower() != normalized_context:
                continue
            matching.append(record)
        active = next((record for record in matching if record.status == "active"), None)
        if active:
            return ConsentEvaluation(approved=True, reason="active", contract=active.contract)
        if any(record.status == "revoked" for record in matching):
            return ConsentEvaluation(approved=False, reason="revoked", contract=None)
        if any(record.status == "expired" for record in matching):
            return ConsentEvaluation(approved=False, reason="expired", contract=None)
        if matching:
            return ConsentEvaluation(approved=False, reason="inactive", contract=None)
        return ConsentEvaluation(approved=False, reason="missing", contract=None)


def require_consent(
    *,
    direction: SignalDirection,
    signal_type: SignalType,
    context: str,
    ledger: ConsentLedger | None = None,
    introspection_path: str | None = None,
) -> ConsentContract | None:
    ledger = ledger or ConsentLedger()
    required_role = _required_role_for(direction, signal_type)
    evaluation = ledger.evaluate(
        direction=direction,
        signal_type=signal_type,
        context=context,
        required_role=required_role,
    )
    metadata = {
        "direction": direction.value,
        "signal_type": signal_type.value,
        "context": context,
        "required_role": required_role.value,
        "result": "approved" if evaluation.approved else "refused",
        "reason": evaluation.reason,
    }
    if evaluation.contract is not None:
        metadata["contract_id"] = evaluation.contract.contract_id
        metadata["expiration"] = _format_timestamp(evaluation.contract.expiration)
    emit_introspection_event(
        event_type=EventType.CLI_ACTION,
        phase="consent_gate",
        summary="Consent gate approved." if evaluation.approved else "Consent gate refused.",
        metadata=metadata,
        path=introspection_path or "logs/introspection_spine.jsonl",
    )
    if evaluation.approved:
        return evaluation.contract
    frame = build_error_frame(
        error_code="CONSENT_REQUIRED",
        error_class=ErrorClass.INTEGRITY,
        failed_phase=FailedPhase.CLI,
        violated_invariant="CONSENT_GATE",
        suppressed_actions=["auto_recovery", "retry", "state_mutation"],
        human_summary="Consent contract is required for this simulated egress.",
        technical_details=metadata,
    )
    raise DiagnosticError(frame)


def _required_role_for(direction: SignalDirection, signal_type: SignalType) -> OperatorRole:
    if direction == SignalDirection.EGRESS:
        return OperatorRole.OPERATOR
    return OperatorRole.OBSERVER


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)


__all__ = [
    "ConsentContract",
    "ConsentContractRecord",
    "ConsentLedger",
    "ConsentScope",
    "OperatorRole",
    "require_consent",
]
