import pytest
pytestmark = pytest.mark.no_legacy_skip

from tests.maintenance_lease_fixtures import artifacts, NOW
from sentientos.maintenance_task_authority_lease import verify_grant

def test_grant_digest_tampering_is_rejected(tmp_path):
    *_,g=artifacts(tmp_path); g['maximum_file_count']=99
    assert 'grant_invalid' in verify_grant(g,evaluation_time=NOW)['reason_codes']
def test_grant_expiry_uses_explicit_evaluation_time(tmp_path):
    *_,g=artifacts(tmp_path)
    assert verify_grant(g,evaluation_time='2026-08-07T00:00:00+00:00')['reason_codes']==('grant_expired',)
def test_unknown_authority_class_is_rejected(tmp_path):
    *_,g=artifacts(tmp_path); g['allowed_authority_classes']=['root']; from sentientos.maintenance_task_authority_lease import seal_grant; g=seal_grant(g)
    assert verify_grant(g,evaluation_time=NOW)['status']=='grant_invalid'
