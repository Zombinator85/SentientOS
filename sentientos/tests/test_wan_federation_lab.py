from __future__ import annotations

import json
from pathlib import Path

from sentientos.lab import (
    deterministic_multihost_topology,
    deterministic_wan_fault_schedule,
    list_wan_scenarios,
    run_wan_federation_lab,
)
from sentientos.ops import main as ops_main
from sentientos.lab.wan_federation import HostSpec
from sentientos.lab.wan_federation import SSHTransport
from sentientos.lab.wan_federation import classify_remote_preflight
from sentientos.lab.wan_federation import remote_preflight_observatory_report


def test_topology_determinism() -> None:
    host_objs = [
        HostSpec(host_id="host-01", transport="local", runtime_root="/tmp/h1"),
        HostSpec(host_id="host-02", transport="local", runtime_root="/tmp/h2"),
        HostSpec(host_id="host-03", transport="local", runtime_root="/tmp/h3"),
    ]
    first = deterministic_multihost_topology(topology="three_host_ring", seed=11, hosts=host_objs, nodes_per_host=1)
    second = deterministic_multihost_topology(topology="three_host_ring", seed=11, hosts=host_objs, nodes_per_host=1)
    assert first == second
    assert len(first["nodes"]) == 3


def test_wan_schedule_determinism_and_bound() -> None:
    first = deterministic_wan_fault_schedule(scenario="wan_partition_recovery", topology="three_host_ring", seed=4, duration_s=2.0)
    second = deterministic_wan_fault_schedule(scenario="wan_partition_recovery", topology="three_host_ring", seed=4, duration_s=2.0)
    assert first == second
    assert all(0.0 <= float(row["offset_s"]) <= 2.0 for row in first)


def test_wan_run_generates_manifests(tmp_path: Path) -> None:
    payload = run_wan_federation_lab(
        tmp_path,
        scenario_name="wan_partition_recovery",
        topology_name="three_host_ring",
        seed=3,
        runtime_s=1.2,
        nodes_per_host=1,
        hosts_file=None,
        emit_bundle=True,
        truth_oracle=True,
        emit_replay=False,
        clean=True,
    )
    run_root = tmp_path / payload["artifact_paths"]["run_root"]
    assert payload["family"] == "wan"
    assert (run_root / "host_manifest.json").exists()
    assert (run_root / "topology_manifest.json").exists()
    assert (run_root / "artifact_hash_manifest.json").exists()
    assert (run_root / "wan_truth/truth_oracle_summary.json").exists()
    assert (run_root / "node_truth_manifest.json").exists()
    assert (run_root / "node_evidence_summary.json").exists()
    assert (run_root / "scenario_evidence_enrichment.json").exists()
    assert (run_root / "wan_truth/scenario_evidence_completeness.json").exists()
    assert (run_root / "wan_truth/evidence_density_report.json").exists()
    manifest = json.loads((run_root / "node_truth_manifest.json").read_text(encoding="utf-8"))
    assert manifest["node_count"] >= 1


def test_ops_wan_routing(tmp_path: Path, capsys) -> None:
    rc = ops_main(
        [
            "--repo-root",
            str(tmp_path),
            "lab",
            "federation",
            "--wan",
            "--scenario",
            "wan_partition_recovery",
            "--topology",
            "three_host_ring",
            "--json",
        ]
    )
    assert rc in {0, 1}
    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line.strip()][-1])
    assert payload["family"] == "wan"


def test_wan_scenarios_listed() -> None:
    names = {row["name"] for row in list_wan_scenarios()}
    assert {"wan_partition_recovery", "wan_asymmetric_loss", "wan_epoch_rotation_under_partition"}.issubset(names)


def test_ops_wan_truth_oracle_routing(tmp_path: Path, capsys) -> None:
    rc = ops_main([
        "--repo-root",
        str(tmp_path),
        "lab",
        "federation",
        "--wan",
        "--truth-oracle",
        "--scenario",
        "wan_partition_recovery",
        "--topology",
        "three_host_ring",
        "--json",
    ])
    assert rc in {0, 1}
    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line.strip()][-1])
    assert "truth_oracle" in payload


def test_ops_wan_gate_routing(tmp_path: Path, capsys) -> None:
    rc = ops_main([
        "--repo-root",
        str(tmp_path),
        "lab",
        "federation",
        "--wan-gate",
        "--scenario",
        "wan_partition_recovery",
        "--topology",
        "three_host_ring",
        "--json",
    ])
    assert rc in {0, 1, 2, 3}
    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line.strip()][-1])
    assert payload["suite"] == "wan_release_gate"


def test_ops_lab_help_mentions_wan_gate(capsys) -> None:
    try:
        ops_main(["lab", "federation", "--help"])
    except SystemExit as exc:
        assert int(exc.code) == 0
    out = capsys.readouterr().out
    assert "--wan-gate" in out
    assert "--remote-preflight-report" in out


def test_load_hosts_yaml_and_metadata(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts.yaml"
    hosts.write_text(
        """
hosts:
  - host_id: host-02
    transport: ssh
    address: 127.0.0.1
    user: runner
    runtime_root: /tmp/sentientos-h2
    tags: [b, a]
    capabilities: [python3, ssh]
  - host_id: host-01
    transport: local
    runtime_root: /tmp/sentientos-h1
""",
        encoding="utf-8",
    )
    payload = run_wan_federation_lab(
        tmp_path,
        scenario_name="wan_partition_recovery",
        topology_name="three_host_ring",
        seed=6,
        runtime_s=0.4,
        nodes_per_host=1,
        hosts_file=hosts,
        emit_bundle=False,
        truth_oracle=False,
        emit_replay=False,
        clean=True,
    )
    normalized = payload["hosts"]
    assert [row["host_id"] for row in normalized] == ["host-01", "host-02"]
    assert tuple(normalized[1]["tags"]) == ("a", "b")


def test_remote_smoke_requires_hosts(tmp_path: Path) -> None:
    try:
        run_wan_federation_lab(
            tmp_path,
            scenario_name="remote_partition_recovery_smoke",
            topology_name="three_host_ring",
            seed=2,
            runtime_s=1.0,
            nodes_per_host=1,
            hosts_file=None,
            emit_bundle=False,
            truth_oracle=False,
            emit_replay=False,
            clean=True,
            remote_smoke=True,
        )
    except ValueError as exc:
        assert "requires --hosts" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_ssh_command_construction() -> None:
    transport = SSHTransport()
    host = HostSpec(host_id="h1", transport="ssh", runtime_root="/r", user="u", address="example")
    cmd = transport.build_ssh_command(host, ["python", "-m", "sentientos.ops"], cwd="/opt/repo")
    assert cmd[0] == "ssh"
    assert cmd[1] == "u@example"
    assert "cd /opt/repo" in cmd[-1]


def test_ops_remote_smoke_routing(tmp_path: Path, capsys) -> None:
    hosts = tmp_path / "hosts.json"
    hosts.write_text(
        json.dumps(
            {
                "hosts": [
                    {"host_id": "host-01", "transport": "local", "runtime_root": str(tmp_path / "h1")},
                    {"host_id": "host-02", "transport": "local", "runtime_root": str(tmp_path / "h2")},
                    {"host_id": "host-03", "transport": "local", "runtime_root": str(tmp_path / "h3")},
                ]
            }
        ),
        encoding="utf-8",
    )
    rc = ops_main([
        "--repo-root",
        str(tmp_path),
        "lab",
        "federation",
        "--wan",
        "--remote-smoke",
        "--hosts",
        str(hosts),
        "--scenario",
        "remote_partition_recovery_smoke",
        "--json",
    ])
    assert rc in {0, 1}
    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line.strip()][-1])
    assert payload["remote_smoke"] is True
    run_root = tmp_path / payload["artifact_paths"]["run_root"]
    assert (run_root / "remote_preflight_report.json").exists()
    assert (run_root / "remote_artifact_collection.json").exists()


def test_classify_remote_preflight_transport_auth_failure() -> None:
    status, labels = classify_remote_preflight(
        check={"exit_code": 255, "stderr": "Permission denied (publickey)"},
        mkdir={"exit_code": 255, "stderr": "Permission denied"},
    )
    assert status == "transport_auth_failure"
    assert "transport_auth_failure" in labels


def test_remote_preflight_observatory_rollup(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts.json"
    hosts.write_text(json.dumps({"hosts": [{"host_id": "host-01", "transport": "local", "runtime_root": str(tmp_path / "h1")}, {"host_id": "host-02", "transport": "local", "runtime_root": str(tmp_path / "h2")}, {"host_id": "host-03", "transport": "local", "runtime_root": str(tmp_path / "h3")}]}), encoding="utf-8")
    payload = run_wan_federation_lab(
        tmp_path,
        scenario_name="remote_partition_recovery_smoke",
        topology_name="three_host_ring",
        seed=5,
        runtime_s=0.5,
        nodes_per_host=1,
        hosts_file=hosts,
        emit_bundle=False,
        truth_oracle=False,
        emit_replay=False,
        clean=True,
        remote_smoke=True,
    )
    report = remote_preflight_observatory_report(tmp_path)
    assert report["suite"] == "remote_preflight_observatory"
    assert "rollup" in report
    assert "trend" in report
    assert payload["failure_classification"] in {
        "passed",
        "remote_transport_or_auth_failure",
        "remote_environment_drift_or_provisioning_failure",
        "scenario_or_runtime_regression",
        "truth_or_gate_contradiction_failure",
    }


def test_ops_remote_preflight_report_route(tmp_path: Path, capsys) -> None:
    rc = ops_main(["--repo-root", str(tmp_path), "lab", "federation", "--remote-preflight-report", "--json"])
    assert rc == 0
    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line.strip()][-1])
    assert payload["suite"] == "remote_preflight_observatory"
