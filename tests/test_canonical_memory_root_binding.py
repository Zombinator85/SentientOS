import hashlib
import json
import os
from pathlib import Path

from sentientos.canonical_memory import (
    CANDIDATE_TYPE,
    ROOT_PATH_BINDING_SCOPE,
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
        json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
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
