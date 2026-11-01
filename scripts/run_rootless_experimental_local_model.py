"""Prepare or execute one workspace-custodied, rootless experimental local inference."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.rootless_experimental_local_model import (
    EXPERIMENT_ROOT, RootlessExperimentalError, execute_intent, prepare_intent,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "execute"):
        command = sub.add_parser(name)
        command.add_argument("--model-manifest", type=Path, required=True)
        command.add_argument("--installation-receipt", type=Path, required=True)
        command.add_argument("--import-receipt", type=Path, required=True)
        command.add_argument("--backend-receipt", type=Path, required=True)
        command.add_argument("--root", type=Path, default=EXPERIMENT_ROOT)
    prepare = sub.choices["prepare"]
    prepare.add_argument("--prompt", required=True)
    prepare.add_argument("--correlation-id")
    execute = sub.choices["execute"]
    execute.add_argument("--intent", type=Path, required=True)
    execute.add_argument("--confirm-intent-digest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_intent(model_manifest_path=args.model_manifest,
                installation_receipt_path=args.installation_receipt,
                import_receipt_path=args.import_receipt,
                backend_receipt_path=args.backend_receipt, prompt=args.prompt,
                correlation_id=args.correlation_id, root=args.root)
        else:
            result = execute_intent(intent_path=args.intent,
                confirm_intent_digest=args.confirm_intent_digest,
                model_manifest_path=args.model_manifest,
                installation_receipt_path=args.installation_receipt,
                import_receipt_path=args.import_receipt,
                backend_receipt_path=args.backend_receipt, root=args.root)
    except (OSError, ValueError, RootlessExperimentalError) as exc:
        result = {"status": "blocked", "reason_code": getattr(exc, "code", "invalid_input")}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    return 0 if result.get("status") not in {"blocked", "rootless_experimental_inference_blocked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
