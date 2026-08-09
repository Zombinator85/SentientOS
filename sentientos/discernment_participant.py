from __future__ import annotations

"""Process-real, non-authoritative SentientOS blind-trial participant."""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from .delegated_judgment_fabric import collect_delegated_judgment_evidence, synthesize_delegated_judgment
from .discernment_synthesis import (
    SurfaceContribution, context_from_inner_world, contribution_from_delegated_judgment,
    contribution_from_epistemic_entry, synthesize_packet,
)
from .governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget
from .innerworld.orchestrator import InnerWorldOrchestrator
from .local_model_authority import digest_payload
from .truth.epistemic_orientation import EpistemicOrientation

JUDGMENT_SCHEMA = "sentientos.discernment_judgment.v1"
STANCES = {"support", "oppose", "suspend"}
LIST_FIELDS = (
    "alternate_interpretations", "missing_evidence", "what_would_change_judgment",
    "expected_observation_keys", "disconfirming_observation_keys", "predicted_consequences",
    "rejected_next_moves", "unresolved_contradictions",
)
TEXT_FIELDS = ("proposition", "interpretation", "strongest_objection", "preferred_next_move")
FORBIDDEN_CONTENT = (
    "```", "<script", "subprocess", "shell command", "tool_call", "write_file", "git commit",
    "git push", "http://", "https://", "provider api", "memory write", "modify memory",
    "grant authority", "authority grant", "approve adoption", "execute this", "run command",
)
MAX_JUDGMENT_BYTES = 32_768
MAX_TEXT_CHARS = 4_000
MAX_LIST_ITEMS = 64


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def validate_judgment_output(value: Any, *, allowed_observation_namespace: str,
                             expected_proposition: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("discernment judgment must be an object")
    data = dict(value)
    required = {"schema_version", "stance", "confidence", *TEXT_FIELDS, *LIST_FIELDS}
    if set(data) != required or data.get("schema_version") != JUDGMENT_SCHEMA:
        raise ValueError("discernment judgment has an invalid exact schema")
    if data.get("proposition") != expected_proposition or not expected_proposition:
        raise ValueError("discernment proposition does not bind the exact question")
    if data.get("stance") not in STANCES:
        raise ValueError("invalid discernment stance")
    confidence = data.get("confidence")
    if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1):
        raise ValueError("invalid discernment confidence")
    if data["stance"] != "suspend" and confidence is None:
        raise ValueError("non-suspended judgment requires confidence")
    if data["stance"] == "suspend" and confidence is not None:
        raise ValueError("suspended judgment confidence must be null")
    for key in TEXT_FIELDS:
        if not isinstance(data[key], str) or len(data[key]) > MAX_TEXT_CHARS:
            raise ValueError(f"invalid text field: {key}")
    for key in LIST_FIELDS:
        rows = data[key]
        if not isinstance(rows, list) or len(rows) > MAX_LIST_ITEMS or any(not isinstance(row, str) or len(row) > MAX_TEXT_CHARS for row in rows):
            raise ValueError(f"invalid list field: {key}")
    for key in ("expected_observation_keys", "disconfirming_observation_keys"):
        if not allowed_observation_namespace or any(not row.startswith(allowed_observation_namespace + ".") for row in data[key]):
            raise ValueError("observation key is outside the allowed namespace")
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_JUDGMENT_BYTES:
        raise ValueError("discernment judgment is oversized")
    lowered = encoded.lower()
    if any(token in lowered for token in FORBIDDEN_CONTENT):
        raise ValueError("discernment judgment contains executable or authority-seeking content")
    return cast(dict[str, Any], _plain(data))


@dataclass(frozen=True)
class DiscernmentParticipantRequest:
    repo_root: Path
    subject_id: str
    question: str
    initial_evidence_snapshot: Mapping[str, Any]
    evaluation_context: Mapping[str, Any]
    allowed_observation_namespace: str
    observed_at: str
    question_digest: str | None = None
    evidence_snapshot_digest: str | None = None
    epistemic_observations: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    epistemic_suspensions: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    inner_world_cycle_input: Mapping[str, Any] | None = None


def _repository_identity(root: Path) -> dict[str, Any]:
    head = root / ".git" / "HEAD"
    if not head.is_file():
        return {"status": "unavailable"}
    head_value = head.read_text(encoding="utf-8").strip()
    revision = head_value
    if head_value.startswith("ref: "):
        ref = root / ".git" / head_value[5:]
        revision = ref.read_text(encoding="utf-8").strip() if ref.is_file() else "unresolved"
    return {"status": "observed_local_git_metadata", "head": head_value, "revision": revision}


def _suspension(reason: str, proposition: str) -> dict[str, Any]:
    return {
        "schema_version": JUDGMENT_SCHEMA, "proposition": proposition, "interpretation": "",
        "stance": "suspend", "confidence": None, "strongest_objection": reason,
        "alternate_interpretations": [], "missing_evidence": [reason],
        "what_would_change_judgment": ["a valid governed local-model discernment judgment"],
        "expected_observation_keys": [], "disconfirming_observation_keys": [],
        "predicted_consequences": [], "preferred_next_move": "",
        "rejected_next_moves": [], "unresolved_contradictions": [reason],
    }


def generate_participant_judgment(request: DiscernmentParticipantRequest, *,
                                  invoker: GovernedLocalModelInvoker,
                                  epistemic_orientation: EpistemicOrientation | None = None,
                                  inner_world: InnerWorldOrchestrator | None = None) -> dict[str, Any]:
    question_digest = digest_payload(request.question)
    evidence_digest = digest_payload(_plain(request.initial_evidence_snapshot))
    if request.question_digest is not None and request.question_digest != question_digest:
        raise ValueError("question digest mismatch")
    if request.evidence_snapshot_digest is not None and request.evidence_snapshot_digest != evidence_digest:
        raise ValueError("initial evidence snapshot digest mismatch")
    if not request.allowed_observation_namespace:
        raise ValueError("allowed observation namespace is required")

    orientation = epistemic_orientation or EpistemicOrientation()
    contributions: list[SurfaceContribution] = []
    for row in request.epistemic_observations:
        entry = orientation.log_observation(
            str(row["entry_id"]), str(row["claim"]), source_class=cast(Any, str(row["source_class"])),
            confidence=float(row["confidence"]), volatility=float(row.get("volatility", 0.0)), fragment=bool(row.get("fragment", True)),
        )
        contributions.append(contribution_from_epistemic_entry(entry))
    suspensions = []
    for row in request.epistemic_suspensions:
        suspensions.append(_plain(orientation.suspend_judgment(
            str(row["claim_id"]), reason=cast(Any, str(row["reason"])), note=str(row["note"]) if row.get("note") else None,
        ).__dict__))

    inner_context = None
    if request.inner_world_cycle_input is not None:
        report = (inner_world or InnerWorldOrchestrator()).run_cycle(request.inner_world_cycle_input)
        inner_context = context_from_inner_world(report)

    delegated_evidence = collect_delegated_judgment_evidence(request.repo_root)
    delegated = synthesize_delegated_judgment(delegated_evidence)
    contributions.append(contribution_from_delegated_judgment(delegated))
    deterministic = {
        "epistemic_orientation": orientation.introspect(), "inner_world": inner_context,
        "delegated_judgment": delegated,
    }
    deterministic_digests = {key: digest_payload(value) for key, value in deterministic.items() if value is not None}
    semantic_request = {
        "schema_version": "sentientos.discernment_participant_model_request.v1",
        "proposition": request.question, "question_digest": question_digest,
        "initial_evidence_snapshot": _plain(request.initial_evidence_snapshot),
        "initial_evidence_snapshot_digest": evidence_digest,
        "evaluation_context": _plain(request.evaluation_context),
        "allowed_observation_namespace": request.allowed_observation_namespace,
        "deterministic_context": deterministic,
        "instruction": "Return only the exact sentientos.discernment_judgment.v1 JSON object. Judgment is non-authoritative and must not request actions or tools.",
    }
    prompt = json.dumps(semantic_request, sort_keys=True, ensure_ascii=False)
    lm_request = invoker.build_request(
        purpose="discernment_judgment", prompt=prompt, caller="sentientos.discernment_participant",
        correlation_id=f"discernment:{question_digest}:{evidence_digest}", expected_output_format="json",
        budget=LocalModelInvocationBudget(max_input_chars=max(8000, len(prompt) + 1), max_output_chars=MAX_JUDGMENT_BYTES),
        upstream_evidence={"question_digest": question_digest, "evidence_snapshot_digest": evidence_digest,
                           "deterministic_component_digests": deterministic_digests},
        linkage={"proposition": request.question, "allowed_observation_namespace": request.allowed_observation_namespace},
    )
    receipt = invoker.invoke(lm_request, include_output_in_receipt=False)
    model_status: dict[str, Any] = {
        "status": receipt.status, "reason_codes": list(receipt.reason_codes), "fabricated": False,
        "model_id": lm_request.model_id, "model_artifact_digest": lm_request.model_artifact_digest,
        "authority_map_digest": lm_request.authority_map_digest, "invocation_request_digest": lm_request.request_digest,
        "invocation_receipt_digest": receipt.receipt_digest, "admission_decision_ref": receipt.admission_decision_ref,
    }
    try:
        if receipt.status != "admitted_completed" or receipt.output_text is None:
            raise ValueError("governed model unavailable: " + receipt.status)
        judgment = validate_judgment_output(json.loads(receipt.output_text),
            allowed_observation_namespace=request.allowed_observation_namespace, expected_proposition=request.question)
        model_status["validated_semantic_output_digest"] = digest_payload(judgment)
        contributions.append(SurfaceContribution(
            surface_id="governed-discernment-model", source_kind="local_model_interpretation",
            component="sentientos.governed_local_model_invocation.GovernedLocalModelInvoker",
            component_version=JUDGMENT_SCHEMA, position=judgment["interpretation"],
            interpretation=judgment["interpretation"], confidence=float(judgment["confidence"] or 0.0),
            alternate_interpretations=tuple(judgment["alternate_interpretations"]),
            strongest_objection=judgment["strongest_objection"], missing_evidence=tuple(judgment["missing_evidence"]),
            would_change_position=tuple(judgment["what_would_change_judgment"]),
            proposed_next_move=judgment["preferred_next_move"], proposed_non_moves=tuple(judgment["rejected_next_moves"]),
            provenance={**model_status, "decision_class": "trial_proposition"},
        ))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        reason = f"governed_model_judgment_unavailable:{receipt.status}"
        judgment = _suspension(reason, request.question)
        model_status.update({"status": "suspended", "invocation_status": receipt.status, "suspension_reason": reason})

    packet = synthesize_packet(
        subject_id=request.subject_id, question=request.question, contributions=contributions,
        evaluation_context={**_plain(request.evaluation_context), "question_digest": question_digest,
                            "initial_evidence_snapshot_digest": evidence_digest,
                            "repository_identity": _repository_identity(request.repo_root),
                            "deterministic_component_digests": deterministic_digests, "inner_world_context": inner_context},
        observed_at=request.observed_at, current_interpretation=judgment["interpretation"] or None,
        epistemic_status=judgment["stance"], confidence=judgment["confidence"], suspended_conclusions=suspensions,
        strategic_consequences=judgment["predicted_consequences"], preferred_next_move=judgment["preferred_next_move"] or None,
        rejected_next_moves=judgment["rejected_next_moves"], unresolved_decision_classes=judgment["unresolved_contradictions"],
        local_model_status=model_status,
    )
    submission = {key: judgment[key] for key in (
        "proposition", "interpretation", "stance", "confidence", "strongest_objection",
        "alternate_interpretations", "missing_evidence", "what_would_change_judgment",
        "expected_observation_keys", "disconfirming_observation_keys", "predicted_consequences",
        "preferred_next_move", "rejected_next_moves", "unresolved_contradictions",
    )}
    submission.update({"sealed_at": request.observed_at, "source_discernment_packet_digest": packet["packet_digest"]})
    return {
        "schema_version": "sentientos.discernment_participant_result.v1", "question_digest": question_digest,
        "initial_evidence_snapshot_digest": evidence_digest, "judgment": judgment,
        "discernment_packet": packet, "trial_submission": submission, "model_invocation": model_status,
        "deterministic_component_digests": deterministic_digests,
        "authority_posture": packet["authority_posture"],
    }
