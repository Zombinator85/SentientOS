# Persistent epistemic revision qualification

This module is a bounded, read-only evaluator for paired epistemic conditions.
It consumes canonical semantic projections from the existing persistent
epistemic owner and verified cognition observations from the existing resident
cognition owner. It checks the state transition separately from the answer
that the inference request actually returned.

Each preregistered case carries private answer keys and a random nonce. The
reported commitment binds those fields without disclosing the keys. The caller
must keep the keys private until evaluation and independently establish that
they were fixed before the observations; the evaluator reports both
preregistration and oracle independence as unverified. A local case pass does
not establish either claim.

The evaluator verifies the owner observation, session-bound invocation
receipt, exact prompt digest, full relevant semantic packet delivery, output
digest, and untruncated completed or simulated status. Missing packet delivery,
an unavailable answer, a fallback, truncation, or mismatched controls produces
an insufficient result. A delivered malformed or incorrect answer is scored
as a failure. Reports contain digests, structured scores, and case status, not
the raw prompt, answer, or private key.

The six bounded case kinds cover contrary evidence, unsupported pressure,
inference correction without new evidence, retaining a correction, revising
outdated evidence, and model replacement. The evaluator applies only structural
checks: for example, replacement requires changed content identity, and an
inference correction must preserve the evidence set while appending one
permitted correction event. It does not decide whether the evidence justifies
the correction or whether an answer is true; the independent case author owns
those judgments.

This code does not call a provider, run inference, mutate epistemic state,
grant authority, or establish model qualification or causal effects. Tests use
synthetic, session-bound invocation receipts to verify the measurement path.
Real cognitive performance requires a separately authorized experiment with
independent held-out scoring and review of the exact packets delivered.
