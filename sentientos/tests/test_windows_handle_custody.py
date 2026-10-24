from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sentientos.windows_handle_custody import (
    WindowsHandleCustodyError,
    read_explicit_file,
    read_regular_files,
)
from sentientos import windows_handle_custody as windows_custody_module
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
def test_windows_replay_recovers_signed_history_without_publication(tmp_path: Path) -> None:
    root = tmp_path / "peer-one"
    private, key_id, catalog = _provision_private_replay_history(root)
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    owner = replay_module.FederationPeerReplayOwner(root, peer_id="peer-one")
    verifier = CryptographyEd25519FederationPeerSignatureVerifier()

    history = owner.verified_history(catalog=catalog, signature_verifier=verifier)
    assert owner.last_accepted_sequence == 2
    assert [entry.verified_event.event["outcome"] for entry in history] == ["adverse", "positive"]
    assert all(entry.created is False for entry in history)
    next_raw, _ = _signed_event(private, key_id, sequence=3)
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_owner_custody_unavailable"):
        owner.accept(next_raw, catalog=catalog, signature_verifier=verifier, now=NOW)
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
    owner = replay_module.FederationPeerReplayOwner(root, peer_id="peer-one")
    assert owner.last_accepted_sequence == 2  # hash-chain integrity is not signature proof
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_history_event_verification_failed"):
        owner.verified_history(catalog=catalog,
            signature_verifier=CryptographyEd25519FederationPeerSignatureVerifier())
    assert path.read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows replay custody")
def test_windows_replay_requires_existing_private_bounded_history(tmp_path: Path) -> None:
    root = tmp_path / "peer-one"
    owner = replay_module.FederationPeerReplayOwner(root, peer_id="peer-one")
    with pytest.raises(replay_module.FederationPeerReplayOwnerError,
                       match="replay_owner_custody_unavailable"):
        _ = owner.last_accepted_sequence
    assert not root.exists()
    root.mkdir()
    _make_current_user_private(root, directory=True)
    assert owner.last_accepted_sequence == 0
    root.rmdir()
    _provision_private_replay_history(root)
    bounded = replay_module.FederationPeerReplayOwner(root, peer_id="peer-one", max_records=1)
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
