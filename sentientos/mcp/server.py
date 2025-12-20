from __future__ import annotations

from typing import Callable, Dict, Tuple

from advisory_connector import ADVISORY_PHASE, AdvisoryRequest, AdvisoryResponse
from fastapi import Depends, FastAPI, HTTPException
from sentientos.innerworld.value_drift import AdvisoryToneSentinel

from .audit import MCPAuditLogger
from .gate import (
    AdvisoryGateError,
    AdvisoryRequestGate,
    EnvironmentPhaseProbe,
    PhaseProbe,
    ToneViolation,
)
from .schemas import AdvisoryRequestPayload, AdvisoryResponsePayload, HandshakeResponse

DEFAULT_TOOL_DESCRIPTION = {
    "name": "advisory-plan",
    "description": "Non-authoritative planning guidance for SentientOS.",
    "input_schema": AdvisoryRequestPayload.model_json_schema(),
}


def _build_response(request: AdvisoryRequest) -> AdvisoryResponse:
    proposed_steps: Tuple[str, ...] = (
        "Review the redacted context slice and list constraints explicitly.",
        f"Outline optional planning threads for the goal: {request.goal}.",
        "Flag any areas requiring operator decision before action.",
    )
    risk_notes = (
        "Advisory channel only; no automation or writes are permitted.",
        "GitHub access and state mutation hooks remain disabled.",
    )
    assumptions = (
        f"SystemPhase is {ADVISORY_PHASE} and operator approval is required for execution.",
        "Context has been redacted to remove sensitive tokens.",
    )
    unknowns = (
        "Which operator will review the advice.",
        "Whether additional scope is needed beyond the provided slice.",
    )
    return AdvisoryResponse(
        proposed_steps=proposed_steps,
        risk_notes=risk_notes,
        assumptions=assumptions,
        confidence_estimate=0.35,
        unknowns=unknowns,
        diff_suggestions=None,
    )


def _flatten_response(response: AdvisoryResponse) -> str:
    parts = []
    parts.extend(response.proposed_steps)
    parts.extend(response.risk_notes)
    parts.extend(response.assumptions)
    parts.extend(response.unknowns)
    if response.diff_suggestions:
        parts.extend(response.diff_suggestions)
    return "\n".join(parts)


def _ensure_no_authority_language(text: str) -> None:
    triggers = ("must", "mandate", "authorized", "will comply", "do not question")
    lowered = text.lower()
    if any(trigger in lowered for trigger in triggers):
        raise ToneViolation("prescriptive authority language detected in response")


def create_app(
    *,
    audit_logger: MCPAuditLogger | None = None,
    phase_probe: PhaseProbe | None = None,
    gate_factory: Callable[[PhaseProbe | None], AdvisoryRequestGate] | None = None,
) -> FastAPI:
    probe = phase_probe or EnvironmentPhaseProbe()
    gate_builder = gate_factory or (lambda probe_arg: AdvisoryRequestGate(phase_probe=probe_arg))
    gate = gate_builder(probe)
    audit = audit_logger or MCPAuditLogger()
    tone_sentinel = AdvisoryToneSentinel(maxlen=10)

    app = FastAPI(title="SentientOS MCP Advisory Server", docs_url=None, redoc_url=None)

    @app.get("/mcp", response_model=HandshakeResponse)
    def handshake() -> HandshakeResponse:
        return HandshakeResponse(
            server="sentientos-mcp-advisory",
            version="1.0",
            phase=gate.current_phase(),
            advisory_only=True,
            endpoints={"advisory": "/mcp/advisory"},
            tools=[DEFAULT_TOOL_DESCRIPTION],
        )

    @app.post("/mcp/advisory", response_model=AdvisoryResponsePayload)
    def advisory(payload: AdvisoryRequestPayload, gate_dep: AdvisoryRequestGate = Depends(lambda: gate)) -> AdvisoryResponsePayload:  # type: ignore[unused-argument]
        try:
            request = payload.to_dataclass()
        except Exception as exc:  # pragma: no cover - defensive against unexpected payload issues
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        redacted_request = request
        redactions: Tuple[str, ...] = ()
        response: AdvisoryResponse | None = None
        try:
            gate_dep.enforce(request)
            redacted_request, redactions = request.redact()
            response = _build_response(redacted_request)
            flattened = _flatten_response(response)
            _ensure_no_authority_language(flattened)
            response.validate()
        except (AdvisoryGateError, ValueError) as exc:
            if not redactions:
                redacted_request, redactions = request.redact()
            audit.log(
                request=redacted_request,
                response=response,
                redactions=redactions,
                decision="rejected",
                reason=str(exc),
                tone_report=None,
            )
            status = 403 if isinstance(exc, ToneViolation) is False else 400
            raise HTTPException(status_code=status, detail=str(exc)) from exc

        tone_sentinel.record_response(flattened)
        tone_report: Dict[str, object] = tone_sentinel.detect_tone_shift()

        audit.log(
            request=redacted_request,
            response=response,
            redactions=redactions,
            decision="accepted",
            reason="advisory response issued",
            tone_report=tone_report,
        )
        return AdvisoryResponsePayload.from_dataclass(response)

    return app


APP = create_app()
__all__ = ["APP", "create_app"]
