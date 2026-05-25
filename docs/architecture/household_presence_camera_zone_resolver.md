# Household Presence Camera Zone Resolver

Metadata-only resolver that maps camera/perception event regions to configured camera zones using deterministic precedence.

- Consumes `household_presence_camera_zone_config` artifacts.
- Emits effective zone, matched zones, redaction requirement, downstream restrictions, warnings, and deterministic digest.
- Integrates with deadzone redaction contract and camera redaction pipeline by emitting compatible metadata-only zone posture.
- No media payload processing, no live camera execution, no adapter authority.
