from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.codex_transfer_packet import (
    CodexTransferPacketError, build_codex_transfer_packets, packet_json_bytes,
    score_codex_transfer_responses,
)
from sentientos.local_model_authority import digest_payload
from sentientos.resident_developmental_writeback import (
    DevelopmentalHistoryStore, DevelopmentalRecord, WritebackReceipt, _identity,
)


def _stored_record(root: Path, name: str, family: str,
        examples: list[tuple[int, int, bool]]) -> DevelopmentalRecord:
    run_id = "run-" + name
    task_digest = "sha256:" + hashlib.sha256((name + "-task").encode()).hexdigest()
    score_digest = "sha256:" + hashlib.sha256((name + "-score").encode()).hexdigest()
    source_id = "developmental-history-run:" + run_id
    source_digest = hashlib.sha256((name + "-source").encode()).hexdigest()
    source = {"source_id": source_id, "digest": source_digest, "kind": "embodiment"}
    payload = {"objective_task_family": family,
        "task_family_posture": "operator_declared_protocol_bound",
        "objective_task_commitment_posture": "salted_private_oracle_commitment:v1",
        "objective_task_descriptor": {"task_family_id": family,
            "task_digest": task_digest,
            "task_digest_posture": "salted_private_oracle_commitment:v1"},
        "run_id": run_id, "run_digest": "sha256:" + hashlib.sha256(
            (name + "-run").encode()).hexdigest(),
        "objective_scores": [{"condition_id": "history_present",
            "schema_version": "sentientos.objective_task_score:v3",
            "task_digest": task_digest, "score_digest": score_digest,
            "evaluator": "deterministic_exact_integer_suite_oracle_v2"}],
        "acquisition_examples": [{"probe_input": x, "observed_answer": y,
            "evaluator_correct": correct, "source_score_digest": score_digest,
            "source_condition": "history_present"} for x, y, correct in examples]}
    fact = {"fact_id": "fact-" + name,
        "subject": {"subject_id": run_id,
            "subject_kind": "developmental_history_intervention_experiment"},
        "source": source, "payload": payload}
    candidate = {"selected_facts": [fact], "selected_sources": [source]}
    raw = DevelopmentalRecord(record_id="", record_digest="", candidate=candidate,
        admission_id="admission-" + name, admission_binding_digest="sha256:" + "a" * 64,
        principal="fixture", operation_id="fixture-operation", correlation_id=name,
        created_at="2026-01-01T00:00:00+00:00")
    record_id, record_digest = _identity("devrec", raw.semantic_payload())
    record = replace(raw, record_id=record_id, record_digest=record_digest)
    store = DevelopmentalHistoryStore(root)
    store.append(record)
    raw_receipt = WritebackReceipt(receipt_id="", receipt_digest="",
        record_id=record.record_id, record_digest=record.record_digest,
        candidate_id="candidate-" + name, candidate_digest="sha256:" + "c" * 64,
        admission_id=record.admission_id,
        admission_binding_digest=record.admission_binding_digest,
        principal=record.principal, operation_id=record.operation_id,
        storage_verified=True)
    receipt_id, receipt_digest = _identity("devreceipt", raw_receipt.semantic_payload())
    store.write_receipt(replace(raw_receipt, receipt_id=receipt_id,
        receipt_digest=receipt_digest))
    return store.get(record_id)


def test_blinded_packets_keep_history_and_scorer_custody_separate(tmp_path: Path) -> None:
    store = DevelopmentalHistoryStore(tmp_path / "history")
    positive = _stored_record(tmp_path / "history", "positive", "affine-v1",
        [(1, 5, True), (2, 8, True)])
    irrelevant = _stored_record(tmp_path / "history", "irrelevant", "color-sequence",
        [(4, 2, True)])
    adverse = _stored_record(tmp_path / "history", "adverse", "affine-v1",
        [(6, 20, False), (7, 23, True)])
    result = build_codex_transfer_packets(history_store=store,
        history_record_id=positive.record_id, irrelevant_record_id=irrelevant.record_id,
        adverse_record_id=adverse.record_id, family="affine-v1",
        irrelevant_family="color-sequence", probe_inputs=(10, 11, 12),
        multiplier=3, offset=2,
        applicability_basis="Preregistered fixture assigns one shared mapping to these episodes.",
        model_settings={"visible_model_name": "Codex", "effort_setting": "medium",
            "generation_settings": {"temperature": 0}}, nonce="0" * 64)
    packets = result["subject_packets"]
    assert len(packets) == 5
    by_condition = {condition: packets[packet_id]
        for packet_id, condition in result["scorer_manifest"]["condition_by_packet_id"].items()}
    assert by_condition["history_present"]["historical_examples"] == \
        by_condition["history_restored"]["historical_examples"]
    assert by_condition["history_withheld"]["historical_examples"] == []
    assert by_condition["history_withheld"]["source_facts"] == []
    assert len(by_condition["history_present"]["historical_examples"]) == 2
    assert len(by_condition["history_present"]["source_facts"]) == 1
    source_fact = by_condition["history_present"]["source_facts"][0]["source_fact"]
    assert source_fact["fact_id"] == by_condition["history_present"]["historical_examples"][0]["source_fact_id"]
    assert [item["evaluator_correct"] for item in
        by_condition["adverse_history"]["historical_examples"]] == [False, True]
    assert by_condition["irrelevant_history"]["historical_examples"][0]["source_task_digest"]
    for packet in packets.values():
        encoded = packet_json_bytes(packet).decode()
        assert '"multiplier"' not in encoded and '"offset"' not in encoded
        assert '"answer_key"' not in encoded
        assert "treatment_condition" not in packet and "condition_label" not in packet
        assert not any(label in packet["instructions"] for label in (
            "history_present", "history_withheld", "history_restored",
            "irrelevant_history", "adverse_history"))
        assert packet["model_settings"] == result["scorer_manifest"]["model_settings_preregistered"]
    manifest = result["scorer_manifest"]
    assert manifest["answer_key"] == [32, 35, 38]
    assert manifest["applicability"]["posture"] == \
        "operator_declared_shared_mapping_not_independently_verified"
    assert manifest["source_record_identities"][0]["record_digest"] == positive.record_digest
    responses = {packet_id: {"raw_output": '{"answers": [32, 35, 38]}',
        "session_id": "fresh-" + packet_id, "timestamp": "2026-10-14T00:00:00Z",
        "visible_model_name": "Codex", "effort_setting": "medium",
        "generation_settings": {"temperature": 0}}
        for packet_id in packets}
    scored = score_codex_transfer_responses(scorer_manifest=manifest, responses=responses)
    assert all(row["correct_count"] == 3 and row["denominator"] == 3
        and row["full_task_correct"] is True
        and row["reported_settings_match_preregistration"] is True
        for row in scored["conditions"])
    malformed = dict(responses)
    malformed[next(iter(malformed))] = {**malformed[next(iter(malformed))],
        "raw_output": '{"answers": [32, true, 38]}'}
    malformed_scores = score_codex_transfer_responses(scorer_manifest=manifest,
        responses=malformed)
    assert next(row for row in malformed_scores["conditions"]
        if row["packet_id"] == next(iter(malformed)))["status"] == \
        "unscoreable_malformed_output"
    interrupted = dict(responses)
    interrupted_id = next(iter(interrupted))
    interrupted.pop(interrupted_id)
    interrupted_scores = score_codex_transfer_responses(scorer_manifest=manifest,
        responses=interrupted)
    assert next(row for row in interrupted_scores["conditions"]
        if row["packet_id"] == interrupted_id)["status"] == "interrupted_or_not_run"


def test_packet_builder_rejects_overlapping_heldout_inputs_and_bad_history(tmp_path: Path) -> None:
    store_root = tmp_path / "history"
    store = DevelopmentalHistoryStore(store_root)
    positive = _stored_record(store_root, "positive", "affine-v1", [(1, 5, True)])
    irrelevant = _stored_record(store_root, "irrelevant", "color-sequence", [(4, 2, True)])
    adverse = _stored_record(store_root, "adverse", "affine-v1", [(6, 20, False)])
    kwargs = dict(history_store=store, history_record_id=positive.record_id,
        irrelevant_record_id=irrelevant.record_id, adverse_record_id=adverse.record_id,
        family="affine-v1", irrelevant_family="color-sequence", probe_inputs=(1, 11),
        multiplier=3, offset=2, applicability_basis="same preregistered fixture mapping",
        model_settings={"visible_model_name": "Codex", "effort_setting": "medium",
            "generation_settings": {"temperature": 0}}, nonce="1" * 64)
    with pytest.raises(CodexTransferPacketError, match="heldout_probe_overlaps_historical_example"):
        build_codex_transfer_packets(**kwargs)
    with pytest.raises(CodexTransferPacketError, match="model_settings_incomplete"):
        build_codex_transfer_packets(**{**kwargs, "probe_inputs": (10, 11),
            "model_settings": {"visible_model_name": "Codex"}})


def test_packet_builder_requires_verified_writeback_receipt(tmp_path: Path) -> None:
    root = tmp_path / "history"
    store = DevelopmentalHistoryStore(root)
    positive = _stored_record(root, "positive", "affine-v1", [(1, 5, True)])
    irrelevant = _stored_record(root, "irrelevant", "color-sequence", [(4, 2, True)])
    adverse = _stored_record(root, "adverse", "affine-v1", [(6, 20, False)])
    for receipt in store.receipts():
        if receipt.record_id == positive.record_id:
            (store.receipts_root / f"{receipt.receipt_id}.json").unlink()
    with pytest.raises(CodexTransferPacketError, match="history_record_writeback_receipt_missing"):
        build_codex_transfer_packets(history_store=store,
            history_record_id=positive.record_id, irrelevant_record_id=irrelevant.record_id,
            adverse_record_id=adverse.record_id, family="affine-v1",
            irrelevant_family="color-sequence", probe_inputs=(10, 11),
            multiplier=3, offset=2, applicability_basis="shared fixture mapping",
            model_settings={"visible_model_name": "Codex", "effort_setting": "medium",
                "generation_settings": {"temperature": 0}})
