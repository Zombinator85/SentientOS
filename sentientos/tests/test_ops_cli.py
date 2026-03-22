from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import audit_immutability as ai

from scripts import node_bootstrap, system_constitution
from sentientos.ops import main as ops_main


def _seed_workspace(root: Path) -> None:
    (root / "vow").mkdir(parents=True, exist_ok=True)
    (root / "vow/immutable_manifest.json").write_text('{"schema_version":1,"files":{}}\n', encoding="utf-8")
    (root / "vow/invariants.yaml").write_text("version: 1\n", encoding="utf-8")


def test_unified_help_lists_domains() -> None:
    cp = subprocess.run([sys.executable, "-m", "sentientos.ops", "--help"], check=False, capture_output=True, text=True)
    assert cp.returncode == 0
    assert "node" in cp.stdout
    assert "constitution" in cp.stdout
    assert "forge" in cp.stdout
    assert "incident" in cp.stdout
    assert "audit" in cp.stdout
    assert "simulate" in cp.stdout
    assert "verify" in cp.stdout


def test_node_bootstrap_shim_routes_to_ops(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called: dict[str, object] = {}

    def _fake(argv, *, prog):  # type: ignore[no-untyped-def]
        called["argv"] = list(argv)
        called["prog"] = prog
        return 0

    monkeypatch.setattr("scripts.node_bootstrap.ops_main", _fake)
    assert node_bootstrap.main(["--json"]) == 0
    assert called["argv"] == ["node", "bootstrap", "--json"]
    assert called["prog"] == "node_bootstrap"


def test_unified_constitution_verify_and_script_parity(tmp_path: Path) -> None:
    _seed_workspace(tmp_path)
    rc_ops = ops_main(["--repo-root", str(tmp_path), "constitution", "verify"])
    rc_script = system_constitution.main(["--repo-root", str(tmp_path), "--verify"])
    assert rc_ops == 0
    assert rc_script == rc_ops




def test_constitution_latest_supports_json_output(tmp_path: Path, capsys) -> None:
    _seed_workspace(tmp_path)
    rc = ops_main(["--repo-root", str(tmp_path), "constitution", "latest", "--json"])
    assert rc in {0, 1, 2, 3}
    payload = json.loads(capsys.readouterr().out)
    assert "constitution_state" in payload
    assert "constitutional_digest" in payload


def test_forge_status_defaults_to_latest_mode(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    called: dict[str, object] = {}

    def _fake(argv):  # type: ignore[no-untyped-def]
        called["argv"] = list(argv)
        return 0

    monkeypatch.setattr("scripts.forge_status.main", _fake)
    rc = ops_main(["--repo-root", str(tmp_path), "forge", "status"])
    assert rc == 0
    assert called["argv"] == ["--latest", "--repo-root", str(tmp_path)]


def test_audit_verify_strips_passthrough_separator(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    called: dict[str, object] = {}

    def _fake(argv):  # type: ignore[no-untyped-def]
        called["argv"] = list(argv)
        return 0

    monkeypatch.setattr("sentientos.audit_tools.verify_audits_main", _fake)
    rc = ops_main(["--repo-root", str(tmp_path), "audit", "verify", "--json", "--", "--strict"])
    assert rc == 0
    assert called["argv"] == ["--json", "--strict", "--repo-root", str(tmp_path)]


def test_audit_immutability_uses_repo_root_for_manifest_resolution(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    called: dict[str, object] = {}

    def _fake(argv):  # type: ignore[no-untyped-def]
        called["argv"] = list(argv)
        called["cwd"] = str(Path.cwd())
        return 0

    monkeypatch.setattr("scripts.audit_immutability_verifier.main", _fake)
    rc = ops_main(["--repo-root", str(tmp_path), "audit", "immutability", "--allow-missing-manifest"])
    assert rc == 0
    assert called["cwd"] == str(tmp_path)
    assert called["argv"] == ["--allow-missing-manifest"]


def test_unified_audit_verify_module_surface(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"x": 1})
    env = os.environ.copy()
    env["LUMOS_AUTO_APPROVE"] = "1"
    env["PYTHONPATH"] = "."
    cp = subprocess.run([sys.executable, "-m", "sentientos.audit", "verify", str(tmp_path), "--json"], env=env, check=False, capture_output=True, text=True)
    assert cp.returncode == 0
    payload = json.loads(cp.stdout)
    assert payload["tool"] == "verify_audits"
    assert payload["status"] in {"passed", "failed"}


def test_unified_help_includes_workflow_examples() -> None:
    cp = subprocess.run([sys.executable, "-m", "sentientos.ops", "--help"], check=False, capture_output=True, text=True)
    assert cp.returncode == 0
    assert "Workflow examples:" in cp.stdout
    assert "node health --json" in cp.stdout
    assert "constitution verify --json" in cp.stdout
    assert "verify formal --json" in cp.stdout


def test_verify_formal_json_surface(tmp_path: Path, capsys) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    (tmp_path / "formal/specs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "formal/models").mkdir(parents=True, exist_ok=True)
    for src in (repo_root / "formal/specs").glob("*"):
        if src.is_file():
            (tmp_path / "formal/specs" / src.name).write_bytes(src.read_bytes())
    for src in (repo_root / "formal/models").glob("*.json"):
        (tmp_path / "formal/models" / src.name).write_bytes(src.read_bytes())

    rc = ops_main(["--repo-root", str(tmp_path), "verify", "formal", "--json"])
    assert rc in {0, 2}
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sentientos.ops"
    assert payload["command"] == "verify.formal"
    assert "spec_count" in payload
    assert "artifact_paths" in payload


def test_constitution_verify_supports_json_with_unified_envelope(tmp_path: Path, capsys) -> None:
    _seed_workspace(tmp_path)
    rc = ops_main(["--repo-root", str(tmp_path), "constitution", "verify", "--json"])
    assert rc in {0, 1, 2, 3}
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sentientos.ops"
    assert payload["command"] == "constitution.verify"
    assert payload["status"] == payload["constitution_state"]
    assert payload["exit_code"] == rc


def test_node_health_json_uses_unified_envelope(tmp_path: Path, capsys) -> None:
    _seed_workspace(tmp_path)
    rc = ops_main(["--repo-root", str(tmp_path), "node", "health", "--json"])
    assert rc in {0, 1, 2, 3}
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sentientos.ops"
    assert payload["command"] == "node.health"
    assert payload["status"] == payload["health_state"]
    assert payload["exit_code"] == rc


def test_help_surfaces_operator_friendly_flags() -> None:
    cp = subprocess.run([sys.executable, "-m", "sentientos.ops", "audit", "immutability", "--help"], check=False, capture_output=True, text=True)
    assert cp.returncode == 0
    assert "--manifest" in cp.stdout
    assert "--allow-missing-manifest" in cp.stdout


def test_unified_help_lists_observatory_domain() -> None:
    cp = subprocess.run([sys.executable, "-m", "sentientos.ops", "--help"], check=False, capture_output=True, text=True)
    assert cp.returncode == 0
    assert "observatory" in cp.stdout


def test_observatory_fleet_json_surface(tmp_path: Path, capsys) -> None:
    (tmp_path / "glow").mkdir(parents=True, exist_ok=True)
    rc = ops_main(["--repo-root", str(tmp_path), "observatory", "fleet", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sentientos.ops"
    assert payload["command"] == "observatory.fleet"
    assert "release_readiness" in payload
    assert "artifact_paths" in payload
    assert "broad_lane_rows" in payload


def test_observatory_artifacts_json_surface(tmp_path: Path, capsys) -> None:
    (tmp_path / "glow").mkdir(parents=True, exist_ok=True)
    rc = ops_main(["--repo-root", str(tmp_path), "observatory", "artifacts", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sentientos.ops"
    assert payload["command"] == "observatory.artifacts"
    assert "latest_pointers" in payload


def test_observatory_artifacts_surface_selector(tmp_path: Path, capsys) -> None:
    (tmp_path / "glow/observatory").mkdir(parents=True, exist_ok=True)
    rc = ops_main(["--repo-root", str(tmp_path), "observatory", "artifacts", "--surface", "wan_gate", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_surface"] == "wan_gate"
    assert isinstance(payload["selected_pointer"], dict)
    assert isinstance(payload["selected_summary_rows"], list)
    assert payload["selected_summary_rows"][0]["row_id"] in {"wan_release_gate", "wan_gate_missing"}


def test_observatory_artifacts_contract_status_surface_selector_rows(tmp_path: Path, capsys) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/contract_status.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-03-21T00:00:00Z",
                "contracts": [
                    {
                        "domain_name": "audits",
                        "baseline_present": True,
                        "drifted": False,
                        "drift_type": "none",
                        "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_AUDIT_DRIFT",
                    },
                    {
                        "domain_name": "perception",
                        "baseline_present": True,
                        "drifted": True,
                        "drift_type": "required_keys_changed",
                        "drift_explanation": "required keys diverged from baseline",
                        "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_PERCEPTION_SCHEMA_DRIFT",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "glow/observatory").mkdir(parents=True, exist_ok=True)
    rc = ops_main(["--repo-root", str(tmp_path), "observatory", "artifacts", "--surface", "contract_status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_surface"] == "contract_status"
    assert isinstance(payload["selected_pointer"], dict)
    assert isinstance(payload["selected_summary_rows"], list)
    rows = {row["domain"]: row for row in payload["selected_summary_rows"]}
    assert rows["audits"]["status"] == "healthy"
    assert rows["perception"]["status"] == "drifted"
    assert rows["audits"]["freshness_posture"] == "fresh_evidence"
    assert rows["audits"]["alert_kind"] == "informational"
    assert rows["perception"]["alert_kind"] == "domain_drift"


def test_observatory_artifacts_broad_lane_surface_selector_exposes_lane_rows(tmp_path: Path, capsys) -> None:
    (tmp_path / "glow/observatory").mkdir(parents=True, exist_ok=True)
    rc = ops_main(["--repo-root", str(tmp_path), "observatory", "artifacts", "--surface", "broad_lane_latest_summary", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_surface"] == "broad_lane_latest_summary"
    assert isinstance(payload["selected_pointer"], dict)
    assert isinstance(payload["selected_summary_rows"], list)
    assert payload["selected_summary_rows"] == []
    assert isinstance(payload["selected_broad_lane_rows"], list)
    rows = {row["lane"]: row for row in payload["selected_broad_lane_rows"]}
    assert "run_tests" in rows
    assert "mypy" in rows


def test_observatory_artifacts_surface_selector_fallback_when_summary_rows_absent(tmp_path: Path, capsys) -> None:
    (tmp_path / "glow/observatory").mkdir(parents=True, exist_ok=True)
    rc = ops_main(["--repo-root", str(tmp_path), "observatory", "artifacts", "--surface", "formal_verification", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_surface"] == "formal_verification"
    assert isinstance(payload["selected_pointer"], dict)
    assert isinstance(payload["selected_summary_rows"], list)
    assert payload["selected_summary_rows"] == []


def test_observatory_artifacts_fleet_surface_includes_contract_alert_semantics(tmp_path: Path, capsys) -> None:
    (tmp_path / "glow/contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "glow/contracts/contract_status.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2020-01-01T00:00:00Z",
                "contracts": [
                    {
                        "domain_name": "audits",
                        "baseline_present": True,
                        "drifted": False,
                        "drift_type": "none",
                        "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_AUDIT_DRIFT",
                    },
                    {
                        "domain_name": "federation_identity",
                        "baseline_present": False,
                        "drifted": None,
                        "drift_type": "baseline_missing",
                        "strict_gate_envvar": "SENTIENTOS_CI_FAIL_ON_FEDERATION_IDENTITY_DRIFT",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "glow/observatory").mkdir(parents=True, exist_ok=True)
    rc = ops_main(["--repo-root", str(tmp_path), "observatory", "artifacts", "--surface", "fleet_observatory", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    row = payload["selected_summary_rows"][0]
    assert row["contract_alert_badge"] == "baseline_absent"
    assert row["contract_alert_reason"] == "baseline_missing_rows_present"
    assert row["contract_alert_counts"]["freshness_issue"] == 1
    assert row["contract_alert_counts"]["baseline_absent"] == 1
