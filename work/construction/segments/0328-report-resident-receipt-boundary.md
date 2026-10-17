# Sequence 328: report the exact resident receipt boundary

## Source and observed failure

This diagnostic continuation starts from sequence 327 candidate `31f0509604b9f058b42c26bd4e8a32a86b36c676`, tree `4c90ccac8a1103baa7b517eed4c6324fb0267741`.

Quality Gate run `39075726571` executed the updated positive PID-reuse test but failed before reconstruction while parsing `parent-receipts.jsonl`: `parent_receipt_journal_truncated`. The exact acceptance selection and strict audits executed; the test result remains failed and the finalizer did not run. This is the first concrete cause behind the earlier `panic_latched`: recovery custody cannot proceed from a receipt journal that fails its append-only newline contract.

## Diagnostic change

The regression now asserts the journal terminates with the required newline before parsing and includes the byte count and trailing bytes in a failure. It retains the canonical parser and all fail-closed checks. No journal repair, truncation, or recovery bypass is introduced.

## Verification boundary

Compilation and diff checks passed. The next hosted run must reveal the exact final journal bytes, after which the source or fixture cause will be repaired. The positive transition remains unverified; no failure is suppressed.
