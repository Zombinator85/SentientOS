# Degraded Audit-Trust Propagation Model

## Overview

SentientOS now treats audit-trust as a first-class runtime state derived from
`verify_audit_chain` recovery semantics:

- `intact_trusted` (normal)
- `broken_preserved` (degraded)
- `reanchored_continuation` (restored through explicit re-anchor)

The runtime captures this state in append-only runtime artifacts and uses it in
a deterministic, rule-based control gate.

## Runtime Trust Artifacts

`sentientos.audit_trust_runtime` emits:

- `glow/runtime/audit_trust_state.json` (latest snapshot)
- `glow/runtime/audit_trust_transitions.jsonl` (append-only state transitions)
- `glow/runtime/audit_trust_decisions.jsonl` (append-only observations)

State transitions are keyed by a deterministic state signature across trust
fields, preserving explicit trust-boundary provenance.

## Propagation Points

Audit-trust is evaluated and propagated in:

- RuntimeGovernor (for every high-impact action admission)
- startup shell bootstrap (`sentientos/start.py`)
- boot ceremony (`sentientos/boot_ceremony.py`)
- GenesisForge expansion loop (`sentientos/genesis_forge.py`)
- runtime amendment apply path (`sentientos/runtime/shell.py`) via governor

Control-plane and federation control paths inherit trust enforcement through
RuntimeGovernor admission calls already used by:

- `control_plane/task_admission.py`
- `sentientos/daemons/pulse_federation.py`
- `daemon_manager.py`
- `sentientos/codex_healer.py`

## Deterministic Degraded Rules

RuntimeGovernor enforces explicit degraded-trust rules:

- `federated_control`: blocked (`degraded_audit_trust_federation_blocked`)
- `amendment_apply`: deferred/blocked (`degraded_audit_trust_amendment_deferred`)
- `control_plane_task`: denied pending escalation
  (`degraded_audit_trust_control_plane_escalation_required`)
- `repair_action`: non-restart repair actions denied pending escalation
  (`degraded_audit_trust_repair_escalation_required`)
- `restart_daemon`: allowed but marked tightened
  (`degraded_audit_trust_tightened`)

These are deterministic and explicit in governor decisions and observability
payloads.

## Restoration

Restoration remains explicit and external to runtime heuristics:

- trust only returns to non-degraded when audit-chain state becomes
  `reanchored_continuation` or `intact_trusted`.
- runtime never rewrites broken history and only records append-only
  observability artifacts.

## Remaining Blind Spots

- Some standalone scripts may execute high-impact actions without going through
  RuntimeGovernor admission helpers.
- Existing non-governed direct filesystem mutations remain outside trust-aware
  gating unless migrated to governor-mediated paths.
- GenesisForge currently defers all needs in degraded trust; finer-grained
  allowlisting for low-impact synthesis can be added later.
