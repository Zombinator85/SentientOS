from __future__ import annotations

"""JSON-only CLI for bounded production-local model commissioning."""

import argparse
import json
from pathlib import Path

from sentientos.config import GenerationConfig
from sentientos.local_model_commissioning import doctor, inspect_artifact, render_bundle, verify_bundle
from sentientos.local_model_production_commissioning import activate


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
        else:
            result = activate(json.loads(args.commissioning_receipt.read_text()), args.activation_path)
    except (OSError, ValueError, FileExistsError, json.JSONDecodeError) as exc:
        result = {"status": "blocked", "reason": str(exc), "semantic_model_generations": 0}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result.get("status") not in {"blocked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
