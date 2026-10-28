# Sequence 912: confine causal-introspection custody ancestry

Causal-introspection configuration reads and snapshot custody previously protected only the leaf file/directory. On POSIX systems with descriptor-relative APIs, configuration parents are now walked with `O_NOFOLLOW`; snapshot ancestry is opened one component at a time and the stable directory descriptor is used for listing, bounded reads, staging detection, and immutable publication. Unsupported platforms keep component checks and existing leaf protections. Symlink-parent regressions cover config loading and custody capture; predecessor reconstruction, immutable publication, and staging recovery remain covered.

This is an `[untested]` construction increment until hosted Required Quality Gate and CI validate the exact candidate. Local strict Administrator audits were not run under the documented construction path. No custody, authority, effect, or production-activation requirements were weakened.

Candidate implementation commit: `26d286a8b9e602b23fc3f98ff5ee242bb2e730c2`, tree `2a11ea79ae72042e8f05bc9e191c9f73a4239313`, based on verified main `31a35d9584f712502b97b59e991ffa49f8d8fbba`, tree `ee0f2f5b3768011fbdc6129bd908a7d3fb679cf5`.

Focused tests: 82 passed, zero failed or skipped across causal-introspection, daemon composition, and runtime-closure suites. Exact task acceptance passed, targeted mypy passed, documentation build generated 617 pages, and `git diff --check` passed.

Evidence record: `work/construction/evidence/0912-confine-causal-introspection-custody-ancestry.json`.
