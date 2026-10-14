from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Iterator, Mapping

import pytest
import scripts.doctor_resident_objective_experiment as readiness

from sentientos.codex_task_authority_admission import RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION
from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, DevelopmentalHistoryInterventionError,
)
from sentientos.developmental_model_replacement_experiment import ObjectivePredictionTask
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import AuthorityClass, ControlPlaneKernel, LifecyclePhase
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import (
    HostObservationCollectorSpec, HostResourceRuntimeCoordinator,
    build_observation_plan, world_state_records,
)
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker, LocalModelInvocationBudget, LocalModelInvocationReceipt,
    FORBIDDEN_EFFECTS,
)
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import (
    CONFIG_SCHEMA, ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionError,
    ResidentDevelopmentalCognitionOwner, load_config, _bind_epistemic_context,
    _bind_history_and_epistemic_context,
    load_objective_request, objective_task_for_request, stage_objective_request,
    stored_objective_request_disposition, stored_objective_request_record,
)
from sentientos.resident_developmental_writeback import (
    DevelopmentalWritebackError, ResidentDevelopmentalWritebackController,
)
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.resident_cognitive_model_serving import CONFIG_SCHEMA as SERVING_CONFIG_SCHEMA
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.runtime_governor import reset_runtime_governor
from sentientos.federated_governance import reset_controller as reset_federated_governance
from sentientos.pulse_trust_epoch import reset_manager as reset_pulse_trust_epoch
from sentientos.trust_ledger import reset_trust_ledger
from sentientos.integrity_quarantine import QuarantineState, save_state
from sentientos.integrity_incident import build_incident, write_incident
from sentientos.world_state_board import WorldStateBoardBuilder
from sentientos.embodied_consequence import (
    WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V4, digest as embodied_digest,
)
from sentientosd import (
    RuntimeMaintenanceSurfaces,
    _attestation_snapshot_verification_world_state_record,
    _load_embodied_consequence_projection,
    _load_epistemic_state_owner,
)
from sentientos.persistent_epistemic_state import (PersistentEpistemicStateOwner,
    make_proposition, make_evidence_binding, make_cognitive_projection,
    MeaningBearingEpistemicCognitiveProjection)

pytestmark = pytest.mark.no_legacy_skip


def snapshot(value: int = 1):
    return WorldStateBoardBuilder().build([
        {"source_id":"source-b", "source_kind":"audit_trust", "subject_id":"b", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":9}},
        {"source_id":"source-a", "source_kind":"capability_registry", "subject_id":"a", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":value}},
        {"source_id":"source-c", "source_kind":"capability_registry", "subject_id":"c", "stage":"observation", "disposition":"recorded", "observed_at":"2026-01-01T00:00:00+00:00", "payload":{"value":3}},
    ])


class FakeInvoker:
    def __init__(self) -> None:
        self.requests = []
        self.lesson_statement = "When prior evidence conflicts, preserve its scope and uncertainty."
        self.lesson_scope = "historical evidence interpretation"
        self.lesson_dependency_override = None
        self.truncate_cognition_output = False
        self.modify_cognition_output_after_digest = False
        self.cross_cognition_request_identity = False
        self.no_cognition_lesson = False
        self.unavailable_cognition_output = False
        self.effective_generation_ceiling: int | None = None
        self.backend_completion_observation: dict[str, object] | None = None
        self.objective_mode = "derive_from_history"
        self.truncate_objective_output = False
        self.fail_objective_condition: str | None = None
        self.objective_plan_root: Path | None = None
        self.history_interpretation = "bounded history"

    def build_request(self, **kwargs):
        request = type("Request", (), {})()
        for key, value in kwargs.items(): setattr(request, key, value)
        request.prompt_digest = digest_payload({"prompt": kwargs["prompt"]})
        request.prompt_size = len(kwargs["prompt"].encode("utf-8"))
        request.model_id = "model-a"; request.model_artifact_digest = "sha256:model"
        request.authority_map_digest = "test-authority-map"; request.active_model_identity = {}
        budget = kwargs.get("budget") or LocalModelInvocationBudget()
        request.budget = budget
        request.lifecycle_phase = kwargs.get("lifecycle_phase", "runtime")
        request.structured_output_schema = (dict(kwargs["structured_output_schema"])
            if kwargs.get("structured_output_schema") is not None else None)
        semantic = {
            "purpose": kwargs["purpose"],
            "prompt_digest": digest_payload({"prompt": kwargs["prompt"]}),
            "prompt_size": len(kwargs["prompt"].encode("utf-8")),
            "model_id": "model-a", "authority_map_digest": "test-authority-map",
            "model_artifact_digest": "sha256:model", "active_model_identity": {},
            "caller": kwargs["caller"], "lifecycle_phase": request.lifecycle_phase,
            "correlation_id": kwargs["correlation_id"],
            "expected_output_format": kwargs.get("expected_output_format", "text"),
            "structured_output_schema": request.structured_output_schema,
            "budget": budget.to_dict(), "upstream_evidence": kwargs.get("upstream_evidence") or {},
            "linkage": kwargs.get("linkage") or {},
            "allowed_effects": {"local_model_inference": True},
            "forbidden_effects": dict(FORBIDDEN_EFFECTS),
        }
        request.request_digest = digest_payload(semantic); request.request_id = "lmreq-" + request.request_digest[:24]
        request.to_receipt_request_dict = lambda: {**semantic, "request_id":request.request_id,
            "request_digest":request.request_digest, "raw_prompt_stored":False,
            "ephemeral_prompt_handling":"raw prompt used only for immediate local backend call"}
        self.requests.append(request)
        return request

    def invoke(self, request, *, persist, include_output_in_receipt):
        if (request.purpose == "resident_developmental_history_intervention_experiment"
                and self.fail_objective_condition == request.linkage.get("condition_id")):
            raise RuntimeError("fixture_interrupted_before_condition_invocation")
        truncated = False
        original_output = None
        if request.purpose == "resident_developmental_interpretation":
            text = json.dumps({"interpretation":self.history_interpretation, "uncertainty":"medium"})
        elif (request.purpose == "resident_developmental_history_intervention_experiment"
                and "objective_task_plan_digest" in request.upstream_evidence):
            assert self.objective_plan_root is not None
            plans = list(self.objective_plan_root.glob("objective-task-plan-*.json"))
            matching = [json.loads(path.read_text(encoding="utf-8")) for path in plans
                if json.loads(path.read_text(encoding="utf-8")).get("plan_digest")
       