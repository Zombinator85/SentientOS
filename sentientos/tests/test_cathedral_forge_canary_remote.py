from __future__ import annotations

from pathlib import Path

from sentientos.cathedral_forge import CathedralForge
from sentientos.forge_goals import resolve_goal
from sentientos.forge_model import ForgeSession
from sentientos.github_artifacts import ArtifactRef, ContractBundle
from sentientos.github_checks import PRChecks, PRRef


class _Prov:
    def __init__(self) -> None:
        self.steps: list[str] = []

    def make_step(self, **kwargs):  # type: ignore[no-untyped-def]
        self.steps.append(str(kwargs.get("step_id", "")))
        return kwargs

    def add_step(self, step, *, stdout: str = "", stderr: str = ""):  # type: ignore[no-untyped-def]
        _ = step, stdout, stderr


def test_canary_remote_doctrine_red_blocks_automerge(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOPR", "0")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        '{"baseline_integrity_ok": true, "runtime_integrity_ok": true, "baseline_unexpected_change_detected": false}\n',
        encoding="utf-8",
    )

    forge = CathedralForge(repo_root=tmp_path)
    prov = _Prov()
    forge._active_provenance = prov  # type: ignore[assignment]
    monkeypatch.setattr("sentientos.cathedral_forge.detect_capabilities", lambda: {"gh": True, "token": False})

    pr = PRRef(number=7, url="https://github.com/o/r/pull/7", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    checks = PRChecks(pr=pr, checks=[], overall="success")
    monkeypatch.setattr("sentientos.cathedral_forge.wait_for_pr_checks", lambda pr_ref, timeout_seconds, poll_interval_seconds: (checks, {"timed_out": False}))
    monkeypatch.setattr(
        "sentientos.cathedral_forge.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=11, sha=sha, created_at="2026-01-01T00:00:00Z"),
    )
    monkeypatch.setattr(
        "sentientos.cathedral_forge.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={"stability_doctrine.json": {"baseline_integrity_ok": False, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}},
            source="remote",
            errors=[],
        ),
    )

    notes, remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )

    assert "publish_remote_doctrine_gated" in notes
    assert "held_remote_doctrine" in notes
    assert remote["automerge_result"] == "not_attempted"
    assert "publish_contract_bundle_downloaded" in prov.steps


def test_canary_remote_metadata_mismatch_blocks_automerge(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")

    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        "{\"baseline_integrity_ok\": true, \"runtime_integrity_ok\": true, \"baseline_unexpected_change_detected\": false}\n",
        encoding="utf-8",
    )

    forge = CathedralForge(repo_root=tmp_path)
    monkeypatch.setattr("sentientos.cathedral_forge.detect_capabilities", lambda: {"gh": True, "token": False})

    pr = PRRef(number=7, url="https://github.com/o/r/pull/7", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    checks = PRChecks(pr=pr, checks=[], overall="success")
    monkeypatch.setattr("sentientos.cathedral_forge.wait_for_pr_checks", lambda pr_ref, timeout_seconds, poll_interval_seconds: (checks, {"timed_out": False}))
    monkeypatch.setattr(
        "sentientos.cathedral_forge.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=11, sha=sha, created_at="2026-01-01T00:00:00Z", selected_via="api:run-artifacts"),
    )
    monkeypatch.setattr(
        "sentientos.cathedral_forge.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={"stability_doctrine.json": {"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}},
            source="remote",
            errors=["metadata_mismatch:sha"],
            metadata={"sha": "different"},
            metadata_ok=False,
        ),
    )

    notes, remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )

    assert "remote_doctrine_metadata_mismatch" in notes
    assert "held_remote_doctrine" in notes
    assert remote["automerge_result"] == "not_attempted"


def test_canary_remote_missing_allows_when_not_required(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "0")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        "{\"baseline_integrity_ok\": true, \"runtime_integrity_ok\": true, \"baseline_unexpected_change_detected\": false}\n",
        encoding="utf-8",
    )

    forge = CathedralForge(repo_root=tmp_path)
    monkeypatch.setattr("sentientos.cathedral_forge.detect_capabilities", lambda: {"gh": True, "token": False})

    pr = PRRef(number=7, url="https://github.com/o/r/pull/7", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    checks = PRChecks(pr=pr, checks=[], overall="success")
    monkeypatch.setattr("sentientos.cathedral_forge.wait_for_pr_checks", lambda pr_ref, timeout_seconds, poll_interval_seconds: (checks, {"timed_out": False}))
    monkeypatch.setattr("sentientos.cathedral_forge.find_contract_artifact_for_sha", lambda pr_number, sha: None)

    notes, remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )

    assert "publish_contract_artifact_missing" in notes
    assert "held_remote_doctrine" not in notes
    assert remote["automerge_result"] == "not_attempted"


def test_canary_remote_manifest_mismatch_blocks_automerge(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")

    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        "{\"baseline_integrity_ok\": true, \"runtime_integrity_ok\": true, \"baseline_unexpected_change_detected\": false}\n",
        encoding="utf-8",
    )

    forge = CathedralForge(repo_root=tmp_path)
    monkeypatch.setattr("sentientos.cathedral_forge.detect_capabilities", lambda: {"gh": True, "token": False})

    pr = PRRef(number=7, url="https://github.com/o/r/pull/7", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    checks = PRChecks(pr=pr, checks=[], overall="success")
    monkeypatch.setattr("sentientos.cathedral_forge.wait_for_pr_checks", lambda pr_ref, timeout_seconds, poll_interval_seconds: (checks, {"timed_out": False}))
    monkeypatch.setattr(
        "sentientos.cathedral_forge.find_contract_artifact_for_sha",
        lambda pr_number, sha: ArtifactRef(name=f"sentientos-contracts-{sha}", url="", run_id=11, sha=sha, created_at="2026-01-01T00:00:00Z", selected_via="api:run-artifacts"),
    )
    monkeypatch.setattr(
        "sentientos.cathedral_forge.download_contract_bundle",
        lambda artifact, dest: ContractBundle(
            sha=artifact.sha,
            paths={},
            parsed={"stability_doctrine.json": {"baseline_integrity_ok": True, "runtime_integrity_ok": True, "baseline_unexpected_change_detected": False}},
            source="remote",
            errors=["manifest_mismatch"],
            metadata={"sha": "abc"},
            metadata_ok=True,
            manifest_ok=False,
            failing_hash_paths=["contract_status.json"],
        ),
    )

    notes, remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )

    assert "remote_doctrine_manifest_mismatch" in notes
    assert "held_remote_doctrine" in notes
    assert remote["automerge_result"] == "not_attempted"


def test_canary_local_fallback_identity_mismatch_records_reason(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "0")
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        '{"git_sha":"abc","baseline_integrity_ok": true, "runtime_integrity_ok": true, "baseline_unexpected_change_detected": false}\n',
        encoding="utf-8",
    )
    (tmp_path / "glow/contracts/contract_manifest.json").write_text(
        '{"bundle_sha256":"local-bundle","file_sha256":{}}\n',
        encoding="utf-8",
    )
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_1.json").write_text(
        '{"doctrine_identity":{"bundle_sha256":"expected-bundle"}}\n',
        encoding="utf-8",
    )

    forge = CathedralForge(repo_root=tmp_path)
    monkeypatch.setattr("sentientos.cathedral_forge.detect_capabilities", lambda: {"gh": True, "token": False})

    pr = PRRef(number=7, url="https://github.com/o/r/pull/7", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    checks = PRChecks(pr=pr, checks=[], overall="success")
    monkeypatch.setattr("sentientos.cathedral_forge.wait_for_pr_checks", lambda pr_ref, timeout_seconds, poll_interval_seconds: (checks, {"timed_out": False}))
    monkeypatch.setattr("sentientos.cathedral_forge.find_contract_artifact_for_sha", lambda pr_number, sha: None)

    notes, remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )

    assert "local_doctrine_identity_mismatch" in notes
    assert remote["doctrine_gate_reason"] == "local_doctrine_identity_mismatch"


def test_canary_receipt_chain_enforce_blocks_automerge(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "1")
    monkeypatch.setenv("SENTIENTOS_RECEIPT_CHAIN_ENFORCE", "1")

    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        '{"baseline_integrity_ok": true, "runtime_integrity_ok": true, "baseline_unexpected_change_detected": false}\n',
        encoding="utf-8",
    )
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_bad.json").write_text(
        '{"schema_version":2,"receipt_id":"bad","created_at":"2026-01-01T00:00:00Z","receipt_hash":"deadbeef","prev_receipt_hash":null}\n',
        encoding="utf-8",
    )

    forge = CathedralForge(repo_root=tmp_path)
    monkeypatch.setattr("sentientos.cathedral_forge.detect_capabilities", lambda: {"gh": True, "token": False})

    pr = PRRef(number=7, url="https://github.com/o/r/pull/7", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    checks = PRChecks(pr=pr, checks=[], overall="success")
    monkeypatch.setattr("sentientos.cathedral_forge.wait_for_pr_checks", lambda pr_ref, timeout_seconds, poll_interval_seconds: (checks, {"timed_out": False}))
    monkeypatch.setattr("sentientos.cathedral_forge.find_contract_artifact_for_sha", lambda pr_number, sha: None)

    notes, remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )

    assert "receipt_chain_broken" in notes
    assert remote["automerge_result"] == "receipt_chain_broken"


def test_canary_receipt_chain_warn_records_warning(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_FORGE_ALLOW_AUTOPUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_CANARY_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_FORGE_AUTOMERGE", "0")
    monkeypatch.setenv("SENTIENTOS_RECEIPT_CHAIN_WARN", "1")

    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/stability_doctrine.json").write_text(
        '{"baseline_integrity_ok": true, "runtime_integrity_ok": true, "baseline_unexpected_change_detected": false}\n',
        encoding="utf-8",
    )
    (tmp_path / "glow/forge/receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/forge/receipts/merge_receipt_bad.json").write_text(
        '{"schema_version":2,"receipt_id":"bad","created_at":"2026-01-01T00:00:00Z","receipt_hash":"deadbeef","prev_receipt_hash":null}\n',
        encoding="utf-8",
    )

    forge = CathedralForge(repo_root=tmp_path)
    monkeypatch.setattr("sentientos.cathedral_forge.detect_capabilities", lambda: {"gh": True, "token": False})

    pr = PRRef(number=7, url="https://github.com/o/r/pull/7", head_sha="abc", branch="b", created_at="2026-01-01T00:00:00Z")
    checks = PRChecks(pr=pr, checks=[], overall="success")
    monkeypatch.setattr("sentientos.cathedral_forge.wait_for_pr_checks", lambda pr_ref, timeout_seconds, poll_interval_seconds: (checks, {"timed_out": False}))
    monkeypatch.setattr("sentientos.cathedral_forge.find_contract_artifact_for_sha", lambda pr_number, sha: None)

    notes, _remote = forge._maybe_publish(
        resolve_goal("forge_smoke_noop"),
        ForgeSession(session_id="1", root_path=str(tmp_path), strategy="x", branch_name="b"),
        improvement_summary=None,
        ci_baseline_before=None,
        ci_baseline_after=None,
        metadata=None,
    )

    assert "receipt_chain_warning" in notes
