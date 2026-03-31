# SentientOS Usage Guide

This guide documents the **current** public CLI surface.

SentientOS exposes two primary command surfaces:

1. `python -m sentientos` for safe runtime introspection and privileged UI entrypoints.
2. `python -m sentientos.ops` for operations workflows (node, audit, federation lab, observability, verification).

For terminology mapping between public engineering language and internal
codenames, see [PUBLIC_LANGUAGE_BRIDGE.md](PUBLIC_LANGUAGE_BRIDGE.md).

## 1) Core runtime CLI (`python -m sentientos`)

Inspect available commands:

```bash
python -m sentientos --help
```

Current command groups:

- Read-only/safe commands:
  - `status`
  - `doctor`
  - `diff`
  - `ois`
  - `summary`
  - `trace`
  - `consent`
  - `system`
- Privileged commands:
  - `dashboard`
  - `avatar-demo`

Examples:

```bash
python -m sentientos status
python -m sentientos doctor
python -m sentientos ois overview
python -m sentientos diff
python -m sentientos summary
python -m sentientos system map
```

## 2) Unified operations CLI (`python -m sentientos.ops`)

Inspect available domains:

```bash
python -m sentientos.ops --help
```

Current domains:

- `node`
- `constitution`
- `forge`
- `incident`
- `audit`
- `simulate`
- `lab`
- `observatory` (public concept: observability)
- `verify`

Examples:

```bash
python -m sentientos.ops node health --json
python -m sentientos.ops constitution verify --json
python -m sentientos.ops audit verify -- --strict
python -m sentientos.ops lab federation --scenario healthy_3node --json
python -m sentientos.ops observatory fleet --json
python -m sentientos.ops verify formal --json
```

## 3) Service entrypoints

Installed script entrypoints include:

- `sentientosd` (runtime daemon)
- `sentientos-chat` (chat service)
- `sentientos-updater` (git update helper)
- `verify_audits` (audit-chain verification)
- `audit_immutability_verifier` (immutability verifier)

Examples:

```bash
sentientosd
sentientos-chat
verify_audits --strict
```

## 4) Historical command note (drift correction)

Older docs referenced orchestrator commands such as:

- `sentientos cycle`
- `sentientos ssa ...`
- `sentientos integrity`
- `sentientos version`

Those are **historical** and are not part of the current argparse surface for
`python -m sentientos`.

Use:

- `python -m sentientos --version` for version reporting.
- `python -m sentientos` + `python -m sentientos.ops` commands listed above for
  current runtime and operations workflows.
