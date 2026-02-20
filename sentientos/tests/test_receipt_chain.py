from __future__ import annotations

import json
from pathlib import Path

from sentientos.receipt_chain import append_receipt, compute_receipt_hash, verify_receipt_chain


def _payload(receipt_id: str, created_at: str, prev_hash: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": 2,
        "receipt_id": receipt_id,
        "created_at": created_at,
        "pr_url": "https://github.com/o/r/pull/1",
        "pr_number": 1,
        "head_sha": "abc",
        "base_branch": "main",
        "doctrine_identity": {
            "bundle_sha256": "bundle-1",
            "selected_via": "api",
            "mirror_used": False,
            "metadata_ok": True,
            "manifest_ok": True,
        },
        "gating_result": "merged",
        "gating_reason": "remote_doctrine_passed",
        "prev_receipt_hash": prev_hash,
    }
    body["receipt_hash"] = compute_receipt_hash({k: v for k, v in body.items() if k != "receipt_hash"})
    return body


def test_receipt_hash_determinism() -> None:
    payload = _payload("r1", "2026-01-01T00:00:00Z")
    unsigned = {k: v for k, v in payload.items() if k != "receipt_hash"}

    first = compute_receipt_hash(unsigned)
    second = compute_receipt_hash(unsigned)

    assert first == second


def test_chain_linkage_and_break_detection(tmp_path: Path) -> None:
    first = append_receipt(
        tmp_path,
        {
            "schema_version": 2,
            "receipt_id": "2026-01-01T00-00-00Z-pr1-abc",
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
    second = append_receipt(
        tmp_path,
        {
            "schema_version": 2,
            "receipt_id": "2026-01-01T00-00-01Z-pr2-def",
            "created_at": "2026-01-01T00:00:01Z",
            "pr_url": "https://github.com/o/r/pull/2",
            "pr_number": 2,
            "head_sha": "def",
            "base_branch": "main",
            "doctrine_identity": {"bundle_sha256": "bundle-2", "selected_via": "api", "mirror_used": False, "metadata_ok": True, "manifest_ok": True},
            "gating_result": "merged",
            "gating_reason": "ok",
        },
    )

    assert second["prev_receipt_hash"] == first["receipt_hash"]
    assert verify_receipt_chain(tmp_path).ok is True

    receipt_path = tmp_path / "glow/forge/receipts/merge_receipt_2026-01-01T00-00-01Z-pr2-def.json"
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["head_sha"] = "tampered"
    receipt_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    broken = verify_receipt_chain(tmp_path)

    assert broken.ok is False
    assert broken.break_info is not None
    assert broken.break_info.reason == "receipt_hash_mismatch"
