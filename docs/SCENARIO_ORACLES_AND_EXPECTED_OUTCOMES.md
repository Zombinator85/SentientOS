# Scenario Oracles and Expected Outcomes

## Canonical baseline manifest

SentientOS records canonical simulation expectations in:

- `sentientos/simulation/federation_baseline_manifest.json`

The manifest is the stable inclusion policy and records:

- scenario names
- expected oracle outcomes
- key artifact expectations
- deterministic seed policy
- release-gating classification

## Scenario catalog

### `healthy_3node`
- Inputs: 3 nodes, no fault injection.
- Expected class: quorum admit, zero restricted nodes.
- Gate class: release-gating.

### `quorum_failure`
- Inputs: digest mismatch on `node-02`, trust-epoch mismatch on `node-03`.
- Expected class: high-impact quorum deny with restricted outcome class.
- Gate class: release-gating.

### `replay_storm`
- Inputs: bounded duplicate replay injections across all nodes.
- Expected class: deterministic duplicate count and stable quorum admit.
- Gate class: release-gating.

### `reanchor_continuation`
- Inputs: audit-chain break then explicit re-anchor on one node.
- Expected class: healthy continuation recognized.
- Gate class: release-gating.

### `pressure_local_safety`
- Inputs: pressure escalation + local safety override + control storm.
- Expected class: local safety dominates federated control admit path.
- Gate class: release-gating.

## Oracle envelope

Every run reports:

- `oracle.expected`
- `oracle.observed`
- `oracle.checks`
- `oracle.passed`

Current checks include:

- quorum admit/deny correctness
- restricted node counts when explicitly expected
- duplicate replay count for storm scenario
- re-anchor continuation recognition
- local safety dominant behavior under pressure

## Boundedness and auditability guarantees

- No hidden randomness; all behavior derives from scenario + seed.
- Every chaos condition is listed in run injection log.
- Every generated artifact is included in run manifest with SHA-256 hash.
- Baseline gate status is deterministic and written to `glow/simulation/baseline_report.json`.
