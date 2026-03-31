# Public Language Bridge (Engineering ↔ Internal Codename)

This glossary is the canonical translation anchor for public-facing SentientOS
documentation.

- **Layer 1 (public):** lead with engineering terms.
- **Layer 2 (bridge):** map to internal codenames for continuity.
- **Layer 3 (internal):** symbolic/cultural language remains valid in internal,
  doctrine, and culture documents.

For deterministic mappings used by tooling, see
`sentientos/public_language_map.py`.

## Canonical term map

| Public engineering term | Internal codename / legacy term | Why this mapping exists |
| --- | --- | --- |
| deterministic state-processing layer | consciousness layer | Clarifies this is bounded processing, not agency. |
| activity telemetry | presence | Runtime logs events and signals; it does not imply awareness. |
| governance control plane | cathedral | The system enforces governance and audit controls. |
| integrity contract | vow | `vow` remains the internal namespace for immutable integrity artifacts. |
| state ledger | glow | `glow` remains the internal namespace for persisted state artifacts. |
| pulse event stream | pulse | `pulse` is a stable internal channel name for event records. |
| background worker | daemon | `daemon` is already standard engineering vocabulary. |
| approval body / governance authority | council | Public docs should emphasize authority and review function. |
| privileged approval | blessing | Approval is procedural and binary in runtime gates. |
| operator procedure | ritual | Use procedural wording on public surfaces. |
| runtime identity contract | self-model | Anchors explicit runtime identity data and constraints. |
| observability surface | observatory | Public docs should describe status/index/report functions. |
| change pipeline | forge | Public docs should describe queue/gate/replay/change operations. |
| bounded automation | autonomy | Clarifies operator-scoped automation without self-generated goals. |
| multi-node coordination | federation | Clarifies peer synchronization and control-plane behavior. |
| telemetry reliability score | trust | Clarifies scoring/consensus reliability, not social meaning. |

## Public writing rule

When an internal codename appears in public-facing docs, dual-label it on first
use:

- `public engineering term (internal codename: X)`

Example:

- `governance control plane (internal codename: cathedral)`
