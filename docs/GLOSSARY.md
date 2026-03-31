# SentientOS Terminology Glossary

This glossary defines the normalized terminology for engineers, reviewers, and
contributors.

## Canonical terms

- **Privileged approval** — explicit operator-authorized approval for a
  privileged action. Legacy alias: `blessing`.
- **Governance authority** — approved reviewers/operators that decide policy,
  approvals, and escalations. Legacy alias: `council`.
- **Governance control plane** — the policy, audit, and gate surfaces that
  control runtime behavior. Legacy alias: `cathedral`.
- **Operator procedure** — a deterministic operational checklist or command
  sequence. Legacy alias: `ritual`.
- **Deterministic state-processing layer** — bounded runtime modules that
  process state and signals predictably. Legacy alias: `consciousness layer`.
- **Deterministic state-processing cycle** — one explicit execution cycle of
  state-processing modules. Legacy alias: `consciousness cycle`.
- **Activity telemetry** — event and status signal records emitted by runtime
  or operators. Legacy alias: `presence`.
- **Runtime identity contract** — identity and policy constraints stored in
  runtime artifacts. Legacy alias: `self-model`.
- **Observability surface** — status/index/reporting endpoints and dashboards.
  Legacy alias: `observatory`.
- **Governed change pipeline** — proposal, validation, and promotion pipeline
  for runtime changes. Legacy alias: `forge`.
- **Integrity contract artifact set (`/vow`)** — immutable integrity artifacts
  and digests.
- **State ledger artifact set (`/glow`)** — state and derived artifacts used by
  runtime/reporting.
- **Exploratory dialogue mode** — bounded exploratory dialogue subsystem.
  Legacy alias: `wild-dialogue`.

## Deprecation guidance

- On public surfaces, use canonical terms above.
- Legacy aliases are compatibility-only and should be labeled as legacy when
  mentioned.
- Internal archival/cultural docs may retain legacy wording without expanding
  that vocabulary into public interfaces.
