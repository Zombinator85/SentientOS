from __future__ import annotations
import json
from pathlib import Path
import pytest
from scripts.run_host_local_diagnostic_rollback_runtime import main
from tests.test_host_local_diagnostic_rollback_runtime import _args, _execution
pytestmark=pytest.mark.no_legacy_skip

def test_cli_executes_exact_rollback_and_validates_historical_bundle(tmp_path:Path,capsys)->None:
    f,e,digest,_=_execution(tmp_path); _,p,args=_args(tmp_path,f,e,digest); snapshot=tmp_path/'snapshot.json'; verification=tmp_path/'verification.json'; snapshot.write_text(json.dumps(f.snapshot)); verification.write_text(json.dumps(f.verification)); ch=p.records['confirmation_challenge']
    base=['rollback','--execution-bundle-root',e.bundle_root,'--expected-execution-bundle-digest',digest,'--current-snapshot-json',str(snapshot),'--current-verification-json',str(verification),'--rollback-time',args['rollback_time'],'--output-root',str(tmp_path/'cli-rollback'),'--confirm-exact-rollback','--confirm-execution-bundle-digest',digest,'--confirm-artifact-path',ch['historical_artifact_path'],'--confirmation-challenge-digest',ch['confirmation_challenge_digest'],'--correlation-id','cli-proof']
    assert main(base)==0; result=json.loads(capsys.readouterr().out); assert result['rollback_call_count']==1; bundle=result['bundle_root']; final=json.loads((Path(bundle)/'bundle_manifest.json').read_text())['bundle_digest']; assert main(['validate-bundle','--bundle-root',bundle,'--expected-final-bundle-digest',final,'--expected-execution-bundle-digest',digest])==0
