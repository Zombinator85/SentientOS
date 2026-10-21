# Sequence 534 — sample stage-approval time offset once

Stage approval freshness validation previously checked `tzinfo.utcoffset()` and then called `astimezone()`, which may call a custom offset provider again. A changing provider could therefore make validation accept a different instant than the one it checked. The verifier now captures one explicit offset and normalizes that sampled wall time arithmetically; unknown offsets and invalid conversions fail closed before any transition effects.

Added an adverse dynamic-timezone regression that asserts one offset read, rejection, no journal entry, no gate quiescence, and unchanged phase. The regression is selected by both CI source validation and hosted acceptance. Existing approval binding and authority checks are unchanged.

Local verification: 2 focused regression/acceptance tests passed; all 42 tests in the transition-experiment module passed; `compileall` passed; targeted Mypy passed with no issues. No production transition, activation, serving, inference, or writeback was performed.

Verified base main: `155eb48b60afda086eeaa03b75b02fc4062907f8`, tree `d47f882f9a86968fd7d8cadd352b3bdb2f3a8b9a`
Implementation candidate: `f2ca9c28e02ff5cb4ee45f854bcae05c48f5371c`, tree `675c7bdd291a7107f881ca368d523543220f8de7`
Latest construction segment: `work/construction/segments/0534-single-sample-stage-approval-clock.md`
Sequence: 534 (candidate pending hosted verification)
