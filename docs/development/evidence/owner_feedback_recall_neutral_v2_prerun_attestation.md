# Neutral v2 current-replan pre-run digest record

Captured: 2026-11-28
Campaign: `rootless-history-campaign-80267c0fbd908e310860`
Plan digest: `5f5a9a621320a30e40a68746dfe6555861bc28894b96651eca5b7c286424fc41`
Protocol digest: `eadf7e24dea6c21b7017464b6ccc46ed672fd2d99c65db7e158c26623cea27ac`

## Improvement

The previous digest-record format named a semantic plan digest
`campaign_plan_sha256`, making it easy to confuse the canonical campaign
identity with a SHA-256 of the private plan file. Version 2 records both values
under distinct names, and the offline verifier checks the raw plan-file hash
against the private plan while separately matching the semantic plan digest to
the card.

The digest-only record binds the current-source replanned campaign, protocol,
and private run card without publishing the plan, card, model identity, or
seeds. It preserves the explicit limit that independent preregistration timing
has not been established. Git commit metadata and remote reachability establish
the record's inclusion in the development history; they do not establish the
actual remote push time or when the plan was first drafted.

## Bound values

- Private plan file SHA-256: `bd711baefa64d5b3fb7c165a9197a9486816de146db665526343c2482cb09fdc`
- Semantic plan digest: `5f5a9a621320a30e40a68746dfe6555861bc28894b96651eca5b7c286424fc41`
- Owner-feedback protocol digest: `eadf7e24dea6c21b7017464b6ccc46ed672fd2d99c65db7e158c26623cea27ac`
- Private run-card file SHA-256: `a303ad4db17bb3a8cd3e2f0f4f30cd0f11ba9ae4b7fcb494f70a9175c3041837`
- Digest-record SHA-256: `e7f188e8da7b0511fd7d6de446940b9e7ec03dbdd87b8c5b5660413ded031ca6`

At record construction, the card was `prepared_not_started`, no inference had
occurred, both planned cycle output roots were absent, and each cycle required
a fresh operator confirmation bound to its cycle ID. Cycle 1 remains gated on
cycle 0 completion and append-only history-chain verification.

This record is a custody and pre-run state check. It is not independent review,
a claim of learning, a performance result, or evidence of a causal effect.

## Remote publication verification

Attestation commit: `20c9a01368aabcb19d75d273bf5b1ba955c76105`
Commit timestamp: `2026-11-28T05:52:18+00:00` (Git committer metadata; not an independent timestamp).
Remote ref: `refs/remotes/origin/codex/cognition-feedback-digest-binding-20261127-local-recovery`, observed head `20c9a01368aabcb19d75d273bf5b1ba955c76105`.
Private offline verification report SHA-256: `fea07c072b918e3dfe881e0a180393b1e63cddee552cd07814b14c1652cc23d2`.

The verifier passed all 18 checks, including exact attestation bytes in the commit, reachability from the fetched remote ref, the private plan-file SHA-256, the semantic plan digest, the protocol and run-card digests, absence of both cycle output roots, and required per-cycle GPU confirmation. The report remains in the private experiment workspace. No model was loaded or invoked.

The commit date and remote reachability are recorded as repository evidence only. The attestation continues to set independent preregistration timing to false.

## Seed-bundle semantic preflight

The offline run-card verifier now calls the campaign runtime's _load_initial_history_bundle before accepting the current replan. This independently recomputes the canonical bundle digest, validates the campaign and plan binding, decodes every private Base64 file entry, checks each file size and SHA-256, and recomputes the source history boundary. Previously the card verifier checked the outer file digest and declared bundle fields but did not itself reconstruct those internal invariants. The experiment runner already enforced them at cycle launch; this moves the same semantic check into CPU-only pre-run review.

Current private run-card verification passed all 24 checks, including initial_history_bundle_semantics_verified. Its private report SHA-256 is 31bfa722ab7331f3673879f67167c8058025472d53bf510fcc4ef684fab97827 and it remains mode 0600. The campaign remains prepared and unstarted; the campaign implementation pins, bundle contents, and private report are not published.
