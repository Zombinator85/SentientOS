from __future__ import annotations

import json
from pathlib import Path

from sentientos.contract_sentinel import ContractSentinel, SentinelPolicy
from sentientos.forge_campaigns import CampaignSpec, resolve_campaign
from sentientos.forge_queue import ForgeQueue, ForgeRequest


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_contracts(tmp_path: Path, *, prev_failed: int, cur_failed: int, prev_passed: bool = True, cur_passed: bool = False) -> None:
    _write_json(
        tmp_path / "glow/contracts/contract_status.json",
        {
            "previous": {"ci_baseline": {"failed_count": prev_failed, "passed": prev_passed}},
            "current": {"ci_baseline": {"failed_count": cur_failed, "passed": cur_passed}},
        },
    )
    _write_json(tmp_path / "glow/contracts/ci_baseline.json", {"failed_count": cur_failed, "passed": cur_passed})
    _write_json(tmp_path / "glow/forge/index.json", {"corrupt_count": {"total": 0}})
    _write_json(tmp_path / "glow/forge/policy.json", {"allowlisted_goal_ids": ["campaign:ci_baseline_recovery", "forge_smoke_noop"], "allowlisted_autopublish_flags": []})


def test_sentinel_enqueues_on_pass_to_fail(tmp_path: Path) -> None:
    _seed_contracts(tmp_path, prev_failed=0, cur_failed=3)
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    sentinel = ContractSentinel(repo_root=tmp_path, queue=queue)
    policy = sentinel.load_policy()
    policy.enabled = True
    policy.cooldown_minutes = {"global": 0, "ci_baseline": 0}
    sentinel.save_policy(policy)

    result = sentinel.tick()

    assert result["status"] == "ok"
    pending = queue.pending_requests()
    assert pending
    assert pending[0].goal == "campaign:ci_baseline_recovery"
    assert pending[0].requested_by == "ContractSentinel"


def test_sentinel_respects_cooldown_and_daily_budget(tmp_path: Path) -> None:
    _seed_contracts(tmp_path, prev_failed=0, cur_failed=1)
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    sentinel = ContractSentinel(repo_root=tmp_path, queue=queue)
    policy = sentinel.load_policy()
    policy.enabled = True
    policy.max_enqueues_per_day = 1
    policy.cooldown_minutes = {"global": 120, "ci_baseline": 120}
    sentinel.save_policy(policy)

    first = sentinel.tick()
    second = sentinel.tick()

    assert first["status"] == "ok"
    assert second["status"] in {"no_change", "ok"}
    assert len(queue.pending_requests()) == 1


def test_sentinel_recursion_guard_blocks_when_lock_owned_by_same_domain(tmp_path: Path) -> None:
    _seed_contracts(tmp_path, prev_failed=0, cur_failed=2)
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    sentinel = ContractSentinel(repo_root=tmp_path, queue=queue)
    policy = sentinel.load_policy()
    policy.enabled = True
    policy.cooldown_minutes = {"global": 0, "ci_baseline": 0}
    sentinel.save_policy(policy)

    req_id = queue.enqueue(
        ForgeRequest(
            request_id="",
            goal="campaign:ci_baseline_recovery",
            goal_id="campaign:ci_baseline_recovery",
            requested_by="ContractSentinel",
            metadata={"trigger_domain": "ci_baseline", "sentinel_triggered": True},
        )
    )
    _write_json(tmp_path / ".forge/forge.lock", {"request_id": req_id, "goal": "campaign:ci_baseline_recovery", "started_at": "2099-01-01T00:00:00Z"})

    result = sentinel.tick()

    assert result["status"] == "ok"
    assert len(queue.pending_requests()) == 1


def test_campaign_spec_exists_and_order() -> None:
    campaign = resolve_campaign("ci_baseline_recovery")
    assert isinstance(campaign, CampaignSpec)
    assert campaign.goals == ["repo_green_storm"]
    assert campaign.stop_on_failure is True


def test_note_quarantine_extends_cooldown_and_records_state(tmp_path: Path) -> None:
    _seed_contracts(tmp_path, prev_failed=0, cur_failed=2)
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    sentinel = ContractSentinel(repo_root=tmp_path, queue=queue)
    policy = sentinel.load_policy()
    policy.enabled = True
    policy.cooldown_minutes = {"global": 1, "ci_baseline": 2}
    sentinel.save_policy(policy)

    sentinel.note_quarantine(domain="ci_baseline", quarantine_ref="quarantine/forge-123", reasons=["contract_drift_appeared"])

    next_policy = sentinel.load_policy()
    state = sentinel.load_state()
    assert next_policy.cooldown_minutes["ci_baseline"] == 6
    assert state.last_quarantine_by_domain["ci_baseline"] == "quarantine/forge-123"
    assert state.last_quarantine_reasons["ci_baseline"] == ["contract_drift_appeared"]
