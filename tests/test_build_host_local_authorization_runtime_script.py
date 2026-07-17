from __future__ import annotations
import json, subprocess, sys
from sentientos.host_local_authorization_runtime import build_review_request
from sentientos.host_live_grant_readiness_runtime import HostLiveGrantReadinessRuntimeCoordinator
from sentientos.control_plane_kernel import ControlPlaneKernel, LifecyclePhase
from tests.test_host_live_grant_readiness_runtime import _controlled

def test_cli_decision_plan_issue_requires_apply(tmp_path):
    ev=_controlled(tmp_path)
    ready=HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path).run_cycle(tick_id='cli-live', source_evaluation=ev, correlation_id='cli')
    req=build_review_request(ready, target_labels=['fan0'], not_before='2030-01-01T00:00:00+00:00', not_after='2030-01-02T00:00:00+00:00', expiry='2030-01-02T00:00:00+00:00')
    rp=tmp_path/'request.json'; rp.write_text(json.dumps(req.to_dict()))
    op=tmp_path/'op.json'; pol=tmp_path/'pol.json'; plan=tmp_path/'plan.json'
    assert subprocess.run([sys.executable,'scripts/build_host_local_authorization_runtime.py','decide-operator','--request',str(rp),'--identity','operator-alice','--role','ops-v1','--output',str(op)]).returncode == 0
    assert subprocess.run([sys.executable,'scripts/build_host_local_authorization_runtime.py','decide-policy','--request',str(rp),'--identity','policy-cooling-v1','--policy-version','v1','--output',str(pol)]).returncode == 0
    assert subprocess.run([sys.executable,'scripts/build_host_local_authorization_runtime.py','plan-issue','--request',str(rp),'--operator-decision',str(op),'--policy-decision',str(pol),'--output',str(plan)]).returncode == 0
    assert subprocess.run([sys.executable,'scripts/build_host_local_authorization_runtime.py','issue','--request',str(rp),'--operator-decision',str(op),'--policy-decision',str(pol),'--plan',str(plan),'--runtime-state-root',str(tmp_path)]).returncode == 78
    assert subprocess.run([sys.executable,'scripts/build_host_local_authorization_runtime.py','issue','--request',str(rp),'--operator-decision',str(op),'--policy-decision',str(pol),'--plan',str(plan),'--runtime-state-root',str(tmp_path),'--apply']).returncode == 0

def test_cli_rejects_sample_identity(tmp_path):
    ev=_controlled(tmp_path)
    ready=HostLiveGrantReadinessRuntimeCoordinator(kernel=ControlPlaneKernel(phase=LifecyclePhase.MAINTENANCE), runtime_state_root=tmp_path).run_cycle(tick_id='cli-live2', source_evaluation=ev, correlation_id='cli2')
    req=build_review_request(ready, target_labels=['fan0'], not_before='2030-01-01T00:00:00+00:00', not_after='2030-01-02T00:00:00+00:00', expiry='2030-01-02T00:00:00+00:00')
    rp=tmp_path/'request.json'; rp.write_text(json.dumps(req.to_dict()))
    op=tmp_path/'op.json'
    subprocess.run([sys.executable,'scripts/build_host_local_authorization_runtime.py','decide-operator','--request',str(rp),'--identity','sample_operator','--role','ops-v1','--output',str(op)], check=True)
    assert subprocess.run([sys.executable,'scripts/build_host_local_authorization_runtime.py','validate-decision',str(op)]).returncode == 64
