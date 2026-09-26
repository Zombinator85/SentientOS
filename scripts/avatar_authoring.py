"""One-shot operator CLI for avatar authoring and embodied consequence evidence."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.avatar_authoring import (
    SyntheticArtifactInspector, SyntheticAuthoringBackend, adopt, blender_readiness,
    build_admission, lineage, load_pointer, renderer_handoff, rollback, run_workcell,
    successor_manifest, validate_plan,
)
from sentientos.embodiment_self_observation import AvatarBodyManifest
from sentientos.embodied_consequence import (
    AvatarRendererReport, EmbodiedActionExpectation, IndependentConsequenceObservation,
    EmbodiedStrategyProposal,
    evaluate_consequence, run_strategy_experiment, verify_independent_observation,
    verify_renderer_report,
)


def _read(path: str) -> dict[str, Any]:
    value=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError("input_must_be_json_object")
    return value


def _manifest(path: str) -> AvatarBodyManifest:
    value=_read(path)
    for key in ("bones","expressions","motion_channels","viseme_channels","sensor_bindings","output_bindings"):
        value[key]=tuple(value[key])
    result=AvatarBodyManifest(**value); result.validate(); return result


def _expectation(path: str) -> EmbodiedActionExpectation:
    value=_read(path); value["observable_fields"]=tuple(value["observable_fields"]); return EmbodiedActionExpectation(**value)


def _report(path: str) -> AvatarRendererReport:
    value=_read(path); value["warnings"]=tuple(value["warnings"]); value["errors"]=tuple(value["errors"]); return AvatarRendererReport(**value)


def _observation(path: str) -> IndependentConsequenceObservation:
    return IndependentConsequenceObservation(**_read(path))


def _write(path: str | None, value: Mapping[str, Any]) -> None:
    data=json.dumps(value,sort_keys=True,separators=(",",":"))
    if path: Path(path).write_text(data+"\n",encoding="utf-8")
    print(data)


def parser() -> argparse.ArgumentParser:
    root=argparse.ArgumentParser(); sub=root.add_subparsers(dest="command",required=True)
    p=sub.add_parser("plan-validate"); p.add_argument("--plan",required=True)
    p=sub.add_parser("readiness"); p.add_argument("--blender",required=True); p.add_argument("--driver",required=True); p.add_argument("--workspace-root",required=True); p.add_argument("--executable-sha256")
    p=sub.add_parser("run-one");
    for name in ("pointer","manifest","predecessor","plan","workspace-root","work-id","admission-id","approval","output"): p.add_argument("--"+name,required=True)
    p.add_argument("--backend",choices=("synthetic",),required=True)
    p=sub.add_parser("candidate-status"); p.add_argument("--candidate",required=True); p.add_argument("--manifest",required=True)
    p=sub.add_parser("adopt")
    for name in ("pointer","lineage","candidate","predecessor-manifest","expected-pointer-digest","approval","output"): p.add_argument("--"+name,required=True)
    p=sub.add_parser("rollback")
    for name in ("pointer","lineage","adoption","predecessor-manifest","approval","output"): p.add_argument("--"+name,required=True)
    p=sub.add_parser("renderer-handoff")
    for name in ("pointer","renderer-interface-id","requested-pose","requested-expression","correlation-id","commanded-at","output"): p.add_argument("--"+name,required=True)
    p=sub.add_parser("lineage"); p.add_argument("--path",required=True)
    p=sub.add_parser("renderer-report-validate"); p.add_argument("--report",required=True)
    p=sub.add_parser("observation-validate"); p.add_argument("--observation",required=True)
    p=sub.add_parser("consequence-evaluate")
    for name in ("expectation","handoff","current-body","evaluated-at","output","comparison-output"): p.add_argument("--"+name,required=True)
    p.add_argument("--renderer-report"); p.add_argument("--observation"); p.add_argument("--fulfillment-receipt"); p.add_argument("--causal-principal-binding-digest")
    p=sub.add_parser("consequence-show"); p.add_argument("--attribution",required=True); p.add_argument("--comparison",required=True)
    p=sub.add_parser("developmental-assimilate"); p.add_argument("--selection",required=True); p.add_argument("--candidate",required=True); p.add_argument("--admission",required=True); p.add_argument("--output",required=True)
    p=sub.add_parser("strategy-experiment"); p.add_argument("--protocol",required=True); p.add_argument("--history-record",required=True); p.add_argument("--situation",required=True); p.add_argument("--consequence",required=True); p.add_argument("--backend-fixture",required=True); p.add_argument("--output",required=True)
    return root


class _FixtureStrategyBackend:
    """Explicit deterministic test cognition backend; never a production model."""
    def __init__(self,value: Mapping[str,Any]) -> None: self.value=value
    def propose(self, *, condition: str, history: Sequence[Mapping[str, Any]],
                situation: Mapping[str, Any]) -> EmbodiedStrategyProposal:
        from sentientos.embodied_consequence import make_strategy_proposal
        template=dict(self.value["with_history"] if history else self.value["without_history"])
        template.setdefault("relevant_consequence_ids",tuple(str(x["candidate"].get("selection",{}).get("consequence_id","")) for x in history if x.get("candidate")))
        template["relevant_consequence_ids"]=tuple(x for x in template["relevant_consequence_ids"] if x)
        template["factual_assertions"]=tuple(template.get("factual_assertions",()))
        return make_strategy_proposal(**template)


def main(argv: list[str] | None=None) -> int:
    args=parser().parse_args(argv); command=args.command; result: Mapping[str,Any]
    if command=="plan-validate": result=validate_plan(_read(args.plan))
    elif command=="readiness": result=blender_readiness(Path(args.blender),Path(args.driver),Path(args.workspace_root),expected_sha256=args.executable_sha256)
    elif command=="run-one":
        pointer=load_pointer(Path(args.pointer)); manifest=_manifest(args.manifest); plan=validate_plan(_read(args.plan)); backend=SyntheticAuthoringBackend(); inspector=SyntheticArtifactInspector()
        workspace=(Path(args.workspace_root)/args.work_id).resolve(); successor=workspace/"output"/f"successor.{manifest.asset_format}"
        admission=build_admission(admission_id=args.admission_id,work_id=args.work_id,pointer=pointer,plan=plan,workspace=workspace,backend=backend.identity,output=successor,operator_approval=args.approval)
        result=run_workcell(current_pointer=pointer,predecessor_manifest=manifest,predecessor=Path(args.predecessor),plan_value=_read(args.plan),admission=admission,workspace_root=Path(args.workspace_root),backend=backend,inspector=inspector,work_id=args.work_id); _write(args.output,result); return 0
    elif command=="candidate-status":
        candidate=_read(args.candidate); successor_manifest(_manifest(args.manifest),candidate)
        result={"status":candidate["receipt"]["result_posture"],"receipt_digest":candidate["receipt"]["receipt_digest"],"candidate_path":str(Path(args.candidate).resolve()),"authority":{}}
    elif command=="adopt":
        old=_manifest(args.predecessor_manifest); candidate=_read(args.candidate); new=successor_manifest(old,candidate)
        result=adopt(pointer_path=Path(args.pointer),lineage_path=Path(args.lineage),expected_pointer_digest=args.expected_pointer_digest,candidate=candidate,manifest=new,approval=args.approval); _write(args.output,result); return 0
    elif command=="rollback": result=rollback(pointer_path=Path(args.pointer),lineage_path=Path(args.lineage),adopted=_read(args.adoption),predecessor_manifest=_manifest(args.predecessor_manifest),approval=args.approval); _write(args.output,result); return 0
    elif command=="renderer-handoff": result=renderer_handoff(load_pointer(Path(args.pointer)),renderer_interface_id=args.renderer_interface_id,requested_pose=args.requested_pose,requested_expression=args.requested_expression,correlation_id=args.correlation_id,commanded_at=args.commanded_at); _write(args.output,result); return 0
    elif command=="lineage": result={"schema":"sentientos.avatar_body_lineage_query:v1","events":lineage(Path(args.path)),"authority":{}}
    elif command=="renderer-report-validate": report=_report(args.report); verify_renderer_report(report); result={"status":"renderer_report_valid","report_id":report.report_id,"authority":{}}
    elif command=="observation-validate": observation=_observation(args.observation); verify_independent_observation(observation); result={"status":"independent_observation_valid","observation_id":observation.observation_id,"authority":{}}
    elif command=="consequence-evaluate":
        attribution,comparison=evaluate_consequence(expectation=_expectation(args.expectation),handoff=_read(args.handoff),current_body=_read(args.current_body),renderer_report=_report(args.renderer_report) if args.renderer_report else None,observation=_observation(args.observation) if args.observation else None,fulfillment_receipt=_read(args.fulfillment_receipt) if args.fulfillment_receipt else None,causal_principal_binding_digest=args.causal_principal_binding_digest,evaluated_at=args.evaluated_at)
        _write(args.comparison_output,comparison); _write(args.output,attribution); return 0
    elif command=="consequence-show": result={"attribution":_read(args.attribution),"comparison":_read(args.comparison),"authority":{}}
    elif command=="developmental-assimilate":
        # This surface binds already governed selection/candidate/admission evidence; runtime
        # admission and durable append remain owned by ResidentDevelopmentalWritebackController.
        result={"schema_version":"sentientos.developmental_assimilation_request:v1","selection":_read(args.selection),"candidate":_read(args.candidate),"admission":_read(args.admission),"status":"ready_for_resident_developmental_writeback_controller","automatic_write":False,"authority":{}}
        _write(args.output,result); return 0
    elif command=="strategy-experiment": result=run_strategy_experiment(protocol=_read(args.protocol),history_record=_read(args.history_record),situation=_read(args.situation),backend=_FixtureStrategyBackend(_read(args.backend_fixture)),consequence=_read(args.consequence)); _write(args.output,result); return 0
    else: raise AssertionError(command)
    _write(None,result); return 0


if __name__=="__main__": raise SystemExit(main())
