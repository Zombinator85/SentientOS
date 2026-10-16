# Sequence 208 - Correct sequence-207 receipt digest evidence

The sequence-207 evidence file remains immutable. Its five `writeback_receipt_digest` values duplicate their matching record digests. Inspection of the retained installation and the read-only `inspect_completed_records()` owner inventory found this to be an evidence extraction error, not a receipt integrity defect.

All eight retained record/receipt pairs pass owner verification. For the five affected event records, the original record files, receipt files, receipt semantic identities under the `devreceipt` domain, candidate identities, admission bindings, and source fact/event identities were independently matched. Their recovered receipt IDs and digests are recorded in `work/construction/evidence/0208-sequence-207-receipt-digest-erratum.json`. No replacement run was generated.

A regression test now obtains the verified owner inventory and asserts that the receipt digest comes from `receipt.receipt_digest` and differs from `record.record_digest`. Its focused node passed (1 passed) in the isolated inherited checkout. This is fixture custody evidence only; no provider inference, physical effect, or model improvement is claimed.

Source commit: 534aca931dcf80d19c0947feb07b7dcc4ad44bc1
Source tree: 1fb7a8e07d2c271f36d3fd86e475896d989440e7

Next: prepare the isolated, operator-run multi-situation Codex pilot from actual admitted records and keep scorer materials outside subject-visible artifacts.
