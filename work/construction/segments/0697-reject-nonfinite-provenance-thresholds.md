# Sequence 697: reject non-finite provenance thresholds

The provenance trend analyzer rejected negative thresholds but accepted `nan` and infinities because comparisons with NaN do not behave like ordinary numbers. Its environment defaults were also converted to floats before argparse validation, bypassing the threshold validator. The shared float validator now requires finite, nonnegative values, and every environment threshold default goes through that validator. Regressions cover NaN and both infinities, including a non-finite environment default.

The tested code-only tree is `1e8f9c95eac3eccaa363aacd5015725c6dfcfd84`, based on verified main `92dcdbbfe3e74071c85a790be2c410b3de00d300` / `345a413f1bf2f6f8ddcc7b7b9647c358bf6649eb`. The focused analyzer suite passed six runnable tests; eleven legacy-quarantined tests were skipped. Targeted mypy, syntax compilation, and diff checks passed. Documentation is unchanged. The frozen v1 anchor and prior v2 shards remain unchanged.

Evidence record: `work/construction/evidence/0697-reject-nonfinite-provenance-thresholds.json`
Evidence SHA-256: `3960cc3db5c921785360235dd288fa9e2320deb42670d408bd3fd1770d5d4164`
