from __future__ import annotations

import ast
from pathlib import Path

from sentientos.embodiment_fusion import (
    build_embodiment_snapshot,
    embodiment_snapshot_source_ref,
    fuse_perception_events,
    group_perception_events_by_correlation,
)
from sentientos.perception_api import build_pulse_compatible_perception_event


def _event(modality: str, ts: float, **kwargs: object) -> dict[str, object]:
    obs = {"timestamp": ts, "sample": modality, "correlation_id": kwargs.pop("corr", "c-1")}
    obs.update(kwargs.pop("obs", {}))
    return build_pulse_compatible_perception_event(
        modality,
        obs,
        source_module=f"{modality}_module",
        privacy_class=str(kwargs.pop("privacy_class", "sensitive")),
        raw_retention=bool(kwargs.pop("raw_retention", False)),
        can_trigger_actions=bool(kwargs.pop("can_trigger_actions", False)),
        can_write_memory=bool(kwargs.pop("can_write_memory", False)),
    )


def test_phase43_fusion_across_modalities_and_provenance() -> None:
    events = [
        _event("screen", 1.0, obs={"text": "hello"}),
        _event("audio", 2.0, can_write_memory=True),
        _event("vision", 3.0, privacy_class="restricted"),
        _event("multimodal", 4.0),
        _event("feedback", 5.0, can_trigger_actions=True),
    ]
    snapshot = fuse_perception_events(events, created_at=99.0)
    assert snapshot["schema_version"] == "embodiment.snapshot.v1"
    assert snapshot["modalities_present"] == ["audio", "feedback", "multimodal", "screen", "vision"]
    assert snapshot["correlation_id"] == "c-1"
    assert len(snapshot["source_event_refs"]) == 5
    assert snapshot["source_modules"]
    assert snapshot["privacy_classes"] == ["restricted", "sensitive"]


def test_phase43_degrades_when_modalities_missing() -> None:
    snapshot = build_embodiment_snapshot([_event("screen", 1.0)], created_at=1.0)
    posture = snapshot["confidence_posture"]
    assert posture["completeness"] == "partial"
    assert set(posture["missing_core_modalities"]) == {"audio", "feedback", "multimodal", "vision"}


def test_phase43_permissions_do_not_escalate() -> None:
    snapshot = build_embodiment_snapshot([
        _event("audio", 1.0, can_write_memory=True),
        _event("feedback", 2.0, can_trigger_actions=True),
    ])
    assert snapshot["risk_flags"]["can_write_memory"] is True
    assert snapshot["risk_flags"]["can_trigger_actions"] is True
    assert snapshot["does_not_write_memory"] is True
    assert snapshot["does_not_trigger_feedback"] is True
    assert snapshot["decision_power"] == "none"


def test_phase43_deterministic_for_deterministic_input() -> None:
    events = [_event("screen", 1.0), _event("audio", 2.0)]
    a = build_embodiment_snapshot(events, created_at=123.0)
    b = build_embodiment_snapshot(events, created_at=123.0)
    assert a == b
    assert embodiment_snapshot_source_ref(events[0]) == embodiment_snapshot_source_ref(events[0])


def test_phase43_group_by_correlation_and_import_purity() -> None:
    grouped = group_perception_events_by_correlation([
        _event("screen", 1.0, corr="x"),
        _event("audio", 2.0, corr="x"),
        _event("vision", 3.0, corr="y"),
    ])
    assert sorted(grouped.keys()) == ["x", "y"]

    module_path = Path("sentientos/embodiment_fusion.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    banned = {"control_plane", "task_admission", "task_executor", "sentientos.authority_surface", "feedback", "screen_awareness", "vision_tracker", "mic_bridge", "multimodal_tracker"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == b or alias.name.startswith(f"{b}.") for b in banned)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not any(module == b or module.startswith(f"{b}.") for b in banned)
