from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from sentientos.developmental_model_replacement_experiment import ModelReplacementArtifactStore
from sentientos.developmental_model_replacement_rehearsal import _load, prepare, run_next
from sentientos.codex_task_authority_admission import (
    RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
)
from sentientos.governed_local_model_resource_allocation import (
    GovernedLocalModelResourceBounds,
    GovernedLocalModelResourcePolicy,
)
from sentientos.host_resource_runtime import (
    resource_consumption_world_state_records,
    resource_invocation_proposal_lineage_records,
)
from sentientos.local_model_authority import digest_payload
from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    produce_production_chat_resource_provisioning_bundle,
)
from sentientos.persistent_epistemic_state import PersistentEpistemicStateOwner
from sentientos.resident_epistemic_state_mutation import ResidentEpistemicStateMutationController
from sentientos.runtime_admission import RuntimeAdmissionVerifier
from sentientosd import RuntimeMaintenanceSurfaces
from tests.test_resident_developmental_cognition import owner as developmental_owner
from tests.test_resident_epistemic_development import fixture as epistemic_fixture
from tests.test_production_chat_resource_provisioning_bundle_producer import inputs
from sentientos.world_state_board import WorldStateBoardBuilder, record_digest

pytestmark = pytest.mark.no_legacy_skip


def test_model_replacement_invocations_reconcile_to_preissued_resource_owner(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust" / "state.json"))
    # These existing singleton owners snapshot their roots during construction.
    # Rebuild them after assigning this test's isolated custody roots.
    from sentientos.federated_governance import reset_controller
    from sentientos.runtime_governor import reset_runtime_governor
    from sentientos.trust_ledger import reset_trust_ledger

    reset_controller()
    reset_runtime_governor()
    reset_trust_ledger()
    resource_installation, provisioning = inputs(tmp_path / "resources", calls=5)
    bounds = GovernedLocalModelResourceBounds(8192, 8192, 32, 30.0, 5)
    policy = GovernedLocalModelResourcePolicy.create(
        epoch=1,
        max_resource_specific_bounds=bounds,
        not_before="2026-09-21T08:00:00Z",
        valid_until="2026-09-21T09:15:00Z",
    )
    provisioning["requested_bounds"] = bounds
    provisioning["resource_policy_artifact"] = (
        json.dumps(policy.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    allocation = produce_production_chat_resource_provisioning_bundle(
        resource_installation, "replacement-trial", **provisioning
    )
    nonce_values = iter(f"replacement-attempt-{index}" for index in range(1, 6))
    owner = load_production_chat_resource_context_owner(
        resource_installation,
        "replacement-trial",
        clock=lambda: "2026-09-21T08:30:00Z",
        nonce_source=lambda: next(nonce_values),
    )

    experiment_root = tmp_path / "model-replacement"
    try:
        scenario = prepare(experiment_root, objective_scored=True)
        completed = run_next(experiment_root, resource_context_owner=owner)
        assert completed["status"] == "completed_one_trial", completed
        run = completed["result"]
        observations = run["observations"]
        assert len(observations) == 5
        assert all(row["resource_allocation_digest"] == allocation.allocation_digest for row in observations)
        assert all(row["resource_attempt_id"] for row in observations)
        assert all(len(row["resource_consumption_receipt_digests"]) == 2 for row in observations)
        assert all(row["resource_linkage_digest"] for row in observations)
        assert owner.allocator.ledger.remaining_calls(allocation.allocation_id) == 0

        _bundle, installation, _scenario, _context, _pa, _pb = _load(experiment_root)
        receipts = []
        for observation in observations:
            receipt_path = installation.fixed_object(
                "local-model/developmental-model-replacement/experimental-serving/inference/receipts/"
                + observation["inference_receipt_id"] + ".json"
            )
            receipt = json.loads(installation.read_regular(receipt_path).decode("utf-8"))
            assert receipt["receipt_digest"] == observation["inference_receipt_digest"]
            receipts.append(receipt)

        resource_records = resource_consumption_world_state_records(
            ledger=owner.allocator.ledger,
            invocation_receipts=tuple(receipts),
        )
        replacement_records = ModelReplacementArtifactStore(
            experiment_root / "rehearsal"
        ).world_state_records(run_refs=((run["run_id"], run["run_digest"]),))
        joined = resource_invocation_proposal_lineage_records(
            [*resource_records, *replacement_records]
        )
        assert len(joined) == 5
        assert all(row["disposition"] == "verified" for row in joined), [
            (row["disposition"], row["payload"].get("lineage_findings")) for row in joined
        ]
        assert all(row["effect_claimed"] is False and row["effect_proven"] is False for row in joined)
        assert all(row["payload"]["shared_host_cpu_gpu_attribution"]
            == "unknown_without_independent_observation" for row in joined)
        assert all(row["payload"]["resource_linkage"]["allocation_digest"] == allocation.allocation_digest
            for row in joined)
        assert {row["payload"]["resource_linkage"]["effect_receipt_digest"] for row in joined} == {
            row["inference_receipt_digest"] for row in observations
        }
        assert {row["payload"]["model_replacement_run_digest"] for row in joined} == {run["run_digest"]}
        assert {row["payload"]["model_identity_digest"] for row in joined} == {
            scenario["model_a_identity_digest"], scenario["model_b_identity_digest"]
        }
        assert {row["payload"]["model_attribution"]["model_id"] for row in joined} == {
            row["model_id"] for row in observations
        }
        assert {row["payload"]["model_attribution"]["invocation_authority_map_digest"] for row in joined} == {
            row["request"]["authority_map_digest"] for row in receipts
        }
        assert all(row["payload"]["model_attribution"]["invocation_model_id"].startswith("lma-")
            for row in joined)
        assert all(row["payload"]["software_attribution"]["generation_posture"]
            == "not_bound_by_selected_protocol" for row in joined)
        assert all(row["payload"]["task_outcome"]["posture"]
            == "run_owner_score_bound_to_condition" for row in joined)
        assert all(row["payload"]["task_outcome"]["inference_receipt_id"]
            == row["payload"]["resource_linkage"]["effect_receipt_id"] for row in joined)
        assert all(row["payload"]["task_outcome"]["oracle_answer_retained"] is False
            and row["payload"]["task_outcome"]["causal_effect_established"] is False
            for row in joined)

        # Compose the same ledger, exact invocation receipts, and model-run
        # artifact through the daemon's actual configured World-State path.
        # Then admit historical evidence, append developmental history, and
        # verify restart plus later-tick retrieval through the existing owner.
        epistemic_root = tmp_path / "composed-epistemics"
        epistemic_state, proposition, admission_ledger, development = epistemic_fixture(
            epistemic_root)
        development_rule = replace(development.config.rules[0], selector={
            "source_kind": "resource_governor",
            "subject_kind": "model_replacement_invocation_resource_lineage",
            "stage": "observation", "disposition": "verified"})
        development.config = replace(development.config, rules=(development_rule,))
        surfaces = RuntimeMaintenanceSurfaces(
            tmp_path, runtime_state_root=tmp_path / "composed-runtime",
            governed_resource_ledger=owner.allocator.ledger,
            governed_invocation_receipts=tuple(receipts),
            longitudinal_self_model_owner=LongitudinalSelfModelOwner(
                tmp_path / "composed-self-model"),
            model_replacement_artifact_store=ModelReplacementArtifactStore(
                experiment_root / "rehearsal"),
            model_replacement_run_refs=((run["run_id"], run["run_digest"]),),
            epistemic_state_owner=epistemic_state,
            epistemic_state_config={"status": "configured",
                "cognitive_consumption_enabled": True,
                "max_cognitive_projection_count": 8},
            epistemic_development_runtime=development)
        tick_n = "2026-09-21T08:40:00+00:00"
        world_state_feedback = surfaces.build_world_state_board(tick_id=tick_n)
        snapshot = surfaces.current_world_state_snapshot
        assert snapshot is not None
        history_lineage_facts = [fact for fact in snapshot.facts
            if fact.subject.subject_kind == "model_replacement_invocation_resource_lineage"]
        assert len(history_lineage_facts) == 5
        assert all(fact.source.finding == "ok" and fact.disposition == "verified"
            for fact in history_lineage_facts)
        assert world_state_feedback["snapshot_id"] == snapshot.snapshot_id
        self_model_feedback = surfaces.reconcile_longitudinal_self_model(tick_id=tick_n)
        assert self_model_feedback["status"] == "ok"
        assert self_model_feedback["claim_count"] > 0
        assert self_model_feedback["authority"] is False
        self_model_owner = surfaces._longitudinal_self_model_owner
        assert self_model_owner is not None
        assert self_model_owner.cognitive_projection(before_tick=tick_n, max_claims=1,
            allowed_predicates=("developmental.model_replacement_interpretation",)) is None
        later_self_model = self_model_owner.cognitive_projection(
            before_tick="model-resource-history-tick-n-plus-one", max_claims=1,
            allowed_predicates=("developmental.model_replacement_interpretation",))
        assert later_self_model is not None
        developed = surfaces.run_epistemic_development(tick_id=tick_n)
        assert developed["status"] == "state_advanced"
        assert developed["next_tick_only"] is True and developed["authority"] is False
        bindings = epistemic_state.bindings(proposition.proposition_id)
        assert len(bindings) == 5
        assert all(binding.freshness != "current" for binding in bindings)
        assert all(binding.observation_time is not None for binding in bindings)
        tick_n_value = int(datetime.fromisoformat(tick_n).timestamp())
        assert epistemic_state.cognitive_projection(max_states=8,
            current_tick=tick_n_value) is None
        later_epistemic = epistemic_state.cognitive_projection(
            max_states=8, current_tick=tick_n_value + 1)
        assert later_epistemic is not None
        assert later_epistemic.source_tick == tick_n_value

        cognition_root = tmp_path / "composed-developmental-history"
        cognition, first_fixture = developmental_owner(
            cognition_root, allowed_source_kinds=("resource_governor",),
            max_selected_facts=1)
        lineage_record = next(row for row in joined
            if row["payload"].get("model_replacement_condition")
                == history_lineage_facts[0].payload.get("model_replacement_condition"))
        cognition_snapshot = WorldStateBoardBuilder(
            clock=lambda: datetime.fromisoformat(tick_n)).build([lineage_record])
        assert len(cognition_snapshot.facts) == 1
        assert cognition_snapshot.facts[0].source.digest == history_lineage_facts[0].source.digest
        first = cognition.run_tick(snapshot=cognition_snapshot,
            tick_id="model-resource-history-tick-n-plus-one",
            prior_epistemic_state=later_epistemic,
            prior_self_model=later_self_model)
        assert first.status == "completed"
        assert first.same_tick_history_excluded is True
        assert first.written_record_id is not None
        retained = cognition.writeback.store.get(first.written_record_id)
        assert retained.current_truth is False
        retained_resource_facts = [fact for fact in retained.candidate["selected_facts"]
            if fact["subject"]["subject_kind"]
                == "model_replacement_invocation_resource_lineage"]
        assert retained_resource_facts
        history_scope = __import__("sentientos.embodied_consequence",
            fromlist=["_history_evidence_scope"])._history_evidence_scope(
                {"candidate": retained.candidate})
        assert history_scope["posture"] in {
            "resource_invocation_lineage_history",
            "resource_invocation_lineage_history_context_bounded"}
        retained_binding = next(binding for binding in history_scope["resource_bindings"]
            if binding.get("lineage_subject_kind")
                == "model_replacement_invocation_resource_lineage")
        assert retained_binding["invocation_model_id"].startswith("lma-")
        assert retained_binding["cognitive_model_id"]
        assert retained_binding["allocation_identity"]["allocation_id"]
        assert retained_binding["allocation_identity"]["allocation_digest"] == allocation.allocation_digest
        assert retained_binding["principal_id"]
        task_context = retained_binding["task_context"]
        assert task_context["posture"] == "recorded_experiment_context_not_sponsorship"
        assert task_context["experiment_condition"] == retained_binding["succession_lineage"]["condition"]
        assert task_context["experiment_protocol_id"]
        assert isinstance(task_context["history_record_count"], int)
        assert isinstance(task_context["history_record_digest_count"], int)
        assert task_context["context_digest"].startswith("sha256:")
        substituted_score = deepcopy(lineage_record)
        substituted_score["payload"]["task_outcome"]["inference_receipt_digest"] = "substituted"
        substituted_score["digest"] = record_digest(substituted_score)
        substituted_score_board = WorldStateBoardBuilder().build([substituted_score])
        from sentientos.resident_developmental_writeback import DevelopmentalWritebackError
        with pytest.raises(DevelopmentalWritebackError,
                match="resource_task_outcome_projection_binding_invalid"):
            cognition.writeback.select_evidence(substituted_score_board,
                fact_ids=tuple(fact.fact_id for fact in substituted_score_board.facts))

        # Cross a real interpreter/process boundary after all three owners have
        # durably published. The child reconstructs their canonical stores and
        # runs later cognition; only the serialized source record and custody
        # roots cross the boundary, never an owner object or cached projection.
        child = r"""
import json, sys
from datetime import datetime
from pathlib import Path
from sentientos.codex_task_authority_admission import (
    RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION)
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.longitudinal_self_model import LongitudinalSelfModelOwner
from sentientos.persistent_epistemic_state import PersistentEpistemicStateOwner
from sentientos.production_chat_resource_observation import ProductionChatResourceObservationOwner
from sentientos.host_resource_runtime import (resource_consumption_world_state_records,
    resource_invocation_proposal_lineage_records)
from sentientos.developmental_model_replacement_experiment import ModelReplacementArtifactStore
from sentientosd import RuntimeMaintenanceSurfaces
from sentientos.resident_epistemic_state_mutation import ResidentEpistemicStateMutationController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionVerifier
from sentientos.world_state_board import WorldStateBoardBuilder
from tests.test_resident_developmental_cognition import owner as developmental_owner

data = json.load(sys.stdin)
ep_root = Path(data["epistemic_root"])
state = PersistentEpistemicStateOwner(ep_root / "epistemics", allowed_namespaces=("operator",))
ledger = AdmissionLedger(ep_root / "admissions.json")
definitions = {RESIDENT_EPISTEMIC_STATE_MUTATION: RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION}
def current():
    admissions, revocations = ledger.load()
    return max([item.issued_sequence for item in admissions] +
               [item.sequence for item in revocations], default=1)
ResidentEpistemicStateMutationController(owner=state,
    admission_verifier=RuntimeAdmissionVerifier(definitions=definitions, ledger=ledger),
    current_sequence=current, receipt_root=ep_root / "receipts")
projection = state.cognitive_projection(max_states=8, current_tick=data["epistemic_tick"])
self_model = LongitudinalSelfModelOwner(Path(data["self_model_root"])).cognitive_projection(
    before_tick=data["tick_id"], max_claims=1,
    allowed_predicates=("developmental.model_replacement_interpretation",))
registry = InstallationStateRegistry._for_testing(Path(data["installation_state_root"]))
handle = registry.open_read_only(InstallationIdentity.parse(data["installation_identity"]))
observer = ProductionChatResourceObservationOwner(handle, data["provisioning_id"])
surfaces = RuntimeMaintenanceSurfaces(Path(data["repo_root"]),
    runtime_state_root=Path(data["runtime_root"]),
    resource_observation_owner=observer,
    resource_observation_configuration_status={
        "status": "configured", "read_only": True, "effect_authority": False},
    model_replacement_artifact_store=ModelReplacementArtifactStore(
        Path(data["model_replacement_root"])),
    model_replacement_run_refs=((data["run_id"], data["run_digest"]),))
surfaces.build_world_state_board(tick_id=data["world_state_tick"])
board = surfaces.current_world_state_snapshot
assert board is not None
lineage_facts = [fact for fact in board.facts
    if fact.subject.subject_kind == "model_replacement_invocation_resource_lineage"]
assert len(lineage_facts) == 5
# Select the exact bounded producer record whose identity appears in the
# daemon-built board. The full projection remains in custody; cognition's
# configured per-tick selector receives one evidence fact.
source_observation = observer.observe()
resource_records = resource_consumption_world_state_records(
    ledger=source_observation.ledger,
    invocation_receipts=source_observation.invocation_receipts,
    verified_predecessor_invocation_receipts=(
        source_observation.predecessor_invocation_receipts),
    observed_at=data["world_state_tick"],
    source_identity={"installation_identity": data["installation_identity"],
        "provisioning_id": data["provisioning_id"],
        "manifest_digest": source_observation.manifest_digest})
replacement_records = ModelReplacementArtifactStore(
    Path(data["model_replacement_root"])).world_state_records(
        run_refs=((data["run_id"], data["run_digest"]),))
joined_records = resource_invocation_proposal_lineage_records(
    [*resource_records, *replacement_records])
target = next(record for record in joined_records
    if record.get("payload", {}).get("model_replacement_condition")
        == lineage_facts[0].payload.get("model_replacement_condition"))
assert target["digest"] == lineage_facts[0].source.digest
bounded_board = WorldStateBoardBuilder(
    clock=lambda: datetime.fromisoformat(data["world_state_tick"])).build([target])
assert len(bounded_board.facts) == 1
assert bounded_board.facts[0].fact_id == lineage_facts[0].fact_id
cognition, invoker = developmental_owner(Path(data["cognition_root"]),
    allowed_source_kinds=("resource_governor",), max_selected_facts=1)
result = cognition.run_tick(snapshot=bounded_board, tick_id=data["tick_id"],
    prior_epistemic_state=projection, prior_self_model=self_model)
request = next(item for item in invoker.requests
    if item.purpose == "resident_developmental_retrieval_cognition")
print(json.dumps({"status": result.status, "prior_record_ids": list(result.prior_record_ids),
    "projection_id": projection.projection_id if projection else None,
    "projection_source_tick": projection.source_tick if projection else None,
    "projection_state_ids": list(projection.state_ids) if projection else [],
    "projection_state_digests": list(projection.state_digests) if projection else [],
    "self_model_projection_id": self_model.projection_id if self_model else None,
    "self_model_reconciliation_id": self_model.source_reconciliation_id if self_model else None,
    "self_model_reconciliation_digest": self_model.source_reconciliation_digest if self_model else None,
    "upstream_evidence": request.upstream_evidence}, sort_keys=True))
"""
        process = subprocess.run([sys.executable, "-c", child], cwd=Path(__file__).parents[1],
            input=json.dumps({"epistemic_root": str(epistemic_root),
                "self_model_root": str(tmp_path / "composed-self-model"),
                "cognition_root": str(cognition_root),
                "installation_state_root": str(tmp_path / "resources" / "state"),
                "installation_identity": "production",
                "provisioning_id": "replacement-trial",
                "repo_root": str(tmp_path),
                "runtime_root": str(tmp_path / "composed-runtime"),
                "model_replacement_root": str(experiment_root / "rehearsal"),
                "run_id": run["run_id"], "run_digest": run["run_digest"],
                "epistemic_tick": tick_n_value + 2, "tick_n": tick_n,
                "world_state_tick": "2026-09-21T08:50:00+00:00",
                "tick_id": "model-resource-history-tick-n-plus-two"}),
            text=True, capture_output=True, timeout=60)
        assert process.returncode == 0, process.stderr
        recovered = json.loads(process.stdout.strip().splitlines()[-1])
        assert recovered["status"] == "completed"
        assert recovered["prior_record_ids"] == [first.written_record_id]
        assert recovered["projection_source_tick"] == later_epistemic.source_tick == tick_n_value
        assert tuple(recovered["projection_state_ids"]) == later_epistemic.state_ids
        assert tuple(recovered["projection_state_digests"]) == later_epistemic.state_digests
        assert recovered["self_model_reconciliation_id"] == later_self_model.source_reconciliation_id
        assert recovered["self_model_reconciliation_digest"] == later_self_model.source_reconciliation_digest
        assert first.written_record_id in recovered["upstream_evidence"]["record_ids"]
        assert recovered["upstream_evidence"]["epistemic_projection_id"] == recovered["projection_id"]
        assert recovered["upstream_evidence"]["self_model_projection_id"] == recovered["self_model_projection_id"]
        assert first_fixture.requests

        # The projection omits private source fields, so its observation hash
        # cannot be recomputed from the projection. The retained ID must still
        # remain bound to the original, correctly formatted observation digest.
        altered_identity_records = deepcopy(replacement_records)
        altered_identity_records[0]["payload"]["observations"][0]["observation_id"] = \
            "model-replacement-observation-" + "f" * 24
        altered_identity_records[0]["digest"] = record_digest(altered_identity_records[0])
        altered_identity = resource_invocation_proposal_lineage_records(
            [*resource_records, *altered_identity_records])
        assert any(row["disposition"] == "degraded"
            and "model_replacement_observation_binding_invalid"
                in row["payload"]["lineage_findings"] for row in altered_identity)

        # A fully re-digested but ledger-substituted attempt remains degraded.
        altered_records = deepcopy(replacement_records)
        altered_observations = altered_records[0]["payload"]["observations"]
        altered = altered_observations[0]
        altered["resource_attempt_id"] = "lmattempt-" + "f" * 32
        semantic_observation = {key: value for key, value in altered.items()
            if key not in {"observation_id", "observation_digest"}}
        altered["observation_digest"] = "sha256:" + digest_payload(semantic_observation)
        altered["observation_id"] = "model-replacement-observation-" + altered["observation_digest"][7:31]
        altered_records[0]["digest"] = record_digest(altered_records[0])
        substituted = resource_invocation_proposal_lineage_records(
            [*resource_records, *altered_records]
        )
        assert any(row["disposition"] == "degraded"
            and "resource_invocation_linkage_substitution" in row["payload"]["lineage_findings"]
            for row in substituted)
    finally:
        owner.close()
