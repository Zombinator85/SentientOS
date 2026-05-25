# Household Presence Camera Redaction Pipeline

This offline deterministic metadata-only pipeline normalizes camera event metadata through the Household Camera Event Bridge, evaluates the Deadzone Redaction Contract, and emits downstream route packets.

- No image/video/audio processing is performed.
- No live adapter/hardware module execution is allowed.
- Child-visible, adult-private, protected-care, speaker, and external-authority boundaries are enforced as routing outcomes.

Stages: input_loaded -> camera_event_normalized -> redaction_contract_evaluated -> downstream_route_selected (+ operator_review_marked/blocked when required).

Routes include allowed metadata-only outputs (`live_awareness_only`, `redacted_ambient_journal`, `wildlife_ledger_candidate`, `security_event_metadata`, `nuisance_evidence_metadata`, `protected_care_summary`) and blocked outcomes (`blocked_by_deadzone`, `blocked_by_missing_redaction`, `blocked_by_adult_private_policy`, `blocked_by_child_visible_policy`, `blocked_by_speaker_boundary`, `blocked_by_external_authority_boundary`, `blocked_by_policy`).

Future live adapters must invoke this pipeline before any storage, evidence retention, naming/profiling, or externalized action.
