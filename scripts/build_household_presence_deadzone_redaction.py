from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.household_presence_deadzone_redaction import (
    HouseholdDeadzoneRedactionPolicy,
    build_default_policy,
    evaluate_redaction_request,
    summarize_result,
    validate_policy,
)


def _load(path: str | None) -> dict[str, Any]:
    if not path:
        raise SystemExit("--input required")
    raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    return dict(raw) if isinstance(raw, dict) else {}


def _dump(path: str | None, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build-default", "validate", "evaluate", "summarize"):
        p = sub.add_parser(name)
        p.add_argument("--input")
        p.add_argument("--output")
        p.add_argument("--summary", action="store_true")

    a = ap.parse_args()
    if a.cmd == "build-default":
        _dump(a.output, build_default_policy().__dict__)
        return 0
    if a.cmd == "validate":
        data = _load(a.input)
        res = validate_policy(HouseholdDeadzoneRedactionPolicy(**data))
        _dump(a.output, res)
        return 0 if res["ok"] else 2
    if a.cmd == "evaluate":
        data = _load(a.input)
        res = evaluate_redaction_request(data).to_dict()
        _dump(a.output, res)
        return 2 if res["decision"]["status"] == "blocked" else 0
    data = _load(a.input)
    res = summarize_result(evaluate_redaction_request(data))
    _dump(a.output, res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
