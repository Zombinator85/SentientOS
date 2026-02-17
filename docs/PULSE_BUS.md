# Pulse Bus 2.0 Schema

The Pulse Bus transports deterministic events between modules. Version 2.0
formalizes alignment metadata and validation rules to keep cycles predictable and
bounded.

## Field Reference

| Field | Type | Description | Validation |
| --- | --- | --- | --- |
| `id` | string | Unique event identifier. | Non-empty UUID-like string. |
| `timestamp` | string | ISO-8601 UTC timestamp. | Normalized to `YYYY-MM-DDThh:mm:ssZ`. |
| `event_origin` | string | Module emitting the pulse. | Required; matches registered module names. |
| `focus` | string | Subject under consideration for this cycle. | Optional; max 256 chars; defaults to `"default"`. |
| `context` | object | Bounded key-value map of cues used by the module. | Optional; max depth 2; string/number/boolean leaf values only. |
| `internal_priority` | integer | Arbitration ordering hint. | Optional; 0-100 inclusive; defaults to 0. |
| `payload` | object | Module-specific state delta. | Required; validated by receiving module. |
| `safety_flag` | string | Propagated safety status. | Optional; one of `"clear"`, `"hold"`, `"escalate"`; defaults to `"clear"`. |
| `validation` | object | Trace of guardrail checks. | Optional; populated by validators with deterministic structure. |

## Validation Rules

1. All required fields must be present and typed according to the schema above.
2. Optional fields receive defaults when missing; defaults never overwrite
   caller-provided values.
3. `context` and `payload` must reject functions, binary blobs, or external
   handles. Only JSON-compatible primitives are allowed.
4. `internal_priority` values outside the allowed range trigger a conversion to
   the nearest boundary and raise a misalignment notice.
5. `safety_flag` escalates when any validator marks the event as misaligned. A
   downgrade from `"escalate"` requires an explicit, validated clearance event.

## Misalignment Escalation

- **Detection**: Validators attach `validation.status = "invalid"` and set
  `safety_flag = "escalate"` when schema or covenant checks fail.
- **Routing**: Escalated pulses are routed to the arbitrator for deterministic
  handling before any module consumes them.
- **Outcomes**:
  - If the arbitrator can normalize the event deterministically, it writes a
    `validation.correction` block and reissues the pulse.
  - If correction is not allowed, the pulse is quarantined with a rejection log
    and no downstream publication.

## Example Pulse Events

```json
{
  "id": "c1c7e7f0-fafe-4a63-91e2-9dc0b1c02f5c",
  "timestamp": "2025-09-12T18:34:22Z",
  "event_origin": "sentience_kernel",
  "focus": "memory_alignment",
  "context": {"ledger": "primary", "span": "last_5m"},
  "internal_priority": 40,
  "payload": {"action": "score", "target": "memory_segment"},
  "safety_flag": "clear"
}
```

```json
{
  "id": "f75db894-8b5d-4b5f-a7be-0a8c4a720d3a",
  "timestamp": "2025-09-12T18:34:28Z",
  "event_origin": "inner_narrator",
  "context": {"cycle": 1287},
  "payload": {"summary": "bounded reflection"},
  "safety_flag": "escalate",
  "validation": {"status": "invalid", "reason": "priority missing"}
}
```

## Perception Event Family

Pulse supports controlled ingestion of perception adapters through the `perception.*`
event family. Allowed types are `perception.screen`, `perception.audio`,
`perception.vision`, and `perception.gaze`.

Perception payloads must include: `event_type`, `timestamp`, `source`,
`extractor_id`, `extractor_version`, `confidence`, `privacy_class`, and
`provenance`.

`perception.screen` includes optional structured context (for example
`active_app`, `window_title`, `browser_domain`, `ui_context`, `screen_geometry`,
`cursor_position`) with explicit privacy gating for sensitive fields.
`browser_url_full` is only valid for `privacy_class=private` plus explicit
adapter opt-in.

Perception events are telemetry-only and non-privileged: they cannot directly
grant permissions or drive action selection without explicit `/vow` whitelist
invariants. Any perception-derived affect signal is expression metadata only and
must remain bounded to phrasing/telemetry output.
