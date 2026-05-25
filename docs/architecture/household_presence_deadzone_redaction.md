# Household Presence Deadzone Redaction Contract

This capability defines a deterministic metadata-only redaction policy contract for camera/perception packets before storage, naming, profiling, evidence retention, child-visible output, speaker output, or disclosure.

## Scope and relationships
- Extends Household Presence Layer doctrine with zone-level privacy/safety enforcement.
- Reuses camera-event style metadata semantics from Household Presence Camera Event Bridge.
- Does **not** process image/video frames and does not access camera hardware.

## Zones and redaction
- `deadzone`: blocks storage, naming, profiling, evidence retention.
- `exterior_sensitive_zone`: requires redaction; if not applied, storage/naming/profile/evidence retention are blocked.
- `protected_care_zone`/`bathroom_child_safety_zone`: allow protected-care summary metadata, block raw retention.
- `adult_private_zone`: allows privacy-state awareness only, blocks explicit/general-memory profiling and naming.
- `wildlife_zone`: can allow non-human wildlife ledger candidates after redaction checks pass.
- `exterior_security_zone`: allows security metadata with default profile constraints.

## Evidence fields
The module exposes typed records:
- `HouseholdDeadzoneRedactionPolicy`
- `HouseholdRedactionRegion`
- `HouseholdRedactionMask`
- `HouseholdRedactionSource`
- `HouseholdRedactionEvidence`
- `HouseholdRedactionRequest`
- `HouseholdRedactionDecision`
- `HouseholdRedactionReport`
- `HouseholdDeadzoneRedactionResult`

## Boundaries
- face/affect/gaze metadata remains non-authority.
- speaker/talkback requests remain blocked (`speaker_gate_required`) until a separate speaker gate exists.
- external authority disclosure/contact remains blocked.

## Future adapter sequence
1. Bridge packets into this validator.
2. Add metadata-only zone configuration artifacts.
3. Add offline sample fixtures.
4. Add image-mask verifier stub (still no image processing).
5. Later add live adapter proof gates.
6. Later permit policy-gated live ingestion.
7. Keep speaker/talkback blocked until separate policy gate exists.

## CLI
`scripts/build_household_presence_deadzone_redaction.py`
- `build-default`
- `validate`
- `evaluate`
- `summarize`
