# Sequence 532 — bind transition request validity to one aware clock sample

The operator ingress now requires a real timezone offset from its clock and normalizes one observation to UTC for the request's provenance-key validity, signed request validity, and journal-recovery authentication checks. This removes the prior path where a custom `tzinfo` with `utcoffset() is None` could be interpreted by `datetime.astimezone()` as machine-local time, and prevents multiple clock reads in one admission from observing inconsistent instants. Receipt inspection also supplies an explicitly validated UTC sample. Trust catalog policy, operator identity delegation, signature requirements, and effect-owner gates are unchanged.

Regressions reject naive and offset-unknown observation clocks and assert exactly one sample for a full accepted request path. The new nodes are bound in unprivileged source validation and the acceptance manifest.

Local verification on the exact source candidate passed 46 transition-operator tests, the three focused regressions plus source-validation contract test, compilation, and targeted Mypy with imported legacy modules excluded (`--follow-imports=silent`: no diagnostics in the two touched production modules). A broader Mypy invocation traversed the existing repository imports and reported the repository's known 339 diagnostics across 64 modules; this is recorded as non-passing and is not attributed to or waived by this change. Hosted candidate checks are pending.

No production transition, activation, serving, inference, or writeback was performed.

Verified base main: `9f240e177afc7eb7b67c05e33ca5283b2d8cd598`, tree `38479e185d368011ef331458de875e15746a0643`
Implementation candidate: `14a1e9881e0a710b5701362778473e2fc0ef14b3`, tree `4b64630c16937ab5aea19aa77a251cbbc8150427`
Latest construction segment: `work/construction/segments/0532-single-sample-operator-validity-time.md`
Sequence: 532 (candidate pending hosted verification)
