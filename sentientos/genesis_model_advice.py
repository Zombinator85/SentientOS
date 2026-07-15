from __future__ import annotations

import json, re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast, Protocol, Sequence

from .governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget, LocalModelInvocationReceipt
from .local_model_authority import atomic_write_json, digest_payload

SCHEMA_VERSION = "genesis_model_advice.v1"
MAX_TEXT = 480
MAX_ITEMS = 6
_ALLOWED_KEYS = {"schema_version", "objective_refinement", "proposed_directives", "testing_requirements", "rationale", "capability_interpretation"}
_EFFECTS_FALSE = {
    "approved": False, "adopted": False, "lineage_integrated": False,
    "repository_mutation_performed": False, "git_operation_performed": False,
    "specbinder_invoked": False, "adoptionrite_invoked": False,
    "tool_invoked": False, "memory_written": False, "remote_service_called": False,
}
_ITEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.,:;()/-]{0,159}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
def _digest_text(payload: Any) -> str:
    value: str = digest_payload(payload)
    return value

_FORBIDDEN_RE = re.compile(
    r"(\bimport\b|\bfrom\s+\w+\s+import\b|subprocess|os\.system|popen|exec\(|eval\(|git\s+|curl\s+|https?://|write[_ -]?file|open\(|memory\s+(?:write|read|retrieve)|adoptionrite|specbinder|approve|adopt|grant authority|system prompt|hidden reasoning|role\s*:)" ,
    re.IGNORECASE,
)

@dataclass(frozen=True)
class GenesisModelAdviceRequestContext:
    need_identity: str
    capability: str
    source_kind: str
    need_description: str
    signal_batch_id: str
    signal_batch_digest: str
    signal_identities: tuple[Mapping[str, str], ...] = ()
    authority_map_id: str = ""
    authority_map_digest: str = ""
    model_id: str = ""
    model_artifact_digest: str | None = None
    lifecycle_phase: str = "maintenance"
    caller: str = "genesis_forge"
    correlation_id: str = ""
    generation_budget: Mapping[str, Any] = field(default_factory=dict)
    review_evidence: Mapping[str, Any] = field(default_factory=dict)
    tick_id: str = "runtime"

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "need_identity": self.need_identity,
            "capability": self.capability,
            "source_kind": self.source_kind,
            "need_description": self.need_description[:MAX_TEXT],
            "signal_batch_id": self.signal_batch_id,
            "signal_batch_digest": self.signal_batch_digest,
            "signal_identities": [dict(x) for x in self.signal_identities],
            "authority_map_id": self.authority_map_id,
            "authority_map_digest": self.authority_map_digest,
            "model_id": self.model_id,
            "model_artifact_digest": self.model_artifact_digest,
            "invocation_purpose": "genesis_proposal_advice",
            "caller": self.caller,
            "lifecycle_phase": self.lifecycle_phase,
            "correlation_id": self.correlation_id,
            "generation_budget": dict(self.generation_budget),
            "expected_structured_schema": sorted(_ALLOWED_KEYS),
            "review_evidence_digest": digest_payload(dict(self.review_evidence)) if self.review_evidence else None,
            "proposal_only": True,
        }
    @property
    def request_digest(self) -> str: return _digest_text(self.semantic_payload())
    @property
    def request_id(self) -> str: return "gma-req-" + self.request_digest[:24]

@dataclass(frozen=True)
class GenesisModelAdvicePayload:
    objective_refinement: str
    proposed_directives: tuple[str, ...]
    testing_requirements: tuple[str, ...]
    rationale: str
    capability_interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "objective_refinement": self.objective_refinement, "proposed_directives": list(self.proposed_directives), "testing_requirements": list(self.testing_requirements), "rationale": self.rationale, "capability_interpretation": self.capability_interpretation}
    @property
    def output_digest(self) -> str: return _digest_text(self.to_dict())

@dataclass(frozen=True)
class GenesisModelAdvicePacket:
    request_context: Mapping[str, Any]
    invocation_receipt: Mapping[str, Any]
    normalized_output: Mapping[str, Any] | None
    disposition: str
    validation_findings: tuple[str, ...]
    fallback_posture: str
    candidate_produced: bool
    candidate_semantic_digest: str | None = None
    effects: Mapping[str, bool] = field(default_factory=lambda: dict(_EFFECTS_FALSE))
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def semantic_payload(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "request_context": dict(self.request_context), "request_id": self.request_context.get("request_id"), "request_digest": self.request_context.get("request_digest"), "receipt_id": self.invocation_receipt.get("receipt_id"), "receipt_digest": self.invocation_receipt.get("receipt_digest"), "normalized_output": dict(self.normalized_output or {}), "normalized_output_digest": digest_payload(self.normalized_output) if self.normalized_output else None, "model_id": self.request_context.get("model_id"), "authority_map_id": self.request_context.get("authority_map_id"), "authority_map_digest": self.request_context.get("authority_map_digest"), "signal_batch_id": self.request_context.get("signal_batch_id"), "signal_batch_digest": self.request_context.get("signal_batch_digest"), "need_identity": self.request_context.get("need_identity"), "disposition": self.disposition, "validation_findings": list(self.validation_findings), "fallback_posture": self.fallback_posture, "candidate_produced": self.candidate_produced, "candidate_semantic_digest": self.candidate_semantic_digest, "effects": dict(self.effects)}
    @property
    def packet_digest(self) -> str: return _digest_text(self.semantic_payload())
    @property
    def packet_id(self) -> str: return "gma-pkt-" + self.packet_digest[:24]
    def to_dict(self) -> dict[str, Any]:
        p = self.semantic_payload(); p.update({"packet_id": self.packet_id, "packet_digest": self.packet_digest, "observed_at": self.observed_at}); return p

class GenesisModelAdviceSource(Protocol):
    def advice_for_need(self, need: Any, *, signal_batch: Mapping[str, Any], tick_id: str, budget: LocalModelInvocationBudget | None = None) -> GenesisModelAdvicePacket: ...

def _bounded_text(value: Any, field: str, reasons: list[str]) -> str:
    if not isinstance(value, str): reasons.append(f"{field}_type_invalid"); return ""
    text = " ".join(value.strip().split())
    if not text: reasons.append(f"{field}_empty")
    if len(text) > MAX_TEXT: reasons.append(f"{field}_oversized")
    if any(ord(ch) < 32 for ch in value): reasons.append(f"{field}_control_char")
    if _FORBIDDEN_RE.search(text): reasons.append(f"{field}_forbidden_semantics")
    return text[:MAX_TEXT]

def _bounded_items(value: Any, field: str, reasons: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list): reasons.append(f"{field}_type_invalid"); return ()
    if not value or len(value) > MAX_ITEMS: reasons.append(f"{field}_count_invalid")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _bounded_text(item, field, reasons)
        key = text.lower()
        if key in seen: reasons.append(f"{field}_duplicate")
        seen.add(key)
        if text and not _ITEM_RE.match(text): reasons.append(f"{field}_item_malformed")
        out.append(text)
    return tuple(out[:MAX_ITEMS])

def parse_advice_output(text: str) -> tuple[GenesisModelAdvicePayload | None, list[str]]:
    reasons: list[str] = []
    if not text or not text.strip(): return None, ["empty_output"]
    if len(text.encode()) > 6000: reasons.append("output_oversized")
    try: data = json.loads(text)
    except json.JSONDecodeError: return None, ["malformed_json"]
    if not isinstance(data, dict): return None, ["root_not_object"]
    keys = set(data)
    missing = _ALLOWED_KEYS - keys; extra = keys - _ALLOWED_KEYS
    if missing: reasons.extend(f"missing_{k}" for k in sorted(missing))
    if extra: reasons.extend(f"unexpected_{k}" for k in sorted(extra))
    if data.get("schema_version") != SCHEMA_VERSION: reasons.append("schema_version_invalid")
    obj = _bounded_text(data.get("objective_refinement"), "objective_refinement", reasons)
    dirs = _bounded_items(data.get("proposed_directives"), "proposed_directives", reasons)
    tests = _bounded_items(data.get("testing_requirements"), "testing_requirements", reasons)
    rat = _bounded_text(data.get("rationale"), "rationale", reasons)
    cap = _bounded_text(data.get("capability_interpretation"), "capability_interpretation", reasons)
    if reasons: return None, reasons
    return GenesisModelAdvicePayload(obj, dirs, tests, rat, cap), []

def validate_packet(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    sem = {k: payload.get(k) for k in ["schema_version", "request_context", "request_id", "request_digest", "receipt_id", "receipt_digest", "normalized_output", "normalized_output_digest", "model_id", "authority_map_id", "authority_map_digest", "signal_batch_id", "signal_batch_digest", "need_identity", "disposition", "validation_findings", "fallback_posture", "candidate_produced", "candidate_semantic_digest", "effects"]}
    reasons: list[str] = []
    d = digest_payload(sem)
    if payload.get("packet_digest") != d: reasons.append("packet_digest_mismatch")
    if payload.get("packet_id") != "gma-pkt-" + d[:24]: reasons.append("packet_id_mismatch")
    if any(bool(dict(payload.get("effects") or {}).get(k)) for k in _EFFECTS_FALSE): reasons.append("forbidden_effect_recorded")
    return not reasons, reasons

def build_prompt(context: GenesisModelAdviceRequestContext) -> str:
    payload = context.semantic_payload()
    return json.dumps({"task": "bounded_genesis_proposal_advice", "advisory_only": True, "forbidden_effects": list(_EFFECTS_FALSE), "input": payload, "output_schema": {k: "string_or_string_array" for k in sorted(_ALLOWED_KEYS)}}, sort_keys=True, separators=(",", ":"))

class GenesisModelAdviceCoordinator:
    def __init__(self, *, invoker: GovernedLocalModelInvoker | None, runtime_root: Path | None = None, review_evidence: Mapping[str, Any] | None = None) -> None:
        self.invoker = invoker; self.runtime_root = Path(runtime_root or "/tmp/sentientos_runtime_state") / "genesis_model_advice"; self.runtime_root.mkdir(parents=True, exist_ok=True); self.review_evidence = dict(review_evidence or {}); self.cache: dict[str, GenesisModelAdvicePacket] = {}; self.feedback = {"advice_attempts":0,"admitted_calls":0,"denied_calls":0,"deferred_calls":0,"malformed_outputs":0,"oversized_outputs":0,"backend_failures":0,"timeouts":0,"valid_advice_packets":0,"advice_derived_candidate_count":0,"deterministic_fallback_count":0,"no_slot_count":0,"cache_reuse_count":0,"second_call_prevention_count":0}
    def _fallback_packet(self, context: GenesisModelAdviceRequestContext, disposition: str, findings: Sequence[str]) -> GenesisModelAdvicePacket:
        pkt = GenesisModelAdvicePacket(request_context={**context.semantic_payload(), "request_id": context.request_id, "request_digest": context.request_digest}, invocation_receipt={}, normalized_output=None, disposition=disposition, validation_findings=tuple(findings), fallback_posture="deterministic_fallback", candidate_produced=False)
        self._persist(pkt); return pkt
    def advice_for_need(self, need: Any, *, signal_batch: Mapping[str, Any], tick_id: str, budget: LocalModelInvocationBudget | None = None) -> GenesisModelAdvicePacket:
        self.feedback["advice_attempts"] += 1
        if self.invoker is None:
            self.feedback["deferred_calls"] += 1; self.feedback["deterministic_fallback_count"] += 1
            ctx = self._context(need, signal_batch, tick_id, budget or LocalModelInvocationBudget())
            return self._fallback_packet(ctx, "no_invoker", ["no_governed_invoker"])
        ctx = self._context(need, signal_batch, tick_id, budget or LocalModelInvocationBudget())
        key = digest_payload({"tick_id": tick_id, "signal_batch_digest": ctx.signal_batch_digest, "need_identity": ctx.need_identity, "authority_map_digest": ctx.authority_map_digest, "model_id": ctx.model_id, "review_evidence": ctx.semantic_payload().get("review_evidence_digest"), "generation_budget": dict(ctx.generation_budget)})
        if key in self.cache:
            self.feedback["cache_reuse_count"] += 1; self.feedback["second_call_prevention_count"] += 1; return self.cache[key]
        if not self.review_evidence or self.review_evidence.get("status") not in {"approved", "allow", "reviewed"}:
            self.feedback["deferred_calls"] += 1; self.feedback["deterministic_fallback_count"] += 1
            pkt = self._fallback_packet(ctx, "review_evidence_unavailable", ["missing_or_invalid_review_evidence"]); self.cache[key] = pkt; return pkt
        prompt = build_prompt(ctx)
        req = self.invoker.build_request(purpose="genesis_proposal_advice", prompt=prompt, caller="genesis_forge", correlation_id=ctx.correlation_id, lifecycle_phase="maintenance", expected_output_format="json", budget=budget or LocalModelInvocationBudget(max_input_chars=12000, max_output_chars=6000, max_new_tokens=512, timeout_seconds=20), upstream_evidence={"genesis_review": self.review_evidence}, linkage=ctx.semantic_payload())
        rec = self.invoker.invoke(req, persist=True, include_output_in_receipt=True)
        if rec.status == "admitted_completed": self.feedback["admitted_calls"] += 1
        elif rec.status == "timeout": self.feedback["timeouts"] += 1
        elif rec.status == "backend_failure": self.feedback["backend_failures"] += 1
        else: self.feedback["denied_calls"] += 1
        payload, findings = parse_advice_output(rec.output_text or "")
        if findings:
            if "output_oversized" in findings or rec.output_truncated: self.feedback["oversized_outputs"] += 1
            else: self.feedback["malformed_outputs"] += 1
        norm = payload.to_dict() if payload else None
        disposition = "valid_advice" if payload and rec.status == "admitted_completed" and not rec.output_truncated else "invalid_or_denied"
        cand_digest = digest_payload({"need_identity": ctx.need_identity, "signal_batch_digest": ctx.signal_batch_digest, "advice_output_digest": payload.output_digest}) if disposition == "valid_advice" and payload else None
        pkt = GenesisModelAdvicePacket(request_context={**ctx.semantic_payload(), "request_id": ctx.request_id, "request_digest": ctx.request_digest}, invocation_receipt=rec.to_dict(include_output=False), normalized_output=norm, disposition=disposition, validation_findings=tuple(findings or list(rec.reason_codes)), fallback_posture="none" if disposition == "valid_advice" else "deterministic_fallback", candidate_produced=disposition == "valid_advice", candidate_semantic_digest=cand_digest)
        if pkt.candidate_produced: self.feedback["valid_advice_packets"] += 1; self.feedback["advice_derived_candidate_count"] += 1
        else: self.feedback["deterministic_fallback_count"] += 1
        self.cache[key] = pkt; self._persist(pkt); return pkt
    def _context(self, need: Any, signal_batch: Mapping[str, Any], tick_id: str, budget: LocalModelInvocationBudget) -> GenesisModelAdviceRequestContext:
        record = self.invoker.authority_map.eligible_record("genesis_proposal_advice") if self.invoker else None
        cap = str(getattr(need, "capability", "unknown")); source = str(getattr(need, "source", "unknown")); desc = str(getattr(need, "description", ""))[:MAX_TEXT]
        need_id = "need-" + digest_payload({"capability": cap, "source": source, "description": desc})[:24]
        sigs = tuple(dict(id=str(x.get("id", x.get("signal_id", ""))), digest=str(x.get("digest", x.get("signal_digest", "")))) for x in signal_batch.get("signals", []) if isinstance(x, Mapping))
        return GenesisModelAdviceRequestContext(need_identity=need_id, capability=cap, source_kind=source, need_description=desc, signal_batch_id=str(signal_batch.get("batch_id", "batch:none")), signal_batch_digest=str(signal_batch.get("batch_digest", digest_payload(signal_batch))), signal_identities=sigs, authority_map_id=self.invoker.authority_map.map_id if self.invoker else "", authority_map_digest=self.invoker.authority_map.map_digest if self.invoker else "", model_id=record.model_id if record else "", model_artifact_digest=record.model_content_sha256 if record else None, correlation_id=f"genesis-advice:{tick_id}:{need_id}", generation_budget=budget.to_dict(), review_evidence=self.review_evidence, tick_id=tick_id)
    def _persist(self, packet: GenesisModelAdvicePacket) -> None:
        atomic_write_json(self.runtime_root / "packets" / f"{packet.packet_id}.json", packet.to_dict())
        atomic_write_json(self.runtime_root / "summaries" / "latest.json", {"schema_version": SCHEMA_VERSION, "packet_id": packet.packet_id, "packet_digest": packet.packet_digest, "feedback": dict(self.feedback), "effects": dict(_EFFECTS_FALSE)})
