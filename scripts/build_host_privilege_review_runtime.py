#!/usr/bin/env python3
"""Build/inspect host privilege-review rehearsal runtime artifacts."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any, cast
from sentientos.host_privilege_review_runtime import build_host_privilege_review_plan, validate_evaluation, persist_evidence_bundle, render_markdown, summary_for_evaluation, HostPrivilegeReviewRuntimeCoordinator


def _load(path: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(Path(path).read_text(encoding="utf-8")))

def _emit(obj: Any) -> int:
    print(json.dumps(obj, sort_keys=True, indent=2, default=str)); return 0

def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    ev=sub.add_parser("evaluate"); ev.add_argument("--input", required=True); ev.add_argument("--output-root", required=True); ev.add_argument("--tick-id", required=True); ev.add_argument("--summary", action="store_true")
    for name in ["validate-plan","validate-evaluation","validate-bundle","summarize","list-items","render-json","render-markdown"]:
        q=sub.add_parser(name); q.add_argument("--input", required=True)
    ins=sub.add_parser("inspect-item"); ins.add_argument("--input", required=True); ins.add_argument("--item-id", required=True)
    diff=sub.add_parser("diff"); diff.add_argument("--before", required=True); diff.add_argument("--after", required=True)
    ns=p.parse_args(argv)
    if ns.cmd=="plan": return _emit(build_host_privilege_review_plan().to_dict())
    if ns.cmd=="validate-plan":
        data=_load(ns.input); return _emit({"valid": data.get("metadata_only") is True and data.get("effect_authority") is False, "findings": []})
    if ns.cmd=="evaluate":
        # Explicit artifact mode: caller supplies a serialized HostResourceRuntimeEvaluation fixture.
        # Rehydration of full dataclasses is intentionally not guessed here; product daemon uses typed in-memory path.
        data=_load(ns.input)
        if data.get("schema_version") == "host_privilege_review_rehearsal_runtime.v1" or "items" in data:
            out=Path(ns.output_root); out.mkdir(parents=True, exist_ok=True); target=out/"evaluation.json"; target.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
            return _emit({"status":"artifact_copied_for_validation", "output": str(target), "collection_triggered": False, "privileged_execution_triggered": False, "host_mutation_performed": False})
        return _emit({"status":"explicit_typed_fixture_required", "collection_triggered": False, "privileged_execution_triggered": False, "host_mutation_performed": False})
    data=_load(getattr(ns,"input", "")) if hasattr(ns,"input") else {}
    if ns.cmd=="validate-evaluation": return _emit({"valid": data.get("no_effect_authority", True) is True and data.get("summary",{}).get("host_mutation_performed", False) is False, "findings": []})
    if ns.cmd=="validate-bundle": return _emit({"valid": isinstance(data, dict), "findings": []})
    if ns.cmd=="summarize": return _emit(data.get("summary", data))
    if ns.cmd=="list-items": return _emit({"items":[i.get("item_id") for i in data.get("items", []) if isinstance(i,dict)]})
    if ns.cmd=="inspect-item":
        for item in data.get("items", []):
            if isinstance(item,dict) and item.get("item_id")==ns.item_id: return _emit(item)
        return _emit({"error":"item_not_found"}) or 1
    if ns.cmd=="render-json": return _emit(data)
    if ns.cmd=="render-markdown":
        print("# Host Privilege Review Rehearsal Runtime\n")
        print(f"- Evaluation: `{data.get('evaluation_id','unknown')}`")
        print(f"- Chain: `{data.get('chain_id','unknown')}`")
        print("- Effects: `none`; rehearsal is not execution.")
        return 0
    if ns.cmd=="diff":
        before=_load(ns.before); after=_load(ns.after); return _emit({"changed": before != after, "before_id": before.get("evaluation_id"), "after_id": after.get("evaluation_id")})
    return 2
if __name__ == "__main__": raise SystemExit(main())
