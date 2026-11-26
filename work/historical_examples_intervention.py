"""Prepare, execute, validate, and score a resident-owned historical-example pair.

Protocol preparation, journal verification, and scoring are CPU-only. The
explicit pair coordinator calls a supplied resident executor; its one-shot
owner path does not write developmental history. Scoring requires governed
invocation receipts.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sentientos.governed_local_model_invocation import validate_receipt


SCHEMA_VERSION = "sentientos.historical_examples_intervention_protocol:v3"
_LEGACY_SCHEMA_VERSION = "sentientos.historical_examples_intervention_protocol:v2"
_PREVIEW_SCHEMA = "sentientos.objective_historical_examples_prompt_pair_preview:v1"
_OWNER_PROTOCOL_SCHEMAS = {
    "sentientos.developmental_history_intervention_protocol:v14",
    "sentientos.developmental_history_intervention_protocol:v15",
}
_ARMS = ("examples_included", "examples_omitted")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RAW_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PAIR_RUN_ID = re.compile(r"rootless-cognition-cycle-[0-9a-f]{20}\Z")
_PAIR_EXECUTION_PLAN_SCHEMA = (
    "sentientos.historical_examples_pair_execution_plan:v1")
_PAIR_RUNNER_BINDING_SCHEMA = (
    "sentientos.historical_examples_pair_runner_binding:v1")
_PAIR_EXECUTION_TERMINAL_SCHEMA = (
    "sentientos.historical_examples_pair_execution_terminal:v1")


class HistoricalExamplesInterventionError(ValueError):
    """Invalid owner preview or frozen protocol binding."""


@dataclass(frozen=True)
class HistoricalExamplesArmExecution:
    """Verified receipt plus the runtime history inventory guard evidence."""

    receipt: Mapping[str, Any]
    runtime_history_inventory: Mapping[str, Any]


class HistoricalExamplesPairJournal:
    """Immutable protocol and arm journal backed by DevelopmentalExperimentStore.

    The store supplies atomic no-replace publication and custody checks. Claims
    are committed before invocation; a claim without a receipt is ambiguous and
    is never replayed automatically.
    """

    def __init__(self, *, store: Any) -> None:
        if (not isinstance(getattr(store, "protocols", None), Path)
                or not isinstance(getattr(store, "runs", None), Path)
                or not callable(getattr(store, "_write_immutable", None))
                or not callable(getattr(store, "_read_json", None))):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_store_invalid")
        self._store = store

    @staticmethod
    def _identifier(value: Any, code: str) -> str:
        if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
            raise HistoricalExamplesInterventionError(code)
        return value[7:31]

    def _publish(self, path: Any, semantic: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(semantic)
        value["journal_record_digest"] = _digest(semantic)
        try:
            self._store._write_immutable(path, value)
            stored = self._store._read_json(path)
        except Exception as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_publication_failed") from exc
        if stored != value:
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_readback_mismatch")
        return stored

    @staticmethod
    def _verify_record(value: Mapping[str, Any], *, code: str) -> dict[str, Any]:
        semantic = {key: item for key, item in value.items()
            if key != "journal_record_digest"}
        if value.get("journal_record_digest") != _digest(semantic):
            raise HistoricalExamplesInterventionError(code)
        return semantic

    def _preflight_audit_path(self, *, protocol_digest: str) -> Path:
        identifier = self._identifier(protocol_digest,
            "historical_examples_protocol_digest_invalid")
        identity = _digest({"domain":
            "sentientos.historical_examples_pair_journal_preflight_audit:v1",
            "protocol_digest": protocol_digest})[7:31]
        return self._store.protocols / f"devexp-protocol-{identity}.json"

    def persist_preflight_audit(self, *, protocol: Mapping[str, Any],
            audit: Mapping[str, Any]) -> dict[str, Any]:
        """Persist the validated held-out separation proof before the protocol."""
        validate_historical_examples_protocol(protocol=protocol)
        checked = verify_historical_examples_probe_history_overlap_audit(audit)
        audit_digest = _digest(checked)
        if protocol.get("held_out_probe_overlap_audit_digest") != audit_digest:
            raise HistoricalExamplesInterventionError(
                "historical_examples_preflight_audit_protocol_mismatch")
        semantic = {"schema_version":
                "sentientos.historical_examples_pair_journal_preflight_audit:v1",
            "protocol_digest": protocol["protocol_digest"],
            "audit_digest": audit_digest, "audit": checked,
            "authority": False}
        self._publish(self._preflight_audit_path(
            protocol_digest=protocol["protocol_digest"]), semantic)
        return self.load_preflight_audit(protocol_digest=protocol[
            "protocol_digest"], expected_audit_digest=audit_digest)

    def load_preflight_audit(self, *, protocol_digest: str,
            expected_audit_digest: str) -> dict[str, Any]:
        _require_digest(expected_audit_digest,
            "historical_examples_preflight_audit_digest_invalid")
        try:
            value = self._store._read_json(self._preflight_audit_path(
                protocol_digest=protocol_digest))
        except Exception as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_preflight_audit_missing") from exc
        semantic = self._verify_record(value,
            code="historical_examples_preflight_audit_record_digest_mismatch")
        if (set(value) != {"schema_version", "protocol_digest", "audit_digest",
                "audit", "authority", "journal_record_digest"}
                or semantic.get("schema_version") !=
                    "sentientos.historical_examples_pair_journal_preflight_audit:v1"
                or semantic.get("protocol_digest") != protocol_digest
                or semantic.get("audit_digest") != expected_audit_digest
                or semantic.get("authority") is not False
                or not isinstance(semantic.get("audit"), Mapping)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_preflight_audit_binding_invalid")
        audit = verify_historical_examples_probe_history_overlap_audit(
            semantic["audit"])
        if _digest(audit) != expected_audit_digest:
            raise HistoricalExamplesInterventionError(
                "historical_examples_preflight_audit_digest_mismatch")
        return audit

    def persist_protocol(self, *, protocol: Mapping[str, Any]) -> dict[str, Any]:
        validate_historical_examples_protocol(protocol=protocol)
        self.load_private_task_plan(
            task_digest=protocol["task_digest"],
            task_plan_digest=protocol["private_task_plan_digest"])
        self.load_preflight_audit(protocol_digest=protocol["protocol_digest"],
            expected_audit_digest=protocol[
                "held_out_probe_overlap_audit_digest"])
        identifier = self._identifier(protocol["protocol_digest"],
            "historical_examples_protocol_digest_invalid")
        semantic = {"schema_version":
                "sentientos.historical_examples_pair_journal_protocol:v1",
            "protocol_digest": protocol["protocol_digest"],
            "protocol": dict(protocol), "authority": False}
        path = self._store.protocols / f"devexp-protocol-{identifier}.json"
        self._publish(path, semantic)
        return self.load_protocol(protocol_digest=protocol["protocol_digest"])

    def load_protocol(self, *, protocol_digest: str) -> dict[str, Any]:
        identifier = self._identifier(protocol_digest,
            "historical_examples_protocol_digest_invalid")
        path = self._store.protocols / f"devexp-protocol-{identifier}.json"
        try:
            value = self._store._read_json(path)
        except Exception as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_protocol_missing") from exc
        semantic = self._verify_record(value,
            code="historical_examples_journal_protocol_digest_mismatch")
        protocol = semantic.get("protocol")
        if (set(value) != {"schema_version", "protocol_digest", "protocol",
                "authority", "journal_record_digest"}
                or semantic.get("schema_version") !=
                "sentientos.historical_examples_pair_journal_protocol:v1"
                or semantic.get("protocol_digest") != protocol_digest
                or semantic.get("authority") is not False
                or not isinstance(protocol, Mapping)
                or protocol.get("protocol_digest") != protocol_digest):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_protocol_binding_invalid")
        validate_historical_examples_protocol(protocol=protocol)
        self.load_private_task_plan(
            task_digest=protocol["task_digest"],
            task_plan_digest=protocol["private_task_plan_digest"])
        self.load_preflight_audit(protocol_digest=protocol_digest,
            expected_audit_digest=protocol[
                "held_out_probe_overlap_audit_digest"])
        return dict(protocol)

    def _task_plan_path(self, task_digest: str,
            task_plan_digest: str | None = None) -> Path:
        task_identifier = self._identifier(task_digest,
            "historical_examples_task_digest_invalid")
        if task_plan_digest is None:
            # Legacy v1 plans were keyed only by the oracle task digest.
            identity = _digest({"domain":
                "sentientos.historical_examples_private_task_plan:v1",
                "task_digest": task_digest})[7:31]
            return self._store.protocols / f"devexp-protocol-{identity}.json"
        plan_identifier = self._identifier(task_plan_digest,
            "historical_examples_private_task_plan_digest_invalid")
        identity = _digest({"domain":
            "sentientos.historical_examples_private_task_plan_path:v2",
            "task_digest": task_digest,
            "task_plan_digest": task_plan_digest})[7:31]
        return self._store.protocols / (
            f"devexp-task-plan-{identity}-{task_identifier}-{plan_identifier}.json")

    def persist_private_task_plan(self, *, objective_task: Any) -> str:
        """Persist the answer-bearing objective task in the private experiment store."""
        if (not callable(getattr(objective_task, "specification", None))
                or not callable(getattr(objective_task, "public_descriptor", None))):
            raise HistoricalExamplesInterventionError(
                "historical_examples_task_plan_invalid")
        specification = objective_task.specification()
        descriptor = objective_task.public_descriptor()
        nonce = getattr(objective_task, "commitment_nonce", None)
        task_digest = (descriptor.get("task_digest")
            if isinstance(descriptor, Mapping) else None)
        identity_policy = (descriptor.get("history_prompt_identity_policy")
            if isinstance(descriptor, Mapping) else None)
        if (not isinstance(specification, Mapping)
                or not isinstance(task_digest, str)
                or _DIGEST.fullmatch(task_digest) is None
                or not isinstance(nonce, str)
                or re.fullmatch(r"[0-9a-f]{64}", nonce) is None
                or identity_policy not in {
                    None, "matched_cross_model_identity_omitted:v1"}):
            raise HistoricalExamplesInterventionError(
                "historical_examples_task_plan_invalid")
        semantic = {"schema_version":
                "sentientos.historical_examples_private_task_plan:v2"
                    if identity_policy is not None else
                    "sentientos.historical_examples_private_task_plan:v1",
            "task_digest": task_digest,
            "task_specification": dict(specification),
            "task_commitment_nonce": nonce,
            **({"history_prompt_identity_policy": identity_policy}
                if identity_policy is not None else {}),
            "authority": False}
        task_plan_digest = _digest(semantic)
        record = {**semantic, "task_plan_digest": task_plan_digest}
        self._publish(self._task_plan_path(task_digest, task_plan_digest), record)
        return task_plan_digest

    def load_private_task_plan(self, *, task_digest: str,
            task_plan_digest: str) -> Any:
        """Reconstruct an exact task from the private answer-bearing plan."""
        _require_digest(task_plan_digest,
            "historical_examples_private_task_plan_digest_invalid")
        path = self._task_plan_path(task_digest, task_plan_digest)
        try:
            value = self._store._read_json(path)
        except FileNotFoundError:
            try:
                value = self._store._read_json(self._task_plan_path(task_digest))
            except Exception as exc:
                raise HistoricalExamplesInterventionError(
                    "historical_examples_private_task_plan_missing") from exc
        except Exception as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_private_task_plan_missing") from exc
        semantic = self._verify_record(value,
            code="historical_examples_private_task_plan_record_digest_mismatch")
        schema_version = semantic.get("schema_version")
        policy_enabled = (schema_version ==
            "sentientos.historical_examples_private_task_plan:v2")
        semantic_keys = {"schema_version", "task_digest", "task_specification",
            "task_commitment_nonce", "authority"}
        if policy_enabled:
            semantic_keys.add("history_prompt_identity_policy")
        if (set(value) != semantic_keys | {"task_plan_digest",
                "journal_record_digest"}
                or schema_version not in {
                    "sentientos.historical_examples_private_task_plan:v1",
                    "sentientos.historical_examples_private_task_plan:v2"}
                or semantic.get("task_digest") != task_digest
                or semantic.get("authority") is not False
                or policy_enabled and semantic.get(
                    "history_prompt_identity_policy") !=
                        "matched_cross_model_identity_omitted:v1"
                or semantic.get("task_plan_digest") != task_plan_digest):
            raise HistoricalExamplesInterventionError(
                "historical_examples_private_task_plan_binding_invalid")
        private_semantic = {key: item for key, item in semantic.items()
            if key != "task_plan_digest"}
        if _digest(private_semantic) != task_plan_digest:
            raise HistoricalExamplesInterventionError(
                "historical_examples_private_task_plan_digest_mismatch")
        specification = semantic.get("task_specification")
        nonce = semantic.get("task_commitment_nonce")
        if (not isinstance(specification, Mapping)
                or not isinstance(nonce, str)
                or re.fullmatch(r"[0-9a-f]{64}", nonce) is None):
            raise HistoricalExamplesInterventionError(
                "historical_examples_private_task_plan_invalid")
        from sentientos.developmental_model_replacement_experiment import (
            FAMILY_TASK_SCHEMA_V3, FAMILY_TASK_SCHEMA_V4,
            FAMILY_TASK_SCHEMA_V5, FAMILY_TASK_SCHEMA_V6,
            ObjectivePredictionTask,
        )
        schema_versions = {FAMILY_TASK_SCHEMA_V3: 3,
            FAMILY_TASK_SCHEMA_V4: 4, FAMILY_TASK_SCHEMA_V5: 5,
            FAMILY_TASK_SCHEMA_V6: 6}
        if specification.get("schema_version") not in schema_versions:
            raise HistoricalExamplesInterventionError(
                "historical_examples_private_task_family_schema_invalid")
        probes = specification.get("probe_inputs")
        if (not isinstance(probes, list) or not probes
                or any(type(value) is not int for value in probes)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_private_task_probes_invalid")
        objective_task = ObjectivePredictionTask(
            multiplier=specification.get("multiplier"),
            offset=specification.get("offset"), probe_input=probes[0],
            additional_probe_inputs=tuple(probes[1:]),
            task_family_id=specification.get("task_family_id"),
            requires_task_family_history=specification.get(
                "requires_task_family_history"),
            commitment_nonce=nonce,
            family_contract_version=schema_versions[
                specification["schema_version"]],
            history_task_family_ids=tuple(specification.get(
                "history_task_family_ids", ())),
            history_prompt_identity_policy=(semantic.get(
                "history_prompt_identity_policy") if policy_enabled else None))
        if (objective_task.specification() != dict(specification)
                or objective_task.public_descriptor().get("task_digest")
                    != task_digest):
            raise HistoricalExamplesInterventionError(
                "historical_examples_private_task_plan_reconstruction_mismatch")
        return objective_task

    def load_task_for_protocol(self, *, protocol_digest: str) -> Any:
        protocol = self.load_protocol(protocol_digest=protocol_digest)
        return self.load_private_task_plan(
            task_digest=protocol["task_digest"],
            task_plan_digest=protocol["private_task_plan_digest"])

    def _event_path(self, *, protocol_digest: str, arm: str,
            event: str) -> Any:
        if arm not in _ARMS or event not in {"claim", "result", "score"}:
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_event_invalid")
        identity = _digest({"domain":
            "sentientos.historical_examples_pair_journal_event:v1",
            "protocol_digest": protocol_digest, "arm": arm,
            "event": event})[7:31]
        return self._store.runs / f"devexp-run-{identity}.json"

    def _load_event(self, *, protocol_digest: str, arm: str,
            event: str) -> dict[str, Any] | None:
        path = self._event_path(protocol_digest=protocol_digest, arm=arm,
            event=event)
        try:
            value = self._store._read_json(path)
        except FileNotFoundError:
            return None
        except Exception as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_event_read_failed") from exc
        return self._verify_record(value,
            code="historical_examples_journal_event_digest_mismatch")

    def arm_state(self, *, protocol_digest: str, arm: str) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest=protocol_digest)
        if arm not in protocol["conditions"]:
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_arm_invalid")
        claim = self._load_event(protocol_digest=protocol_digest, arm=arm,
            event="claim")
        result = self._load_event(protocol_digest=protocol_digest, arm=arm,
            event="result")
        expected = {"protocol_digest": protocol_digest, "arm": arm,
            "authority": False}
        if claim is None:
            if result is not None:
                raise HistoricalExamplesInterventionError(
                    "historical_examples_journal_result_without_claim")
            return {"status": "not_started", **expected}
        if (claim.get("schema_version") !=
                "sentientos.historical_examples_pair_arm_claim:v1"
                or set(claim) != {"schema_version", "protocol_digest", "arm",
                    "invoke_once", "authority"}
                or any(claim.get(key) != value
                    for key, value in expected.items())
                or claim.get("invoke_once") is not True):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_claim_invalid")
        if result is None:
            return {"status": "claimed_without_receipt", "claim": claim,
                **expected}
        binding = result.get("receipt_binding")
        result_schema = result.get("schema_version")
        expected_result_fields = {"schema_version", "protocol_digest", "arm",
            "receipt_binding", "authority"}
        has_archived_receipt = (result_schema ==
            "sentientos.historical_examples_pair_arm_result:v2")
        result_v2_fields = expected_result_fields | {
            "receipt", "runtime_history_inventory"}
        if (result_schema not in {
                "sentientos.historical_examples_pair_arm_result:v1",
                "sentientos.historical_examples_pair_arm_result:v2"}
                or set(result) != (expected_result_fields | (
                    result_v2_fields - expected_result_fields
                    if has_archived_receipt else set()))
                or any(result.get(key) != value
                    for key, value in expected.items())
                or not isinstance(binding, Mapping)
                or set(binding) != {"receipt_id", "receipt_digest", "request_id",
                    "request_digest", "preview_request_digest", "output_digest",
                    "prompt_digest"}):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_result_invalid")
        state = {"status": "completed", "claim": claim,
            "receipt_binding": dict(binding), **expected}
        if has_archived_receipt:
            receipt = result.get("receipt")
            if (not isinstance(receipt, Mapping)
                    or verify_historical_examples_arm_receipt(
                        protocol=protocol, arm=arm, receipt=receipt)
                            != dict(binding)):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_journal_archived_receipt_invalid")
            state["receipt"] = dict(receipt)
            state["runtime_history_inventory"] = (
                _verify_runtime_history_inventory(
                    result.get("runtime_history_inventory"),
                    protocol=protocol))
        return state

    def arm_execution_history(self, *, protocol_digest: str, arm: str) -> dict[str, Any]:
        """Summarize a verified journal state without disclosing a prompt or output."""
        state = self.arm_state(protocol_digest=protocol_digest, arm=arm)
        session = _receipt_session(state.get("receipt"))
        run_id = session.get("run_id")
        preregistration = session.get("preregistration_digest")
        return {
            "status": state["status"],
            "receipt_digest": state.get("receipt_binding", {}).get("receipt_digest"),
            "receipt_run_id": run_id if isinstance(run_id, str) and
                _PAIR_RUN_ID.fullmatch(run_id) else None,
            "run_preregistration_digest": preregistration if
                isinstance(preregistration, str) and _RAW_DIGEST.fullmatch(preregistration)
                and preregistration != "0" * 64 else None,
        }

    def claim_arm(self, *, protocol_digest: str, arm: str) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest=protocol_digest)
        if arm not in protocol["conditions"]:
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_arm_invalid")
        state = self.arm_state(protocol_digest=protocol_digest, arm=arm)
        if state["status"] != "not_started":
            raise HistoricalExamplesInterventionError(
                "historical_examples_arm_already_claimed")
        semantic = {"schema_version":
                "sentientos.historical_examples_pair_arm_claim:v1",
            "protocol_digest": protocol_digest, "arm": arm,
            "invoke_once": True, "authority": False}
        path = self._event_path(protocol_digest=protocol_digest, arm=arm,
            event="claim")
        try:
            created = self._store._write_immutable(path,
                {**semantic, "journal_record_digest": _digest(semantic)})
        except Exception as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_arm_claim_publication_failed") from exc
        if not created:
            raise HistoricalExamplesInterventionError(
                "historical_examples_arm_already_claimed")
        return self.arm_state(protocol_digest=protocol_digest, arm=arm)["claim"]

    def complete_arm(self, *, protocol: Mapping[str, Any], arm: str,
            receipt: Mapping[str, Any],
            runtime_history_inventory: Mapping[str, Any]
            ) -> dict[str, Any]:
        protocol_digest = protocol.get("protocol_digest")
        state = self.arm_state(protocol_digest=protocol_digest, arm=arm)
        if state["status"] not in {"claimed_without_receipt", "completed"}:
            raise HistoricalExamplesInterventionError(
                "historical_examples_arm_claim_required")
        binding = verify_historical_examples_arm_receipt(protocol=protocol,
            arm=arm, receipt=receipt)
        inventory = _verify_runtime_history_inventory(
            runtime_history_inventory, protocol=protocol)
        if state["status"] == "completed":
            if state["receipt_binding"] != binding:
                raise HistoricalExamplesInterventionError(
                    "historical_examples_journal_receipt_collision")
            if ("receipt" in state
                    and dict(state["receipt"]) != dict(receipt)):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_journal_receipt_collision")
            if (state.get("runtime_history_inventory") is not None
                    and state["runtime_history_inventory"] != inventory):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_journal_history_inventory_collision")
            return state["receipt_binding"]
        semantic = {"schema_version":
                "sentientos.historical_examples_pair_arm_result:v2",
            "protocol_digest": protocol_digest, "arm": arm,
            "receipt_binding": binding, "receipt": dict(receipt),
            "runtime_history_inventory": inventory, "authority": False}
        path = self._event_path(protocol_digest=protocol_digest, arm=arm,
            event="result")
        self._publish(path, semantic)
        return dict(binding)

    def _verify_score_from_archived_receipts(self, *,
            protocol: Mapping[str, Any], score: Mapping[str, Any],
            receipts: Mapping[str, Mapping[str, Any]]) -> None:
        if set(receipts) != set(protocol["conditions"]):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_receipt_archive_required")
        task = self.load_task_for_protocol(
            protocol_digest=protocol["protocol_digest"])
        descriptor = task.public_descriptor()
        specification = task.specification()
        if (not isinstance(descriptor, Mapping)
                or not isinstance(specification, Mapping)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_private_task_invalid")
        probes = descriptor.get("probe_inputs")
        multiplier, offset = (specification.get("multiplier"),
            specification.get("offset"))
        if (not isinstance(probes, (list, tuple))
                or type(multiplier) is not int or type(offset) is not int):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_private_task_invalid")
        answer_key = {_digest({
            "schema_version": "sentientos.objective_probe_binding:v1",
            "task_digest": descriptor["task_digest"],
            "probe_index": index, "probe_input": probe,
        }): multiplier * probe + offset
            for index, probe in enumerate(probes)}
        verify_historical_examples_score_artifact(
            score_artifact=score, protocol=protocol,
            answer_key=answer_key, invocation_receipts_by_arm=receipts)

    def persist_score(self, *, protocol_digest: str,
            score: Mapping[str, Any]) -> dict[str, Any]:
        protocol = self.load_protocol(protocol_digest=protocol_digest)
        completed_bindings: dict[str, Mapping[str, Any]] = {}
        completed_receipts: dict[str, Mapping[str, Any]] = {}
        completed_inventories: dict[str, Mapping[str, Any]] = {}
        for arm in protocol["conditions"]:
            state = self.arm_state(protocol_digest=protocol_digest, arm=arm)
            if state["status"] != "completed":
                raise HistoricalExamplesInterventionError(
                    "historical_examples_pair_score_before_all_arms")
            completed_bindings[arm] = state["receipt_binding"]
            if isinstance(state.get("receipt"), Mapping):
                completed_receipts[arm] = state["receipt"]
            if isinstance(state.get("runtime_history_inventory"), Mapping):
                completed_inventories[arm] = state["runtime_history_inventory"]
        if (score.get("schema_version") !=
                "sentientos.historical_examples_intervention_score:v2"
                or score.get("protocol_digest") != protocol_digest
                or score.get("answer_key_digest") != protocol["answer_key_digest"]
                or score.get("owner_prompt_pair_preview_digest") !=
                    protocol["owner_prompt_pair_preview_digest"]
                or score.get("probe_count") != len(
                    protocol["probe_binding_digests"])
                or score.get("invocation_receipt_bindings") !=
                    dict(completed_bindings)
                or score.get("inference_performed") is not True
                or score.get("scoring_posture") !=
                    "same_process_answer_key_and_arm_labeled_receipts"
                or score.get("independent_scorer_attested") is not False
                or score.get("learning_established") is not False
                or score.get("authority") is not False):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_score_invalid")
        score_semantic = {key: item for key, item in score.items()
            if key != "score_digest"}
        if score.get("score_digest") != _digest(score_semantic):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_score_digest_mismatch")
        _verify_runtime_history_inventory_pair(completed_inventories,
            protocol=protocol)
        self._verify_score_from_archived_receipts(protocol=protocol,
            score=score, receipts=completed_receipts)
        semantic = {"schema_version":
                "sentientos.historical_examples_pair_score:v1",
            "protocol_digest": protocol_digest, "score": dict(score),
            "authority": False}
        path = self._event_path(protocol_digest=protocol_digest,
            arm=_ARMS[0], event="score")
        value = self._publish(path, semantic)
        self._verify_record(value,
            code="historical_examples_journal_score_digest_mismatch")
        return dict(value["score"])

    def load_score(self, *, protocol_digest: str) -> dict[str, Any]:
        """Recover a score only after reconstructing it from archived receipts."""
        protocol = self.load_protocol(protocol_digest=protocol_digest)
        completed_bindings: dict[str, Mapping[str, Any]] = {}
        receipts: dict[str, Mapping[str, Any]] = {}
        inventories: dict[str, Mapping[str, Any]] = {}
        for arm in protocol["conditions"]:
            state = self.arm_state(protocol_digest=protocol_digest, arm=arm)
            if state.get("status") != "completed":
                raise HistoricalExamplesInterventionError(
                    "historical_examples_pair_score_before_all_arms")
            completed_bindings[arm] = state["receipt_binding"]
            if isinstance(state.get("receipt"), Mapping):
                receipts[arm] = state["receipt"]
            if isinstance(state.get("runtime_history_inventory"), Mapping):
                inventories[arm] = state["runtime_history_inventory"]
        semantic = self._load_event(protocol_digest=protocol_digest,
            arm=_ARMS[0], event="score")
        if (not isinstance(semantic, Mapping)
                or set(semantic) != {"schema_version", "protocol_digest",
                    "score", "authority"}
                or semantic.get("schema_version") !=
                    "sentientos.historical_examples_pair_score:v1"
                or semantic.get("protocol_digest") != protocol_digest
                or semantic.get("authority") is not False
                or not isinstance(semantic.get("score"), Mapping)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_score_invalid")
        score = dict(semantic["score"])
        score_semantic = {key: item for key, item in score.items()
            if key != "score_digest"}
        if (score.get("schema_version") !=
                "sentientos.historical_examples_intervention_score:v2"
                or score.get("protocol_digest") != protocol_digest
                or score.get("answer_key_digest") != protocol[
                    "answer_key_digest"]
                or score.get("owner_prompt_pair_preview_digest") != protocol[
                    "owner_prompt_pair_preview_digest"]
                or score.get("invocation_receipt_bindings") !=
                    dict(completed_bindings)
                or score.get("score_digest") != _digest(score_semantic)
                or score.get("learning_established") is not False
                or score.get("authority") is not False):
            raise HistoricalExamplesInterventionError(
                "historical_examples_journal_score_binding_invalid")
        _verify_runtime_history_inventory_pair(inventories,
            protocol=protocol)
        self._verify_score_from_archived_receipts(protocol=protocol,
            score=score, receipts=receipts)
        return score


def _digest(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise HistoricalExamplesInterventionError(
            "historical_examples_value_not_canonical_json") from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _verify_runtime_history_inventory(value: Mapping[str, Any], *,
        protocol: Mapping[str, Any]) -> dict[str, Any]:
    if (not isinstance(value, Mapping)
            or set(value) != {"schema_version", "protocol_digest",
                "selected_history_set_digest", "runtime_record_count",
                "runtime_record_set_digest", "before_record_set_digest",
                "after_record_set_digest", "pair_baseline_record_set_digest",
        "runtime_receipt_count", "runtime_receipt_set_digest",
        "before_receipt_set_digest", "after_receipt_set_digest",
        "pair_baseline_receipt_set_digest",
                "stable_within_arm", "selected_records_verified",
                "receipt_record_links_verified",
                "selected_record_receipts_verified", "authority",
                "history_inventory_digest"}
            or value.get("schema_version") !=
                "sentientos.historical_examples_runtime_history_inventory:v2"
            or value.get("protocol_digest") != protocol.get("protocol_digest")
            or value.get("selected_history_set_digest") !=
                protocol.get("history_set_digest")
            or type(value.get("runtime_record_count")) is not int
            or value["runtime_record_count"] < 1
            or type(value.get("runtime_receipt_count")) is not int
            or value["runtime_receipt_count"] < 0
            or value.get("stable_within_arm") is not True
            or value.get("selected_records_verified") is not True
            or value.get("receipt_record_links_verified") is not True
            or value.get("selected_record_receipts_verified") is not True
            or value.get("authority") is not False):
        raise HistoricalExamplesInterventionError(
            "historical_examples_runtime_history_inventory_invalid")
    semantic = {key: item for key, item in value.items()
        if key != "history_inventory_digest"}
    record_digests = [value.get(key) for key in (
        "runtime_record_set_digest", "before_record_set_digest",
        "after_record_set_digest", "pair_baseline_record_set_digest")]
    receipt_digests = [value.get(key) for key in (
        "runtime_receipt_set_digest", "before_receipt_set_digest",
        "after_receipt_set_digest", "pair_baseline_receipt_set_digest")]
    if (any(not isinstance(item, str) or _DIGEST.fullmatch(item) is None
            for item in record_digests + receipt_digests)
            or len(set(record_digests)) != 1
            or len(set(receipt_digests)) != 1
            or value.get("history_inventory_digest") != _digest(semantic)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_runtime_history_inventory_digest_mismatch")
    return dict(value)


def _verify_runtime_history_inventory_pair(values: Mapping[str, Mapping[str, Any]],
        *, protocol: Mapping[str, Any]) -> None:
    if not isinstance(values, Mapping) or set(values) != set(protocol["conditions"]):
        raise HistoricalExamplesInterventionError(
            "historical_examples_runtime_history_inventory_pair_invalid")
    verified = {arm: _verify_runtime_history_inventory(values[arm],
        protocol=protocol) for arm in protocol["conditions"]}
    baseline_digests = {row["pair_baseline_record_set_digest"]
        for row in verified.values()}
    receipt_digests = {row["pair_baseline_receipt_set_digest"]
        for row in verified.values()}
    record_counts = {row["runtime_record_count"] for row in verified.values()}
    receipt_counts = {row["runtime_receipt_count"]
        for row in verified.values()}
    if (len(baseline_digests) != 1 or len(record_counts) != 1
            or len(receipt_digests) != 1 or len(receipt_counts) != 1):
        raise HistoricalExamplesInterventionError(
            "historical_examples_runtime_history_inventory_cross_arm_mismatch")


def _require_digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise HistoricalExamplesInterventionError(code)
    return value


def _normalize_digest(value: Any, code: str) -> str:
    if isinstance(value, str) and _RAW_DIGEST.fullmatch(value) is not None:
        return "sha256:" + value
    return _require_digest(value, code)


def _validate_preview(preview: Mapping[str, Any], *,
        target_model_identity_digest: str, task_digest: str
        ) -> tuple[str, dict[str, str], dict[str, str]]:
    if (preview.get("schema_version") != _PREVIEW_SCHEMA
            or preview.get("condition_id") != "history_present"
            or preview.get("exact_owner_prompts_reconstructed") is not True
            or preview.get("prompt_pair_owner_composition_verified") is not True
            or preview.get("runtime_condition_created") is not False
            or preview.get("inference_performed") is not False
            or preview.get("learning_established") is not False
            or preview.get("authority") is not False
            or preview.get("changed_context_fields") != ["developmental_history"]
            or preview.get("per_record_strategies_unchanged") is not True
            or preview.get("accumulated_strategy_unchanged") is not True
            or type(preview.get("withheld_example_count")) is not int
            or preview.get("withheld_example_count", 0) <= 0
            or type(preview.get("retained_per_record_strategy_count")) is not int
            or preview.get("retained_per_record_strategy_count", -1) < 0
            or preview.get("intervention") !=
                "remove_examples_arrays_from_selected_history_experiences"
            or preview.get("target_model_identity_digest") !=
                target_model_identity_digest
            or preview.get("task_digest") != task_digest):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_invalid")
    preview_digest = _require_digest(preview.get("pair_preview_digest"),
        "historical_examples_owner_preview_digest_invalid")
    semantic = {key: value for key, value in preview.items()
        if key != "pair_preview_digest"}
    if _digest(semantic) != preview_digest:
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_digest_mismatch")

    _normalize_digest(preview.get("snapshot_digest"),
        "historical_examples_owner_preview_binding_invalid")
    for field in ("target_model_identity_digest", "generation_budget_digest", "history_set_digest",
            "baseline_prompt_digest", "ablated_prompt_digest",
            "withheld_examples_digest"):
        _require_digest(preview.get(field),
            "historical_examples_owner_preview_binding_invalid")
    if (not isinstance(preview.get("task_family_id"), str)
            or not preview["task_family_id"]
            or not isinstance(preview.get("snapshot_id"), str)
            or not preview["snapshot_id"]
            or preview["baseline_prompt_digest"] == preview["ablated_prompt_digest"]):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_context_invalid")
    ablation = preview.get("historical_examples_prompt_ablation")
    if (not isinstance(ablation, Mapping)
            or ablation.get("schema_version") !=
                "sentientos.objective_historical_examples_prompt_ablation:v1"
            or ablation.get("intervention") !=
                "remove_examples_arrays_from_selected_history_experiences"
            or ablation.get("changed_context_fields") != ["developmental_history"]
            or ablation.get("baseline_prompt_digest") !=
                preview.get("baseline_prompt_digest")
            or ablation.get("ablated_prompt_digest") !=
                preview.get("ablated_prompt_digest")
            or ablation.get("withheld_examples_digest") !=
                preview.get("withheld_examples_digest")
            or ablation.get("withheld_example_count") !=
                preview.get("withheld_example_count")
            or ablation.get("per_record_strategies_unchanged") is not True
            or ablation.get("accumulated_strategy_unchanged") is not True
            or ablation.get("inference_performed") is not False
            or ablation.get("learning_established") is not False
            or ablation.get("authority") is not False):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_ablation_invalid")

    ids = preview.get("history_record_ids")
    digests = preview.get("history_record_digests")
    if (not isinstance(ids, list) or not ids or len(ids) > 256
            or any(not isinstance(item, str) or not item or len(item) > 256
                for item in ids)
            or len(set(ids)) != len(ids)
            or not isinstance(digests, list) or len(digests) != len(ids)
            or any(_DIGEST.fullmatch(item) is None
                if isinstance(item, str) else True for item in digests)
            or preview["history_set_digest"] != _digest({
                "record_ids": ids, "record_digests": digests})):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_history_invalid")
    if (ablation.get("selected_record_ids") != ids
            or ablation.get("selected_record_digests") != digests
            or ablation.get("selected_record_set_digest") !=
                preview["history_set_digest"]
            or ablation.get("retained_per_record_strategy_count") !=
                preview.get("retained_per_record_strategy_count")):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_ablation_history_mismatch")

    prompts = preview.get("invocation_prompt_digests")
    requests = preview.get("preview_request_digests")
    if (not isinstance(prompts, Mapping) or set(prompts) != set(_ARMS)
            or not isinstance(requests, Mapping) or set(requests) != set(_ARMS)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_requests_invalid")
    prompt_digests = {arm: _require_digest(prompts[arm],
        "historical_examples_prompt_digest_invalid") for arm in _ARMS}
    request_digests = {arm: _require_digest(requests[arm],
        "historical_examples_request_digest_invalid") for arm in _ARMS}
    if (len(set(prompt_digests.values())) != 2
            or len(set(request_digests.values())) != 2
            or prompt_digests[_ARMS[0]] != preview["baseline_prompt_digest"]
            or prompt_digests[_ARMS[1]] != preview["ablated_prompt_digest"]):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_arm_binding_invalid")

    probes = preview.get("probe_binding_digests")
    if (not isinstance(probes, list) or not probes or len(probes) > 128
            or any(not isinstance(value, str)
                or _DIGEST.fullmatch(value) is None for value in probes)
            or len(set(probes)) != len(probes)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_probes_invalid")

    owners = preview.get("owner_protocols")
    if not isinstance(owners, Mapping) or set(owners) != set(_ARMS):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_protocols_invalid")
    ticks: set[str] = set()
    owner_protocol_digests: dict[str, str] = {}
    for arm in _ARMS:
        owner = owners[arm]
        protocol = owner.get("protocol") if isinstance(owner, Mapping) else None
        tick = owner.get("execution_tick_id") if isinstance(owner, Mapping) else None
        owner_ids = protocol.get("record_ids") if isinstance(protocol, Mapping) else None
        owner_record_digests = (protocol.get("record_digests")
            if isinstance(protocol, Mapping) else None)
        owner_budget = (protocol.get("inference_budget")
            if isinstance(protocol, Mapping) else None)
        if (not isinstance(protocol, Mapping)
                or protocol.get("schema_version") not in _OWNER_PROTOCOL_SCHEMAS
                or (protocol.get("schema_version") ==
                    "sentientos.developmental_history_intervention_protocol:v15"
                    and (not isinstance(protocol.get(
                            "authority_map_policy_digest"), str)
                        or _RAW_DIGEST.fullmatch(protocol[
                            "authority_map_policy_digest"]) is None))
                or protocol.get("condition_order") not in
                    (["history_present"], ("history_present",))
                or protocol.get("objective_task_digest") != task_digest
                or protocol.get("snapshot_id") != preview["snapshot_id"]
                or protocol.get("snapshot_digest") != preview["snapshot_digest"]
                or protocol.get("active_model_identity_digest") !=
                    target_model_identity_digest
                or protocol.get("planned_comparisons") not in
                    (["strategy_arm:included"], ("strategy_arm:included",))
                or not isinstance(owner_ids, (list, tuple))
                or list(owner_ids) !=
                    preview["history_record_ids"]
                or not isinstance(owner_record_digests, (list, tuple))
                or list(owner_record_digests) !=
                    preview["history_record_digests"]
                or not isinstance(owner_budget, Mapping)
                or _digest(dict(owner_budget)) !=
                    preview["generation_budget_digest"]
                or protocol.get("condition_order_trial_index") is not None
                or not isinstance(tick, str) or not tick or len(tick) > 256
                or tick in ticks):
            raise HistoricalExamplesInterventionError(
                "historical_examples_owner_protocol_binding_invalid:" + arm)
        ticks.add(tick)
        owner_digest = _require_digest(protocol.get("protocol_digest"),
            "historical_examples_owner_protocol_digest_invalid")
        if (not isinstance(protocol.get("protocol_id"), str)
                or protocol.get("protocol_id") !=
                    "devexp-protocol-" + owner_digest[7:31]):
            raise HistoricalExamplesInterventionError(
                "historical_examples_owner_protocol_id_invalid:" + arm)
        excluded_protocol_fields = {"protocol_id", "protocol_digest",
            "condition_order_trial_index"}
        if protocol.get("schema_version") == (
                "sentientos.developmental_history_intervention_protocol:v15"):
            excluded_protocol_fields.add("authority_map_digest")
        protocol_semantic = {key: value for key, value in protocol.items()
            if key not in excluded_protocol_fields}
        if (_digest(protocol_semantic) != owner_digest
                or owner.get("protocol_digest") != owner_digest
                or owner.get("protocol_id") != protocol.get("protocol_id")
                or not isinstance(owner.get("objective_task_plan_digest"), str)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_owner_protocol_digest_mismatch:" + arm)
        _require_digest(owner["objective_task_plan_digest"],
            "historical_examples_owner_plan_digest_invalid")
        owner_protocol_digests[arm] = owner_digest
    return preview_digest, prompt_digests, request_digests


def verify_historical_examples_probe_history_overlap_audit(
        audit: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the count-and-digest-only exact-overlap preflight proof."""
    fields = {"schema_version", "scope", "history_record_count",
        "history_probe_input_occurrence_count", "history_probe_input_set_digest",
        "task_probe_count", "task_probe_input_digest",
        "overlapping_probe_input_count", "overlapping_probe_input_digest",
        "measurement_complete", "no_exact_overlap_detected",
        "inference_performed", "learning_established", "authority"}
    if (not isinstance(audit, Mapping) or set(audit) != fields
            or audit.get("schema_version") !=
                "sentientos.historical_examples_probe_history_overlap_audit:v1"
            or audit.get("scope") !=
                "all_recursive_input_and_probe_fields_in_all_history_records"
            or type(audit.get("history_record_count")) is not int
            or audit["history_record_count"] <= 0
            or type(audit.get("history_probe_input_occurrence_count")) is not int
            or audit["history_probe_input_occurrence_count"] < 0
            or type(audit.get("task_probe_count")) is not int
            or audit["task_probe_count"] <= 0
            or audit.get("overlapping_probe_input_count") != 0
            or audit.get("measurement_complete") is not True
            or audit.get("no_exact_overlap_detected") is not True
            or audit.get("inference_performed") is not False
            or audit.get("learning_established") is not False
            or audit.get("authority") is not False):
        raise HistoricalExamplesInterventionError(
            "historical_examples_probe_history_overlap_audit_invalid")
    for field in ("history_probe_input_set_digest", "task_probe_input_digest",
            "overlapping_probe_input_digest"):
        _require_digest(audit.get(field),
            "historical_examples_probe_history_overlap_audit_digest_invalid")
    if audit["overlapping_probe_input_digest"] != _digest([]):
        raise HistoricalExamplesInterventionError(
            "historical_examples_probe_history_overlap_digest_not_empty")
    return dict(audit)


def prepare_historical_examples_pair(*, target_model_identity_digest: str,
        task_digest: str, generation_config_digest: str,
        owner_prompt_pair_preview: Mapping[str, Any],
        answer_key: Mapping[str, int],
        private_task_plan_digest: str,
        held_out_probe_overlap_audit_digest: str,
        arm_order: Sequence[str] = _ARMS) -> dict[str, Any]:
    """Create a content-addressed, pre-inference execution protocol."""
    _require_digest(target_model_identity_digest,
        "historical_examples_model_identity_invalid")
    _require_digest(task_digest, "historical_examples_task_digest_invalid")
    _require_digest(generation_config_digest,
        "historical_examples_generation_config_digest_invalid")
    _require_digest(private_task_plan_digest,
        "historical_examples_private_task_plan_digest_invalid")
    _require_digest(held_out_probe_overlap_audit_digest,
        "historical_examples_preflight_audit_digest_invalid")
    if not isinstance(owner_prompt_pair_preview, Mapping):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_preview_invalid")
    preview = owner_prompt_pair_preview
    owner_protocol_field_digests: dict[str, dict[str, str]] = {}
    owner_authority_map_digests: dict[str, str] = {}
    owner_protocols = preview.get("owner_protocols")
    if not isinstance(owner_protocols, Mapping) or set(owner_protocols) != set(_ARMS):
        raise HistoricalExamplesInterventionError(
            "historical_examples_owner_protocol_preview_invalid")
    for arm in _ARMS:
        row = owner_protocols.get(arm)
        owner_protocol = row.get("protocol") if isinstance(row, Mapping) else None
        if (not isinstance(owner_protocol, Mapping)
                or not owner_protocol
                or not isinstance(owner_protocol.get("authority_map_digest"), str)
                or _RAW_DIGEST.fullmatch(owner_protocol[
                    "authority_map_digest"].removeprefix("sha256:")) is None):
            raise HistoricalExamplesInterventionError(
                "historical_examples_owner_protocol_preview_invalid")
        owner_protocol_field_digests[arm] = {
            str(key): _digest(value) for key, value in owner_protocol.items()
            if not (owner_protocol.get("schema_version") ==
                "sentientos.developmental_history_intervention_protocol:v15"
                and key == "authority_map_digest")
            and isinstance(key, str)}
        owner_authority_map_digests[arm] = owner_protocol.get(
            "authority_map_policy_digest") or owner_protocol[
                "authority_map_digest"]
    (preview_digest, prompt_digests, request_digests) = _validate_preview(
        preview, target_model_identity_digest=target_model_identity_digest,
        task_digest=task_digest)
    probes = preview["probe_binding_digests"]
    if (not isinstance(answer_key, Mapping) or set(answer_key) != set(probes)
            or any(type(value) is not int for value in answer_key.values())):
        raise HistoricalExamplesInterventionError(
            "historical_examples_preregistered_answer_key_invalid")
    if not isinstance(arm_order, (list, tuple)) or tuple(arm_order) not in (
            _ARMS, tuple(reversed(_ARMS))):
        raise HistoricalExamplesInterventionError(
            "historical_examples_arm_order_invalid")
    semantic = {
        "schema_version": SCHEMA_VERSION,
        "conditions": list(arm_order),
        "intervention": "remove_raw_history_examples_only",
        "changed_context_fields": ["developmental_history"],
        "target_model_identity_digest": target_model_identity_digest,
        "task_digest": task_digest,
        "private_task_plan_digest": private_task_plan_digest,
        "held_out_probe_overlap_audit_digest":
            held_out_probe_overlap_audit_digest,
        "task_family_id": preview["task_family_id"],
        "snapshot_id": preview["snapshot_id"],
        "snapshot_digest": _normalize_digest(preview["snapshot_digest"],
            "historical_examples_owner_preview_binding_invalid"),
        "generation_budget_digest": preview["generation_budget_digest"],
        "generation_config_digest": generation_config_digest,
        "history_record_ids": list(preview["history_record_ids"]),
        "history_record_digests": list(preview["history_record_digests"]),
        "history_set_digest": preview["history_set_digest"],
        "probe_binding_digests": list(preview["probe_binding_digests"]),
        "answer_key_digest": _digest(dict(answer_key)),
        "withheld_example_count": preview["withheld_example_count"],
        "withheld_examples_digest": preview["withheld_examples_digest"],
        "historical_examples_prompt_ablation": dict(
            preview["historical_examples_prompt_ablation"]),
        "retained_per_record_strategy_count": preview[
            "retained_per_record_strategy_count"],
        "per_record_strategies_unchanged": True,
        "accumulated_strategy_unchanged": True,
        "invocation_prompt_digests": prompt_digests,
        "preview_request_digests": request_digests,
        "owner_execution_tick_ids": {arm: preview["owner_protocols"][arm][
            "execution_tick_id"] for arm in _ARMS},
        "owner_protocol_digests": {arm: preview["owner_protocols"][arm][
            "protocol_digest"] for arm in _ARMS},
        "owner_task_plan_digests": {arm: preview["owner_protocols"][arm][
            "objective_task_plan_digest"] for arm in _ARMS},
        "owner_protocol_field_digests_by_arm": owner_protocol_field_digests,
        "owner_authority_map_digests": owner_authority_map_digests,
        "owner_prompt_pair_preview_digest": preview_digest,
        "owner_prompt_pair_preview_schema": _PREVIEW_SCHEMA,
        "owner_prompt_pair_composition_verified": True,
        "exact_pair_verified": True,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    protocol = {**semantic, "protocol_digest": _digest(semantic)}
    validate_historical_examples_protocol(protocol=protocol,
        target_model_identity_digest=target_model_identity_digest,
        task_digest=task_digest)
    return {"protocol": protocol}


def validate_historical_examples_protocol(*, protocol: Mapping[str, Any],
        target_model_identity_digest: str | None = None,
        task_digest: str | None = None) -> None:
    """Verify a frozen protocol without needing prompts or answer values."""
    if (not isinstance(protocol, Mapping)
            or protocol.get("schema_version") not in {
                SCHEMA_VERSION, _LEGACY_SCHEMA_VERSION}
            or protocol.get("conditions") not in
                (list(_ARMS), list(reversed(_ARMS)))
            or protocol.get("intervention") != "remove_raw_history_examples_only"
            or protocol.get("changed_context_fields") != ["developmental_history"]
            or protocol.get("owner_prompt_pair_preview_schema") != _PREVIEW_SCHEMA
            or protocol.get("owner_prompt_pair_composition_verified") is not True
            or protocol.get("per_record_strategies_unchanged") is not True
            or protocol.get("accumulated_strategy_unchanged") is not True
            or protocol.get("exact_pair_verified") is not True
            or protocol.get("inference_performed") is not False
            or protocol.get("learning_established") is not False
            or protocol.get("authority") is not False):
        raise HistoricalExamplesInterventionError(
            "historical_examples_protocol_invalid")
    semantic = {key: value for key, value in protocol.items()
        if key != "protocol_digest"}
    digest = _require_digest(protocol.get("protocol_digest"),
        "historical_examples_protocol_digest_invalid")
    if digest != _digest(semantic):
        raise HistoricalExamplesInterventionError(
            "historical_examples_protocol_digest_mismatch")
    for field in ("target_model_identity_digest", "task_digest",
            "snapshot_digest", "generation_budget_digest",
            "generation_config_digest", "history_set_digest",
            "owner_prompt_pair_preview_digest", "withheld_examples_digest",
            "private_task_plan_digest", "held_out_probe_overlap_audit_digest",
            "answer_key_digest"):
        _require_digest(protocol.get(field),
            "historical_examples_protocol_binding_invalid")
    if (type(protocol.get("withheld_example_count")) is not int
            or protocol["withheld_example_count"] <= 0
            or type(protocol.get("retained_per_record_strategy_count")) is not int
            or protocol["retained_per_record_strategy_count"] < 0):
        raise HistoricalExamplesInterventionError(
            "historical_examples_protocol_summary_invalid")
    if ((target_model_identity_digest is not None and protocol.get(
            "target_model_identity_digest") != target_model_identity_digest)
            or (task_digest is not None and protocol.get("task_digest") != task_digest)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_protocol_expected_binding_mismatch")
    for field in ("owner_protocol_digests", "owner_task_plan_digests"):
        bindings = protocol.get(field)
        if (not isinstance(bindings, Mapping) or set(bindings) != set(_ARMS)
                or any(not isinstance(value, str)
                    or _DIGEST.fullmatch(value) is None
                    for value in bindings.values())):
            raise HistoricalExamplesInterventionError(
                "historical_examples_protocol_owner_bindings_invalid")
    if protocol.get("schema_version") == SCHEMA_VERSION:
        field_bindings = protocol.get("owner_protocol_field_digests_by_arm")
        authority_bindings = protocol.get("owner_authority_map_digests")
        if (not isinstance(field_bindings, Mapping)
                or set(field_bindings) != set(_ARMS)
                or not isinstance(authority_bindings, Mapping)
                or set(authority_bindings) != set(_ARMS)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_protocol_owner_field_bindings_invalid")
        for arm in _ARMS:
            fields = field_bindings.get(arm)
            if (not isinstance(fields, Mapping) or not fields
                    or not ("authority_map_policy_digest" in fields
                        or "authority_map_digest" in fields)
                    or any(not isinstance(key, str) or not key
                        or not isinstance(value, str)
                        or _DIGEST.fullmatch(value) is None
                        for key, value in fields.items())
                    or not isinstance(authority_bindings.get(arm), str)
                    or _RAW_DIGEST.fullmatch(authority_bindings[arm].removeprefix(
                        "sha256:")) is None
                    or fields.get("authority_map_policy_digest",
                        fields.get("authority_map_digest")) != _digest(
                            authority_bindings[arm])):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_protocol_owner_field_bindings_invalid")
    execution_ticks = protocol.get("owner_execution_tick_ids")
    if (not isinstance(execution_ticks, Mapping)
            or set(execution_ticks) != set(_ARMS)
            or any(not isinstance(value, str) or not value or len(value) > 256
                for value in execution_ticks.values())
            or len(set(execution_ticks.values())) != len(_ARMS)
            or not isinstance(protocol.get("task_family_id"), str)
            or not protocol["task_family_id"]
            or not isinstance(protocol.get("snapshot_id"), str)
            or not protocol["snapshot_id"]):
        raise HistoricalExamplesInterventionError(
            "historical_examples_protocol_execution_bindings_invalid")
    prompts = protocol.get("invocation_prompt_digests")
    requests = protocol.get("preview_request_digests")
    if (not isinstance(prompts, Mapping) or set(prompts) != set(_ARMS)
            or not isinstance(requests, Mapping) or set(requests) != set(_ARMS)
            or any(_DIGEST.fullmatch(value) is None
                if isinstance(value, str) else True for value in prompts.values())
            or any(_DIGEST.fullmatch(value) is None
                if isinstance(value, str) else True for value in requests.values())
            or len(set(prompts.values())) != 2
            or len(set(requests.values())) != 2):
        raise HistoricalExamplesInterventionError(
            "historical_examples_protocol_arm_bindings_invalid")
    ids = protocol.get("history_record_ids")
    digests = protocol.get("history_record_digests")
    probes = protocol.get("probe_binding_digests")
    if (not isinstance(ids, list) or not ids
            or any(not isinstance(value, str) or not value for value in ids)
            or len(ids) != len(set(ids))
            or not isinstance(digests, list) or len(digests) != len(ids)
            or any(_DIGEST.fullmatch(value) is None
                if isinstance(value, str) else True for value in digests)
            or protocol.get("history_set_digest") != _digest({
                "record_ids": ids, "record_digests": digests})
            or not isinstance(probes, list) or not probes
            or any(not isinstance(value, str)
                or _DIGEST.fullmatch(value) is None for value in probes)
            or len(probes) != len(set(probes))
            ):
        raise HistoricalExamplesInterventionError(
            "historical_examples_protocol_history_or_probe_binding_invalid")
    ablation = protocol.get("historical_examples_prompt_ablation")
    if (not isinstance(ablation, Mapping)
            or ablation.get("schema_version") !=
                "sentientos.objective_historical_examples_prompt_ablation:v1"
            or ablation.get("baseline_prompt_digest") != prompts.get(
                "examples_included")
            or ablation.get("ablated_prompt_digest") != prompts.get(
                "examples_omitted")
            or ablation.get("selected_record_ids") != ids
            or ablation.get("selected_record_digests") != digests
            or ablation.get("withheld_examples_digest") !=
                protocol.get("withheld_examples_digest")
            or ablation.get("withheld_example_count") !=
                protocol.get("withheld_example_count")
            or ablation.get("changed_context_fields") != ["developmental_history"]
            or ablation.get("per_record_strategies_unchanged") is not True
            or ablation.get("accumulated_strategy_unchanged") is not True
            or ablation.get("inference_performed") is not False
            or ablation.get("learning_established") is not False
            or ablation.get("authority") is not False):
        raise HistoricalExamplesInterventionError(
            "historical_examples_protocol_ablation_binding_invalid")


def _output_schema_contract(schema: Any, probe_count: int) -> tuple[bool, bool]:
    """Validate the exact objective answer shape carried by the receipt."""
    if (not isinstance(schema, Mapping) or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or not isinstance(schema.get("properties"), Mapping)
            or not isinstance(schema.get("required"), list)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_receipt_output_schema_invalid")
    props, required = schema["properties"], schema["required"]
    if (set(props) not in ({"answers"}, {"answers", "confidence_basis_points"})
            or set(required) != set(props) or len(required) != len(set(required))
            or "answers" not in required):
        raise HistoricalExamplesInterventionError(
            "historical_examples_receipt_output_schema_invalid")
    answers = props.get("answers")
    if (not isinstance(answers, Mapping) or answers.get("type") != "array"
            or answers.get("minItems") != probe_count
            or answers.get("maxItems") != probe_count):
        raise HistoricalExamplesInterventionError(
            "historical_examples_receipt_answer_schema_invalid")
    item_schema = answers.get("items")
    item_types = ({item.get("type") for item in item_schema.get("anyOf", ())
        if isinstance(item, Mapping)} if isinstance(item_schema, Mapping)
        and isinstance(item_schema.get("anyOf"), list) else
        {item_schema.get("type")} if isinstance(item_schema, Mapping) else set())
    if "integer" not in item_types or item_types - {"integer", "null"}:
        raise HistoricalExamplesInterventionError(
            "historical_examples_receipt_answer_schema_invalid")
    include_confidence = "confidence_basis_points" in props
    if include_confidence:
        conf = props["confidence_basis_points"]
        if (not isinstance(conf, Mapping) or conf.get("type") != "array"
                or conf.get("minItems") != probe_count
                or conf.get("maxItems") != probe_count):
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_confidence_schema_invalid")
        conf_items = conf.get("items")
        conf_schemas = (conf_items.get("anyOf", ())
            if isinstance(conf_items, Mapping) else ())
        conf_types = {item.get("type") for item in conf_schemas
            if isinstance(item, Mapping)} if isinstance(conf_schemas, list) else set()
        if (not isinstance(conf_items, Mapping)
                or not isinstance(conf_schemas, list)
                or not any(isinstance(item, Mapping)
                    and item.get("type") == "integer"
                    and item.get("minimum") == 0
                    and item.get("maximum") == 10000 for item in conf_schemas)
                or any(isinstance(item, Mapping)
                    and item.get("type") not in {"integer", "null"}
                    for item in conf_schemas)
                or ("null" in item_types) != ("null" in conf_types)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_confidence_schema_invalid")
    return "null" in item_types, include_confidence


def _normalize_probe_values(value: Any, probes: Sequence[str], *,
        allow_null: bool) -> dict[str, int | None]:
    if isinstance(value, list) and len(value) == len(probes):
        values = dict(zip(probes, value))
    elif isinstance(value, Mapping) and set(value) == set(probes):
        values = dict(value)
    else:
        raise HistoricalExamplesInterventionError(
            "historical_examples_output_values_invalid")
    if (any(item is not None and type(item) is not int
            for item in values.values())
            or (not allow_null and any(item is None for item in values.values()))):
        raise HistoricalExamplesInterventionError(
            "historical_examples_output_values_invalid")
    return values


def _reject_non_json_constant(value: str) -> Any:
    raise ValueError("nonstandard_json_constant:" + value)


def verify_historical_examples_arm_receipt(*, protocol: Mapping[str, Any],
        arm: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Verify one arm's governed request binding before the other arm runs."""
    validate_historical_examples_protocol(protocol=protocol)
    if (arm not in _ARMS or arm not in protocol["conditions"]
            or not isinstance(receipt, Mapping)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_arm_receipt_invalid")
    valid, reasons = validate_receipt(receipt)
    if not valid:
        raise HistoricalExamplesInterventionError(
            "historical_examples_arm_receipt_invalid:" + ",".join(reasons))
    request = receipt.get("request")
    effects = receipt.get("effects")
    identity = request.get("active_model_identity") if isinstance(
        request, Mapping) else None
    upstream = request.get("upstream_evidence") if isinstance(
        request, Mapping) else None
    linkage = request.get("linkage") if isinstance(request, Mapping) else None
    prompt_digest = protocol["invocation_prompt_digests"][arm].removeprefix(
        "sha256:")
    request_digest = (request.get("request_digest")
        if isinstance(request, Mapping) else None)
    expected_ablation = (protocol["historical_examples_prompt_ablation"]
        if arm == "examples_omitted" else None)
    if (receipt.get("status") != "admitted_completed"
            or receipt.get("output_truncated") is not False
            or receipt.get("fallback_occurred") is not False
            or not isinstance(effects, Mapping)
            or effects.get("local_model_inference") is not True
            or not isinstance(request, Mapping)
            or request.get("prompt_digest") != prompt_digest
            or not isinstance(request_digest, str)
            or _RAW_DIGEST.fullmatch(request_digest) is None
            or request.get("expected_output_format") != "json"
            or not isinstance(receipt.get("generation_config"), Mapping)
            or _digest(dict(receipt["generation_config"])) !=
                protocol["generation_config_digest"]
            or not isinstance(identity, Mapping)
            or _digest(dict(identity)) != protocol["target_model_identity_digest"]
            or not isinstance(upstream, Mapping)
            or upstream.get("objective_task_digest") != protocol["task_digest"]
            or upstream.get("objective_task_plan_digest") !=
                protocol["owner_task_plan_digests"][arm]
            or upstream.get("historical_examples_prompt_ablation")
                != expected_ablation
            or not isinstance(linkage, Mapping)
            or linkage.get("condition_id") != "history_present"
            or linkage.get("history_present") is not True
            or linkage.get("condition_group") != protocol[
                "owner_execution_tick_ids"][arm] + ":retrieval-comparison"
            or not isinstance(request.get("budget"), Mapping)
            or _digest(dict(request["budget"])) !=
                protocol["generation_budget_digest"]):
        raise HistoricalExamplesInterventionError(
            "historical_examples_arm_receipt_binding_mismatch:" + arm)
    output_text = receipt.get("output_text")
    if not isinstance(output_text, str):
        raise HistoricalExamplesInterventionError(
            "historical_examples_arm_receipt_output_missing:" + arm)
    try:
        decoded = json.loads(output_text, parse_constant=_reject_non_json_constant)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HistoricalExamplesInterventionError(
            "historical_examples_arm_receipt_output_invalid:" + arm) from exc
    if not isinstance(decoded, Mapping):
        raise HistoricalExamplesInterventionError(
            "historical_examples_arm_receipt_output_invalid:" + arm)
    probes = protocol["probe_binding_digests"]
    allow_abstention, include_confidence = _output_schema_contract(
        request.get("structured_output_schema"), len(probes))
    expected_fields = ({"answers", "confidence_basis_points"}
        if include_confidence else {"answers"})
    if set(decoded) != expected_fields:
        raise HistoricalExamplesInterventionError(
            "historical_examples_arm_receipt_output_shape_invalid:" + arm)
    answers = _normalize_probe_values(decoded["answers"], probes,
        allow_null=allow_abstention)
    if include_confidence:
        confidence = _normalize_probe_values(
            decoded["confidence_basis_points"], probes, allow_null=True)
        if (any(value is not None and not 0 <= value <= 10000
                for value in confidence.values())
                or any((answers[probe] is None) !=
                    (confidence[probe] is None) for probe in probes)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_arm_receipt_confidence_invalid:" + arm)
    return {"receipt_id": receipt.get("receipt_id"),
        "receipt_digest": receipt.get("receipt_digest"),
        "request_id": request.get("request_id"),
        "request_digest": request.get("request_digest"),
        "preview_request_digest": protocol["preview_request_digests"][arm],
        "prompt_digest": request.get("prompt_digest"),
        "output_digest": receipt.get("output_digest")}


def score_verified_historical_examples_pair(*, protocol: Mapping[str, Any],
        answer_key: Mapping[str, int],
        invocation_receipts_by_arm: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Verify two governed receipts and emit answer-free paired score evidence."""
    validate_historical_examples_protocol(protocol=protocol)
    if (not isinstance(invocation_receipts_by_arm, Mapping)
            or set(invocation_receipts_by_arm) != set(_ARMS)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_receipts_invalid")
    probes = protocol["probe_binding_digests"]
    if (not isinstance(answer_key, Mapping) or set(answer_key) != set(probes)
            or any(type(value) is not int for value in answer_key.values())):
        raise HistoricalExamplesInterventionError(
            "historical_examples_answer_key_invalid")
    if _digest(dict(answer_key)) != protocol["answer_key_digest"]:
        raise HistoricalExamplesInterventionError(
            "historical_examples_answer_key_digest_mismatch")

    outcomes: dict[str, list[dict[str, Any]]] = {}
    receipt_bindings: dict[str, dict[str, Any]] = {}
    confidence_sums: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    correct_counts: dict[str, int] = {}
    answered_counts: dict[str, int] = {}
    prompt_bindings = protocol["invocation_prompt_digests"]
    request_bindings = protocol["preview_request_digests"]

    for arm in _ARMS:
        receipt = invocation_receipts_by_arm[arm]
        if not isinstance(receipt, Mapping):
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_invalid:" + arm)
        valid, reasons = validate_receipt(receipt)
        if not valid:
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_invalid:" + arm + ":"
                    + ",".join(reasons))
        request = receipt.get("request")
        effects = receipt.get("effects")
        identity = request.get("active_model_identity") if isinstance(
            request, Mapping) else None
        upstream = request.get("upstream_evidence") if isinstance(
            request, Mapping) else None
        linkage = request.get("linkage") if isinstance(request, Mapping) else None
        expected_ablation = (protocol["historical_examples_prompt_ablation"]
            if arm == "examples_omitted" else None)
        task_family_projection = (upstream.get(
            "task_family_history_prompt_projection")
            if isinstance(upstream, Mapping) else None)
        if (receipt.get("status") != "admitted_completed"
                or receipt.get("output_truncated") is not False
                or receipt.get("fallback_occurred") is not False
                or not isinstance(effects, Mapping)
                or effects.get("local_model_inference") is not True
                or not isinstance(request, Mapping)
                or request.get("prompt_digest") !=
                    prompt_bindings[arm].removeprefix("sha256:")
                or not isinstance(request.get("request_digest"), str)
                or _RAW_DIGEST.fullmatch(request["request_digest"]) is None
                or request.get("expected_output_format") != "json"
                or not isinstance(identity, Mapping)
                or _digest(dict(identity)) !=
                    protocol["target_model_identity_digest"]
                or not isinstance(upstream, Mapping)
                or upstream.get("objective_task_digest") != protocol["task_digest"]
                or upstream.get("objective_task_plan_digest") !=
                    protocol["owner_task_plan_digests"][arm]
                or upstream.get("historical_examples_prompt_ablation")
                    != expected_ablation
                or not isinstance(linkage, Mapping)
                or linkage.get("condition_id") != "history_present"
                or linkage.get("history_present") is not True
                or linkage.get("condition_group") != protocol[
                    "owner_execution_tick_ids"][arm] + ":retrieval-comparison"
                or not isinstance(request.get("budget"), Mapping)
                or _digest(dict(request["budget"])) !=
                    protocol["generation_budget_digest"]
                or not isinstance(receipt.get("generation_config"), Mapping)
                or _digest(dict(receipt["generation_config"])) !=
                    protocol["generation_config_digest"]
                or not isinstance(receipt.get("output_text"), str)
                or not isinstance(receipt.get("output_digest"), str)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_binding_mismatch:" + arm)
        if arm == "examples_omitted":
            projection_semantic = ({key: value for key, value in
                task_family_projection.items() if key != "projection_digest"}
                if isinstance(task_family_projection, Mapping) else {})
            if (not isinstance(task_family_projection, Mapping)
                    or task_family_projection.get("schema_version") !=
                        "sentientos.task_family_history_prompt_projection:v36"
                    or task_family_projection.get(
                        "governed_request_prompt_digest")
                            != request.get("prompt_digest")
                    or task_family_projection.get(
                        "historical_examples_prompt_ablation")
                            != expected_ablation
                    or not isinstance(task_family_projection.get(
                        "projection_digest"), str)
                    or _DIGEST.fullmatch(task_family_projection[
                        "projection_digest"]) is None
                    or _digest(projection_semantic) !=
                        task_family_projection["projection_digest"]):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_receipt_projection_mismatch")
        try:
            decoded = json.loads(receipt["output_text"],
                parse_constant=_reject_non_json_constant)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_output_json_invalid:" + arm) from exc
        if not isinstance(decoded, Mapping):
            raise HistoricalExamplesInterventionError(
                "historical_examples_output_object_invalid:" + arm)
        allow_abstention, include_confidence = _output_schema_contract(
            request.get("structured_output_schema"), len(probes))
        expected_fields = ({"answers", "confidence_basis_points"}
            if include_confidence else {"answers"})
        if set(decoded) != expected_fields:
            raise HistoricalExamplesInterventionError(
                "historical_examples_output_shape_invalid:" + arm)
        predictions = _normalize_probe_values(decoded["answers"], probes,
            allow_null=allow_abstention)
        confidences: dict[str, int | None] = {}
        if include_confidence:
            confidences = _normalize_probe_values(
                decoded["confidence_basis_points"], probes, allow_null=True)
            if (any(value is not None and not 0 <= value <= 10000
                    for value in confidences.values())
                    or any((predictions[probe] is None)
                        != (confidences[probe] is None) for probe in probes)):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_output_confidence_invalid:" + arm)
        rows: list[dict[str, Any]] = []
        confidence_sum = 0
        for probe in probes:
            prediction = predictions[probe]
            correct = prediction is not None and prediction == answer_key[probe]
            row: dict[str, Any] = {"probe_binding_digest": probe,
                "outcome": ("abstained" if prediction is None else
                    "correct" if correct else "incorrect")}
            confidence = confidences.get(probe)
            if confidence is not None:
                target = 10000 if correct else 0
                error = (confidence - target) ** 2
                confidence_sum += error
                row["brier_squared_error_basis_points_squared"] = error
            rows.append(row)
        outcomes[arm] = rows
        confidence_sums[arm] = confidence_sum
        confidence_counts[arm] = sum(value is not None
            for value in confidences.values())
        correct_counts[arm] = sum(row["outcome"] == "correct" for row in rows)
        answered_counts[arm] = sum(row["outcome"] != "abstained" for row in rows)
        receipt_bindings[arm] = {
            "receipt_id": receipt.get("receipt_id"),
            "receipt_digest": receipt.get("receipt_digest"),
            "request_id": request.get("request_id"),
            "request_digest": request.get("request_digest"),
            "preview_request_digest": request_bindings[arm],
            "prompt_digest": request.get("prompt_digest"),
            "output_digest": receipt.get("output_digest"),
        }

    paired = [{"probe_binding_digest": probe,
        "examples_included": outcomes["examples_included"][index]["outcome"],
        "examples_omitted": outcomes["examples_omitted"][index]["outcome"]}
        for index, probe in enumerate(probes)]
    semantic = {
        "schema_version": "sentientos.historical_examples_intervention_score:v2",
        "protocol_digest": protocol["protocol_digest"],
        "answer_key_digest": _digest(dict(answer_key)),
        "probe_count": len(probes),
        "outcomes_by_arm": outcomes,
        "paired_probe_outcomes": paired,
        "correct_counts": correct_counts,
        "answered_counts": answered_counts,
        "coverage_basis_points": {arm: answered_counts[arm] * 10000 // len(probes)
            for arm in _ARMS},
        "confidence_brier_squared_error_sums": confidence_sums,
        "confidence_scored_counts": confidence_counts,
        "invocation_receipt_bindings": receipt_bindings,
        "owner_prompt_pair_preview_digest":
            protocol["owner_prompt_pair_preview_digest"],
        "paired_delivery_verified": True,
        "inference_performed": True,
        "scoring_posture":
            "same_process_answer_key_and_arm_labeled_receipts",
        "independent_scorer_attested": False,
        "learning_established": False,
        "authority": False,
    }
    return {**semantic, "score_digest": _digest(semantic)}




def verify_historical_examples_score_artifact(*, score_artifact: Mapping[str, Any],
        protocol: Mapping[str, Any], answer_key: Mapping[str, int],
        invocation_receipts_by_arm: Mapping[str, Mapping[str, Any]]) -> None:
    """Reconstruct and verify a saved answer-free score artifact exactly.

    This read-only CPU check binds a saved score back to the frozen protocol,
    preregistered answer key, and both original governed invocation receipts.
    """
    if not isinstance(score_artifact, Mapping):
        raise HistoricalExamplesInterventionError(
            "historical_examples_score_artifact_invalid")
    reconstructed = score_verified_historical_examples_pair(
        protocol=protocol, answer_key=answer_key,
        invocation_receipts_by_arm=invocation_receipts_by_arm)
    if dict(score_artifact) != reconstructed:
        raise HistoricalExamplesInterventionError(
            "historical_examples_score_artifact_reconstruction_mismatch")


def derive_historical_examples_objective_request_bindings(*,
        protocol: Mapping[str, Any], objective_task: Any
        ) -> dict[str, dict[str, str]]:
    """Derive stable staging request identities from the frozen pair and task."""
    if (not callable(getattr(objective_task, "specification", None))
            or not callable(getattr(objective_task, "public_descriptor", None))):
        raise HistoricalExamplesInterventionError(
            "historical_examples_resident_executor_task_invalid")
    descriptor = objective_task.public_descriptor()
    if (not isinstance(descriptor, Mapping)
            or not isinstance(descriptor.get("task_digest"), str)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_resident_executor_task_invalid")
    validate_historical_examples_protocol(protocol=protocol,
        task_digest=descriptor["task_digest"])
    from sentientos.resident_developmental_cognition import (
        objective_request_payload,
    )
    result: dict[str, dict[str, str]] = {}
    for arm in _ARMS:
        request_id = ("historical-examples:" +
            protocol["protocol_digest"].removeprefix("sha256:") + ":" + arm)
        request = objective_request_payload(
            request_id=request_id, task=objective_task)
        result[arm] = {"request_id": request_id,
            "request_digest": request["request_digest"]}
    return result


def build_resident_historical_examples_arm_executor(*, owner: Any,
        snapshot: Any, objective_task: Any
        ) -> Callable[[str, Mapping[str, Any]], HistoricalExamplesArmExecution]:
    """Adapt a resident owner to the one-call-per-arm frozen protocol API."""
    if (not callable(getattr(owner, "run_objective_intervention_once", None))
            or not callable(getattr(owner, "verified_cognition_observation", None))
            or not callable(getattr(owner,
                "verified_cognition_invocation_receipt", None))
            or not callable(getattr(objective_task, "specification", None))
            or not callable(getattr(objective_task, "public_descriptor", None))):
        raise HistoricalExamplesInterventionError(
            "historical_examples_resident_executor_dependencies_invalid")

    history_store = getattr(getattr(owner, "writeback", None), "store", None)
    read_history_records = getattr(history_store, "records", None)
    read_history_receipts = getattr(history_store, "receipts", None)
    composition_lock = getattr(owner, "_composition_lock", None)
    if (not callable(read_history_records)
            or not callable(read_history_receipts)
            or not callable(composition_lock)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_resident_history_inventory_unavailable")
    baseline_history_inventory: dict[str, str] | None = None

    def observe_history_inventory(protocol: Mapping[str, Any]) -> dict[str, Any]:
        nonlocal baseline_history_inventory
        try:
            with composition_lock():
                records = read_history_records()
                receipts = read_history_receipts()
        except Exception as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_history_or_receipt_inventory_failed") from exc
        if not isinstance(records, (list, tuple)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_history_inventory_invalid")
        digests_by_id: dict[str, str] = {}
        rows: list[dict[str, str]] = []
        for record in records:
            record_id = getattr(record, "record_id", None)
            record_digest = getattr(record, "record_digest", None)
            if (not isinstance(record_id, str) or not record_id
                    or not isinstance(record_digest, str)
                    or record_id in digests_by_id):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_resident_history_inventory_invalid")
            digest = _normalize_digest(record_digest,
                "historical_examples_resident_history_inventory_invalid")
            digests_by_id[record_id] = digest
            rows.append({"record_id": record_id, "record_digest": digest})
        expected_ids = protocol.get("history_record_ids")
        expected_digests = protocol.get("history_record_digests")
        if (not isinstance(expected_ids, list)
                or not isinstance(expected_digests, list)
                or len(expected_ids) != len(expected_digests)
                or any(digests_by_id.get(record_id) != record_digest
                    for record_id, record_digest in zip(
                        expected_ids, expected_digests, strict=True))):
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_history_protocol_binding_mismatch")
        inventory = _digest(sorted(rows, key=lambda row: row["record_id"]))
        if not isinstance(receipts, (list, tuple)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_receipt_inventory_invalid")
        receipt_digests_by_id: dict[str, str] = {}
        receipt_rows: list[dict[str, str]] = []
        receipt_record_ids: set[str] = set()
        for receipt in receipts:
            receipt_id = getattr(receipt, "receipt_id", None)
            receipt_digest = getattr(receipt, "receipt_digest", None)
            if (not isinstance(receipt_id, str) or not receipt_id
                    or not isinstance(receipt_digest, str)
                    or receipt_id in receipt_digests_by_id):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_resident_receipt_inventory_invalid")
            digest = _normalize_digest(receipt_digest,
                "historical_examples_resident_receipt_inventory_invalid")
            record_id = getattr(receipt, "record_id", None)
            record_digest = getattr(receipt, "record_digest", None)
            if not isinstance(record_id, str):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_resident_receipt_record_binding_invalid")
            linked_record_digest = _normalize_digest(record_digest,
                "historical_examples_resident_receipt_record_binding_invalid")
            if digests_by_id.get(record_id) != linked_record_digest:
                raise HistoricalExamplesInterventionError(
                    "historical_examples_resident_receipt_record_binding_invalid")
            receipt_record_ids.add(record_id)
            receipt_digests_by_id[receipt_id] = digest
            receipt_rows.append({"receipt_id": receipt_id,
                "receipt_digest": digest})
        if not set(expected_ids).issubset(receipt_record_ids):
            raise HistoricalExamplesInterventionError(
                "historical_examples_selected_history_receipts_missing")
        receipt_inventory = _digest(sorted(receipt_rows,
            key=lambda row: row["receipt_id"]))
        if baseline_history_inventory is None:
            baseline_history_inventory = {"record": inventory,
                "receipt": receipt_inventory}
        elif (inventory != baseline_history_inventory["record"]
                or receipt_inventory != baseline_history_inventory["receipt"]):
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_history_mutated_during_pair")
        return {"runtime_record_count": len(rows),
            "runtime_record_set_digest": inventory,
            "runtime_receipt_count": len(receipt_rows),
            "runtime_receipt_set_digest": receipt_inventory}

    def execute(arm: str, protocol: Mapping[str, Any]) -> Mapping[str, Any]:
        if (arm not in _ARMS or not isinstance(protocol, Mapping)
                or arm not in protocol.get("conditions", ())):
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_executor_arm_invalid")
        validate_historical_examples_protocol(protocol=protocol)
        before_history_inventory = observe_history_inventory(protocol)
        request_bindings = derive_historical_examples_objective_request_bindings(
            protocol=protocol, objective_task=objective_task)
        tick_ids = protocol["owner_execution_tick_ids"]
        history_record_ids = protocol.get("history_record_ids")
        if (not isinstance(history_record_ids, list) or not history_record_ids
                or any(not isinstance(record_id, str) or not record_id
                    for record_id in history_record_ids)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_history_allowlist_invalid")
        request_id = request_bindings[arm]["request_id"]
        try:
            result = owner.run_objective_intervention_once(
                snapshot=snapshot, tick_id=tick_ids[arm],
                objective_task=objective_task, request_id=request_id,
                request_digest=request_bindings[arm]["request_digest"],
                history_record_allowlist=tuple(history_record_ids),
                accumulated_strategy_inclusion="included",
                historical_examples_condition=arm,
                historical_examples_protocol=protocol)
        finally:
            after_history_inventory = observe_history_inventory(protocol)
            if after_history_inventory != before_history_inventory:
                raise HistoricalExamplesInterventionError(
                    "historical_examples_resident_history_mutated_during_pair")
        observation_ids = getattr(result, "cognition_observation_ids", ())
        if (getattr(result, "status", None) != "objective_strategy_arm_completed"
                or getattr(result, "tick_id", None) != tick_ids[arm]
                or not isinstance(observation_ids, (list, tuple))
                or len(observation_ids) != 1
                or not isinstance(observation_ids[0], str)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_executor_result_invalid")
        observation = owner.verified_cognition_observation(observation_ids[0])
        observed_request_digest = observation.get("request_digest")
        if (observation.get("tick_id") != tick_ids[arm]
                or observation.get("condition_id") != "history_present"
                or observation.get("observation_id") != observation_ids[0]
                or not isinstance(observed_request_digest, str)
                or _RAW_DIGEST.fullmatch(observed_request_digest) is None
                or not isinstance(observation.get("observation_digest"), str)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_executor_observation_invalid")
        receipt = owner.verified_cognition_invocation_receipt(
            observation_ids[0], observation["observation_digest"])
        receipt_request = (receipt.get("request")
            if isinstance(receipt, Mapping) else None)
        if (not isinstance(receipt, Mapping)
                or not isinstance(receipt_request, Mapping)
                or receipt_request.get("request_digest") !=
                    observed_request_digest):
            raise HistoricalExamplesInterventionError(
                "historical_examples_resident_executor_receipt_invalid")
        verify_historical_examples_arm_receipt(protocol=protocol, arm=arm,
            receipt=receipt)
        inventory_semantic = {
            "schema_version":
                "sentientos.historical_examples_runtime_history_inventory:v2",
            "protocol_digest": protocol["protocol_digest"],
            "selected_history_set_digest": protocol["history_set_digest"],
            **before_history_inventory,
            "before_record_set_digest": before_history_inventory[
                "runtime_record_set_digest"],
            "after_record_set_digest": after_history_inventory[
                "runtime_record_set_digest"],
            "pair_baseline_record_set_digest": baseline_history_inventory[
                "record"],
            "before_receipt_set_digest": before_history_inventory[
                "runtime_receipt_set_digest"],
            "after_receipt_set_digest": after_history_inventory[
                "runtime_receipt_set_digest"],
            "pair_baseline_receipt_set_digest": baseline_history_inventory[
                "receipt"],
            "stable_within_arm": True, "selected_records_verified": True,
            "receipt_record_links_verified": True,
            "selected_record_receipts_verified": True,
            "authority": False}
        runtime_inventory = {**inventory_semantic,
            "history_inventory_digest": _digest(inventory_semantic)}
        return HistoricalExamplesArmExecution(receipt=dict(receipt),
            runtime_history_inventory=runtime_inventory)

    return execute


def build_resident_historical_examples_receipt_loader(*, owner: Any
        ) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """Resolve a journaled receipt binding through verified resident observations."""
    recover = getattr(owner, "_recover_observation_ticks", None)
    read_receipt = getattr(owner, "verified_cognition_invocation_receipt", None)
    if not callable(recover) or not callable(read_receipt):
        raise HistoricalExamplesInterventionError(
            "historical_examples_receipt_loader_dependencies_invalid")

    def load(binding: Mapping[str, Any]) -> Mapping[str, Any]:
        if (not isinstance(binding, Mapping)
                or not isinstance(binding.get("receipt_id"), str)
                or not isinstance(binding.get("receipt_digest"), str)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_loader_binding_invalid")
        try:
            observations = recover(include_records=True)
        except Exception as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_loader_recovery_failed") from exc
        if not isinstance(observations, Mapping):
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_loader_observations_invalid")
        matches = [observation for observation in observations.values()
            if isinstance(observation, Mapping)
            and observation.get("inference_receipt_id") == binding["receipt_id"]
            and isinstance(observation.get("inference_receipt_digest"), str)
            and observation["inference_receipt_digest"].removeprefix("sha256:")
                == binding["receipt_digest"].removeprefix("sha256:")]
        if len(matches) != 1:
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_loader_match_count_invalid")
        observation = matches[0]
        observation_id = observation.get("observation_id")
        observation_digest = observation.get("observation_digest")
        if (not isinstance(observation_id, str)
                or not isinstance(observation_digest, str)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_loader_observation_invalid")
        try:
            receipt = read_receipt(observation_id, observation_digest)
        except Exception as exc:
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_loader_receipt_invalid") from exc
        receipt_digest = (receipt.get("receipt_digest")
            if isinstance(receipt, Mapping) else None)
        if (not isinstance(receipt, Mapping)
                or receipt.get("receipt_id") != binding["receipt_id"]
                or not isinstance(receipt_digest, str)
                or receipt_digest.removeprefix("sha256:")
                    != binding["receipt_digest"].removeprefix("sha256:")):
            raise HistoricalExamplesInterventionError(
                "historical_examples_receipt_loader_receipt_mismatch")
        return dict(receipt)

    return load


def _receipt_session(receipt: Any) -> Mapping[str, Any]:
    request = receipt.get("request") if isinstance(receipt, Mapping) else None
    linkage = request.get("linkage") if isinstance(request, Mapping) else None
    session = (linkage.get("rootless_experimental_session")
        if isinstance(linkage, Mapping) else None)
    return session if isinstance(session, Mapping) else {}


def execute_historical_examples_pair_once(*, protocol: Mapping[str, Any],
        answer_key: Mapping[str, int],
        execute_arm: Callable[[str, Mapping[str, Any]],
            HistoricalExamplesArmExecution],
        journal: HistoricalExamplesPairJournal,
        load_receipt_by_binding: Callable[[Mapping[str, Any]], Mapping[str, Any]]
            | None = None,
        fresh_run_binding: tuple[str, str] | None = None,
        ) -> dict[str, Any]:
    """Recover a frozen pair, or require new receipts from the specified run."""
    validate_historical_examples_protocol(protocol=protocol)
    probes = protocol["probe_binding_digests"]
    if (not isinstance(answer_key, Mapping) or set(answer_key) != set(probes)
            or any(type(value) is not int for value in answer_key.values())
            or _digest(dict(answer_key)) != protocol["answer_key_digest"]):
        raise HistoricalExamplesInterventionError(
            "historical_examples_preregistered_answer_key_invalid")
    if (not callable(execute_arm)
            or not isinstance(journal, HistoricalExamplesPairJournal)
            or (load_receipt_by_binding is not None
                and not callable(load_receipt_by_binding))):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_executor_invalid")
    if fresh_run_binding is not None:
        run_id, run_preregistration = fresh_run_binding
        if (not isinstance(run_id, str) or not _PAIR_RUN_ID.fullmatch(run_id)
                or not isinstance(run_preregistration, str)
                or not _RAW_DIGEST.fullmatch(run_preregistration)
                or run_preregistration == "0" * 64):
            raise HistoricalExamplesInterventionError("historical_examples_run_binding_invalid")
    protocol = journal.persist_protocol(protocol=protocol)
    receipts: dict[str, Mapping[str, Any]] = {}
    for arm in protocol["conditions"]:
        state = journal.arm_state(protocol_digest=protocol["protocol_digest"],
            arm=arm)
        if state["status"] == "claimed_without_receipt":
            raise HistoricalExamplesInterventionError(
                "historical_examples_pair_arm_outcome_ambiguous:" + arm)
        if state["status"] == "completed":
            if fresh_run_binding is not None:
                raise HistoricalExamplesInterventionError(
                    "historical_examples_pair_arm_previously_completed:" + arm)
            archived_receipt = state.get("receipt")
            if isinstance(archived_receipt, Mapping):
                receipt = archived_receipt
            elif load_receipt_by_binding is None:
                raise HistoricalExamplesInterventionError(
                    "historical_examples_pair_receipt_loader_required:" + arm)
            else:
                receipt = load_receipt_by_binding(state["receipt_binding"])
            if not isinstance(receipt, Mapping):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_pair_receipt_recovery_failed:" + arm)
            binding = verify_historical_examples_arm_receipt(protocol=protocol,
                arm=arm, receipt=receipt)
            if binding != state["receipt_binding"]:
                raise HistoricalExamplesInterventionError(
                    "historical_examples_pair_recovered_receipt_mismatch:" + arm)
            runtime_history_inventory = state.get("runtime_history_inventory")
            if not isinstance(runtime_history_inventory, Mapping):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_pair_history_inventory_unavailable:" + arm)
        elif state["status"] == "not_started":
            journal.claim_arm(protocol_digest=protocol["protocol_digest"],
                arm=arm)
            execution = execute_arm(arm, protocol)
            if not isinstance(execution, HistoricalExamplesArmExecution):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_pair_arm_execution_evidence_missing:" + arm)
            receipt = execution.receipt
            if fresh_run_binding is not None:
                session = _receipt_session(receipt)
                if (session.get("run_id"), session.get("preregistration_digest")
                        ) != fresh_run_binding:
                    raise HistoricalExamplesInterventionError(
                        "historical_examples_pair_arm_receipt_run_mismatch:" + arm)
            runtime_history_inventory = _verify_runtime_history_inventory(
                execution.runtime_history_inventory, protocol=protocol)
            if not isinstance(receipt, Mapping):
                raise HistoricalExamplesInterventionError(
                    "historical_examples_pair_arm_receipt_missing:" + arm)
            verify_historical_examples_arm_receipt(protocol=protocol, arm=arm,
                receipt=receipt)
            journal.complete_arm(protocol=protocol, arm=arm, receipt=receipt,
                runtime_history_inventory=runtime_history_inventory)
        else:
            raise HistoricalExamplesInterventionError(
                "historical_examples_pair_arm_state_invalid:" + arm)
        receipts[arm] = dict(receipt)
    score = score_verified_historical_examples_pair(protocol=protocol,
        answer_key=answer_key, invocation_receipts_by_arm=receipts)
    persisted_score = journal.persist_score(
        protocol_digest=protocol["protocol_digest"], score=score)
    if persisted_score != score:
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_score_readback_mismatch")
    return {"protocol_digest": protocol["protocol_digest"],
        "score": persisted_score, "score_digest": persisted_score["score_digest"],
        "inference_performed": True, "paired_delivery_verified": True,
        "learning_established": False, "authority": False}


def make_historical_examples_pair_execution_plan(*, cohort: Mapping[str, Any],
        analysis_plan: Mapping[str, Any], runner_cycle_ids: Sequence[str],
        backend_seed: int) -> dict[str, Any]:
    """Freeze pair-level execution identity without claiming full-cycle status."""
    if (not isinstance(cohort, Mapping)
            or cohort.get("schema_version") !=
                "sentientos.historical_examples_preflight_cohort_audit:v1"
            or cohort.get("model_loaded") is not False
            or cohort.get("model_invoked") is not False
            or cohort.get("learning_established") is not False
            or cohort.get("authority") is not False):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_cohort_invalid")
    cohort_body = {key: value for key, value in cohort.items()
        if key != "cohort_digest"}
    if cohort.get("cohort_digest") != _digest(cohort_body):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_cohort_digest_mismatch")
    if (not isinstance(analysis_plan, Mapping)
            or analysis_plan.get("schema_version") not in {
                "sentientos.historical_examples_pair_cohort_analysis_plan:v1",
                "sentientos.historical_examples_pair_cohort_analysis_plan:v2"}
            or analysis_plan.get("cohort_digest") != cohort["cohort_digest"]
            or analysis_plan.get("model_loaded") is not False
            or analysis_plan.get("model_invoked") is not False
            or analysis_plan.get("learning_established") is not False
            or analysis_plan.get("authority") is not False):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_analysis_plan_invalid")
    try:
        from sentientos.historical_examples_analysis_plan import (
            verify_analysis_plan)
        verify_analysis_plan(cohort=cohort, plan=analysis_plan)
    except Exception as exc:
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_analysis_plan_reconstruction_failed") from exc
    analysis_body = {key: value for key, value in analysis_plan.items()
        if key != "analysis_plan_digest"}
    if analysis_plan.get("analysis_plan_digest") != _digest(analysis_body):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_analysis_digest_mismatch")
    trials = cohort.get("trials")
    shared = cohort.get("shared_boundary")
    if (not isinstance(trials, list) or len(trials) < 2
            or len(trials) > 32 or cohort.get("trial_count") != len(trials)
            or not isinstance(shared, Mapping)
            or set(shared) not in ({"cycle_root_id", "generation_budget_digest",
                "generation_config_digest", "history_set_digest",
                "history_prompt_identity_policy",
                "snapshot_digest", "snapshot_id", "source_receipt_digest",
                "source_receipt_id", "target_model_identity_digest",
                "task_family_id"}, {"cycle_root_id", "generation_budget_digest",
                "generation_config_digest", "history_set_digest",
                "history_prompt_identity_policy", "model_identity_backend_seed",
                "snapshot_digest", "snapshot_id", "source_receipt_digest",
                "source_receipt_id", "target_model_identity_digest",
                "task_family_id"})
            or any(not isinstance(shared.get(key), str) or not shared[key]
                for key in ("cycle_root_id", "source_receipt_id", "task_family_id"))
            or any(not isinstance(shared.get(key), str)
                or _DIGEST.fullmatch(shared[key]) is None for key in (
                    "generation_budget_digest", "generation_config_digest",
                    "history_set_digest", "snapshot_digest",
                    "target_model_identity_digest"))
            or not isinstance(shared.get("source_receipt_digest"), str)
            or _RAW_DIGEST.fullmatch(shared["source_receipt_digest"]) is None
            or not isinstance(shared.get("snapshot_id"), str)
            or shared.get("history_prompt_identity_policy") not in {
                None, "matched_cross_model_identity_omitted:v1"}
            or not isinstance(runner_cycle_ids, (list, tuple))
            or len(runner_cycle_ids) != len(trials)
            or any(not isinstance(item, str)
                or _PAIR_RUN_ID.fullmatch(item) is None
                for item in runner_cycle_ids)
            or len(set(runner_cycle_ids)) != len(runner_cycle_ids)
            or type(backend_seed) is not int
            or not 0 <= backend_seed <= 2**31 - 1):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_roster_invalid")
    if ("model_identity_backend_seed" in shared
            and shared["model_identity_backend_seed"] != backend_seed):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_identity_backend_seed_mismatch")
    normalized = []
    seen_protocols: set[str] = set()
    seen_task_digests: set[str] = set()
    seen_probe_sets: set[str] = set()
    for index, row in enumerate(trials):
        if not isinstance(row, Mapping):
            raise HistoricalExamplesInterventionError(
                "historical_examples_pair_execution_trial_invalid")
        protocol_digest = _require_digest(row.get("protocol_digest"),
            "historical_examples_pair_execution_protocol_digest_invalid")
        task_digest = _require_digest(row.get("task_digest"),
            "historical_examples_pair_execution_task_digest_invalid")
        probe_set_digest = _require_digest(row.get("probe_binding_set_digest"),
            "historical_examples_pair_execution_probe_set_digest_invalid")
        seed, probe_count = row.get("task_generation_seed"), row.get("probe_count")
        if (protocol_digest in seen_protocols or task_digest in seen_task_digests
                or probe_set_digest in seen_probe_sets
                or type(seed) is not int or not 1 <= seed <= 2**32 - 1
                or type(probe_count) is not int or probe_count < 1
                or not isinstance(row.get("arm_order"), list)
                or len(row["arm_order"]) != 2
                or any(not isinstance(arm, str) for arm in row["arm_order"])
                or set(row["arm_order"]) != set(_ARMS)):
            raise HistoricalExamplesInterventionError(
                "historical_examples_pair_execution_trial_binding_invalid")
        seen_protocols.add(protocol_digest)
        seen_task_digests.add(task_digest)
        seen_probe_sets.add(probe_set_digest)
        normalized.append({"trial_index": index,
            "protocol_digest": protocol_digest,
            "task_digest": task_digest,
            "task_generation_seed": seed,
            "probe_binding_set_digest": probe_set_digest,
            "probe_count": probe_count,
            "arm_order": list(row["arm_order"]),
            "runner_cycle_id": runner_cycle_ids[index],
            "backend_seed": backend_seed})
    semantic = {"schema_version": _PAIR_EXECUTION_PLAN_SCHEMA,
        "cohort_digest": cohort["cohort_digest"],
        "analysis_plan_digest": analysis_plan["analysis_plan_digest"],
        "source_cycle_root_id": shared["cycle_root_id"],
        "source_receipt_id": shared["source_receipt_id"],
        "source_receipt_digest": shared["source_receipt_digest"],
        "source_history_set_digest": shared["history_set_digest"],
        "source_boundary_digest": _digest(dict(shared)),
        "generation_budget_digest": shared["generation_budget_digest"],
        "generation_config_digest": shared["generation_config_digest"],
        "snapshot_id": shared["snapshot_id"],
        "snapshot_digest": shared["snapshot_digest"],
        "target_model_identity_digest": shared["target_model_identity_digest"],
        "history_prompt_identity_policy": shared[
            "history_prompt_identity_policy"],
        "task_family_id": shared["task_family_id"],
        "trial_count": len(normalized), "trials": normalized,
        "execution_policy": {"ordered_one_pair_per_run": True,
            "retry_ambiguous_invocation": False,
            "replace_incomplete_trial": False,
            "require_all_trials_for_cohort_score": True},
        "preregistration_timing_independently_attested": False,
        "outcomes_observed": False, "model_loaded": False,
        "model_invoked": False, "learning_established": False,
        "authority": False}
    return {**semantic, "execution_plan_digest": _digest(semantic)}


def validate_historical_examples_pair_execution_plan(*, cohort: Mapping[str, Any],
        analysis_plan: Mapping[str, Any], runner_cycle_ids: Sequence[str],
        backend_seed: int, plan: object) -> dict[str, Any]:
    """Rebuild a task-level plan from its frozen cohort and reject any drift."""
    canonical = make_historical_examples_pair_execution_plan(
        cohort=cohort, analysis_plan=analysis_plan,
        runner_cycle_ids=runner_cycle_ids, backend_seed=backend_seed)
    if not isinstance(plan, Mapping) or canonical != dict(plan):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_plan_mismatch")
    return canonical


def validate_historical_examples_pair_execution_slot(*, plan: Mapping[str, Any],
        trial_index: int, protocol: Mapping[str, Any], objective_task: Any,
        runner_cycle_id: str, backend_seed: int) -> dict[str, Any]:
    """Bind one plan slot to its exact journal protocol and private task."""
    if (not isinstance(plan, Mapping)
            or plan.get("schema_version") != _PAIR_EXECUTION_PLAN_SCHEMA
            or plan.get("execution_plan_digest") != _digest({key: value
                for key, value in plan.items()
                if key != "execution_plan_digest"})
            or not isinstance(plan.get("trials"), list)
            or type(trial_index) is not int
            or not 0 <= trial_index < len(plan["trials"])):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_slot_plan_invalid")
    slot = plan["trials"][trial_index]
    descriptor = getattr(objective_task, "public_descriptor", None)
    if not callable(descriptor):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_slot_task_invalid")
    task_descriptor = descriptor()
    validate_historical_examples_protocol(protocol=protocol,
        target_model_identity_digest=plan.get("target_model_identity_digest"),
        task_digest=(task_descriptor.get("task_digest")
            if isinstance(task_descriptor, Mapping) else None))
    probes = protocol.get("probe_binding_digests")
    if (not isinstance(slot, Mapping)
            or not isinstance(task_descriptor, Mapping)
            or task_descriptor.get("history_prompt_identity_policy") !=
                plan.get("history_prompt_identity_policy")
            or type(backend_seed) is not int
            or slot.get("trial_index") != trial_index
            or slot.get("runner_cycle_id") != runner_cycle_id
            or slot.get("backend_seed") != backend_seed
            or backend_seed < 0 or backend_seed > 2**31 - 1
            or slot.get("protocol_digest") != protocol.get("protocol_digest")
            or slot.get("task_digest") != task_descriptor.get("task_digest")
            or protocol.get("conditions") != slot.get("arm_order")
            or not isinstance(probes, list)
            or slot.get("probe_count") != len(probes)
            or slot.get("probe_binding_set_digest") != _digest(sorted(probes))
            or protocol.get("snapshot_id") != plan.get("snapshot_id")
            or protocol.get("snapshot_digest") != plan.get("snapshot_digest")
            or protocol.get("history_set_digest") !=
                plan.get("source_history_set_digest")
            or protocol.get("generation_budget_digest") !=
                plan.get("generation_budget_digest")
            or protocol.get("generation_config_digest") !=
                plan.get("generation_config_digest")
            or protocol.get("task_family_id") != plan.get("task_family_id")):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_slot_binding_mismatch")
    return {"trial_index": trial_index,
        "runner_cycle_id": runner_cycle_id,
        "protocol_digest": protocol["protocol_digest"],
        "task_digest": task_descriptor["task_digest"],
        "probe_binding_set_digest": slot["probe_binding_set_digest"],
        "probe_count": len(probes), "backend_seed": backend_seed,
        "snapshot_id": plan["snapshot_id"],
        "target_model_identity_digest": plan[
            "target_model_identity_digest"],
        "model_invoked": False, "learning_established": False,
        "authority": False}


def derive_historical_examples_objective_answer_key(*, protocol: Mapping[str, Any],
        objective_task: Any) -> dict[str, int]:
    """Reconstruct the private affine answer key without exposing it in evidence."""
    validate_historical_examples_protocol(protocol=protocol)
    specification_method = getattr(objective_task, "specification", None)
    descriptor_method = getattr(objective_task, "public_descriptor", None)
    if not callable(specification_method) or not callable(descriptor_method):
        raise HistoricalExamplesInterventionError(
            "historical_examples_objective_answer_task_invalid")
    specification, descriptor = specification_method(), descriptor_method()
    probes = descriptor.get("probe_inputs") if isinstance(descriptor, Mapping) else None
    multiplier = (specification.get("multiplier")
        if isinstance(specification, Mapping) else None)
    offset = specification.get("offset") if isinstance(specification, Mapping) else None
    if (not isinstance(descriptor, Mapping)
            or descriptor.get("task_digest") != protocol.get("task_digest")
            or not isinstance(probes, (list, tuple)) or not probes
            or any(type(value) is not int for value in probes)
            or type(multiplier) is not int or type(offset) is not int):
        raise HistoricalExamplesInterventionError(
            "historical_examples_objective_answer_task_invalid")
    answer_key = {_digest({
        "schema_version": "sentientos.objective_probe_binding:v1",
        "task_digest": descriptor["task_digest"],
        "probe_index": index, "probe_input": probe}): multiplier * probe + offset
        for index, probe in enumerate(probes)}
    if (set(answer_key) != set(protocol.get("probe_binding_digests", ()))
            or _digest(answer_key) != protocol.get("answer_key_digest")):
        raise HistoricalExamplesInterventionError(
            "historical_examples_objective_answer_key_binding_mismatch")
    return answer_key


def make_historical_examples_pair_runner_binding(*, plan: Mapping[str, Any],
        trial_index: int, model_identity_digest: str,
        runtime_bundle_digest: str, source_boundary_digest: str,
        preregistration_digest: str,
        source_history_seed_evidence_digest: str,
        resource_guard_evidence_digest: str,
        source_history_seed_verified: bool,
        resource_gate_passed: bool) -> dict[str, Any]:
    """Seal the run's verified relation to one preregistered pair slot."""
    if not isinstance(plan, Mapping):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_runner_plan_invalid")
    trials = plan.get("trials")
    if (not isinstance(trials, list) or type(trial_index) is not int
            or not 0 <= trial_index < len(trials)
            or plan.get("schema_version") != _PAIR_EXECUTION_PLAN_SCHEMA
            or plan.get("execution_plan_digest") != _digest({key: value
                for key, value in plan.items()
                if key != "execution_plan_digest"})
            or model_identity_digest != plan.get("target_model_identity_digest")
            or not isinstance(runtime_bundle_digest, str)
            or _DIGEST.fullmatch(runtime_bundle_digest) is None
            or not isinstance(source_history_seed_evidence_digest, str)
            or _DIGEST.fullmatch(source_history_seed_evidence_digest) is None
            or not isinstance(resource_guard_evidence_digest, str)
            or _DIGEST.fullmatch(resource_guard_evidence_digest) is None
            or source_boundary_digest != plan.get("source_boundary_digest")
            or preregistration_digest != plan.get("execution_plan_digest")
            or source_history_seed_verified is not True
            or resource_gate_passed is not True):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_runner_binding_invalid")
    trial = trials[trial_index]
    if (not isinstance(trial, Mapping)
            or not isinstance(trial.get("runner_cycle_id"), str)
            or not isinstance(trial.get("protocol_digest"), str)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_runner_trial_invalid")
    semantic = {"schema_version": _PAIR_RUNNER_BINDING_SCHEMA,
        "execution_plan_digest": plan["execution_plan_digest"],
        "cohort_digest": plan["cohort_digest"],
        "analysis_plan_digest": plan["analysis_plan_digest"],
        "trial_index": trial_index,
        "protocol_digest": trial["protocol_digest"],
        "runner_cycle_id": trial["runner_cycle_id"],
        "target_model_identity_digest": model_identity_digest,
        "runtime_bundle_digest": runtime_bundle_digest,
        "source_boundary_digest": source_boundary_digest,
        "preregistration_digest": preregistration_digest,
        "source_history_seed_evidence_digest":
            source_history_seed_evidence_digest,
        "resource_guard_evidence_digest": resource_guard_evidence_digest,
        "source_history_seed_verified": True,
        "resource_gate_passed": True,
        "authority": False}
    return {**semantic, "runner_binding_digest": _digest(semantic)}


def make_historical_examples_pair_execution_terminal(*,
        plan: Mapping[str, Any], runner_binding: Mapping[str, Any],
        protocol: Mapping[str, Any], score: Mapping[str, Any],
        runtime_history_inventories: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Bind a completed pair score to its run, frozen slot, and stable history."""
    validate_historical_examples_protocol(protocol=protocol)
    trial_index = (runner_binding.get("trial_index")
        if isinstance(runner_binding, Mapping) else None)
    trials = plan.get("trials") if isinstance(plan, Mapping) else None
    if (not isinstance(trials, list) or type(trial_index) is not int
            or not 0 <= trial_index < len(trials)
            or plan.get("schema_version") != _PAIR_EXECUTION_PLAN_SCHEMA
            or plan.get("execution_plan_digest") != _digest({key: value
                for key, value in plan.items()
                if key != "execution_plan_digest"})
            or not isinstance(score, Mapping)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_terminal_inputs_invalid")
    slot = trials[trial_index]
    if (not isinstance(slot, Mapping)
            or protocol.get("protocol_digest") != slot.get("protocol_digest")
            or protocol.get("task_digest") != slot.get("task_digest")
            or score.get("protocol_digest") != slot.get("protocol_digest")
            or score.get("schema_version") !=
                "sentientos.historical_examples_intervention_score:v2"
            or score.get("inference_performed") is not True
            or score.get("paired_delivery_verified") is not True
            or score.get("learning_established") is not False
            or score.get("authority") is not False):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_terminal_score_binding_invalid")
    score_body = {key: value for key, value in score.items()
        if key != "score_digest"}
    if score.get("score_digest") != _digest(score_body):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_terminal_score_digest_invalid")
    receipt_bindings = score.get("invocation_receipt_bindings")
    if (not isinstance(receipt_bindings, Mapping)
            or set(receipt_bindings) != set(_ARMS)):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_terminal_receipt_bindings_invalid")
    receipt_fields = {"receipt_id", "receipt_digest", "request_id",
        "request_digest", "preview_request_digest", "prompt_digest",
        "output_digest"}
    for arm in _ARMS:
        receipt = receipt_bindings[arm]
        if (not isinstance(receipt, Mapping)
                or set(receipt) != receipt_fields
                or any(not isinstance(receipt.get(key), str)
                    or not receipt[key] for key in
                    ("receipt_id", "request_id"))
                or (not isinstance(receipt.get("receipt_digest"), str)
                    or _RAW_DIGEST.fullmatch(receipt["receipt_digest"]) is None)
                or (not isinstance(receipt.get("preview_request_digest"), str)
                    or _DIGEST.fullmatch(receipt["preview_request_digest"]) is None)
                or any(not isinstance(receipt.get(key), str)
                    or _RAW_DIGEST.fullmatch(receipt[key]) is None
                    for key in ("request_digest", "prompt_digest", "output_digest"))):
            raise HistoricalExamplesInterventionError(
                "historical_examples_pair_terminal_receipt_binding_invalid")
    _verify_runtime_history_inventory_pair(runtime_history_inventories,
        protocol=protocol)
    binding_body = {key: value for key, value in runner_binding.items()
        if key != "runner_binding_digest"}
    if (runner_binding.get("schema_version") != _PAIR_RUNNER_BINDING_SCHEMA
            or runner_binding.get("execution_plan_digest") !=
                plan.get("execution_plan_digest")
            or runner_binding.get("protocol_digest") != slot["protocol_digest"]
            or runner_binding.get("trial_index") != trial_index
            or runner_binding.get("runner_cycle_id") != slot.get("runner_cycle_id")
            or runner_binding.get("runner_binding_digest") != _digest(binding_body)
            or runner_binding.get("target_model_identity_digest") !=
                plan.get("target_model_identity_digest")
            or runner_binding.get("source_boundary_digest") !=
                plan.get("source_boundary_digest")
            or runner_binding.get("source_history_seed_verified") is not True
            or runner_binding.get("resource_gate_passed") is not True
            or runner_binding.get("authority") is not False):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_terminal_runner_binding_invalid")
    expected_binding = make_historical_examples_pair_runner_binding(
        plan=plan, trial_index=trial_index,
        model_identity_digest=runner_binding.get(
            "target_model_identity_digest"),
        runtime_bundle_digest=runner_binding.get("runtime_bundle_digest"),
        source_boundary_digest=runner_binding.get("source_boundary_digest"),
        preregistration_digest=runner_binding.get("preregistration_digest"),
        source_history_seed_evidence_digest=runner_binding.get(
            "source_history_seed_evidence_digest"),
        resource_guard_evidence_digest=runner_binding.get(
            "resource_guard_evidence_digest"),
        source_history_seed_verified=runner_binding.get(
            "source_history_seed_verified"),
        resource_gate_passed=runner_binding.get("resource_gate_passed"))
    if expected_binding != dict(runner_binding):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_terminal_runner_binding_mismatch")
    inventory = runtime_history_inventories[protocol["conditions"][0]]
    semantic = {"schema_version": _PAIR_EXECUTION_TERMINAL_SCHEMA,
        "execution_plan_digest": plan["execution_plan_digest"],
        "runner_binding_digest": runner_binding["runner_binding_digest"],
        "cohort_digest": plan["cohort_digest"],
        "analysis_plan_digest": plan["analysis_plan_digest"],
        "trial_index": trial_index,
        "protocol_digest": slot["protocol_digest"],
        "runner_cycle_id": slot["runner_cycle_id"],
        "target_model_identity_digest": plan["target_model_identity_digest"],
        "source_boundary_digest": plan["source_boundary_digest"],
        "score_digest": score["score_digest"],
        "invocation_receipt_bindings": {
            arm: dict(receipt_bindings[arm]) for arm in _ARMS},
        "runtime_history_inventory": {
            "record_count": inventory["runtime_record_count"],
            "record_set_digest": inventory["pair_baseline_record_set_digest"],
            "receipt_count": inventory["runtime_receipt_count"],
            "receipt_set_digest": inventory["pair_baseline_receipt_set_digest"],
            "stable_across_arms": True,
            "selected_record_receipts_verified": True},
        "completion_status": "completed",
        "inference_performed": True,
        "durable_learning_established": False,
        "learning_established": False, "authority": False}
    return {**semantic, "terminal_digest": _digest(semantic)}


def validate_historical_examples_pair_execution_terminal(*,
        plan: Mapping[str, Any], runner_binding: Mapping[str, Any],
        protocol: Mapping[str, Any], score: Mapping[str, Any],
        runtime_history_inventories: Mapping[str, Mapping[str, Any]],
        terminal: object) -> dict[str, Any]:
    """Recompute pair terminal evidence from its complete bound inputs."""
    canonical = make_historical_examples_pair_execution_terminal(
        plan=plan, runner_binding=runner_binding, protocol=protocol,
        score=score, runtime_history_inventories=runtime_history_inventories)
    if not isinstance(terminal, Mapping) or canonical != dict(terminal):
        raise HistoricalExamplesInterventionError(
            "historical_examples_pair_execution_terminal_mismatch")
    return canonical
