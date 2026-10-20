# Sequence 494 — restore nightly workflow trigger coverage

## Trigger repair and current-head runs

PR #2489 expanded the Nightly Audit Integrity and Nightly Self Check path filters to include their verifier, repair, test, dependency, and audit inputs. The contract test pins the exact expected path sets. The scheduled cadence, strict Administrator checks, and minimal permissions were preserved.

The change merged as 0ac5125cafd104df0b72d40207bae19eecf6faba, tree f5e2dff52fd1c54478e01d0bb38ceff5cfc08cae. On that exact main head, Nightly Audit Integrity run 39403772754 succeeded after the hosted Administrator preflight and strict audit verification; its repair job was correctly skipped. Nightly Self Check run 39403773009 also succeeded on that head: Administrator preflight, audit verification, privilege lint, Mypy, airlock, and full pytest passed (143 passed, 13 skipped, 0 failed).

These were push-triggered executions on the repaired paths, not scheduled executions. At the time of this record, no post-merge scheduled Federation Health execution on the exact main head had been observed. The latest known scheduled run remained bound to older head 800dcef026b32c45c5668282b260ca2e39ab4c24; its report generation succeeded but publication failed under the repository's Actions-token PR-creation policy.

## Limits

The publisher still needs an appropriately scoped credential or a deliberate repository policy decision. No broader workflow write authority or weakened Administrator gate was introduced.
