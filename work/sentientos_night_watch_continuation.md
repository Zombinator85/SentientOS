# SentientOS night-watch continuation

Construction work is **untested for production**. Continue from branch `codex/construct-sentientos`; inspect status before editing. Original source HEAD: `329efdfd4237e6c8e9ea9ad2b66d1c6d5482e34d`.

## Completed checkpoints

- `b40fd789c22162d2faac85ecadaaa3f287246912` (remote verified): `sentientos/embodied_consequence.py` imports without POSIX `fcntl`; consequence file custody keeps its descriptor-relative POSIX guarantees and fails closed when unavailable. Read-only lookups do not create storage.
- `c4dbce7ca8a1eea89e7de77a46ae8543278b93f0` (remote verified): exact opt-in selectors project digest-verified strategy experiment and controlled model-replacement artifacts into World-State. Their absent event times remain undated through epistemic adaptation.
- Third increment compiled: durable immutable consequence-chain bundle; exact chain projection; model-comparison linkage validation; stable undated chain summary; explicit source/record byte and projection-count budgets; daemon reports degraded if World-State’s 128-source cap omits selected projected records. `evaluate_consequence` never upgrades descriptive fulfillment to effect proof. `py_compile` and `git diff --check` passed; no runtime behavior was exercised.
- Fourth increment in progress: the existing observation digest proves content identity, not observer authority. Consequence attribution now labels that source as `unverified_caller_assertion`; the epistemic adapter keeps its freshness unknown even when the timestamp parses as recent.
- Fifth increment compiled: `ConsequenceStore` opens the configured root and artifact directories by no-follow descriptors; artifact/checkpoint reads are relative to the opened kind directory. Missing checkpoints remain non-mutating and publication retains existing immutable locking.
- Sixth increment in progress: strategy proposals have a typed adapter to the existing review-only receipt owner; new review receipts bind proposal digests and mark reviewer identity `declared_unverified`. Review resolution matches both ID and digest, while the legacy handoff table continues to block unsupported strategy kinds.

## Boundaries and blockers

- Cognition executes before same-tick epistemic development; retained state is only eligible for later cognition through the existing configured owner path.
- Legacy proposal review/fulfillment types do not authenticate or bind embodied strategy proposal digests. Do not cast strategies into those types or issue authority.
- No independently authoritative physical-effect receipt owner is composed; consequence records remain effect-unproven.
- `sentientosd.py` imports other POSIX-only maintenance owners. Only the consequence module import is made portable; whole-daemon Windows importability is not established.
- Model-replacement protocol does not bind software generation; preserve it as unknown.

## Exact next work

1. Compile the review bridge, commit `[untested]`, push, and verify remote SHA.
2. Review other adjacent portability/custody owners for the same read-vs-write asymmetry; do not broaden beyond directly connected code.
3. No pytest, mypy, audit, matrix, landing workflow, production activation, external effect, or authority expansion. No runtime or Windows validation has been performed.
