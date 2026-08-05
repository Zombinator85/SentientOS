from __future__ import annotations
import argparse,json,sys
from typing import Any, Sequence
from pathlib import Path
from sentientos import maintenance_implementation_agent as mia

def emit(v: Any) -> None: print(json.dumps(v,sort_keys=True,separators=(",",":")))
def driver(args: argparse.Namespace) -> mia.ImplementationAgentDriver:
    plan=mia.load_fake_plan(args.fake_plan) if getattr(args,'fake_plan',None) else None
    reg=mia.default_driver_registry(plan); return reg[args.driver_id]
def main(argv: Sequence[str] | None = None) -> int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument('--state-root',required=True); sp.add_argument('--repo-root',default='.')
    vr=sub.add_parser('verify-request'); vr.add_argument('--request',required=True)
    ld=sub.add_parser('list-drivers'); ld.add_argument('--fake-plan')
    st=sub.add_parser('start'); common(st); st.add_argument('--lease-id',required=True); st.add_argument('--request',required=True); st.add_argument('--fake-plan',required=True); st.add_argument('--evaluation-time',required=True); st.add_argument('--driver-id',default='fake_scripted_default')
    po=sub.add_parser('poll'); common(po); po.add_argument('--task-id',required=True); po.add_argument('--session-id',required=True); po.add_argument('--request',required=True); po.add_argument('--fake-plan',required=True); po.add_argument('--evaluation-time',required=True); po.add_argument('--driver-id',default='fake_scripted_default')
    ca=sub.add_parser('cancel'); common(ca); ca.add_argument('--task-id',required=True); ca.add_argument('--session-id',required=True); ca.add_argument('--request',required=True); ca.add_argument('--fake-plan',required=True); ca.add_argument('--evaluation-time',required=True); ca.add_argument('--cancellation-reference',required=True); ca.add_argument('--driver-id',default='fake_scripted_default')
    re=sub.add_parser('recover'); common(re); re.add_argument('--task-id',required=True); re.add_argument('--session-id',required=True); re.add_argument('--request',required=True); re.add_argument('--fake-plan',required=True); re.add_argument('--evaluation-time',required=True); re.add_argument('--driver-id',default='fake_scripted_default')
    isess=sub.add_parser('inspect-session'); common(isess); isess.add_argument('--session-id',required=True)
    ires=sub.add_parser('inspect-result'); common(ires); ires.add_argument('--session-id',required=True)
    a=p.parse_args(argv)
    try:
        if a.cmd=='verify-request': emit({'status':'request_valid','request':mia.verify_request(json.loads(Path(a.request).read_text()))}); return 0
        if a.cmd=='list-drivers': emit({'status':'drivers_listed','drivers':[driver(a).describe_driver()]}); return 0
        if a.cmd=='start':
            r=mia.start_implementation_agent_session(state_root=a.state_root,lease_id=a.lease_id,request=json.loads(Path(a.request).read_text()),driver=driver(a),evaluation_time=a.evaluation_time,repo_root=a.repo_root); emit(r); return 0 if r['status'] in {'agent_session_ready','agent_session_already_ready','agent_session_recovered'} else 2
        if a.cmd in {'poll','recover'}:
            r=mia.poll_implementation_agent_session(state_root=a.state_root,task_id=a.task_id,session_id=a.session_id,request=json.loads(Path(a.request).read_text()),driver=driver(a),evaluation_time=a.evaluation_time,repo_root=a.repo_root); emit(r); return 0 if not str(r['status']).endswith('invalid') and r['status']!='agent_session_conflict' else 2
        if a.cmd=='cancel':
            r=mia.cancel_implementation_agent_session(state_root=a.state_root,task_id=a.task_id,session_id=a.session_id,request=json.loads(Path(a.request).read_text()),driver=driver(a),evaluation_time=a.evaluation_time,cancellation_reference=a.cancellation_reference,repo_root=a.repo_root); emit(r); return 0 if r['status'] in {'agent_session_cancelled','agent_session_already_terminal','agent_session_interrupted'} else 2
        if a.cmd=='inspect-session': emit(mia.inspect_session(state_root=a.state_root,session_id=a.session_id,repo_root=a.repo_root)); return 0
        if a.cmd=='inspect-result': emit(mia.inspect_result(state_root=a.state_root,session_id=a.session_id,repo_root=a.repo_root)); return 0
    except Exception as e:
        emit({'status':'error','reason_codes':[str(e)]}); return 2
    return 2
if __name__=='__main__': sys.exit(main())
