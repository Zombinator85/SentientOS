# Household Presence Camera Zone Configuration

Metadata-only zone configuration for household camera/perception sources. Declares zone classes, region shapes, precedence, and staleness/review policy before any live adapter or media processing.

- No image/video/audio processing.
- Integrates with deadzone redaction and camera redaction pipeline through metadata compatibility helpers.
- Precedence: deadzone > exterior_sensitive > adult_private > protected_care/bathroom > child_safety > exterior_security > wildlife > exterior_ambient > home > unknown.
- `speaker_output_allowed` and `external_disclosure_allowed` default false and true values block validation.
