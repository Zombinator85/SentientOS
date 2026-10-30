"""Deterministic execution bindings for epistemic qualification samples."""
from __future__ import annotations

from typing import Any, Mapping

from .local_model_authority import digest_payload

SCHEMA = "sentientos.epistemic_execution_binding:v1"


def build_execution_binding(*, case_id: str, evaluator_version: str, condition: str,
        model_id: Any, model_artifact_digest: Any, active_model_identity: Any,
        generation_config: Any, prompt_digest: str, projection_digest: str,
        observation_digest: str, receipt_digest: str, output_digest: str | None) -> dict[str, Any]:
    """Bind one scored sample to the worker, execution, supplied context, and test.

    Identity/configuration values are represented by stable digests where they may
    contain deployment-local detail. Missing identity remains explicit and makes
    the binding incomplete; no performance or qualification claim is implied.
    """
    identity_valid = isinstance(active_model_identity, Mapping)
    config_valid = isinstance(generation_config, Mapping)
    complete = (isinstance(case_id, str) and bool(case_id)
        and isinstance(evaluator_version, str) and bool(evaluator_version)
        and condition in {"before", "after"}
        and isinstance(model_id, str) and bool(model_id)
        and isinstance(model_artifact_digest, str) and bool(model_artifact_digest)
        and identity_valid and config_valid
        and all(isinstance(value, str) and bool(value) for value in
            (prompt_digest, projection_digest, observation_digest, receipt_digest)))
    payload = {
        "schema": SCHEMA,
        "case_id": case_id,
        "evaluator_version": evaluator_version,
        "condition": condition,
        "model_id": model_id,
        "model_artifact_digest": model_artifact_digest,
        "active_model_identity_digest": ("sha256:" + digest_payload(active_model_identity)
            if identity_valid else None),
        "generation_config_digest": ("sha256:" + digest_payload(generation_config)
            if config_valid else None),
        "prompt_digest": prompt_digest,
        "projection_digest": projection_digest,
        "observation_digest": observation_digest,
        "receipt_digest": receipt_digest,
        "output_digest": output_digest,
        "complete": complete,
    }
    return {**payload, "binding_digest": "sha256:" + digest_payload(payload)}


__all__ = ["SCHEMA", "build_execution_binding"]
