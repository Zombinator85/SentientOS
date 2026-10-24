from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path

import pytest

from sentientos.windows_handle_custody import (
    WindowsHandleCustodyError,
    read_explicit_file,
    read_regular_files,
)
from sentientos.work_plan import (
    WORK_PLAN_EVIDENCE_DIR,
    WorkPlanError,
    _open_work_plan_evidence_directory,
)


pytestmark = pytest.mark.no_legacy_skip


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
