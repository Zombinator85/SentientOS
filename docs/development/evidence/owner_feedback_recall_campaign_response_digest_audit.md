# Owner-feedback recall campaign: response-digest audit

Captured: 2026-11-28
Campaign: `rootless-history-campaign-cf6b83fb9e064587bc88`
Plan digest: `01ce99e9f4c6c5600a3592c1285797e45b1c0bf5a9eebb446d43a910bfab6d98`
Protocol: `owner-cognition-feedback-cross-cycle-recall-v1`
Protocol digest: `dc876a24153465ad632fc1893bd564192cbcf51a4cc5654728b7081d99174b60`

## Historical-source verification

The two completed cycle records report repository revision
`ba099ceda50983611465bf1f4600fe1efa8cbad0`, a clean worktree, and complete
source fingerprints. That commit remains in Git history. A detached checkout of
that exact commit independently returned `verify-plan: operation=verified`
for all 2,558 implementation pins and both model identity recipes. The campaign
verifier then reported both cycles complete, with append-only history, seed
boundary, and runtime-admission chains verified.

The verifier did **not** establish every custody chain: its report marks the
cognition-recovery-state chain false, the initial history seed bundle
unverified, and the history-transfer-precondition snapshot chain false. It
reports learning, model attention, authority, and independent preregistration
timing as false. The audit was run locally against the retained artifacts; no
raw prompts or model outputs were copied into this note.

Private evidence digests:

| Artifact | SHA-256 |
|---|---|
| Campaign plan | `d72c3866fccfcb64b3c04f385e37c53b01b6e69eacf45ea8df07b4ac38c322e3` |
| Historical-source campaign audit (mode 0600) | `3176bad142e2d8cb78f609eeadaa083af77f0e31200c3f6bbe015e8bb292bace` |
| Cycle 0 result (mode 0600) | `26d31a809eccfca10b9fa256e3ab94022f3bad2af9dff352bbe9156b50ede26f` |
| Cycle 1 result (mode 0600) | `a2dccde54d3d23e170b6b71e357ae8f99b9156ccd83e6d38b1e6d3b84679f4a3` |

The private audit is at
`sentientos-data/rootless-experimental/owner-feedback-recall-campaign-20261127-response-digest/campaign-audit-current-source.json`.
It was produced using the historical verifier from the cycle-reported source
revision above, not the present checkout.

## Recall outcome

Cycle 0 correctly records that the cross-cycle recall probe was not run. In
cycle 1, the controlled probe selected the same feedback record and digest in
history-present and history-restored, selected no record when history was
withheld, and verified matched non-history inputs. Yet the model abstained
without a citation in both present and restored conditions; it answered in
the withheld condition without a citation. Thus the preregistered exact recall
criterion failed. Restoring history reproduced the present prompt and output,
but that stability did not make either response correct.

This is evidence that this single history-conditioned recall attempt failed
its response and citation criteria. It does not establish durable learning,
a general capability deficit, model-independent continuity, or causal
self-development. The incomplete cognition-recovery and initial-seed custody
chains further limit claims about durable continuity. These cycles did use
model inference; the audit described here was CPU-only.

## Current follow-up readiness

A later neutral-query v2 protocol and 12-acquisition/12-transfer plan were
prepared, but the current offline run-card verifier rejects its revision-2
card with `history_campaign_model_identity_implementation_mismatch`. The
card's saved plan-verification claim is stale relative to the current source.
The private card digest is
`67fb0e15870e4f4c63bc22bd9c04729c3ac389542a202253549ee29779624960`.
It remains `prepared_not_started`; its cycles have no output roots. Do not use
that card for launch. A future attempt needs a newly pinned plan and run card
from current source, fresh cycle identities and seeds, and verified initial
history/recovery custody. The separate active v6 campaign also remains
unlaunched while its GPU gate is closed.
