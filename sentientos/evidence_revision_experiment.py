"""Pure, bounded composition of supplied evidence interventions and responses.

Digests establish input integrity, never owner provenance or execution. This
module neither invokes a model nor changes the longitudinal self-model owner.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Mapping, cast

from .local_model_authority import digest_payload
from .longitudinal_self_model import (
    CognitiveSelfModelProjection, FALSE_AUTHORITY, MAX_PROJECTION_CLAIMS,
    PROJECTION_POLICY, PROJECTION_SCHEMA,
)
from .self_model_intervention_experiment import SCORER_V3, build_answer_key, score_assessment

PROTOCOL_SCHEMA = "sentientos.evidence_revision_protocol:v1"
REPORT_SCHEMA = "sentientos.evidence_revision_report:v1"
CONDITIONS = ("evidence_original", "evidence_revised", "evidence_restored")
MAX_BYTES = 1_048_576
MAX_RESPONSES = 128


def _copy(value: Any) -> Any:
    """Detach inputs and reject non-JSON/nonfinite or oversized payloads."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("experiment_payload_limit_exceeded")
    return json.loads(raw)


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256 and value not in {
        "latest", "current", "default", "*"}


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _projection_key(projection: CognitiveSelfModelProjection) -> dict[str, Any]:
    raw = _copy(asdict(projection))
    semantic = dict(raw)
    semantic.pop("projection_id")
    semantic.pop("projection_digest")
    digest = _digest(semantic)
    if (raw["schema"] != PROJECTION_SCHEMA or raw["projection_policy"] != PROJECTION_POLICY
            or raw["projection_digest"] != digest
            or raw["projection_id"] != "cognitive-self-model-" + digest[7:31]
            or raw["authority"] != FALSE_AUTHORITY or raw["read_only"] is not True
            or raw["derived_evidence"] is not True or raw["current_truth"] is not False):
        raise ValueError("invalid_evidence_projection")
    claims = raw["selected_claims"]
    ids = [claim.get("claim_id") for claim in claims]
    if (not 1 <= len(claims) <= MAX_PROJECTION_CLAIMS
            or any(not _identity(item) for item in ids) or len(set(ids)) != len(ids)
            or ids != raw["selected_claim_ids"]
            or [claim.get("semantic_digest") for claim in claims] != raw["selected_claim_digests"]):
        raise ValueError("invalid_evidence_claim_inventory")
    for claim in claims:
        sources = claim.get("source_evidence_ids")
        digests = claim.get("source_evidence_digests")
        if (claim.get("authority") != FALSE_AUTHORITY or not _sha(claim.get("semantic_digest"))
                or not isinstance(sources, list) or not sources or len(sources) > 256
                or any(not _identity(item) for item in sources) or len(set(sources)) != len(sources)
                or not isinstance(digests, list) or len(digests) != len(sources)
                or any(not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{64}", item) is None
                       for item in digests)):
            raise ValueError("invalid_evidence_claim_provenance")
    return {"projection": raw, "answer_key": _copy(build_answer_key(projection, scorer_version=SCORER_V3))}


def make_protocol(*, projections: Mapping[str, CognitiveSelfModelProjection],
                  model_id: str, model_artifact_digest: str, prompt_digest: str,
                  developmental_history_digest: str, generation_parameters: Mapping[str, Any],
                  inference_budget: Mapping[str, Any]) -> dict[str, Any]:
    """Bind a supplied three-condition intervention before collecting responses.

    Exact restoration reuses the original evidence projection, including its
    source boundary. Revised evidence must address the same bounded claim set.
    Callers retain responsibility for verifying the actual source owners.
    """
    if set(projections) != set(CONDITIONS):
        raise ValueError("condition_set_mismatch")
    if not _identity(model_id) or not all(_sha(item) for item in (
            model_artifact_digest, prompt_digest, developmental_history_digest)):
        raise ValueError("invalid_fixed_context")
    if not generation_parameters or not inference_budget:
        raise ValueError("missing_fixed_context")
    evidence = {condition: _projection_key(projections[condition]) for condition in CONDITIONS}
    original, revised, restored = (evidence[condition] for condition in CONDITIONS)
    if original != restored:
        raise ValueError("evidence_restoration_mismatch")
    if set(original["answer_key"]) != set(revised["answer_key"]):
        raise ValueError("evidence_claim_set_mismatch")
    if original == revised:
        raise ValueError("evidence_revision_missing")
    for field in ("software_generations", "cognitive_model_identities", "developmental_history_boundaries"):
        if original["projection"][field] != revised["projection"][field]:
            raise ValueError("evidence_fixed_lineage_mismatch")
    fixed_context = _copy({"model_id": model_id, "model_artifact_digest": model_artifact_digest,
        "prompt_digest": prompt_digest, "developmental_history_digest": developmental_history_digest,
        "generation_parameters": generation_parameters, "inference_budget": inference_budget})
    body = _copy({"schema_version": PROTOCOL_SCHEMA, "condition_order": list(CONDITIONS),
        "fixed_context": fixed_context, "fixed_context_digest": _digest(fixed_context),
        "evidence": evidence, "scorer": SCORER_V3, "retries": 0,
        "retain_negative_null_incomplete_unstable": True, "authority": dict(FALSE_AUTHORITY)})
    body["protocol_digest"] = _digest(body)
    return cast(dict[str, Any], body)


def assess_responses(*, protocol: Mapping[str, Any],
                     condition_responses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Externally score supplied structured responses without inference or I/O.

    Each response envelope must bind the preregistered protocol, fixed context
    and exact condition projection. Bindings are caller assertions of integrity,
    not proof that an inference ran under those conditions.
    """
    bound = _copy(protocol)
    claimed_digest = bound.pop("protocol_digest", None)
    if claimed_digest != _digest(bound) or bound.get("schema_version") != PROTOCOL_SCHEMA:
        raise ValueError("protocol_digest_mismatch")
    try:
        projections = {condition: CognitiveSelfModelProjection(**bound["evidence"][condition]["projection"])
                       for condition in CONDITIONS}
        canonical = make_protocol(projections=projections, **bound["fixed_context"])
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid_protocol") from exc
    if canonical != _copy(protocol):
        raise ValueError("noncanonical_protocol")
    if set(condition_responses) != set(CONDITIONS):
        raise ValueError("condition_set_mismatch")
    responses = _copy(condition_responses)
    scores: dict[str, Any] = {}
    answers: dict[str, list[Mapping[str, Any]]] = {}
    for condition in CONDITIONS:
        envelope = responses[condition]
        if (not isinstance(envelope, dict) or envelope.get("protocol_digest") != claimed_digest
                or envelope.get("fixed_context_digest") != bound["fixed_context_digest"]
                or envelope.get("projection_digest") != bound["evidence"][condition]["projection"]["projection_digest"]):
            raise ValueError("response_binding_mismatch")
        rows = envelope.get("answers")
        if not isinstance(rows, list) or len(rows) > MAX_RESPONSES:
            raise ValueError("response_limit_exceeded")
        for row in rows:
            if (not isinstance(row, dict) or not _identity(row.get("question_id"))
                    or row.get("answer") not in ("current", "historical", "contradicted", "unknown", "abstain", None)):
                raise ValueError("invalid_structured_response")
            for field in ("claim_ids", "source_evidence_ids"):
                citations = row.get(field, [])
                if (not isinstance(citations, list) or len(citations) > 256
                        or any(not _identity(item) for item in citations)):
                    raise ValueError("invalid_response_citations")
        answers[condition] = rows
        scores[condition] = score_assessment(answer_key=bound["evidence"][condition]["answer_key"],
            answers=rows, scorer_version=SCORER_V3)
    original_key = bound["evidence"][CONDITIONS[0]]["answer_key"]
    revised_key = bound["evidence"][CONDITIONS[1]]["answer_key"]
    rows_by_question = {condition: {question: [row for row in answers[condition]
        if row["question_id"] == question] for question in original_key} for condition in CONDITIONS}
    comparisons = []
    for question in original_key:
        rows = [rows_by_question[condition][question] for condition in CONDITIONS]
        changed_key = original_key[question]["answer"] != revised_key[question]["answer"]
        outcome = "incomplete"
        if all(len(items) == 1 for items in rows):
            values = [items[0].get("answer") for items in rows]
            values = ["unknown" if item in (None, "abstain") else item for item in values]
            expected = [bound["evidence"][condition]["answer_key"][question]["answer"] for condition in CONDITIONS]
            if values[0] != values[2]:
                outcome = "unstable_restoration"
            elif not changed_key:
                outcome = "null_classification_intervention"
            elif values == expected:
                outcome = "classification_followed_evidence_revision"
            else:
                outcome = "classification_did_not_follow_evidence_revision"
        comparisons.append({"question_id": question, "expected_classification_changed": changed_key,
                            "outcome": outcome})
    report = _copy({"schema_version": REPORT_SCHEMA, "protocol_digest": claimed_digest,
        "condition_order": list(CONDITIONS), "condition_responses": responses,
        "condition_scores": scores, "comparisons": comparisons, "descriptive_only": True,
        "execution_proven": False, "source_owner_provenance_verified": False,
        "causal_claim_made": False, "improvement_claim_made": False,
        "authority": dict(FALSE_AUTHORITY)})
    report["report_digest"] = _digest(report)
    return cast(dict[str, Any], report)


__all__ = ["CONDITIONS", "PROTOCOL_SCHEMA", "REPORT_SCHEMA", "make_protocol", "assess_responses"]
