from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentientos.windows_handle_custody import (
    WindowsHandleCustodyError,
    observe_private_directory_identity,
    read_explicit_file,
    read_regular_files,
)
from sentientos import windows_handle_custody as windows_custody_module
from sentientos import windows_peer_replay_custody as publication_module
from sentientos.federation.peer_authentication import FederationPeerEventVerificationError
from sentientos.work_plan import (
    WORK_PLAN_EVIDENCE_DIR,
    WorkPlanError,
    _open_work_plan_evidence_directory,
)
from sentientos.federation import peer_replay_owner as replay_module
from sentientos.federation.peer_authentication_ed25519 import (
    CryptographyEd25519FederationPeerSignatureVerifier,
)
from sentientos.federation.peer_health_source_factory import (
    FederationPeerHealthSourceFactoryError,
    load_operator_pinned_peer_health_sources,
)
from sentientos.federation.peer_trust_catalog import ReadOnlyFederationPeerTrustCatalog
from tests.test_federation_peer_authentication import NOW, _make_catalog, _signed_event


pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("name", [
    "receipt.json:claim", "receipt.json::$DATA", "C:receipt.json", "a/b.json",
    "a\\b.json", "receipt.json\x00", "receipt\n.json", "receipt?.json",
    "receipt*.json", 'receipt".json', "receipt<.json", "receipt>.json",
    "receipt|.json", "receipt.json.", "receipt.json ", ".", "..", "",
    "a" * 256, "\ud800.json",
])
def test_reader_rejects_nonliteral_selected_names_before_open(
    tmp_path: Path, name: str,
) -> None:
    with pytest.raises(WindowsHandleCustodyError, match="windows_custody_read_limits_invalid"):
        read_regular_files(tmp_path / "absent", max_entries=1,
            max_file_bytes=64, max_total_bytes=64, selected_names=(name,))
    assert not (tmp_path / "absent").exists()


def test_reader_rejects_case_alias_selection_before_open(tmp_path: Path) -> None:
    with pytest.raises(WindowsHandleCustodyError, match="windows_custody_read_limits_invalid"):
        read_regular_files(tmp_path, max_entries=2, max_file_bytes=64,
            max_total_bytes=128, selected_names=("receipt.json", "RECEIPT.JSON"))


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows alternate data streams")
def test_windows_reader_rejects_existing_alternate_data_stream(tmp_path: Path) -> None:
    source = tmp_path / "receipt.json"
    stream = tmp_path / "receipt.json:claim"
    source.write_bytes(b'{"status":"rejected"}')
    stream.write_bytes(b'{"status":"verified"}')
    assert stream.read_bytes() == b'{"status":"verified"}'

    with pytest.raises(WindowsHandleCustodyError, match="windows_custody_read_limits_invalid"):
        read_explicit_file(stream, max_bytes=64)
    assert read_explicit_file(source, max_bytes=64) == b'{"status":"rejected"}'
    assert stream.read_bytes() == b'{"status":"verified"}'


def _make_current_user_private(path: Path, *, directory: bool) -> None:
    if os.name != "nt":
        raise RuntimeError("private_windows_acl_fixture_requires_windows")
    identity = subprocess.check_output(
        ["whoami", "/user", "/fo", "csv", "/nh"], text=True,
    )
    user_sid = next(csv.reader([identity]))[1]
    inheritance = "(OI)(CI)(F)" if directory else "(F)"
    grants = [
        f"*{user_sid}:{inheritance}",
        f"*S-1-5-18:{inheritance}",
        f"*S-1-5-32-544:{inheritance}",
    ]
    subprocess.run(
        ["icacls", str(path), "/grant:r", *grants],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["icacls", str(path), "/inheritance:r"],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["icacls", str(path), "/setowner", f"*{user_sid}"],
        check=True, capture_output=True, text=True,
    )


def _windows_root_identity(path: Path) -> tuple[int, bytes]:
    return observe_private_directory_identity(path)


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows filesystem identity")
def test_windows_private_root_identity_is_observed_without_mutation(tmp_path: Path) -> None:
    missing = tmp_path / "missing-root"
    with pytest.raises(WindowsHandleCustodyError):
        observe_private_directory_identity(missing)
    assert not missing.exists()

    _make_current_user_private(tmp_path, directory=True)
    identity = observe_private_directory_identity(tmp_path)
    assert type(identity[0]) is int and 0 <= identity[0] <= 2**64 - 1
    assert type(identity[1]) is bytes and len(identity[1]) == 16
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows root identity enforcement")
def test_windows_reader_rejects_changed_operator_pinned_root(tmp_path: Path) -> None:
    _make_current_user_private(tmp_path, directory=True)
    expected = _windows_root_identity(tmp_path)
    wrong = (expected[0], bytes([expected[1][0] ^ 1]) + expected[1][1:])
    with pytest.raises(WindowsHandleCustodyError, match="windows_custody_root_identity_mismatch"):
        read_regular_files(tmp_path, max_entries=1, max_file_bytes=64,
            max_total_bytes=64, selected_names=(), require_private_acl=True,
            expected_root_identity=wrong)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows immutable publication")
def test_windows_replay_publication_rejects_changed_operator_pinned_root(tmp_path: Path) -> None:
    _make_current_user_private(tmp_path, directory=True)
    expected = _windows_root_identity(tmp_path)
    wrong = (expected[0], bytes([expected[1][0] ^ 1]) + expected[1][1:])
    with pytest.raises(publication_module.WindowsReplayCustodyError,
                       match="windows_replay_root_identity_mismatch"):
        publication_module.publish_immutable_replay_bytes(
            tmp_path / replay_module._record_name(1), b"record-one",
            max_bytes=64, max_entries=8, expected_root_identity=wrong)
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(publication_module.WindowsReplayCustodyError,
                       match="windows_replay_root_identity_required"):
        publication_module.publish_immutable_replay_bytes(
            tmp_path / replay_module._record_name(1), b"record-one",
            max_bytes=64, max_entries=8)


def test_explicit_file_reader_returns_bounded_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_bytes(b'{"status":"verified"}\n')

    assert read_explicit_file(path, max_bytes=64) == path.read_bytes()
    with pytest.raises(WindowsHandleCustodyError):
        read_explicit_file(path, max_bytes=8)


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows handle APIs")
def test_windows_reader_returns_selected_files_in_deterministic_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "b.json").write_bytes(b'{"id":"b"}')
    (tmp_path / "ignored.txt").write_bytes(b"not selected")
    (tmp_path / "a.json").write_bytes(b'{"id":"a"}')

    assert read_regular_files(
        tmp_path,
        max_entries=3,
        max_file_bytes=32,
        max_total_bytes=64,
        selected_names=("b.json", "a.json"),
    ) == [("a.json", b'{"id":"a"}'), ("b.json", b'{"id":"b"}')]


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows handle APIs")
def test_windows_reader_rejects_hard_linked_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    alias = tmp_path / "alias.json"
    source.write_bytes(b'{"id":"shared"}')
    os.link(source, alias)

    with pytest.raises(
        WindowsHandleCustodyError,
        match="cognition_observation_windows_file_alias_rejected",
    ):
        read_regular_files(
            tmp_path,
            max_entries=1,
            max_file_bytes=32,
            max_total_bytes=32,
            selected_names=("alias.json",),
        )


@pytest.mark.skipif(os.name != "nt", reason="requires Windows path semantics")
def test_work_plan_evidence_storage_fails_closed_without_dirfd(tmp_path: Path) -> None:
    evidence_dir = tmp_path / WORK_PLAN_EVIDENCE_DIR
    evidence_dir.mkdir(parents=True)

    with pytest.raises(
        WorkPlanError,
        match="work_plan_evidence_descriptor_relative_required",
    ):
        _open_work_plan_evidence_directory(tmp_path, create=True)

    assert evidence_dir.is_dir()
    assert list(evidence_dir.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="requires Windows handle ACL inspection")
def test_windows_reader_verifies_private_acl_on_open_handle(tmp_path: Path) -> None:
    _make_current_user_private(tmp_path, directory=True)
    path = tmp_path / "private.json"
    path.write_bytes(b'{"private":true}')
    _make_current_user_private(path, directory=False)

    assert read_explicit_file(path, max_bytes=32, require_private_acl=True) == path.read_bytes()


@pytest.mark.parametrize("grant_target", ["directory", "file"])
@pytest.mark.skipif(os.name != "nt", reason="requires Windows handle ACL inspection")
def test_private_acl_rejects_broad_write_grants(
    tmp_path: Path, grant_target: str,
) -> None:
    _make_current_user_private(tmp_path, directory=True)
    path = tmp_path / "private.json"
    path.write_bytes(b'{"pinned":true}')
    _make_current_user_private(path, directory=False)
    target = tmp_path if grant_target == "directory" else path
    subprocess.run(
        ["icacls", str(target), "/grant:r", "*S-1-1-0:(W)"],
        check=True, capture_output=True, text=True,
    )

    with pytest.raises(WindowsHandleCustodyError, match="private_acl_broad_write_grant"):
        read_explicit_file(path, max_bytes=64, require_private_acl=True)


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows sharing contracts")
def test_windows_reader_retains_earlier_handles_until_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_current_user_private(tmp_path, directory=True)
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    for path in (first, second):
        _make_current_user_private(path, directory=False)
    real_check = windows_custody_module.verify_private_handle_acl
    checks = 0

    def check_and_attempt_mutation(handle: int) -> None:
        nonlocal checks
        real_check(handle)
        checks += 1
        if checks == 3:  # root, first file, then second file
            with pytest.raises(PermissionError):
                first.write_bytes(b"replacement")
            with pytest.raises(PermissionError):
                first.unlink()

    monkeypatch.setattr(windows_custody_module, "verify_private_handle_acl", check_and_attempt_mutation)
    assert read_regular_files(tmp_path, max_entries=2, max_file_bytes=64,
        max_total_bytes=128, selected_names=("a.json", "b.json"),
        require_private_acl=True) == [("a.json", b"first"), ("b.json", b"second")]
    assert checks >= 3
    first.write_bytes(b"released")
    first.unlink()


@pytest.mark.parametrize("grant_target", ["directory", "earlier_file"])
@pytest.mark.skipif(os.name != "nt", reason="requires native Windows terminal ACL inspection")
def test_windows_reader_rechecks_acl_before_releasing_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grant_target: str,
) -> None:
    _make_current_user_private(tmp_path, directory=True)
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    for path in (first, second):
        _make_current_user_private(path, directory=False)
    real_check = windows_custody_module.verify_private_handle_acl
    checks = 0

    def check_and_change_acl(handle: int) -> None:
        nonlocal checks
        real_check(handle)
        checks += 1
        if checks == 3:
            target = tmp_path if grant_target == "directory" else first
            subprocess.run(["icacls", str(target), "/grant:r", "*S-1-1-0:(W)"],
                check=True, capture_output=True, text=True, timeout=20)

    monkeypatch.setattr(windows_custody_module, "verify_private_handle_acl", check_and_change_acl)
    with pytest.raises(WindowsHandleCustodyError, match="private_acl_broad_write_grant"):
        read_regular_files(tmp_path, max_entries=2, max_file_bytes=64,
            max_total_bytes=128, selected_names=("a.json", "b.json"), require_private_acl=True)
    assert checks >= 3
    first.write_bytes(b"released after rejection")
    second.unlink()


def _provision_private_replay_history(
    root: Path,
) -> tuple[Ed25519PrivateKey, str, ReadOnlyFederationPeerTrustCatalog]:
    """Explicit test provisioning; the runtime reader never writes these records."""
    root.mkdir()
    _make_current_user_private(root, directory=True)
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    previous_digest = None
    for sequence, outcome in enumerate(("adverse", "positive"), start=1):
        raw, envelope = _signed_event(private, key_id, sequence=sequence,
            event={"kind": "trial_outcome", "outcome": outcome})
        body = {
            "schema": replay_module.REPLAY_RECORD_SCHEMA,
            "peer_id": "peer-one", "sequence": sequence,
            "previous_digest": previous_digest, "recorded_at": "2026-10-23T10:00:00Z",
            "signed_envelope": raw.decode(), "signing_key_id": key_id,
            "event_digest": envelope["event_digest"],
            "catalog_version": catalog.catalog_version, "catalog_digest": catalog.catalog_digest,
        }
        previous_digest = replay_module._record_digest(body)
        path = root / replay_module._record_name(sequence)
        path.write_bytes(replay_module._canonical({**body, "record_digest": previous_digest}))
        _make_current_user_private(path, directory=False)
    return private, key_id, catalog


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows replay custody")
def test_windows_replay_recovers_signed_history_without_mutation(tmp_path: Path) -> None:
    root = tmp_path / "peer-one"
    _, _, catalog = _provision_private_replay_history(root)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    owner = replay_module.FederationPeerReplayOwner(
        root, peer_id="peer-one", expected_root_identity=_windows_root_identity(root))
    verifier = CryptographyEd25519FederationPeerSignatureVerifier()

    history = owner.verified_history(catalog=catalog, signature_verifier=verifier)
    assert owner.last_accepted_sequence == 2
    assert [entry.verified_event.event["outcome"] for entry in history] == ["adverse", "positive"]
    assert all(entry.created is False for entry in history)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows replay custody")
def test_windows_replay_rejects_recomputed_signature_tamper(tmp_path: Path) -> None:
    root = tmp_path / "peer-one"
    _, _, catalog = _provision_private_replay_history(root)
    path = root / replay_module._record_name(2)
    record = json.loads(path.read_bytes())
    envelope = json.loads(record["signed_envelope"])
    signature = envelope["signature"]
    envelope["signature"] = ("A" if signature[0] != "A" else "B") + signature[1:]
    record["signed_envelope"] = replay_module._canonical(envelope).decode()
    record["record_digest"] = replay_module._record_digest({
        key: value for key, value in record.items() if key != "record_digest"})
    path.write_bytes(replay_module._canonical(record))
    before = path.read_bytes()
    owner = replay_module.FederationPeerReplayOwner(
        root, peer_id="peer-one", expected_root_identity=_windows_root_identity(root))
    assert owner.last_accepted_sequence == 2  # hash-chain integrity is not signature proof
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_history_event_verification_failed"):
        owner.verified_history(catalog=catalog,
            signature_verifier=CryptographyEd25519FederationPeerSignatureVerifier())
    assert path.read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows replay custody")
def test_windows_replay_requires_existing_private_bounded_history(tmp_path: Path) -> None:
    root = tmp_path / "peer-one"
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_owner_root_identity_required"):
        replay_module.FederationPeerReplayOwner(root, peer_id="peer-one")
    with pytest.raises(WindowsHandleCustodyError):
        observe_private_directory_identity(root)
    assert not root.exists()
    root.mkdir()
    _make_current_user_private(root, directory=True)
    identity = _windows_root_identity(root)
    owner = replay_module.FederationPeerReplayOwner(
        root, peer_id="peer-one", expected_root_identity=identity)
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_owner_custody_unavailable"):
        _ = owner.last_accepted_sequence
    assert root.exists()
    assert owner.last_accepted_sequence == 0
    root.rmdir()
    _provision_private_replay_history(root)
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_owner_custody_unavailable"):
        _ = owner.last_accepted_sequence
    bounded = replay_module.FederationPeerReplayOwner(
        root, peer_id="peer-one", max_records=1,
        expected_root_identity=_windows_root_identity(root))
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_owner_record_limit_exceeded"):
        _ = bounded.last_accepted_sequence
    subprocess.run(["icacls", str(root), "/grant:r", "*S-1-1-0:(W)"],
                   check=True, capture_output=True, text=True)
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_owner_custody_unavailable"):
        _ = owner.last_accepted_sequence
    with pytest.raises(FederationPeerHealthSourceFactoryError,
                       match="peer_replay_owner_custody_unsupported"):
        load_operator_pinned_peer_health_sources(tmp_path / "absent-pin.json",
            runtime_root=tmp_path, configured_peer_ids=("peer-one",))
    assert not (tmp_path / "absent-pin.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows operator pin custody")
def test_windows_factory_binds_operator_pin_to_existing_replay_root(tmp_path: Path) -> None:
    from tests.test_federation_peer_health_source_factory import _write_pinned_peer

    pin_path, runtime_root, _ = _write_pinned_peer(
        tmp_path, windows_identity=(0, bytes(16)))
    for directory in (
        runtime_root,
        runtime_root / "federation",
        runtime_root / "federation" / "peer_trust_catalogs",
    ):
        _make_current_user_private(directory, directory=True)
    catalog_path = runtime_root / "federation" / "peer_trust_catalogs" / "peer-one.json"
    _make_current_user_private(catalog_path, directory=False)

    replay_root = runtime_root / "federation" / "peer_health_replay" / "peer-one"
    replay_root.mkdir(parents=True)
    _make_current_user_private(runtime_root / "federation" / "peer_health_replay", directory=True)
    _make_current_user_private(replay_root, directory=True)
    identity = _windows_root_identity(replay_root)
    pin = json.loads(pin_path.read_text())
    pin["peers"][0]["root_identity"] = {
        "volume_serial_number": identity[0], "file_id": identity[1].hex(),
    }
    pin_path.write_text(json.dumps(pin, sort_keys=True, separators=(",", ":")) + "\n")
    _make_current_user_private(pin_path, directory=False)

    sources = load_operator_pinned_peer_health_sources(
        pin_path, runtime_root=runtime_root, configured_peer_ids={"peer-one"})
    owner = sources["peer-one"].owner
    assert owner.expected_root_identity == identity
    assert owner.last_accepted_sequence == 0

    replay_root.rename(replay_root.with_name("peer-one-old"))
    replay_root.mkdir()
    _make_current_user_private(replay_root, directory=True)
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_owner_custody_unavailable"):
        _ = owner.last_accepted_sequence
    assert list(replay_root.iterdir()) == []


def _publish_test_record(root: Path, data: bytes = b"record-one", *, max_entries: int = 8) -> bool:
    expected = _windows_root_identity(root) if os.name == "nt" and root.exists() else None
    return publication_module.publish_immutable_replay_bytes(
        root / replay_module._record_name(1), data, max_bytes=140_000,
        max_entries=max_entries, expected_root_identity=expected)


@pytest.mark.skipif(os.name == "nt", reason="exercises the non-Windows refusal")
def test_windows_replay_publication_refuses_other_platforms_without_effects(tmp_path: Path) -> None:
    root = tmp_path / "not-created"
    with pytest.raises(publication_module.WindowsReplayCustodyError,
                       match="windows_replay_publication_unsupported"):
        _publish_test_record(root)
    assert not root.exists()


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows immutable publication")
def test_windows_replay_publication_create_retry_and_conflict(tmp_path: Path) -> None:
    _make_current_user_private(tmp_path, directory=True)
    assert _publish_test_record(tmp_path) is True
    target = tmp_path / replay_module._record_name(1)
    assert read_explicit_file(target, max_bytes=64, require_private_acl=True) == b"record-one"
    assert _publish_test_record(tmp_path) is False
    with pytest.raises(publication_module.WindowsReplayCustodyError, match="replay_owner_record_conflict"):
        _publish_test_record(tmp_path, b"conflicting record")
    assert target.read_bytes() == b"record-one"
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows no-replace rename")
def test_windows_replay_publication_preserves_destination_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_current_user_private(tmp_path, directory=True)
    target = tmp_path / replay_module._record_name(1)

    def create_conflict(phase: str) -> None:
        if phase == "prepared":
            target.write_bytes(b"foreign conflict")
            _make_current_user_private(target, directory=False)

    monkeypatch.setattr(publication_module, "_publication_boundary", create_conflict)
    with pytest.raises(publication_module.WindowsReplayCustodyError, match="replay_owner_record_conflict"):
        _publish_test_record(tmp_path)
    assert target.read_bytes() == b"foreign conflict"
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows held-handle sharing")
def test_windows_replay_publication_blocks_root_and_stage_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_current_user_private(tmp_path, directory=True)
    observed: list[str] = []
    moved_stage_paths: list[Path] = []

    def attempt_substitution(phase: str) -> None:
        if phase == "prepared":
            stage, = tmp_path.glob(".pending-*")
            with pytest.raises(PermissionError):
                tmp_path.rename(tmp_path.with_name(tmp_path.name + "-substituted"))
            with pytest.raises(PermissionError):
                stage.write_bytes(b"substituted bytes")
            moved_stage = tmp_path / "substituted-stage"
            try:
                stage.rename(moved_stage)
            except PermissionError:
                pass
            else:
                assert moved_stage.exists()
                moved_stage_paths.append(moved_stage)
            observed.append(phase)

    monkeypatch.setattr(publication_module, "_publication_boundary", attempt_substitution)
    assert _publish_test_record(tmp_path) is True
    assert observed == ["prepared"]
    assert (tmp_path / replay_module._record_name(1)).read_bytes() == b"record-one"
    assert not (tmp_path / "substituted-stage").exists()
    assert all(not path.exists() for path in moved_stage_paths)
    assert not list(tmp_path.glob(".pending-*"))


@pytest.mark.parametrize("phase", ["prepared", "committed"])
@pytest.mark.skipif(os.name != "nt", reason="requires native Windows abrupt process death")
def test_windows_replay_publication_crash_retry_preserves_evidence(tmp_path: Path, phase: str) -> None:
    _make_current_user_private(tmp_path, directory=True)
    script = """import json, os, sys
from pathlib import Path
from sentientos import windows_peer_replay_custody as publication
from sentientos.windows_handle_custody import observe_private_directory_identity
def boundary(phase):
    if phase == sys.argv[2]:
        os._exit(71)
publication._publication_boundary = boundary
print(json.dumps({'pid': os.getpid()}), flush=True)
publication.publish_immutable_replay_bytes(Path(sys.argv[1]) / 'event-00000000000000000001.json',
    b'record-one', max_bytes=140000, max_entries=8,
    expected_root_identity=observe_private_directory_identity(Path(sys.argv[1])))
"""
    child = subprocess.run([sys.executable, "-c", script, str(tmp_path), phase],
        capture_output=True, text=True, timeout=30)
    assert child.returncode == 71, child.stderr
    assert json.loads(child.stdout)["pid"] != os.getpid()
    stale = {p.name: p.read_bytes() for p in tmp_path.glob(".pending-*")}
    target = tmp_path / replay_module._record_name(1)
    if phase == "prepared":
        assert len(stale) == 1 and not target.exists()
        assert _publish_test_record(tmp_path) is True
    else:
        assert not stale and target.read_bytes() == b"record-one"
        assert _publish_test_record(tmp_path) is False
    assert target.read_bytes() == b"record-one"
    assert {p.name: p.read_bytes() for p in tmp_path.glob(".pending-*")} == stale


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows visible-commit recovery")
def test_windows_replay_publication_preserves_commit_after_flush_boundary_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_current_user_private(tmp_path, directory=True)

    def fail_before_directory_flush(phase: str) -> None:
        if phase == "before_directory_flush":
            raise publication_module.WindowsReplayCustodyError("injected_directory_flush_failure")

    monkeypatch.setattr(publication_module, "_publication_boundary", fail_before_directory_flush)
    with pytest.raises(publication_module.WindowsReplayCustodyError, match="injected_directory_flush_failure"):
        _publish_test_record(tmp_path)
    target = tmp_path / replay_module._record_name(1)
    assert target.read_bytes() == b"record-one"
    monkeypatch.setattr(publication_module, "_publication_boundary", lambda _phase: None)
    assert _publish_test_record(tmp_path) is False
    assert [p.name for p in tmp_path.iterdir()] == [target.name]


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows protected ancestry")
def test_windows_replay_publication_enforces_bounds_and_parent_custody(tmp_path: Path) -> None:
    _make_current_user_private(tmp_path, directory=True)
    ignored = tmp_path / "unrelated.txt"
    ignored.write_bytes(b"preserve")
    with pytest.raises(publication_module.WindowsReplayCustodyError,
                       match="windows_replay_directory_bound_exceeded"):
        _publish_test_record(tmp_path, max_entries=1)
    assert ignored.read_bytes() == b"preserve" and not list(tmp_path.glob(".pending-*"))
    parent = tmp_path / "unsafe-parent"
    parent.mkdir()
    _make_current_user_private(parent, directory=True)
    root = parent / "private-root"
    root.mkdir()
    _make_current_user_private(root, directory=True)
    subprocess.run(["icacls", str(parent), "/grant:r", "*S-1-1-0:(RX)"],
                   check=True, capture_output=True, text=True, timeout=20)
    assert _publish_test_record(root) is True
    protected = {p.name: p.read_bytes() for p in root.iterdir()}
    subprocess.run(["icacls", str(parent), "/grant:r", "*S-1-1-0:(DC)"],
                   check=True, capture_output=True, text=True, timeout=20)
    with pytest.raises(publication_module.WindowsReplayCustodyError, match="ancestor_acl_replacement_grant"):
        _publish_test_record(root)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == protected
    missing = tmp_path / "missing"
    with pytest.raises(publication_module.WindowsReplayCustodyError):
        _publish_test_record(missing)
    assert not missing.exists()


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows single-link custody")
def test_windows_replay_publication_rejects_aliased_existing_record(tmp_path: Path) -> None:
    _make_current_user_private(tmp_path, directory=True)
    assert _publish_test_record(tmp_path) is True
    target = tmp_path / replay_module._record_name(1)
    alias = tmp_path / "alias.txt"
    os.link(target, alias)
    with pytest.raises(publication_module.WindowsReplayCustodyError, match="windows_replay_file_unbounded_or_aliased"):
        _publish_test_record(tmp_path)
    assert target.read_bytes() == alias.read_bytes() == b"record-one"


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows signed replay publication")
def test_windows_replay_owner_publishes_and_reverifies_signed_outcomes(tmp_path: Path) -> None:
    _make_current_user_private(tmp_path, directory=True)
    private, _, key_id, _, _, catalog, _ = _make_catalog()
    verifier = CryptographyEd25519FederationPeerSignatureVerifier()
    identity = _windows_root_identity(tmp_path)
    owner = replay_module.FederationPeerReplayOwner(
        tmp_path, peer_id="peer-one", expected_root_identity=identity)
    for sequence, outcome in enumerate(("adverse", "positive"), start=1):
        raw, _ = _signed_event(private, key_id, sequence=sequence,
            event={"kind": "trial_outcome", "outcome": outcome})
        accepted = owner.accept(raw, catalog=catalog, signature_verifier=verifier, now=NOW)
        assert accepted.created is True and accepted.sequence == sequence
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    bad, _ = _signed_event(private, key_id, sequence=3,
        signature_from=Ed25519PrivateKey.from_private_bytes(bytes(reversed(range(32)))))
    with pytest.raises(FederationPeerEventVerificationError):
        owner.accept(bad, catalog=catalog, signature_verifier=verifier, now=NOW)
    recovered = replay_module.FederationPeerReplayOwner(
        tmp_path, peer_id="peer-one", expected_root_identity=_windows_root_identity(tmp_path))
    history = recovered.verified_history(catalog=catalog, signature_verifier=verifier)
    assert recovered.last_accepted_sequence == 2
    assert [record.verified_event.event["outcome"] for record in history] == ["adverse", "positive"]
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
