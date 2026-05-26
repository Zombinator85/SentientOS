# Household Presence Camera Host Inventory Bridge

This bridge exists to deterministically convert **host inventory metadata** into household camera source candidates for readiness and dry-run planning, without opening hardware.

It reuses host-inventory style metadata from `sentientos/host_inventory.py` and aligns with sensor inventory, live adapter readiness, and dry-run adapter contracts.

## Model
- Classifies devices into camera candidates vs blocked/non-camera classes.
- Emits candidate metadata only.
- Requires operator confirmation, zone binding, and policy-chain path before any future live stub.
- Keeps `live_hardware_allowed=false`, `raw_media_allowed=false`, `speaker_output_allowed=false`, and `external_disclosure_allowed=false` by default.

## Why no hardware discovery
The module is metadata-only by design, so it does not probe `/dev/video`, call media stacks, open cameras, or perform network fetches.

## Future live sequence
1. host inventory bridge metadata
2. operator review
3. zone config binding
4. dry-run session
5. live adapter stub with hardware disabled by default
6. policy-gated live adapter only after explicit confirmation
