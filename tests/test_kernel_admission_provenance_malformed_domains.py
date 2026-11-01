from __future__ import annotations

import pytest

from sentientos.kernel_admission_provenance import _compose_trust_posture

pytestmark = pytest.mark.no_legacy_skip


def test_malformed_domain_lists_are_ignored() -> None:
    result = _compose_trust_posture(
        mode="baseline",
        issues=[],
        intent_checks=[{"expected_domains": object()}],
        execution_consistency_checks=[
            {
                "expected_domains": object(),
                "observed_side_effect_domains": object(),
            }
        ],
        non_bypass_checks=[],
        covered_relevance_domains={"genesisforge_lineage_proposal_adoption"},
    )

    global_scope = result["global_covered_scope"]
    assert isinstance(global_scope, dict)
    assert "genesisforge_lineage_proposal_adoption" in global_scope["domains"]
