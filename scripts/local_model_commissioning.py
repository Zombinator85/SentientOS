from __future__ import annotations

"""JSON-only CLI for bounded production-local model commissioning."""

import argparse
import json
from pathlib import Path

from sentientos.config import GenerationConfig
from sentientos.local_model_commissioning import doctor, inspect_artifact, render_bundle, verify_bundle
from sentientos.local_model_production_commissioning import (
    ProductionCommissioningError, activate, authorization_for, commission,
    compose_commissioning_plan, load_activation, reconstruct_chain, revalidate_chain,
    verify_compatibility,
)

EVIDENCE_NAMES = ("selection", "runtime_provisioning", "installation_plan", "installation_receipt",
                  "import_plan", "import_receipt", "backend_plan", "backend_receipt", "catalog",
                  "acquisition_plan", "acquisition_receipt")


def _production_chain(root: Path) -> dict[str, object]:
    return reconstruct_chain(**{name: json.loads((root / f"{name}.json").read_text()) for name in EVIDENCE_NAMES})


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    render = sub.add_parser("render")
    for command in (inspect, render):
        command.add_argument("--model-path", type=Path, required=True)
        command.add_argument("--allowed-root", type=Path, required=True)
        command.add_argument("--name")
        command.add_argument("--max-context-tokens", type=int, default=4096)
        command.add_argument("--max-new-tokens", type=int, default=512)
        command.add_argument("--temperature", type=float, default=.7)
        command.add_argument("--top-p", type=float, default=.95)
    render.add_argument("--state-root", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--state-root", type=Path, required=True)
    verify.add_argument("--load", action="store_true")
    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--state-root", type=Path, required=True)
    doctor_parser.add_argument("--require-load-verification", action="store_true")
    handoff = sub.add_parser("handoff")
    handoff.add_argument("--state-root", type=Path, required=True)
    activation = sub.add_parser("activate")
    activation.add_argument("--commissioning-receipt", type=Path, required=True)
    activation.add_argument("--activation-path", type=Path, required=True)
    for name in ("production-plan", "compatibility", "commission"):
        command = sub.add_parser(name)
        command.add_argument("--evidence-root", type=Path, required=True)
        command.add_argument("--output-root", type=Path, required=True)
        if name != "production-plan": command.add_argument("--compatibility-receipt", type=Path)
        if name == "commission": command.add_argument("--confirm-plan-digest", required=True)
    status = sub.add_parser("status")
    status.add_argument("--activation-path", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command in {"inspect", "render"}:
            generation = GenerationConfig(max_new_tokens=args.max_new_tokens,
                                          temperature=args.temperature, top_p=args.top_p)
            kwargs = {"allowed_root": args.allowed_root, "name": args.name,
                      "max_context_tokens": args.max_context_tokens, "generation": generation}
            result = (inspect_artifact(args.model_path, **kwargs) if args.command == "inspect"
                      else render_bundle(args.model_path, state_root=args.state_root, **kwargs))
        elif args.command == "verify":
            result = verify_bundle(args.state_root, load=args.load)
        elif args.command == "doctor":
            result = doctor(args.state_root,
                            require_load_verification=args.require_load_verification)
        elif args.command == "handoff":
            validation = verify_bundle(args.state_root)
            if not validation.get("bundle_valid"):
                result = validation
            else:
                result = json.loads((args.state_root / "calibration-handoff.json").read_text())
        elif args.command == "activate":
            result = activate(json.loads(args.commissioning_receipt.read_text()), args.activation_path)
        elif args.command in {"production-plan", "compatibility", "commission"}:
            chain = _production_chain(args.evidence_root)
            if args.command == "compatibility":
                result = verify_compatibility(chain)
                target = args.compatibility_receipt or (args.output_root / "compatibility-receipt.json")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
            else:
                compatibility_path = args.compatibility_receipt or (args.output_root / "compatibility-receipt.json")
                compatibility = json.loads(compatibility_path.read_text()) if compatibility_path.exists() else {
                    "receipt_semantic_digest": "plan_requires_verified_compatibility"}
                result = compose_commissioning_plan(chain, compatibility, args.output_root)
                if args.command == "commission":
                    authorization = authorization_for(result, operator_confirmed_plan_digest=args.confirm_plan_digest)
                    result = commission(result, compatibility, authorization)
        else:
            model, _ = load_activation(args.activation_path)
            try:
                result = {"status": "active_production_chain_current", "active_model_identity": model.active_identity.to_dict(),
                          "semantic_model_generations": 0}
            finally:
                close = getattr(model, "close", None)
                if close is not None: close()
    except (OSError, ValueError, FileExistsError, json.JSONDecodeError, ProductionCommissioningError) as exc:
        result = {"status": "blocked", "reason": str(exc), "semantic_model_generations": 0}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result.get("status") not in {"blocked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
