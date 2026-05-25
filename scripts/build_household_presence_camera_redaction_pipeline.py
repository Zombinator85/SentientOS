from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.household_presence_camera_redaction_pipeline import HouseholdCameraRedactionPipelinePolicy, build_default_policy, evaluate_pipeline, validate_policy


def _load(path: str | None) -> dict[str, Any]:
    if not path:
        raise SystemExit("--input required")
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
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
    for name in ("build-default", "run-fixture", "evaluate", "validate", "summarize"):
        p = sub.add_parser(name)
        p.add_argument("--input")
        p.add_argument("--fixtures-dir")
        p.add_argument("--output")
        p.add_argument("--summary", action="store_true")
        p.add_argument("--fixture")
    a = ap.parse_args()

    if a.cmd == "build-default":
        _dump(a.output, build_default_policy().__dict__)
        return 0
    if a.cmd == "validate":
        res = validate_policy(HouseholdCameraRedactionPipelinePolicy(**_load(a.input)))
        _dump(a.output, res)
        return 0 if res["ok"] else 2

    data = _load(a.input) if a.input else {}
    if a.cmd == "run-fixture":
        if not a.fixtures_dir or not a.fixture:
            raise SystemExit("--fixtures-dir and --fixture required")
        data = _load(str(Path(a.fixtures_dir) / a.fixture))
    result = evaluate_pipeline(data).to_dict()
    if a.cmd == "summarize":
        payload = {"status": result["status"], "route": result["decision"]["route"], "blocked": result["decision"]["blocked"], "digest": result["packet"]["digest"]}
    else:
        payload = result
    _dump(a.output, payload)
    return 2 if result["decision"]["blocked"] and a.cmd in {"run-fixture", "evaluate"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
