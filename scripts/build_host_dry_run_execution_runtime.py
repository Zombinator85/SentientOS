#!/usr/bin/env python3
"""CLI for the simulation-only host dry-run execution runtime."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from typing import Any, Mapping
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentientos.host_dry_run_execution_runtime import (
    HostDryRunExecutionRuntimeCoordinator, render_markdown, summarize_evaluation,
    validate_evaluation, validate_source_evaluation, build_request,
)
from sentientos.host_fulfillment_executor_readiness_runtime import (
    HostFulfillmentExecutorPrerequisiteRecord,
    HostFulfillmentExecutorReadinessEvaluation,
    HostFulfillmentExecutorReadinessPlan,
    HostFulfillmentExecutorReadinessReceipt,
    HostFulfillmentExecutorReadinessRequest,
)


def _load_json(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("json_object_required")
    return data


def _decode_eval(data: dict[str, Any]) -> HostFulfillmentExecutorReadinessEvaluation:
    def maybe(cls: Any, val: Any) -> Any:
        return cls(**val) if isinstance(val, dict) else None
    return HostFulfillmentExecutorReadinessEvaluation(
        str(data.get("status", data.get("posture", ""))), tuple(data.get("findings", ())),
        maybe(HostFulfillmentExecutorReadinessRequest, data.get("request")),
        maybe(HostFulfillmentExecutorReadinessPlan, data.get("plan")), data.get("metadata_admission"),
        tuple(HostFulfillmentExecutorPrerequisiteRecord(**x) for x in data.get("prerequisite_records", ())),
        data.get("contract"), data.get("backend_declaration"), data.get("precondition_manifest"), data.get("dry_run_plan"), data.get("admission_packet"), data.get("readiness_receipt"),
        maybe(HostFulfillmentExecutorReadinessReceipt, data.get("runtime_receipt")), bool(data.get("persisted", False)), bool(data.get("replayed", False)), int(data.get("builder_call_count", 0)), int(data.get("admission_call_count", 0)),
    )


def _decode_readiness_bundle(root: str | Path) -> HostFulfillmentExecutorReadinessEvaluation:
    bundle = Path(root)
    if not bundle.is_dir():
        raise SystemExit("persisted_readiness_bundle_directory_required")
    allowed_extra = {"README.md"}
    required = ["bundle_manifest.json","readiness_request.json","current_grant_evidence.json","source_manifest.json","metadata_admission.json","runtime_plan.json","prerequisites.json","executor_contract.json","backend_declaration.json","precondition_manifest.json","dry_run_plan.json","admission_packet.json","readiness_receipt.json","runtime_receipt.json","validation_findings.json","summary.json"]
    missing = [name for name in required if not (bundle/name).is_file()]
    if missing:
        raise SystemExit("missing_readiness_bundle_artifacts:" + ",".join(missing))
    manifest = _load_json(bundle/"bundle_manifest.json")
    seen = [str(e.get("relative_filename")) for e in manifest.get("files", ()) if isinstance(e, dict)]
    for name in required:
        if name == "bundle_manifest.json":
            continue
        if seen.count(name) != 1:
            raise SystemExit("readiness_bundle_manifest_required_artifact_mismatch:" + name)
    for entry in manifest.get("files", ()):
        if not isinstance(entry, dict):
            raise SystemExit("readiness_bundle_manifest_entry_malformed")
        rel = str(entry.get("relative_filename", ""))
        if (rel not in required and rel not in allowed_extra) or rel == "bundle_manifest.json":
            raise SystemExit("readiness_bundle_unmanifested_or_unknown_artifact:" + rel)
        raw = (bundle/rel).read_bytes()
        if len(raw) != int(entry.get("size", -1)) or "sha256:" + hashlib.sha256(raw).hexdigest() != entry.get("digest"):
            raise SystemExit("readiness_bundle_file_custody_mismatch:" + rel)
    data = {
        "status": _load_json(bundle/"runtime_receipt.json").get("posture", ""),
        "findings": tuple(_load_json(bundle/"validation_findings.json").get("findings", ())),
        "request": _load_json(bundle/"readiness_request.json"),
        "plan": _load_json(bundle/"runtime_plan.json"),
        "metadata_admission": _load_json(bundle/"metadata_admission.json"),
        "prerequisite_records": json.loads((bundle/"prerequisites.json").read_text(encoding="utf-8")),
        "contract": _load_json(bundle/"executor_contract.json"),
        "backend_declaration": _load_json(bundle/"backend_declaration.json"),
        "precondition_manifest": _load_json(bundle/"precondition_manifest.json"),
        "dry_run_plan": _load_json(bundle/"dry_run_plan.json"),
        "admission_packet": _load_json(bundle/"admission_packet.json"),
        "readiness_receipt": _load_json(bundle/"readiness_receipt.json"),
        "runtime_receipt": _load_json(bundle/"runtime_receipt.json"),
        "persisted": True,
    }
    ev = _decode_eval(data)
    object.__setattr__(ev, "_current_grant_evidence", _load_json(bundle/"current_grant_evidence.json"))
    return ev


def _decode_diagnostic_source(path: str) -> HostFulfillmentExecutorReadinessEvaluation:
    p = Path(path)
    if p.is_dir():
        return _decode_readiness_bundle(p)
    data = _load_json(p)
    if "runtime_receipt" not in data and ("readiness_receipt" in data or "receipt_id" in data):
        raise SystemExit("standalone_readiness_receipt_rejected")
    return _decode_eval(data)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build/inspect simulation-only host dry-run execution runtime bundles.")
    sub = p.add_subparsers(dest="cmd", required=False)
    for name in ("validate-source", "simulate", "validate-evaluation", "validate-bundle", "inspect-result", "inspect-receipt", "summarize", "render-json", "render-markdown", "diff"):
        sp = sub.add_parser(name)
        sp.add_argument("--source")
        sp.add_argument("--evaluation")
        sp.add_argument("--readiness-bundle-root")
        sp.add_argument("--current-snapshot")
        sp.add_argument("--current-verification")
        sp.add_argument("--output-root")
        sp.add_argument("--output")
        sp.add_argument("--correlation-id")
    args = p.parse_args(argv)
    out: Mapping[str, Any]
    if args.cmd is None:
        p.print_help(); return 0
    if args.cmd == "diff":
        print(json.dumps({"status":"diff_not_applicable", "simulation_only": True}, sort_keys=True)); return 0
    if args.cmd == "validate-bundle":
        if not args.source and not args.evaluation:
            raise SystemExit("--source persisted-host-dry-run-bundle required")
        ev = HostDryRunExecutionRuntimeCoordinator()._evaluation_from_bundle(Path(args.source or args.evaluation))
        out = validate_evaluation(ev).to_dict()
    elif args.cmd == "simulate":
        if not (args.readiness_bundle_root and args.current_snapshot and args.current_verification and args.output_root):
            raise SystemExit("simulate requires --readiness-bundle-root --current-snapshot --current-verification --output-root")
        source = _decode_readiness_bundle(args.readiness_bundle_root)
        ev = HostDryRunExecutionRuntimeCoordinator().evaluate(source, output_root=args.output_root, correlation_id=args.correlation_id, current_snapshot=_load_json(args.current_snapshot), current_verification=_load_json(args.current_verification))
        out = ev.to_dict()
    elif args.cmd == "validate-source":
        if args.readiness_bundle_root:
            source = _decode_readiness_bundle(args.readiness_bundle_root)
            findings = list(validate_source_evaluation(source).findings)
            if args.current_snapshot and args.current_verification:
                try:
                    build_request(source, current_snapshot=_load_json(args.current_snapshot), current_verification=_load_json(args.current_verification))
                except ValueError as exc:
                    findings.append(str(exc))
            out = {"ok": not findings, "findings": sorted(set(findings))}
        else:
            source_path = args.source or args.evaluation
            if not source_path: raise SystemExit("--readiness-bundle-root or --source required")
            out = validate_source_evaluation(_decode_diagnostic_source(source_path)).to_dict()
    else:
        source_path = args.source or args.evaluation or args.readiness_bundle_root
        if not source_path: raise SystemExit("--source or --readiness-bundle-root required")
        source = _decode_diagnostic_source(source_path)
        ev = HostDryRunExecutionRuntimeCoordinator().evaluate(source, output_root=args.output_root or "/tmp/host_dry_run_execution_runtime_cli", correlation_id=args.correlation_id, persist=False)
        if args.cmd == "validate-evaluation": out = validate_evaluation(ev).to_dict()
        elif args.cmd == "inspect-result": out = ev.result_or_block_receipt or {}
        elif args.cmd == "inspect-receipt": out = ev.dry_run_receipt or (ev.runtime_receipt.to_dict() if ev.runtime_receipt else {})
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
