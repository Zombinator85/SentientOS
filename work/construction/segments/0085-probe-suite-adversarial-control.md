# 0085 — Reject malformed multi-probe answers as successes

Source baseline: `1d3c0aaf8240424576f8fa2e42bd3d1ec124d7a8`, tree `c46ff57562c1c4bd9c6dcc70add05213ffa0eddd`. Added a negative control for the new bounded probe-suite scorer: a fixture endpoint returns duplicate JSON keys in place of the required answer array. The run remains a completed observation, but every suite score is `invalid_answer` with `correct=false`; malformed output is not promoted to a successful performance result.

Focused objective-scoring module: **20 passed, 0 failed, 0 skipped**. Python compilation and `git diff --check` passed. Evidence: `work/construction/evidence/0085-probe-suite-adversarial-junit.xml` and `work/construction/evidence/0085-probe-suite-adversarial-results.json`. This remains fixture acceptance, unverified for production.

Next: check exact hosted workflow results for seq84; then inspect the adjacent existing behavioral/recovery owners for concrete gaps. Real-model experimentation remains blocked on actual model payload custody and the exact preregistered commissioning/approval requirements.
