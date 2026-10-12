from __future__ import annotations

import pytest

from sentientos.resident_developmental_cognition import ResidentDevelopmentalCognitionError
from tests.test_resident_developmental_cognition import FakeInvoker, owner, snapshot

pytestmark = pytest.mark.no_legacy_skip


def test_restart_repairs_history_record_published_before_receipt_acknowledgement(tmp_path) -> None:
    interrupted, _fake = owner(tmp_path)

    def fail_receipt_acknowledgement(receipt):
        # The canonical record publication has already succeeded when this
        # method is called. Simulate process loss before receipt custody.
        assert len(interrupted.writeback.store.records()) == 1
        assert interrupted.writeback.store.receipts() == ()
        raise ResidentDevelopmentalCognitionError("simulated_before_receipt_publication")

    interrupted.writeback.store.write_receipt = fail_receipt_acknowledgement
    with pytest.raises(ResidentDevelopmentalCognitionError,
                       match="simulated_before_receipt_publication"):
        interrupted.run_tick(snapshot=snapshot(), tick_id="tick-before-receipt")

    durable_records = interrupted.writeback.store.records()
    assert len(durable_records) == 1
    assert interrupted.writeback.store.receipts() == ()

    restarted, fake = owner(tmp_path)
    recovered_state = restarted._state()
    assert len(restarted.writeback.store.records()) == 1
    recovered_receipts = restarted.writeback.store.receipts()
    assert len(recovered_receipts) == 1
    assert recovered_receipts[0].record_id == durable_records[0].record_id
    assert recovered_receipts[0].record_digest == durable_records[0].record_digest
    checkpoint = next(row for row in recovered_state["completed_ticks"]
                      if row["tick_id"] == "tick-before-receipt")
    assert checkpoint["record_id"] == durable_records[0].record_id
    assert checkpoint["receipt_id"] == recovered_receipts[0].receipt_id
    assert not any(row.get("tick_id") == "tick-before-receipt"
                   for row in recovered_state["incomplete_ticks"])
    assert restarted.writeback.recover_completed_records() == (
        (durable_records[0], recovered_receipts[0]),)

    with pytest.raises(ResidentDevelopmentalCognitionError, match="tick_already_completed"):
        restarted.run_tick(snapshot=snapshot(), tick_id="tick-before-receipt")
    later = restarted.run_tick(snapshot=snapshot(2), tick_id="tick-after-receipt-recovery")
    assert later.prior_record_ids == (durable_records[0].record_id,)
    assert any(request.purpose == "resident_developmental_retrieval_cognition"
               for request in fake.requests)
