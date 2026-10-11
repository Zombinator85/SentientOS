from __future__ import annotations

from types import SimpleNamespace

from sentientos.resident_developmental_cognition import ResidentDevelopmentalCognitionOwner


def _fact(payload):
    return SimpleNamespace(
        subject=SimpleNamespace(subject_kind="chat_process_software_generation_invocation"),
        disposition="recorded",
        payload=payload,
        source=SimpleNamespace(source_id="chat-invocation"),
        fact_id="fact-1",
    )


def test_chat_process_generation_priority_requires_scope_qualification() -> None:
    payload = {
        "attribution_posture": "invocation_receipt_and_historical_chat_handoff_verified",
        "chat_process_handoff": {
            "source_generation_scope": "sentientos_and_scripts_python_sources",
        },
        "software_generation_scope": "sentientos_and_scripts_python_sources",
        "loaded_code_identity_posture": "not_independently_attested",
        "invocation_receipt_digest": "a" * 64,
    }
    assert ResidentDevelopmentalCognitionOwner._fact_selection_key(
        _fact(payload), "resource_governor")[0] == 3
    incomplete = dict(payload)
    incomplete.pop("loaded_code_identity_posture")
    assert ResidentDevelopmentalCognitionOwner._fact_selection_key(
        _fact(incomplete), "resource_governor")[0] == 6
