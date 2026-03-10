from __future__ import annotations

import json
from pathlib import Path

from sentientos.attestation import read_json
from sentientos.node_operations import build_incident_bundle, node_health, run_bootstrap


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_workspace(root: Path) -> None:
    _write_json(root / "vow/immutable_manifest.json", {"schema_version": 1, "files": {}})
    (root / "vow/invariants.yaml").parent.mkdir(parents=True, exist_ok=True)
    (root / "vow/invariants.yaml").write_text("version: 1\n", encoding="utf-8")


def test_fresh_bootstrap_converges_and_writes_cockpit_artifacts(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    report = run_bootstrap(tmp_path, reason="test-bootstrap", seed_minimal=True, allow_restore=True)

    assert report["health_state"] in {"healthy", "degraded", "restricted"}
    assert (tmp_path / "glow/operators/operator_summary.json").exists()
    assert (tmp_path / "glow/operators/peer_health_summary.json").exists()
    assert (tmp_path / "glow/operators/current_restrictions.json").exists()
    assert (tmp_path / "glow/operators/restoration_history.jsonl").exists()


def test_node_health_agrees_with_bootstrap_state(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    bootstrap = run_bootstrap(tmp_path, reason="agreement", seed_minimal=True, allow_restore=True)
    health = node_health(tmp_path)

    assert health["health_state"] == bootstrap["health_state"]
    assert health["exit_code"] == bootstrap["exit_code"]


def test_operator_summary_deterministic_for_stable_inputs(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)

    run_bootstrap(tmp_path, reason="determinism-a", seed_minimal=True, allow_restore=True)
    summary_a = read_json(tmp_path / "glow/operators/operator_summary.json")
    run_bootstrap(tmp_path, reason="determinism-b", seed_minimal=True, allow_restore=True)
    summary_b = read_json(tmp_path / "glow/operators/operator_summary.json")

    for payload in (summary_a, summary_b):
        payload.pop("generated_at", None)
        high = payload.get("recent_high_impact_actions")
        if isinstance(high, dict):
            high.pop("restoration", None)
    assert summary_a == summary_b


def test_incident_bundle_has_manifest_hash_and_bounded_logs(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    run_bootstrap(tmp_path, reason="bundle", seed_minimal=True, allow_restore=True)

    for idx in range(12):
        with (tmp_path / "glow/operators/restoration_history.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"idx": idx}, sort_keys=True) + "\n")

    report = build_incident_bundle(tmp_path, reason="triage", window=5)
    manifest = read_json(tmp_path / report["manifest_path"])

    assert report["included_count"] >= 1
    assert manifest["collection_window"] == 5
    bounded = [item for item in manifest["included_files"] if item["path"] == "glow/operators/restoration_history.jsonl"]
    assert bounded
    assert bounded[0]["bounded_rows"] <= 5


def test_restore_flow_preserves_broken_history_and_writes_checkpoint(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_workspace(tmp_path)
    broken = '{"timestamp":"2026-01-01T00:00:00Z","data":{"ok":true},"prev_hash":"bad","rolling_hash":"bad"}\n'
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs/privileged_audit.jsonl").write_text(broken, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    report = run_bootstrap(tmp_path, reason="restore", seed_minimal=True, allow_restore=True)

    assert (tmp_path / "logs/privileged_audit.jsonl").read_text(encoding="utf-8") == broken
    assert any(phase["phase"] == "restore_and_reanchor" for phase in report["phases"])
