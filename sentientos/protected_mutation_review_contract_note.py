"""Review contract note for covered protected-mutation corridor.

Review contract is a narrow machine-readable review-expectation layer derived
from escalation posture for the currently covered corridor only. It does not
add remediation, approval workflows, or a broad governance engine.

Mapping:
- none -> none
- observe -> observe_on_touch
- forward_block -> explicit_review_before_protected_change
- strict_block -> strict_review_required
- verification_attention -> proof_review_required

Interpretation:
- observe_on_touch: observational review recommendation for legacy-only posture.
- explicit_review_before_protected_change: forward-blocking review expectation
  before further protected mutation in that domain.
- strict_review_required: strict-blocking highest review posture.
- proof_review_required: proof/integrity review attention posture.

Trust posture, escalation posture, and review contract are separate fields:
- trust posture classifies evidence/trust state.
- escalation posture classifies operational stance.
- review contract classifies review expectation.

Scope remains the currently covered protected-mutation corridor only.
"""

REVIEW_CONTRACT_NOTE = __doc__
