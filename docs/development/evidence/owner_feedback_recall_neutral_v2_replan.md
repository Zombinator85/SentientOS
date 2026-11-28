# Owner-feedback recall neutral-query v2 replan

Captured: 2026-11-28
Campaign: `rootless-history-campaign-80267c0fbd908e310860`
Plan digest: `5f5a9a621320a30e40a68746dfe6555861bc28894b96651eca5b7c286424fc41`
Task family: `rootless_integer_affine_transfer_novel_range_v8`
Protocol: `owner-cognition-feedback-cross-cycle-recall-v2`
Protocol digest: `eadf7e24dea6c21b7017464b6ccc46ed672fd2d99c65db7e158c26623cea27ac`

## CPU-only implementation correction

The first replan attempt (plan digest
`4e2f9b5699ee739d67435d5cda054896c2341a62c3421845422d5f93e3ef10d9`)
never launched. Its owner-preflight rejected the planned model identity because
the preflight helper hardcoded 32 GPU layers while the plan bound 24. The helper
now takes the layer count from the plan's verified identity recipe and verifies
current source pins for plan schemas v8 through v15. The abandoned cycle roots
were checked and do not exist. Its identifiers and seeds were discarded.

The replacement binds fresh cycle identifiers and task/backend seeds. Its plan
was created and verified offline. Verification matched all 2,558 implementation
pins (digest
`239e19195373b7b1c5bc64cc13948ebbeebfdf32d3f0dc2c2c8fe14ef5ce7e1f`) and
both model identity recipes. The model manifest was hash-checked; no model was
loaded. The initial history boundary is
`bedca4464283f06e3180850ec144dd65ec79c92fc1a4149b4543a55b34575956`.
Its private bundle contains 22 files and 264,302 bytes.

Cycle 0's reconstructed CPU owner/binder preflight passed the independent
report verifier. It selected a 24-example accumulated strategy history and
derived 12 held-out transfer probes with no exact historical input overlap.
The bound prompt was 24,823 characters, below the 28,672-character limit.
This is preparation and source/context verification; it is not model
performance evidence. Cycle 1 cannot be preflighted until cycle 0 has completed
and its append-only history, runtime-admission, and cognition-recovery chains
verify.

## Private artifact custody

Artifacts remain in the mode-0700 experiment directory; listed files are mode
0600. The private contents are not copied into the repository.

| Artifact | Workspace-relative path | SHA-256 |
|---|---|---|
| Current-source campaign plan | `sentientos-data/rootless-experimental/owner-feedback-recall-campaign-20261128-neutral-v2-12x12-repinned/campaign-plan.json` | `bd711baefa64d5b3fb7c165a9197a9486816de146db665526343c2482cb09fdc` |
| Plan verification | `sentientos-data/rootless-experimental/owner-feedback-recall-campaign-20261128-neutral-v2-12x12-repinned/campaign-plan-verification.json` | `e9918fe86d9f7099d35db821e0e78be1ef41817dd017ec3f0c022f28a1e24249` |
| Private initial-history bundle | `sentientos-data/rootless-experimental/owner-feedback-recall-campaign-20261128-neutral-v2-12x12-repinned/initial-history-bundle.json` | `529d69e81165a360afaa16f9fb77cba908fae17c20778c608619f572a58d3108` |
| Cycle 0 CPU owner/preflight report | `sentientos-data/rootless-experimental/owner-feedback-recall-campaign-20261128-neutral-v2-12x12-repinned/cycle0-owner-preflight.json` | `0071312ecabb29a669fea9a0c81f7af7f40896e4435441d24681cdb9fcc6a8c3` |
| Independent preflight verification | `sentientos-data/rootless-experimental/owner-feedback-recall-campaign-20261128-neutral-v2-12x12-repinned/cycle0-owner-preflight-verification.json` | `a98325acf380464a63b267bdf74116e72811971e97211173e1087e3b2427904b` |
| Prepared v3 run card | `sentientos-data/rootless-experimental/owner-feedback-recall-campaign-20261128-neutral-v2-12x12-repinned/campaign-run-card-neutral-v2-12x12-current.json` | `a303ad4db17bb3a8cd3e2f0f4f30cd0f11ba9ae4b7fcb494f70a9175c3041837` |
| Offline run-card verification | `sentientos-data/rootless-experimental/owner-feedback-recall-campaign-20261128-neutral-v2-12x12-repinned/campaign-run-card-verification.json` | `c2fc967ced3537fa74bd48a8de552bea943613a6a6f58df13371e42a0733f8e9` |

The v3 card supersedes the stale v2 card after the source-pin replan. Its
offline verifier passed all bindings, including current implementation and
model identity pins, protocol digest, initial boundary and bundle, cycle-0
preflight, private file mode, and absence of cycle output roots. Cycle 1 is
explicitly marked blocked pending cycle-0 completion and chain verification.
Both per-cycle GPU confirmations remain unset in the card. Do not launch while
the operator is using the GPU; recheck host telemetry and obtain fresh,
cycle-specific confirmation before any inference.

Independent preregistration timing remains false. No inference, learning,
performance improvement, causal development, or authority is claimed.
