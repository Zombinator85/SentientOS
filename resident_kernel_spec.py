# SentientOS Resident Governance + Embodiment Kernel (Design Spec)
# Status: design-only, no implementation
#
# Constraints
# - No world model
# - No anthropomorphizing or narrative framing
# - No learning, belief accumulation, or ontology change
# - Must remain compatible with existing ledgers, Codex, federation guards
# - Must support future cameras/mics/screens without redesign
#
# Kernel State Surface (Always Hot)
#
# A. Governance / Identity Kernel
# | Variable | Represents | Update Authority | Invariant |
# | --- | --- | --- | --- |
# | identity_invariants | Canonical identity tuple (system_id, genesis_hash, operator_binding_id) | Governance Kernel Arbiter | Immutable after genesis; must match ledger genesis record |
# | doctrine_digest | Hash of active doctrine text bundle | Doctrine Digest Builder via Arbiter | Must reference a signed, ledgered doctrine artifact |
# | active_policy_pointer | Pointer to active policy set (policy_id, version) | Policy Engine via Arbiter | Must resolve to a ledgered policy set; version monotonic within a phase |
# | authority_flags | Current authority scope flags (operator_present, operator_verified, automated_ok) | Consent/Presence Gate via Arbiter | operator_verified implies operator_present; automated_ok requires active_policy_pointer |
# | system_phase | Phase enum (boot, ready, degraded, maintenance, shutdown) | Runtime Controller via Arbiter | Must be one of allowed enum; phase transitions follow policy rules |
# | posture_flags | Safety posture (normal, guarded, safe_brownout, quarantine) | Safety/Integrity Controller via Arbiter | safe_brownout or quarantine blocks non-essential outputs |
# | constraint_rejustify_deadline | Timestamp or counter for next required justification | Council Justifier via Arbiter | Must be >= last_justification_at; cadence must satisfy policy |
# | last_justification_at | Timestamp/counter of last completed justification | Council Justifier via Arbiter | Monotonic; cannot be in future relative to kernel clock |
# | federation_compat_digest | Read-only digest of federation rules/compat version | Federation Guard (read-only feed) | Must match federation registry; no local mutation |
#
# B. Embodiment State Vector
# | Variable | Represents | Update Authority | Invariant |
# | --- | --- | --- | --- |
# | sensor_presence_flags | Availability booleans per sensor class (camera, mic, tactile, etc.) | I/O Subsystem via Arbiter | Unknown sensors default false; must map to declared hardware registry |
# | sensor_health_flags | Health booleans per sensor class | I/O Subsystem via Arbiter | Health true requires presence true |
# | actuator_output_state | Output activity flags (screen_active, audio_active, haptics_active, etc.) | Output Controller via Arbiter | Output active requires system_phase in {ready, degraded} |
# | delta_signals | Event deltas (motion_detected, audio_threshold_crossed, etc.) | Signal Aggregator via Arbiter | Must be event-latched with monotonic seq counters |
# | kernel_seq | Global monotonic sequence counter | Arbiter | Strictly monotonic per update |
# | kernel_time | Monotonic time source (ticks) | Arbiter | Non-decreasing; independent of wall clock |
#
# Explicit Exclusions
# - Raw sensor streams
# - Semantic interpretation
# - Narrative meaning
#
# Update Semantics
# - Continuous updates: kernel_time, kernel_seq
# - Event-driven: delta_signals, sensor_presence_flags, sensor_health_flags, actuator_output_state
# - Governance updates: doctrine_digest, active_policy_pointer, authority_flags, system_phase, posture_flags,
#   constraint_rejustify_deadline, last_justification_at
# - SystemPhase gating:
#   - boot: only identity_invariants, doctrine_digest, active_policy_pointer, federation_compat_digest, kernel_time, kernel_seq
#   - ready: all updates allowed subject to policy
#   - degraded: actuator_output_state constrained; posture_flags may elevate
#   - maintenance: governance updates allowed; actuator_output_state limited to diagnostics
#   - shutdown: only kernel_time, kernel_seq, system_phase, posture_flags
# - Restart/rehydration:
#   - Load last committed checkpoint from cold ledger
#   - Validate hashes/digests before enabling ready phase
#   - If validation fails, enter safe_brownout and require operator verification
# - Corruption detection:
#   - If kernel_seq regression or digest mismatch, freeze updates and set posture_flags=quarantine
#
# Read/Write Boundaries
# - Readers: policy engine, safety controllers, I/O subsystems, presence gate, federation guard, audit logger
# - Update requests: I/O subsystem, policy engine, council justifier, runtime controller, safety controller
# - Write arbiter: Kernel Arbiter (single writer, validates invariants)
# - Cold logging on every update:
#   - kernel_seq, kernel_time, diff, updater_id, reason_code, invariant_check_result
#
# Failure and Recovery Semantics
# - Inconsistency criteria:
#   - kernel_seq regression
#   - invariant violation in any variable
#   - digest mismatch against ledgered artifacts
# - Rollback:
#   - Restore from last valid checkpoint; if unavailable, enter safe_brownout
# - Divergence detection:
#   - Periodic reconciliation of hot state hashes vs cold ledger snapshots
#   - Any mismatch triggers quarantine posture and operator notification
#
# Explicit Non-Goals
# - Belief store
# - Knowledge graph
# - Memory of experience
# - Autonomous planner substrate
# - Semantic world model
#
# Success Criteria
# - Provides current state without reconstruction
# - Change over time is detectable without tasks
# - Constraints remain justifiable and auditable
# - No new autonomy pathways
# - No weakening of existing invariants
