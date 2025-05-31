import json
import importlib
from pathlib import Path

import final_approval as fa


def setup(tmp_path, approvers):
    log = tmp_path / "log.jsonl"
    cfg = tmp_path / "approvers.json"
    cfg.write_text(json.dumps(approvers))
    return log, cfg


def test_multi_approver_chain(tmp_path, monkeypatch):
    log, cfg = setup(tmp_path, ["4o", "alice"])
    monkeypatch.setenv("FINAL_APPROVAL_LOG", str(log))
    monkeypatch.setenv("FINAL_APPROVER_FILE", str(cfg))
    monkeypatch.setenv("FOUR_O_APPROVE", "true")
    monkeypatch.setenv("ALICE_APPROVE", "true")
    importlib.reload(fa)
    assert fa.request_approval("demo")
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    data = [json.loads(l) for l in lines]
    assert all(d["approved"] for d in data)


def test_reject_in_chain(tmp_path, monkeypatch):
    log, cfg = setup(tmp_path, ["4o", "alice"])
    monkeypatch.setenv("FINAL_APPROVAL_LOG", str(log))
    monkeypatch.setenv("FINAL_APPROVER_FILE", str(cfg))
    monkeypatch.setenv("FOUR_O_APPROVE", "true")
    monkeypatch.setenv("ALICE_APPROVE", "false")
    importlib.reload(fa)
    assert not fa.request_approval("demo")
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    last = json.loads(lines[-1])
    assert not last["approved"] and last["approver"] == "alice"
