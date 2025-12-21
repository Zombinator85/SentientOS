# SentientOS Governance Doctrine (Offline, Single-Operator)

SentientOS is prepared for offline, single-operator deployments where
determinism and auditability outrank throughput. This doctrine locks in the
governance invariants that future changes must respect. Friction is
intentional.

## Authoritative Invariants

- **Upgrade-path enforcement**
  - Any change touching admission, authorization, advisory gates, snapshot
    canonicalization, pulse boundaries, determinism or daemon control is
    governance-critical.
  - Such changes must update `docs/governance_claims_checklist.md`, pass CI,
    and carry an explicit operator acknowledgement (use
    `--ack-governance-drift` with `scripts/check_governance_drift.py`).
  - Cryptographic attestation is not required; deliberate operator friction is.
- **Time determinism**
  - Wall-clock time is not an authority input. No decision, authorization, or
    admission branch depends on timestamps. Timestamps remain diagnostic only.
  - Replay ignores timestamp drift; time is observational, never causal.
- **Daemon authority**
  - `sentientosd` is governed, not a convenience wrapper. Running via CLI-only
    paths is allowed but does not bypass governance assertions.
  - The daemon introduces no new intent, goals, or side effects beyond those a
    manual operator can trigger.
- **Operator identity**
  - Exactly one operator is assumed. Shared or multi-operator authority is out
    of scope until doctrine changes explicitly.
- **No background intent**
  - The runtime does not mint goals, tasks, or intent without operator
    initiation. Background processes are limited to maintenance (audit,
    integrity, verification).
- **Configuration immutability**
  - Configuration is read once at startup. Runtime services treat it as
    immutable; no subsystem writes back to config files while running.
  - Configuration changes require explicit amendment flows and a restart.
- **Determinism seed centralization**
  - `sentientos.determinism.seed_everything` is the single entry point for
    seeding randomness. All randomness sources derive from the unified seed.

## Self-Update Approval Model

- Offline deployments rely on operator/owner trust, not remote attestations or
  cryptographic approvals.
- The AmendmentReviewBoard validates integrity and policy, but final approval
  is environmental (the operator choosing to run the update).
- Use `--ack-governance-drift` when invoking governance tooling to document the
  operator decision for self-updates. Introducing additional approval
  infrastructure is intentionally deferred.

## Failure Mode Classification

- **Hard aborts:** integrity violations, provenance mismatches, canonicalization
  divergence. Expected to stop execution.
- **Soft aborts:** optional extensions that fail validation or exceed bounds;
  safe to skip while preserving determinism.
- **Deferred failures:** logged non-blocking issues (e.g., optional connectors)
  that must be reviewed before future runs. Fail-fast is the default posture;
  slow degradation is a regression.

## Shutdown and Crash Semantics

- Snapshots are written atomically (temp → rename); partial artifacts are
  discarded.
- Logs are diagnostic, not authoritative.
- Restarts assume a clean slate; integrity checks fail closed on inconsistency
  rather than attempting recovery from partial state.

## Daemon Execution Model

- Execution is single-threaded. No async worker pools or background tasks may be
  added without doctrine change.
- Subprocess calls must remain blocking and serialized. Introducing concurrency
  is a governance change, not a performance tweak.

## Startup Validation

- Startup validates that model paths exist (cross-platform defaults are used
  when absent) and warns when optional features lack dependencies.
- Missing assets emit warnings rather than enabling partial execution. Hard
  failures are reserved for integrity violations.

## Explicit Non-Goals (Out of Scope)

- Multi-tenant or multi-operator control
- Continuous or online learning
- Autonomous goal generation or background intent
- Real-time autonomous actuation
- High-availability clustering
- Background task automation without operator action

These boundaries are defensive. Any attempt to expand them is governance work
that must pass through the checklist, CI, and explicit operator acknowledgement.
