import json
from pathlib import Path

from sentientos.daemons.witness_daemon import WitnessDaemon
from witness.witness_rules import WitnessRules


def create_event(path: Path, name: str, payload: dict) -> Path:
    event_file = path / f"{name}.json"
    event_file.write_text(json.dumps(payload))
    return event_file


def test_witness_daemon_validates_and_quarantines(tmp_path):
    base_dir = tmp_path / "perception"
    audit_log = tmp_path / "audit" / "witness_log.jsonl"
    rules = WitnessRules(known_good_peers=["peer-123"])
    daemon = WitnessDaemon(base_dir=base_dir, audit_log=audit_log, rules=rules)

    incoming = base_dir / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    valid_event = {
        "source": "camera",
        "event_type": "frame",
        "payload": "frame-bytes",
        "timestamp": "2025-01-01T00:00:00Z",
        "signal_trust": 0.93,
    }

    spoofed_event = {
        "source": "mic",
        "event_type": "speech",
        "payload": "this is a spoof attempt",
        "timestamp": "2025-01-01T00:00:01Z",
        "signal_trust": 0.9,
    }

    missing_fields_event = {
        "source": "peer",
        "event_type": "hearing",
        "payload": "hello",
        # timestamp intentionally missing
        "signal_trust": 0.5,
        "peer_id": "peer-999",
    }

    create_event(incoming, "valid", valid_event)
    create_event(incoming, "spoofed", spoofed_event)
    create_event(incoming, "missing", missing_fields_event)

    daemon.monitor_once()

    validated_files = list((base_dir / "validated").glob("*.json"))
    suspect_files = list((base_dir / "suspect").glob("*.json"))

    assert len(validated_files) == 1
    assert len(suspect_files) == 2

    validated_content = json.loads(validated_files[0].read_text())
    assert validated_content["source"] == "camera"
    assert "witness_checksum" in validated_content
    assert "witness_stamp" in validated_content

    suspect_data = [json.loads(path.read_text()) for path in suspect_files]
    suspect_reasons = {item["witness_reasons"][0] for item in suspect_data}
    assert any("spoof" in reason for reason in suspect_reasons)
    assert any("signal trust below threshold" in reason or "missing fields" in reason for reason in suspect_reasons)

    log_lines = audit_log.read_text().strip().splitlines()
    assert len(log_lines) == 3

    log_entries = [json.loads(line) for line in log_lines]
    statuses = {entry["status"] for entry in log_entries}
    assert statuses == {"approved", "rejected"}

    sample_approval = next(entry for entry in log_entries if entry["status"] == "approved")
    sample_rejection = next(entry for entry in log_entries if entry["status"] == "rejected")

    assert "checksum" in sample_approval
    assert "reasons" in sample_rejection
    assert sample_rejection["reasons"]

    # Return a summary to satisfy prompt requirements
    valid_count = len(validated_files)
    suspect_count = len(suspect_files)
    assert (valid_count, suspect_count) == (1, 2)
