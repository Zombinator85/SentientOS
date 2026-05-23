from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.codex_task_scaffold_verifier import verify_codex_task_scaffold_payload


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scaffold", type=Path, required=True)
    p.add_argument("--summary", action="store_true")
    a = p.parse_args(argv)

    payload = json.loads(a.scaffold.read_text(encoding="utf-8"))
    result = verify_codex_task_scaffold_payload(payload)
    if a.summary:
        print(json.dumps({"status": result.status}, sort_keys=True))
    else:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "codex_task_scaffold_verifier_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
