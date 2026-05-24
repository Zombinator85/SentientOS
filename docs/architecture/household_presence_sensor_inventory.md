# Household Presence Sensor Surface Inventory

This layer is a **metadata-only inventory/reconciliation bridge** for Household Presence Layer v2.
It discovers and classifies existing SentientOS camera, vision, perception bus, host-inventory,
and embodiment surfaces without executing live adapters.

## Why this exists

- prevent duplicate implementation of already-existing perception/embodiment work
- produce deterministic do-not-duplicate integration posture
- map existing surfaces to Household Presence modalities

## Existing surfaces mapped

- `camera_daemon.py` → `camera_exterior` (reuse + wrap + defer runtime)
- `vision_tracker.py` → `camera_interior` (reuse + wrap)
- `face_emotion.py` → affect/perception input (non-authority, defer runtime)
- `scripts/perception/gaze_adapter.py` → `quest_operator_visor` embodied gaze
- `docs/PERCEPTION_BUS.md` + `docs/schemas/perception_bus.schema.json` → perception bus doc/schema contract
- `sentientos/host_inventory.py` → `usb_device_presence` / local device context inventory
- `sentientos/embodiment/embodiment_daemon.py` + `sentientos/embodiment/embodiment_digest.py` → embodiment surfaces
- `talkback_bridge.py` (if present) → speaker-adjacent surface requiring speaker gate and external-authority restraint

## Boundaries

- no camera/microphone/Wi-Fi/RF/Quest runtime invocation
- no live sensor execution
- no provider/network/subprocess/shell authority in library implementation
- affective surfaces remain non-authority
- speaker/talkback surfaces require explicit policy gate before any runtime output

## Future adapter sequence

1. stabilize existing camera/vision/perception bus docs and tests
2. add policy-gated exterior camera event bridge using existing camera/vision surfaces where possible
3. add deadzone/masking metadata and event redaction contract
4. add wildlife ledger adapter from policy-gated exterior event metadata
5. add protected care event summaries without raw bathroom retention
6. add host inventory / USB sensory device discovery bridge using existing host_inventory work
7. add roomfield/Wi-Fi RF stub only after inventory confirms available hardware path
8. add roomfield fusion
9. add Quest/operator visor read-only overlay if existing surfaces support it
10. add speaker policy gate before any talkback/runtime output
