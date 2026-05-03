# Phase 42 Perception Pulse Routing ExecPlan

1. Phase 41 quarantine state: five legacy modules remain quarantined with explicit risk markers and direct writes preserved.
2. Target shape: emit pulse-compatible `perception.legacy.<modality>` telemetry envelopes with authority=`none`, telemetry_only=true, privacy_class/raw_retention fields, and source provenance.
3. Files routed: sentientos/perception_api.py, screen_awareness.py, mic_bridge.py, vision_tracker.py, multimodal_tracker.py, feedback.py.
4. Helper strategy: add `build_pulse_compatible_perception_event`, `publish_perception_telemetry`, `maybe_publish_legacy_perception_event`, `emit_legacy_perception_telemetry`, and `perception_event_source_ref`; keep publisher dependency-injected no-op safe default.
5. Privacy/retention: every bridged event includes privacy_class and raw_retention metadata; sensitive/restricted used for risky streams.
6. Compatibility preserved: existing jsonl writes, memory append, and feedback actions are unchanged; telemetry emission is additive only.
7. Tests: architecture boundaries enforce bridge marker + API usage; phase tests assert event shape, risk flags, publisher injection, and public imports.
8. Unresolved risks: mic memory writes, feedback action side effects, vision biometric/emotion outputs, and legacy direct logs remain by design pending later migration phases.
