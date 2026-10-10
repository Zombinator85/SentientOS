# SentientOS construction campaign II continuation

Non-authorizing progress record. Construction changes are **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remote checkpoint

GitHub branch `codex/construct-sentientos` was independently read after publication at commit `84dd6d2aef1785fc06123a7662b68cecb9288a81`, tree `e87ef8aa31bb455841cfc7c2f476acd219d5786a` (parent `8f3c34bb6051aa2ece57323c6247ab97552917de`). Shell Git transport is unavailable; GitHub Git-data commits used compare-and-swap ref updates and were verified by rereading the branch. Local Git commit IDs are not remote commit identities.

## Completed construction in this campaign

- A shared explicit-file reader now binds every POSIX parent component with descriptor-relative `O_DIRECTORY|O_NOFOLLOW`, opens the leaf relative to the held parent, requires a single-link regular file, and checks stable identity and size during bounded reads. Windows reads use the existing held-handle/reparse-safe implementation; missing NT paths receive a distinct fail-closed status.
- Configured proposal-review receipts can enter the resident World-State through projection config v2 with explicit absolute log path and exact selected IDs. Canonical review identity fields are verified; historical v2 receipts are accepted only by reconstructing their original deterministic ID material, and their unbound execution context is excluded. Review identity remains an unverified caller assertion with no authenticated event time, effect proof, or authority.
- The daemon rereads only selected review IDs each tick, exposes read-only projection health, and drops/degrades invalid, missing, conflicting, oversized, or source-limit-omitted rows instead of reusing cached facts. Epistemic adaptation preserves historic/unknown freshness. Longitudinal self-model can retain a compact `embodiment.historical_proposal_review` interpretation with review and proposal identities, outcome, bounded execution lineage, and World-State provenance. Existing configured selectors still gate retention and later cognition.
- Post-adoption attribution now has a bounded Windows read-only recovery path; canonical JSON rows, single-link POSIX custody, and read-stability checks precede its existing shared lineage verification. Mutation remains POSIX-only.
- Model-replacement read-only recovery now requires canonical artifact bytes, bounded regular files, and stable POSIX file identity across reads before its existing artifact digest checks.
- Successor-generation config and handoff-journal reads use the shared bounded descriptor/handle reader. Journal recovery enforces record/line/total-byte limits, canonical rows, digest chaining, phase order, and truthful partial-transition handling.

## Configuration and evidence limits

Review evidence reaches World-State only through the explicit v2 projection config with an absolute review-log path and selected receipt IDs. Epistemic writeback requires a configured selector for the review source; later self-model cognition requires `embodiment.historical_proposal_review` in its allowed predicates and the enabled history/cognition paths. The review source remains undated and unknown-freshness; reconstruction is not a fresh event.

Python compilation of changed modules and `git diff --check` passed. No pytest, mypy, audit, runtime or Windows execution, production acceptance, or independent cold-start evaluation was performed. Windows handle APIs are compile-only verified here. Some writer/adoption modules and their dependency import graph remain POSIX-only; no new successor operation was started. No independently authenticated reviewer or physical consequence observer is composed, and no production model/software transition is evidenced.

## Next executable task

Map the import and custody closure for Windows-hosted successor adoption, starting at `maintenance_successor_generation_adoption.py` and `maintenance_wake_daemon_adoption.py`. Identify the smallest safe read-only recovery owner that can be made Windows-importable without changing process-start, cadence-lock, or transition authority. Keep all effectful activation paths fail-closed and compile changed files only.
