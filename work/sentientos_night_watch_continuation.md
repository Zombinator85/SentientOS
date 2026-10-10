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
- `ef207185ab623e91b74560a171d1f4a7f48751f6` (remote verified): A/B comparison conditions now have immutable start and terminal records. Recovery reuses completed conditions, never replays a started condition without a terminal, and preserves partial/incomplete trials instead of counting them complete.
- `ace50f1d842f43cac790c483b5f27ae9555699bf` (remote verified): campaign protocol/report/failure records use bounded descriptor-relative no-follow custody; campaign state is locked, atomically replaced, stale-writer checked, and retained in a bounded immutable predecessor chain for restart reconstruction. File custody is fail-closed where POSIX descriptor primitives are unavailable.
- `ee4677c8ce36847657822bc7d19adb487f018b41` (remote verified): persistent epistemic observation adapter verifies observation content identity but records it as contextual, unknown-freshness evidence with unresolved dependency. A self-declared observer ID no longer yields current independent support.
- Next increment in progress: post-adoption epistemic adapter now verifies the evaluation content identity and preserves its historical `evaluated_at`; unverified collector/source issuers produce only contextual, unknown-freshness evidence. Its compatibility `observed_at` argument no longer controls event time.

## Boundaries and blockers

- Cognition executes before same-tick epistemic development; retained state is only eligible for later cognition through the existing configured owner path.
- Legacy proposal review/fulfillment types do not authenticate or bind embodied strategy proposal digests. Do not cast strategies into those types or issue authority.
- No independently authoritative physical-effect receipt owner is composed; consequence records remain effect-unproven.
- `sentientosd.py` imports other POSIX-only maintenance owners. Only the consequence module import is made portable; whole-daemon Windows importability is not established.
- Model-replacement protocol does not bind software generation; preserve it as unknown.

## Exact next work

1. Compile, commit `[untested]`, push, and verify the post-adoption adapter change.
2. Inspect the frozen model-replacement context for missing controlled factors already represented by existing self-model, epistemic-state, resource-receipt, or software-generation owners; add only exact, source-backed bindings.
3. No pytest, mypy, audit, matrix, landing workflow, production activation, external effect, or authority expansion. No runtime or Windows validation has been performed.
