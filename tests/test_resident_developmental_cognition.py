from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos.codex_task_authority_admission import RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION
from sentientos.developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, DevelopmentalHistoryInterventionError,
)
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from sentientos.governed_local_model_invocation import (
    GovernedLocalModelInvoker, LocalModelInvocationBudget, LocalModelInvocationReceipt,
    FORBIDDEN_EFFECTS,
)
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_cognition import (
    CONFIG_SCHEMA, ResidentDevelopmentalCognitionConfig, ResidentDevelopmentalCognitionError,
    ResidentDevelopmentalCognitionOwner, load_config, _bind_epistemic_context,
)
from sentientos.resident_developmental_writeback import (
    DevelopmentalWritebackError, ResidentDevelopmentalWritebackController,
)
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
from sentientos.integrity_quarantine import QuarantineState, save_state
from sentientos.world_state_board import WorldStateBoardBuilder
from sentientosd import RuntimeMaintenanceSurfaces, _load_epistemic_state_owner
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
        truncated = False
        original_output = None
        if request.purpose == "resident_developmental_interpretation":
            text = json.dumps({"interpretation":"bounded history", "uncertainty":"medium"})
        elif request.expected_output_format == "json" and request.structured_output_schema:
            upstream = request.upstream_evidence
            consumed = (upstream.get("record_ids") or upstream.get("current_fact_ids")
                        or upstream.get("self_model_claim_ids") or
                        upstream.get("epistemic_consumed_packet_ids") or [])
            dependency = (self.lesson_dependency_override or consumed[0]) if consumed else "missing"
            lesson = None if self.no_cognition_lesson else {
                "statement": self.lesson_statement, "scope": self.lesson_scope,
                "applicability": "Only when the cited evidence and scope still match.",
                "uncertainty": "medium",
                "uncertainty_rationale": "The source is historical interpretation.",
                "evidence_dependencies": [dependency],
                "possible_contradiction_ids": [],
            }
            text = json.dumps({
                "conclusion": f"Conclusion supporting: {self.lesson_statement}",
                "lesson_candidate": lesson,
            }, sort_keys=True)
            original_output = text
            if self.truncate_cognition_output:
                text = text[:24]
                truncated = True
        else:
            text = "cognition-with-history" if request.linkage.get("history_present") else "cognition-withheld"
        if original_output is None:
            original_output = text
        if (self.modify_cognition_output_after_digest
                and request.purpose == "resident_developmental_retrieval_cognition"):
            text = text + " substituted"
        receipt_request = request.to_receipt_request_dict()
        if self.cross_cognition_request_identity and request.expected_output_format == "json":
            receipt_request["request_id"] = "lmreq-crossed"
        receipt_text = None if (self.unavailable_cognition_output
            and request.purpose == "resident_developmental_retrieval_cognition") else text
        return LocalModelInvocationReceipt(request=receipt_request, status="admitted_completed",
            reason_codes=("completed",), output_text=receipt_text, output_digest=digest_payload({"output":original_output}),
            output_size_bytes=len(original_output.encode()), admission_decision_ref="local",
            purpose=request.purpose, latency_ms=1, output_truncated=truncated, fallback_occurred=False,
            effects={"local_model_inference":True}, observed_at="2026-01-01T00:00:00+00:00",
            generation_config={"actual_generation_parameters":{"temperature":0}} if request.purpose == "resident_developmental_history_intervention_experiment" else {})


class SessionBoundFakeInvoker(FakeInvoker):
    def __init__(self) -> None:
        super().__init__()
        self.session_id = "fixture-serving-session"
        self.session_binding = {
            "model_serving_admission_ref": "fixture-model-serving-admission",
            "activation_state_semantic_digest": "a" * 64,
            "session_receipt_id": "resident-serving-receipt-" + "b" * 24,
            "session_receipt_semantic_digest": "c" * 64,
        }
        self.receipts = {}
        self.verified_receipts = []

    def build_request(self, **kwargs):
        linkage = dict(kwargs.get("linkage") or {})
        linkage["resident_cognitive_serving"] = {
            "session_id": self.session_id,
            **{key: value for key, value in self.session_binding.items()
                if key in {"model_serving_admission_ref", "activation_state_semantic_digest"}},
            "session_receipt_id": self.session_binding["session_receipt_id"],
            "session_receipt_semantic_digest": self.session_binding["session_receipt_semantic_digest"]}
        kwargs["linkage"] = linkage
        return super().build_request(**kwargs)

    def invoke(self, request, **kwargs):
        receipt = super().invoke(request, **kwargs)
        self.receipts[receipt.receipt_id] = receipt
        return receipt

    def verify_persisted_invocation_receipt(self, receipt_id, receipt_digest, **expected):
        self.verified_receipts.append((receipt_id, receipt_digest, dict(expected)))
        receipt = self.receipts[receipt_id]
        assert receipt.receipt_digest == receipt_digest
        assert receipt.request["request_id"] == expected["expected_request_id"]
        assert receipt.request["request_digest"] == expected["expected_request_digest"]
        expected_serving = {
            "session_id": expected["expected_session_id"],
            **dict(expected["expected_session_binding"])}
        if expected.get("expected_session_receipt_id") is not None:
            expected_serving.update({"session_receipt_id": expected["expected_session_receipt_id"],
                "session_receipt_semantic_digest": expected["expected_session_receipt_digest"]})
        assert receipt.request["linkage"]["resident_cognitive_serving"] == expected_serving
        assert receipt.request["active_model_identity"] == expected["expected_active_model_identity"]
        return {"receipt_id": receipt.receipt_id, "receipt_digest": receipt.receipt_digest,
            "request": receipt.request, "status": receipt.status,
            "output_digest": receipt.output_digest}


def test_session_bound_observation_recovery_reconciles_exact_invocation_receipt(tmp_path: Path) -> None:
    invoker = SessionBoundFakeInvoker()
    first, _ = owner(tmp_path, comparison=True, invoker=invoker)
    first.run_tick(snapshot=snapshot(), tick_id="session-tick-1")
    experiment_result = first.run_tick(snapshot=snapshot(), tick_id="session-tick-2")
    observations = first._recover_observation_ticks(include_records=True)
    assert observations
    assert all(row["serving_session_id"] == invoker.session_id for row in observations.values())
    expected_binding = {key: invoker.session_binding[key] for key in (
        "model_serving_admission_ref", "activation_state_semantic_digest")}
    assert all(row["serving_session_binding"] == expected_binding for row in observations.values())
    assert all(row["serving_session_receipt_id"] == invoker.session_binding["session_receipt_id"]
        and row["serving_session_receipt_digest"] == invoker.session_binding[
            "session_receipt_semantic_digest"] for row in observations.values())

    loaded = first.experiments.load_run(experiment_result.changed_cognition_measurement_id)
    assert loaded["validity"] == "valid_controlled_observation"
    with pytest.raises(DevelopmentalHistoryInterventionError,
                       match="run_artifact_invocation_verifier_unavailable"):
        DevelopmentalExperimentStore(tmp_path / "state").load_run(
            experiment_result.changed_cognition_measurement_id)
    restarted, _ = owner(tmp_path, invoker=invoker)
    restarted.run_tick(snapshot=snapshot(), tick_id="session-tick-3")
    assert invoker.verified_receipts
    assert all(item[2]["expected_session_id"] == invoker.session_id
        for item in invoker.verified_receipts)


def owner(root: Path, *, comparison: bool = False, invoker: FakeInvoker | None = None,
          allowed_source_kinds: tuple[str, ...] = ("capability_registry",)):
    ledger = AdmissionLedger(root / "state" / "admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    def current():
        admissions, _ = ledger.load(); return max((a.issued_sequence for a in admissions), default=1)
    def next_sequence():
        admissions, revocations = ledger.load()
        return max([a.issued_sequence for a in admissions] + [r.sequence for r in revocations], default=0) + 1
    ctrl = ResidentDevelopmentalWritebackController(history_root=root / "history",
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger), current_sequence=current)
    fake = invoker or FakeInvoker()
    result = ResidentDevelopmentalCognitionOwner(config=ResidentDevelopmentalCognitionConfig(
        root / "history", root / "state", allowed_source_kinds, 1, 4, comparison), writeback=ctrl,
        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        invoker=fake, current_sequence=next_sequence)
    return result, fake


def test_quarantine_custody_failure_reaches_configured_cognition_and_next_tick_history(
    tmp_path: Path,
) -> None:
    from sentientos.integrity_quarantine import QUARANTINE_PATH

    target = tmp_path / QUARANTINE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"schema_version":1')
    narrative = tmp_path / "pulse" / "integrity_incidents.jsonl"
    narrative.parent.mkdir(parents=True)
    narrative.write_text('{"severity":"critical","triggers":["attack confirmed"]}\n')

    cognition, fake = owner(tmp_path / "cognition", allowed_source_kinds=("quarantine",))
    surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=cognition,  # type: ignore[arg-type]
    )
    tick = "2026-10-11T00:00:00+00:00"
    surfaces.build_world_state_board(tick_id=tick)
    snapshot_value = surfaces.current_world_state_snapshot
    assert snapshot_value is not None
    facts = [fact for fact in snapshot_value.facts
             if fact.source.kind == "quarantine"]
    assert len(facts) == 1
    fact = facts[0]
    assert fact.subject.subject_kind == "quarantine_custody_observation"
    assert fact.disposition == "custody_invalid"
    assert fact.observed_at == tick
    assert fact.source.staleness == "unknown"
    assert fact.payload["custody_error_code"] == "quarantine_json_invalid"
    assert fact.payload["quarantine_active"] is None
    assert fact.payload["attack_established"] is False
    assert fact.payload["hostile_activity_established"] is False

    first = surfaces.run_resident_developmental_cognition(tick_id=tick)
    record_id = first["written_record_id"]
    assert first["status"] == "completed" and record_id
    interpretation = next(request for request in fake.requests
        if request.purpose == "resident_developmental_interpretation")
    interpretation_input = json.loads(interpretation.prompt)
    selected = interpretation_input["selection"]["facts"]
    assert "Do not infer hostile activity, attack, intent, or cause" in interpretation_input["instruction"]
    assert len(selected) == 1
    selected_payload = selected[0]["payload"]
    assert selected_payload["custody_error_code"] == "quarantine_json_invalid"
    assert selected_payload["quarantine_active"] is None
    assert selected_payload["attack_established"] is False
    assert "attack confirmed" not in interpretation.prompt
    stored = cognition.writeback.store.get(record_id)
    assert stored.candidate["selected_facts"][0]["source"]["kind"] == "quarantine"

    restarted, later_fake = owner(tmp_path / "cognition", invoker=FakeInvoker(),
        allowed_source_kinds=("quarantine",))
    later_fake.no_cognition_lesson = True
    later_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=restarted,  # type: ignore[arg-type]
    )
    later_tick = "2026-10-11T00:00:01+00:00"
    later_surfaces.build_world_state_board(tick_id=later_tick)
    later = later_surfaces.run_resident_developmental_cognition(tick_id=later_tick)
    retrieval = next(request for request in later_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert retrieval.upstream_evidence["record_ids"] == [record_id]
    assert fact.fact_id in retrieval.upstream_evidence["current_fact_ids"]
    context = json.loads(retrieval.prompt)
    assert context["current_evidence"]["facts"][0]["payload"]["custody_error_code"] == "quarantine_json_invalid"
    assert later["status"] == "completed"


def test_quarantine_custody_context_can_yield_scoped_later_tick_lesson(tmp_path: Path) -> None:
    """A cognition conclusion stays an untrusted, evidence-bound history candidate."""
    from sentientos.integrity_quarantine import QUARANTINE_PATH

    target = tmp_path / QUARANTINE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"schema_version":1')
    cognition, _first_fake = owner(
        tmp_path / "cognition", allowed_source_kinds=("quarantine",))
    first_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=cognition,  # type: ignore[arg-type]
    )
    first_tick = "2026-10-11T00:00:00+00:00"
    first_surfaces.build_world_state_board(tick_id=first_tick)
    first = first_surfaces.run_resident_developmental_cognition(tick_id=first_tick)
    assert first["status"] == "completed" and first["written_record_id"]

    # The lesson-producing request is the ordinary later history-conditioned
    # cognition call. Its proposal is scoped to interpreting this custody
    # failure, keeps uncertainty, and makes no claim about hostile activity.
    second_fake = FakeInvoker()
    second_fake.lesson_statement = (
        "A failed quarantine custody read leaves the stored protective posture unknown.")
    second_fake.lesson_scope = "quarantine custody observation interpretation"
    second = owner(tmp_path / "cognition", invoker=second_fake,
        allowed_source_kinds=("quarantine",))[0]
    second_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=second,  # type: ignore[arg-type]
    )
    second_tick = "2026-10-11T00:00:01+00:00"
    second_surfaces.build_world_state_board(tick_id=second_tick)
    second_snapshot = second_surfaces.current_world_state_snapshot
    assert second_snapshot is not None
    custody_fact = next(fact for fact in second_snapshot.facts
        if fact.subject.subject_kind == "quarantine_custody_observation")
    second_fake.lesson_dependency_override = custody_fact.fact_id
    result = second_surfaces.run_resident_developmental_cognition(tick_id=second_tick)
    lesson_record_id = result["written_record_id"]
    assert result["status"] == "completed" and lesson_record_id
    history_conditioned_request = next(request for request in second_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert "Treat the stored protective posture as unknown" in history_conditioned_request.prompt
    assert "do not turn it into a protective procedure, policy, or authority" in (
        history_conditioned_request.prompt)
    lesson_record = second.writeback.store.get(lesson_record_id)
    provenance = lesson_record.candidate["transformation_provenance"]
    lesson = provenance["lesson_candidate"]
    assert lesson["statement"] == second_fake.lesson_statement
    assert lesson["scope"] == second_fake.lesson_scope
    assert lesson["uncertainty"] == "medium"
    assert lesson["evidence_dependencies"] == [custody_fact.fact_id]
    assert lesson["possible_contradiction_ids"] == []
    assert provenance["candidate_posture"] == (
        "untrusted_candidate_not_truth_policy_authority_or_adopted_procedure")
    assert provenance["current_truth"] is False
    assert provenance["authority"] is False
    assert provenance["policy"] is False
    assert provenance["canonical_explicit_user_retention"] is False
    assert lesson_record.candidate["epistemic_status"] == (
        "untrusted_history_conditioned_cognition_candidate")

    # A fresh owner recovers the admitted record and makes it available to a
    # third-tick cognition request, still as historical context only.
    third_fake = FakeInvoker()
    third_fake.no_cognition_lesson = True
    third = owner(tmp_path / "cognition", invoker=third_fake,
        allowed_source_kinds=("quarantine",))[0]
    third_surfaces = RuntimeMaintenanceSurfaces(
        tmp_path, runtime_state_root=tmp_path / "runtime",
        resident_developmental_owner=third,  # type: ignore[arg-type]
    )
    third_tick = "2026-10-11T00:00:02+00:00"
    third_surfaces.build_world_state_board(tick_id=third_tick)
    third_result = third_surfaces.run_resident_developmental_cognition(tick_id=third_tick)
    retrieval = next(request for request in third_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition")
    assert lesson_record_id in retrieval.upstream_evidence["record_ids"]
    retrieval_context = json.loads(retrieval.prompt)
    assert second_fake.lesson_statement in json.dumps(retrieval_context, sort_keys=True)
    assert third_result["status"] == "completed"


@pytest.mark.parametrize(("active", "expected"), [(False, False), (True, True)])
def test_valid_quarantine_state_projection_preserves_actual_posture(
    tmp_path: Path, active: bool, expected: bool,
) -> None:
    save_state(tmp_path, QuarantineState(active=active, allow_publish=not active,
        allow_automerge=not active, freeze_forge=active, allow_federation_sync=not active))
    surfaces = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime")
    surfaces.build_world_state_board(tick_id="2026-10-11T00:00:00+00:00")
    snapshot_value = surfaces.current_world_state_snapshot
    assert snapshot_value is not None
    facts = [fact for fact in snapshot_value.facts if fact.source.kind == "quarantine"]
    assert len(facts) == 1
    assert facts[0].disposition == "recorded"
    assert facts[0].payload["custody_result"] == "valid_v1"
    assert facts[0].payload["quarantine_active"] is expected
    assert facts[0].payload["attack_established"] is False


def epistemic_projection(root: Path):
    epistemic = PersistentEpistemicStateOwner(root, allowed_namespaces=["embodiment"])
    proposition = make_proposition(namespace="embodiment", subject="body:g1", predicate="healthy",
        object_value=True, polarity="positive", qualifiers={}, temporal_scope={"kind":"prior"},
        context_scope={}, proposition_class="descriptive")
    epistemic.register_proposition(proposition)
    state, _ = epistemic.commit_update(proposition_id=proposition.proposition_id,
        expected_predecessor_digest=None, stance="unknown", reason="initialization",
        active_binding_ids=[], correlation_id="prior", tick=1,
        recorded_at="2026-01-01T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=1)
    assert projection is not None
    return projection, proposition, state


def test_meaning_bearing_epistemic_packets_reach_actual_inference_request(tmp_path: Path):
    epistemic = PersistentEpistemicStateOwner(tmp_path / "epistemic",
        allowed_namespaces=["embodiment"])
    propositions = [make_proposition(namespace="embodiment", subject="sensor:g9",
        predicate="reports_temperature", object_value={"celsius": 20}, polarity="positive",
        qualifiers={"sensor": "exact-a"}, temporal_scope={"window": window},
        context_scope={"room": room}, proposition_class="descriptive",
        statement="canonical temperature proposition")
        for window, room in (("morning", "lab-a"), ("evening", "lab-b"))]
    for index, proposition_value in enumerate(propositions):
        epistemic.register_proposition(proposition_value)
        support = make_evidence_binding(proposition_id=proposition_value.proposition_id,
            source_artifact_id=f"support-{index}", source_digest="sha256:" + str(index + 1) * 64,
            source_schema="sentientos.test_sensor:v1", source_class="fixture",
            observation_time="2026-01-01T00:00:00Z", evidence_relation="supports",
            dependency_kind="independently_sourced_observation", dependency_group=f"group-{index}",
            upstream_binding_ids=(), freshness="current", reliability_posture="verified")
        contradiction = make_evidence_binding(proposition_id=proposition_value.proposition_id,
            source_artifact_id=f"contradiction-{index}", source_digest="sha256:" + str(index + 3) * 64,
            source_schema="sentientos.test_sensor:v1", source_class="fixture",
            observation_time="2025-01-01T00:00:00Z", evidence_relation="contradicts",
            dependency_kind="unknown_dependency", dependency_group=None,
            upstream_binding_ids=(), freshness="stale", reliability_posture="unverified")
        epistemic.bind_evidence(support)
        epistemic.bind_evidence(contradiction)
        state, _ = epistemic.commit_update(proposition_id=proposition_value.proposition_id,
            expected_predecessor_digest=None, stance="contested", reason="initialization",
            active_binding_ids=[support.binding_id, contradiction.binding_id],
            added_binding_ids=[support.binding_id, contradiction.binding_id],
            correlation_id=f"contested-{index}", tick=1,
            recorded_at="2026-01-01T00:00:00Z", confidence={"uncertainty": "high"})
        if index == 1:
            current_contradiction = make_evidence_binding(
                proposition_id=proposition_value.proposition_id,
                source_artifact_id="contradiction-current",
                source_digest="sha256:" + "5" * 64,
                source_schema="sentientos.test_sensor:v1", source_class="fixture",
                observation_time="2026-01-02T00:00:00Z", evidence_relation="contradicts",
                dependency_kind="unknown_dependency", dependency_group=None,
                upstream_binding_ids=(), freshness="current", reliability_posture="unverified")
            epistemic.bind_evidence(current_contradiction)
            changed_state, _ = epistemic.commit_update(proposition_id=proposition_value.proposition_id,
                expected_predecessor_digest=state.state_digest, stance="contested",
                reason="evidence_withdrawal", active_binding_ids=[support.binding_id,
                    current_contradiction.binding_id], added_binding_ids=[current_contradiction.binding_id],
                removed_binding_ids=[contradiction.binding_id], correlation_id="withdraw-stale",
                tick=2, recorded_at="2026-01-02T00:00:00Z")
            epistemic.commit_update(proposition_id=proposition_value.proposition_id,
                expected_predecessor_digest=changed_state.state_digest, stance="contested",
                reason="update_rule_correction", active_binding_ids=[support.binding_id,
                    current_contradiction.binding_id], update_rule_id="fixture-rule:v2",
                correlation_id="after-withdrawal", tick=3,
                recorded_at="2026-01-03T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=2, current_tick=4)
    assert isinstance(projection, MeaningBearingEpistemicCognitiveProjection)
    composition, fake = owner(tmp_path / "cognition")
    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-2",
        prior_epistemic_state=projection)
    request = next(item for item in fake.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    consumed = json.loads(request.prompt)["prior_epistemic_state"]
    packets = consumed["semantic_packets"]
    # The full two-packet projection exceeds the fixed input budget. Selection
    # delivers the complete packet with recent withdrawal/contradiction first
    # and binds the other packet as omitted rather than silently truncating it.
    assert len(packets) == 1
    assert packets[0]["state"]["stance"] == "contested"
    assert packets[0]["proposition"]["temporal_scope"]["window"] == "evening"
    assert packets[0]["proposition"]["context_scope"]["room"] == "lab-b"
    assert request.upstream_evidence["epistemic_owner_packet_count"] == 2
    assert len(request.upstream_evidence["epistemic_omitted_packets"]) == 1
    assert request.upstream_evidence["epistemic_omitted_packets"][0]["packet_id"] != packets[0]["packet_id"]
    withdrawn = next(packet for packet in packets if packet["removed_evidence_history"])
    assert withdrawn["removed_evidence_history"][0]["freshness"] == "stale"
    assert withdrawn["evidence_posture"]["dependency_unresolved"] is True
    assert withdrawn["contradicting_evidence"]
    upstream = request.upstream_evidence
    assert upstream["epistemic_consumed_packet_ids"] == [p["packet_id"] for p in packets]
    assert upstream["epistemic_consumed_packet_digests"] == [p["packet_digest"] for p in packets]
    assert upstream["epistemic_prompt_digest"] == "sha256:" + request.prompt_digest
    observation_id = result.cognition_observation_ids[0]
    recovered, _ = owner(tmp_path / "cognition")
    observation = recovered.verified_cognition_observation(observation_id)
    assert observation["epistemic_consumed_packet_ids"] == upstream["epistemic_consumed_packet_ids"]
    assert observation["epistemic_consumed_content_digest"] == upstream["epistemic_consumed_content_digest"]


def test_legacy_identifier_projection_is_valid_but_not_delivered_as_meaning(tmp_path: Path):
    semantic, proposition_value, state = epistemic_projection(tmp_path / "epistemic")
    legacy = make_cognitive_projection([state], source_tick=1, current_tick=2)
    composition, fake = owner(tmp_path / "cognition")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-2", prior_epistemic_state=legacy)
    request = next(item for item in fake.requests
        if item.purpose == "resident_developmental_retrieval_cognition")
    prior = json.loads(request.prompt)["prior_epistemic_state"]
    assert prior["semantic_status"] == "canonical_definition_unavailable"
    assert prior["semantic_packets"] == []
    assert proposition_value.predicate not in request.prompt
    assert request.upstream_evidence["epistemic_state_ids"] == [state.state_id]


def test_semantic_packets_are_whole_and_omissions_are_bound_under_input_budget(tmp_path: Path):
    epistemic = PersistentEpistemicStateOwner(tmp_path, allowed_namespaces=["embodiment"])
    for index in range(2):
        proposition_value = make_proposition(namespace="embodiment", subject=f"sensor:{index}",
            predicate="long_scoped_measurement", object_value={"value": index}, polarity="positive",
            qualifiers={"canonical_qualifier": "q" * 4500},
            temporal_scope={"window": f"exact-window-{index}"},
            context_scope={"facility": f"facility-{index}"}, proposition_class="descriptive",
            statement="complete statement " + ("s" * 4500))
        epistemic.register_proposition(proposition_value)
        epistemic.commit_update(proposition_id=proposition_value.proposition_id,
            expected_predecessor_digest=None, stance="unknown", reason="initialization",
            active_binding_ids=[], correlation_id=f"long-{index}", tick=index + 1,
            recorded_at="2026-01-01T00:00:00Z")
    projection = epistemic.cognitive_projection(max_states=2, current_tick=3)
    context, metadata, prompt = _bind_epistemic_context(
        context={"instruction": "prior positions are not truth"}, projection=projection)
    assert len(prompt) <= 16_000
    prior = context["prior_epistemic_state"]
    assert len(prior["semantic_packets"]) == 1
    assert len(metadata["epistemic_omitted_packets"]) == 1
    delivered = prior["semantic_packets"][0]
    assert delivered["proposition"]["qualifiers"]["canonical_qualifier"] == "q" * 4500
    assert delivered["proposition"]["context_scope"]["facility"] in {"facility-0", "facility-1"}
    assert prior["omitted_packets_digest"] == metadata["epistemic_omitted_packets_digest"]


def self_model_projection(root: Path):
    from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
    from tests.test_longitudinal_self_model import record, snapshot as self_model_snapshot

    self_model = LongitudinalSelfModelOwner(root)
    self_model.reconcile(self_model_snapshot(record()), tick_id="tick-1")
    projection = self_model.cognitive_projection(before_tick="tick-2", max_claims=2,
        allowed_predicates=("software_generation", "cognitive_model_identity"))
    assert projection is not None
    return projection


def test_epistemic_only_prior_context_causes_real_owner_cognition(tmp_path: Path) -> None:
    projection, proposition, state = epistemic_projection(tmp_path / "epistemic")
    composition, fake = owner(tmp_path / "cognition")

    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-2",
                                  prior_epistemic_state=projection)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_retrieval_cognition"]
    assert len(cognition) == 1
    assert result.cognition_observation_ids
    request = cognition[0]
    assert request.upstream_evidence["record_ids"] == []
    assert request.upstream_evidence["self_model_projection_present"] is False
    assert request.upstream_evidence["epistemic_projection_id"] == projection.projection_id
    assert request.upstream_evidence["epistemic_projection_digest"] == projection.projection_digest
    assert request.upstream_evidence["epistemic_proposition_ids"] == [proposition.proposition_id]
    assert request.upstream_evidence["epistemic_state_ids"] == [state.state_id]
    assert request.upstream_evidence["epistemic_state_digests"] == [state.state_digest]
    assert request.upstream_evidence["epistemic_generations"] == [state.generation]
    assert request.upstream_evidence["epistemic_evidence_set_digests"] == [state.evidence_set_digest]
    observation = json.loads((composition.observations_root /
                              f"{result.cognition_observation_ids[0]}.json").read_text())
    assert observation["epistemic_projection_present"] is True
    assert observation["epistemic_projection_id"] == projection.projection_id
    assert observation["epistemic_projection_digest"] == projection.projection_digest
    assert observation["epistemic_proposition_ids"] == [proposition.proposition_id]
    assert observation["epistemic_state_ids"] == [state.state_id]
    assert observation["epistemic_state_digests"] == [state.state_digest]
    assert observation["epistemic_generations"] == [state.generation]
    assert observation["epistemic_evidence_set_digests"] == [state.evidence_set_digest]
    assert observation["developmental_projection_present"] is False
    assert observation["self_model_projection_present"] is False
    assert observation["authority"] is False


def test_self_model_and_epistemic_context_run_one_ordinary_condition(tmp_path: Path) -> None:
    epistemic, _, _ = epistemic_projection(tmp_path / "epistemic")
    self_model = self_model_projection(tmp_path / "self-model")
    composition, fake = owner(tmp_path / "cognition", comparison=True)

    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-2",
        prior_self_model=self_model, prior_epistemic_state=epistemic)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_retrieval_cognition"]
    assert len(cognition) == 1
    assert cognition[0].upstream_evidence["record_ids"] == []
    assert cognition[0].upstream_evidence["self_model_projection_id"] == self_model.projection_id
    assert cognition[0].upstream_evidence["epistemic_projection_id"] == epistemic.projection_id
    assert result.changed_cognition_measurement_id is None
    assert not list(composition.experiments.protocols.glob("*.json"))
    assert not list(composition.experiments.runs.glob("*.json"))


def test_all_four_substrates_reach_ordinary_cognition_when_comparison_disabled(tmp_path: Path) -> None:
    first, _ = owner(tmp_path / "cognition")
    written = first.run_tick(snapshot=snapshot(), tick_id="tick-1").written_record_id
    epistemic, _, _ = epistemic_projection(tmp_path / "epistemic")
    self_model = self_model_projection(tmp_path / "self-model")
    restarted, fake = owner(tmp_path / "cognition")

    result = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2",
        prior_self_model=self_model, prior_epistemic_state=epistemic)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_retrieval_cognition"]
    assert len(cognition) == 1
    assert cognition[0].upstream_evidence["current_fact_ids"]
    assert cognition[0].upstream_evidence["record_ids"] == [written]
    assert cognition[0].upstream_evidence["self_model_projection_id"] == self_model.projection_id
    assert cognition[0].upstream_evidence["epistemic_projection_id"] == epistemic.projection_id
    assert result.changed_cognition_measurement_id is None


def test_history_comparison_keeps_self_model_and_epistemic_bindings_constant(tmp_path: Path) -> None:
    first, _ = owner(tmp_path / "cognition")
    first.run_tick(snapshot=snapshot(), tick_id="tick-1")
    epistemic, _, _ = epistemic_projection(tmp_path / "epistemic")
    self_model = self_model_projection(tmp_path / "self-model")
    restarted, fake = owner(tmp_path / "cognition", comparison=True)

    result = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2",
        prior_self_model=self_model, prior_epistemic_state=epistemic)

    cognition = [request for request in fake.requests
                 if request.purpose == "resident_developmental_history_intervention_experiment"
                 and "history_present" in request.linkage]
    assert [request.linkage["history_present"] for request in cognition] == [True, False, True]
    assert {request.upstream_evidence["self_model_projection_digest"] for request in cognition} == {
        self_model.projection_digest}
    assert {request.upstream_evidence["epistemic_projection_digest"] for request in cognition} == {
        epistemic.projection_digest}
    assert result.changed_cognition_measurement_id is not None


def test_tick_n_admitted_developmental_writeback_is_durable_and_bounded(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    result = composition.run_tick(snapshot=snapshot(), tick_id="tick-n")
    assert result.status == "completed" and result.written_record_id and result.writeback_receipt_id
    assert len(result.selected_fact_ids) == 1
    selected = next(f for f in snapshot().facts if f.fact_id == result.selected_fact_ids[0])
    assert selected.source.kind == "capability_registry"
    assert not result.prior_record_ids and result.same_tick_history_excluded
    assert [r.purpose for r in fake.requests] == ["resident_developmental_interpretation"]
    assert composition.writeback.store.get(result.written_record_id).current_truth is False
    assert composition.writeback.store.get_receipt(result.writeback_receipt_id).storage_verified


def test_restart_recovers_writeback_committed_before_composition_checkpoint(tmp_path: Path) -> None:
    interrupted, _fake = owner(tmp_path)
    save_state = interrupted._save_state

    def interrupt_final_checkpoint(state):
        if state["completed_ticks"]:
            raise ResidentDevelopmentalCognitionError("simulated_after_writeback_before_checkpoint")
        save_state(state)

    interrupted._save_state = interrupt_final_checkpoint
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="simulated_after_writeback_before_checkpoint"):
        interrupted.run_tick(snapshot=snapshot(), tick_id="tick-interrupted")

    durable_records = interrupted.writeback.store.records()
    assert len(durable_records) == 1
    durable_receipts = interrupted.writeback.store.receipts()
    assert len(durable_receipts) == 1

    restarted, fake = owner(tmp_path)
    recovered = restarted._state()
    checkpoint = next(row for row in recovered["completed_ticks"]
                      if row["tick_id"] == "tick-interrupted")
    assert checkpoint["record_id"] == durable_records[0].record_id
    assert checkpoint["receipt_id"] == durable_receipts[0].receipt_id
    assert not any(row.get("tick_id") == "tick-interrupted"
                   for row in recovered["incomplete_ticks"])
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="tick-interrupted")

    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-following")
    assert later.prior_record_ids == (durable_records[0].record_id,)
    assert any(request.purpose == "resident_developmental_retrieval_cognition"
               for request in fake.requests)


def test_same_tick_record_is_prohibited_from_retrieval(tmp_path: Path) -> None:
    composition, _ = owner(tmp_path)
    first = composition.run_tick(snapshot=snapshot(), tick_id="tick-n")
    assert first.written_record_id not in first.prior_record_ids
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        composition.run_tick(snapshot=snapshot(), tick_id="tick-n")


def test_restart_tick_n_plus_one_retrieves_prior_history_for_cognition(tmp_path: Path) -> None:
    first, _ = owner(tmp_path)
    written = first.run_tick(snapshot=snapshot(), tick_id="tick-n").written_record_id
    restarted, fake = owner(tmp_path)
    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-n-plus-one")
    assert later.prior_record_ids == (written,)
    assert len(later.cognition_observation_ids) == 1
    cognition = [r for r in fake.requests if r.purpose == "resident_developmental_retrieval_cognition"]
    assert cognition[0].upstream_evidence["record_ids"] == [written]
    observation = json.loads(next(restarted.observations_root.glob("*.json")).read_text())
    assert observation["historical_context_only"] and not observation["authority"]
    assert not observation["canonical_explicit_user_retention"]


def test_controlled_with_record_and_withheld_comparison_is_opt_in_and_difference_only(tmp_path: Path) -> None:
    first, _ = owner(tmp_path); first.run_tick(snapshot=snapshot(), tick_id="tick-n")
    restarted, fake = owner(tmp_path, comparison=True)
    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-n-plus-one")
    cognition = [r for r in fake.requests if r.purpose == "resident_developmental_history_intervention_experiment" and "history_present" in r.linkage]
    assert [r.linkage["history_present"] for r in cognition] == [True, False, True]
    assert cognition[0].upstream_evidence["snapshot_digest"] == cognition[1].upstream_evidence["snapshot_digest"]
    assert later.changed_cognition_measurement_id
    measured = json.loads((restarted.experiments.runs / f"{later.changed_cognition_measurement_id}.json").read_text())
    assert measured["summary"]["present_vs_withheld_difference_observed"] is True
    assert measured["summary"]["classification"] == "history_presence_associated_stable_difference"


def test_repeated_current_evidence_does_not_reinterpret_after_history_changes(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-2")
    later = composition.run_tick(snapshot=snapshot(), tick_id="tick-3")
    assert later.written_record_id is not None
    record = composition.writeback.store.get(later.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] == "history_conditioned_cognition_conclusion:v1"
    assert len([r for r in fake.requests if r.purpose == "resident_developmental_interpretation"]) == 1
    assert len([r for r in fake.requests if r.purpose == "resident_developmental_retrieval_cognition"]) == 2


def test_missing_or_crossed_admission_prevents_history_mutation(tmp_path: Path) -> None:
    composition, _ = owner(tmp_path)
    composition.admission_authority = type("Missing", (), {"issue": lambda *a, **k: None})()
    with pytest.raises((AttributeError, ValueError)):
        composition.run_tick(snapshot=snapshot(), tick_id="tick-missing")
    assert not list((tmp_path / "history" / "records").glob("*.json"))


def test_configuration_is_exact_and_malformed_configuration_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    valid = {"schema":CONFIG_SCHEMA, "enabled":False, "history_root":str(tmp_path / "history"),
             "state_root":str(tmp_path / "state"), "allowed_source_kinds":["capability_registry"],
             "max_selected_facts":1, "max_retrieved_records":2, "comparison_enabled":False}
    path.write_text(json.dumps(valid)); assert load_config(path).enabled is False
    path.write_text(json.dumps({**valid, "personality":"helpful"}))
    with pytest.raises(ResidentDevelopmentalCognitionError, match="shape_invalid"): load_config(path)


def test_sentientosd_preserves_exact_snapshot_and_absent_config_is_inert(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG", raising=False)
    surfaces = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime")
    feedback = surfaces.build_world_state_board(tick_id="2026-01-01T00:00:00+00:00")
    exact = surfaces.current_world_state_snapshot
    assert exact is not None and exact.snapshot_id == feedback["snapshot_id"]
    assert surfaces.run_resident_developmental_cognition(tick_id="2026-01-01T00:00:00+00:00")["status"] == "disabled"

    class Spy:
        seen = None
        def run_tick(self, *, snapshot, tick_id, **_kwargs):
            self.seen = snapshot
            return type("Result", (), {"__dataclass_fields__": {}, "status":"completed"})()
    spy = Spy()
    injected = RuntimeMaintenanceSurfaces(tmp_path, runtime_state_root=tmp_path / "runtime-2",
                                          resident_developmental_owner=spy)  # type: ignore[arg-type]
    injected.build_world_state_board(tick_id="2026-01-02T00:00:00+00:00")
    # The injected owner receives object identity, not a JSON reconstruction.
    try:
        injected.run_resident_developmental_cognition(tick_id="2026-01-02T00:00:00+00:00")
    except TypeError:
        pass
    assert spy.seen is injected.current_world_state_snapshot


def test_sentientosd_composes_explicit_prior_epistemic_projection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SENTIENTOS_EPISTEMIC_STATE_CONFIG", raising=False)
    epistemic=PersistentEpistemicStateOwner(tmp_path/"epistemic",allowed_namespaces=["embodiment"])
    p=make_proposition(namespace="embodiment",subject="body:g1",predicate="healthy",
        object_value=True,polarity="positive",qualifiers={},temporal_scope={"kind":"prior"},
        context_scope={},proposition_class="descriptive")
    epistemic.register_proposition(p)
    epistemic.commit_update(proposition_id=p.proposition_id,expected_predecessor_digest=None,
        stance="unknown",reason="initialization",active_binding_ids=[],correlation_id="prior",tick=1,
        recorded_at="2026-01-01T00:00:00Z")
    class Spy:
        seen = None
        def run_tick(self, **kwargs):
            self.seen = kwargs
            return type("Result", (), {"__dataclass_fields__": {}, "status":"completed"})()
    spy=Spy()
    surfaces=RuntimeMaintenanceSurfaces(tmp_path,runtime_state_root=tmp_path/"runtime-epistemic",
        resident_developmental_owner=spy,epistemic_state_owner=epistemic,
        epistemic_state_config={"status":"configured","max_cognitive_projection_count":1,
                                "cognitive_consumption_enabled":True})  # type: ignore[arg-type]
    tick="2026-01-03T00:00:00+00:00"
    surfaces.build_world_state_board(tick_id=tick)
    feedback=surfaces.run_resident_developmental_cognition(tick_id=tick)
    projection=spy.seen["prior_epistemic_state"]
    assert projection.proposition_ids == (p.proposition_id,)
    assert feedback["epistemic_composition"]["status"] == "composed"
    assert feedback["epistemic_composition"]["authority"] is False


def test_epistemic_runtime_configuration_is_explicit_exact_and_independently_disabled(tmp_path: Path) -> None:
    assert _load_epistemic_state_owner(None) == (None, {"status":"disabled", "cognitive_consumption_enabled":False})
    path=tmp_path/"epistemic-config.json"
    payload={"schema":"sentientos.epistemic_runtime_config:v1","custody_root":str(tmp_path/"custody"),
        "allowed_proposition_namespaces":["embodiment"],"max_cognitive_projection_count":2,
        "cognitive_consumption_enabled":False}
    path.write_text(json.dumps(payload))
    configured, status=_load_epistemic_state_owner(str(path))
    assert configured is not None and status == {"status":"configured","max_cognitive_projection_count":2,
                                                  "cognitive_consumption_enabled":False}
    path.write_text(json.dumps({**payload,"ambient_discovery":True}))
    with pytest.raises(ValueError,match="configuration_invalid"):
        _load_epistemic_state_owner(str(path))



def test_recovered_history_order_uses_intent_not_wall_clock() -> None:
    from types import SimpleNamespace

    first = SimpleNamespace(
        created_at="2026-02-02T00:00:00+00:00",
        correlation_id="tick-first:resident-developmental-writeback",
        record_id="record-first")
    second = SimpleNamespace(
        created_at="2026-01-01T00:00:00+00:00",
        correlation_id="tick-second:resident-developmental-writeback",
        record_id="record-second")
    order = {"tick-first": 0, "tick-second": 1}
    first_key = ResidentDevelopmentalCognitionOwner._recovered_record_order(
        first, completed_order={}, recovery_intent_order=order)
    second_key = ResidentDevelopmentalCognitionOwner._recovered_record_order(
        second, completed_order={}, recovery_intent_order=order)
    assert first_key < second_key


def test_developmental_roots_resolve_aliases_and_exclude_canonical_memory(tmp_path: Path) -> None:
    import os

    from sentientos.canonical_memory import sentientos_memory_dir
    from sentientos.resident_developmental_cognition import _validate_root_separation

    if os.name == "posix":
        history = tmp_path / "history"
        history.mkdir()
        alias = tmp_path / "history-alias"
        alias.symlink_to(history, target_is_directory=True)
        with pytest.raises(ResidentDevelopmentalCognitionError,
                           match="configuration_roots_must_be_separate"):
            _validate_root_separation(history, alias, memory_root=tmp_path / "memory")

    memory = sentientos_memory_dir()
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="configuration_root_overlaps_canonical_memory"):
        _validate_root_separation(memory / "developmental-history", tmp_path / "state",
                                  memory_root=memory)

    # Reject the opposite nesting direction too: a developmental owner must
    # not claim a parent directory that also contains canonical user memory.
    memory_child = tmp_path / "owner-root" / "user-memory"
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="configuration_root_overlaps_canonical_memory"):
        _validate_root_separation(tmp_path / "owner-root", tmp_path / "other-state",
                                  memory_root=memory_child)


def test_cognition_checkpoint_round_trips_through_private_descriptor_custody(tmp_path: Path) -> None:
    import os
    import stat

    if os.name != "posix":
        pytest.skip("cognition checkpoint publication requires POSIX custody")
    cognition, _ = owner(tmp_path)
    state = cognition._state()
    cognition._save_state(state)

    metadata = cognition.state_path.stat()
    root_metadata = cognition.state_path.parent.stat()
    assert stat.S_ISREG(metadata.st_mode)
    assert metadata.st_uid == os.geteuid()
    assert metadata.st_mode & 0o077 == 0
    assert root_metadata.st_uid == os.geteuid()
    assert root_metadata.st_mode & 0o022 == 0
    assert cognition._state() == state


def test_cognition_checkpoint_rejects_replaced_symlink_root(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("no-follow checkpoint publication requires POSIX")
    from sentientos.resident_developmental_cognition import _replace_cognition_state

    target = tmp_path / "external"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="composition_state_publication_failed"):
        _replace_cognition_state(alias / "composition_state.json", {"state": "bounded"})
    assert list(target.iterdir()) == []


def test_concurrent_developmental_ticks_cannot_replay_one_tick(tmp_path: Path) -> None:
    import os
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    if os.name != "posix":
        pytest.skip("POSIX cognition tick lock is required")
    first, _ = owner(tmp_path)
    second, _ = owner(tmp_path)
    tick_snapshot = WorldStateBoardBuilder().build([])
    barrier = Barrier(2)

    def run(owner_instance):
        barrier.wait()
        return owner_instance.run_tick(snapshot=tick_snapshot, tick_id="one-shared-tick")

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(run, first)
        right = pool.submit(run, second)
        results = []
        for future in (left, right):
            try:
                results.append(future.result())
            except ResidentDevelopmentalCognitionError as exc:
                results.append(str(exc))

    assert sum(getattr(result, "status", None) == "completed" for result in results) == 1
    assert results.count("tick_already_completed") == 1


def test_actual_history_conditioned_conclusion_is_the_retained_candidate(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path / "one")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")

    assert result.written_record_id and result.writeback_receipt_id
    record = composition.writeback.store.get(result.written_record_id)
    candidate = record.candidate
    provenance = candidate["transformation_provenance"]
    assert provenance["kind"] == "history_conditioned_cognition_conclusion:v1"
    assert candidate["interpretation"] == fake.lesson_statement
    assert provenance["lesson_candidate"]["scope"] == fake.lesson_scope
    assert provenance["source_output_digest"] == candidate["output_digest"]
    assert digest_payload({"output": provenance["source_output_text"]}) == candidate["output_digest"]
    assert provenance["observation_id"] in result.cognition_observation_ids
    assert provenance["consumed_context"]["retrieved_record_ids"] == list(result.prior_record_ids)
    assert candidate["inference_receipt_id"] != ""
    # The candidate reuses the cognition call. Only the first tick's existing
    # current-evidence interpretation call occurred; no lesson-only call was added.
    assert [request.purpose for request in fake.requests] == [
        "resident_developmental_interpretation",
        "resident_developmental_retrieval_cognition",
    ]


def test_distinct_actual_conclusions_produce_distinct_bound_candidates(tmp_path: Path) -> None:
    records = []
    for label in ("lesson-alpha", "lesson-beta"):
        root = tmp_path / label
        composition, fake = owner(root)
        composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
        fake.lesson_statement = label
        result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
        records.append(composition.writeback.store.get(result.written_record_id))
    left, right = (record.candidate for record in records)
    assert left["interpretation"] == "lesson-alpha"
    assert right["interpretation"] == "lesson-beta"
    assert left["candidate_id"] != right["candidate_id"]
    assert left["candidate_digest"] != right["candidate_digest"]
    assert left["transformation_provenance"]["source_output_text"] != right["transformation_provenance"]["source_output_text"]


def test_retained_cognition_lesson_reaches_later_tick_after_restart(tmp_path: Path) -> None:
    first, fake = owner(tmp_path)
    first.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.lesson_statement = "Later reasoning should revisit the bounded cited condition."
    retained = first.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = first.writeback.store.get(retained.written_record_id)
    restarted, later_fake = owner(tmp_path)
    later = restarted.run_tick(snapshot=snapshot(3), tick_id="tick-3")
    assert record.record_id in later.prior_record_ids
    prompt = json.loads(next(
        request.prompt for request in later_fake.requests
        if request.purpose == "resident_developmental_retrieval_cognition"))
    history_packet = next(item for item in prompt["developmental_history"]
        if item["record_id"] == record.record_id)
    assert {"record_id": record.record_id,
        "record_digest": record.record_digest} in prompt[
            "developmental_history_selection"]["selected_records"]
    assert history_packet["interpretation"] == record.candidate["interpretation"]
    lesson = record.candidate["transformation_provenance"]["lesson_candidate"]
    assert history_packet["scope"] == lesson["scope"]
    assert history_packet["applicability"] == lesson["applicability"]
    assert history_packet["current_truth"] is False
    assert "source_output_text" not in json.dumps(prompt)
    assert "Later reasoning should revisit the bounded cited condition." in json.dumps(prompt)
    assert "authority" not in record.candidate and "current_truth" not in record.candidate
    assert record.epistemic_posture == "historical_interpretation_not_current_truth"


def test_unconsumed_evidence_citation_does_not_become_a_cognition_candidate(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.lesson_dependency_override = "fabricated-source-id"
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] != "history_conditioned_cognition_conclusion:v1"
    assert any(request.purpose == "resident_developmental_interpretation" for request in fake.requests)


def test_truncated_cognition_output_never_manufactures_retained_lesson(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.truncate_cognition_output = True
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] != "history_conditioned_cognition_conclusion:v1"


def test_recovered_candidate_requires_its_exact_durable_cognition_observation(tmp_path: Path) -> None:
    composition, _fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    candidate = composition.writeback.store.get(result.written_record_id).candidate
    observation_path = composition.observations_root / f"{candidate['transformation_provenance']['observation_id']}.json"
    observation = json.loads(observation_path.read_text())
    observation["output_digest"] = "sha256:" + "0" * 64
    observation_path.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\\n")
    restarted, _ = owner(tmp_path)
    with pytest.raises(ResidentDevelopmentalCognitionError, match="cognition_observation"):
        restarted._state()


def test_experimental_history_arms_do_not_retain_cognition_lessons(tmp_path: Path) -> None:
    first, _ = owner(tmp_path)
    first.run_tick(snapshot=snapshot(), tick_id="tick-1")
    experimental, fake = owner(tmp_path, comparison=True)
    experimental.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    experiment_calls = [request for request in fake.requests
        if request.purpose == "resident_developmental_history_intervention_experiment"
        and "history_present" in request.linkage]
    assert len(experiment_calls) == 3
    assert all(request.expected_output_format == "text" for request in experiment_calls)
    assert all(request.to_receipt_request_dict().get("structured_output_schema") is None
        for request in experiment_calls)
    records = experimental.writeback.store.records()
    assert all(record.candidate["transformation_provenance"].get("kind")
        != "history_conditioned_cognition_conclusion:v1" for record in records)


def test_cognition_lesson_writeback_is_later_tick_only_and_recovery_is_idempotent(tmp_path: Path) -> None:
    first, _fake = owner(tmp_path)
    first.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = first.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = first.writeback.store.get(result.written_record_id)
    assert record.record_id not in result.prior_record_ids
    restarted, fake = owner(tmp_path)
    recovered = restarted._state()
    assert any(row["tick_id"] == "tick-2" and row["record_id"] == record.record_id
        for row in recovered["completed_ticks"])
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    later = restarted.run_tick(snapshot=snapshot(3), tick_id="tick-3")
    assert record.record_id in later.prior_record_ids
    assert any(request.purpose == "resident_developmental_retrieval_cognition"
        for request in fake.requests)


def test_modified_output_and_crossed_request_identity_are_rejected(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path / "modified")
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.modify_cognition_output_after_digest = True
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] != "history_conditioned_cognition_conclusion:v1"

    crossed, crossed_fake = owner(tmp_path / "crossed")
    crossed.run_tick(snapshot=snapshot(), tick_id="tick-1")
    crossed_fake.cross_cognition_request_identity = True
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="cognition_epistemic_receipt_binding_mismatch"):
        crossed.run_tick(snapshot=snapshot(2), tick_id="tick-2")


def test_out_of_scope_length_and_substituted_evidence_are_not_retained(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.lesson_scope = "x" * 401
    fake.lesson_dependency_override = "different-unconsumed-evidence"
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"]["kind"] != "history_conditioned_cognition_conclusion:v1"


def test_interruption_after_cognition_observation_does_not_reinfer_or_fabricate_candidate(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")

    def interrupt_candidate(*_args, **_kwargs):
        raise RuntimeError("interrupted_before_candidate_commit")

    composition.writeback.candidate_from_history_conditioned_cognition = interrupt_candidate
    with pytest.raises(RuntimeError, match="interrupted_before_candidate_commit"):
        composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    assert len(list(composition.observations_root.glob("*.json"))) == 1

    restarted, restarted_fake = owner(tmp_path)
    recovered = restarted._state()
    interrupted = next(row for row in recovered["incomplete_ticks"] if row["tick_id"] == "tick-2")
    assert interrupted["status"] == "interrupted_recovered"
    assert not restarted_fake.requests
    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    assert not restarted_fake.requests


def test_candidate_record_committed_before_checkpoint_recovers_once(tmp_path: Path) -> None:
    composition, _fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    save_state = composition._save_state

    def interrupt_final_checkpoint(state):
        if (state["completed_ticks"]
                and state["completed_ticks"][-1]["tick_id"] == "tick-2"):
            raise ResidentDevelopmentalCognitionError("simulated_after_candidate_before_checkpoint")
        save_state(state)

    composition._save_state = interrupt_final_checkpoint
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="simulated_after_candidate_before_checkpoint"):
        composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")

    durable = composition.writeback.store.records()
    assert len(durable) == 2
    candidate_record = next(record for record in durable
        if record.candidate["transformation_provenance"].get("kind")
        == "history_conditioned_cognition_conclusion:v1")
    restarted, fake = owner(tmp_path)
    recovered = restarted._state()
    assert any(row["record_id"] == candidate_record.record_id
        and row["tick_id"] == "tick-2" for row in recovered["completed_ticks"])
    later = restarted.run_tick(snapshot=snapshot(3), tick_id="tick-3")
    assert candidate_record.record_id in later.prior_record_ids
    assert any(request.purpose == "resident_developmental_retrieval_cognition"
        for request in fake.requests)


def test_null_lesson_packet_is_not_automatically_retained(tmp_path: Path) -> None:
    composition, fake = owner(tmp_path)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    fake.no_cognition_lesson = True
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"].get("kind") != "history_conditioned_cognition_conclusion:v1"
    assert any(request.purpose == "resident_developmental_interpretation"
        for request in fake.requests)


class HermeticCognitionBackend:
    """Local deterministic model substitute used behind the real governed invoker."""

    def __init__(self, statement: str = "Preserve the cited historical condition.") -> None:
        self.statement = statement
        self.calls: list[str] = []
        self.no_lesson = False

    def generate(self, prompt: str, **kwargs) -> str:
        self.calls.append(prompt)
        schema = kwargs.get("structured_output_schema")
        required = set(schema.get("required", ())) if isinstance(schema, dict) else set()
        if required == {"interpretation", "uncertainty"}:
            return json.dumps({"interpretation": "bounded current evidence",
                               "uncertainty": "medium"})
        context = json.loads(prompt)
        history = context.get("developmental_history", [])
        evidence_ids = [str(item["record_id"]) for item in history
                        if isinstance(item, dict) and isinstance(item.get("record_id"), str)]
        current = context.get("current_evidence", {})
        evidence_ids.extend(str(item["fact_id"]) for item in current.get("facts", [])
                            if isinstance(item, dict) and isinstance(item.get("fact_id"), str))
        return json.dumps({
            "conclusion": "I conclude: " + self.statement,
            "lesson_candidate": None if self.no_lesson else {
                "statement": self.statement,
                "scope": "the cited historical context",
                "applicability": "only while the cited conditions remain applicable",
                "uncertainty": "medium",
                "uncertainty_rationale": "the source is an interpretation of retained evidence",
                "evidence_dependencies": evidence_ids[:1],
                "possible_contradiction_ids": [],
            },
        }, sort_keys=True)


def governed_owner(root: Path, *, backend: HermeticCognitionBackend, comparison: bool = False):
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "fixture.gguf"
    model_path.write_bytes(b"hermetic local backend fixture")
    model_config = ModelConfig(
        candidates=[ModelCandidate(path=model_path, engine="llama_cpp", name="fixture")],
        generation=GenerationConfig(max_new_tokens=512),
    )
    authority_map = build_local_model_authority_map(model_config, allowed_roots=[root])
    invoker = GovernedLocalModelInvoker(
        model=backend, authority_map=authority_map,
        kernel=ControlPlaneKernel(phase=LifecyclePhase.RUNTIME,
            decisions_path=root / "control-plane-decisions.jsonl"),
        runtime_root=root / "invocation-custody",
    )
    ledger = AdmissionLedger(root / "state" / "admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK: RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}

    def current_sequence():
        admissions, revocations = ledger.load()
        return max([item.issued_sequence for item in admissions]
                   + [item.sequence for item in revocations], default=1)

    def next_sequence():
        return current_sequence() + 1

    writeback = ResidentDevelopmentalWritebackController(
        history_root=root / "history",
        admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
        current_sequence=current_sequence,
    )
    owner_value = ResidentDevelopmentalCognitionOwner(
        config=ResidentDevelopmentalCognitionConfig(
            root / "history", root / "state", ("capability_registry",), 1, 4, comparison),
        writeback=writeback,
        admission_authority=RuntimeAdmissionAuthority(definitions=definitions, ledger=ledger),
        invoker=invoker,
        current_sequence=next_sequence,
    )
    return owner_value, invoker


def test_real_governed_invocation_output_is_retained_without_a_lesson_only_call(tmp_path: Path) -> None:
    backend = HermeticCognitionBackend("keep the observation's original scope")
    composition, invoker = governed_owner(tmp_path, backend=backend)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")

    record = composition.writeback.store.get(result.written_record_id)
    candidate = record.candidate
    provenance = candidate["transformation_provenance"]
    assert provenance["kind"] == "history_conditioned_cognition_conclusion:v1"
    assert candidate["interpretation"] == backend.statement
    assert candidate["model_id"] == provenance["source_request"]["model_id"]
    assert candidate["request_digest"] == provenance["source_request"]["request_digest"]
    assert provenance["source_output_text"].startswith('{"conclusion":')
    assert digest_payload({"output": provenance["source_output_text"]}) == candidate["output_digest"]
    # Tick one uses the existing interpretation request; tick two uses one
    # history-conditioned call whose exact output becomes the candidate.
    assert len(backend.calls) == 2
    assert result.cognition_observation_ids == (provenance["observation_id"],)


def test_real_invoker_retains_distinct_lessons_and_later_tick_reads_them(tmp_path: Path) -> None:
    backend = HermeticCognitionBackend("lesson A")
    composition, _invoker = governed_owner(tmp_path, backend=backend)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    first = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    first_record = composition.writeback.store.get(first.written_record_id)
    assert first_record.candidate["interpretation"] == "lesson A"

    backend.statement = "lesson B"
    restarted, _ = governed_owner(tmp_path, backend=backend)
    second = restarted.run_tick(snapshot=snapshot(3), tick_id="tick-3")
    second_record = restarted.writeback.store.get(second.written_record_id)
    assert second_record.candidate["interpretation"] == "lesson B"
    assert first_record.candidate["candidate_id"] != second_record.candidate["candidate_id"]
    assert first_record.record_id in second.prior_record_ids

    later_backend = HermeticCognitionBackend("later conclusion")
    later_owner, _ = governed_owner(tmp_path, backend=later_backend)
    later = later_owner.run_tick(snapshot=snapshot(4), tick_id="tick-4")
    assert second_record.record_id in later.prior_record_ids
    assert any(second_record.record_id in prompt for prompt in later_backend.calls)


def test_real_invoker_null_candidate_does_not_turn_the_conclusion_into_a_lesson(tmp_path: Path) -> None:
    backend = HermeticCognitionBackend("conclusion with no scoped lesson")
    backend.no_lesson = True
    composition, _ = governed_owner(tmp_path, backend=backend)
    composition.run_tick(snapshot=snapshot(), tick_id="tick-1")
    result = composition.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    record = composition.writeback.store.get(result.written_record_id)
    assert record.candidate["transformation_provenance"].get("kind") != "history_conditioned_cognition_conclusion:v1"
    assert len(backend.calls) == 3


def test_missing_output_text_and_substituted_scope_never_create_a_candidate(tmp_path: Path) -> None:
    missing, missing_fake = owner(tmp_path / "missing")
    missing.run_tick(snapshot=snapshot(), tick_id="tick-1")
    missing_fake.unavailable_cognition_output = True
    missing_result = missing.run_tick(snapshot=snapshot(2), tick_id="tick-2")
    missing_record = missing.writeback.store.get(missing_result.written_record_id)
    assert missing_record.candidate["transformation_provenance"].get("kind") != "history_conditioned_cognition_conclusion:v1"

    scoped, _ = owner(tmp_path / "scope")
    scoped.run_tick(snapshot=snapshot(), tick_id="tick-1")
    original = scoped.writeback.candidate_from_history_conditioned_cognition

    def substitute_scope(selection, receipt, **kwargs):
        altered = dict(kwargs["lesson_payload"])
        altered_lesson = dict(altered["lesson_candidate"])
        altered_lesson["scope"] = "substituted scope"
        altered["lesson_candidate"] = altered_lesson
        kwargs["lesson_payload"] = altered
        return original(selection, receipt, **kwargs)

    scoped.writeback.candidate_from_history_conditioned_cognition = substitute_scope
    with pytest.raises(DevelopmentalWritebackError, match="cognition_lesson_output_invalid"):
        scoped.run_tick(snapshot=snapshot(2), tick_id="tick-2")
