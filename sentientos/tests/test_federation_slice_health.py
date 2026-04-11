from __future__ import annotations

from sentientos.federation_slice_health import synthesize_bounded_federation_seed_health


def _rows(outcome_by_action: dict[str, str]) -> list[dict[str, object]]:
    return [
        {
            "typed_action_identity": action_id,
            "outcome_class": outcome,
        }
        for action_id, outcome in outcome_by_action.items()
    ]


def test_all_success_latest_lifecycles_report_healthy() -> None:
    health = synthesize_bounded_federation_seed_health(
        _rows(
            {
                "sentientos.federation.restart_daemon_request": "success",
                "sentientos.federation.governance_digest_or_quorum_denial_gate": "success",
                "sentientos.federation.epoch_or_trust_posture_gate": "success",
                "sentientos.federation.replay_or_receipt_consistency_gate": "success",
                "sentientos.federation.ingest_replay_admission_gate": "success",
            }
        )
    )
    assert health["health_status"] == "healthy"
    assert health["outcome_counts"]["success"] == 5
    assert health["has_fragmentation"] is False
    assert health["has_admitted_failure"] is False


def test_admitted_failure_presence_reports_degraded() -> None:
    health = synthesize_bounded_federation_seed_health(
        _rows(
            {
                "sentientos.federation.restart_daemon_request": "success",
                "sentientos.federation.governance_digest_or_quorum_denial_gate": "failed_after_admission",
                "sentientos.federation.epoch_or_trust_posture_gate": "denied",
                "sentientos.federation.replay_or_receipt_consistency_gate": "success",
                "sentientos.federation.ingest_replay_admission_gate": "denied",
            }
        )
    )
    assert health["health_status"] == "degraded"
    assert health["has_admitted_failure"] is True
    assert health["outcome_counts"]["failed_after_admission"] == 1


def test_fragmentation_presence_reports_fragmented() -> None:
    health = synthesize_bounded_federation_seed_health(
        _rows(
            {
                "sentientos.federation.restart_daemon_request": "success",
                "sentientos.federation.governance_digest_or_quorum_denial_gate": "fragmented_unresolved",
                "sentientos.federation.epoch_or_trust_posture_gate": "success",
                "sentientos.federation.replay_or_receipt_consistency_gate": "success",
                "sentientos.federation.ingest_replay_admission_gate": "success",
            }
        )
    )
    assert health["health_status"] == "fragmented"
    assert health["has_fragmentation"] is True
    assert health["outcome_counts"]["fragmented_unresolved"] == 1


def test_denied_only_stays_healthy_in_bounded_model() -> None:
    health = synthesize_bounded_federation_seed_health(
        _rows(
            {
                "sentientos.federation.restart_daemon_request": "denied",
                "sentientos.federation.governance_digest_or_quorum_denial_gate": "denied",
                "sentientos.federation.epoch_or_trust_posture_gate": "denied",
                "sentientos.federation.replay_or_receipt_consistency_gate": "denied",
                "sentientos.federation.ingest_replay_admission_gate": "denied",
            }
        )
    )
    assert health["health_status"] == "healthy"
    assert health["outcome_counts"]["denied"] == 5


def test_health_signal_is_explicitly_non_sovereign() -> None:
    health = synthesize_bounded_federation_seed_health([])
    assert health["diagnostic_only"] is True
    assert health["non_authoritative"] is True
    assert health["decision_power"] == "none"
    assert health["support_signal_only"] is True
    assert health["affects_admission"] is False
    assert health["affects_mergeability"] is False
    assert health["affects_runtime_governor_behavior"] is False
    assert health["acts_as_federation_adjudicator"] is False
