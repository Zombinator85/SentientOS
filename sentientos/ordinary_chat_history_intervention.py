"""Pre-registration controls for ordinary-chat history interventions.

This module prepares and verifies a digest-bound protocol. It does not execute
model calls, persist results, or claim that any effect or learning occurred.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

from .conversation_session import (
    verify_ordinary_chat_history_intervention_prompt_bundle,
)
from .local_model_authority import digest_payload

PROTOCOL_SCHEMA = "sentientos.ordinary_chat_history_intervention_protocol:v1"
PROTOCOL_ID_PREFIX = "ordinary-history-protocol-"
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


def _validate_json_bound(value: Any, *, maximum_bytes: int, error_code: str) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError(error_code) from exc
    if len(encoded) > maximum_bytes:
        raise ValueError(error_code)


def _semantic(protocol: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in protocol.items()
        if key not in {"protocol_id", "protocol_digest"}}


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
    if (not isinstance(protocol, Mapping) or set(protocol) != expected_fields
            or protocol.get("schema_version") != PROTOCOL_SCHEMA
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
        task_commitment_digest: str, scoring_plan_digest: str) -> dict[str, Any]:
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
