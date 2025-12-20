from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Protocol
import json
import os

from advisory_connector import ADVISORY_PHASE, AdvisoryRequest
from system_continuity import SystemPhase


class PhaseProbe(Protocol):
    def current_phase(self) -> str:
        ...


class EnvironmentPhaseProbe:
    """Resolve the system phase from a file or environment variable."""

    def __init__(self, phase_file: Path | None = None) -> None:
        self.phase_file = phase_file or Path("sentientos_data/system_phase.txt")

    def current_phase(self) -> str:
        if self.phase_file.exists():
            return self.phase_file.read_text(encoding="utf-8").strip()
        env_value = os.getenv("SENTIENTOS_SYSTEM_PHASE")
        if env_value:
            return env_value
        # Fallback to a safe baseline that will not satisfy advisory checks
        return SystemPhase.GENESIS.name


class AdvisoryGateError(RuntimeError):
    pass


class PhaseViolation(AdvisoryGateError):
    pass


class ScopeViolation(AdvisoryGateError):
    pass


class PayloadLimitViolation(AdvisoryGateError):
    pass


class RedactionViolation(AdvisoryGateError):
    pass


class ToneViolation(AdvisoryGateError):
    pass


class SchemaViolation(AdvisoryGateError):
    pass


class AdvisoryRequestGate:
    """Validate advisory requests for MCP exposure."""

    def __init__(
        self,
        *,
        phase_probe: PhaseProbe | None = None,
        max_scope: int = 20,
        max_payload_bytes: int = 16_384,
    ) -> None:
        self.phase_probe = phase_probe or EnvironmentPhaseProbe()
        self.max_scope = max_scope
        self.max_payload_bytes = max_payload_bytes

    def enforce(self, request: AdvisoryRequest) -> None:
        try:
            request.validate()
        except ValueError as exc:
            raise SchemaViolation(str(exc)) from exc
        current_phase = self.phase_probe.current_phase()
        if current_phase != ADVISORY_PHASE:
            raise PhaseViolation("SystemPhase is not within ADVISORY_WINDOW")
        if len(request.context_slice) > self.max_scope:
            raise ScopeViolation("context scope exceeds maximum")
        if not request.redaction_profile:
            raise RedactionViolation("redaction_profile cannot be empty")
        if self._payload_size(request) > self.max_payload_bytes:
            raise PayloadLimitViolation("payload size exceeds advisory limit")
        if self._contains_authority_language(request.goal):
            raise ToneViolation("prescriptive authority language detected in goal")

    def current_phase(self) -> str:
        return self.phase_probe.current_phase()

    def _payload_size(self, request: AdvisoryRequest) -> int:
        return len(json.dumps(asdict(request)))

    def _contains_authority_language(self, text: str) -> bool:
        triggers = ("must", "mandate", "authorized", "will comply", "do not question")
        lowered = text.lower()
        return any(trigger in lowered for trigger in triggers)


def hash_dataclass(instance: object) -> str:
    serialized = json.dumps(asdict(instance), sort_keys=True)
    return sha256(serialized.encode("utf-8")).hexdigest()
