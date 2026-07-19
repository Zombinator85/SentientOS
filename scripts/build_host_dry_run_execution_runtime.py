#!/usr/bin/env python3
# mypy: ignore-errors
"""CLI for the simulation-only host dry-run execution runtime."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass, ControlActionDecision, LifecyclePhase
from sentientos.host_dry_run_execution_runtime import (
    HostDryRunExecutionRuntimeCoordinator, render_markdown, summarize_evaluation,
    validate_evaluation, validate_source_evaluation,
)
from sentientos.host_fulfillment_executor_readiness_runtime import HostFulfillmentExecutorReadinessEvaluation


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _decode_readiness(path: str) -> HostFulfillmentExecutorReadinessEvaluation:
    data = _load_json(path)
    if "runtime_receipt" not in data and ("readiness_receipt" in data or "receipt_id" in data):
        raise SystemExit("standalone_readiness_receipt_rejected")
    # Persisted complete evaluation JSON is the strict CLI source. The runtime
    # bundle path may also point at a directory containing summary/evaluation.json.
    if Path(path).is_dir():
        data = _load_json(str(Path(path) / "evaluation.json"))
    from sentientos.host_fulfillment_executor_readiness_runtime import HostFulfillmentExecutorReadinessRequest, HostFulfillmentExecutorReadinessPlan, HostFulfillmentExecutorPrerequisiteRecord, HostFulfillmentExecutorReadinessReceipt
    def maybe(cls, val): return cls(**val) if isinstance(val, dict) else None
    return HostFulfillmentExecutorReadinessEvaluation(
        data.get("status", data.get("posture", "")), tuple(data.get("findings", ())),
        maybe(HostFulfillmentExecutorReadinessRequest, data.get("request")),
        maybe(HostFulfillmentExecutorReadinessPlan, data.get("plan")), data.get("metadata_admission"),
        tuple(HostFulfillmentExecutorPrerequisiteRecord(**x) for x in data.get("prerequisite_records", ())),
        data.get("contract"), data.get("backend_declaration"), data.get("precondition_manifest"), data.get("dry_run_plan"), data.get("admission_packet"), data.get("readiness_receipt"),
        maybe(HostFulfillmentExecutorReadinessReceipt, data.get("runtime_receipt")), bool(data.get("persisted", False)), bool(data.get("replayed", False)), int(data.get("builder_call_count", 0)), int(data.get("admission_call_count", 0)),
    )

class _CliKernel:
    def admit(self, req):
        return ControlActionDecision(AdmissionOutcome.ALLOW, ("cli_simulation_review",), LifecyclePhase.MAINTENANCE, LifecyclePhase.MAINTENANCE, req.authority_class, req.action_kind, req.actor, req.target_subsystem, {}, req.metadata.get("correlation_id", "cli"))

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build/inspect simulation-only host dry-run execution runtime bundles.")
    sub = p.add_subparsers(dest="cmd", required=False)
    for name in ("validate-source", "build-request", "plan", "simulate", "validate-evaluation", "validate-bundle", "inspect-result", "inspect-receipt", "summarize", "render-json", "render-markdown", "diff"):
        sp = sub.add_parser(name)
        sp.add_argument("--source")
        sp.add_argument("--evaluation")
        sp.add_argument("--output-root")
        sp.add_argument("--output")
        sp.add_argument("--correlation-id")
    args = p.parse_args(argv)
    if args.cmd is None:
        p.print_help(); return 0
    if args.cmd == "diff":
        print(json.dumps({"status":"diff_not_applicable", "simulation_only": True}, sort_keys=True)); return 0
    source_path = args.source or args.evaluation
    if not source_path:
        raise SystemExit("--source or --evaluation required")
    source = _decode_readiness(source_path)
    if args.cmd == "validate-source":
        out = validate_source_evaluation(source).to_dict()
    elif args.cmd in {"simulate", "validate-bundle"}:
        if not args.output_root: raise SystemExit("--output-root required")
        ev = HostDryRunExecutionRuntimeCoordinator(kernel=_CliKernel()).evaluate(source, output_root=args.output_root, correlation_id=args.correlation_id)
        out = ev.to_dict() if args.cmd == "simulate" else validate_evaluation(ev).to_dict()
    else:
        ev = HostDryRunExecutionRuntimeCoordinator(kernel=_CliKernel()).evaluate(source, output_root=args.output_root or "/tmp/host_dry_run_execution_runtime_cli", correlation_id=args.correlation_id, persist=False)
        if args.cmd == "build-request": out = ev.request.to_dict() if ev.request else {}
        elif args.cmd == "plan": out = ev.plan.to_dict() if ev.plan else {}
        elif args.cmd == "validate-evaluation": out = validate_evaluation(ev).to_dict()
        elif args.cmd == "inspect-result": out = ev.result_or_block_receipt or {}
        elif args.cmd == "inspect-receipt": out = ev.dry_run_receipt or ev.runtime_receipt.to_dict() if ev.runtime_receipt else {}
        elif args.cmd == "summarize": out = summarize_evaluation(ev)
        elif args.cmd == "render-markdown":
            text = render_markdown(ev)
            if args.output: Path(args.output).write_text(text, encoding="utf-8")
            else: print(text, end="")
            return 0
        else: out = ev.to_dict()
    text=json.dumps(out, sort_keys=True, indent=2)
    if args.output: Path(args.output).write_text(text, encoding="utf-8")
    else: print(text)
    return 0
if __name__ == "__main__": raise SystemExit(main())
