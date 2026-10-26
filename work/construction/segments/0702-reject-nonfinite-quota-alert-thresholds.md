# Sequence 702: reject non-finite quota alert thresholds

Quota alert threshold parsing now accepts only finite fractions in `[0, 1]`; invalid values are rejected by argparse before usage records are read or Slack is contacted. The tested code-only tree is `6256bc666c38d69f483536849d5c23b03038810a`, based on verified main `7cf60733700eefd56dbcdb8328a920bb5ee4f4b9` / `8744d52d29a7ecb0ecf0ce3f89dbb1dc54dbd302`. All 13 focused regressions passed, targeted mypy and privilege lint passed, and Python syntax compilation and diff checks passed.

Evidence record: `work/construction/evidence/0702-reject-nonfinite-quota-alert-thresholds.json`
Evidence SHA-256: `aa4d540914534544a5e55f5e63e334cfae5a647aef576f87b99e8c6b21ae3467`
