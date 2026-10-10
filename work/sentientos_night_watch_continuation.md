# SentientOS night-watch continuation

Construction work is **untested for production**. Continue from branch `codex/construct-sentientos`; inspect status before editing. Original source HEAD: `329efdfd4237e6c8e9ea9ad2b66d1c6d5482e34d`.

## Completed checkpoints

- `b40fd789c22162d2faac85ecadaaa3f287246912` (remote verified): `sentientos/embodied_consequence.py` imports without POSIX `fcntl`; consequence file custody keeps its descriptor-relative POSIX guarantees and fails closed when unavailable. Read-only lookups do not create storage.
- `c4dbce7ca8a1eea89e7de77a46ae8543278b93f0` (remote verified): exact opt-in selectors project digest-verified strategy experiment and controlled model-replacement artifacts into World-State. Their absent event times remain undated through epistemic adaptation.
- Third increment compiled: durable immutable consequence-chain bundle; exact chain projection; model-comparison linkage validation; stable undated chain summary; explicit source/record byte and projection-count budgets; daemon reports degraded if World-State’s 128-source cap omits selected projected records. `evaluate_consequence` never upgrades descriptive fulfillment to effect proof. `py_compile` and `git diff --check` passed; no runtime behavior was exercised.
- `07b0653cb87b8420a530989a5f1eced29cbd0b94` (remote verified): immutable consequence-chain registration/projection, exact chain selectors, stable undated summary, bounded World-State projection, and source-limit degradation reporting.
- `4088dbe748d5da9321f1efc2aec57f799f2d3394` (remote verified): digest-bound observations remain explicitly unverified caller assertions; epistemic freshness is unknown absent an authenticated observer issuer.
- `6fd32f7064a8d60dadac7c2316f82a08950b38a9` (remote verified): consequence artifact reads now use no-follow descriptor traversal.
- `1ec6d5b5e7436fde62ad49012e27b3de8f98adb9` (remote verified): strategy proposal review adapter and digest-aware review receipts; strategy kinds remain blocked from legacy handoff.
- `7ca153d9516069bf78b951f6bce579f9e70b9f73` (remote verified): controlled model-replacement artifacts use no-follow descriptor reads and immutable descriptor-relative publication.
- Eighth increment in progress: durable per-condition start/terminal custody for A/B comparisons; completed observations are reused after restart, a started nonterminal condition is never replayed, partial runs are content-addressed and projected as incomplete/contradictory, and campaign recovery reconciles an in-progress trial without marking partial output complete.

## Boundaries and blockers

- Cognition executes before same-tick epistemic development; retained state is only eligible for later cognition through the existing configured owner path.
- Legacy proposal review/fulfillment types do not authenticate or bind embodied strategy proposal digests. Do not cast strategies into those types or issue authority.
- No independently authoritative physical-effect receipt owner is composed; consequence records remain effect-unproven.
- `sentientosd.py` imports other POSIX-only maintenance owners. Only the consequence module import is made portable; whole-daemon Windows importability is not established.
- Model-replacement protocol does not bind software generation; preserve it as unknown.

## Exact next work

1. Compile the per-condition recovery changes, commit `[untested]`, push, and verify remote SHA.
2. Review the campaign state store’s adjacent path-based custody, then check for any other directly connected restart gap.
3. No pytest, mypy, audit, matrix, landing workflow, production activation, external effect, or authority expansion. No runtime or Windows validation has been performed.
