
## 2026-10-12 checkpoint — distinguish fresh remote identity from local construction state

- Continued from exact remote `898a638299312cfebe9cc7c89df5680a646e4742`, tree `5f14c4331e5c34eaa4aadd8ff7dffc50d895003b`.
- Added a read-only construction source preflight. It checks the exact configured origin, calls `git ls-remote` for one branch ref, separates the committed tree from staged/unstaged/untracked state, and distinguishes exact base, valid dirty-on-base work, stale checkout, divergent history, unpublished commits, equal-tree/different-commit, unknown remote objects, unreachable/mismatched origin, and expected-head race. It never fetches, changes refs, stages, or publishes.
- Disposable bare-remote acceptance covers clean base, staged/unstaged/untracked changes, unpublished candidate, stale dirty checkout, divergence, branch advancement, equal-tree commit rewrite, origin mismatch, and unreachable remote. All eight focused cases passed.
- Acceptance details: `work/construction/construction_source_preflight_acceptance.json`.
- Reacquire GitHub branch and main identity before continuation or publication. No mainline acceptance or landing has been run.
- Next: use the reconciled source baseline to identify the minimum complete hosted lifecycle and close the highest-impact source composition gap; distinguish integration from fixture-backed behavior and production evidence.
