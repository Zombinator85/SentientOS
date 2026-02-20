from __future__ import annotations

import json
from pathlib import Path

from sentientos.anchor_witness import maybe_publish_anchor_witness
from sentientos.receipt_anchors import create_anchor
from sentientos.receipt_chain import append_receipt


def _seed_anchor(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_ANCHOR_SIGNING", "hmac-test")
    append_receipt(
        tmp_path,
        {
            "schema_version": 2,
            "receipt_id": "r1",
            "created_at": "2026-01-01T00:00:00Z",
            "pr_url": "https://github.com/o/r/pull/1",
            "pr_number": 1,
            "head_sha": "abc",
            "base_branch": "main",
            "doctrine_identity": {"bundle_sha256": "bundle-1", "selected_via": "api", "mirror_used": False, "metadata_ok": True, "manifest_ok": True},
            "gating_result": "merged",
            "gating_reason": "ok",
        },
    )
    create_anchor(tmp_path)


def test_witness_file_backend_idempotent(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _seed_anchor(tmp_path, monkeypatch)
    monkeypatch.setenv("SENTIENTOS_ANCHOR_WITNESS_PUBLISH", "1")
    monkeypatch.setenv("SENTIENTOS_ANCHOR_WITNESS_BACKEND", "file")
    monkeypatch.setenv("SENTIENTOS_ANCHOR_WITNESS_LOG", str(tmp_path / "glow/federation/witness.jsonl"))

    first, err1 = maybe_publish_anchor_witness(tmp_path)
    second, err2 = maybe_publish_anchor_witness(tmp_path)

    assert err1 is None
    assert err2 is None
    assert first["witness_status"] == "ok"
    rows = (tmp_path / "glow/federation/witness.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["anchor_id"] == first["last_witness_anchor_id"] == second["last_witness_anchor_id"]


def test_witness_disabled(tmp_path: Path) -> None:
    status, err = maybe_publish_anchor_witness(tmp_path)
    assert err is None
    assert status["witness_status"] == "disabled"
