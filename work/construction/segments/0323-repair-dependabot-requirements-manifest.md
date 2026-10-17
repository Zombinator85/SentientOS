# Sequence 323: make optional requirements parseable by Dependabot

## Change

Replaced the INI-style section headers in `requirements-extras.txt` with explanatory comments while retaining the four dependency entries. This preserves the existing dependency set and makes the file valid pip input for Dependabot. Added a regression test that parses every active line with `packaging.Requirement`.

## Verification

The canonical dependency-bootstrap contract module passed 9 tests, including the new parser regression. `scripts.verify_dependency_bootstrap --summary`, task acceptance, compilation, and `git diff --check` completed successfully. Exact test provenance and required-node acceptance are recorded in the source artifacts. The tracked test failure digest was restored byte-for-byte after the test runner modified it; generated XML and report files were excluded from publication.

The local test checkout was `08179763200d24c406da2bebb6b5e1ea52f0c65e` (`b152d3f309a28f27c6d398acd991592f0ce8ed70`) with the task's staged source; publication is based on freshly verified main `1bb5a004e263e0fa13fd20c1dd8ab5d93fc9cf74` (`fe24d3600ac802bf58d0e784f113ea8570a44661`). Local Git transport was unavailable, so the remote source identity and file blobs were read through GitHub. Post-merge CI and Docker were still running at evidence preparation; they are not represented as passing here.

## Prior construction and failures retained

Sequence 322 merged as PR #2321 with append-only history. Its first two privileged Quality Gate attempts (`39072311292`, `39072470951`) failed because workflow dispatch captured stale/mismatched PR titles. Both passed strict Administrator audit and exact acceptance before finalizer title binding failed. The corrected run `39072543856` passed strict audit, acceptance, and privileged landing finalization; all other PR checks passed.

The current main's Dependabot Graph Update `39071515030` failed because pip rejected `[js]` on line 1 of `requirements-extras.txt`. This increment addresses that concrete parser failure without removing dependency entries or weakening update coverage.

## Boundaries and next work

No authority or production behavior changed. The Vow salt key incident remains unresolved: the original bytes are unrecovered and no replacement or rotation was generated. The next architecture dependency remains attributable process-generation termination and proof of no in-flight transition before recovery; stage replay remains fail-closed. The scheduled Federation Health execution for `1bb5a004e263e0fa13fd20c1dd8ab5d93fc9cf74` is not yet observed. The changed-output publisher fixture still requires an explicitly authorized workflow dispatch. Nightly privileged workflow repairs remain pending. Sequence 286 payload loss and the stale sequence-178 workspace remain preserved.
