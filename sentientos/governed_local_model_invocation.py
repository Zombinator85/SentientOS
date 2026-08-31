from __future__ import annotations

import json, os, time, concurrent.futures
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast

from .control_plane_kernel import AuthorityClass, ControlActionRequest, ControlPlaneKernel, LifecyclePhase, get_control_plane_kernel
from .local_model_authority import LocalModelAuthorityMap, LocalModelAuthorityRecord, atomic_write_json, digest_payload, validate_authority_map

SUPPORTED_PURPOSES = {"local_user_chat", "local_model_commissioning_smoke", "genesis_proposal_advice", "discernment_judgment"}
FORBIDDEN_EFFECTS = {"provider_network": False, "tool": False, "memory": False, "action": False, "adoption": False, "repository_mutation": False}

def _digest_text(payload: Any) -> str:
    value: str = digest_payload(payload)
    return value

@dataclass(frozen=True)
class LocalModelInvocationBudget:
    max_input_chars: int = 8000
    max_output_chars: int = 4000
    max_new_tokens: int = 512
    timeout_seconds: float = 30.0
    max_calls_per_correlation: int = 1

    def to_dict(self) -> dict[str, Any]: return dict(self.__dict__)

@dataclass(frozen=True)
class LocalModelInvocationRequest:
    purpose: str
    prompt: str
    model_id: str
    authority_map_digest: str
    model_artifact_digest: str | None
    caller: str
    lifecycle_phase: str
    correlation_id: str
    expected_output_format: str = "text"
    budget: LocalModelInvocationBudget = field(default_factory=LocalModelInvocationBudget)
    upstream_evidence: Mapping[str, Any] = field(default_factory=dict)
    linkage: Mapping[str, Any] = field(default_factory=dict)
    active_model_identity: Mapping[str, Any] = field(default_factory=dict)
    structured_output_schema: Mapping[str, Any] | None = None

    def semantic_payload(self) -> dict[str, Any]:
        return {"purpose": self.purpose, "prompt_digest": digest_payload({"prompt": self.prompt}), "prompt_size": len(self.prompt.encode("utf-8")), "model_id": self.model_id, "authority_map_digest": self.authority_map_digest, "model_artifact_digest": self.model_artifact_digest, "active_model_identity": dict(self.active_model_identity), "caller": self.caller, "lifecycle_phase": self.lifecycle_phase, "correlation_id": self.correlation_id, "expected_output_format": self.expected_output_format, "structured_output_schema": dict(self.structured_output_schema) if self.structured_output_schema is not None else None, "budget": self.budget.to_dict(), "upstream_evidence": dict(self.upstream_evidence), "linkage": dict(self.linkage), "allowed_effects": {"local_model_inference": True}, "forbidden_effects": dict(FORBIDDEN_EFFECTS)}

    @property
    def request_digest(self) -> str: return _digest_text(self.semantic_payload())
    @property
    def request_id(self) -> str: return "lmreq-" + self.request_digest[:24]

    def to_receipt_request_dict(self) -> dict[str, Any]:
        p = self.semantic_payload(); p.update({"request_id": self.request_id, "request_digest": self.request_digest, "raw_prompt_stored": False, "ephemeral_prompt_handling": "raw prompt used only for immediate local backend call"}); return p

@dataclass(frozen=True)
class LocalModelInvocationDecision:
    admitted: bool
    status: str
    reason_codes: tuple[str, ...]
    admission_decision_ref: str | None
    control_plane: Mapping[str, Any]

@dataclass(frozen=True)
class LocalModelInvocationReceipt:
    request: Mapping[str, Any]
    status: str
    reason_codes: tuple[str, ...]
    output_text: str | None
    output_digest: str | None
    output_size_bytes: int
    generation_config: Mapping[str, Any]
    admission_decision_ref: str | None
    purpose: str
    latency_ms: int
    output_truncated: bool
    fallback_occurred: bool
    effects: Mapping[str, bool]
    observed_at: str

    def semantic_payload(self) -> dict[str, Any]:
        return {"request": dict(self.request), "status": self.status, "reason_codes": list(self.reason_codes), "output_digest": self.output_digest, "output_size_bytes": self.output_size_bytes, "generation_config": dict(self.generation_config), "admission_decision_ref": self.admission_decision_ref, "purpose": self.purpose, "output_truncated": self.output_truncated, "fallback_occurred": self.fallback_occurred, "effects": dict(self.effects)}

    @property
    def receipt_digest(self) -> str: return _digest_text(self.semantic_payload())
    @property
    def receipt_id(self) -> str: return "lmrec-" + self.receipt_digest[:24]
    def to_dict(self, *, include_output: bool = False) -> dict[str, Any]:
        p = self.semantic_payload(); p.update({"receipt_id": self.receipt_id, "receipt_digest": self.receipt_digest, "latency_ms": self.latency_ms, "observed_at": self.observed_at})
        if include_output and self.output_text is not None: p["output_text"] = self.output_text
        return p


def validate_receipt(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    semantic = {k: payload.get(k) for k in ["request", "status", "reason_codes", "output_digest", "output_size_bytes", "generation_config", "admission_decision_ref", "purpose", "output_truncated", "fallback_occurred", "effects"]}
    if payload.get("receipt_digest") != digest_payload(semantic): reasons.append("receipt_digest_mismatch")
    if payload.get("receipt_id") != "lmrec-" + digest_payload(semantic)[:24]: reasons.append("receipt_id_mismatch")
    effects = payload.get("effects")
    if not isinstance(effects, Mapping) or any(bool(effects.get(k)) for k in FORBIDDEN_EFFECTS): reasons.append("forbidden_effect_recorded")
    return not reasons, reasons


def _status_for_denial(outcome: str) -> str:
    if outcome == "defer": return "deferred"
    if outcome == "deny": return "denied"
    return "blocked_invalid"

class GovernedLocalModelInvoker:
    def __init__(self, *, model: Any, authority_map: LocalModelAuthorityMap, kernel: ControlPlaneKernel | None = None, runtime_root: Path | None = None) -> None:
        self.model = model; self.authority_map = authority_map; self.kernel = kernel or get_control_plane_kernel(); self.runtime_root = Path(runtime_root or Path(os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT", "/tmp/sentientos_runtime_state")) / "governed_local_model_invocation"); self.runtime_root.mkdir(parents=True, exist_ok=True); self.invocation_counts: dict[str, int] = {}

    def build_request(self, *, purpose: str, prompt: str, caller: str, correlation_id: str, lifecycle_phase: str = "runtime", expected_output_format: str = "text", budget: LocalModelInvocationBudget | None = None, upstream_evidence: Mapping[str, Any] | None = None, linkage: Mapping[str, Any] | None = None, structured_output_schema: Mapping[str, Any] | None = None) -> LocalModelInvocationRequest:
        identity = getattr(self.model, "active_identity", None)
        record = self.authority_map.record_for_active_identity(identity, purpose) if identity is not None else self.authority_map.eligible_record(purpose)
        if record is None and self.authority_map.records:
            record = self.authority_map.records[0]
        if record is None: raise ValueError("authority_map_has_no_records")
        if structured_output_schema is not None and (purpose != "discernment_judgment" or expected_output_format != "json"):
            raise ValueError("structured output is restricted to discernment JSON")
        return LocalModelInvocationRequest(purpose=purpose, prompt=prompt, model_id=record.model_id, authority_map_digest=self.authority_map.map_digest, model_artifact_digest=record.model_content_sha256, caller=caller, lifecycle_phase=lifecycle_phase, correlation_id=correlation_id, expected_output_format=expected_output_format, budget=budget or LocalModelInvocationBudget(), upstream_evidence=upstream_evidence or {}, linkage=linkage or {}, active_model_identity=identity.to_dict() if identity is not None else {}, structured_output_schema=dict(structured_output_schema) if structured_output_schema is not None else None)

    def invoke(self, request: LocalModelInvocationRequest, *, persist: bool = True, include_output_in_receipt: bool = False) -> LocalModelInvocationReceipt:
        started = time.monotonic(); status = "blocked_invalid"; reasons: list[str] = [] ; output: str | None = None; admitted_ref = None; fallback = False; truncated = False
        record = self._record_for(request.model_id)
        ok, map_reasons = validate_authority_map(self.authority_map.to_dict())
        if not ok: reasons += ["authority_map_invalid", *map_reasons]
        if request.purpose not in SUPPORTED_PURPOSES: reasons.append("purpose_unsupported")
        if record is None: reasons.append("model_record_missing")
        elif record.runtime_eligibility_status != "eligible" or (request.purpose not in record.allowed_invocation_purposes and request.purpose != "local_model_commissioning_smoke"):
            if record.engine in {"null", "echo"} and request.purpose == "local_user_chat":
                reasons.append("simulation_backend")
            else: reasons.append("model_not_eligible_for_purpose")
        if len(request.prompt) > request.budget.max_input_chars: reasons.append("input_oversized")
        if request.expected_output_format not in {"text", "json"}: reasons.append("expected_output_format_invalid")
        if request.structured_output_schema is not None:
            schema = request.structured_output_schema
            if (request.purpose != "discernment_judgment" or request.expected_output_format != "json"
                    or not isinstance(schema.get("oneOf"), list)):
                reasons.append("structured_output_schema_invalid")
            else:
                from .discernment_participant import judgment_output_schema
                canonical_schema = judgment_output_schema(
                    proposition=str(request.linkage.get("proposition") or ""),
                    allowed_observation_namespace=str(
                        request.linkage.get("allowed_observation_namespace") or ""
                    ),
                )
                if dict(schema) != canonical_schema:
                    reasons.append("structured_output_schema_not_canonical")
        if request.purpose == "genesis_proposal_advice":
            ev = dict(request.upstream_evidence.get("genesis_review") or {}) if isinstance(request.upstream_evidence, Mapping) else {}
            link = dict(request.linkage or {})
            if not ev or ev.get("status") not in {"approved", "allow", "reviewed"}: reasons.append("genesis_review_evidence_missing_or_invalid")
            for key in ("need_identity", "signal_batch_digest", "authority_map_digest", "invocation_purpose", "proposal_only"):
                if key not in link: reasons.append(f"genesis_linkage_missing_{key}")
        if self.invocation_counts.get(request.correlation_id, 0) >= request.budget.max_calls_per_correlation: reasons.append("duplicate_correlation")
        if request.authority_map_digest != self.authority_map.map_digest: reasons.append("model_authority_stale")
        if record and request.model_artifact_digest != record.model_content_sha256: reasons.append("model_digest_mismatch")
        identity = getattr(self.model, "active_identity", None)
        if request.purpose in {"discernment_judgment", "local_model_commissioning_smoke"}:
            if identity is None:
                reasons.append("active_model_identity_unavailable")
            elif identity.fallback or identity.posture != "production":
                reasons.append("active_model_not_production")
            elif self.authority_map.record_for_active_identity(identity, request.purpose) != record:
                reasons.append("active_model_authority_mismatch")
            if identity is not None and request.active_model_identity != identity.to_dict():
                reasons.append("active_model_request_identity_mismatch")
        decision_payload: dict[str, Any] = {}
        if not any(r for r in reasons if r not in {"simulation_backend"}):
            phase = LifecyclePhase(request.lifecycle_phase) if request.lifecycle_phase in LifecyclePhase._value2member_map_ else self.kernel.phase
            cp_req = ControlActionRequest(action_kind="local_model_inference", authority_class=AuthorityClass.LOCAL_MODEL_INFERENCE, actor=request.caller, target_subsystem="governed_local_model_invocation", requested_phase=phase, metadata={"correlation_id": request.correlation_id, "purpose": request.purpose, "request_digest": request.request_digest})
            decision = self.kernel.admit(cp_req); decision_payload = decision.to_dict(); admitted_ref = decision.admission_decision_ref
            if not decision.allowed: reasons += list(decision.reason_codes); status = _status_for_denial(decision.outcome.value)
            else:
                try:
                    self.invocation_counts[request.correlation_id] = self.invocation_counts.get(request.correlation_id, 0) + 1
                    generation = {"max_new_tokens": min(request.budget.max_new_tokens, int(record.generation_ceilings.get("max_new_tokens", request.budget.max_new_tokens))) if record else request.budget.max_new_tokens, "temperature": 0 if request.purpose in {"genesis_proposal_advice", "discernment_judgment", "local_model_commissioning_smoke"} else None, "structured_output_schema": dict(request.structured_output_schema) if request.structured_output_schema is not None else None}
                    gen_kwargs: dict[str, Any] = {k: v for k, v in generation.items() if v is not None}
                    def _call_model() -> str:
                        governed_generate = getattr(self.model, "generate_governed", None)
                        if governed_generate is not None:
                            return cast(str, governed_generate(request.prompt, **gen_kwargs))
                        try:
                            return cast(str, self.model.generate(request.prompt, **gen_kwargs))
                        except TypeError:
                            return cast(str, self.model.generate(request.prompt))
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(_call_model)
                        try:
                            output = future.result(timeout=max(float(request.budget.timeout_seconds), 0.001))
                        except concurrent.futures.TimeoutError as exc:
                            future.cancel()
                            raise TimeoutError() from exc
                    if len(output.encode("utf-8")) > request.budget.max_output_chars:
                        output = output.encode("utf-8")[:request.budget.max_output_chars].decode("utf-8", "ignore"); truncated = True; reasons.append("output_oversized")
                    if not output.strip(): reasons.append("empty_output"); status = "degraded_fallback"; fallback = True
                    elif request.purpose == "genesis_proposal_advice" and not self._valid_genesis_advice(output): reasons.append("output_malformed"); status = "output_malformed"
                    elif request.purpose == "discernment_judgment" and not self._valid_discernment_judgment(output, request): reasons.append("output_malformed"); status = "output_malformed"
                    else: status = "admitted_simulation" if record and record.engine in {"null", "echo"} else "admitted_completed"
                except TimeoutError: status = "timeout"; reasons.append("timeout")
                except Exception as exc: status = "backend_failure"; reasons.append(f"backend_failure:{exc.__class__.__name__}")
        if status == "blocked_invalid" and not reasons: reasons.append("blocked_invalid")
        receipt = LocalModelInvocationReceipt(request=request.to_receipt_request_dict(), status=status, reason_codes=tuple(reasons or ["completed"]), output_text=output, output_digest=digest_payload({"output": output}) if output is not None else None, output_size_bytes=len((output or "").encode("utf-8")), generation_config={**request.budget.to_dict(), "actual_generation_parameters": gen_kwargs if "gen_kwargs" in locals() else {}}, admission_decision_ref=admitted_ref, purpose=request.purpose, latency_ms=int((time.monotonic()-started)*1000), output_truncated=truncated, fallback_occurred=fallback, effects={"local_model_inference": status in {"admitted_completed", "admitted_simulation", "output_malformed", "degraded_fallback"}, **FORBIDDEN_EFFECTS}, observed_at=datetime.now(timezone.utc).isoformat())
        if persist: self._persist(request, receipt, decision_payload, include_output=include_output_in_receipt)
        return receipt

    def _record_for(self, model_id: str) -> LocalModelAuthorityRecord | None:
        return next((r for r in self.authority_map.records if r.model_id == model_id), None)

    def _persist(self, request: LocalModelInvocationRequest, receipt: LocalModelInvocationReceipt, decision: Mapping[str, Any], *, include_output: bool) -> None:
        atomic_write_json(self.runtime_root / "requests" / f"{request.request_id}.json", request.to_receipt_request_dict())
        if decision: atomic_write_json(self.runtime_root / "decisions" / f"{request.request_id}.json", dict(decision))
        atomic_write_json(self.runtime_root / "receipts" / f"{receipt.receipt_id}.json", receipt.to_dict(include_output=include_output))

    @staticmethod
    def _valid_genesis_advice(text: str) -> bool:
        try: data = json.loads(text)
        except json.JSONDecodeError: return False
        if not isinstance(data, Mapping): return False
        required = {"objective_refinement", "proposed_directives", "testing_requirements", "rationale", "capability_interpretation"}
        if not required.issubset(data): return False
        blob = json.dumps(data).lower()
        forbidden = ["import ", "subprocess", "shell", "git ", "openai", "huggingface", "http://", "https://", "adoptionrite", "specbinder", "write_file", "memory"]
        
        try:
            from .genesis_model_advice import parse_advice_output
            payload, reasons = parse_advice_output(text)
            return payload is not None and not reasons
        except Exception:
            return not any(item in blob for item in forbidden)

    @staticmethod
    def _valid_discernment_judgment(text: str, request: LocalModelInvocationRequest) -> bool:
        try:
            from .discernment_participant import validate_judgment_output
            validate_judgment_output(
                json.loads(text),
                allowed_observation_namespace=str(request.linkage.get("allowed_observation_namespace") or ""),
                expected_proposition=str(request.linkage.get("proposition") or ""),
            )
            return True
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
