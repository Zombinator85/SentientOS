from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from sentientos.developmental_model_replacement_experiment import ModelReplacementArtifactStore
from sentientos.developmental_model_replacement_rehearsal import _load, prepare, run_next
from sentientos.governed_local_model_resource_allocation import (
    GovernedLocalModelResourceBounds,
    GovernedLocalModelResourcePolicy,
)
from sentientos.host_resource_runtime import (
    resource_consumption_world_state_records,
    resource_invocation_proposal_lineage_records,
)
from sentientos.local_model_authority import digest_payload
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    produce_production_chat_resource_provisioning_bundle,
)
from tests.test_production_chat_resource_provisioning_bundle_producer import inputs
from sentientos.world_state_board import record_digest

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
        scenario = prepare(experiment_root)
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
