# Formal Specification + Model Checking Wing

This document describes the SentientOS formal verification wing added for bounded model checking of the highest-stakes state machines.

## Scope

The wing models existing behavior only. It does **not** redesign runtime architecture.

Modeled state machines:

1. RuntimeGovernor admission/arbitration
2. Audit-chain re-anchor + continuation trust boundary
3. Federated governance digest + quorum gating
4. Pulse trust-epoch compromise response

## What is modeled

Formal artifacts are under `formal/`:

- `formal/specs/*.tla` — explicit state-machine specs and invariants
- `formal/models/*.json` — bounded model configurations for deterministic checking
- `formal/README.md` — runbook and artifacts

Programmatic checker:

- `sentientos/formal_verification.py`
- `scripts/formal_check.py`
- `python -m sentientos.ops verify formal`

## Outputs

Each run emits deterministic artifacts under `glow/formal/`:

- `formal_check_summary.json` — pass/fail, per-spec property outcomes, explored state counts
- `formal_check_manifest.json` — exact checked spec/model files + SHA256 hashes

These outputs are machine-readable and suitable for operator review, CI checks, and incident bundles.

## Relationship to existing simulation/baseline suites

- **Formal checks**: bounded exhaustive checks over abstracted state machines and explicit invariants.
- **Simulation/baseline**: deterministic scenario execution over integrated federation/runtime behavior.

They are complementary:

- formal checking proves critical safety/gating properties over bounded state spaces;
- deterministic simulation validates end-to-end scenario behavior and release gates.

## Canonical CLI

```bash
python -m sentientos.ops verify formal
python -m sentientos.ops verify formal --json
python -m sentientos.ops verify formal --spec runtime_governor
```

## Known blind spots

- Bounded models only (not unbounded temporal proofs).
- Abstract transition relation mirrors critical logic but does not execute full runtime side effects.
- Peer/network nondeterminism is represented as bounded combinations, not full asynchronous protocols.
