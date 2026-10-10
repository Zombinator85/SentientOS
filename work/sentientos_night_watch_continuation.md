# SentientOS long construction continuation

Non-authorizing progress record. Construction changes are **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remotely verified checkpoint

GitHub Git-data commit `781cdc3b43e0f5fabb81a4a0b9eba11dde2a503b` (tree `3ed912bced50488abfa15e443ec077b299841aaf`) is present. Its parent is `290070f2b31acad0806adb0f30a022bb0bc900ba`. The workspace's local Git `HEAD` is historical (`2e3208a...`) and is not the remote branch identity. Publish by creating Git objects on top of the verified commit and CAS-updating the branch; reject/inspect any lease mismatch.

## Completed source construction after that checkpoint

- Added `platform_fcntl` as an import-safe POSIX lock facade. Read-only modules can load on Windows; every attempted `flock` and every associated live transition/adoption effect fails closed. POSIX locking remains native.
- Expanded Windows custody support across the statically inspected maintenance-successor import closure and bounded recovery owners. Exact file reads use the existing Windows handle walker, reject reparse points and multiply linked files, and enforce file/aggregate/count bounds. The walk now also bounds all directory entries, including names excluded by the requested suffix.
- Added a Windows `InstallationStateReadOnlyView` implementation derived from the canonical machine installation root. It validates that root through the handle walker and exposes only bounded reads and bounded listing; it does not provide writes, locks, activation, or adoption. `_load_resident_transition_custody` uses it only on Windows to recover the exact configured model protocol and journal.
- Separated resident cognitive transition custody inspection from transition processing. The read-only inspection authenticates bounded request packets, receipt chains, and journal references without consuming requests or appending recovery receipts. Request/receipt publication and transition processing remain POSIX-only. The daemon reports a blocked platform posture rather than letting this one optional surface fail the maintenance tick.
- Bounded the resident-model serving configuration read. The resident transition protocol and journal readers retain canonical digest validation and historical incomplete states; controller recovery never recreates process-local quiescence or replays an interrupted stage.
- Model-replacement and developmental-history experiment recovery uses bounded canonical reads, validates exact identities, and preserves an interrupted trial instead of re-running inference. Added a read-only custody inspection path. Campaign roots retain their lexical path so Windows handle validation can see and reject junctions rather than resolving through them first.
- Added a configured, selected-only proposal-review receipt projection into World-State and later self-model claims. Review material binds the exact proposal and bounded source execution context; legacy identity-only receipts remain explicitly weaker. Reviewer identity, time, authority, approval, and consequences remain unverified. Projection health reports selected-source omissions instead of silently treating truncation as success.
- Previous work in this workspace also hardens epistemic, cognition, developmental-history, runtime-admission and invocation-receipt recovery. Writers fail closed where no equivalent atomic Windows publication contract exists.

## Verification and known limits

Python compilation of changed Python files and `git diff --check` pass. No tests, mypy, runtime execution, Windows execution, production validation, model inference, or external effects were performed. Windows behavior is source-constructed and compilation-checked only. The full installation-backed serving/adoption transition remains POSIX-only because installation mutation, activation custody, locks, and durable publication do not have Windows contracts. No production evidence or physical consequence is established here.

## Next executable task

Trace the configured consequence evidence path end-to-end: verify that expectation/prediction, proposal/review, independent observation, attribution, comparison, and any authorized later epistemic change preserve exact identities and historical event time. Close the highest-leverage missing owner handoff using only existing authority. Then inspect whether retained evidence can guide a later resource-selection proposal without adding a resource-minimization objective or inferring measurements.
