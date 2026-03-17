# Node Truth Artifacts

SentientOS WAN/live federation nodes now emit a default truth artifact at:

- `glow/lab/node_truth_artifacts.json`

This artifact is intentionally bounded, deterministic, and append-only-friendly (derived from existing node state, without rewriting history).

## Default evidence dimensions emitted per node

- `quorum_state` (decision + pending posture)
- `digest_state` (governance digest + peer compatibility observations)
- `epoch_state` (active/retired/revoked posture)
- `reanchor_state` (history state + checkpoint + continuation)
- `fairness_state` (lightweight starvation/noisy-subject summaries)
- `health_state` (cluster-facing health posture)
- `replay_state` (lightweight replay/provenance posture)

## Replay posture states

`replay_state.state` uses bounded categories:

- `no_replay_evidence_requested`
- `replay_compatible_evidence`
- `replay_confirmed`
- `replay_contradicted`
- `replay_missing_but_expected`

This allows the WAN truth oracle to distinguish “not requested” from “expected but missing”, without forcing full replay in every run.

## Where these artifacts are surfaced

- per-node runtime roots (`glow/lab/node_truth_artifacts.json`)
- WAN run-level manifest (`glow/lab/wan/<run_id>/node_truth_manifest.json`)
- truth-oracle evidence manifest (`wan_truth/evidence_manifest.json`)
- operator/incident surfaces (source listing + incident bundle inclusion)
