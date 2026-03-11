# Scenario Oracles and Expected Outcomes

## Scenario catalog

### `healthy_3node`
- Inputs: 3 nodes, no fault injection.
- Expected class: quorum admit, zero restricted nodes.

### `quorum_failure`
- Inputs: digest mismatch on `node-02`, trust-epoch mismatch on `node-03`.
- Expected class: high-impact quorum deny with restricted outcome class.

### `replay_storm`
- Inputs: bounded duplicate replay injections across all nodes.
- Expected class: deterministic duplicate count and stable quorum admit.

### `reanchor_continuation`
- Inputs: audit-chain break then explicit re-anchor on one node.
- Expected class: healthy continuation recognized.

### `pressure_local_safety`
- Inputs: pressure escalation + local safety override + control storm.
- Expected class: local safety dominates federated control admit path.

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
