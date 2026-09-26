from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from sentientos.maintenance_authority_continuity import GENERATION_SCHEMA, RECEIPT_SCHEMA as CONTINUITY_SCHEMA
from sentientos.maintenance_post_adoption_attribution_campaign import ControlDefinition, make_campaign_protocol
from sentientos.maintenance_post_adoption_evaluation import MeasurementDefinition, make_baseline, make_protocol
from sentientos.maintenance_production_post_adoption_campaign import (
    FALSE_EFFECTS, MaintenanceProductionPostAdoptionCampaign, ProductionCampaignError, _digest,
)
from sentientos.maintenance_resident_runtime_adoption import EVENT_SCHEMA, PROVENANCE_SCHEMA, RECEIPT_SCHEMA

pytestmark = pytest.mark.no_legacy_skip


def _source(path: Path, value: int) -> dict[str, str]:
    payload = {"value": value}; path.write_text(json.dumps(payload), encoding="utf-8")
    return {"source_path": str(path), "source_digest": _digest(payload), "source_schema": "example.metric:v1"}


def _prepared(tmp_path: Path) -> tuple[MaintenanceProductionPostAdoptionCampaign, object]:
    owner = MaintenanceProductionPostAdoptionCampaign(tmp_path / "state")
    evaluations = []; baselines = []
    for index in range(2):
        protocol = make_protocol(maintenance_task_id="task", proposal_id="proposal", signal_ids=("signal",),
            implementation_session_id="session", validation_result_digest="sha256:" + "1" * 64,
            landed_commit="b" * 40, landed_tree="c" * 40, predecessor_generation=4,
            expected_successor_generation=5, target_scope="metric",
            measurements=(MeasurementDefinition("metric", "exact_record", "metric-law:v1", "increase", None, -1),),
            required_evidence_sources=("exact_record",), observation_trigger={"trial": index},
            created_at=f"2026-01-01T00:00:0{index}Z", creation_generation=4)
        source = _source(tmp_path / f"baseline-{index}.json", index)
        baseline = make_baseline(protocol, source_revision="a" * 40, source_tree="d" * 40,
            runtime_identity="predecessor:4", observations={"metric": index}, source_records={"metric": source},
            measurement_laws={"metric": "metric-law:v1"}, observed_at=f"2026-01-01T00:01:0{index}Z", collector_id="exact-file")
        evaluations.append(protocol); baselines.append(baseline)
    campaign = make_campaign_protocol(maintenance_task_id="task", proposal_id="proposal", signal_ids=("signal",),
        predecessor_generation=4, predecessor_revision="a" * 40, predecessor_tree="d" * 40,
        successor_generation=5, successor_revision="b" * 40, successor_tree="c" * 40,
        adoption_identity="resident-transition:exact", evaluation_protocol_ids=tuple(x.protocol_id for x in evaluations),
        evaluation_protocol_digests=tuple(x.protocol_digest for x in evaluations), target_observable_ids=("metric",),
        target_measurement_laws={"metric": "metric-law:v1"}, protected_invariant_ids=(),
        controls=(ControlDefinition("cpu.load_average_1m", "host-load:v1", "absolute-delta", "canonical host collector", ("host_observation",)),),
        control_design="observed_environmental_stability", attribution_rule="repeat-under-matched-controls",
        trial_ids=("trial-1", "trial-2"), minimum_trials=2, maximum_trials=2, evidence_class="production",
        created_at="2026-01-01T00:00:00Z", creation_generation=4, no_retry=True, no_replacement=True, no_cherry_picking=True)
    owner.prepare(campaign, evaluations, baselines)
    return owner, campaign


def _sealed(schema: str, digest_key: str, **values: object) -> dict[str, object]:
    result = {"schema_version": schema, **values}; result[digest_key] = _digest(result); return result


def _evidence(tmp_path: Path) -> dict[str, object]:
    generation = _sealed(GENERATION_SCHEMA, "generation_digest", ordinal=5, base_sha="b" * 40)
    continuity = _sealed(CONTINUITY_SCHEMA, "receipt_digest", successor_sha="b" * 40)
    provenance = _sealed(PROVENANCE_SCHEMA, "provenance_digest", process_instance_id="pid:real")
    adoption = _sealed(RECEIPT_SCHEMA, "receipt_digest", status="resident_ready",
        successor_generation_digest=generation["generation_digest"], continuity_receipt_digest=continuity["receipt_digest"],
        successor_launch_provenance_digest=provenance["provenance_digest"])
    event = _sealed(EVENT_SCHEMA, "event_digest", phase="resident_adoption_completed")
    journal = tmp_path / "resident-journal.jsonl"; journal.write_text(json.dumps(event) + "\n", encoding="utf-8")
    target = {"value": 10}; target_path = tmp_path / "target.json"; target_path.write_text(json.dumps(target), encoding="utf-8")
    return {"generation": generation, "continuity": continuity, "launch_provenance": provenance,
        "adoption": adoption, "adoption_completion_event": event, "resident_journal": {"path": str(journal)},
        "repository": {"tree_sha": "c" * 40}, "target_sources": {"records": [
            {"observable_id": "metric", "path": str(target_path), "digest": _digest(target), "schema": "example.metric:v1"}]}}


def test_readiness_is_derived_from_real_exact_artifacts_and_rejects_declared_production(tmp_path: Path) -> None:
    owner, campaign = _prepared(tmp_path)
    rejected = owner.readiness(campaign.campaign_id, {"evidence_class": {"value": "production"}})
    assert rejected["status"] == "production_campaign_not_ready"
    assert rejected["caller_declared_evidence_class_trusted"] is False
    evidence = _evidence(tmp_path)
    assert owner.readiness(campaign.campaign_id, evidence)["status"] == "production_campaign_ready"
    bad = dict(evidence); bad["repository"] = {"tree_sha": "0" * 40}
    assert "successor_tree_exact" in owner.readiness(campaign.campaign_id, bad)["missing_prerequisites"]


def test_predecessor_custody_reconstructs_and_tampering_fails(tmp_path: Path) -> None:
    owner, campaign = _prepared(tmp_path); first = owner.reconstruct(campaign.campaign_id)
    restarted = MaintenanceProductionPostAdoptionCampaign(tmp_path / "state")
    assert restarted.reconstruct(campaign.campaign_id) == first
    path = tmp_path / "state" / "custody.json"; value = json.loads(path.read_text()); value["expected_successor"]["tree"] = "x"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ProductionCampaignError, match="tampered"): restarted.reconstruct(campaign.campaign_id)


def test_real_host_control_is_production_and_law_bound(tmp_path: Path) -> None:
    owner, campaign = _prepared(tmp_path)
    control = owner.collect_host_control(campaign.campaign_id, "trial-1", "cpu.load_average_1m",
        before_value=0.0, matching_result="matched", window_identity="window:1")
    assert control.evidence_class == "production" and control.source_class == "host_observation"
    assert control.measurement_law == "host-load:v1" and control.dependency_ids == ()


def test_restart_order_no_replay_interruption_and_non_authority(tmp_path: Path) -> None:
    owner, campaign = _prepared(tmp_path)
    first = owner.interrupt_next(campaign.campaign_id, completed_at="2026-01-02T00:00:00Z")
    assert first["trial_id"] == "trial-1" and first["outcome"] == "interrupted_or_invalid_trial"
    restarted = MaintenanceProductionPostAdoptionCampaign(tmp_path / "state")
    second = restarted.interrupt_next(campaign.campaign_id, completed_at="2026-01-02T00:01:00Z")
    assert second["trial_id"] == "trial-2"
    result = restarted.finalize(campaign.campaign_id, completed_at="2026-01-02T00:02:00Z")
    assert result["classification"] == "interrupted_or_invalid_trial"
    with pytest.raises((ProductionCampaignError, ValueError)): restarted.interrupt_next(campaign.campaign_id, completed_at="2026-01-02T00:03:00Z")
    assert all(value is False for value in FALSE_EFFECTS.values())


def test_stale_dependent_wrong_or_malformed_source_fails_closed(tmp_path: Path) -> None:
    owner, campaign = _prepared(tmp_path); evidence = _evidence(tmp_path)
    evidence["target_sources"]["records"][0]["digest"] = "sha256:" + "0" * 64  # type: ignore[index]
    ready = owner.readiness(campaign.campaign_id, evidence)  # type: ignore[arg-type]
    assert "target_collector_available" in ready["missing_prerequisites"]
    event = evidence["adoption_completion_event"]; event["phase"] = "self_exec_requested"  # type: ignore[index]
    assert "adoption_completion_event_valid" in owner.readiness(campaign.campaign_id, evidence)["missing_prerequisites"]  # type: ignore[arg-type]


def test_baseline_must_be_real_exact_source(tmp_path: Path) -> None:
    owner, campaign = _prepared(tmp_path)
    baseline = owner.evaluations.baseline(campaign.evaluation_protocol_ids[0])
    bad = replace(baseline, source_records={"metric": {"source_path": str(tmp_path / "absent"), "source_digest": "sha256:x", "source_schema": "x"}})
    other = MaintenanceProductionPostAdoptionCampaign(tmp_path / "other")
    protocols = [owner.evaluations.protocol(x) for x in campaign.evaluation_protocol_ids]
    with pytest.raises(ProductionCampaignError, match="baseline_source_not_production"):
        other.prepare(campaign, protocols, [bad, owner.evaluations.baseline(campaign.evaluation_protocol_ids[1])])
