import json
import importlib
from pathlib import Path
import os
import sys

# ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import final_approval as fa


def reload_with(tmp_path, monkeypatch, env=None, file_chain=None):
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FINAL_APPROVAL_LOG", str(log))
    if env is not None:
        monkeypatch.setenv("REQUIRED_FINAL_APPROVER", env)
    else:
        monkeypatch.delenv("REQUIRED_FINAL_APPROVER", raising=False)
    if file_chain is not None:
        cfg = tmp_path / "approvers.json"
        cfg.write_text(json.dumps(file_chain))
        monkeypatch.setenv("FINAL_APPROVER_FILE", str(cfg))
    else:
        monkeypatch.delenv("FINAL_APPROVER_FILE", raising=False)
    importlib.reload(fa)
    return log


def test_single_approver_env(tmp_path, monkeypatch):
    log = reload_with(tmp_path, monkeypatch, env="alice")
    monkeypatch.setenv("ALICE_APPROVE", "true")
    assert fa.request_approval("demo")
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["approver"] == "alice" and data["approved"]


def test_multi_approver_chain(tmp_path, monkeypatch):
    log = reload_with(tmp_path, monkeypatch, file_chain=["4o", "alice"])
    monkeypatch.setenv("FOUR_O_APPROVE", "true")
    monkeypatch.setenv("ALICE_APPROVE", "true")
    assert fa.request_approval("demo")
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    assert all(json.loads(l)["approved"] for l in lines)


def test_reject_in_chain(tmp_path, monkeypatch):
    log = reload_with(tmp_path, monkeypatch, file_chain=["4o", "alice"])
    monkeypatch.setenv("FOUR_O_APPROVE", "true")
    monkeypatch.setenv("ALICE_APPROVE", "false")
    assert not fa.request_approval("demo")
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    last = json.loads(lines[-1])
    assert not last["approved"] and last["approver"] == "alice"


def test_override_chain(tmp_path, monkeypatch):
    log = reload_with(tmp_path, monkeypatch, env="4o")
    monkeypatch.setenv("FOUR_O_APPROVE", "false")
    monkeypatch.setenv("ALICE_APPROVE", "true")
    fa.override_approvers(["alice"])
    assert fa.request_approval("demo")
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["approver"] == "alice"


def test_cli_override(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("FINAL_APPROVAL_LOG", str(tmp_path / "fa.jsonl"))
    monkeypatch.setenv("REQUIRED_FINAL_APPROVER", "4o")
    monkeypatch.setenv("FOUR_O_APPROVE", "false")
    monkeypatch.setenv("ALICE_APPROVE", "true")
    import importlib
    import final_approval
    importlib.reload(final_approval)
    import memory_cli as mc
    import self_patcher
    p = self_patcher.apply_patch("note", auto=False)
    import sys
    monkeypatch.setattr(sys, "argv", ["mc", "--final-approvers", "alice", "approve_patch", p["id"]])
    mc.main()
    out = capsys.readouterr().out
    assert "Approved" in out
    log = Path(tmp_path / "fa.jsonl").read_text().splitlines()
    assert json.loads(log[0])["approver"] == "alice"


def test_file_runtime_override(tmp_path, monkeypatch):
    log = reload_with(tmp_path, monkeypatch, env="4o")
    monkeypatch.setenv("FOUR_O_APPROVE", "false")
    monkeypatch.setenv("ALICE_APPROVE", "true")
    cfg = tmp_path / "ap.txt"
    cfg.write_text("alice\n")
    fa.override_approvers(fa.load_file_approvers(cfg), source="file")
    assert fa.request_approval("demo")
    entry = json.loads(log.read_text().splitlines()[0])
    assert entry["approver"] == "alice" and entry["source"] == "file"


def test_priority_order(tmp_path, monkeypatch):
    log = reload_with(tmp_path, monkeypatch, env="4o", file_chain=["bob"])
    monkeypatch.setenv("FOUR_O_APPROVE", "true")
    monkeypatch.setenv("BOB_APPROVE", "true")
    fa.override_approvers(["alice"], source="cli")
    monkeypatch.setenv("ALICE_APPROVE", "true")
    assert fa.request_approval("demo")
    data = json.loads(log.read_text().splitlines()[0])
    assert data["approver"] == "alice" and data["source"] == "cli"
