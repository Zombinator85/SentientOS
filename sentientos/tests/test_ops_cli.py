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


def test_help_surfaces_operator_friendly_flags() -> None:
    cp = subprocess.run([sys.executable, "-m", "sentientos.ops", "audit", "immutability", "--help"], check=False, capture_output=True, text=True)
    assert cp.returncode == 0
    assert "--manifest" in cp.stdout
    assert "--allow-missing-manifest" in cp.stdout
