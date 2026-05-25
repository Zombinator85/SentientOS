from __future__ import annotations

import json
from pathlib import Path

from sentientos.household_presence_camera_redaction_pipeline import build_default_policy, evaluate_pipeline, validate_policy

FIXTURES = Path("tests/fixtures/household_presence_camera_events")


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_policy_validates() -> None:
    assert validate_policy(build_default_policy())["ok"]


def test_required_routes() -> None:
    assert evaluate_pipeline(_fixture("wildlife_squirrel_fat_boi.json")).decision.route == "wildlife_ledger_candidate"
    assert evaluate_pipeline(_fixture("exterior_person_deadzone.json")).decision.route == "blocked_by_deadzone"
    assert evaluate_pipeline(_fixture("vehicle_parking_lot.json")).decision.route == "security_event_metadata"
    assert evaluate_pipeline(_fixture("nuisance_yelling_event.json")).decision.route == "nuisance_evidence_metadata"
    assert evaluate_pipeline(_fixture("protected_care_bath_summary.json")).decision.route == "protected_care_summary"
    assert evaluate_pipeline(_fixture("adult_private_context_event.json")).decision.route == "blocked_by_adult_private_policy"
    assert evaluate_pipeline(_fixture("speaker_request_blocked.json")).decision.route == "blocked_by_speaker_boundary"
    assert evaluate_pipeline(_fixture("external_authority_request_blocked.json")).decision.route == "blocked_by_external_authority_boundary"


def test_missing_redaction_block() -> None:
    payload = _fixture("exterior_person_redacted.json")
    payload["metadata"]["redaction_applied"] = False
    assert evaluate_pipeline(payload).decision.route == "blocked_by_missing_redaction"


def test_deterministic_digest() -> None:
    a = evaluate_pipeline(_fixture("face_affect_gaze_annotation.json")).packet.digest
    b = evaluate_pipeline(_fixture("face_affect_gaze_annotation.json")).packet.digest
    assert a == b
