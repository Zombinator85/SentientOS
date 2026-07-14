# mypy: ignore-errors
#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, validate_receipt
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import atomic_write_json, build_local_model_authority_map, render_authority_map_markdown, validate_authority_map

SUCCESS = 0; DENIED_OR_BLOCKED = 2; INPUT_ERROR = 3

def _load(path: Path): return json.loads(path.read_text(encoding="utf-8"))

def _config_from_args(args: argparse.Namespace) -> ModelConfig:
    candidates = []
    for model_path in args.model or []:
        candidates.append(ModelCandidate(path=Path(model_path), engine=args.engine, name=args.name, options={"sha256": args.sha256} if args.sha256 else {}))
    if not candidates:
        candidates.append(ModelCandidate(path=None, engine=args.engine, name=args.name or "explicit simulation"))
    return ModelConfig(candidates=candidates, generation=GenerationConfig(max_new_tokens=args.max_new_tokens))

def cmd_build_map(args):
    authority = build_local_model_authority_map(_config_from_args(args), allowed_roots=[Path(r) for r in args.allowed_root])
    payload = authority.to_dict()
    if args.output: atomic_write_json(Path(args.output), payload)
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True); Path(args.markdown).write_text(render_authority_map_markdown(authority), encoding="utf-8")
    if args.summary: print(json.dumps(payload["summary"], sort_keys=True))
    else: print(json.dumps(payload, indent=2, sort_keys=True))
    return SUCCESS

def cmd_validate_map(args):
    ok, reasons = validate_authority_map(_load(Path(args.path)))
    print(json.dumps({"valid": ok, "reason_codes": reasons}, sort_keys=True))
    return SUCCESS if ok else INPUT_ERROR

def cmd_inspect(args):
    payload = _load(Path(args.path)); ok, reasons = validate_authority_map(payload)
    print(json.dumps({"valid": ok, "reason_codes": reasons, "summary": payload.get("summary", {})}, sort_keys=True))
    return SUCCESS if ok else INPUT_ERROR

def cmd_validate_receipt(args):
    ok, reasons = validate_receipt(_load(Path(args.path)))
    print(json.dumps({"valid": ok, "reason_codes": reasons}, sort_keys=True))
    return SUCCESS if ok else INPUT_ERROR

def cmd_invoke_fixture(args):
    authority = build_local_model_authority_map(_config_from_args(args), allowed_roots=[Path(r) for r in args.allowed_root])
    model = LocalModel.autoload() if args.use_configured_model else type("FixtureModel", (), {"generate": lambda self, prompt, **kw: args.fixture_response})()
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority, runtime_root=Path(args.runtime_root))
    request = invoker.build_request(purpose=args.purpose, prompt=args.prompt, caller="governed_local_model_cli", correlation_id=args.correlation_id, expected_output_format=args.expected_output_format)
    receipt = invoker.invoke(request, include_output_in_receipt=args.include_output)
    print(json.dumps(receipt.to_dict(include_output=args.include_output), indent=2, sort_keys=True))
    return SUCCESS if receipt.status in {"admitted_completed", "admitted_simulation"} else DENIED_OR_BLOCKED

def main(argv=None):
    parser = argparse.ArgumentParser(description="Build and validate governed local model authority/invocation artifacts. Local-only; no provider/network/tool/memory/git/adoption authority.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    def common(p):
        p.add_argument("--model", action="append"); p.add_argument("--engine", default="echo"); p.add_argument("--name"); p.add_argument("--sha256"); p.add_argument("--allowed-root", action="append", default=[str(Path.cwd())]); p.add_argument("--max-new-tokens", type=int, default=64)
    p=sub.add_parser("build-map"); common(p); p.add_argument("--output"); p.add_argument("--markdown"); p.add_argument("--summary", action="store_true"); p.set_defaults(func=cmd_build_map)
    p=sub.add_parser("validate-map"); p.add_argument("path"); p.set_defaults(func=cmd_validate_map)
    p=sub.add_parser("inspect"); p.add_argument("path"); p.set_defaults(func=cmd_inspect)
    p=sub.add_parser("validate-receipt"); p.add_argument("path"); p.set_defaults(func=cmd_validate_receipt)
    p=sub.add_parser("invoke-fixture"); common(p); p.add_argument("--prompt", required=True); p.add_argument("--purpose", choices=["local_user_chat", "genesis_proposal_advice"], default="local_user_chat"); p.add_argument("--correlation-id", required=True); p.add_argument("--expected-output-format", default="text"); p.add_argument("--runtime-root", default=str(Path.cwd()/"sentientos_data/runtime/governed_local_model_invocation")); p.add_argument("--fixture-response", default="fixture response"); p.add_argument("--include-output", action="store_true"); p.add_argument("--use-configured-model", action="store_true"); p.set_defaults(func=cmd_invoke_fixture)
    args = parser.parse_args(argv)
    try: return args.func(args)
    except Exception as exc:
        print(json.dumps({"error": exc.__class__.__name__, "message": str(exc)}, sort_keys=True), file=sys.stderr); return INPUT_ERROR
if __name__ == "__main__": raise SystemExit(main())
