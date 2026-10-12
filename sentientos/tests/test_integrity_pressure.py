from __future__ import annotations

import json
from datetime import datetime
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from sentientos.forge_merge_train import ForgeMergeTrain
from sentientos.integrity_incident import (
    INCIDENTS_DIR,
    IntegrityIncidentArtifactError,
    IntegrityIncidentFeedRecordError,
    Incident,
    MAX_INCIDENT_ARTIFACT_BYTES,
    append_incident_feed,
    inspect_quarantine_incident_custody,
    write_incident,
)
from sentientos.integrity_pressure import (
    MAX_INCIDENT_FEED_BYTES, MAX_INCIDENT_ROWS, MAX_INCIDENT_ROW_BYTES,
    IntegrityPressureInputError, apply_escalation, compute_integrity_pressure,
    parse_bounded_incident_feed,
)


def _write_incidents(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(body, encoding="utf-8")


def test_compute_pressure_from_synthetic_incidents(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _write_incidents(
        tmp_path / "pulse/integrity_incidents.jsonl",
        [
            {
                "created_at": "2026-01-01T00:00:00Z",
                "enforcement_mode": "warn",
                "triggers": ["receipt_chain_broken"],
                "quarantine_activated": False,
            },
            {
                "created_at": "2026-01-01T00:30:00Z",
                "enforcement_mode": "enforce",
                "triggers": ["audit_chain_broken", "receipt_chain_broken"],
                "quarantine_activated": True,
            },
            {
                "created_at": "2025-12-31T00:30:00Z",
                "enforcement_mode": "enforce",
                "triggers": ["old"],
                "quarantine_activated": True,
            },
        ],
    )
    monkeypatch.setenv("SENTIENTOS_PRESSURE_WARN_THRESHOLD", "2")
    monkeypatch.setenv("SENTIENTOS_PRESSURE_ENFORCE_THRESHOLD", "4")
    monkeypatch.setenv("SENTIENTOS_PRESSURE_CRITICAL_THRESHOLD", "7")

    snapshot = compute_integrity_pressure(tmp_path, now=datetime.fromisoformat("2026-01-01T01:00:00+00:00"))

    assert snapshot.metrics.incidents_last_1h == 2
    assert snapshot.metrics.incidents_last_24h == 2
    assert snapshot.metrics.enforced_failures_last_24h == 1
    assert snapshot.metrics.unique_trigger_types_last_24h == 2
    assert snapshot.metrics.quarantine_activations_last_24h == 1
    assert snapshot.level == 2


@pytest.mark.no_legacy_skip
def test_incident_owner_publishes_rows_accepted_by_bounded_pressure_reader(
    tmp_path: Path,
) -> None:
    incident = Incident(
        schema_version=1,
        incident_id="incident-bounded-1",
        created_at="2026-10-12T00:00:00Z",
        severity="warning",
        triggers=["receipt_chain_warning"],
        enforcement_mode="warn",
        context={},
        evidence_paths=[],
        suggested_actions=[],
    )
    write_incident(tmp_path, incident)

    snapshot = compute_integrity_pressure(tmp_path)
    assert snapshot.metrics.incidents_last_24h == 1
    assert snapshot.metrics.unique_trigger_types_last_24h == 1


@pytest.mark.no_legacy_skip
def test_incident_owner_rejects_row_outside_reader_trigger_bound_before_writing(
    tmp_path: Path,
) -> None:
    incident = Incident(
        schema_version=1,
        incident_id="incident-oversized-trigger",
        created_at="2026-10-12T00:00:00Z",
        severity="warning",
        triggers=["x" * 513],
        enforcement_mode="warn",
        context={},
        evidence_paths=[],
        suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentFeedRecordError) as raised:
        write_incident(tmp_path, incident)
    assert raised.value.code == "incident_feed_trigger_limit_exceeded"
    assert not list((tmp_path / INCIDENTS_DIR).glob("incident_*.json"))
    assert not (tmp_path / "pulse/integrity_incidents.jsonl").exists()
    assert compute_integrity_pressure(tmp_path).metrics.incidents_last_24h == 0


def test_escalation_and_disable_flag(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    enforce, warn = apply_escalation(2, gate_name="receipt_chain", base_enforce=False, base_warn=False, high_severity=True)
    assert enforce is True
    assert warn is True

    monkeypatch.setenv("SENTIENTOS_PRESSURE_DISABLE_ESCALATION", "1")
    enforce_off, warn_off = apply_escalation(3, gate_name="receipt_chain", base_enforce=False, base_warn=False, high_severity=True)
    assert enforce_off is False
    assert warn_off is False


def test_critical_pressure_forces_quarantine_activation(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_QUARANTINE_AUTO", "0")
    train = ForgeMergeTrain(repo_root=tmp_path)
    train._record_integrity_incident(  # noqa: SLF001
        triggers=["receipt_chain_broken"],
        enforcement_mode="warn",
        severity="critical",
        context={"test": True},
        evidence_paths=["glow/forge/receipts/receipts_index.jsonl"],
        pressure_level=3,
    )

    quarantine = json.loads((tmp_path / "glow/forge/quarantine.json").read_text(encoding="utf-8"))
    assert quarantine["active"] is True


@pytest.mark.parametrize(("body", "expected_code"), [
    (b'{"created_at":"2026-01-01T00:00:00Z","created_at":"2026-01-01T00:00:00Z"}\n',
     "incident_feed_row_invalid"),
    (b'{"created_at":"2026-01-01T00:00:00Z","triggers":[NaN]}\n',
     "incident_feed_row_invalid"),
    (b'[]\n', "incident_feed_row_not_object"),
    (b'{"created_at":"2026-01-01T00:00:00Z"', "incident_feed_row_invalid"),
    (b'{"created_at":"not-a-time"}\n', "incident_feed_event_time_invalid"),
    (b'{"created_at":"2026-01-01T00:00:00Z","quarantine_activated":"false"}\n',
     "incident_feed_quarantine_flag_invalid"),
    (b'{"created_at":"2026-01-01T00:00:00Z","triggers":"receipt_chain_broken"}\n',
     "incident_feed_triggers_invalid"),
])
def test_invalid_incident_feed_rows_block_pressure_calculation(
    tmp_path: Path, body: bytes, expected_code: str,
) -> None:
    target = tmp_path / "pulse/integrity_incidents.jsonl"
    target.parent.mkdir(parents=True)
    target.write_bytes(body)

    with pytest.raises(IntegrityPressureInputError) as raised:
        compute_integrity_pressure(tmp_path)
    assert raised.value.code == expected_code


def test_incident_feed_bounds_block_pressure_calculation(tmp_path: Path) -> None:
    target = tmp_path / "pulse/integrity_incidents.jsonl"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"{}\n" * (MAX_INCIDENT_ROWS + 1))
    with pytest.raises(IntegrityPressureInputError, match="incident_feed_row_limit_exceeded"):
        compute_integrity_pressure(tmp_path)

    target.write_bytes(b"{}" + b" " * MAX_INCIDENT_ROW_BYTES + b"\n")
    with pytest.raises(IntegrityPressureInputError, match="incident_feed_row_size_limit_exceeded"):
        compute_integrity_pressure(tmp_path)

    target.write_text(json.dumps({"created_at": "2026-01-01T00:00:00Z",
        "triggers": ["bounded-trigger"] * 513}) + "\n",
        encoding="utf-8")
    with pytest.raises(IntegrityPressureInputError, match="incident_feed_trigger_limit_exceeded"):
        compute_integrity_pressure(tmp_path)

    target.write_bytes(b" " * MAX_INCIDENT_FEED_BYTES + b"\n")
    with pytest.raises(IntegrityPressureInputError, match="incident_feed_size_or_custody_invalid"):
        compute_integrity_pressure(tmp_path)


def test_incident_feed_symlink_is_not_followed(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX symlink custody fixture")
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    target = tmp_path / "pulse/integrity_incidents.jsonl"
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)

    with pytest.raises(IntegrityPressureInputError, match="incident_feed_custody_unavailable"):
        compute_integrity_pressure(tmp_path)


@pytest.mark.no_legacy_skip
def test_incident_artifact_identity_collision_preserves_prior_bytes(tmp_path: Path) -> None:
    first = Incident(
        schema_version=1, incident_id="stable-incident-id",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["first-trigger"], enforcement_mode="warn", context={"source": "first"},
        evidence_paths=[], suggested_actions=[],
    )
    path = write_incident(tmp_path, first)
    original = path.read_bytes()
    # Exercise the artifact owner's collision path independently of feed
    # identity deduplication: simulate a missing feed with retained artifact.
    (tmp_path / "pulse/integrity_incidents.jsonl").unlink()
    second = Incident(
        schema_version=1, incident_id="stable-incident-id",
        created_at="2026-10-12T00:00:00Z", severity="critical",
        triggers=["second-trigger"], enforcement_mode="enforce", context={"source": "second"},
        evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentArtifactError) as raised:
        write_incident(tmp_path, second)
    assert raised.value.code == "incident_artifact_publication_incident_artifact_identity_conflict"
    assert path.read_bytes() == original
    assert not (tmp_path / "pulse/integrity_incidents.jsonl").exists()


@pytest.mark.no_legacy_skip
def test_incident_artifact_size_limit_fails_before_any_publication(tmp_path: Path) -> None:
    incident = Incident(
        schema_version=1, incident_id="oversized-artifact",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["bounded-trigger"], enforcement_mode="warn",
        context={"large": "x" * MAX_INCIDENT_ARTIFACT_BYTES},
        evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentArtifactError) as raised:
        write_incident(tmp_path, incident)
    assert raised.value.code == "incident_artifact_size_limit_exceeded"
    assert not list((tmp_path / INCIDENTS_DIR).glob("incident_*.json"))
    assert not (tmp_path / "pulse/integrity_incidents.jsonl").exists()


@pytest.mark.no_legacy_skip
def test_incident_artifact_directory_symlink_is_rejected_before_feed_publication(
    tmp_path: Path,
) -> None:
    if os.name != "posix":
        pytest.skip("descriptor-relative artifact publisher is POSIX-only")
    (tmp_path / "glow/forge").mkdir(parents=True)
    outside = tmp_path / "outside-incidents"
    outside.mkdir()
    (tmp_path / INCIDENTS_DIR).symlink_to(outside, target_is_directory=True)
    incident = Incident(
        schema_version=1, incident_id="symlinked-artifact-directory",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["bounded-trigger"], enforcement_mode="warn", context={},
        evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentArtifactError) as raised:
        write_incident(tmp_path, incident)
    assert raised.value.code.startswith("incident_artifact_publication_directory_")
    assert not list(outside.glob("incident_*.json"))
    assert not (tmp_path / "pulse/integrity_incidents.jsonl").exists()


@pytest.mark.no_legacy_skip
def test_incident_feed_exact_retry_is_idempotent_and_conflict_preserves_bytes(tmp_path: Path) -> None:
    first = Incident(
        schema_version=1, incident_id="feed-retry-id",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["receipt_chain_warning"], enforcement_mode="warn", context={},
        evidence_paths=[], suggested_actions=[],
    )
    path = tmp_path / "glow/forge/incidents/incident.json"
    path = write_incident(tmp_path, first)
    feed = tmp_path / "pulse/integrity_incidents.jsonl"
    original = feed.read_bytes()
    append_incident_feed(tmp_path, first, path)
    assert feed.read_bytes() == original
    second = Incident(
        schema_version=1, incident_id=first.incident_id,
        created_at=first.created_at, severity="critical",
        triggers=["different_trigger"], enforcement_mode="enforce", context={},
        evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentFeedRecordError) as raised:
        append_incident_feed(tmp_path, second, path)
    assert raised.value.code == "incident_feed_identity_conflict"
    assert feed.read_bytes() == original
    assert len(parse_bounded_incident_feed(original)) == 1


@pytest.mark.no_legacy_skip
def test_incident_feed_rejects_missing_or_substituted_artifact(tmp_path: Path) -> None:
    incident = Incident(
        schema_version=1, incident_id="artifact-reference-id",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["receipt_chain_warning"], enforcement_mode="warn", context={"source": "original"},
        evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentFeedRecordError) as missing:
        append_incident_feed(tmp_path, incident, tmp_path / "missing.json")
    assert missing.value.code == "incident_feed_artifact_path_mismatch"
    assert not (tmp_path / "pulse/integrity_incidents.jsonl").exists()

    path = write_incident(tmp_path, incident)
    (tmp_path / "pulse/integrity_incidents.jsonl").unlink()
    substituted = Incident(
        schema_version=1, incident_id=incident.incident_id,
        created_at=incident.created_at, severity=incident.severity,
        triggers=incident.triggers, enforcement_mode=incident.enforcement_mode,
        context={"source": "substituted"}, evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentArtifactError) as mismatch:
        append_incident_feed(tmp_path, substituted, path)
    assert mismatch.value.code == "incident_artifact_identity_conflict"
    assert not (tmp_path / "pulse/integrity_incidents.jsonl").exists()


@pytest.mark.no_legacy_skip
def test_malformed_existing_incident_feed_blocks_artifact_and_feed_publication(tmp_path: Path) -> None:
    feed = tmp_path / "pulse/integrity_incidents.jsonl"
    feed.parent.mkdir()
    original = b'{"created_at":"not-a-time"}\n'
    feed.write_bytes(original)
    incident = Incident(
        schema_version=1, incident_id="malformed-feed-block", created_at="2026-10-12T00:00:00Z",
        severity="warning", triggers=["bounded-trigger"], enforcement_mode="warn", context={},
        evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentFeedRecordError) as raised:
        write_incident(tmp_path, incident)
    assert raised.value.code.startswith("incident_feed_existing_invalid_")
    assert feed.read_bytes() == original
    assert not list((tmp_path / INCIDENTS_DIR).glob("incident_*.json"))


@pytest.mark.no_legacy_skip
def test_incident_feed_row_capacity_rejects_before_artifact_publication(tmp_path: Path) -> None:
    feed = tmp_path / "pulse/integrity_incidents.jsonl"
    rows = [{"incident_id": f"old-{index}", "created_at": "2026-10-12T00:00:00Z"}
            for index in range(MAX_INCIDENT_ROWS)]
    _write_incidents(feed, rows)
    original = feed.read_bytes()
    incident = Incident(
        schema_version=1, incident_id="would-exceed-row-limit", created_at="2026-10-12T00:00:00Z",
        severity="warning", triggers=["bounded-trigger"], enforcement_mode="warn", context={},
        evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentFeedRecordError) as raised:
        write_incident(tmp_path, incident)
    assert raised.value.code == "incident_feed_row_capacity_exhausted"
    assert feed.read_bytes() == original
    assert not list((tmp_path / INCIDENTS_DIR).glob("incident_*.json"))


@pytest.mark.no_legacy_skip
def test_incident_feed_byte_capacity_rejects_before_artifact_publication(tmp_path: Path) -> None:
    feed = tmp_path / "pulse/integrity_incidents.jsonl"
    feed.parent.mkdir()
    prefix = b'{"created_at":"2026-10-12T00:00:00Z","pad":"'
    suffix = b'"}'
    row = prefix + b"x" * (65_535 - len(prefix) - len(suffix)) + suffix + b"\n"
    original = row * 16
    assert len(original) == MAX_INCIDENT_FEED_BYTES
    feed.write_bytes(original)
    incident = Incident(
        schema_version=1, incident_id="would-exceed-byte-limit", created_at="2026-10-12T00:00:00Z",
        severity="warning", triggers=["bounded-trigger"], enforcement_mode="warn", context={},
        evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentFeedRecordError) as raised:
        write_incident(tmp_path, incident)
    assert raised.value.code == "incident_feed_capacity_exhausted"
    assert feed.read_bytes() == original
    assert not list((tmp_path / INCIDENTS_DIR).glob("incident_*.json"))


@pytest.mark.no_legacy_skip
def test_incident_feed_symlink_and_lock_symlink_are_rejected(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("descriptor-relative incident feed publisher is POSIX-only")
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"")
    pulse = tmp_path / "pulse"
    pulse.mkdir()
    (pulse / "integrity_incidents.jsonl").symlink_to(outside)
    incident = Incident(
        schema_version=1, incident_id="feed-symlink-id", created_at="2026-10-12T00:00:00Z",
        severity="warning", triggers=["bounded-trigger"], enforcement_mode="warn", context={},
        evidence_paths=[], suggested_actions=[],
    )
    with pytest.raises(IntegrityIncidentFeedRecordError):
        write_incident(tmp_path, incident)
    assert outside.read_bytes() == b""

    (pulse / "integrity_incidents.jsonl").unlink()
    (pulse / ".integrity-incidents.lock").unlink()
    (pulse / ".integrity-incidents.lock").symlink_to(outside)
    with pytest.raises(IntegrityIncidentFeedRecordError) as raised:
        write_incident(tmp_path, incident)
    assert raised.value.code == "incident_feed_lock_unavailable"
    assert outside.read_bytes() == b""


@pytest.mark.no_legacy_skip
def test_concurrent_incident_feed_publishers_preserve_both_rows(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("interprocess flock is POSIX-only")
    def publish(index: int) -> None:
        incident = Incident(
            schema_version=1, incident_id=f"concurrent-{index}",
            created_at="2026-10-12T00:00:00Z", severity="warning",
            triggers=[f"trigger-{index}"], enforcement_mode="warn", context={},
            evidence_paths=[], suggested_actions=[],
        )
        write_incident(tmp_path, incident)
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(publish, (1, 2)))
    rows = parse_bounded_incident_feed((tmp_path / "pulse/integrity_incidents.jsonl").read_bytes())
    assert {row["incident_id"] for row in rows} == {"concurrent-1", "concurrent-2"}


@pytest.mark.no_legacy_skip
def test_restart_custody_inspection_reconciles_exact_artifact_and_feed(tmp_path: Path) -> None:
    incident = Incident(
        schema_version=1, incident_id="activation-lineage-id",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["verified_integrity_mismatch"], enforcement_mode="enforce",
        context={"source": "integrity_controller"}, evidence_paths=[], suggested_actions=[],
    )
    write_incident(tmp_path, incident, quarantine_activated=True)

    custody = inspect_quarantine_incident_custody(
        tmp_path, incident_id=incident.incident_id, activated_at=incident.created_at,
    )

    assert custody["status"] == "complete_local_custody"
    assert custody["artifact_status"] == "valid"
    assert custody["feed_status"] == "present_unverified"
    assert custody["catalog_status"] == "present_unverified"
    assert custody["catalog_duplicate_count"] == 0
    assert custody["catalog_row_is_authenticated"] is False
    assert custody["feed_is_authenticated"] is False
    assert custody["attack_established"] is False
    assert isinstance(custody["artifact_sha256"], str)
    assert isinstance(custody["feed_row_sha256"], str)
    assert isinstance(custody["catalog_entry_sha256"], str)


@pytest.mark.no_legacy_skip
def test_restart_custody_inspection_marks_missing_catalog_as_incomplete(tmp_path: Path) -> None:
    incident = Incident(
        schema_version=1, incident_id="activation-without-catalog",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["verified_integrity_mismatch"], enforcement_mode="enforce",
        context={}, evidence_paths=[], suggested_actions=[],
    )
    write_incident(tmp_path, incident, quarantine_activated=True)
    (tmp_path / "pulse/artifact_catalog.jsonl").unlink()
    custody = inspect_quarantine_incident_custody(
        tmp_path, incident_id=incident.incident_id, activated_at=incident.created_at,
    )
    assert custody["status"] == "incomplete"
    assert custody["artifact_status"] == "valid"
    assert custody["feed_status"] == "present_unverified"
    assert custody["catalog_status"] == "missing"


@pytest.mark.no_legacy_skip
def test_restart_custody_surfaces_conflicting_catalog_reference(tmp_path: Path) -> None:
    incident = Incident(
        schema_version=1, incident_id="activation-conflicting-catalog",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["verified_integrity_mismatch"], enforcement_mode="enforce",
        context={}, evidence_paths=[], suggested_actions=[],
    )
    write_incident(tmp_path, incident, quarantine_activated=True)
    catalog = tmp_path / "pulse/artifact_catalog.jsonl"
    rows = [json.loads(line) for line in catalog.read_text(encoding="utf-8").splitlines()]
    row = next(item for item in rows if item.get("id") == incident.incident_id)
    row["path"] = "glow/forge/incidents/substituted.json"
    catalog.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in rows), encoding="utf-8")
    custody = inspect_quarantine_incident_custody(
        tmp_path, incident_id=incident.incident_id, activated_at=incident.created_at,
    )
    assert custody["status"] == "conflict"
    assert custody["catalog_status"] == "conflict"
    assert custody["attack_established"] is False


@pytest.mark.no_legacy_skip
def test_restart_custody_tolerates_identical_catalog_retry_rows(tmp_path: Path) -> None:
    incident = Incident(
        schema_version=1, incident_id="activation-identical-catalog-retry",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["verified_integrity_mismatch"], enforcement_mode="enforce",
        context={}, evidence_paths=[], suggested_actions=[],
    )
    write_incident(tmp_path, incident, quarantine_activated=True)
    write_incident(tmp_path, incident, quarantine_activated=True)
    custody = inspect_quarantine_incident_custody(
        tmp_path, incident_id=incident.incident_id, activated_at=incident.created_at,
    )
    assert custody["status"] == "complete_local_custody"
    assert custody["catalog_status"] == "present_unverified"
    assert custody["catalog_duplicate_count"] == 1


@pytest.mark.no_legacy_skip
def test_restart_custody_inspection_reports_missing_records_without_repair(tmp_path: Path) -> None:
    custody = inspect_quarantine_incident_custody(
        tmp_path, incident_id="activation-without-artifact", activated_at="2026-10-12T00:00:00Z",
    )

    assert custody["status"] == "incomplete"
    assert custody["artifact_status"] == "missing"
    assert custody["feed_status"] == "missing"
    assert not (tmp_path / INCIDENTS_DIR).exists()
    assert not (tmp_path / "pulse/integrity_incidents.jsonl").exists()


@pytest.mark.no_legacy_skip
def test_restart_custody_inspection_surfaces_feed_conflict_without_trusting_it(tmp_path: Path) -> None:
    incident = Incident(
        schema_version=1, incident_id="activation-conflict-id",
        created_at="2026-10-12T00:00:00Z", severity="warning",
        triggers=["verified_integrity_mismatch"], enforcement_mode="enforce",
        context={}, evidence_paths=[], suggested_actions=[],
    )
    write_incident(tmp_path, incident, quarantine_activated=True)
    feed = tmp_path / "pulse/integrity_incidents.jsonl"
    row = parse_bounded_incident_feed(feed.read_bytes())[0]
    row["triggers"] = ["substituted_trigger"]
    feed.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    custody = inspect_quarantine_incident_custody(
        tmp_path, incident_id=incident.incident_id, activated_at=incident.created_at,
    )

    assert custody["status"] == "conflict"
    assert custody["artifact_status"] == "valid"
    assert custody["feed_status"] == "conflict"
    assert custody["feed_is_authenticated"] is False
