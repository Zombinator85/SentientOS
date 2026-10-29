# Sequence 965: integrate PR #3044 and finalize linkcheck measurements

Sequence 964 was published through PR #3044 as candidate 03d0ecec011999c08964194753e8eeccce86997d with tree 60d38c93ed781b50417e6c2f148f5aa9f2b00f9f. The Required Quality Gate initially stopped at its metadata preflight because the PR title did not match the exact commit subject. The PR title was corrected; the rerun completed the hosted pre-commit and privileged landing finalization successfully. CI, Docker, Codex CI, Invariant, Gradient, Release, and Lint passed on the exact candidate. The separate push-triggered Invariant Tests workflow passed.

PR #3044 merged normally as b8955222c06e88dcf19a220df033c9eac7aac03d; remote main and merge tree 60d38c93ed781b50417e6c2f148f5aa9f2b00f9f exactly match the candidate. Post-merge CI, Codex CI, Docker, Docs Deploy, Invariant Tests, and Required Quality Gate passed; Forge Smoke was skipped by condition. Main CI's append-only custody verification passed through all 964 predecessors.

The linkcheck investigation found default Sphinx 8.2.3 settings (five workers) passed strict linkcheck on the PR in about 2m13s and on main in about 2m12s, with no observed 429 events. The one-worker PR #3043 run took about 7m15s and logged six 60-second 429 backoffs, so it remains closed and unmerged. This evidence supports keeping the current strict check unchanged; it does not establish worker count as the sole cause of run-to-run differences.

The repository-supported focused custody, v3-index, and candidate-publication tests passed (53 tests). Full continuation custody is ready through sequence 965.
