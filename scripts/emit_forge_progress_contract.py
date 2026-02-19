from __future__ import annotations

import json
from pathlib import Path

from sentientos.forge_progress_contract import emit_forge_progress_contract

DEFAULT_OUTPUT = Path("glow/contracts/forge_progress_baseline.json")


def main(argv: list[str] | None = None) -> int:
    _ = argv
    contract = emit_forge_progress_contract(Path.cwd())
    payload = contract.to_dict()
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"tool": "emit_forge_progress_contract", "output": str(DEFAULT_OUTPUT), "runs": len(payload.get("last_runs", []))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
