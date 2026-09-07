from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import pytest

import sentientos.installation_state as installation_state_module
import sentientos.local_model_catalog_deployment_architecture as architecture
from sentientos.installation_state import (
    InstallationIdentity,
    InstallationStateError,
    InstallationStateHandle,
    InstallationStateRegistry,
    StateRelativePath,
)
from sentientos.local_model_catalog_deployment_architecture import (
    AUTHORITATIVE_CATALOG,
    CATALOG_DOMAIN,
    CATALOG_LOCK,
    DEPLOYMENT_RECEIPTS,
    TRANSACTIONS,
)
from sentientos.model_catalog_custody import ModelCatalogCustody

pytestmark = pytest.mark.no_legacy_skip


def _handle(tmp_path: Path, name: str = "primary") -> InstallationStateHandle:
    registry = InstallationStateRegistry._for_testing(tmp_path / "machine-state")
    return registry.open(InstallationIdentity.parse(name), create=True)


def _custody(tmp_path: Path, name: str = "primary") -> ModelCatalogCustody:
    custody = ModelCatalogCustody.for_installation(_handle(tmp_path, name))
    custody.initialize_directories()
    return custody


def _require_bytes(expected: bytes) -> Callable[[bytes], None]:
    def verify(observed: bytes) -> None:
        assert observed == expected
    return verify


def test_installation_identity_normalizes_and_remains_distinct() -> None:
    assert InstallationIdentity.parse("PRIMARY").value == "primary"
    assert InstallationIdentity.parse("primary") == InstallationIdentity.parse("PRIMARY")
    assert InstallationIdentity.parse("primary") != InstallationIdentity.parse("secondary")
    assert len({InstallationIdentity.parse("primary"), InstallationIdentity.parse("secondary")}) == 2


@pytest.mark.parametrize("value", ["", ".", "..", "a/b", "a\\b", " white", "white ", "CON", "nul.txt", "é"])
def test_installation_identity_rejects_ambiguous_values(value: str) -> None:
    with pytest.raises(ValueError, match="invalid_installation_identity"):
        InstallationIdentity.parse(value)


def test_registry_is_canonical_and_handle_constructor_is_not_public(tmp_path: Path) -> None:
    registry = InstallationStateRegistry._for_testing(tmp_path / "trusted")
    identity = InstallationIdentity.parse("one")
    handle = registry.open(identity, create=True)
    assert handle.root == tmp_path / "trusted" / "installations" / "one" / "state"
    with pytest.raises(TypeError):
        InstallationStateHandle(identity, tmp_path / "substituted")  # type: ignore[call-arg]
    with pytest.raises(InstallationStateError, match="registry_construction_forbidden"):
        InstallationStateRegistry(tmp_path / "caller-selected")


def test_relative_paths_and_model_catalog_projection_are_fixed(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    custody = ModelCatalogCustody.for_installation(handle)
    assert str(custody.domain.relative) == CATALOG_DOMAIN
    assert str(custody.authoritative_catalog.relative) == AUTHORITATIVE_CATALOG
    assert str(custody.catalog_lock.relative) == CATALOG_LOCK
    assert str(custody.transactions.relative) == TRANSACTIONS
    assert str(custody.deployment_receipts.relative) == DEPLOYMENT_RECEIPTS
    assert custody.custody_identity == "sentientos-installation:model-catalog:primary"
    assert all(handle.root in item.path.parents for item in (
        custody.domain, custody.authoritative_catalog, custody.catalog_lock,
        custody.transactions, custody.deployment_receipts,
    ))
    for invalid in ("/absolute", "../escape", "model-catalog/../escape", r"other\escape"):
        with pytest.raises(ValueError, match="invalid_state_relative_path"):
            StateRelativePath.parse(invalid)


def test_symlink_and_unexpected_object_substitution_fail_closed(tmp_path: Path) -> None:
    custody = _custody(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    custody.transactions.path.rmdir()
    custody.transactions.path.symlink_to(outside, target_is_directory=True)
    with pytest.raises(InstallationStateError, match="state_parent_unsafe"):
        custody.installation.durable_create(custody.transactions.child("intent.json"), b"intent")

    custody.authoritative_catalog.path.mkdir()
    with pytest.raises(InstallationStateError, match="state_object_not_regular"):
        custody.installation.durable_replace(custody.authoritative_catalog, b"catalog")


def test_installation_scoped_exclusive_lock_contention_and_release(tmp_path: Path) -> None:
    first = _custody(tmp_path, "first")
    second = _custody(tmp_path, "second")
    with first.installation.exclusive_lock(first.catalog_lock):
        with pytest.raises(InstallationStateError, match="lock_contended"):
            with first.installation.exclusive_lock(first.catalog_lock, blocking=False):
                pass
        with second.installation.exclusive_lock(second.catalog_lock, blocking=False):
            pass
    with first.installation.exclusive_lock(first.catalog_lock, blocking=False):
        pass


def test_lock_path_symlink_cannot_redirect(tmp_path: Path) -> None:
    custody = _custody(tmp_path)
    outside = tmp_path / "outside-lock"
    outside.write_bytes(b"")
    custody.catalog_lock.path.symlink_to(outside)
    with pytest.raises(InstallationStateError, match="lock_open_failed"):
        with custody.installation.exclusive_lock(custody.catalog_lock):
            pass


def test_durable_immutable_create_is_reopenable_and_never_clobbers(tmp_path: Path) -> None:
    custody = _custody(tmp_path)
    intent = custody.transactions.child("fixture-intent.json")
    custody.installation.durable_create(intent, b"first", verify=_require_bytes(b"first"))
    assert custody.installation.read_regular(intent) == b"first"
    with pytest.raises(InstallationStateError, match="state_object_already_exists"):
        custody.installation.durable_create(intent, b"second")
    assert custody.installation.read_regular(intent) == b"first"


def test_atomic_replace_publishes_new_regular_bytes_and_removes_stage(tmp_path: Path) -> None:
    custody = _custody(tmp_path)
    target = custody.authoritative_catalog
    custody.installation.durable_create(target, b"old")
    custody.installation.durable_replace(target, b"new", verify=_require_bytes(b"new"))
    assert custody.installation.read_regular(target) == b"new"
    assert not list(target.path.parent.glob(".authoritative-catalog.json.stage-*"))


def test_faulted_file_or_directory_flush_never_reports_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custody = _custody(tmp_path)
    intent = custody.transactions.child("faulted-intent.json")
    real_fsync = os.fsync
    calls = 0

    def fail_first(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected file flush failure")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_first)
    with pytest.raises(InstallationStateError, match="durable_create_failed"):
        custody.installation.durable_create(intent, b"not-success")


def test_faulted_post_replace_directory_flush_never_reports_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custody = _custody(tmp_path)
    target = custody.authoritative_catalog
    custody.installation.durable_create(target, b"old")
    real_fsync = os.fsync
    calls = 0

    def fail_second(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected directory flush failure")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_second)
    with pytest.raises(InstallationStateError, match="durable_replace_failed"):
        custody.installation.durable_replace(target, b"new")
    assert calls == 2


def test_cross_handle_object_redirection_is_rejected(tmp_path: Path) -> None:
    first = _custody(tmp_path, "first")
    second = _custody(tmp_path, "second")
    with pytest.raises(InstallationStateError, match="state_object_binding_mismatch"):
        first.installation.durable_create(second.transactions.child("intent.json"), b"redirect")


def test_unsupported_platform_contract_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = InstallationStateRegistry._for_testing(tmp_path / "machine-state")
    monkeypatch.setattr(installation_state_module, "fcntl", None)
    with pytest.raises(InstallationStateError, match="durable_state_platform_unsupported"):
        registry.open(InstallationIdentity.parse("primary"), create=True)


def test_storage_substrate_does_not_broaden_catalog_deployment_authority() -> None:
    assert architecture.PRINCIPAL == "deterministic_catalog_deployment_controller"
    assert architecture.ARCHITECTURE.controller_status == "implemented-without-live-authority"
    assert architecture.ARCHITECTURE.runtime_effects_enabled is False
    assert not hasattr(installation_state_module, "deploy_catalog")


def test_optional_read_distinguishes_only_absence_and_rejects_symlink(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    directory = handle.fixed_object("secure")
    handle.ensure_directory(directory)
    obj = directory.child("value.json")
    assert handle.read_optional_regular(obj) is None
    handle.durable_create(obj, b"{}")
    assert handle.read_optional_regular(obj) == b"{}"
    obj.path.unlink()
    obj.path.symlink_to(tmp_path / "outside")
    with pytest.raises(InstallationStateError):
        handle.read_optional_regular(obj)


def test_regular_enumeration_is_sorted_bound_and_rejects_nonregular_entries(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    directory = handle.fixed_object("transactions")
    handle.ensure_directory(directory)
    handle.durable_create(directory.child("b.json"), b"b")
    handle.durable_create(directory.child("a.json"), b"a")
    assert handle.list_regular_names(directory) == ("a.json", "b.json")
    (directory.path / "bad").mkdir()
    with pytest.raises(InstallationStateError, match="state_directory_entry_not_regular"):
        handle.list_regular_names(directory)
