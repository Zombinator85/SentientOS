from __future__ import annotations

import argparse
import json

from sentientos.codex_task_scaffold_preset_verifier import verify_codex_task_scaffold_presets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset-id")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    result = verify_codex_task_scaffold_presets(preset_id=args.preset_id)
    payload = result.to_dict()
    if args.summary:
        print(json.dumps({"status": payload["status"], "checked_preset_ids": payload["checked_preset_ids"], "error_count": len(payload["errors"])}, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.status == "codex_task_scaffold_preset_verifier_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
