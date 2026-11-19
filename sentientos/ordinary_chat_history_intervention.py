"""Pre-registration and immutable result artifacts for ordinary-chat interventions.

The runner is capability-injected and has no model access of its own. This
module makes no effect or learning claim. Result packets bind external receipt
and scoring references; only the runner checks them at execution time, while
artifact reload checks internal bindings.
"""
from __future__ import annotations

import json
import hashlib
import re
import secrets
from pathlib import Path
from typing import Any, Callable, Mapping

from .conversation_session import (
    verify_ordinary_chat_history_intervention_prompt_bundle,
)
from .local_model_authority import digest_payload
from .governed_local_model_invocation import LocalModelInvocationBudget
from .developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore,
)

LEGACY_PROTOCOL_SCHEMA = "sentientos.ordinary_chat_history_intervention_protocol:v1"
PROTOCOL_SCHEMA = "sentientos.ordinary_chat_history_intervention_protocol:v2"
PROTOCOL_ID_PREFIX = "ordinary-history-protocol-"
RESULT_SCHEMA = "sentientos.ordinary_chat_history_intervention_result:v2"
RESULT_ID_PREFIX = "ordinary-history-result-"
SCORE_SCHEMA = "sentientos.ordinary_chat_history_score_artifact:v1"
SCORE_ID_PREFIX = "ordinary-history-score-"
SCORE_PLAN_SCHEMA = "sentientos.ordinary_chat_history_objective_scoring_plan:v1"
SCORE_PLAN_ID_PREFIX = "ordinary-history-score-plan-"
INTERVENTION_LINKAGE_KEY = "ordinary_chat_history_intervention"
CONDITIONS = ("history_present", "history_withheld", "history_restored")
PLANNED_COMPARISONS = (
    "history_present_vs_history_withheld",
    "history_restored_vs_history_withheld",
)
NON_CLAIMS = ("effect", "improvement", "learning", "model_independent_continuity")
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
_SESSION_ID = re.compile(r"[a-z0-9][a-z0-9-]{7,63}")
_TURN_ID = re.compile(r"turn-[0-9a-f]{24}")
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_BLIND_SAMPLE_ID = re.compile(r"blind-sample-[0-9a-f]{32}")


def _validate_json_bound(value: Any, *, maximum_bytes: int, error_code: str) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError(error_code) from exc
    if len(encoded) > maximum_bytes:
        raise ValueError(error_code)


def _semantic(protocol: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in protocol.items()
        if key not in {"protocol_id", "protocol_digest"}}


def _validate_blind_score_payload(payload: Any, *, depth: int = 0) -> None:
    if (not isinstance(payload, Mapping) or not payload or len(payload) > 64
            or depth > 8):
        raise ValueError("ordinary_chat_history_score_payload_invalid")
    forbidden_keys = {"condition", "history_present", "history_withheld",
        "history_restored", "output_text", "prompt", "sample_id"}
    for key, value in payload.items():
        if (not isinstance(key, str) or not key or len(key) > 128
                or key.casefold() in forbidden_keys):
            raise ValueError("ordinary_chat_history_score_payload_not_blind")
        if isinstance(value, Mapping):
            _validate_blind_score_payload(value, depth=depth + 1)
        elif isinstance(value, list):
            if len(value) > 64 or any(isinstance(item, list)
                    or (not isinstance(item, Mapping)
                        and not isinstance(item, (str, int, float, bool, type(None))))
                    for item in value):
                raise ValueError("ordinary_chat_history_score_payload_invalid")
            for item in value:
                if isinstance(item, Mapping):
                    _validate_blind_score_payload(item, depth=depth + 1)
            if any(isinstance(item, str) and item.casefold() in forbidden_keys
                    for item in value):
                raise ValueError("ordinary_chat_history_score_payload_not_blind")
        elif isinstance(value, str) and value.casefold() in forbidden_keys:
            raise ValueError("ordinary_chat_history_score_payload_not_blind")
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("ordinary_chat_history_score_payload_invalid")
    _validate_json_bound(dict(payload), maximum_bytes=16_384,
        error_code="ordinary_chat_history_score_payload_over_bound")


def build_ordinary_chat_history_score_artifact(*, protocol: Mapping[str, Any],
        sample_id: str, output_digest: str, scorer_identity_digest: str,
        score_payload: Mapping[str, Any]) -> dict[str, Any]:
    if (not isinstance(protocol, Mapping)
            or protocol.get("schema_version") != PROTOCOL_SCHEMA
            or not isinstance(protocol.get("protocol_id"), str)
            or not isinstance(protocol.get("protocol_digest"), str)
            or not isinstance(protocol.get("scoring_plan_digest"), str)
            or protocol.get("scorer_identity_digest") != scorer_identity_digest
            or not isinstance(sample_id, str) or _BLIND_SAMPLE_ID.fullmatch(sample_id) is None
            or not isinstance(output_digest, str) or _HEX_DIGEST.fullmatch(output_digest) is None
            or not isinstance(scorer_identity_digest, str)
            or _HEX_DIGEST.fullmatch(scorer_identity_digest) is None):
        raise ValueError("ordinary_chat_history_score_artifact_binding_invalid")
    protocol_digest = digest_payload(_semantic(protocol))
    if (protocol.get("protocol_digest") != protocol_digest
            or protocol.get("protocol_id") != PROTOCOL_ID_PREFIX + protocol_digest[:24]):
        raise ValueError("ordinary_chat_history_score_artifact_protocol_invalid")
    _validate_blind_score_payload(score_payload)
    semantic = {"schema_version": SCORE_SCHEMA,
        "protocol_id": protocol["protocol_id"],
        "protocol_digest": protocol["protocol_digest"],
        "scoring_plan_digest": protocol["scoring_plan_digest"],
        "sample_id": sample_id, "output_digest": output_digest,
        "scorer_identity_digest": scorer_identity_digest,
        "blinding_posture": "condition_blinded_independent_score:v1",
        "score_payload": dict(score_payload), "authority": False}
    _validate_json_bound(semantic, maximum_bytes=32_768,
        error_code="ordinary_chat_history_score_artifact_over_bound")
    digest = digest_payload(semantic)
    return {**semantic, "score_artifact_id": SCORE_ID_PREFIX + digest[:24],
        "score_artifact_digest": digest}


def verify_ordinary_chat_history_score_artifact(artifact: Mapping[str, Any], *,
        protocol: Mapping[str, Any],
        scoring_plan: Mapping[str, Any] | None = None,
        prompt_bundle: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(artifact, Mapping) or set(artifact) != {
            "schema_version", "protocol_id", "protocol_digest", "scoring_plan_digest",
            "sample_id", "output_digest", "scorer_identity_digest", "blinding_posture",
            "score_payload", "authority", "score_artifact_id", "score_artifact_digest"}:
        raise ValueError("ordinary_chat_history_score_artifact_invalid")
    rebuilt = build_ordinary_chat_history_score_artifact(protocol=protocol,
        sample_id=artifact.get("sample_id"), output_digest=artifact.get("output_digest"),
        scorer_identity_digest=artifact.get("scorer_identity_digest"),
        score_payload=artifact.get("score_payload"))
    if dict(artifact) != rebuilt:
        raise ValueError("ordinary_chat_history_score_artifact_digest_mismatch")
    score_semantics_verified = False
    if scoring_plan is not None:
        verify_ordinary_chat_history_objective_scoring_plan(
            scoring_plan, protocol=protocol, prompt_bundle=prompt_bundle)
        from .developmental_model_replacement_experiment import _verify_objective_score
        try:
            _verify_objective_score(scoring_plan, artifact["score_payload"],
                artifact["output_digest"], output_truncated=False)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("ordinary_chat_history_objective_score_invalid") from exc
        score_semantics_verified = True
    return {"schema_version": "sentientos.ordinary_chat_history_score_verification:v1",
        "score_artifact_id": artifact["score_artifact_id"],
        "score_artifact_digest": artifact["score_artifact_digest"],
        "protocol_id": artifact["protocol_id"],
        "output_digest": artifact["output_digest"],
        "scoring_plan_digest": artifact["scoring_plan_digest"],
        "blinding_posture": artifact["blinding_posture"],
        "score_semantics_verified": score_semantics_verified,
        "effect_established": False,
        "learning_established": False}


def _verify_invocation_summary(receipt: Mapping[str, Any], *,
        receipt_id: str, receipt_digest: str,
        protocol: Mapping[str, Any], prompt_digest: str,
        output_digest: str) -> None:
    if (not isinstance(receipt, Mapping)
            or receipt.get("receipt_identity_verified") is not True
            or receipt.get("receipt_id") != receipt_id
            or receipt.get("receipt_digest") != receipt_digest
            or receipt.get("prompt_digest") != prompt_digest
            or receipt.get("output_digest") != output_digest
            or receipt.get("serving_model_identity_digest")
                != protocol["serving_model_identity_digest"]
            or receipt.get("generation_config_digest")
                != protocol["generation_config_digest"]
            or receipt.get("status") != "admitted_completed"
            or receipt.get("output_truncated") is not False
            or receipt.get("fallback_occurred") is not False):
        raise ValueError("ordinary_chat_history_invocation_receipt_binding_invalid")


def _objective_scorer_identity_digest() -> str:
    from . import developmental_model_replacement_experiment as evaluator
    source_path = Path(str(evaluator.__file__))
    try:
        source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError("ordinary_chat_history_scorer_source_unavailable") from exc
    return digest_payload({"module": evaluator.__name__,
        "source_sha256": source_digest,
        "entrypoint": "_objective_score+_verify_objective_score"})


def build_ordinary_chat_history_objective_scoring_plan(task: Any) -> dict[str, Any]:
    """Commit a private deterministic affine-task oracle before inference."""
    from .developmental_model_replacement_experiment import (
        FAMILY_TASK_SCHEMA_V3, FAMILY_TASK_SCHEMA_V4, ObjectivePredictionTask,
    )
    if not isinstance(task, ObjectivePredictionTask):
        raise ValueError("ordinary_chat_history_objective_task_invalid")
    try:
        specification = task.specification()
        descriptor = task.public_descriptor()
    except (TypeError, ValueError) as exc:
        raise ValueError("ordinary_chat_history_objective_task_invalid") from exc
    suite = specification.get("schema_version") in {
        "sentientos.affine_prediction_task_suite:v2",
        FAMILY_TASK_SCHEMA_V3, FAMILY_TASK_SCHEMA_V4}
    selective_family = specification.get("schema_version") == FAMILY_TASK_SCHEMA_V4
    public_semantic = {"schema_version": SCORE_PLAN_SCHEMA,
        "task_descriptor": descriptor,
        "condition_order": list(CONDITIONS),
        "rubric": ("selective_integer_answer_suite_v1" if selective_family else
            "exact_integer_answer_suite_v2" if suite else "exact_integer_answer_v1"),
        "authority": False}
    plan_digest = digest_payload(public_semantic)
    task_commitment_digest = digest_payload({"task_commitment": descriptor})
    scorer_identity_digest = _objective_scorer_identity_digest()
    return {**public_semantic, "task": specification,
        "task_commitment_nonce": task.commitment_nonce,
        "task_commitment_digest": task_commitment_digest,
        "scoring_plan_digest": plan_digest,
        "scorer_identity_digest": scorer_identity_digest}


def verify_ordinary_chat_history_objective_scoring_plan(
        plan: Mapping[str, Any], *,
        protocol: Mapping[str, Any] | None = None,
        prompt_bundle: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from .developmental_model_replacement_experiment import (
        FAMILY_TASK_SCHEMA_V3, FAMILY_TASK_SCHEMA_V4, ObjectivePredictionTask,
    )
    expected_fields = {"schema_version", "task_descriptor", "condition_order",
        "rubric", "authority", "task", "task_commitment_nonce",
        "task_commitment_digest", "scoring_plan_digest", "scorer_identity_digest"}
    if (not isinstance(plan, Mapping) or set(plan) != expected_fields
            or plan.get("schema_version") != SCORE_PLAN_SCHEMA
            or plan.get("condition_order") != list(CONDITIONS)
            or plan.get("authority") is not False
            or not isinstance(plan.get("task"), Mapping)
            or not isinstance(plan.get("task_descriptor"), Mapping)):
        raise ValueError("ordinary_chat_history_objective_scoring_plan_invalid")
    task_raw = dict(plan["task"])
    schema = task_raw.get("schema_version")
    try:
        if schema in {"sentientos.affine_prediction_task_suite:v2",
                FAMILY_TASK_SCHEMA_V3, FAMILY_TASK_SCHEMA_V4}:
            probes = task_raw["probe_inputs"]
            family = schema in {FAMILY_TASK_SCHEMA_V3, FAMILY_TASK_SCHEMA_V4}
            task = ObjectivePredictionTask(task_raw["multiplier"], task_raw["offset"],
                probes[0], tuple(probes[1:]),
                task_raw.get("task_family_id") if family else None,
                task_raw.get("requires_task_family_history", False) if family else False,
                commitment_nonce=plan["task_commitment_nonce"],
                family_contract_version=3 if schema == FAMILY_TASK_SCHEMA_V3 else 4)
        elif schema == "sentientos.affine_prediction_task:v1":
            task = ObjectivePredictionTask(task_raw["multiplier"], task_raw["offset"],
                task_raw["probe_input"],
                commitment_nonce=plan["task_commitment_nonce"])
        else:
            raise ValueError("ordinary_chat_history_objective_task_schema_invalid")
        if (task.specification() != task_raw
                or task.public_descriptor() != dict(plan["task_descriptor"])):
            raise ValueError("ordinary_chat_history_objective_task_binding_invalid")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ordinary_chat_history_objective_task_binding_invalid") from exc
    rebuilt = build_ordinary_chat_history_objective_scoring_plan(task)
    if dict(plan) != rebuilt:
        raise ValueError("ordinary_chat_history_objective_scoring_plan_digest_mismatch")
    if prompt_bundle is not None:
        prompts = prompt_bundle.get("prompts") if isinstance(prompt_bundle, Mapping) else None
        question = plan["task_descriptor"].get("question")
        if (not isinstance(prompts, Mapping) or set(prompts) != set(CONDITIONS)
                or not isinstance(question, str) or not question
                or any(not isinstance(prompts.get(condition), str)
                    or question not in prompts[condition] for condition in CONDITIONS)):
            raise ValueError("ordinary_chat_history_objective_prompt_task_binding_invalid")
    if protocol is not None and (
            protocol.get("task_commitment_digest") != plan["task_commitment_digest"]
            or protocol.get("scoring_plan_digest") != plan["scoring_plan_digest"]
            or protocol.get("scorer_identity_digest") != plan["scorer_identity_digest"]):
        raise ValueError("ordinary_chat_history_objective_plan_protocol_binding_invalid")
    return {"schema_version": "sentientos.ordinary_chat_history_objective_scoring_plan_verification:v1",
        "scoring_plan_digest": plan["scoring_plan_digest"],
        "task_commitment_digest": plan["task_commitment_digest"],
        "scorer_identity_digest": plan["scorer_identity_digest"],
        "authority": False}


def build_ordinary_chat_history_intervention_result(*,
        protocol: Mapping[str, Any], prompt_bundle: Mapping[str, Any],
        conditions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Bind condition outputs and blinded score artifacts to a preregistration.

    Receipt and score digests are provenance references. This packet does not
    authenticate those external artifacts or interpret their contents.
    """
    verified = verify_ordinary_chat_history_intervention_protocol(
        protocol, prompt_bundle=prompt_bundle)
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        raise ValueError("ordinary_chat_history_result_requires_current_protocol")
    if not isinstance(conditions, Mapping) or set(conditions) != set(CONDITIONS):
        raise ValueError("ordinary_chat_history_result_conditions_invalid")
    normalized: dict[str, dict[str, str]] = {}
    for condition in CONDITIONS:
        item = conditions[condition]
        if not isinstance(item, Mapping) or set(item) != {
                "prompt_digest", "output_digest", "invocation_receipt_id",
                "invocation_receipt_digest", "score_artifact_id",
                "score_artifact_digest"}:
            raise ValueError("ordinary_chat_history_result_condition_invalid")
        if item.get("prompt_digest") != protocol["condition_prompt_digests"][condition]:
            raise ValueError("ordinary_chat_history_result_prompt_binding_invalid")
        for field in ("prompt_digest", "output_digest", "invocation_receipt_digest",
                "score_artifact_digest"):
            if not isinstance(item.get(field), str) or _HEX_DIGEST.fullmatch(item[field]) is None:
                raise ValueError("ordinary_chat_history_result_digest_invalid")
        receipt_id = item.get("invocation_receipt_id")
        if not isinstance(receipt_id, str) or _RUN_ID.fullmatch(receipt_id) is None:
            raise ValueError("ordinary_chat_history_result_receipt_id_invalid")
        score_artifact_id = item.get("score_artifact_id")
        if (not isinstance(score_artifact_id, str)
                or len(score_artifact_id) != len(SCORE_ID_PREFIX) + 24
                or not score_artifact_id.startswith(SCORE_ID_PREFIX)
                or re.fullmatch(r"[0-9a-f]{24}", score_artifact_id[len(SCORE_ID_PREFIX):]) is None):
            raise ValueError("ordinary_chat_history_result_score_identity_invalid")
        normalized[condition] = {field: item[field] for field in (
            "prompt_digest", "output_digest", "invocation_receipt_id",
            "invocation_receipt_digest", "score_artifact_id", "score_artifact_digest")}
    semantic = {
        "schema_version": RESULT_SCHEMA,
        "protocol_id": verified["protocol_id"],
        "protocol_digest": verified["protocol_digest"],
        "prompt_bundle_digest": verified["prompt_bundle_digest"],
        "condition_order": list(verified["condition_order"]),
        "conditions": normalized,
        "score_interpretation": "not_verified_or_interpreted:v1",
        "effect_established": False,
        "improvement_established": False,
        "learning_established": False,
        "authority": False,
    }
    _validate_json_bound(semantic, maximum_bytes=32_768,
        error_code="ordinary_chat_history_result_over_bound")
    digest = digest_payload(semantic)
    return {**semantic, "result_id": RESULT_ID_PREFIX + digest[:24],
        "result_digest": digest}


def verify_ordinary_chat_history_intervention_result(result: Mapping[str, Any], *,
        protocol: Mapping[str, Any], prompt_bundle: Mapping[str, Any],
        score_artifacts: Mapping[str, Mapping[str, Any]] | None = None,
        scoring_plan: Mapping[str, Any] | None = None,
        invocation_receipt_verifier: Callable[..., Mapping[str, Any]] | None = None
        ) -> dict[str, Any]:
    """Check result links and, when supplied, bound durable score artifacts."""
    rebuilt = build_ordinary_chat_history_intervention_result(
        protocol=protocol, prompt_bundle=prompt_bundle,
        conditions=result.get("conditions") if isinstance(result, Mapping) else None)
    if (dict(result) != rebuilt
            or result.get("schema_version") != RESULT_SCHEMA
            or result.get("protocol_id") != protocol.get("protocol_id")
            or result.get("protocol_digest") != protocol.get("protocol_digest")):
        raise ValueError("ordinary_chat_history_result_digest_mismatch")
    scores_verified = False
    receipts_verified = False
    if invocation_receipt_verifier is not None:
        if not callable(invocation_receipt_verifier):
            raise ValueError("ordinary_chat_history_invocation_verifier_invalid")
        for condition in CONDITIONS:
            item = result["conditions"][condition]
            receipt = invocation_receipt_verifier(condition=condition,
                receipt_id=item["invocation_receipt_id"],
                receipt_digest=item["invocation_receipt_digest"],
                protocol=dict(protocol),
                expected_prompt_digest=item["prompt_digest"],
                expected_output_digest=item["output_digest"])
            _verify_invocation_summary(receipt,
                receipt_id=item["invocation_receipt_id"],
                receipt_digest=item["invocation_receipt_digest"],
                protocol=protocol, prompt_digest=item["prompt_digest"],
                output_digest=item["output_digest"])
        receipts_verified = True
    if score_artifacts is not None:
        if not isinstance(score_artifacts, Mapping):
            raise ValueError("ordinary_chat_history_result_score_artifacts_invalid")
        if scoring_plan is None:
            raise ValueError("ordinary_chat_history_result_scoring_plan_required")
        conditions = result["conditions"]
        expected_ids = {conditions[condition]["score_artifact_id"]
            for condition in CONDITIONS}
        if set(score_artifacts) != expected_ids:
            raise ValueError("ordinary_chat_history_result_score_artifacts_incomplete")
        for score_id in expected_ids:
            artifact = score_artifacts[score_id]
            checked = verify_ordinary_chat_history_score_artifact(artifact,
                protocol=protocol, scoring_plan=scoring_plan,
                prompt_bundle=prompt_bundle)
            matches = [condition for condition in CONDITIONS
                if conditions[condition]["score_artifact_id"] == score_id]
            if (len(matches) != 1
                    or checked["score_artifact_digest"]
                        != conditions[matches[0]]["score_artifact_digest"]
                    or checked["output_digest"]
                        != conditions[matches[0]]["output_digest"]):
                raise ValueError("ordinary_chat_history_result_score_binding_invalid")
        scores_verified = True
    return {"schema_version": "sentientos.ordinary_chat_history_intervention_result_verification:v1",
        "result_id": result["result_id"], "result_digest": result["result_digest"],
        "protocol_id": result["protocol_id"], "references_bound": True,
        "referenced_receipts_verified": receipts_verified,
        "score_artifact_bindings_verified": scores_verified,
        "score_semantics_verified": scores_verified,
        "effect_established": False, "learning_established": False,
        "authority": False}


def execute_ordinary_chat_history_intervention(*, protocol: Mapping[str, Any],
        prompt_bundle: Mapping[str, Any],
        invoke: Callable[..., Mapping[str, Any]],
        verify_invocation_receipt: Callable[..., Mapping[str, Any]],
        score_blinded: Callable[..., Mapping[str, Any]],
        store: Any) -> dict[str, Any]:
    """Run three matched conditions through explicit serving and scoring owners.

    This function has no model access of its own. ``invoke`` and receipt
    verification are separate required capabilities. Outputs remain in memory
    only long enough to be scored; the returned artifact contains digests and
    externally persisted evidence references, not output text or scores.
    """
    if (not all(callable(value) for value in
            (invoke, verify_invocation_receipt, score_blinded))
            or not callable(getattr(store, "load_protocol", None))
            or not callable(getattr(store, "load_scoring_plan", None))
            or not callable(getattr(store, "load_score_artifact", None))):
        raise ValueError("ordinary_chat_history_runner_owner_required")
    protocol_check = verify_ordinary_chat_history_intervention_protocol(
        protocol, prompt_bundle=prompt_bundle)
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        raise ValueError("ordinary_chat_history_runner_requires_current_protocol")
    persisted_protocol = store.load_protocol(protocol["protocol_id"],
        prompt_bundle=prompt_bundle)
    if dict(persisted_protocol) != dict(protocol):
        raise ValueError("ordinary_chat_history_runner_protocol_not_persisted")
    scoring_plan = store.load_scoring_plan(protocol=protocol,
        prompt_bundle=prompt_bundle)
    verify_ordinary_chat_history_objective_scoring_plan(
        scoring_plan, protocol=protocol, prompt_bundle=prompt_bundle)
    prompts = prompt_bundle.get("prompts")
    outputs: dict[str, str] = {}
    condition_evidence: dict[str, dict[str, str]] = {}
    for condition in protocol_check["condition_order"]:
        prompt = prompts.get(condition)
        prompt_digest = protocol["condition_prompt_digests"][condition]
        invoked = invoke(condition=condition, prompt=prompt, protocol=dict(protocol))
        if (not isinstance(invoked, Mapping)
                or set(invoked) != {"output_text", "invocation_receipt_id",
                    "invocation_receipt_digest"}
                or not isinstance(invoked.get("output_text"), str)
                or not invoked.get("output_text")
                or len(invoked["output_text"].encode("utf-8")) > 65_536):
            raise ValueError("ordinary_chat_history_runner_invocation_invalid")
        output_text = invoked["output_text"]
        output_digest = digest_payload({"output": output_text})
        receipt_id = invoked.get("invocation_receipt_id")
        receipt_digest = invoked.get("invocation_receipt_digest")
        if (not isinstance(receipt_id, str) or _RUN_ID.fullmatch(receipt_id) is None
                or not isinstance(receipt_digest, str)
                or _HEX_DIGEST.fullmatch(receipt_digest) is None):
            raise ValueError("ordinary_chat_history_runner_receipt_reference_invalid")
        receipt = verify_invocation_receipt(condition=condition,
            receipt_id=receipt_id, receipt_digest=receipt_digest,
            protocol=dict(protocol), expected_prompt_digest=prompt_digest,
            expected_output_digest=output_digest)
        _verify_invocation_summary(receipt, receipt_id=receipt_id,
            receipt_digest=receipt_digest, protocol=protocol,
            prompt_digest=prompt_digest, output_digest=output_digest)
        outputs[condition] = output_text
        condition_evidence[condition] = {
            "prompt_digest": prompt_digest,
            "output_digest": output_digest,
            "invocation_receipt_id": receipt_id,
            "invocation_receipt_digest": receipt_digest,
        }

    sample_ids = {condition: "blind-sample-" + secrets.token_hex(16)
        for condition in CONDITIONS}
    samples = [{"sample_id": sample_ids[condition],
        "output_digest": condition_evidence[condition]["output_digest"],
        "output_text": outputs[condition]} for condition in CONDITIONS]
    secrets.SystemRandom().shuffle(samples)
    scoring = score_blinded(scoring_plan_digest=protocol["scoring_plan_digest"],
        samples=samples)
    score_map = scoring.get("score_artifacts") if isinstance(scoring, Mapping) else None
    if (not isinstance(scoring, Mapping)
            or scoring.get("scoring_plan_digest") != protocol["scoring_plan_digest"]
            or scoring.get("scorer_identity_digest")
                != protocol.get("scorer_identity_digest")
            or scoring.get("blinding_posture") != "condition_blinded_independent_score:v1"
            or not isinstance(score_map, Mapping)
            or set(score_map) != set(sample_ids.values())
            or any(not isinstance(score_map.get(sample_id), Mapping)
                or set(score_map[sample_id]) != {"score_artifact_id",
                    "score_artifact_digest"}
                or not isinstance(score_map[sample_id].get("score_artifact_id"), str)
                or len(score_map[sample_id]["score_artifact_id"])
                    != len(SCORE_ID_PREFIX) + 24
                or not score_map[sample_id]["score_artifact_id"].startswith(SCORE_ID_PREFIX)
                or re.fullmatch(r"[0-9a-f]{24}",
                    score_map[sample_id]["score_artifact_id"][len(SCORE_ID_PREFIX):]) is None
                or not isinstance(score_map[sample_id].get("score_artifact_digest"), str)
                or _HEX_DIGEST.fullmatch(score_map[sample_id]["score_artifact_digest"]) is None
                for sample_id in sample_ids.values())):
        raise ValueError("ordinary_chat_history_runner_scoring_verification_failed")
    score_artifacts: dict[str, Mapping[str, Any]] = {}
    for condition in CONDITIONS:
        references = score_map[sample_ids[condition]]
        artifact = store.load_score_artifact(references["score_artifact_id"],
            protocol=protocol, prompt_bundle=prompt_bundle)
        checked = verify_ordinary_chat_history_score_artifact(artifact,
            protocol=protocol, scoring_plan=scoring_plan,
            prompt_bundle=prompt_bundle)
        if (artifact.get("sample_id") != sample_ids[condition]
                or checked["score_artifact_digest"]
                    != references["score_artifact_digest"]
                or checked["output_digest"]
                    != condition_evidence[condition]["output_digest"]):
            raise ValueError("ordinary_chat_history_runner_score_artifact_mismatch")
        condition_evidence[condition].update(references)
        score_artifacts[references["score_artifact_id"]] = artifact
    result = build_ordinary_chat_history_intervention_result(
        protocol=protocol, prompt_bundle=prompt_bundle,
        conditions=condition_evidence)
    verify_ordinary_chat_history_intervention_result(result,
        protocol=protocol, prompt_bundle=prompt_bundle,
        score_artifacts=score_artifacts, scoring_plan=scoring_plan,
        invocation_receipt_verifier=verify_invocation_receipt)
    return result


class OrdinaryChatHistoryChatInferenceAdapter:
    """Adapt an existing governed chat inference owner to the runner contract.

    The adapter neither creates nor loads a model. It uses the injected chat
    inference owner and its persisted-receipt verifier, bound to the source
    conversation turn recorded in the protocol.
    """

    def __init__(self, inference: Any, *, budget: LocalModelInvocationBudget,
            caller_linkage: Mapping[str, Any] | None = None) -> None:
        if (not callable(getattr(inference, "generate", None))
                or not callable(getattr(inference,
                    "current_conversation_model_identity", None))
                or not callable(getattr(inference, "verify_stored_chat_invocation", None))
                or not isinstance(budget, LocalModelInvocationBudget)
                or (caller_linkage is not None and not isinstance(caller_linkage, Mapping))):
            raise ValueError("ordinary_chat_history_chat_inference_owner_invalid")
        _validate_json_bound(dict(caller_linkage or {}), maximum_bytes=16_384,
            error_code="ordinary_chat_history_chat_linkage_invalid")
        self._inference = inference
        self._budget = budget
        self._caller_linkage = dict(caller_linkage or {})

    def invoke(self, *, condition: str, prompt: str,
            protocol: Mapping[str, Any]) -> Mapping[str, Any]:
        if condition not in CONDITIONS or not isinstance(prompt, str):
            raise ValueError("ordinary_chat_history_chat_invocation_invalid")
        if digest_payload({"prompt": prompt}) != protocol.get(
                "condition_prompt_digests", {}).get(condition):
            raise ValueError("ordinary_chat_history_chat_prompt_binding_invalid")
        observed_identity = self._inference.current_conversation_model_identity()
        expected_identity = protocol.get("serving_model_identity")
        if (not isinstance(observed_identity, Mapping)
                or not isinstance(expected_identity, Mapping)
                or dict(observed_identity) != dict(expected_identity)):
            raise ValueError("ordinary_chat_history_chat_model_identity_changed")
        session_id = protocol.get("session_id")
        user_turn_id = protocol.get("source_user_turn_id")
        if (not isinstance(session_id, str) or not isinstance(user_turn_id, str)
                or ("session_id" in self._caller_linkage
                    and self._caller_linkage["session_id"] != session_id)
                or ("user_turn_id" in self._caller_linkage
                    and self._caller_linkage["user_turn_id"] != user_turn_id)):
            raise ValueError("ordinary_chat_history_chat_source_binding_invalid")
        linkage = {**self._caller_linkage, "session_id": session_id,
            "user_turn_id": user_turn_id,
            INTERVENTION_LINKAGE_KEY: {"protocol_id": protocol.get("protocol_id"),
                "protocol_digest": protocol.get("protocol_digest"),
                "condition": condition}}
        correlation = (f"ordinary-history:{protocol.get('run_id')}:"
            f"{condition}:{protocol.get('trial_index')}")
        receipt = self._inference.generate(prompt=prompt, caller="chat_service",
            correlation_id=correlation, budget=self._budget,
            caller_linkage=linkage)
        output_text = getattr(receipt, "output_text", None)
        receipt_id = getattr(receipt, "receipt_id", None)
        receipt_digest = getattr(receipt, "receipt_digest", None)
        output_digest = getattr(receipt, "output_digest", None)
        if (not isinstance(output_text, str) or not output_text
                or not isinstance(receipt_id, str)
                or not isinstance(receipt_digest, str)
                or not isinstance(output_digest, str)
                or output_digest != digest_payload({"output": output_text})):
            raise ValueError("ordinary_chat_history_chat_receipt_invalid")
        return {"output_text": output_text, "invocation_receipt_id": receipt_id,
            "invocation_receipt_digest": receipt_digest}

    def verify_invocation_receipt(self, *, condition: str, receipt_id: str,
            receipt_digest: str, protocol: Mapping[str, Any],
            expected_prompt_digest: str,
            expected_output_digest: str) -> Mapping[str, Any]:
        if condition not in CONDITIONS:
            raise ValueError("ordinary_chat_history_chat_condition_invalid")
        verified = self._inference.verify_stored_chat_invocation(
            receipt_id=receipt_id, receipt_digest=receipt_digest,
            session_id=str(protocol.get("session_id")),
            user_turn_id=str(protocol.get("source_user_turn_id")))
        if not isinstance(verified, Mapping):
            raise ValueError("ordinary_chat_history_chat_receipt_verification_failed")
        identity = verified.get("loaded_model_identity")
        if not isinstance(identity, Mapping) or not identity:
            raise ValueError("ordinary_chat_history_chat_identity_unavailable")
        return {"receipt_identity_verified": True,
            "receipt_id": verified.get("receipt_id"),
            "receipt_digest": verified.get("receipt_digest"),
            "prompt_digest": verified.get("prompt_digest"),
            "output_digest": verified.get("output_digest"),
            "serving_model_identity_digest": digest_payload(dict(identity)),
            "generation_config_digest": verified.get("generation_config_digest"),
            "status": verified.get("status"),
            "output_truncated": verified.get("output_truncated"),
            "fallback_occurred": verified.get("fallback_occurred")}


class OrdinaryChatHistoryAffineObjectiveScorer:
    """Score blind outputs with SentientOS's deterministic affine-task oracle."""

    def __init__(self, *, protocol: Mapping[str, Any],
            prompt_bundle: Mapping[str, Any], scoring_plan: Mapping[str, Any],
            store: Any) -> None:
        if not callable(getattr(store, "persist_score_artifact", None)):
            raise ValueError("ordinary_chat_history_score_store_required")
        verify_ordinary_chat_history_intervention_protocol(
            protocol, prompt_bundle=prompt_bundle)
        verify_ordinary_chat_history_objective_scoring_plan(
            scoring_plan, protocol=protocol, prompt_bundle=prompt_bundle)
        self._protocol = dict(protocol)
        self._prompt_bundle = prompt_bundle
        self._plan = dict(scoring_plan)
        self._store = store

    def score_blinded(self, *, scoring_plan_digest: str,
            samples: list[Mapping[str, Any]]) -> Mapping[str, Any]:
        if (scoring_plan_digest != self._plan["scoring_plan_digest"]
                or not isinstance(samples, list) or len(samples) != len(CONDITIONS)):
            raise ValueError("ordinary_chat_history_blind_score_input_invalid")
        from .developmental_model_replacement_experiment import (
            _objective_score, _verify_objective_score,
        )
        artifacts: dict[str, dict[str, str]] = {}
        seen_sample_ids: set[str] = set()
        for sample in samples:
            if (not isinstance(sample, Mapping)
                    or set(sample) != {"sample_id", "output_digest", "output_text"}
                    or not isinstance(sample.get("sample_id"), str)
                    or _BLIND_SAMPLE_ID.fullmatch(sample["sample_id"]) is None
                    or sample["sample_id"] in seen_sample_ids
                    or not isinstance(sample.get("output_text"), str)
                    or not isinstance(sample.get("output_digest"), str)
                    or _HEX_DIGEST.fullmatch(sample["output_digest"]) is None
                    or sample["output_digest"] != digest_payload({
                        "output": sample["output_text"]})):
                raise ValueError("ordinary_chat_history_blind_score_sample_invalid")
            seen_sample_ids.add(sample["sample_id"])
            score = _objective_score(self._plan, sample["output_text"],
                sample["output_digest"], output_truncated=False)
            _verify_objective_score(self._plan, score, sample["output_digest"],
                output_truncated=False)
            artifact = build_ordinary_chat_history_score_artifact(
                protocol=self._protocol, sample_id=sample["sample_id"],
                output_digest=sample["output_digest"],
                scorer_identity_digest=self._plan["scorer_identity_digest"],
                score_payload=score)
            artifact_id = self._store.persist_score_artifact(artifact,
                protocol=self._protocol, prompt_bundle=self._prompt_bundle)
            artifacts[sample["sample_id"]] = {
                "score_artifact_id": artifact_id,
                "score_artifact_digest": artifact["score_artifact_digest"]}
        if len(artifacts) != len(CONDITIONS):
            raise ValueError("ordinary_chat_history_blind_score_incomplete")
        return {"scoring_plan_digest": self._plan["scoring_plan_digest"],
            "scorer_identity_digest": self._plan["scorer_identity_digest"],
            "blinding_posture": "condition_blinded_independent_score:v1",
            "score_artifacts": artifacts}


def verify_ordinary_chat_history_intervention_protocol(
        protocol: Mapping[str, Any], *,
        prompt_bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a pre-registration artifact without invoking its model."""
    if not isinstance(prompt_bundle, Mapping):
        raise ValueError("ordinary_chat_history_protocol_prompt_bundle_invalid")
    bundle_verification = verify_ordinary_chat_history_intervention_prompt_bundle(
        prompts=prompt_bundle.get("prompts"),
        verification=prompt_bundle.get("verification"))
    expected_fields = {
        "schema_version", "run_id", "session_id", "source_user_turn_id",
        "source_assistant_turn_id", "source_assistant_response_digest",
        "serving_model_identity", "serving_model_identity_digest",
        "generation_config_digest", "prompt_bundle_digest", "condition_order",
        "condition_prompt_digests", "trial_index", "task_commitment_digest",
        "scoring_plan_digest", "scoring_blinding_posture", "planned_comparisons",
        "non_claims", "authority", "claims_posture", "protocol_id",
        "protocol_digest",
    }
    schema = protocol.get("schema_version") if isinstance(protocol, Mapping) else None
    if schema == PROTOCOL_SCHEMA:
        expected_fields.add("scorer_identity_digest")
    if (not isinstance(protocol, Mapping) or set(protocol) != expected_fields
            or schema not in {LEGACY_PROTOCOL_SCHEMA, PROTOCOL_SCHEMA}
            or not isinstance(protocol.get("run_id"), str)
            or _RUN_ID.fullmatch(protocol["run_id"]) is None
            or not isinstance(protocol.get("session_id"), str)
            or _SESSION_ID.fullmatch(protocol["session_id"]) is None
            or any(not isinstance(protocol.get(key), str)
                or _TURN_ID.fullmatch(protocol[key]) is None
                for key in ("source_user_turn_id", "source_assistant_turn_id"))):
        raise ValueError("ordinary_chat_history_protocol_invalid")
    _validate_json_bound(_semantic(protocol), maximum_bytes=32_768,
        error_code="ordinary_chat_history_protocol_invalid")
    for key in ("source_assistant_response_digest", "generation_config_digest",
            "task_commitment_digest", "scoring_plan_digest"):
        if not isinstance(protocol.get(key), str) or _HEX_DIGEST.fullmatch(
                protocol[key]) is None:
            raise ValueError("ordinary_chat_history_protocol_digest_invalid")
    if schema == PROTOCOL_SCHEMA:
        scorer_digest = protocol.get("scorer_identity_digest")
        if (not isinstance(scorer_digest, str)
                or _HEX_DIGEST.fullmatch(scorer_digest) is None
                or scorer_digest == protocol.get("serving_model_identity_digest")):
            raise ValueError("ordinary_chat_history_protocol_scorer_identity_invalid")
    identity = protocol.get("serving_model_identity")
    if (not isinstance(identity, Mapping) or not identity
            or protocol.get("serving_model_identity_digest")
                != digest_payload(dict(identity))):
        raise ValueError("ordinary_chat_history_protocol_model_identity_invalid")
    trial_index = protocol.get("trial_index")
    order = (list(CONDITIONS) if type(trial_index) is int and trial_index % 2 == 0
        else ["history_withheld", "history_present", "history_restored"]
        if type(trial_index) is int and trial_index % 2 == 1 else None)
    prompt_digests = protocol.get("condition_prompt_digests")
    if (type(trial_index) is not int or not 0 <= trial_index <= 2**31 - 1
            or protocol.get("condition_order") != order
            or not isinstance(prompt_digests, Mapping)
            or set(prompt_digests) != set(CONDITIONS)
            or any(not isinstance(prompt_digests.get(condition), str)
                or _HEX_DIGEST.fullmatch(prompt_digests[condition]) is None
                for condition in CONDITIONS)
            or not isinstance(protocol.get("prompt_bundle_digest"), str)
            or _HEX_DIGEST.fullmatch(protocol["prompt_bundle_digest"]) is None
            or protocol["prompt_bundle_digest"]
                != bundle_verification["prompt_bundle_digest"]
            or protocol.get("condition_order")
                != bundle_verification["condition_order"]
            or protocol.get("condition_prompt_digests")
                != bundle_verification["condition_prompt_digests"]
            or protocol.get("trial_index") != bundle_verification["trial_index"]):
        raise ValueError("ordinary_chat_history_protocol_prompt_binding_invalid")
    if (protocol.get("scoring_blinding_posture") != "condition_blinded_independent_score:v1"
            or protocol.get("planned_comparisons") != list(PLANNED_COMPARISONS)
            or protocol.get("non_claims") != list(NON_CLAIMS)
            or protocol.get("authority") is not False
            or protocol.get("claims_posture") != "preregistered_no_effect_claim:v1"):
        raise ValueError("ordinary_chat_history_protocol_controls_invalid")
    digest = digest_payload(_semantic(protocol))
    if (protocol.get("protocol_digest") != digest
            or protocol.get("protocol_id") != PROTOCOL_ID_PREFIX + digest[:24]):
        raise ValueError("ordinary_chat_history_protocol_digest_mismatch")
    return {
        "schema_version": "sentientos.ordinary_chat_history_intervention_protocol_verification:v1",
        "protocol_id": protocol["protocol_id"],
        "protocol_digest": digest,
        "prompt_bundle_digest": protocol["prompt_bundle_digest"],
        "prompt_bundle_verified": True,
        "condition_order": list(order or ()),
        "authority": False,
        "effect_established": False,
        "learning_established": False,
    }


def build_ordinary_chat_history_intervention_protocol(*, prompt_bundle: Mapping[str, Any],
        run_id: str, session_id: str, source_user_turn_id: str,
        source_assistant_turn_id: str, source_assistant_response_digest: str,
        serving_model_identity: Mapping[str, Any], generation_config_digest: str,
        task_commitment_digest: str, scoring_plan_digest: str,
        scorer_identity_digest: str) -> dict[str, Any]:
    """Freeze exact prompts, serving identity, and independent scoring plan."""
    if not isinstance(prompt_bundle, Mapping):
        raise ValueError("ordinary_chat_history_protocol_prompt_bundle_invalid")
    prompts = prompt_bundle.get("prompts")
    verification = prompt_bundle.get("verification")
    verified_bundle = verify_ordinary_chat_history_intervention_prompt_bundle(
        prompts=prompts, verification=verification)
    if (not isinstance(serving_model_identity, Mapping)
            or not serving_model_identity):
        raise ValueError("ordinary_chat_history_protocol_model_identity_invalid")
    _validate_json_bound(dict(serving_model_identity), maximum_bytes=16_384,
        error_code="ordinary_chat_history_protocol_model_identity_invalid")
    semantic = {
        "schema_version": PROTOCOL_SCHEMA,
        "run_id": run_id,
        "session_id": session_id,
        "source_user_turn_id": source_user_turn_id,
        "source_assistant_turn_id": source_assistant_turn_id,
        "source_assistant_response_digest": source_assistant_response_digest,
        "serving_model_identity": dict(serving_model_identity),
        "serving_model_identity_digest": digest_payload(
            dict(serving_model_identity)),
        "generation_config_digest": generation_config_digest,
        "prompt_bundle_digest": verified_bundle["prompt_bundle_digest"],
        "condition_order": list(verified_bundle["condition_order"]),
        "condition_prompt_digests": dict(
            verified_bundle["condition_prompt_digests"]),
        "trial_index": verified_bundle["trial_index"],
        "task_commitment_digest": task_commitment_digest,
        "scoring_plan_digest": scoring_plan_digest,
        "scorer_identity_digest": scorer_identity_digest,
        "scoring_blinding_posture": "condition_blinded_independent_score:v1",
        "planned_comparisons": list(PLANNED_COMPARISONS),
        "non_claims": list(NON_CLAIMS),
        "authority": False,
        "claims_posture": "preregistered_no_effect_claim:v1",
    }
    _validate_json_bound(semantic, maximum_bytes=32_768,
        error_code="ordinary_chat_history_protocol_over_bound")
    digest = digest_payload(semantic)
    protocol = {**semantic, "protocol_id": PROTOCOL_ID_PREFIX + digest[:24],
        "protocol_digest": digest}
    verify_ordinary_chat_history_intervention_protocol(
        protocol, prompt_bundle=prompt_bundle)
    return protocol


class OrdinaryChatHistoryInterventionStore:
    """Persist immutable ordinary-chat protocols in the governed experiment store."""

    def __init__(self, state_root: Path) -> None:
        self._store = DevelopmentalExperimentStore(Path(state_root))

    def persist_scoring_plan(self, scoring_plan: Mapping[str, Any], *,
            protocol: Mapping[str, Any], prompt_bundle: Mapping[str, Any]) -> str:
        verify_ordinary_chat_history_intervention_protocol(
            protocol, prompt_bundle=prompt_bundle)
        verified = verify_ordinary_chat_history_objective_scoring_plan(
            scoring_plan, protocol=protocol, prompt_bundle=prompt_bundle)
        plan_id = SCORE_PLAN_ID_PREFIX + verified["scoring_plan_digest"][:24]
        path = self._store.protocols / f"{plan_id}.json"
        normalized = json.loads(json.dumps(dict(scoring_plan), sort_keys=True))
        self._store._write_immutable(path, scoring_plan)
        reloaded = self._store._read_json(path)
        verify_ordinary_chat_history_objective_scoring_plan(
            reloaded, protocol=protocol, prompt_bundle=prompt_bundle)
        if reloaded != normalized:
            raise ValueError("ordinary_chat_history_scoring_plan_persistence_mismatch")
        return plan_id

    def load_scoring_plan(self, *, protocol: Mapping[str, Any],
            prompt_bundle: Mapping[str, Any]) -> dict[str, Any]:
        verify_ordinary_chat_history_intervention_protocol(
            protocol, prompt_bundle=prompt_bundle)
        plan_id = SCORE_PLAN_ID_PREFIX + str(protocol["scoring_plan_digest"])[:24]
        try:
            plan = self._store._read_json(self._store.protocols / f"{plan_id}.json")
        except FileNotFoundError as exc:
            raise ValueError("ordinary_chat_history_scoring_plan_missing") from exc
        verified = verify_ordinary_chat_history_objective_scoring_plan(
            plan, protocol=protocol, prompt_bundle=prompt_bundle)
        if (verified["scoring_plan_digest"] != protocol["scoring_plan_digest"]
                or plan_id != SCORE_PLAN_ID_PREFIX
                    + verified["scoring_plan_digest"][:24]):
            raise ValueError("ordinary_chat_history_scoring_plan_identity_mismatch")
        return plan

    def persist_protocol(self, protocol: Mapping[str, Any], *,
            prompt_bundle: Mapping[str, Any],
            scoring_plan: Mapping[str, Any] | None = None) -> str:
        verified = verify_ordinary_chat_history_intervention_protocol(
            protocol, prompt_bundle=prompt_bundle)
        if protocol.get("schema_version") == PROTOCOL_SCHEMA:
            if scoring_plan is None:
                raise ValueError("ordinary_chat_history_preregistered_scoring_plan_required")
            self.persist_scoring_plan(scoring_plan, protocol=protocol,
                prompt_bundle=prompt_bundle)
        protocol_id = verified["protocol_id"]
        normalized = json.loads(json.dumps(dict(protocol), sort_keys=True))
        path = self._store.protocols / f"{protocol_id}.json"
        self._store._write_immutable(path, protocol)
        reloaded = self._store._read_json(path)
        verify_ordinary_chat_history_intervention_protocol(
            reloaded, prompt_bundle=prompt_bundle)
        if reloaded != normalized:
            raise ValueError("ordinary_chat_history_protocol_persistence_mismatch")
        return protocol_id

    def load_protocol(self, protocol_id: str, *,
            prompt_bundle: Mapping[str, Any]) -> dict[str, Any]:
        prefix = PROTOCOL_ID_PREFIX
        if (not isinstance(protocol_id, str)
                or len(protocol_id) != len(prefix) + 24
                or not protocol_id.startswith(prefix)
                or re.fullmatch(r"[0-9a-f]{24}", protocol_id[len(prefix):]) is None):
            raise ValueError("ordinary_chat_history_protocol_identity_invalid")
        path = self._store.protocols / f"{protocol_id}.json"
        try:
            protocol = self._store._read_json(path)
        except FileNotFoundError as exc:
            raise ValueError("ordinary_chat_history_protocol_missing") from exc
        result = verify_ordinary_chat_history_intervention_protocol(
            protocol, prompt_bundle=prompt_bundle)
        if result["protocol_id"] != protocol_id:
            raise ValueError("ordinary_chat_history_protocol_identity_mismatch")
        return protocol

    def persist_score_artifact(self, artifact: Mapping[str, Any], *,
            protocol: Mapping[str, Any], prompt_bundle: Mapping[str, Any]) -> str:
        scoring_plan = self.load_scoring_plan(protocol=protocol,
            prompt_bundle=prompt_bundle)
        verified = verify_ordinary_chat_history_score_artifact(
            artifact, protocol=protocol, scoring_plan=scoring_plan,
            prompt_bundle=prompt_bundle)
        score_id = verified["score_artifact_id"]
        path = self._store.runs / f"{score_id}.json"
        normalized = json.loads(json.dumps(dict(artifact), sort_keys=True))
        self._store._write_immutable(path, artifact)
        reloaded = self._store._read_json(path)
        verify_ordinary_chat_history_score_artifact(reloaded, protocol=protocol,
            scoring_plan=scoring_plan, prompt_bundle=prompt_bundle)
        if reloaded != normalized:
            raise ValueError("ordinary_chat_history_score_persistence_mismatch")
        return score_id

    def load_score_artifact(self, score_id: str, *, protocol: Mapping[str, Any],
            prompt_bundle: Mapping[str, Any]) -> dict[str, Any]:
        if (not isinstance(score_id, str)
                or len(score_id) != len(SCORE_ID_PREFIX) + 24
                or not score_id.startswith(SCORE_ID_PREFIX)
                or re.fullmatch(r"[0-9a-f]{24}", score_id[len(SCORE_ID_PREFIX):]) is None):
            raise ValueError("ordinary_chat_history_score_identity_invalid")
        scoring_plan = self.load_scoring_plan(protocol=protocol,
            prompt_bundle=prompt_bundle)
        try:
            artifact = self._store._read_json(self._store.runs / f"{score_id}.json")
        except FileNotFoundError as exc:
            raise ValueError("ordinary_chat_history_score_artifact_missing") from exc
        verified = verify_ordinary_chat_history_score_artifact(
            artifact, protocol=protocol, scoring_plan=scoring_plan,
            prompt_bundle=prompt_bundle)
        if verified["score_artifact_id"] != score_id:
            raise ValueError("ordinary_chat_history_score_identity_mismatch")
        return artifact

    def _score_artifacts_for_result(self, result: Mapping[str, Any], *,
            protocol: Mapping[str, Any], prompt_bundle: Mapping[str, Any]
            ) -> dict[str, Mapping[str, Any]]:
        score_ids = {result["conditions"][condition]["score_artifact_id"]
            for condition in CONDITIONS}
        return {score_id: self.load_score_artifact(score_id, protocol=protocol,
            prompt_bundle=prompt_bundle) for score_id in score_ids}

    def persist_result(self, result: Mapping[str, Any], *,
            protocol: Mapping[str, Any], prompt_bundle: Mapping[str, Any],
            invocation_receipt_verifier: Callable[..., Mapping[str, Any]] | None = None
            ) -> str:
        """Immutably persist a result packet after rechecking its protocol links."""
        verification = verify_ordinary_chat_history_intervention_result(
            result, protocol=protocol, prompt_bundle=prompt_bundle,
            invocation_receipt_verifier=invocation_receipt_verifier)
        scores = self._score_artifacts_for_result(result, protocol=protocol,
            prompt_bundle=prompt_bundle)
        scoring_plan = self.load_scoring_plan(protocol=protocol,
            prompt_bundle=prompt_bundle)
        verify_ordinary_chat_history_intervention_result(result,
            protocol=protocol, prompt_bundle=prompt_bundle,
            score_artifacts=scores, scoring_plan=scoring_plan,
            invocation_receipt_verifier=invocation_receipt_verifier)
        result_id = verification["result_id"]
        normalized = json.loads(json.dumps(dict(result), sort_keys=True))
        path = self._store.runs / f"{result_id}.json"
        self._store._write_immutable(path, result)
        reloaded = self._store._read_json(path)
        reloaded_scores = self._score_artifacts_for_result(reloaded,
            protocol=protocol, prompt_bundle=prompt_bundle)
        verify_ordinary_chat_history_intervention_result(reloaded,
            protocol=protocol, prompt_bundle=prompt_bundle,
            score_artifacts=reloaded_scores, scoring_plan=scoring_plan,
            invocation_receipt_verifier=invocation_receipt_verifier)
        if reloaded != normalized:
            raise ValueError("ordinary_chat_history_result_persistence_mismatch")
        return result_id

    def load_result(self, result_id: str, *, protocol: Mapping[str, Any],
            prompt_bundle: Mapping[str, Any],
            invocation_receipt_verifier: Callable[..., Mapping[str, Any]] | None = None
            ) -> dict[str, Any]:
        prefix = RESULT_ID_PREFIX
        if (not isinstance(result_id, str) or len(result_id) != len(prefix) + 24
                or not result_id.startswith(prefix)
                or re.fullmatch(r"[0-9a-f]{24}", result_id[len(prefix):]) is None):
            raise ValueError("ordinary_chat_history_result_identity_invalid")
        try:
            result = self._store._read_json(self._store.runs / f"{result_id}.json")
        except FileNotFoundError as exc:
            raise ValueError("ordinary_chat_history_result_missing") from exc
        verification = verify_ordinary_chat_history_intervention_result(
            result, protocol=protocol, prompt_bundle=prompt_bundle,
            invocation_receipt_verifier=invocation_receipt_verifier)
        scores = self._score_artifacts_for_result(result, protocol=protocol,
            prompt_bundle=prompt_bundle)
        scoring_plan = self.load_scoring_plan(protocol=protocol,
            prompt_bundle=prompt_bundle)
        verify_ordinary_chat_history_intervention_result(result,
            protocol=protocol, prompt_bundle=prompt_bundle,
            score_artifacts=scores, scoring_plan=scoring_plan,
            invocation_receipt_verifier=invocation_receipt_verifier)
        if verification["result_id"] != result_id:
            raise ValueError("ordinary_chat_history_result_identity_mismatch")
        return result
