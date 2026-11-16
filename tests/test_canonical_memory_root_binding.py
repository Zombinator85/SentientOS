import hashlib
import json
import os
from pathlib import Path

from sentientos.canonical_memory import (
    CANDIDATE_TYPE,
    ROOT_PATH_BINDING_SCOPE,
    ROOT_FILESYSTEM_BINDING_SCOPE,
    AdmittedRetentionWriter,
    CanonicalMemoryStore,
    ExplicitRetentionAdmissionGate,
    configured_root_path_binding_digest,
    digest,
    retention_request_id,
)


def _retention_fixture(tmp_path: Path):
    root = tmp_path / "user-memory"
    raw_root = root / "raw"
    raw_root.mkdir(parents=True, mode=0o700)
    os.chmod(root, 0o700)
    os.chmod(raw_root, 0o700)
    store = CanonicalMemoryStore(root)
    gate = ExplicitRetentionAdmissionGate()
    writer = AdmittedRetentionWriter(store, admission_gate=gate)

    session_id = "session-root-binding"
    turn_id = "turn-" + "a" * 24
    text = "explicitly retained user memory"
    text_digest = digest({"text": text})
    operation = "retain:" + session_id + ":" + turn_id
    request_id = retention_request_id(operation)
    candidate = {
        "candidate_type": CANDIDATE_TYPE,
        "session_id": session_id,
        "source_turn_id": turn_id,
        "source_role": "user",
        "source_text_digest": text_digest,
        "explicitly_requested": True,
        "request_id": request_id,
        "operation_id": operation,
    }
    admission = gate.decide(candidate)
    memory_id = "memory-" + hashlib.sha256(
        operation.encode()).hexdigest()[:24]
    source_turn = {
        "role": "user",
        "turn_id": turn_id,
        "text": text,
        "text_digest": text_digest,
        "retention_state": "retained",
    }
    record = {
        "id": memory_id,
        "text": text,
        "text_digest": text_digest,
        "timestamp": "2030-01-02T00:00:00+00:00",
        "source": "conversation_user_turn",
        "category": "event",
        "tags": ["explicit-retention"],
        "importance": 1.0,
        "meta": {
            "session_id": session_id,
            "turn_id": turn_id,
            "request_id": request_id,
            "operation_id": operation,
            "admission_receipt_digest": admission.receipt_digest,
        },
    }
    record_path = raw_root / (memory_id + ".json")
    record_path.write_text(
        json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    os.chmod(record_path, 0o600)
    receipt = {
        "status": "memory_retention_committed",
        "memory_id": memory_id,
        "source_session_id": session_id,
        "source_turn_id": turn_id,
        "source_text_digest": text_digest,
        "admission_receipt_digest": admission.receipt_digest,
        "execution_operation_id": operation,
        "canonical_stored_record_digest": digest(record),
        "target_root_path_binding_digest": configured_root_path_binding_digest(root),
        "target_root_path_binding_scope": ROOT_PATH_BINDING_SCOPE,
        "index_update_result": "raw_fragment_available",
    }
    return writer, source_turn, receipt


def test_new_retention_receipt_labels_configured_path_binding(tmp_path: Path) -> None:
    writer, source_turn, receipt = _retention_fixture(tmp_path)
    result = writer.verify_committed_artifact(receipt, source_turn, "session-root-binding")
    assert result["artifact_status"] == "verified"
    assert result["root_path_binding_scope"] == ROOT_PATH_BINDING_SCOPE
    assert result["cross_restart_root_identity"] == "not_established"


def test_legacy_target_root_field_remains_readable_as_path_digest(tmp_path: Path) -> None:
    writer, source_turn, receipt = _retention_fixture(tmp_path)
    legacy = dict(receipt)
    legacy["target_root_identity"] = legacy.pop("target_root_path_binding_digest")
    legacy.pop("target_root_path_binding_scope")
    result = writer.verify_committed_artifact(legacy, source_turn, "session-root-binding")
    assert result["artifact_status"] == "verified"
    assert result["root_path_binding_scope"] == "legacy_target_root_identity_path_digest"
    assert result["cross_restart_root_identity"] == "not_established"


def test_path_binding_receipt_rejects_substituted_path_and_scope(tmp_path: Path) -> None:
    writer, source_turn, receipt = _retention_fixture(tmp_path)
    substituted = dict(receipt)
    substituted["target_root_path_binding_digest"] = "0" * 64
    assert writer.verify_committed_artifact(
        substituted, source_turn, "session-root-binding")["artifact_status"] == "conflict"
    wrong_scope = dict(receipt)
    wrong_scope["target_root_path_binding_scope"] = "filesystem_identity"
    assert writer.verify_committed_artifact(
        wrong_scope, source_turn, "session-root-binding")["artifact_status"] == "conflict"


def test_real_retention_writer_emits_and_reconciles_path_scoped_receipt(tmp_path: Path) -> None:
    writer, source_turn, _manual_receipt = _retention_fixture(tmp_path)
    session_id = "writer-produced-session"
    operation = "retain:" + session_id + ":" + source_turn["turn_id"]
    candidate = {
        "candidate_type": CANDIDATE_TYPE,
        "session_id": session_id,
        "source_turn_id": source_turn["turn_id"],
        "source_role": "user",
        "source_text_digest": source_turn["text_digest"],
        "explicitly_requested": True,
        "request_id": retention_request_id(operation),
        "operation_id": operation,
    }
    admission = writer.admission_gate.decide(candidate)
    receipt = writer.execute(candidate, admission, source_turn)
    assert receipt["target_root_path_binding_digest"] == configured_root_path_binding_digest(
        writer.store.root)
    assert receipt["target_root_path_binding_scope"] == ROOT_PATH_BINDING_SCOPE
    assert "target_root_identity" not in receipt
    verified = writer.verify_committed_artifact(receipt, source_turn, session_id)
    assert verified["artifact_status"] == "verified"
    assert verified["cross_restart_root_identity"] == "device_inode_rechecked_not_external_issuer"
    assert receipt["target_root_filesystem_binding_scope"] == ROOT_FILESYSTEM_BINDING_SCOPE
    assert receipt["target_root_filesystem_binding_digest"] == (
        writer.store.root_filesystem_binding_digest())

    artifact = writer.store.raw / (receipt["memory_id"] + ".json")
    prior_bytes = artifact.read_bytes()
    recovery_turn = {**source_turn, "retention_state": "requested"}
    recovered = writer.recover_existing_artifact(recovery_turn, session_id)
    assert recovered["artifact_status"] == "verified"
    assert recovered["write_replayed"] is False
    assert recovered["receipt"]["target_root_path_binding_digest"] == (
        receipt["target_root_path_binding_digest"])
    assert artifact.read_bytes() == prior_bytes


def test_filesystem_root_identity_survives_process_restart_and_rejects_replacement(
        tmp_path: Path, monkeypatch) -> None:
    if os.name != "posix":
        return
    import shutil
    import sentientos.canonical_memory as memory

    writer, source_turn, _path_receipt = _retention_fixture(tmp_path)
    session_id = "filesystem-root-binding"
    operation = "retain:" + session_id + ":" + source_turn["turn_id"]
    candidate = {
        "candidate_type": CANDIDATE_TYPE,
        "session_id": session_id,
        "source_turn_id": source_turn["turn_id"],
        "source_role": "user",
        "source_text_digest": source_turn["text_digest"],
        "explicitly_requested": True,
        "request_id": retention_request_id(operation),
        "operation_id": operation,
    }
    admission = writer.admission_gate.decide(candidate)
    receipt = writer.execute(candidate, admission, source_turn)
    first = writer.verify_committed_artifact(receipt, source_turn, session_id)
    assert first["artifact_status"] == "verified"
    assert first["cross_restart_root_identity"] == "device_inode_rechecked_not_external_issuer"

    # A fresh process has no process-local path-to-inode cache; durable receipt
    # evidence must still bind the exact filesystem directory observed at write.
    monkeypatch.setattr(memory, "_PROCESS_MEMORY_ROOT_IDENTITIES", {})
    restarted = AdmittedRetentionWriter(CanonicalMemoryStore(writer.store.root))
    after_restart = restarted.verify_committed_artifact(
        receipt, source_turn, session_id)
    assert after_restart["artifact_status"] == "verified"
    assert after_restart["cross_restart_root_identity"] == (
        "device_inode_rechecked_not_external_issuer")

    root = writer.store.root
    moved = root.with_name(root.name + "-prior")
    root.rename(moved)
    shutil.copytree(moved, root)
    os.chmod(root, 0o700)
    monkeypatch.setattr(memory, "_PROCESS_MEMORY_ROOT_IDENTITIES", {})
    replacement = AdmittedRetentionWriter(CanonicalMemoryStore(root))
    rejected = replacement.verify_committed_artifact(
        receipt, source_turn, session_id)
    assert rejected["artifact_status"] == "conflict"
    assert rejected["reason_code"] == "target_root_filesystem_identity_changed"


def test_memory_retrieval_prefers_newer_record_only_when_relevance_ties(
        tmp_path: Path, monkeypatch) -> None:
    store = CanonicalMemoryStore(tmp_path / "unused-memory")
    records = [
        {"id": "memory-older", "text": "My preference is concise replies.",
            "timestamp": "2025-01-01T00:00:00Z"},
        {"id": "memory-newer", "text": "My preference is detailed replies.",
            "timestamp": "2026-01-01T00:00:00Z"},
        {"id": "memory-middle", "text": "My preference is detailed replies.",
            "timestamp": "2025-06-01T00:00:00Z"},
    ]
    monkeypatch.setattr(store, "_records", lambda: (records, "complete"))

    selected = store.retrieve("preference replies", limit=3)["memories"]

    assert [record["id"] for record in selected] == [
        "memory-newer", "memory-middle", "memory-older"]
    assert [record["id"] for record in store.retrieve(
        "preference replies", limit=1)["memories"]] == ["memory-newer"]


def test_corrected_memory_is_retrievable_through_superseded_wording(
        tmp_path: Path, monkeypatch) -> None:
    store = CanonicalMemoryStore(tmp_path / "unused-memory")
    old = {"id": "memory-" + "a" * 24,
        "text": "I prefer expansive detailed replies.",
        "timestamp": "2025-01-01T00:00:00Z"}
    corrected = {"id": "memory-" + "b" * 24,
        "text": "Keep responses spare and direct.",
        "timestamp": "2026-01-01T00:00:00Z",
        "meta": {"correction_schema": "sentientos.canonical_memory_correction:v1",
            "correction_targets": [{"memory_id": old["id"],
                "memory_record_digest": digest(old)}]}}
    monkeypatch.setattr(store, "_records", lambda: ([old, corrected], "complete"))

    result = store.retrieve("How should I write expansive detailed replies?")

    assert [record["id"] for record in result["memories"]] == [corrected["id"]]
    assert result["memories"][0]["text"] == corrected["text"]
    assert old["text"] not in json.dumps(result["memories"])
    assert result["correction_relations"][0]["posture"] == (
        "explicit_user_correction_unverified")
    assert store.retrieve("quasar navigation")["memories"] == []


def test_superseded_wording_routes_through_a_correction_chain(
        tmp_path: Path, monkeypatch) -> None:
    store = CanonicalMemoryStore(tmp_path / "unused-memory")
    oldest = {"id": "memory-" + "c" * 24,
        "text": "I prefer expansive detailed replies.",
        "timestamp": "2024-01-01T00:00:00Z"}
    middle = {"id": "memory-" + "d" * 24,
        "text": "Keep answers brief and plain.",
        "timestamp": "2025-01-01T00:00:00Z",
        "meta": {"correction_schema": "sentientos.canonical_memory_correction:v1",
            "correction_targets": [{"memory_id": oldest["id"],
                "memory_record_digest": digest(oldest)}]}}
    current = {"id": "memory-" + "e" * 24,
        "text": "Use concise, direct wording.",
        "timestamp": "2026-01-01T00:00:00Z",
        "meta": {"correction_schema": "sentientos.canonical_memory_correction:v1",
            "correction_targets": [{"memory_id": middle["id"],
                "memory_record_digest": digest(middle)}]}}
    monkeypatch.setattr(store, "_records",
        lambda: ([oldest, middle, current], "complete"))

    oldest_wording = store.retrieve("expansive detailed replies")
    middle_wording = store.retrieve("brief plain answers")

    assert [record["id"] for record in oldest_wording["memories"]] == [current["id"]]
    assert [record["id"] for record in middle_wording["memories"]] == [current["id"]]
    assert oldest["text"] not in json.dumps(oldest_wording["memories"])
    assert middle["text"] not in json.dumps(middle_wording["memories"])


def test_distinctive_memory_anchor_beats_multiple_common_term_matches(
        tmp_path: Path, monkeypatch) -> None:
    store = CanonicalMemoryStore(tmp_path / "unused-memory")
    records = [{"id": "memory-atlas", "text": "Atlas roadmap owner is Mira.",
        "timestamp": "2020-01-01T00:00:00Z"}]
    records.extend({"id": f"memory-generic-{index}",
        "text": f"Project status update {index}: routine work continues.",
        "timestamp": "2030-01-01T00:00:00Z"} for index in range(6))
    monkeypatch.setattr(store, "_records", lambda: (records, "complete"))

    selected = store.retrieve("Atlas project status", limit=1)["memories"]

    assert [record["id"] for record in selected] == ["memory-atlas"]


def test_invalid_memory_timestamp_never_wins_recency_tie(
        tmp_path: Path, monkeypatch) -> None:
    store = CanonicalMemoryStore(tmp_path / "unused-memory")
    records = [
        {"id": "memory-unknown-time", "text": "My preference is concise replies.",
            "timestamp": "not-a-timestamp"},
        {"id": "memory-known-time", "text": "My preference is detailed replies.",
            "timestamp": "2026-01-01T00:00:00Z"},
    ]
    monkeypatch.setattr(store, "_records", lambda: (records, "complete"))

    selected = store.retrieve("preference replies", limit=2)["memories"]

    assert [record["id"] for record in selected] == [
        "memory-known-time", "memory-unknown-time"]


def test_indirect_answer_style_query_retrieves_both_conflicting_preferences(
        tmp_path: Path, monkeypatch) -> None:
    store = CanonicalMemoryStore(tmp_path / "unused-memory")
    records = [
        {"id": "memory-concise", "text": "Concise answers work best for me.",
            "timestamp": "2025-01-01T00:00:00Z"},
        {"id": "memory-detailed", "text": "Detailed answers work best for me.",
            "timestamp": "2026-01-01T00:00:00Z"},
    ]
    monkeypatch.setattr(store, "_records", lambda: (records, "complete"))

    selected = store.retrieve("What answer style suits me?", limit=4)["memories"]

    assert [record["id"] for record in selected] == [
        "memory-detailed", "memory-concise"]
