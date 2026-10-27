# Sequence 889: fix hosted Quality Gate failure-line reporting

The hosted Required Quality Gate previously reported the line inside its `ERR` trap function, obscuring the command that failed during pre-commit reconstruction. The correction captures `${BASH_LINENO[0]}` at trap entry with `${LINENO}` as fallback and prints that caller line. A Bash reproduction reported the failing call site as line 11 while the handler itself was line 5.

The focused static regression assertions and the complete `tests/test_github_hosted_acceptance_workflows.py` file passed (58 tests) on verified main `402a2ae423d67113e70c64e841cf12f27d77d1d3` with this two-file patch. The exact Administrator assertion `test "$(sudo -n id -u)" = "0"` remains present and asserted; no privilege requirement changed. The patch-only tree was `5d5f8c0306af4beabd1860941b8484a51876b288`.

The base PR #2968 merge was verified on remote main, all eight exact-candidate workflows and six required post-merge workflows passed, and custody verified 888 predecessor sequences before this append.

Evidence record: `work/construction/evidence/0889-fix-hosted-quality-gate-failure-line-reporting.json`
