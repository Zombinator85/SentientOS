from __future__ import annotations

import json
from pathlib import Path

from sentientos.receipt_anchors import (
    canonical_anchor_payload_bytes,
    compute_anchor_payload_sha256,
    create_anchor,
    verify_receipt_anchors,
)
from sentientos.receipt_chain import append_receipt


def _append_sample_receipt(tmp_path: Path, receipt_id: str = "r1") -> None:
    append_receipt(
        tmp_path,
        {
            "schema_version": 2,
            "receipt_id": receipt_id,
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


def test_anchor_payload_canonicalization_deterministic() -> None:
    payload = {
        "schema_version": 1,
        "anchor_id": "a",
        "created_at": "2026-01-01T00:00:00Z",
        "receipt_chain_tip_hash": "abc",
        "prev_anchor_hash": None,
        "receipts_index_sha256": "def",
        "public_key_id": "hmac-test",
        "algorithm": "hmac-sha256-test",
    }

    first_bytes = canonical_anchor_payload_bytes(payload)
    second_bytes = canonical_anchor_payload_bytes(dict(payload))

    assert first_bytes == second_bytes
    assert compute_anchor_payload_sha256(payload) == compute_anchor_payload_sha256(dict(payload))


def test_hmac_anchor_sign_and_verify(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_ANCHOR_SIGNING", "hmac-test")
    monkeypatch.setenv("SENTIENTOS_ANCHOR_HMAC_SECRET", "unit-test-secret")
    monkeypatch.setenv("SENTIENTOS_ANCHOR_PUBLIC_KEY_ID", "unit-test")
    _append_sample_receipt(tmp_path)

    create_anchor(tmp_path)
    result = verify_receipt_anchors(tmp_path, require_tip=True)

    assert result.ok is True
    assert result.last_anchor_public_key_id == "unit-test"


def test_anchor_verify_fails_if_receipt_mutated_after_anchor(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_ANCHOR_SIGNING", "hmac-test")
    _append_sample_receipt(tmp_path)
    create_anchor(tmp_path)

    receipt_path = next((tmp_path / "glow/forge/receipts").glob("merge_receipt_*.json"))
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["head_sha"] = "tampered"
    receipt_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_receipt_anchors(tmp_path)

    assert result.ok is False
    assert result.failure_reason == "receipt_chain_broken"
