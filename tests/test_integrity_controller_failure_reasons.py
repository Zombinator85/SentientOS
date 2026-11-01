from __future__ import annotations

from pathlib import Path

import pytest

from sentientos import integrity_controller as controller
from sentientos.audit_chain_gate import AuditChainVerification
from sentientos.receipt_anchors import AnchorVerification
from sentientos.receipt_chain import ChainBreak, ReceiptChainVerification

pytestmark = pytest.mark.no_legacy_skip


def test_receipt_chain_gate_uses_structured_break_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    check = ReceiptChainVerification(
        status="broken",
        checked_at="2026-11-01T00:00:00Z",
        checked_count=1,
        break_info=ChainBreak(receipt_id="r1", reason="receipt_hash_mismatch"),
    )
    monkeypatch.setattr(
        controller, "maybe_verify_receipt_chain", lambda *_args, **_kwargs: (check, True, False)
    )

    result = controller._gate_receipt_chain(Path("."), "now")

    assert (result.status, result.reason) == ("fail", "receipt_hash_mismatch")


def test_anchor_gate_uses_structured_failure_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    check = AnchorVerification(
        status="broken",
        checked_at="2026-11-01T00:00:00Z",
        checked_count=1,
        failure_reason="anchor_signature_invalid",
    )
    monkeypatch.setattr(
        controller, "maybe_verify_receipt_anchors", lambda *_args, **_kwargs: (check, True, False)
    )

    result = controller._gate_receipt_anchor(Path("."), "now")

    assert (result.status, result.reason) == ("fail", "anchor_signature_invalid")


def test_audit_gate_emits_status_reason_and_report(monkeypatch: pytest.MonkeyPatch) -> None:
    check = AuditChainVerification(
        status="broken",
        created_at="2026-11-01T00:00:00Z",
        break_count=1,
        checked_files=1,
    )
    monkeypatch.setattr(
        controller, "maybe_verify_audit_chain",
        lambda *_args, **_kwargs: (check, False, True, "report.json"),
    )

    result = controller._gate_audit_chain(Path("."), "now")

    assert (result.status, result.reason) == ("warn", "audit_chain_broken")
    assert result.evidence_paths == ["report.json"]
