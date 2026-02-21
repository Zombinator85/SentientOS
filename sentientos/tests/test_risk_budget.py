from __future__ import annotations

import json
from pathlib import Path

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_goals import resolve_goal
from sentientos.forge_merge_train import ForgeMergeTrain, TrainState
from sentientos.forge_model import ForgeSession
from sentientos.risk_budget import compute_risk_budget, derive_risk_budget
from sentientos.github_merge import MergeResult, RebaseResult
from sentientos.forge_merge_train import TrainEntry


class _Ops:
    def __init__(self) -> None:
        self.behind = False
        self.rebase = RebaseResult(ok=True, conflict=False, message="ok", new_head_sha="newsha", suspect_files=[])
        self.checks = "success"
        self.wait = ("success", False)
        self.merge = MergeResult(ok=True, conflict=False, message="ok")

    def checks_for(self, entry: TrainEntry) -> tuple[str, str | None, str | None]:
        _ = entry
        return (self.checks, None, None)

    def wait_for_checks(self, entry: TrainEntry, timeout_seconds: int = 1800) -> tuple[str, bool]:
        _ = entry, timeout_seconds
        return self.wait

    def is_branch_behind_base(self, entry: TrainEntry, base_branch: str) -> bool:
        _ = entry, base_branch
        return self.behind

    def rebase_branch(self, entry: TrainEntry, base_branch: str) -> RebaseResult:
        _ = entry, base_branch
        return self.rebase

    def merge_pull_request(self, entry: TrainEntry, strategy: str) -> MergeResult:
        _ = entry, strategy
        return self.merge


def _entry(status: str = "ready") -> TrainEntry:
    return TrainEntry(
        run_id="run-1",
        pr_url="https://github.com/o/r/pull/11",
        pr_number=11,
        head_sha="abc",
        branch="forge/1",
        goal_id="forge_smoke_noop",
        campaign_id=None,
        status=status,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        check_overall="success",
    )


def test_quarantine_and_lockdown_clamp_to_minima(tmp_path: Path) -> None:
    budget = derive_risk_budget(posture="balanced", pressure_level=3, operating_mode="lockdown", quarantine_active=True)
    assert budget.router_k_max == 1
    assert budget.router_m_max == 0
    assert budget.router_allow_escalation is False
    assert budget.forge_max_files_changed == 0
    assert budget.allow_publish is False
    assert budget.allow_automerge is False


def test_recovery_mode_disables_escalation_and_tightens_forge() -> None:
    budget = derive_risk_budget(posture="velocity", pressure_level=2, operating_mode="recovery", quarantine_active=False)
    assert budget.router_k_max <= 2
    assert budget.router_m_max <= 1
    assert budget.router_allow_escalation is False
    assert budget.forge_max_files_changed <= 20
    assert budget.forge_max_retries == 0


def test_normal_mode_posture_defaults_ordering() -> None:
    stability = derive_risk_budget(posture="stability", pressure_level=0, operating_mode="normal", quarantine_active=False)
    velocity = derive_risk_budget(posture="velocity", pressure_level=0, operating_mode="normal", quarantine_active=False)
    assert velocity.router_k_max > stability.router_k_max
    assert velocity.router_m_max >= stability.router_m_max
    assert velocity.forge_max_files_changed > stability.forge_max_files_changed


def test_override_requires_explicit_allow(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    override = tmp_path / "override.json"
    override.write_text(json.dumps({"router_k_max": 9, "allow_publish": False}), encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_RISK_BUDGET_FORCE_JSON", str(override))

    denied = compute_risk_budget(repo_root=tmp_path, posture="balanced", pressure_level=0, operating_mode="normal", quarantine_active=False)
    assert denied.router_k_max != 9
    assert any("override_rejected:" in note for note in (denied.notes or []))

    monkeypatch.setenv("SENTIENTOS_RISK_BUDGET_ALLOW_OVERRIDE", "1")
    allowed = compute_risk_budget(repo_root=tmp_path, posture="balanced", pressure_level=0, operating_mode="normal", quarantine_active=False)
    assert allowed.router_k_max == 9
    assert allowed.allow_publish is False
    assert any("override_applied:" in note for note in (allowed.notes or []))


def test_canary_uses_risk_budget_throttle_reason(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOPR", "0")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "0")
    monkeypatch.setenv("SENTIENTOS_RISK_BUDGET_ALLOW_OVERRIDE", "1")
    override = tmp_path / "risk_override.json"
    override.write_text(json.dumps({"allow_publish": False}), encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_RISK_BUDGET_FORCE_JSON", str(override))
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text('{"baseline_integrity_ok": true, "runtime_integrity_ok": true, "baseline_unexpected_change_detected": false}\n', encoding="utf-8")

    forge = CathedralForge(repo_root=tmp_path)
    notes, remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )
    assert "risk_budget_throttle" in notes
    assert remote["automerge_result"] == "risk_budget_throttle"


def test_merge_train_uses_risk_budget_throttle_reason(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_RISK_BUDGET_ALLOW_OVERRIDE", "1")
    override = tmp_path / "risk_override.json"
    override.write_text(json.dumps({"allow_automerge": False}), encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_RISK_BUDGET_FORCE_JSON", str(override))
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )

    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()
    assert result["reason"] == "risk_budget_throttle"
    state = train.load_state()
    assert state.entries[0].last_error == "risk_budget_throttle"
