import pytest
pytestmark=pytest.mark.no_legacy_skip
from sentientos import maintenance_loop_watchdog as w

def test_implementation_brief_is_deterministic_and_closed():
    c={'candidate_id':'c','candidate_revision_digest':'d','objective':'o','declared_subject_paths':['b','a'],'declared_validation_expectations':['z']}
    assert w.build_implementation_brief(c,{'admission_digest':'x'},{'base_sha':'s'}) == w.build_implementation_brief(c,{'admission_digest':'x'},{'base_sha':'s'})
