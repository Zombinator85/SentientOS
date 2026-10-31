"""Read-only paired qualification of persistent positions and delivered answers.

Existing owners supply state and cognition custody. This evaluator does not run
inference, admit updates, rewrite an answer, or declare a model qualified.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol, Sequence

from .governed_local_model_invocation import LocalModelInvocationReceipt, validate_receipt
from .local_model_authority import digest_payload
from .epistemic_qualification_execution_binding import build_execution_binding
from .persistent_epistemic_state import (
    EpistemicCognitiveProjection, PersistentEpistemicStateOwner,
    semantic_packets_for_projection,
)

SCHEMA = "sentientos.epistemic_revision_case_result:v1"
KINDS = frozenset({"contrary_evidence", "unsupported_pressure", "inference_correction",
                   "retained_correction", "outdated_evidence", "model_replacement"})
STANCES = frozenset({"unknown", "suspended", "provisionally_supported", "supported",
                     "contested", "provisionally_contradicted", "contradicted", "superseded"})
MAX_BYTES = 1_048_576


class ObservationReader(Protocol):
    def verified_cognition_observation(self, observation_id: str,
            observation_digest: str | None = None) -> Mapping[str, Any]: ...


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def _canonical(value: Any) -> str:
    result = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(result.encode("utf-8")) > MAX_BYTES:
        raise ValueError("qualification_input_limit_exceeded")
    return result


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("qualification_duplicate_json_key")
        result[key] = value
    return result


def _object(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("qualification_input_limit_exceeded")
    value = json.loads(text, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("qualification_json_object_required")
    _canonical(value)
    return value


def _prompt_context_mismatch(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """Return whether paired prompts differ outside the intended treatment fields."""
    ignored = {"prior_epistemic_state", "current_evidence"}
    before_fixed = {key: value for key, value in before.items() if key not in ignored}
    after_fixed = {key: value for key, value in after.items() if key not in ignored}
    return _canonical(before_fixed) != _canonical(after_fixed)


@dataclass(frozen=True)
class IndependentAnswerKey:
    """Private stipulated task oracle, never derived from the candidate answer.

    A structured reason code evaluates a bounded task rubric, not unrestricted
    natural-language reasoning. Evidence IDs name exact delivered bindings.
    """
    stance: str
    conclusion: str
    reason_code: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class RevisionCase:
    case_id: str
    kind: str
    proposition_id: str
    evaluator_version: str
    before_prompt_digest: str
    after_prompt_digest: str
    before_key: IndependentAnswerKey
    after_key: IndependentAnswerKey
    commitment_nonce: str

    def commitment(self) -> str:
        if (self.kind not in KINDS or not self.case_id or len(self.case_id) > 128
                or not self.evaluator_version or len(self.evaluator_version) > 128
                or len(self.commitment_nonce) != 64
                or any(c not in "0123456789abcdef" for c in self.commitment_nonce)):
            raise ValueError("qualification_case_invalid")
        for key in (self.before_key, self.after_key):
            if (key.stance not in STANCES or not key.conclusion or len(key.conclusion) > 4096
                    or not key.reason_code or len(key.reason_code) > 128
                    or any(not isinstance(item, str) or not item for item in key.evidence_ids)
                    or len(key.evidence_ids) > 256 or len(set(key.evidence_ids)) != len(key.evidence_ids)):
                raise ValueError("qualification_answer_key_invalid")
        for value in (self.before_prompt_digest, self.after_prompt_digest):
            if (not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:")
                    or any(char not in "0123456789abcdef" for char in value[7:])):
                raise ValueError("qualification_prompt_digest_invalid")
        if not isinstance(self.proposition_id, str) or not self.proposition_id or len(self.proposition_id) > 256:
            raise ValueError("qualification_proposition_id_invalid")
        semantic_case = asdict(self)
        _canonical(semantic_case)
        return _digest(semantic_case)


def capture_position(owner: PersistentEpistemicStateOwner, *, proposition_id: str,
                     current_tick: int) -> EpistemicCognitiveProjection:
    """Capture one meaning-bearing, prior-only position using the existing owner."""
    projection = owner.cognitive_projection(max_states=1, current_tick=current_tick,
        prioritized_proposition_ids=(proposition_id,))
    if projection is None or projection.proposition_ids != (proposition_id,):
        raise ValueError("qualification_position_unavailable")
    semantic_packets_for_projection(projection)
    return projection


def _sample(*, reader: ObservationReader, observation_id: str,
            projection: EpistemicCognitiveProjection, proposition_id: str,
            prompt: str, expected_prompt_digest: str, receipt: LocalModelInvocationReceipt,
            key: IndependentAnswerKey, case_id: str, evaluator_version: str,
            condition: str) -> tuple[dict[str, Any], Mapping[str, Any], dict[str, Any]]:
    observation = reader.verified_cognition_observation(observation_id)
    if (not isinstance(observation.get("serving_session_id"), str)
            or not observation.get("serving_session_id")
            or not isinstance(observation.get("serving_session_binding"), Mapping)):
        raise ValueError("qualification_session_bound_observation_required")
    if projection.proposition_ids != (proposition_id,):
        raise ValueError("qualification_proposition_scope_mismatch")
    packets = semantic_packets_for_projection(projection)
    [expected_packet] = packets
    payload = receipt.to_dict(include_output=True)
    valid, reasons = validate_receipt(payload)
    if not valid:
        raise ValueError("qualification_receipt_invalid:" + ",".join(reasons))
    request = receipt.request
    bindings = {"request_id": request.get("request_id"), "request_digest": request.get("request_digest"),
        "inference_receipt_id": receipt.receipt_id, "inference_receipt_digest": receipt.receipt_digest,
        "output_digest": receipt.output_digest, "model_id": request.get("model_id"),
        "model_artifact_digest": request.get("model_artifact_digest"),
        "active_model_identity": request.get("active_model_identity"),
        "generation_config": receipt.generation_config}
    if any(_canonical(observation.get(k)) != _canonical(v) for k, v in bindings.items()):
        raise ValueError("qualification_observation_receipt_mismatch")
    if (_digest({"prompt": prompt}) != expected_prompt_digest
            or observation.get("epistemic_prompt_digest") != expected_prompt_digest
            or request.get("prompt_digest") != expected_prompt_digest[7:]):
        raise ValueError("qualification_prompt_binding_mismatch")
    context = _object(prompt)
    prior = context.get("prior_epistemic_state")
    delivered = prior.get("semantic_packets", []) if isinstance(prior, dict) else []
    complete = (isinstance(prior, dict)
        and prior.get("projection_digest") == projection.projection_digest
        and observation.get("epistemic_projection_digest") == projection.projection_digest
        and any(_canonical(packet) == _canonical(expected_packet) for packet in delivered)
        and expected_packet["packet_id"] in observation.get("epistemic_consumed_packet_ids", ())
        and expected_packet["packet_digest"] in observation.get("epistemic_consumed_packet_digests", ()))
    result: dict[str, Any] = {"observation_id": observation_id,
        "observation_digest": observation["observation_digest"],
        "receipt_id": receipt.receipt_id, "receipt_digest": receipt.receipt_digest,
        "output_digest": receipt.output_digest, "projection_digest": projection.projection_digest,
        "state_digest": expected_packet["state"]["state_digest"],
        "state_stance_correct": expected_packet["state"]["stance"] == key.stance,
        "relevant_packet_delivered": complete, "execution_status": receipt.status,
        "answer_correct": None, "reason_code_correct": None, "citations_correct": None,
        "answer_shape_valid": None, "measurement_status": "insufficient"}
    result["execution_binding"] = build_execution_binding(
        case_id=case_id, evaluator_version=evaluator_version, condition=condition,
        model_id=request.get("model_id"),
        model_artifact_digest=request.get("model_artifact_digest"),
        active_model_identity=request.get("active_model_identity"),
        generation_config=receipt.generation_config,
        prompt_digest=expected_prompt_digest,
        projection_digest=projection.projection_digest,
        observation_digest=observation["observation_digest"],
        receipt_digest=receipt.receipt_digest, output_digest=receipt.output_digest)
    if (not complete or receipt.output_truncated or receipt.fallback_occurred
            or receipt.status not in {"admitted_completed", "admitted_simulation"}
            or receipt.output_text is None
            or not result["execution_binding"]["complete"]):
        return result, expected_packet, context
    output = receipt.output_text
    if (digest_payload({"output": output}) != receipt.output_digest
            or len(output.encode("utf-8")) != receipt.output_size_bytes):
        raise ValueError("qualification_output_binding_mismatch")
    try:
        answer = _object(output)
    except (ValueError, TypeError):
        result.update(answer_shape_valid=False, answer_correct=False, reason_code_correct=False,
            citations_correct=False, measurement_status="scored")
        return result, expected_packet, context
    citations = answer.get("evidence_ids")
    shape_valid = (isinstance(answer.get("conclusion"), str)
        and isinstance(answer.get("reason_code"), str) and isinstance(citations, list)
        and len(citations) <= 256 and all(isinstance(item, str) for item in citations))
    available = {row["binding_id"] for row in expected_packet["active_evidence_bindings"]}
    available.update(row["binding_id"] for row in expected_packet["removed_evidence_history"])
    citation_values = citations if isinstance(citations, list) else []
    result.update(answer_shape_valid=shape_valid,
        answer_correct=shape_valid and answer.get("conclusion") == key.conclusion,
        reason_code_correct=shape_valid and answer.get("reason_code") == key.reason_code,
        citations_correct=shape_valid and set(key.evidence_ids) <= set(citation_values)
            and set(citation_values) <= available, measurement_status="scored")
    return result, expected_packet, context


def evaluate_pair(*, case: RevisionCase,
                  before_reader: ObservationReader, after_reader: ObservationReader,
                  before_observation_id: str, after_observation_id: str,
                  before_projection: EpistemicCognitiveProjection, after_projection: EpistemicCognitiveProjection,
                  before_prompt: str, after_prompt: str,
                  before_receipt: LocalModelInvocationReceipt, after_receipt: LocalModelInvocationReceipt
                  ) -> dict[str, Any]:
    """Score both delivered answers and the state transition; never repair either.

    Expected full prompt digests bind the stipulated treatments. The caller must
    preregister the private oracle and independently justify treatment semantics.
    A successful local score does not prove that preregistration happened in time.
    """
    commitment = case.commitment()
    before, old, old_context = _sample(reader=before_reader, observation_id=before_observation_id,
        projection=before_projection, proposition_id=case.proposition_id, prompt=before_prompt,
        expected_prompt_digest=case.before_prompt_digest, receipt=before_receipt, key=case.before_key,
        case_id=case.case_id, evaluator_version=case.evaluator_version, condition="before")
    after, new, new_context = _sample(reader=after_reader, observation_id=after_observation_id,
        projection=after_projection, proposition_id=case.proposition_id, prompt=after_prompt,
        expected_prompt_digest=case.after_prompt_digest, receipt=after_receipt, key=case.after_key,
        case_id=case.case_id, evaluator_version=case.evaluator_version, condition="after")
    controls = []
    for field in ("budget", "authority_map_digest"):
        if _canonical(before_receipt.request.get(field)) != _canonical(after_receipt.request.get(field)):
            controls.append(field)
    if _canonical(before_receipt.generation_config) != _canonical(after_receipt.generation_config):
        controls.append("generation_config")
    # Compare the full shared context so newly added prompt fields cannot
    # become untracked confounds. The epistemic state is the intended state
    # treatment; current evidence may change in evidence-arrival/withdrawal
    # cases and is checked separately for cases that require it to stay fixed.
    if _prompt_context_mismatch(old_context, new_context):
        controls.append("prompt_context")
    old_identity = {k: before_receipt.request.get(k) for k in
        ("model_id", "model_artifact_digest", "active_model_identity")}
    new_identity = {k: after_receipt.request.get(k) for k in old_identity}
    identity_changed = _canonical(old_identity) != _canonical(new_identity)
    if identity_changed != (case.kind == "model_replacement"):
        controls.append("model_identity")
    if _canonical(old["proposition"]) != _canonical(new["proposition"]):
        controls.append("proposition_meaning")
    same_state = old["state"]["state_digest"] == new["state"]["state_digest"]
    preserve = case.kind in {"unsupported_pressure", "retained_correction", "model_replacement"}
    # A matching current-state digest alone does not bind the evidence lineage
    # and update history that justify a retained correction.
    preserved_position = (same_state
        and old["state"]["evidence_set_digest"] == new["state"]["evidence_set_digest"]
        and _canonical(old["state"]) == _canonical(new["state"])
        and _canonical(old["proposition"]) == _canonical(new["proposition"])
        and _canonical(old["active_evidence_bindings"])
            == _canonical(new["active_evidence_bindings"])
        and _canonical(old["removed_evidence_history"])
            == _canonical(new["removed_evidence_history"])
        and _canonical(old["update_event_history"]) == _canonical(new["update_event_history"])
        and _canonical(old["last_update_event"]) == _canonical(new["last_update_event"]))
    if preserve and not preserved_position:
        controls.append("canonical_position_changed")
    event = new["last_update_event"]
    old_history = old["update_event_history"]
    new_history = new["update_event_history"]
    delta_valid = (len(new_history) == len(old_history) + 1
        and _canonical(new_history[:-1]) == _canonical(old_history)
        and event["prior_state_digest"] == old["state"]["state_digest"])
    allowed = {"contrary_evidence": {"contradiction_arrival", "new_evidence"},
        "inference_correction": {"update_rule_correction", "dependency_correction", "operator_error_correction"},
        "outdated_evidence": {"source_reliability_revision", "evidence_withdrawal", "new_evidence"}}
    transition = preserved_position if preserve else (not same_state and delta_valid
        and event["reason"] in allowed[case.kind])
    if not delta_valid and not preserve:
        transition = False
    if case.kind == "inference_correction":
        transition = transition and old["state"]["evidence_set_digest"] == new["state"]["evidence_set_digest"]
    if case.kind in {"contrary_evidence", "outdated_evidence"}:
        transition = transition and old["state"]["evidence_set_digest"] != new["state"]["evidence_set_digest"]
    if case.kind in {"unsupported_pressure", "retained_correction", "inference_correction", "model_replacement"}:
        if _canonical(old_context.get("current_evidence")) != _canonical(new_context.get("current_evidence")):
            controls.append("current_evidence")
    if case.kind == "model_replacement":
        # Display names and declared artifact labels alone do not establish a
        # worker change. Require a changed content identity recorded by the
        # existing serving owner.
        old_content = (old_identity["active_model_identity"] or {}).get("model_content_sha256")
        new_content = (new_identity["active_model_identity"] or {}).get("model_content_sha256")
        if (not isinstance(old_content, str) or len(old_content) != 64
                or not isinstance(new_content, str) or len(new_content) != 64
                or old_content == new_content):
            controls.append("model_content_identity")
    insufficient = bool(controls) or any(row["measurement_status"] != "scored" for row in (before, after))
    passed = transition and all(row[field] is True for row in (before, after)
        for field in ("state_stance_correct", "answer_correct", "reason_code_correct", "citations_correct"))
    report = {"schema_version": SCHEMA, "case_id": case.case_id, "kind": case.kind,
        "case_commitment": commitment, "evaluator_version": case.evaluator_version,
        "status": "insufficient" if insufficient else "case_passed" if passed else "case_failed",
        "before": before, "after": after, "state_transition_appropriate": transition,
        "control_mismatches": controls, "model_identity_changed": identity_changed,
        "real_model_qualification_established": False, "causal_claim_made": False,
        "oracle_independence_verified": False, "preregistration_timing_verified": False,
        "authority": False, "source_mutation_performed": False}
    return {**report, "report_digest": _digest(report)}


__all__ = ["IndependentAnswerKey", "RevisionCase", "capture_position", "evaluate_pair"]
