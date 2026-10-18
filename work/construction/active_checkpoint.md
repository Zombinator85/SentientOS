# Active construction checkpoint

Latest verified main after sequence 401: regular merge `128a8410890d57d2d52b797b488e7e11dcd41c9a`, tree `5075600c1029318d8881aa6e5f0f09b80093591c`, PR #2373. Exact-main Required Quality Gate, CI, Docker Image, Invariant Tests, Docs Deploy, and Codex CI succeeded; Forge Smoke was skipped by its configured condition. The current-main scheduled Federation Health run is pending; the latest completed schedule (#39164710891) used prior main `ae55461e13be358c2754c7686b381ae2d72daa63`. Nightly Audit Integrity and Nightly Self Check have successful push-run evidence on `e3011573c2eb05c1a4dfbf9a142f5376823d515c`; their workflow and relevant dependency blobs match current main, but current-main scheduled executions remain pending. Exact-main post-merge Required Quality Gate, CI, Docker, Invariants, Docs Deploy, and Codex CI passed; Forge Smoke was skipped by its configured condition. The QG artifact #12136979866 (11,202 bytes) was independently downloaded and matched SHA-256 `78b5ff4b2a98626f8cf3eac144762988877dd4b60b569540671113f08efb78ad`; it binds Administrator UID 0, strict audit, immutability, and 29/29 acceptance to this exact SHA/tree. CI source-validation artifact #12137458734 (472,355 bytes) matched `ac718bdd07667f76ef8d875648194a09a8ede167d2d25d58f06b3c98008eb259`; canonical planning (20), source validation (11), and World-State contracts (3) were ready with zero failures. The latest visible scheduled Federation Health run is still #39122005777 on older source `0e2a7bff`; no schedule on current main `1737cc7` was visible by 13:18 UTC.

Historical scheduled Federation Health evidence was later independently verified for source `f0564c9f780e1f86a53e84348ec4a4a9534c0e48` (tree `62d9b93b038f92a5df1b25d6cb7cc70847a86f23`): run #39028288072 succeeded, Administrator preflight and generator passed, artifact #12098768757 reports 1 node/0 recent/quiet, and publisher created no PR because output matched main. This closes the scheduled-execution gap for that historical merged source; it does not substitute for a scheduled execution on current main `1737cc7`. This is not changed-output fixture proof.

The corrected nightly workflows also have hosted runtime evidence. Nightly Audit Integrity #39100678248 and Nightly Self Check #39100678294 succeeded as push events on `e3011573c2eb05c1a4dfbf9a142f5376823d515c`. Their workflow blobs and relevant test/audit dependency blobs are identical to current main. Audit ran strict verification with `contents:read`; its conditional write-capable repair job was skipped after a clean result. Self Check passed strict audits, privilege lint, mypy, pytest airlock guard, and pytest (143 passed, 13 skipped, zero failures). These runs are not labeled scheduled or exact-commit runs on `0e2a7bff…`.

Sequence 368 fixed the Federation Health fixture publisher's Git ref DELETE route and retained API error detail in fail-closed cleanup evidence. The real changed-output fixture remains blocked by the repository Actions setting `Allow GitHub Actions to create and approve pull requests`; the failed proof remains unverified. After the setting is enabled, dispatch Federation Health Update with `publication_fixture=true` to verify the exact one-file draft PR and no-merge cleanup. The health job remains read-only; write authority remains scoped to publisher job.

Sequence 369 reconciles stale README and thesis status and appends exact scheduled/nightly evidence. On source `0e2a7bff…`, the canonical workflow-contract suite passed 36/36 with zero skips; documentation dependency checks and build passed (614 pages); `git diff --check` passed; construction custody verifies all 369 segments after correction of one recorded source-tree transcription mismatch. Runner bootstrap failures caused by sandbox networking/read-only user install were recorded and superseded with a fresh isolated virtualenv. Generated test artifacts were hash-captured; tracked runner state was restored exactly.

The next developmental evidence dependency remains a real, longitudinal resident A→B→A transition using exact commissioned hardened A/B model identities and receipts, exact installation/runtime/environment/software lineage, and separately operator-approved activation, serving, and trial protocol. Current source already composes resident cognition, writeback/retrieval, protocol and history-boundary checks, staged replacement, live operator ingress, process-local quiescence, and synthetic temporal rehearsal. No production inference was started. Process-death quiescence recovery remains deferred: journal evidence cannot recreate a process-local token. Output difference and scheduled health telemetry do not establish developmental learning or improvement.

Sequence-286 provenance loss remains unresolved and unchanged. The stale sequence-178 workspace, preexisting sequence-368 workspace, remote `codex/construct-sentientos`, and old fixture branches were left untouched.

Sequence 370 source candidate: `b4dc89c13ab773eafa048926a5f7ed3daeb82923`, tree `a03424d810a8843982d1a5a61720bd1e1ced6542`. It records the hosted PR-finalizer title-contract failure discovered while landing sequence 369. The QG's hosted Administrator audit and 29 acceptance nodes passed; finalization did not run because the PR title differed from the latest commit subject by capitalization. A metadata rename and retry reused the original GitHub event payload, so the guard failed again. The title guard and finalizer remain unchanged. The next descendant's commit subject and draft PR title will match exactly, and its fresh hosted finalizer must pass before merge.

Sequence 371 source candidate: `4606778f352d38ca86b0f233719c495792c17b7d`, tree `c0c3d5926b9ae81a51066830086da7dd525164d5`. Sequence 371 records the second hosted finalizer stop (#39122735813): all 29 acceptance nodes and strict Administrator audit passed, but the pull-request synchronize event retained the prior PR title and correctly failed the exact title/commit-subject guard before finalizer invocation. PR #2361 title was updated before the next head update; the next commit subject is set to match. A fresh full gate is pending.


Sequence 372 source is the exact verified main `a205fdeb280e5488ff6216ab54d7d1800dc0bee8`, tree `a378b176cff01d46697c351944051d5c01af71d0`. The construction continuation index at that main is unreadable binary (blob `8e94b8f63fb590b56a25957be7da7141eda1bc0c`); the recovery restores the valid sequence-368 index from `f78a538547c4c41a1d396e8ad6108f55ac164276` and reconstructs entries 369–371 from their unchanged tracked segments/evidence. This preserves the original segment chain and records the defect in sequence 372 evidence.

Sequence 372 also binds the daemon's World-State resource facts and causal-resource introspection to one read-only owner snapshot per tick. A read is cached across both projections; a new tick refreshes it, and a same-tick owner failure is not retried into an inconsistent second view. The source schema now declares the two chat-process generation observations its callback already emitted. Runtime-closure tests also exposed missing optional transition attributes on lightweight injected surfaces; those reads now default safely while preserving the fail-closed transition behavior when the error is present.

Canonical targeted tests passed: 40 passed, 0 skipped across resource observation integration, causal introspection composition, and daemon runtime closure. `py_compile`, `git diff --check`, and `scripts/check_mypy_baseline.py` passed; the baseline reported 0 new errors and 40 retired errors. The local finalizer did not return ready: its two Administrator-only audit stages failed closed with `Access denied`. Hosted QG, hosted strict audit and immutability gate, and post-merge verification remain pending. No production inference or authority expansion occurred.

The changed-output Federation Health fixture still requires repository setting `Allow GitHub Actions to create and approve pull requests`; do not represent the prior denied run as publication proof. Sequence-286 provenance loss remains unresolved. The stale sequence-178 and sequence-368 workspaces remain untouched.

Sequence 373 starts from exact merged main `fa8a934ed34bb50b0988aeb0fd829a8806d132f8`, tree `a67c9c115990317c79e98f6edb5ae619e2d6cb25`. PR #2362 candidate `09417da4c869233587c3640f24a9378376b6a294` passed the hosted Required Quality Gate (including Administrator strict audit, exact call-phase acceptance, and hosted landing finalizer), CI, Docker, invariants, Gradient, Codex CI, lint, and Release. GitHub main readback returned the exact six candidate blob IDs. The connector's commit-run endpoint filters to PR-triggered runs and returned none for the merge commit; its combined status endpoint returned no simple statuses. A direct read-only GitHub REST request was blocked by the sandbox proxy. Post-merge workflow conclusions are therefore unknown, not successful by implication.

Sequence 373 adds an adversarial failure-path regression for the resource observation snapshot cache. A transient first owner read fails World-State and same-tick causal introspection consistently with one owner call; the next tick retries exactly once and both projections recover from the same successful snapshot. This adds no runtime behavior or authority.

The relevant resource/introspection/runtime regression set passed 82/82 with zero skips on the exact merged source tree. The repository mypy baseline reported zero new errors and 40 retired error records; py_compile, diff check, and continuation custody verification passed.

The next developmental evidence dependency remains a real, longitudinal resident A→B→A trial with exact commissioned hardened model identities and separate operator approvals. No production inference was started. The Federation Health changed-output fixture still needs the repository Actions PR-creation setting enabled; sequence-286 provenance loss remains unresolved. The stale sequence-178 and sequence-368 workspaces remain untouched.

Latest construction segment: `work/construction/segments/0373-bind-resource-read-failure-to-tick.md`
Latest segment SHA-256: `a4c3b484d94aa5db159ea1a00ed8ce04a8e2406dbfc7147bbd7d3e3d30edea37`
Sequence: 373


Sequence 374 records the completed sequence-373 hosted candidate verification and regular merge. The targeted resource/introspection/runtime suite passed 82 tests with zero skips; py_compile, diff check, custody, and mypy baseline checks passed. No production inference or runtime authority was added. The next developmental evidence dependency remains a real resident A→B→A trial with exact commissioned A/B identities and separate operator approvals. The Federation Health changed-output fixture still requires the repository Actions PR-creation setting; sequence-286 provenance loss remains preserved. The stale sequence-178 and sequence-368 workspaces remain untouched.

Latest construction segment: `work/construction/segments/0374-verify-sequence373-merge-and-hosted-checks.md`
Latest segment SHA-256: `aa28e55c931e932bb8e3466d2d8e977c7af0cc75a0ddb88b36bc4907bf242a83`
Sequence: 374


Sequence 375 records independently verified exact-main post-merge execution evidence for sequence 374. Local resource/introspection/runtime regression tests passed 82/82 with zero skips; mypy, py_compile, diff check, and continuation custody passed. The Federation Health workflow remains read-only for health and retains the hourly schedule, but its 12:17 execution on this exact main SHA was not observed by 12:19 UTC. The changed-output fixture still requires the repository Actions PR-creation setting; corrected nightly scheduled executions remain pending their next scheduled window. No production inference or runtime authority was added. The A→B→A trial still requires exact commissioned models and separate operator approvals. Sequence-286 provenance loss and stale sequence-178/368 workspaces remain preserved.

Latest construction segment: `work/construction/segments/0375-verify-exact-main-post-merge-gates.md`
Latest segment SHA-256: `be9806bba510a2d85c3549b2cb4ddd92b6334253a0d03fcee9866734970e819c`
Sequence: 375


Sequence 376 verifies exact-main post-merge checks for sequence 375. The runtime regression suite and mypy/compile/custody results were verified on the exact parent source tree; this evidence-only merge did not change runtime sources or authority. Federation Health remains read-only in its health job with hourly schedule. At the recorded cutoff, the 12:17 event had not appeared on c09d569…, nor had a scheduled run appeared on bed8ec6…. The changed-output fixture still requires the repository Actions PR-creation setting; exact-main nightly scheduled executions remain pending. No production inference was started; the real A→B→A trial still requires commissioned model identities and separate operator approvals. Sequence-286 provenance loss and stale sequence-178/368 workspaces remain preserved.

Latest construction segment: `work/construction/segments/0376-verify-sequence375-postmerge-main.md`
Latest segment SHA-256: `3c9954d5c07d393112aff711b280849455b51f406b438c66ee33f2338fb2e2c5`
Sequence: 376


Sequence 377 verifies exact-main post-merge gates for sequence 376. Runtime regression and mypy/compile/custody results were verified on its exact parent source; this evidence-only merge changes no runtime source or authority. Federation Health retains its hourly schedule and read-only health permission, but no run on current main was visible at 12:45 UTC. The changed-output fixture still requires the repository Actions PR-creation setting; the next scheduled opportunity is 13:17 UTC. Current-main nightly scheduled evidence remains pending. No production inference was started. The real resident A→B→A trial still requires commissioned model identities and separate operator approvals. Sequence-286 provenance loss and stale sequence-178/368 workspaces remain preserved.

Latest construction segment: `work/construction/segments/0377-verify-sequence376-postmerge-main.md`
Latest segment SHA-256: `9d1c1b974cddd06bc414305e7895f5c8b03f0c031a482ed9c6ebdc8dcfaf3d29`
Sequence: 377


Sequence 378 verifies exact-main post-merge gates for sequence 377. The local runtime regression suite and mypy/compile/custody results were verified on the exact parent runtime tree; this evidence-only merge changes no runtime source or authority. Federation Health retains its hourly schedule and read-only health permission, but no run on current main was visible at 12:56 UTC. The changed-output fixture still requires the repository Actions PR-creation setting; the next scheduled opportunity is 13:17 UTC. Current-main nightly scheduled evidence remains pending. No production inference was started; the real resident A→B→A trial still requires commissioned model identities and separate operator approvals. Sequence-286 provenance loss and stale sequence-178/368 workspaces remain preserved.

Latest construction segment: `work/construction/segments/0378-verify-sequence377-postmerge-main.md`
Latest segment SHA-256: `d0cb622af871ca3220e408e9fc77213e9dd9b55d836ff535427247d90f8a8d19`
Sequence: 378


Sequence 379 independently verifies the exact-main post-merge evidence for sequence 378, the historical scheduled Federation Health execution on f0564c9, and the changed-output fixture's repository-setting blocker. It registers a narrow maintenance scope for production self-reflection custody; no runtime source or authority changed. The current-main scheduled run remains pending. The campaign's next source dependency is exact protocol binding and preservation of partial/completed no-retry progress.

Latest construction segment: `work/construction/segments/0379-verify-scheduled-federation-health-and-open-transition-scope.md`
Latest segment SHA-256: `326888bd63f6bfa238150b0167834a00c54b5378432d2494c32cdf93edf1d3de`
Sequence: 379
Local sequence-379 pre-commit finalizer returned `repair_required_task_caused`: focused tests, mypy, baseline, prompt-boundary and compile/diff passed; docs dependencies were unavailable offline, and strict audits plus immutability correctly denied non-Administrator access. The finalizer's two append-only runtime audit rows were preserved; only identified generated glow test artifacts were restored/removed. Hosted validation must verify the exact candidate before landing.
Latest construction segment: `work/construction/segments/0379-verify-scheduled-federation-health-and-open-transition-scope.md`
Latest segment SHA-256: `398b33f3987bec651b68671ac1677d8c118b5f20e00a5757eeeb3e01533939b4`
Sequence: 379


Sequence 380 verifies PR #2369's merge and all exact-main push gates on `d70d63b31416f21bcc50b4c2a4708c6c822ff5e6`, tree `c2d41c644daec56a285bae564cb482831570652a`. Its QG binds Administrator UID 0, strict audit, immutability, and 29/29 acceptance; CI source-validation records canonical planning 20, source validation 11, and World-State contracts 3 with zero failures/skips. The next bounded repair preserves campaign state, protocol identity, ordered trial history, and referenced receipt custody when campaign creation is repeated. Local regressions passed 160/160; hosted verification for this source repair remains pending. Federation Health has no scheduled execution on current main by 13:35 UTC; sequence-379's changed-output publication setting remains unresolved.

Latest verified main: `d70d63b31416f21bcc50b4c2a4708c6c822ff5e6`; tree `c2d41c644daec56a285bae564cb482831570652a`.
Latest construction segment: `work/construction/segments/0380-preserve-self-reflection-campaign-progress.md`
Latest segment SHA-256: `12919099c8a5b386209f021bbd72df1f0240b08e7dcd252739c14148e91c4fdc`
Sequence: 380

Local sequence-380 pre-commit finalization failed closed on the offline docs toolchain and Administrator-only strict audit stages; focused tests, targeted mypy, baseline, and prompt-boundary checks passed. Its two runtime audit rows are preserved append-only. Hosted verification of the exact campaign change is required before landing.

The pre-commit finalizer was rerun after adding the malformed-state regression and updated exact-node acceptance; it returned the same fail-closed environmental result, and its two appended runtime audit rows are retained.


Sequence 380 source publication now uses the documented generated-runtime-artifact boundary: the candidate inherits the existing remote audit blob, while the two newest privileged runtime rows remain byte-for-byte in the original workspace and are hash-bound in sequence-380 evidence. The exact updated source has not yet been hosted-verified.


Sequence 381 records campaign receipt-lineage revalidation in `run_one()` and `report()`. Exact local regression passed 169/169; all 10 exact acceptance nodes passed. Sequence 380's regular merge is `5da046b5a990a15dbc240053351f74e87393d3a6` with tree `d318bc4fd76b2f2df4e5100c1012727a7704f584`. Exact-main post-merge docs and self-check are pending in the current snapshot. The inspected escrow files are Git LFS pointer stubs and no local model runtime or invocation endpoint is available; no real-model experiment is claimed.

Latest verified main: `5da046b5a990a15dbc240053351f74e87393d3a6`; tree `d318bc4fd76b2f2df4e5100c1012727a7704f584`.
Latest construction segment: `work/construction/segments/0381-revalidate-campaign-receipt-lineage.md`
Latest segment SHA-256: `6e8a96b9c7af90bc97bf32d753079fdf0ec7d4786ccc7253000ae47549b17e93`
Sequence: 381


Post-merge evidence is now complete for sequence 380. Exact-main QG artifact #12139099532 matched its published SHA-256 and confirms Administrator UID 0, strict audit, immutability, and 29/29 acceptance. CI/source-validation artifacts #12140375527 and self-check #12139658216 matched their published digests; source validation passed 34/34 across its three groups, and self-check reported 143 passed, 13 setup-phase skips, zero failures. Scheduled Federation Health run #39136688867 on `5da046b5a990a15dbc240053351f74e87393d3a6` succeeded with Administrator verification and reported 1 node, 0 recent events, quiet. Its artifact #12139992259 matched its published SHA-256; publication created no PR because the output was unchanged.

Latest construction segment: `work/construction/segments/0381-revalidate-campaign-receipt-lineage.md`
Latest segment SHA-256: `fbda4e5f917f85335cdbcdd3cbc6c15bb9f34bcfefabba906b82a87c16703e80`
Sequence: 381


Sequence 382 records an isolated campaign-report custody repair. PR #2371 exact candidate 045dc196c641cecbb3b9cf2313ed05187fd73d4c passed its hosted checks and remains open as a draft. The local Git object stores do not contain that candidate, its parent 5da046b5a990a15dbc240053351f74e87393d3a6, or its tree, so exact-source metadata guard validation and merge were not possible. A public clone attempt failed at the configured proxy. The original dirty and protected workspaces remain unchanged.

The report race was reproduced: after full receipt validation, replacing a receipt with a different valid receipt before report scoring changed the old implementation's output. The isolated source now scores the verifier-returned receipt mappings directly. Campaign tests passed 21/21; exact acceptance passed 1/1; module-targeted mypy, py_compile, pip check, and diff check passed. This increment is local and unpublished; it is based on local commit `0ed3caf3d483dc49d6000343fc74f3a6ee9e5a8d` tree `c2d41c644daec56a285bae564cb482831570652a`, not a verified descendant commit of PR #2371.

Latest verified main: `5da046b5a990a15dbc240053351f74e87393d3a6`; tree `d318bc4fd76b2f2df4e5100c1012727a7704f584`.
Latest construction segment: `work/construction/segments/0382-score-only-the-verified-campaign-receipt-snapshot.md`
Latest segment SHA-256: `f6aebe00e4978c623108e36e42a0880ded87869d5572b0c13209c855c2bd1704`
Sequence: 382 (unpublished local increment)


Sequence 383 serializes campaign trial execution, campaign creation/re-entry, recovery, and report publication under the native private interprocess lock. An active executor can no longer be mistaken for a dead process by concurrent reconstruction. The campaign/transition/capability/rehearsal regression set passed 149/149; both exact serialization acceptance nodes passed 2/2. The repository mypy baseline reported zero new errors and 40 retired records; targeted mypy, compilation, and diff check passed. This increment remains unpublished and is based on local commit `0ed3caf3d483dc49d6000343fc74f3a6ee9e5a8d`, tree `c2d41c644daec56a285bae564cb482831570652a`.

The protected PR #2371 remains a draft at candidate `045dc196c641cecbb3b9cf2313ed05187fd73d4c`, parent `5da046b5a990a15dbc240053351f74e87393d3a6`, tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`. GitHub confirms the candidate is exactly one commit ahead of main, and its listed hosted checks passed. The candidate, parent, and main tree objects are absent from all available local stores; the exact-source metadata guard remains unrun. No finalizer was substituted, no PR metadata was changed, and no merge occurred.

Latest verified main: `5da046b5a990a15dbc240053351f74e87393d3a6`; tree `d318bc4fd76b2f2df4e5100c1012727a7704f584`.
Latest local segment: `work/construction/segments/0383-serialize-campaign-execution-and-recovery.md`
Latest local segment SHA-256: `fe23c11e6972043d93a05c7865f279170fc45c850c12bf43edc2004623b33f95`
Sequence: 383 (unpublished local increment)


Sequence 384 binds `run_one()` to a digest-valid readiness receipt for the exact campaign protocol. Tampered, cross-protocol, status-only, and valid not-ready receipts cannot invoke the executor; the valid exact-transition path remains accepted. The combined campaign/transition/capability/rehearsal set passed 153/153; exact acceptance passed 5/5. The full mypy baseline reported zero new errors and 40 retired records; compilation and diff checks passed. Sequence 384 has its own acceptance manifest; sequence 383's manifest and evidence are preserved byte-for-byte.

This remains unpublished local work on local base `0ed3caf3d483dc49d6000343fc74f3a6ee9e5a8d` / tree `c2d41c644daec56a285bae564cb482831570652a`. GitHub confirms PR #2371 is still open, draft, and one commit ahead of main at `045dc196c641cecbb3b9cf2313ed05187fd73d4c`; its candidate object and required full tree are absent locally. The exact-source metadata guard is not run; no source or PR metadata was published and no merge was attempted.

Latest local segment: `work/construction/segments/0384-bind-readiness-receipts-to-campaign-protocol.md`
Latest local segment SHA-256: `49b917d1a2bf1c89839960761e6feef1393bf36c125e5cfbb8cb6a00840cf7aa`
Sequence: 384 (unpublished local increment)


Sequence 385 reconstructs PR #2371 candidate `045dc196c641cecbb3b9cf2313ed05187fd73d4c` / tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846` into a clean detached checkout using existing local objects and GitHub Git-object reads. Sequences 382–384 are revalidated in a separate candidate-based worktree. The campaign/transition/capability/rehearsal selection passed 150/150; exact candidate-bound acceptance passed 5/5; full mypy baseline had zero new and 40 retired errors; targeted mypy, compilation, diff check, and pre-append custody passed. The separate metadata guard is still blocked because its finalizer/matrix JSON inputs cannot be read from the returned File Service reference. PR #2371 remains draft; no publication or merge occurred.

Latest local segment: `work/construction/segments/0385-recover-and-revalidate-pr2371-exact-candidate.md`
Latest local segment SHA-256: `aa7c2de1e3f7e7305f10c35b22803f80a348282dc1e06c26125d7f640db9418b`
Sequence: 385 (unpublished local increment)


Sequence 386 blocks standalone JSON-backed campaign trials because a digest does not prove canonical owner provenance. The CLI exits before campaign or bundle access; a subprocess regression covers this guard and the positive in-process campaign path remains required. The canonical affected set passed 151/151 with zero skips; exact acceptance passed 2/2; the mypy baseline has 0 new and 40 retired errors; targeted mypy, compileall, diff check, and pre-append custody passed. This is unpublished work atop the exact PR #2371 candidate. The metadata guard remains blocked on unreadable finalizer/matrix artifact inputs; PR #2371 remains a draft.

Latest local segment: `work/construction/segments/0386-block-unverified-campaign-cli-trials.md`
Latest local segment SHA-256: `c18b1d33c4bd96cf603e8fe99a64b6d5fb0fdfee248232c30b7514a8f6c4b891`
Sequence: 386 (unpublished local increment)


Sequence 387 verifies the regular merge of PR #2371 into `main` at `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`, tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`. The exact candidate’s eight PR checks passed; exact-main CI, Required Quality Gate, Codex CI, Docs Deploy, Invariant Tests, and Docker Image passed, while Forge Smoke was skipped by workflow conditions. The contract places the metadata guard before PR publication, not before merging; solo profile was configured and exhaustive matrix was not requested. The preserved sequence-382–386 source changes passed the fresh affected 151-test suite, exact post-merge acceptance, targeted mypy, compilation, diff, and continuation custody checks on a clean isolated worktree with the same source tree. Those source changes remain unpublished and are not claimed as part of PR #2371.

Latest verified main: `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`; tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`.
Latest construction segment: `work/construction/segments/0387-reconcile-pr2371-merge-and-preserve-campaign-work.md`
Latest segment SHA-256: `6a4db18c342e116ba039a34deb0d6b01cdaed02a94ec3bf97f2fb26e482f4688`
Sequence: 387


Sequence 388 repairs the exact configured ASCII privilege banner missing from the new campaign CLI test. The failure was found by the remote CI self-check after the initial post-merge candidate passed hosted QG; it was reproduced locally and fixed without suppressing the linter. On the repaired local tree, the affected 151-test set, exact acceptance, full privilege lint, targeted mypy, compilation, and diff checks pass. The hosted follow-up checks for this repair are pending.

Latest verified main: `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`; tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`.
Latest construction segment: `work/construction/segments/0388-fix-campaign-cli-test-privilege-banner.md`
Latest segment SHA-256: `d49788a4dabf1f19e1e8b83b3627df497db482e54a2a21ac5c2dbfc9c3b3c97d`
Sequence: 388

Hosted source-candidate parent at the sequence-388 follow-up: `abd33e735064a068d00a4f344893ce30fb82cf14`; tree `acc822896c4b5e9f532c277c00799e350301c0c4`.


Sequence 389 adds the missing hosted pre-publication PR metadata verification path to Required Quality Gate. Locally, the exact workflow contract test passed; the related workflow/finalizer/metadata-guard test selection passed without failures (environment-dependent finalizer cases were skipped locally); YAML parsing, compilation, and diff checks passed. Construction custody passed through sequence 388 before this append. GitHub CI, actual Administrator precommit finalization, and the metadata guard for this new candidate remain pending and are not claimed. The exact candidate is based on verified construction head `ef8609ceb96dc207432c2070bee6f0dcf0ba420a`, tree `b070bf198e4d8d3b72b1fdd9a2018243feaedacb`; latest verified main is `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`, tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`.

Latest construction segment: `work/construction/segments/0389-hosted-prepublication-guard-in-required-quality-gate.md`
Latest segment SHA-256: `743515597b188bdcb31d3081083934042c5b30ed1ad559f36ad60289882af7e8`
Sequence: 389 (hosted verification pending)


Sequence 390 repairs the actual hosted sequence-389 QG failure: detached worktree creation tried to download a missing LFS model object. Reconstruction now uses `GIT_LFS_SKIP_SMUDGE=1`, preserving the repository checkout's pointer form. The exact hosted workflow contract test passed 1/1 with no skips; task acceptance and diff checks passed. The hosted repair has not yet run. Failed QG evidence remains attached to run `39158284969` and is not reclassified as success. This candidate is based on construction head `0c3948d281cd64e55cba005525277c9330379642`, tree `d867fcca4fa88463ad275f26c2724c887a4fc7fd`; latest verified main remains `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`, tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`.

Latest construction segment: `work/construction/segments/0390-preserve-lfs-pointer-form-in-precommit-worktree.md`
Latest segment SHA-256: `10f62a155ad6dd8c3007bad53d554904184c33402ae2e37b3dfd5304b2114b98
Sequence: 390 (hosted verification pending)


Sequence 391 fixes a second source-caused failure in the hosted precommit workflow: it now reads the runner's canonical `git_sha` provenance field and compares it to the exact reconstructed parent. The failure from QG run `39158544727` remains recorded as a failed hosted check. The corrected workflow contract test passed 1/1 with zero skips; its task acceptance is ready. The fix awaits its exact-candidate hosted run. Candidate parent is `e3259f8dd59108842aa287a83e31bbba3358fdc0`, tree `6eb37dd027479c3da0b9caa7de7e669372402909`; latest verified main remains `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`, tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`.

Latest construction segment: `work/construction/segments/0391-bind-precommit-provenance-to-canonical-git-sha.md`
Latest segment SHA-256: `103b2540efb666420bf9aa5e5f5202432dd99b0c21263ce4a0cff5ff3820c432`
Sequence: 391 (hosted verification pending)

Sequence 392 repairs the hosted precommit finalizer's missing documentation dependencies using the repository's guarded minimal bootstrap with actual hosted Administrator authority. The local hosted-workflow contract test passed 1/1 with zero skips and acceptance is ready. Hosted rerun is pending; run `39158737729` remains a failed result, and no finalizer/guard success is claimed. The source candidate is `bfbb1abd21200a1ffc8e0be5ede5de5c307724bd`, tree `6b0dd48681b209223147dca6fd752759894ecb47`.

Latest construction segment: `work/construction/segments/0392-bootstrap-docs-for-precommit-finalizer.md`
Latest segment SHA-256: `514b714cc9e96e2cb8254b54f6f7c6c2cf2318fba48b7cd3622ca1982ca881dc`
Sequence: 392 (hosted verification pending)

Sequence 393 binds the PR finalizer and metadata guard to a detached checkout of the exact PR head, with a fresh 29-node candidate-bound acceptance run. The local workflow and evidence-binding regressions passed 2/2 with zero skips; hosted validation remains pending. This prevents GitHub's synthetic merge checkout from being associated with PR-head precommit evidence. Source candidate: `5f87e1b36bd93a07983ada6f6735ce3e893dba48`, tree `8f9b5b2721fc0e4ecdbbc4c3753e0ad49af6a569`.

Latest construction segment: `work/construction/segments/0393-bind-pr-finalization-to-exact-candidate.md`
Latest segment SHA-256: `ebb483c56a6e5f80d4d1d3a3dc428302b3b643b91718eae31e1414bbee5c5d4d`
Sequence: 393 (hosted verification pending)

Sequence 394 hardens immutable campaign evidence publication with descriptor-bound private custody, atomic first-writer semantics, symlink rejection, collision detection, and a 16 MiB bound. The full campaign module passed 29/29, exact acceptance passed 2/2 with zero skips, changed-module mypy, compilation, privilege lint, and custody checks passed. Hosted verification remains pending. No inference or runtime authority was added. Source candidate: `9d77f455557b4f408eb1f77cefe528c3b780297d`, tree `a9bd6b476303e421b4d547837fda0c1932af031c`.

Latest construction segment: `work/construction/segments/0394-preserve-immutable-readiness-evidence.md`
Latest segment SHA-256: `21a93ee2b05f56c860f6b5a5ad12f7b98b9a81d26c36abeb2dcdcecd12cc1f35`
Sequence: 394 (hosted verification pending)

Source candidate parent: `1bbd4abd0bb6d33870b9a79b90248f079a06ddba`, tree `297983b58b80346ab7fc8157754d3ca9ba783293`.
Latest construction segment: `work/construction/segments/0395-audit-before-hosted-bootstrap.md`
Latest segment SHA-256: `295ecc09d5e5df05caf20210a84d80f54e3052065a587cf8c3f7073c5fb81063`

Sequence 396 repairs the hosted QG cleanup failure. Run `39162183378` passed strict audit, immutability, and reached `ready_to_commit`, then failed because the runner lacked permission to remove the root-owned detached precommit worktree. Precommit and exact PR candidate cleanup now require exact `$RUNNER_TEMP` paths and use `sudo -n git worktree remove` with Git trust scoped to the main workspace. Overall QG remains failed pending rerun; no finalizer/guard completion is claimed. Source parent: `2222fe85292b36f8277465b99cf42ed99b3fd041`, tree `396547271a26186a8ffb749e94831679efc99328`; latest verified main: `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`, tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`.

Latest construction segment: `work/construction/segments/0396-remove-finalizer-worktrees-with-scoped-admin-custody.md`
Latest segment SHA-256: `9a3ce041ccdfd4a555e0bb727f3a43a3322d6609d189136f13cb874ab677a150`
Sequence: 396 (untested; hosted verification pending)

Sequence 397 improves hosted failure observability for the exact PR metadata guard. Sequence-396 run `39162397893` passed strict audit, immutability, all 29 required nodes, and both finalizer phases, but the guard failed and its redirected JSON reasons were not emitted before `set -e` stopped the job. The workflow now captures the status and emits exact guard reasons while preserving fail-closed behavior and unchanged criteria. Hosted rerun remains pending; no guard success is claimed. Source parent: `b935c6ec34007111df491801ce277f865f434a34`, tree `0fd3cbc04c170217675f09b3776818f33101ad24`; latest verified main: `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`, tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`.

Latest construction segment: `work/construction/segments/0397-surface-metadata-guard-failure-reasons.md`
Latest segment SHA-256: `c8d93b036f87fdf6649a14e021fdc431cf0b3956c3ca40ccfd73eba6c7d52d04`
Sequence: 397 (untested; hosted verification pending)


Sequence 398 resolves the acceptance lineage mismatch diagnosed by the sequence-397 hosted gate. The exact transition verifier now accepts a manifest/provenance digest change only across the verified workspace-parent to exact-candidate SHA boundary and only when readiness, classification, exact required and successful node IDs, call-phase outcomes, and passing witness summaries match. Targeted metadata guard tests passed 29/29 non-legacy cases (14 legacy cases remain skipped under the repository marker policy); hosted workflow contract test passed; changed-module mypy, compilation, and diff checks passed. Documentation build succeeded at 614 pages. Sequence-397 CI and invariants passed; its required gate remains recorded as failed for the diagnosed transition mismatch. Sequence-398 hosted verification is pending. Parent: `efc6ac6c906601445b8b1fc88597101bcfd6180e`, tree `be7bb0fe2d65cd44f006e4cf151fd2143d0b7390`; verified main: `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`, tree `65ab41d1842e26ed0d9e5dcd05b8db8e8f84d846`.

Latest construction segment: `work/construction/segments/0398-allow-exact-task-acceptance-source-rollforward.md`
Latest segment SHA-256: `1e561ea6e6b574e3364a2c96da9b59fb2a5eeb2b91a9bb02b347fd702b51bf1e`
Sequence: 398 (local checks passed; hosted verification pending)


Sequence 399 repairs the exact PR-event finalizer failure from run 39163615834: task acceptance was reverified from the synthetic merge checkout after being bound to the detached PR-head worktree. The verifier now runs from that exact worktree; a workflow contract test binds the cwd to the candidate. Malformed acceptance reports also return explicit blocked decisions instead of raising. Focused landing/workflow tests passed 150 with 16 legacy skips; targeted mypy, compilation, and diff checks passed. Sequence-398 push QG passed; sequence-399 hosted checks are pending. Parent `320ab95e9073eb043eab5fd8169ea3865b368d67`, tree `7de4093d83f76a2d88ee79edbc20320f15639038`; main `8a2b6807e7868fcf67dfbe6b11b650d4ad020837`.

Latest construction segment: `work/construction/segments/0399-run-candidate-acceptance-from-exact-worktree.md`
Latest segment SHA-256: `2433a5d10bc05ce102f15d936782fd6060e8ca09cb46a60fcf9e7ec809593bc8`
Sequence: 399 (local checks passed; hosted verification pending)


Sequence 400 closes the mutable nested campaign-protocol gap before execution. Exact campaign tests passed 30/30; compilation, focused mypy and diff checks passed. The local mypy baseline wrapper remains blocked by its isolated-venv import environment. The verified parent main `ae55461e13be358c2754c7686b381ae2d72daa63` has successful Required Quality Gate, CI, Docker, Invariants, Docs Deploy and Codex CI runs. A Federation Health schedule on this main SHA is still pending.

Latest construction segment: `work/construction/segments/0400-revalidate-mutable-campaign-protocol.md`
Latest segment SHA-256: `dbe6a950ef7152794a3d49a5d5556bf7fe30a0f89227e8b4d080ad450a9acbf9`
Sequence: 400 (hosted candidate checks pending)


Sequence 401 isolates execution from caller mutation through a verified campaign protocol snapshot and serializes concurrent immutable publication without weakening first-writer custody. Campaign tests passed 31/31; the collision regression passed ten repeats; all seven selected dependent owner suites completed successfully. Compilation, focused mypy, and diff checks passed; repository baseline mypy wrapper remains blocked by the isolated environment. Sequence-400 exact PR Required Quality Gate passed (#39164845405); sequence-401 hosted verification is pending. Parent candidate `6cbdea630933d7e3247da5711f4df898a040d011`, tree `c2d9e42a8ac50bbcd75c8b407f8284f8a9621381`.

Latest construction segment: `work/construction/segments/0401-snapshot-campaign-protocol-and-serialize-immutable-publication.md`
Latest segment SHA-256: `212f1c815eff31870bb1f553e95eca4e8681491f7195110099c77012a70639f4`
Sequence: 401 (hosted verification pending)


Sequence 402 records exact-main post-merge verification for the sequence-401 merge and restores the 77 missing construction-index bindings for sequences 189–265 from the last complete committed index. The sequence-266 evidence pointer was also restored from that index. All retained pairs were verified against bytes; the only preexisting row digest error was sequence 196, whose corrected retained-byte hash is supported by sequence 197 evidence. The complete 1–402 predecessor chain now passes strict custody with zero failures. No prior source or evidence bytes changed. The Required Quality Gate and every configured post-merge push check succeeded except configured Forge Smoke skip. Canonical planning and execution separation passed, including the verified prior-epistemic-owner allocation test and the planning-without-execution proof. Current-main Federation Health and the next scheduled nightly executions remain pending; historical scheduled or push events are not substituted for those events.

Latest construction segment: `work/construction/segments/0402-verify-sequence401-postmerge-main.md`
Latest segment SHA-256: `d64ad9535191b45284bc31158b11b78034248d575e9a097b4e5a8a9c4d31e4ae`
Sequence: 402 (post-merge checks and construction custody verified; scheduled production-workflow observations pending)
