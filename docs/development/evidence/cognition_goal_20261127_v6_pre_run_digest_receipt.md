# Cognition campaign v6 pre-run digest receipt

Captured: 2026-11-27 (before either planned cycle was created)
Source commit: `c671f496de349030e52f1b1b88dbc5cbd6d82cd1`
Campaign: `rootless-history-campaign-20261127000100000027`

This receipt records the exact plan and readiness artifacts held in the private
experiment workspace. It provides repository-hosted custody of their digests;
it does not publish the history bundle or independently attest when the plan
was preregistered.

| Artifact | Workspace-relative path | SHA-256 |
|---|---|---|
| Campaign plan | `sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/campaign-plan.json` | `ad374b9630527e49a4adc0de308b6cd49409113eb7bb68693bf4ce1b4f4e7a31` |
| Private initial-history bundle (digest only; contents remain local) | `sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/initial-history-bundle.json` | `0f322512ea6983efae10ef416a8e07e6b1a7346e51b410c61aadff4cee8b52ac` |
| Cycle 27 answer-free owner/binder preflight | `sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/cycle27-owner-preflight.json` | `4927e9f7ca35e979c6ee5f20ba8c2fa783f5d789b88039589216ef9922f3bf09` |
| Cycle 27 current-source reconstruction verification | `sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/cycle27-owner-preflight-verification.json` | `e7e83e35aa1e9989dbb4a8891ad8bacfc79eb8f2a4a70dff62028ddbd3ccef57` |

The plan digest is `e515d86db444ed271712fde6c305f4815b0029a3c943ba5726907dd00894550c`.
Offline verification confirmed all 2,558 implementation pins and both model
identity recipes against current source. Both planned cycle directories were
absent at capture. The plan records `preregistration_timing_independently_attested=false`.
No model was loaded, no inference was performed, and learning and authority
remain unestablished. This receipt is custody evidence only; it is not a
preregistration attestation or evidence of learning.
