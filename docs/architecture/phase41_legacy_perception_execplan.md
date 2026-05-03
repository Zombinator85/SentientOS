# Phase 41 Legacy Perception Remediation ExecPlan

## 1) Canonical perception path
`docs/PERCEPTION_BUS.md`, `scripts/perception/*_adapter.py`, and `sentientos/daemons/pulse_bus.py` define non-authoritative telemetry flow with explicit privacy gating.

## 2) Legacy perception files inspected
- `screen_awareness.py` (screen/OCR + JSONL)
- `mic_bridge.py` (microphone/STT + memory append + audio write)
- `vision_tracker.py` (face/emotion + JSONL)
- `multimodal_tracker.py` (fusion + per-person/environment JSONL)
- `feedback.py` (action cueing + action logs + notifications)

## 3) Selected files for remediation/quarantine
All five selected for **façade_route_now + quarantine annotation** to keep behavior while making risk explicit.

## 4) Façade/helper strategy
Introduce `sentientos.perception_api` with telemetry-only helper builders:
- `build_perception_event`
- `normalize_screen_observation`
- `normalize_audio_observation`
- `normalize_vision_observation`
- `normalize_multimodal_observation`
- `build_feedback_observation`
- `quarantine_legacy_perception_event`

Legacy modules route record shaping through these helpers while maintaining current outputs.

## 5) Privacy/retention risk handling
- Set explicit module markers for authority posture and retention default.
- Keep `RAW_RETENTION_DEFAULT = False` across all five modules.
- Explicitly surface exceptions: microphone memory writes and feedback action triggers.

## 6) Tests to add/update
- Architecture checks for required quarantine markers on known legacy modules.
- Architecture checks that `perception_api` does not import authority/execution modules or legacy root modules.
- Phase 41 helper shape tests and module compatibility import tests.

## 7) Deferred items
- Full migration from direct filesystem writes to canonical pulse bus sinks is deferred to avoid runtime behavior breakage and hardware coupling risk in a single wave.
- Mic memory append and feedback side-effects remain but are explicitly quarantined and listed as known violations.
