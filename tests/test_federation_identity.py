from pathlib import Path

from sentientos.federation.identity import NodeId, build_node_id_payload, compute_fingerprint


def test_compute_fingerprint_stable(tmp_path: Path) -> None:
    config = {"runtime": {"root": str(tmp_path), "watchdog_interval": 5}}
    fp1 = compute_fingerprint(node_name="APRIL-PC01", runtime_root=tmp_path, config=config)
    fp2 = compute_fingerprint(node_name="APRIL-PC01", runtime_root=tmp_path, config=config)
    assert fp1 == fp2
    assert len(fp1) == 12


def test_compute_fingerprint_changes_with_inputs(tmp_path: Path) -> None:
    config = {"runtime": {"root": str(tmp_path), "watchdog_interval": 5}}
    fp_name = compute_fingerprint(node_name="APRIL-PC01", runtime_root=tmp_path, config=config)
    fp_other = compute_fingerprint(node_name="MAY-PC02", runtime_root=tmp_path, config=config)
    config_variant = {"runtime": {"root": str(tmp_path), "watchdog_interval": 10}}
    fp_config = compute_fingerprint(node_name="APRIL-PC01", runtime_root=tmp_path, config=config_variant)
    assert fp_name != fp_other
    assert fp_name != fp_config


def test_build_node_id_payload() -> None:
    node = build_node_id_payload("NodeA", "abc123")
    assert isinstance(node, NodeId)
    assert node.name == "NodeA"
    assert node.fingerprint == "abc123"
