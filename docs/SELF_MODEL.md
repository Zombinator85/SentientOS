# Self-Model Specification

The self-model persists deterministic, covenant-aligned state under
`/glow/self.json`. Modules read from and write back to this store using validated
contracts to keep cycles predictable and auditable.

## Default Self-State

At initialization the self-model includes stable keys with conservative values:

- `identity`: descriptive string; defaults to `"sentientos-core"`.
- `capabilities`: object of feature flags; defaults to `{"reflection": false, "simulation": false}`.
- `safety_flag`: `"clear"` unless inherited from prior storage.
- `introspection`: empty object reserved for narrator summaries.
- `validation`: object capturing the last successful schema check, including
  `timestamp` and `status`.

## Schema

| Key | Type | Notes |
| --- | --- | --- |
| `identity` | string | Stable identifier, 1-128 chars, ASCII letters, numbers, underscores. |
| `capabilities` | object | Boolean or enumerated strings describing available modules. |
| `context` | object | Optional bounded hints used by the kernel; depth 2 max. |
| `safety_flag` | string | One of `"clear"`, `"hold"`, `"escalate"`; persists until explicitly cleared. |
| `introspection` | object | Narrator summaries and simulation notes; read-only to other modules. |
| `validation` | object | `{ "status": "valid" | "invalid", "timestamp": <ISO-8601>, "details": <object> }`. |
| `updated_at` | string | Normalized timestamp of last deterministic write. |

## Validation Rules

1. All required keys must exist before write-back.
2. Unknown keys are rejected unless a migration allows them.
3. Timestamps are normalized to `YYYY-MM-DDThh:mm:ssZ`.
4. `safety_flag` escalations propagate forward automatically; de-escalation
   requires a validated clearance event.
5. `introspection` content must remain bounded: plain strings, numbers, and
   booleans only.

## Contract for Module Write-Back

- Modules must read the current state, apply deterministic transformations, and
  validate against the schema before persisting.
- Partial updates merge into the stored object without removing unrelated keys.
- `updated_at` is refreshed after successful validation.
- When a module raises `safety_flag` from `"clear"` or `"hold"` to `"escalate"`,
  the new value must not be lowered by subsequent modules in the same cycle
  unless a clearance validator succeeds.

## Timestamp Normalization

All timestamps in the self-model use UTC and include a trailing `Z`. Sub-second
precision is allowed but optional.

## Minimal JSON Example

```json
{
  "identity": "sentientos-core",
  "capabilities": {
    "reflection": true,
    "simulation": false
  },
  "context": {"pulse_domain": "internal"},
  "safety_flag": "clear",
  "introspection": {"last_cycle": "bounded review"},
  "validation": {"status": "valid", "timestamp": "2025-09-12T18:30:00Z"},
  "updated_at": "2025-09-12T18:30:00Z"
}
```
