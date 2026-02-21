from __future__ import annotations

import json
from pathlib import Path

from sentientos.forge_merge_train import ForgeMergeTrain, TrainEntry, TrainState
from sentientos.github_artifacts import ArtifactRef, ContractBundle
from sentientos.forge_queue import ForgeQueue, ForgeRequest
from sentientos.github_merge import MergeResult, RebaseResult


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


def test_state_persistence_roundtrip(tmp_path: Path) -> None:
    train = ForgeMergeTrain(repo_root=tmp_path)
    state = TrainState(entries=[_entry()], last_merged_pr=None, last_failure_at=None)
    train.save_state(state)

    loaded = train.load_state()

    assert len(loaded.entries) == 1
    assert loaded.entries[0].pr_number == 11


def test_tick_selects_ready_fifo(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("held"), _entry("ready")]))

    result = train.tick()

    assert result["status"] in {"mergeable", "merged"}


def test_rebase_conflict_marks_held_and_writes_docket(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    ops.behind = True
    ops.rebase = RebaseResult(ok=False, conflict=True, message="conflict", new_head_sha=None, suspect_files=["a.py"])
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    dockets = list((tmp_path / "glow/forge").glob("merge_train_docket_*.json"))
    assert dockets
    payload = json.loads(dockets[0].read_text(encoding="utf-8"))
    assert payload["suspected_conflict_files"] == ["a.py"]


def test_checks_fail_retry_then_failed(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    ops.checks = "failure"
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    policy = train.load_policy()
    policy.cooldown_minutes_on_failure = 0
    train.save_policy(policy)
    train.save_state(TrainState(entries=[_entry("ready")]))

    first = train.tick()
    second = train.tick()

    assert first["status"] in {"held", "failed"}
    assert second["status"] == "failed"


def test_ingest_from_receipts_and_max_active(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_MAX_RUNS_PER_DAY", "10")
    monkeypatch.setenv("SENTIENTOS_FORGE_MAX_RUNS_PER_HOUR", "10")
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="", goal="forge_smoke_noop", goal_id="forge_smoke_noop"))
    queue.mark_finished(
        "forge-ignored",
        status="success",
        report_path=None,
        publish_status="ready_to_merge",
        publish_pr_url="https://github.com/o/r/pull/22",
        publish_checks_overall="success",
        provenance_run_id="run-x",
    )
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, queue=queue, github_ops=ops)
    policy = train.load_policy()
    policy.enabled = True
    policy.max_active_prs = 0
    train.save_policy(policy)

    result = train.tick()

    assert result["status"] == "max_active_exceeded"


def test_select_candidate_prefers_improving_recovery_pr(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_PREFER_IMPROVEMENT", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    (tmp_path / "glow/forge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/report_a.json").write_text(
        json.dumps(
            {
                "provenance_run_id": "run-a",
                "goal_id": "repo_green_storm",
                "ci_baseline_before": {"failed_count": 6},
                "ci_baseline_after": {"failed_count": 6},
                "baseline_progress": [{"delta": {"improved": False}}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/forge/report_b.json").write_text(
        json.dumps(
            {
                "provenance_run_id": "run-b",
                "goal_id": "repo_green_storm",
                "ci_baseline_before": {"failed_count": 6},
                "ci_baseline_after": {"failed_count": 4},
                "progress_delta": {"reduction_pct": 33.0},
                "baseline_progress": [{"delta": {"improved": True}}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    state = TrainState(
        entries=[
            TrainEntry(run_id="run-a", pr_url="https://github.com/o/r/pull/11", pr_number=11, head_sha="abc", branch="forge/1", goal_id="repo_green_storm", campaign_id="ci_baseline_recovery", status="ready", created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z", check_overall="success"),
            TrainEntry(run_id="run-b", pr_url="https://github.com/o/r/pull/12", pr_number=12, head_sha="abd", branch="forge/2", goal_id="repo_green_storm", campaign_id="ci_baseline_recovery", status="ready", created_at="2026-01-01T00:00:01Z", updated_at="2026-01-01T00:00:01Z", check_overall="success"),
        ]
    )

    candidate = train._select_candidate(state)

    assert candidate is not None
    assert candidate.run_id == "run-b"


def test_select_candidate_prefers_contract_improving_run(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_PREFER_IMPROVEMENT", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/forge_progress_baseline.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00Z",
                "git_sha": "abc",
                "window_size": 10,
                "last_runs": [
                    {"run_id": "run-a", "created_at": "2026-01-01T00:00:00Z", "goal_id": "repo_green_storm", "campaign_id": "ci_baseline_recovery", "before_failed": 6, "after_failed": 6, "progress_delta_percent": 0.0, "improved": False, "notes_truncated": []},
                    {"run_id": "run-b", "created_at": "2026-01-01T00:00:01Z", "goal_id": "repo_green_storm", "campaign_id": "ci_baseline_recovery", "before_failed": 6, "after_failed": 4, "progress_delta_percent": 33.0, "improved": True, "notes_truncated": []},
                ],
                "stagnation_alert": False,
                "stagnation_reason": None,
                "last_improving_run_id": "run-b",
                "last_stagnant_run_id": "run-a",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    state = TrainState(
        entries=[
            TrainEntry(run_id="run-a", pr_url="https://github.com/o/r/pull/11", pr_number=11, head_sha="abc", branch="forge/1", goal_id="repo_green_storm", campaign_id="ci_baseline_recovery", status="ready", created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z", check_overall="success"),
            TrainEntry(run_id="run-b", pr_url="https://github.com/o/r/pull/12", pr_number=12, head_sha="abd", branch="forge/2", goal_id="repo_green_storm", campaign_id="ci_baseline_recovery", status="ready", created_at="2026-01-01T00:00:01Z", updated_at="2026-01-01T00:00:01Z", check_overall="success"),
        ]
    )

    candidate = train._select_candidate(state)

    assert candidate is not None
    assert candidate.run_id == "run-b"


def test_merge_train_holds_when_audit_integrity_red(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": False, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "audit_integrity_failed"


def test_merge_train_holds_when_remote_doctrine_red(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    monkeypatch.setattr(
        "sentientos.forge_merge_train.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=12, sha=sha, created_at="2026-01-01T00:00:00Z"),
    )
    monkeypatch.setattr(
        "sentientos.forge_merge_train.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={
                "stability_doctrine.json": {"baseline_integrity_ok": False, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False},
                "contract_status.json": {"contracts": [{"domain_name": "stability_doctrine", "drifted": True}]},
            },
            source="remote",
            errors=[],
        ),
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "remote_doctrine_failed"


def test_merge_train_remote_green_is_mergeable(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "0")
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    monkeypatch.setattr(
        "sentientos.forge_merge_train.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=12, sha=sha, created_at="2026-01-01T00:00:00Z"),
    )
    monkeypatch.setattr(
        "sentientos.forge_merge_train.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={
                "stability_doctrine.json": {"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False},
                "contract_status.json": {"contracts": [{"domain_name": "stability_doctrine", "drifted": False}]},
            },
            source="remote",
            errors=[],
        ),
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "mergeable"


def test_merge_train_remote_missing_falls_back_local(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "0")
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    monkeypatch.setattr("sentientos.forge_merge_train.find_contract_artifact_for_sha", lambda pr_number, sha: None)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()
    state = train.load_state()

    assert result["status"] == "mergeable"
    assert state.entries[0].doctrine_gate_reason == "remote_missing_fallback"


def test_merge_train_remote_required_blocks_when_missing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_REQUIRE_REMOTE_DOCTRINE", "1")
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    monkeypatch.setattr("sentientos.forge_merge_train.find_contract_artifact_for_sha", lambda pr_number, sha: None)
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "remote_doctrine_missing"


def test_merge_train_blocks_on_remote_metadata_mismatch(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    monkeypatch.setattr(
        "sentientos.forge_merge_train.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=12, sha=sha, created_at="2026-01-01T00:00:00Z", selected_via="api:run-artifacts"),
    )
    monkeypatch.setattr(
        "sentientos.forge_merge_train.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={
                "stability_doctrine.json": {"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False},
                "contract_status.json": {"contracts": [{"domain_name": "stability_doctrine", "drifted": False}]},
            },
            source="remote",
            errors=["metadata_mismatch:sha"],
            metadata={"sha": "different"},
            metadata_ok=False,
        ),
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "remote_doctrine_metadata_mismatch"


def test_merge_train_blocks_on_remote_corrupt_bundle(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    ops = _Ops()
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=ops)
    monkeypatch.setattr(
        "sentientos.forge_merge_train.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=12, sha=sha, created_at="2026-01-01T00:00:00Z", selected_via="api:run-artifacts"),
    )
    monkeypatch.setattr(
        "sentientos.forge_merge_train.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={"stability_doctrine.json": {"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}},
            source="remote",
            errors=["bundle_missing_required:contract_status.json"],
            metadata={"sha": "abc"},
            metadata_ok=True,
        ),
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "remote_doctrine_corrupt_bundle"


def test_merge_train_blocks_on_remote_manifest_missing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    monkeypatch.setattr(
        "sentientos.forge_merge_train.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=12, sha=sha, created_at="2026-01-01T00:00:00Z", selected_via="api:run-artifacts"),
    )
    monkeypatch.setattr(
        "sentientos.forge_merge_train.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={
                "stability_doctrine.json": {"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False},
                "contract_status.json": {"contracts": [{"domain_name": "stability_doctrine", "drifted": False}]},
            },
            source="remote",
            errors=["bundle_missing_required:contract_manifest.json"],
            metadata={"sha": "abc"},
            metadata_ok=True,
        ),
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "remote_doctrine_manifest_missing"


def test_merge_train_blocks_on_remote_manifest_mismatch(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    monkeypatch.setattr(
        "sentientos.forge_merge_train.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=12, sha=sha, created_at="2026-01-01T00:00:00Z", selected_via="api:run-artifacts"),
    )
    monkeypatch.setattr(
        "sentientos.forge_merge_train.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={
                "stability_doctrine.json": {"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False},
                "contract_status.json": {"contracts": [{"domain_name": "stability_doctrine", "drifted": False}]},
            },
            source="remote",
            errors=["manifest_mismatch"],
            metadata={"sha": "abc"},
            metadata_ok=True,
            manifest_ok=False,
            failing_hash_paths=["stability_doctrine.json"],
        ),
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "remote_doctrine_manifest_mismatch"


def test_merge_train_mirror_fallback_passes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "0")
    monkeypatch.setenv("SENTIENTOS_CONTRACT_MIRROR_FETCH", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    monkeypatch.setattr(
        "sentientos.forge_merge_train.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}.zip", url="", run_id=0, sha=sha, created_at="2026-01-01T00:00:00Z", selected_via="mirror:release", source="mirror_release"),
    )
    monkeypatch.setattr(
        "sentientos.forge_merge_train.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={
                "stability_doctrine.json": {"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False},
                "contract_status.json": {"contracts": [{"domain_name": "stability_doctrine", "drifted": False}]},
            },
            source="remote",
            errors=[],
            metadata={"sha": artifact.sha, "repository": "o/r"},
            metadata_ok=True,
            manifest_ok=True,
            bundle_sha256="abc123",
            mirror_used=True,
        ),
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "mergeable"


def test_merge_train_writes_merge_receipt_with_doctrine_identity(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    monkeypatch.setattr(
        "sentientos.forge_merge_train.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=12, sha=sha, created_at="2026-01-01T00:00:00Z", selected_via="api:run-artifacts"),
    )
    monkeypatch.setattr(
        "sentientos.forge_merge_train.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={
                "stability_doctrine.json": {"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False},
                "contract_status.json": {"contracts": [{"domain_name": "stability_doctrine", "drifted": False}]},
            },
            source="remote",
            errors=[],
            metadata={"sha": artifact.sha},
            metadata_ok=True,
            manifest_ok=True,
            bundle_sha256="bundle-abc123",
        ),
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "merged"
    receipts = list((tmp_path / "glow/forge/receipts").glob("merge_receipt_*.json"))
    assert receipts
    payload = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert payload["doctrine_identity"]["bundle_sha256"] == "bundle-abc123"


def test_merge_train_local_fallback_identity_mismatch_reason(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "0")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    monkeypatch.setattr("sentientos.forge_merge_train.find_contract_artifact_for_sha", lambda pr_number, sha: None)
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"git_sha": "abc", "baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/contracts/contract_manifest.json").write_text(
        json.dumps({"bundle_sha256": "local-bundle", "file_sha256": {}}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_2026.json").write_text(
        json.dumps({"doctrine_identity": {"bundle_sha256": "expected-bundle"}}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "mergeable"
    state = train.load_state()
    assert state.entries[0].doctrine_gate_reason == "local_doctrine_identity_mismatch"


def test_merge_train_enforce_blocks_on_broken_receipt_chain(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_RECEIPT_CHAIN_ENFORCE", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_bad.json").write_text(
        json.dumps({"schema_version": 2, "receipt_id": "bad", "created_at": "2026-01-01T00:00:00Z", "receipt_hash": "deadbeef", "prev_receipt_hash": None}) + "\n",
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "receipt_chain_broken"


def test_merge_train_warn_allows_on_broken_receipt_chain(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_RECEIPT_CHAIN_WARN", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_bad.json").write_text(
        json.dumps({"schema_version": 2, "receipt_id": "bad", "created_at": "2026-01-01T00:00:00Z", "receipt_hash": "deadbeef", "prev_receipt_hash": None}) + "\n",
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "merged"
    assert result.get("reason") == "receipt_chain_warning"


def test_merge_train_anchor_enforce_blocks_when_missing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_RECEIPT_ANCHOR_ENFORCE", "1")
    monkeypatch.setenv("SENTIENTOS_ANCHOR_SIGNING", "hmac-test")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "receipt_anchor_missing"


def test_merge_train_anchor_warn_allows_and_marks_warning(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_RECEIPT_ANCHOR_WARN", "1")
    monkeypatch.setenv("SENTIENTOS_ANCHOR_SIGNING", "hmac-test")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "merged"
    assert result.get("reason") == "receipt_anchor_warning"


def test_merge_train_audit_chain_enforce_blocks(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_AUDIT_CHAIN_ENFORCE", "1")
    monkeypatch.setenv("SENTIENTOS_MODE_ALLOW_AUTOMERGE", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs/audit.jsonl").write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","data":{"a":1},"prev_hash":"deadbeef","rolling_hash":"deadbeef"}\n',
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "held"
    assert result["reason"] == "audit_chain_broken"


def test_merge_train_audit_chain_warn_allows(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_AUDIT_CHAIN_WARN", "1")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs/audit.jsonl").write_text(
        '{"timestamp":"2026-01-01T00:00:00Z","data":{"a":1},"prev_hash":"deadbeef","rolling_hash":"deadbeef"}\n',
        encoding="utf-8",
    )
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "merged"
    assert result.get("reason") == "audit_chain_warning"


def test_train_cautious_mode_disables_automerge(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_MODE_FORCE", "cautious")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n", encoding="utf-8")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["status"] == "mergeable"


def test_train_recovery_mode_holds_with_mode_reason(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_TRAIN_ENABLED", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_MODE_FORCE", "recovery")
    monkeypatch.setenv("SENTIENTOS_AUDIT_CHAIN_ENFORCE", "1")
    monkeypatch.setenv("SENTIENTOS_MODE_ALLOW_AUTOMERGE", "1")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(json.dumps({"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}) + "\n", encoding="utf-8")
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs/audit.jsonl").write_text('{"timestamp":"2026-01-01T00:00:00Z","data":{"a":1},"prev_hash":"deadbeef","rolling_hash":"deadbeef"}\n', encoding="utf-8")
    train = ForgeMergeTrain(repo_root=tmp_path, github_ops=_Ops())
    train.save_state(TrainState(entries=[_entry("ready")]))

    result = train.tick()

    assert result["reason"] in {"mode_recovery_hold", "risk_budget_throttle"}
