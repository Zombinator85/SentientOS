# Sequence 697: reject non-finite provenance thresholds

The provenance trend analyzer rejected negative thresholds but accepted `nan` and infinities because comparisons with NaN do not behave like ordinary numbers. Its environment defaults were also converted to floats before argparse validation, bypassing the threshold validator. The shared float validator now requires finite, nonnegative values, and every environment threshold default goes through that validator. Regressions cover NaN and both infinities, including a non-finite environment default.

The tested code-only tree is `c78f7ec5e1928e2cc563436292a2dd748c45f550`, based on verified main `92dcdbbfe3e74071c85a790be2c410b3de00d300` / `345a413f1bf2f6f8ddcc7b7b9647c358bf6649eb`. The focused analyzer suite passed six runnable tests; eleven legacy-quarantined tests were skipped. Targeted mypy, syntax compilation, privilege lint, and diff checks passed. Documentation is unchanged. The frozen v1 anchor and prior v2 shards remain unchanged.

Evidence record: `work/construction/evidence/0697-reject-nonfinite-provenance-thresholds.json`
Evidence SHA-256: `c69d18444e3eed87c90ffb7b0f014cfa4d7d0ec0e0b0875f600046db1afeb887`
