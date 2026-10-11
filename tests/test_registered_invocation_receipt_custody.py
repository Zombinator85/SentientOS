from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import sentientosd
from sentientos.private_file_custody import replace_private_bytes
from sentientosd import RuntimeMaintenanceSurfaces

from tests.test_governed_local_model_invocation import _invoker


def test_receipt_registry_retains_visible_candidate_on_directory_fsync_uncertainty(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, invoker = _invoker(tmp_path)
    request = invoker.build_request(
        purpose="local_user_chat", prompt="bounded fixture", caller="test",
        correlation_id="receipt-registry-durability")
    payload = invoker.invoke(request).to_dict()
    path = tmp_path / "runtime" / "governed_local_model_invocation" / "registered_receipts.json"

    owner = object.__new__(RuntimeMaintenanceSurfaces)
    owner._governed_invocation_receipts_path = path
    owner._governed_invocation_receipt_lock = threading.RLock()
    owner._governed_invocation_receipts = ()

    def replace_then_report_uncertain(target: Path, data: bytes, *, max_bytes: int) -> bool:
        replace_private_bytes(target, data, max_bytes=max_bytes)
        return False

    monkeypatch.setattr(
        sentientosd, "replace_private_bytes_with_status", replace_then_report_uncertain)
    with pytest.raises(ValueError, match="durability_uncertain"):
        owner.register_governed_invocation_receipt(payload)

    assert owner._governed_invocation_receipts == (payload,)
    assert json.loads(path.read_text(encoding="utf-8")) == [payload]
