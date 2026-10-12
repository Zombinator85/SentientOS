from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import pytest

from sentientos.integrity_controller import evaluate_integrity
from sentientos.integrity_quarantine import (
    MAX_QUARANTINE_BYTES,
    QuarantineCustodyStatus,
    QuarantinePublicationUncertain,
    QuarantineState,
    QuarantineStateError,
    clear,
    load_state,
    load_state_with_status,
    save_state,
)
from sentientos.private_file_custody import PrivateFileCustodyError


def _path(root: Path) -> Path:
    return root / "glow" / "forge" / "quarantine.json"


def _write_v1(root: Path, *, active: bool, **changes: object) -> bytes:
    state = QuarantineState(active=active, **changes)
    target = _path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(state.to_dict(), sort_keys=True, indent=2) + "\n").encode()
    target.write_bytes(raw)
    return raw


def test_first_use_and_historical_v1_mode_are_distinct_and_readable(tmp_path: Path) -> None:
    first = load_state_with_status(tmp_path)
    assert first.custody_status is QuarantineCustodyStatus.FIRST_USE_ABSENT
    assert first.state.active is False

    raw = _write_v1(tmp_path, active=True, freeze_forge=True,
        allow_automerge=False, allow_publish=False, allow_federation_sync=True)
    _path(tmp_path).chmod(0o644)  # Existing v1 writer inherited ordinary umask.
    loaded = load_state_with_status(tmp_path)
    assert loaded.custody_status is QuarantineCustodyStatus.VALID_V1
    assert loaded.state.active is True
    assert loaded.state.allow_federation_sync is True
    assert _path(tmp_path).read_bytes() == raw


@pytest.mark.parametrize("payload,code", [
    (b"", "quarantine_json_invalid"),
    (b'{"schema_version":1', "quarantine_json_invalid"),
    (b"[]", "quarantine_object_required"),
    (b'{"schema_version":1,"schema_version":1}', "quarantine_duplicate_json_key"),
    (b'{"schema_version":NaN}', "quarantine_json_constant_invalid"),
    (b"\xff", "quarantine_json_invalid"),
])
def test_malformed_custody_is_not_defaulted(tmp_path: Path, payload: bytes, code: str) -> None:
    target = _path(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    with pytest.raises(QuarantineStateError) as error:
        load_state(tmp_path)
    assert error.value.code == code


@pytest.mark.parametrize("mutation,code", [
    ({"active": 1}, "quarantine_boolean_type_invalid"),
    ({"allow_publish": "false"}, "quarantine_boolean_type_invalid"),
    ({"freeze_forge": None}, "quarantine_boolean_type_invalid"),
    ({"schema_version": True}, "quarantine_schema_unsupported"),
    ({"schema_version": 2}, "quarantine_schema_unsupported"),
    ({"unknown": "value"}, "quarantine_fields_incomplete_or_unexpected"),
    ({"notes": "not-a-list"}, "quarantine_notes_invalid"),
])
def test_semantically_invalid_v1_fields_are_rejected(
    tmp_path: Path, mutation: dict[str, object], code: str,
) -> None:
    body = QuarantineState().to_dict()
    body.update(mutation)
    target = _path(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(QuarantineStateError) as error:
        load_state(tmp_path)
    assert error.value.code == code


def test_incomplete_security_fields_are_rejected(tmp_path: Path) -> None:
    body = QuarantineState().to_dict()
    del body["allow_publish"]
    target = _path(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(QuarantineStateError, match="quarantine_fields_incomplete"):
        load_state(tmp_path)


def test_oversized_wrong_type_hardlinked_and_permission_unsafe_files_fail_closed(
    tmp_path: Path,
) -> None:
    target = _path(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b" " * (MAX_QUARANTINE_BYTES + 1))
    with pytest.raises(QuarantineStateError, match="quarantine_custody_file_unbounded"):
        load_state(tmp_path)

    target.unlink()
    target.write_bytes((json.dumps(QuarantineState().to_dict()) + "\n").encode())
    target.chmod(0o200)
    with pytest.raises(QuarantineStateError, match="file_permission_denied"):
        load_state(tmp_path)

    target.chmod(0o600)
    target.chmod(0o622)
    with pytest.raises(QuarantineStateError, match="file_unbounded_or_not_private"):
        load_state(tmp_path)
    target.chmod(0o600)
    target_link = target.with_name("linked.json")
    os.link(target, target_link)
    with pytest.raises(QuarantineStateError, match="file_unbounded_or_not_private"):
        load_state(tmp_path)


def test_symlink_directory_fifo_and_substituted_root_are_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    target = _path(real_root)
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(QuarantineState().to_dict()), encoding="utf-8")
    link_root = tmp_path / "linked-root"
    link_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(QuarantineStateError):
        load_state(link_root)

    target.unlink()
    target.symlink_to(tmp_path / "absent")
    with pytest.raises(QuarantineStateError):
        load_state(real_root)
    target.unlink()
    target.mkdir()
    with pytest.raises(QuarantineStateError):
        load_state(real_root)
    target.rmdir()

    if hasattr(os, "mkfifo"):
        os.mkfifo(target)
        with pytest.raises(QuarantineStateError):
            load_state(real_root)


def test_unstable_read_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _path(tmp_path)
    original = _write_v1(tmp_path, active=False)
    target.chmod(0o600)
    import sentientos.private_file_custody as custody

    real_read = os.read
    changed = False

    def mutate_then_read(descriptor: int, count: int) -> bytes:
        nonlocal changed
        if not changed:
            changed = True
            with target.open("ab") as handle:
                handle.write(b" ")
        return real_read(descriptor, count)

    monkeypatch.setattr(custody.os, "read", mutate_then_read)
    with pytest.raises(QuarantineStateError, match="file_changed_during_read"):
        load_state(tmp_path)
    assert target.read_bytes() == original + b" "


def test_atomic_publication_and_clear_round_trip(tmp_path: Path) -> None:
    active = QuarantineState(active=True, freeze_forge=True,
        allow_automerge=False, allow_publish=False, notes=["operator-confirmed"])
    save_state(tmp_path, active)
    first_bytes = _path(tmp_path).read_bytes()
    assert stat.S_IMODE(_path(tmp_path).stat().st_mode) == 0o600
    assert load_state(tmp_path).active is True
    assert _path(tmp_path).read_bytes() == first_bytes

    cleared = clear(tmp_path, "authorized-operator-clear")
    assert cleared.active is False
    assert cleared.notes[-1].endswith("authorized-operator-clear")
    assert load_state(tmp_path).active is False


def test_acknowledgment_preserves_active_protective_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import quarantine_ack

    save_state(tmp_path, QuarantineState(active=True, freeze_forge=True,
        allow_automerge=False, allow_publish=False, notes=[]))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sentientos.event_stream.FORGE_EVENTS_PATH",
        tmp_path / "pulse" / "forge_events.jsonl")
    assert quarantine_ack.main(["--note", "operator reviewed evidence"]) == 0
    acknowledged = load_state(tmp_path)
    assert acknowledged.active is True
    assert acknowledged.freeze_forge is True
    assert acknowledged.acknowledged_at is not None
    assert acknowledged.notes[-1].startswith("ack:")
    assert load_state(tmp_path).active is True


def test_clear_cannot_repair_or_overwrite_damaged_active_evidence(tmp_path: Path) -> None:
    target = _path(tmp_path)
    target.parent.mkdir(parents=True)
    damaged = b'{"schema_version":1,"active":true'
    target.write_bytes(damaged)
    with pytest.raises(QuarantineStateError):
        clear(tmp_path, "must-not-clear-corruption")
    assert target.read_bytes() == damaged


def test_save_cannot_repair_or_overwrite_invalid_existing_evidence(tmp_path: Path) -> None:
    target = _path(tmp_path)
    target.parent.mkdir(parents=True)
    damaged = b'{"schema_version":1,"active":true'
    target.write_bytes(damaged)
    with pytest.raises(QuarantineStateError):
        save_state(tmp_path, QuarantineState(active=False, notes=[]))
    assert target.read_bytes() == damaged


def test_failed_publication_before_replace_preserves_active_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sentientos.private_file_custody as custody

    save_state(tmp_path, QuarantineState(active=True, freeze_forge=True,
        allow_automerge=False, allow_publish=False, notes=[]))
    prior = _path(tmp_path).read_bytes()

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError("injected-before-replacement")

    monkeypatch.setattr(custody.os, "replace", fail_replace)
    with pytest.raises(QuarantineStateError, match="publication_unavailable"):
        save_state(tmp_path, QuarantineState(active=False, notes=[]))
    assert _path(tmp_path).read_bytes() == prior
    assert load_state(tmp_path).active is True


def test_directory_fsync_uncertainty_is_reported_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sentientos.private_file_custody as custody

    save_state(tmp_path, QuarantineState(active=True, freeze_forge=True,
        allow_automerge=False, allow_publish=False, notes=[]))
    candidate = QuarantineState(active=False, notes=[])
    real_fsync = os.fsync
    directory_syncs = 0

    def fail_directory_sync(descriptor: int) -> None:
        nonlocal directory_syncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_syncs += 1
            if directory_syncs == 2:
                raise OSError("injected-directory-fsync-uncertain")
        real_fsync(descriptor)

    monkeypatch.setattr(custody.os, "fsync", fail_directory_sync)
    with pytest.raises(QuarantinePublicationUncertain):
        save_state(tmp_path, candidate)
    assert directory_syncs == 2
    assert _path(tmp_path).read_bytes() == (
        json.dumps(candidate.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()  # The replacement is visible; its directory durability is unknown.
    with pytest.raises(QuarantineStateError, match="publication_recovery_required"):
        load_state(tmp_path)


def test_controller_reports_unknown_custody_and_denies_all_mutation(tmp_path: Path) -> None:
    target = _path(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text("{truncated", encoding="utf-8")
    status = evaluate_integrity(tmp_path, policy_hash="test-policy")
    row = next(gate for gate in status.gate_results if gate.name == "quarantine_custody")
    assert row.status == "fail"
    assert row.reason.startswith("quarantine_custody_invalid:")
    assert status.quarantine_active is None
    assert status.quarantine_custody_status.startswith("invalid:")
    assert status.mutation_allowed is False
    assert status.publish_allowed is False
    assert status.automerge_allowed is False


def test_controller_does_not_resolve_away_a_substituted_repository_root(
    tmp_path: Path,
) -> None:
    _write_v1(tmp_path, active=False)
    substituted = tmp_path.parent / f"{tmp_path.name}-substituted"
    substituted.symlink_to(tmp_path, target_is_directory=True)
    status = evaluate_integrity(substituted, policy_hash="test-policy")
    assert status.quarantine_active is None
    assert status.mutation_allowed is False
    gate = next(item for item in status.gate_results if item.name == "quarantine_custody")
    assert gate.status == "fail"


def test_enabled_forge_is_stopped_before_effector_on_invalid_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sentientos.forge_daemon import ForgeDaemon
    from sentientos.forge_queue import ForgeQueue, ForgeRequest

    class Effector:
        calls = 0

        def run(self, *args: object, **kwargs: object) -> object:
            self.calls += 1
            raise AssertionError("Forge effector must remain unreachable")

    target = _path(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text("{truncated", encoding="utf-8")
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="blocked", goal="forge_smoke_noop",
        goal_id="forge_smoke_noop"))
    effector = Effector()
    daemon = ForgeDaemon(queue=queue, forge=effector, repo_root=tmp_path)  # type: ignore[arg-type]
    monkeypatch.setenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "1")
    monkeypatch.setattr("sentientos.event_stream.FORGE_EVENTS_PATH",
        tmp_path / "pulse" / "forge_events.jsonl")

    daemon.run_tick()

    assert effector.calls == 0
    receipt = queue.recent_receipts(limit=1)[0]
    assert receipt.status == "rejected_quarantine_custody"
    assert receipt.error == "quarantine_json_invalid"
    assert queue.pending_requests() == []
    index = json.loads((tmp_path / "glow/forge/index.json").read_text(encoding="utf-8"))
    assert index["quarantine_active"] is None
    assert index["quarantine_custody_status"] == "invalid:quarantine_json_invalid"
    assert index["quarantine_incident_custody"]["status"] == "custody_invalid"


def test_first_use_does_not_block_independently_allowed_forge_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sentientos.forge_daemon import ForgeDaemon
    from sentientos.forge_queue import ForgeQueue, ForgeRequest

    class Report:
        generated_at = "2026-01-01T00:00:00Z"
        notes: list[str] = []
        outcome = "success"
        docket_path = None
        git_sha = "fixture"
        failure_reasons: list[str] = []
        publish_remote: dict[str, object] = {}
        transaction_status = "completed"
        regression_reasons: list[str] = []
        provenance_run_id = None
        provenance_path = None

    class Forge:
        calls = 0

        def run(self, *args: object, **kwargs: object) -> Report:
            self.calls += 1
            return Report()

        def _report_path(self, generated_at: str) -> Path:
            return tmp_path / "glow" / "forge" / "report.json"

    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="positive", goal="forge_smoke_noop",
        goal_id="forge_smoke_noop"))
    forge = Forge()
    daemon = ForgeDaemon(queue=queue, forge=forge, repo_root=tmp_path)  # type: ignore[arg-type]
    monkeypatch.setenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "1")
    monkeypatch.setattr("sentientos.event_stream.FORGE_EVENTS_PATH",
        tmp_path / "pulse" / "forge_events.jsonl")

    daemon.run_tick()

    assert forge.calls == 1
    assert any(receipt.status == "success" for receipt in queue.recent_receipts(limit=2))


def test_valid_inactive_state_does_not_block_independently_allowed_forge_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sentientos.forge_daemon import ForgeDaemon
    from sentientos.forge_queue import ForgeQueue, ForgeRequest

    class Report:
        generated_at = "2026-01-01T00:00:00Z"
        notes: list[str] = []
        outcome = "success"
        docket_path = None
        git_sha = "fixture"
        failure_reasons: list[str] = []
        publish_remote: dict[str, object] = {}
        transaction_status = "completed"
        regression_reasons: list[str] = []
        provenance_run_id = None
        provenance_path = None

    class Forge:
        calls = 0

        def run(self, *args: object, **kwargs: object) -> Report:
            self.calls += 1
            return Report()

        def _report_path(self, generated_at: str) -> Path:
            return tmp_path / "glow" / "forge" / "report.json"

    save_state(tmp_path, QuarantineState(active=False, notes=[]))
    queue = ForgeQueue(pulse_root=tmp_path / "pulse")
    queue.enqueue(ForgeRequest(request_id="inactive-positive", goal="forge_smoke_noop",
        goal_id="forge_smoke_noop"))
    forge = Forge()
    daemon = ForgeDaemon(queue=queue, forge=forge, repo_root=tmp_path)  # type: ignore[arg-type]
    monkeypatch.setenv("SENTIENTOS_FORGE_DAEMON_ENABLED", "1")
    monkeypatch.setattr("sentientos.event_stream.FORGE_EVENTS_PATH",
        tmp_path / "pulse" / "forge_events.jsonl")

    daemon.run_tick()

    assert forge.calls == 1
    assert any(receipt.status == "success" for receipt in queue.recent_receipts(limit=2))

