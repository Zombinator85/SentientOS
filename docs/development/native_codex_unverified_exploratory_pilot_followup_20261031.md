# Native Codex Exploratory Pilot Follow-up — 2026-10-31

This follow-up records publication and a reproducible consistency check for the
pilot described in
[`native_codex_unverified_exploratory_pilot_results_20261031.md`](native_codex_unverified_exploratory_pilot_results_20261031.md).
It does not alter the original preregistration, observations, scores, or results
commit. The earlier report's pending-publication paragraph records the state at
the time that results commit was prepared; the publication status below is the
later update.

## Publication

The original preregistration commit
`3f7164cc7d00de2bdbb0939a3ab9d45e9ce20adf` was merged in PR #3144 at merge
commit `2f1d9f67b4fdf47b033d6c97049aa5c01a664d38` after the exact-commit
`Required / Quality Gate` passed.

The original results commit
`df92265fc3911bc258e6469dc609d63490eb549c`, whose parent is the preregistration
commit, was merged in PR #3145 at merge commit
`69df5f9ed1e978cc90ba73a873621adc45701c73` after its exact-commit gate passed.
The two original commits were not amended or reconstructed. The original
`gpt-6-astra` experiment remains at 0/12 valid observations; the 12 captured
responses belong only to the separate native-task condition with unverified
subject model identity.

## Reproducible consistency check

Run from the repository root:

```bash
python -m scripts.verify_native_codex_pilot_results
```

The verifier checks protocol and capture-manifest digests, each observation and
score file digest, exact prompt and response bytes, score-to-response stance
consistency, per-condition counts, and corrected-versus-pressure-only pairings.
It prints a machine-readable summary. It never opens the held-out answer key.

This is an integrity and internal-consistency check, not a fresh scoring pass.
It does not independently establish that expected stances are correct, that the
subject model was a particular model, or that the findings generalize beyond
these 12 observations.

## External backup status

The Git commits and experimental results are published in the repository. A
separate encrypted backup of the held-out key is attached to an owner-only Page,
but its binary contents have not yet been independently downloaded and verified.
Keep the protected local key copy and managed workspace intact until a separate
retrieval path verifies the backup. This outstanding custody check does not
block ordinary SentientOS development.
