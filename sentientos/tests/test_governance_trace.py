from __future__ import annotations

import json
from pathlib import Path

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_goals import resolve_goal
from sentientos.forge_merge_train import ForgeMergeTrain, TrainEntry, TrainState
from sentientos.forge_model import ForgeSession
from sentientos.genesis_forge import (
    AdoptionRite,
    CovenantVow,
    DaemonManifest,
    ForgeEngine,
    GenesisForge,
    NeedSeer,
    RecoveryLedger,
    SpecBinder,
    TelemetryStream,
    TrialRun,
)
from sentientos.github_merge import MergeResult, RebaseResult
from sentientos.governance_trace import reset_current_trace, set_current_trace, start_governance_trace


class _Ops:
    def __init__(self) -> None:
        self.merge = MergeResult(ok=True, conflict=False, message="ok")

    def checks_for(self, entry: TrainEntry) -> tuple[str, str | None, str | None]:
        _ = entry
        return ("success", None, None)

    def wait_for_checks(self, entry: TrainEntry, timeout_seconds: int = 1800) -> tuple[str, bool]:
        _ = entry, timeout_seconds
        return ("success", False)

    def is_branch_behind_base(self, entry: TrainEntry, base_branch: str) -> bool:
        _ = entry, base_branch
        return False

    def rebase_branch(self, entry: TrainEntry, base_branch: str) -> RebaseResult:
        _ = entry, base_branch
        return RebaseResult(ok=True, conflict=False, message="ok", new_head_sha="new", suspect_files=[])

    def merge_pull_request(self, entry: TrainEntry, strategy: str) -> MergeResult:
        _ = entry, strategy
        return self.merge


class _EvalA:
    def __init__(self) -> None:
        self.valid_a = True
        self.reason_codes_a: list[str] = []
        self.probe: dict[str, object] = {}


class _EvalB:
    def __init__(self) -> None:
        self.valid = True
        self.reason_codes: list[str] = []


class _IntegrityDaemon:
    def evaluate_report_stage_a(self, proposal: object) -> _EvalA:
        _ = proposal
        return _EvalA()

    def evaluate_report_stage_b(self, proposal: object, *, probe_cache: object = None) -> _EvalB:
        _ = proposal, probe_cache
        return _EvalB()


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


def test_held_merge_due_to_risk_budget_writes_trace(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
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
    train.save_state(TrainState(entries=[_entry()]))
    result = train.tick()

    assert result["reason"] == "risk_budget_throttle"
    trace_path = tmp_path / str(result["trace_path"])
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["final_decision"] == "hold"
    assert payload["final_reason"] == "risk_budget_throttle"
    assert any(item.get("name") == "risk_budget_automerge" for item in payload["clamps_applied"])
    assert payload["reason_stack"][0] == "risk_budget_throttle"


def test_blocked_publish_due_to_quarantine_writes_trace_with_suggestion(tmp_path: Path) -> None:
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/quarantine.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "active": True,
                "activated_at": "2026-01-01T00:00:00Z",
                "activated_by": "auto",
                "last_incident_id": "inc-1",
                "freeze_forge": True,
                "allow_automerge": False,
                "allow_publish": False,
                "allow_federation_sync": True,
                "notes": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    forge = CathedralForge(repo_root=tmp_path)
    notes, remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )
    assert "quarantine_active" in notes
    trace_path = tmp_path / str(remote["trace_path"])
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["final_decision"] == "block"
    assert payload["gates_evaluated"][0]["name"] == "quarantine_publish"
    assert any("quarantine_clear" in item for item in payload["suggested_actions"])


def test_diagnostics_only_forge_run_includes_trace(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_DIAGNOSTICS_ONLY", "1")
    report = CathedralForge(repo_root=tmp_path).run("forge_smoke_noop")
    assert report.outcome == "diagnostics_only"
    assert report.governance_trace_id
    traces = sorted((tmp_path / "glow/forge/traces").glob("trace_*_forge_run.json"))
    payload = json.loads(traces[-1].read_text(encoding="utf-8"))
    assert payload["final_decision"] == "diagnostics_only"


def test_router_clamp_records_clamp_in_current_trace(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sentientos.genesis_forge.enforce_codex_startup", lambda _symbol: None)
    monkeypatch.setenv("SENTIENTOS_RISK_BUDGET_ALLOW_OVERRIDE", "1")
    override = tmp_path / "risk_override.json"
    override.write_text(json.dumps({"router_k_max": 1, "router_m_max": 0, "router_allow_escalation": False}), encoding="utf-8")
    monkeypatch.setenv("SENTIENTOS_RISK_BUDGET_FORCE_JSON", str(override))

    trace = start_governance_trace(
        repo_root=tmp_path,
        context="router_test",
        strategic_posture="balanced",
        integrity_pressure_level=0,
        integrity_metrics_summary={},
        operating_mode="normal",
        mode_toggles_summary={},
        quarantine_state_summary={},
        risk_budget_summary={},
    )
    token = set_current_trace(trace)
    try:
        genesis = GenesisForge(
            need_seer=NeedSeer(daemons=[DaemonManifest(name="m", capabilities=frozenset())]),
            forge_engine=ForgeEngine(),
            integrity_daemon=_IntegrityDaemon(),
            trial_run=TrialRun(),
            spec_binder=SpecBinder(lineage_root=tmp_path / "lineage", covenant_root=tmp_path / "covenant"),
            adoption_rite=AdoptionRite(live_mount=tmp_path / "live", codex_index=tmp_path / "codex_index.json", review_board=lambda _p, _r: True),
            ledger=RecoveryLedger(tmp_path / "logs/genesis.jsonl"),
        )
        try:
            genesis.expand(
                [TelemetryStream(name="n", capability="new_cap", description="d")],
                [CovenantVow(capability="new_cap", description="d")],
            )
        except Exception:
            pass
    finally:
        reset_current_trace(token)

    persisted = trace.finalize(final_decision="allow", final_reason="ok", reason_stack=["ok"])
    payload = json.loads((tmp_path / persisted["trace_path"]).read_text(encoding="utf-8"))
    assert any(item.get("name") == "router_proof_budget" for item in payload["clamps_applied"])


def test_governance_trace_finalize_emits_remediation_pack(tmp_path: Path) -> None:
    trace = start_governance_trace(
        repo_root=tmp_path,
        context="merge_train",
        strategic_posture="balanced",
        integrity_pressure_level=1,
        integrity_metrics_summary={},
        operating_mode="recovery",
        mode_toggles_summary={},
        quarantine_state_summary={"active": False},
        risk_budget_summary={},
    )
    persisted = trace.finalize(final_decision="hold", final_reason="audit_chain_broken", reason_stack=["audit_chain_broken"])
    remediation = persisted.get("remediation_pack")
    assert isinstance(remediation, dict)
    pack_path = tmp_path / str(remediation["pack_path"])
    assert pack_path.exists()


def test_governance_trace_records_auto_remediation_outcomes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _fake_auto(*args: object, **kwargs: object):
        _ = args, kwargs
        class _R:
            status = "succeeded"
            reason = "run_completed"
            attempted = True
            run_id = "run-123"
            pack_id = "pack-123"
            gate_results = [{"name": "audit_chain", "result": "pass", "reason": "auto_remediation_recheck"}]
        return _R()

    monkeypatch.setattr("sentientos.governance_trace.maybe_auto_run_pack", _fake_auto)

    trace = start_governance_trace(
        repo_root=tmp_path,
        context="merge_train",
        strategic_posture="balanced",
        integrity_pressure_level=1,
        integrity_metrics_summary={},
        operating_mode="recovery",
        mode_toggles_summary={},
        quarantine_state_summary={"active": False},
        risk_budget_summary={},
    )
    persisted = trace.finalize(final_decision="hold", final_reason="audit_chain_broken", reason_stack=["audit_chain_broken"])
    payload = json.loads((tmp_path / str(persisted["trace_path"])).read_text(encoding="utf-8"))
    assert "auto_remediation_attempted" in payload["reason_stack"]
    assert "auto_remediation_succeeded" in payload["reason_stack"]
    assert any(item.get("reason") == "auto_remediation_recheck" for item in payload["gates_evaluated"])
