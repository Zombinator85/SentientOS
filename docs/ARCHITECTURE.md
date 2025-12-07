# SentientOS Final Architecture Overview

This document summarizes the integrated SentientOS surfaces exposed by the
orchestrator and CLI. No new subsystems are introduced; the goal is to present
the stabilized, deterministic pathways for developers.

## Path A: Integrity envelope

- **Canonical vow digest** anchors immutable resources via
  `vow_digest.canonical_vow_digest()`.
- **Version consensus** compares local state with the canonical digest using
  `version_consensus.VersionConsensus`.
- **Drift reporting** remains deterministic and self-referential when invoked
  via `compute_system_diagnostics()`.
- **Cycle gate** reports readiness state without scheduling work.

## Path B: SSA Agent stages (0–6)

- **Stage 0–2**: deterministic selector routing and dry-run planning.
- **Stage 3–4**: screenshot planning and optional OracleRelay execution gated by
  explicit approval.
- **Stage 5–6**: review bundle assembly and export guarded by approval flags and
  redaction routines.

## Determinism and approval gates

- No background scheduling or persistence occurs unless an approval flag is
  provided.
- CLI commands that modify or emit sensitive artifacts require `--approve`.
- Orchestrator methods return deterministic status payloads when approval is
  withheld.

## CLI architecture

The `sentientos` CLI is argparse-based and prints JSON for every command. The
entry point defers to `SentientOrchestrator` and helper utilities for profile
loading, system diagnostics, and redacted bundle summaries.

```
sentientos cycle
sentientos ssa dry-run --profile PROFILE.json
sentientos ssa execute --profile PROFILE.json --approve
sentientos ssa prefill-827 --profile PROFILE.json --approve
sentientos ssa review --bundle BUNDLE.json
sentientos integrity
sentientos version
```

## Orchestrator flow

1. Optional profile + approval flag instantiate `SentientOrchestrator`.
2. Consciousness cycles call directly into `run_consciousness_cycle` for a
   deterministic report.
3. SSA commands delegate to `SSADisabilityAgent` for dry-runs, execution,
   prefill, and review bundle assembly.
4. Approval gates block privileged actions and exports while still returning
   deterministic payloads.
5. CLI commands surface the same flows for developer-facing usage.
