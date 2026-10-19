# Sequence 424 — Bind manual workflow dispatch to verified main

**Construction status: untested candidate; hosted exact-candidate validation is pending.**

The audit-nightly and nightly-self-check workflows expose `workflow_dispatch`. GitHub permits a dispatcher to select a branch, but those workflows did not restrict the jobs to `main`. In particular, an audit-repair run from another branch could execute that branch's repository code in a job holding `contents:write` and `pull-requests:write`. The Federation Health workflow had the same ref-selection gap across its Administrator health job and write-capable publisher.

The candidate adds `refs/heads/main` job guards to the nightly audit, its repair job, and nightly self-check. It also binds Federation Health's real report path and publisher to main, while keeping the existing fixture path limited to a main dispatch or the exact disposable fixture branch. No workflow permission scope changed: strict audits retain `sudo -n`, audit repair remains the only nightly writer, and self-check remains read-only.

One exact acceptance node, `tests/test_github_hosted_acceptance_workflows.py::test_workflow_dispatch_jobs_are_main_bound`, is added to the Required Quality Gate's call-phase node set; its exact count is increased from 29 to 30. Local YAML parsing, direct workflow-contract assertions, Python compilation, and `git diff --check` passed. The canonical pytest wrapper could not install its editable test package because network access is blocked in this sandbox, so no local pytest success is claimed. Hosted verification remains pending.

The underlying source is sequence-423 candidate `53ba18b4d810510da93a12e30f4e2435d1078be7` / tree `26d88c5f0f3727d9ae02c1db8652a2ff5ef52c7d`, based on verified main `00cedf9c46a24c268a6867d80c2a3f04da6a05c2` / tree `2bfdb289021e00e9f14449a6c938b45dfe7b9703`. Sequence 423's hosted CI, invariants, privileged Quality Gate, and pre-publication metadata guard passed; its evidence branch remains unmerged and untouched.

Post-merge main CI, Quality Gate, Docker, invariant, Codex CI, and Docs Deploy runs have now been independently read back as successful. Federation Health still has no observed post-merge scheduled run as of 05:30:42 UTC. A local manual-dispatch attempt failed because the shell's `GH_TOKEN` is invalid; the GitHub connector supports read-only Actions access. The next Federation Health evidence must come from a future main execution. The two nightly schedules are next due 2026-10-20 at 03:41 and 04:37 UTC.

No production inference, resident transition, or authority expansion occurred. Historical provenance integrity remains `INTEGRITY_BROKEN` at its unanchored start. Prior append-only records and stale workspaces remain preserved.
