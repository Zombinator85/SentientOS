from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

import sentientos.production_chat_resource_provisioning_request_doctor as doctor
import sentientos.production_chat_resource_provisioning_request_consumer as consumer
from sentientos.installation_state import InstallationStateHandle
from sentientos.production_chat_resource_provisioning_request_publisher import (
    publish_production_chat_resource_provisioning_request,
)
from tests.test_production_chat_resource_provisioning_bundle_producer import inputs

pytestmark = pytest.mark.no_legacy_skip


def _publish(tmp_path: Path, selected: str = "doctor") -> tuple[Any, bytes, bytes]:
    handle, values = inputs(tmp_path)
    clock = values.pop("clock")
    publish_production_chat_resource_provisioning_request(
        handle, selected, publication_clock=clock, **values)
    prefix = f"local-model/resource-provisioning-requests/{selected}/"
    return (handle,
            handle.read_regular(handle.fixed_object(prefix + "request.json")),
            handle.read_regular(handle.fixed_object(prefix + "publication-receipt.json")))


def _diagnose(handle: Any, selected: str = "doctor") -> dict[str, Any]:
    return doctor.diagnose_production_chat_resource_provisioning_request_publication(
        handle, selected).to_dict()


def _tree(root: Path) -> dict[str, tuple[str, bytes | None]]:
    result: dict[str, tuple[str, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        result[relative] = ("directory", None) if path.is_dir() else ("file", path.read_bytes())
    return result


def test_real_complete_publication_diagnosis_reuses_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    handle, request, _ = _publish(tmp_path)
    calls = []
    original = consumer.load_published_production_chat_resource_provisioning_request
    def observed(*args: object) -> bytes:
        calls.append(args)
        return original(*args)  # type: ignore[arg-type]
    monkeypatch.setattr(doctor, "load_published_production_chat_resource_provisioning_request", observed)
    report = _diagnose(handle)
    assert calls and report["custody_shape"] == "complete_pair"
    assert report["overall_doctor_status"] == "publication_doctor_complete"
    assert report["completed_publication_verification_status"] == "verified"
    assert report["publication_complete"] is True
    serialized = json.dumps(report, sort_keys=True)
    assert request.decode() not in serialized
    assert str(handle.root) not in serialized


def test_bare_request_diagnosis_is_unpublished_and_not_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    handle, values = inputs(tmp_path); clock = values.pop("clock")
    original = InstallationStateHandle.durable_create
    def fail_receipt(self: Any, obj: Any, data: bytes, **options: object) -> None:
        if obj.relative.parts[-1] == "publication-receipt.json":
            raise OSError("injected")
        original(self, obj, data, **options)
    monkeypatch.setattr(InstallationStateHandle, "durable_create", fail_receipt)
    with pytest.raises(Exception, match="request_publication_failed"):
        publish_production_chat_resource_provisioning_request(
            handle, "doctor", publication_clock=clock, **cast(Any, values))
    report = _diagnose(handle)
    assert report["custody_shape"] == "bare_request"
    assert report["overall_doctor_status"] == "publication_doctor_incomplete"
    assert report["verification_reason_code"] == "unpublished_incomplete_custody_at_observation_time"
    assert report["request_verification_status"] == "valid"
    assert report["request_digest"] and report["intent_digest"]
    assert report["publication_complete"] is False
    assert report["terminal_failure_inferred"] is False
    assert report["concurrent_publication_excluded"] is False


def test_malformed_bare_request_preserves_topology(tmp_path: Path) -> None:
    handle, _ = inputs(tmp_path)
    destination = handle.fixed_object("local-model/resource-provisioning-requests/doctor")
    handle.ensure_directory(destination)
    handle.durable_create(handle.fixed_object(
        "local-model/resource-provisioning-requests/doctor/request.json"), b"not-json")
    report = _diagnose(handle)
    assert report["custody_shape"] == "bare_request"
    assert report["request_verification_status"] == "invalid"
    assert report["request_verification_reason_code"] == "invalid_request_json"


def test_receipt_only_is_contradictory(tmp_path: Path) -> None:
    handle, _ = inputs(tmp_path)
    destination = handle.fixed_object("local-model/resource-provisioning-requests/doctor")
    handle.ensure_directory(destination)
    handle.durable_create(handle.fixed_object(
        "local-model/resource-provisioning-requests/doctor/publication-receipt.json"), b"receipt")
    report = _diagnose(handle)
    assert report["custody_shape"] == "orphan_receipt"
    assert report["overall_doctor_status"] == "publication_doctor_contradictory"
    assert report["receipt_storage_sha256"] and report["receipt_storage_bytes"] == 7


def test_empty_existing_destination_is_absent_without_authority(tmp_path: Path) -> None:
    handle, _ = inputs(tmp_path)
    handle.ensure_directory(handle.fixed_object("local-model/resource-provisioning-requests/doctor"))
    report = _diagnose(handle)
    assert report["custody_shape"] == "empty_existing_destination"
    assert report["overall_doctor_status"] == "publication_doctor_absent"
    assert report["next_inspection_guidance"] == "no_publication_authority_inferred"


def test_unavailable_parent_is_not_absence(tmp_path: Path) -> None:
    handle, _ = inputs(tmp_path)
    report = _diagnose(handle)
    assert report["custody_shape"] == "custody_unavailable"
    assert report["request_present"] is None and report["receipt_present"] is None


@pytest.mark.parametrize("name", ["request.json", "publication-receipt.json"])
def test_nonregular_object_is_bounded_unavailable(tmp_path: Path, name: str) -> None:
    handle, _ = inputs(tmp_path)
    destination = handle.fixed_object("local-model/resource-provisioning-requests/doctor")
    handle.ensure_directory(destination)
    handle.fixed_object(f"local-model/resource-provisioning-requests/doctor/{name}").path.mkdir()
    report = _diagnose(handle)
    assert report["custody_shape"] == "custody_unavailable"
    assert report["verification_reason_code"] == "authenticated_custody_inspection_unavailable"


def test_tampered_complete_custody_is_invalid_through_consumer(tmp_path: Path) -> None:
    handle, _, _ = _publish(tmp_path)
    receipt = handle.fixed_object(
        "local-model/resource-provisioning-requests/doctor/publication-receipt.json").path
    receipt.write_bytes(receipt.read_bytes() + b" ")
    report = _diagnose(handle)
    assert report["custody_shape"] == "complete_pair"
    assert report["overall_doctor_status"] == "publication_doctor_invalid"
    assert report["completed_publication_verification_status"] == "invalid"
    assert report["verification_reason_code"] == "noncanonical_receipt_custody"


def test_lock_free_zero_mutation_and_deterministic_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    handle, _, _ = _publish(tmp_path)
    lock = handle.fixed_object("local-model/resource-provisioning-request-locks/doctor.lock").path
    lock.unlink()
    before = _tree(handle.root)
    for name in ("exclusive_lock", "ensure_directory", "durable_create", "durable_replace"):
        monkeypatch.setattr(InstallationStateHandle, name,
                            lambda *args, _name=name, **kwargs: pytest.fail(_name))
    first = _diagnose(handle)
    second = _diagnose(handle)
    assert first == second
    assert first["snapshot_is_lock_free"] is True
    assert first["non_authority_posture"] == doctor.NON_AUTHORITY_POSTURE
    assert not lock.exists()
    assert _tree(handle.root) == before


def test_doctor_has_no_execution_allocation_or_recovery_authority(tmp_path: Path) -> None:
    handle, _, _ = _publish(tmp_path)
    report = _diagnose(handle)
    posture = report["non_authority_posture"]
    assert all(posture.values())
    assert posture["doctor_does_not_execute"]
    assert posture["doctor_does_not_allocate"]
    assert posture["doctor_does_not_repair"]
    source = Path(doctor.__file__).read_text()
    for forbidden in ("execute_provisioning_intent", "exclusive_lock(", "durable_create(",
                      "durable_replace(", "ensure_directory(", "publish_production"):
        assert forbidden not in source
