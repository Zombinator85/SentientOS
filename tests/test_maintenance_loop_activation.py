from __future__ import annotations

import os
from pathlib import Path

import pytest

from sentientos import maintenance_loop_activation as activation

pytestmark = pytest.mark.no_legacy_skip


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"; repo.mkdir(); (repo / ".git").mkdir()
    return repo


def test_init_roots_is_safe_and_idempotent(tmp_path: Path) -> None:
    repo = _repo(tmp_path); names = {n: tmp_path / "external" / n for n in ("state", "workspace", "scratch", "inbox")}
    first = activation.init_roots(repo, names); second = activation.init_roots(repo, names)
    assert first["status"] == second["status"] == "roots_ready"
    assert {x["status"] for x in first["roots"]} == {"created"}
    assert {x["status"] for x in second["roots"]} == {"verified"}
    if os.name == "posix": assert all((p.stat().st_mode & 0o777) == 0o700 for p in names.values())


def test_init_roots_rejects_repository_descendant(tmp_path: Path) -> None:
    repo = _repo(tmp_path); roots = {n: tmp_path / n for n in ("state", "workspace", "scratch", "inbox")}; roots["state"] = repo / "state"
    with pytest.raises(ValueError, match="inside_repository"): activation.init_roots(repo, roots)


def test_init_roots_rejects_symlink(tmp_path: Path) -> None:
    repo = _repo(tmp_path); target = tmp_path / "target"; target.mkdir(); link = tmp_path / "link"; link.symlink_to(target, target_is_directory=True)
    roots = {n: tmp_path / n for n in ("state", "workspace", "scratch", "inbox")}; roots["state"] = link
    with pytest.raises(ValueError, match="symlink"): activation.init_roots(repo, roots)


def test_inspect_activation_rejects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "receipts.jsonl"
    receipt = {"schema_version": activation.ACTIVATION_RECEIPT_SCHEMA, "sequence": 1,
               "previous_receipt_digest": activation.ZERO_DIGEST, "terminal_status": "idle"}
    receipt["receipt_digest"] = activation.digest(receipt); path.write_bytes(activation.canonical_bytes(receipt) + b"\n")
    assert activation.inspect_activation(path)["head_digest"] == receipt["receipt_digest"]
    receipt["terminal_status"] = "published"; path.write_bytes(activation.canonical_bytes(receipt) + b"\n")
    with pytest.raises(ValueError, match="integrity"): activation.inspect_activation(path)


def test_run_argv_is_an_array_without_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "config.json"; config.write_text("{}")
    monkeypatch.setattr(activation.watchdog, "load_config", lambda _: {"repository_root": str(tmp_path)})
    argv = activation.run_argv(config, "2030-01-01T00:00:00Z")
    assert isinstance(argv, list) and argv[-1] == "run-bounded" and not any("shell" in x for x in argv)
