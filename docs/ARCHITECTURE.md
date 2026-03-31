# SentientOS Final Architecture Overview

This document summarizes the integrated SentientOS command and runtime surfaces.
No new subsystem is introduced here; this is a stabilized view for engineers.

## Path A: Integrity envelope

- **Canonical vow digest** anchors immutable resources via
  `vow_digest.canonical_vow_digest()`.
- **Version consensus** compares local state with canonical digest constraints.
- **Drift reporting** is deterministic when invoked through diagnostics and ops
  verification surfaces.
- **Cycle gate** reports readiness state without hidden scheduling.

## Path B: Runtime + operations surfaces

- **Runtime CLI:** `python -m sentientos` (status/doctor/diff/ois/summary/trace).
- **Operations CLI:** `python -m sentientos.ops` (node, audit, lab, observatory/observability
  surface, verify, forge).
- **Service scripts:** `sentientosd`, `sentientos-chat`, `verify_audits`, and
  related command entrypoints from `pyproject.toml`.

## Determinism and approval gates

- Read-only surfaces remain non-mutating by design.
- Privileged UI/demo entrypoints (`dashboard`, `avatar-demo`) require privilege
  enforcement.
- Governance and contract checks remain explicit; no new autonomous behavior is
  implied by terminology.

## Current CLI architecture

The public argparse surface is:

```bash
python -m sentientos --help
python -m sentientos.ops --help
```

Typical workflows:

```bash
python -m sentientos status
python -m sentientos doctor
python -m sentientos ois overview
python -m sentientos.ops node health --json
python -m sentientos.ops observatory fleet --json
python -m sentientos.ops verify formal --json
```

## Historical command note

Older docs previously referenced `sentientos cycle`, `sentientos ssa ...`, and
`sentientos integrity`. Those are historical examples and are not part of the
current `python -m sentientos` command parser.
