# SentientOS construction campaign II continuation

Non-authorizing progress record. All changes below are **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remote checkpoint

GitHub branch `codex/construct-sentientos` was independently read after publication at commit `d2f82574f40a4a96a500e549d276816ab3ec7700`, tree `5cb1f26123726eea98c4582c1f7baf911482f4d3` (parent `78d26a8635644770d480cb2167c2c99954174b53`). Shell Git transport is unavailable; source was published through GitHub's Git-data API with a compare-and-swap branch update and the branch was then fetched again. Local historical commit IDs are not remote commit identities.

## Construction added in this campaign

- Cross-platform bounded read custody is available through `sentientos/windows_handle_custody.py`. Windows uses held directory/file handles and rejects reparse-backed custody; POSIX explicit-file reads now walk each parent with `O_DIRECTORY|O_NOFOLLOW`, bind the leaf open to the final directory descriptor, require a single-link regular file, and check stable identity/size during bounded reads.
- Explicitly selected proposal-review receipts can feed World-State from projection config v2. Receipt identities and canonical fields are checked; legacy v2 IDs are reconstructed from their original bound fields without treating unbound execution context as trusted. Review outcomes remain caller assertions, lack authenticated event time, and carry unknown freshness and no authority/effect proof.
- The runtime rereads only configured review receipt IDs at each World-State tick. Missing, malformed, conflicting, oversized, or source-limit-omitted selected rows degrade that projection rather than leaving cached evidence active. The emitted health row reports read-only source custody state.
- Review facts are historical in the epistemic adapter. Longitudinal self-model can retain a compact `embodiment.historical_proposal_review` interpretation with receipt/proposal identities, outcome, reviewer posture, bounded execution context, and source-fact lineage. The existing configured rules and predicates still gate writeback and later cognition; retained review interpretation is never current truth, authorization, execution, or proof of reviewer identity.

## Configuration and evidence limits

A review can reach World-State only when the explicit embodied-consequence projection config uses schema v2 and selects an absolute review log path plus exact receipt IDs. Epistemic retention requires a configured rule selecting the embodiment/review source fact; longitudinal cognition requires the predicate `embodiment.historical_proposal_review` in its allowed predicate selection (and the corresponding enabled history/cognition path). Resident cognition still applies its configured source and temporal selectors. Historical receipts have no authenticated event time; reconstruction does not make them fresh.

Compilation of changed Python modules and `git diff --check` passed. No pytest, mypy, runtime, Windows execution, independent cold-start, or production checks were run. No independently authenticated physical observer or reviewer issuer is composed. Windows native handles remain compile-only verified here. Durable Windows publication paths for longitudinal/developmental and some model/software transition stores remain fail-closed or POSIX-only; no live model/software successor or physical consequence is evidenced.

## Next executable task

Inspect the read-only recovery paths and custody contracts in `maintenance_post_adoption_attribution_campaign.py` and `developmental_model_replacement_experiment.py`. Add Windows handle-bound reconstruction where the existing immutable journal contracts allow it, preserving fail-closed behavior for mutation/publication until a sound Windows atomic writer exists. Compile changed files only.
