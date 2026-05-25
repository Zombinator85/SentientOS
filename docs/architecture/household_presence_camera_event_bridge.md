# Household Presence Camera Event Bridge

Deterministic offline metadata bridge from camera/vision/perception event metadata into Household Presence event packets.

- Metadata-only: does not import/execute live camera modules.
- Applies policy for zone, modality, entity class, memory class, room composition, retention, and authority boundaries.
- Deadzone/redaction fields are explicit (`deadzone_match`, `redaction_required`, `redaction_applied`, `storage_allowed`).
- Face/affect/gaze metadata is non-authority only.
- Speaker/talkback remains gated; bridge emits metadata only.
- External authority contact remains blocked by default.

Future adapters may feed this bridge, but this module is intentionally offline and deterministic.
