# Sequence 203 — Reject timestamp substitution and completed-tick replay

Starting HEAD: `a5597aba9ac79fcef2b0156ab7643e399ec2f7cd`; the seq202 source tree was `024e7f710ce4c94a76a10d3de77f510549659791`.

Added two recovery adversaries to the fresh-process canonical integration. First, a source consequence timestamp is changed in a copied durable record without changing its bound identity; a newly reconstructed owner rejects read-only inventory inspection with `record_digest_mismatch` before the altered chronology can affect relevance. Second, the fresh owner is asked to replay its just-completed distinct task; the owner rejects it as `tick_already_completed`, and the admitted record inventory remains unchanged.

Validation: integrated adversarial node passed; affected suites passed (121 passed); compileall and diff check passed. Synthetic fixture evidence only.

Source commit: `32b3868dde213403828720ec3dcc5e097e8d6a08`; tree `2b9a60bfb5987574075c8470e079ccaf116d1483`.

No receipt or admission authority was fabricated, and no history record was rewritten into a valid substitute identity. Continue with the remaining longitudinal and cross-model composition work.
