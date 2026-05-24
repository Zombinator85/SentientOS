from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.household_presence_layer import build_default_household_presence_layer, household_presence_layer_json, validate_household_presence_layer

def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for n in ("build-default","validate","summarize"):
        sp = sub.add_parser(n)
        sp.add_argument("--input", type=Path)
        sp.add_argument("--output", type=Path)
        sp.add_argument("--summary", action="store_true")
    a = p.parse_args()
    layer = build_default_household_presence_layer() if not a.input else json.loads(a.input.read_text(encoding='utf-8'))
    if a.cmd == "validate":
        res = validate_household_presence_layer(layer)
        out = json.dumps(res, indent=2, sort_keys=True)+"\n"
        if a.output: a.output.write_text(out, encoding='utf-8')
        else: print(out, end="")
        return 0 if res["ok"] else 1
    if a.cmd == "summarize" or a.summary:
        summary = {"schema_version": layer["schema_version"], "rule_count": len(layer["discernment_rules"]), "metadata_only": layer["metadata_only"], "digest": layer["deterministic_digest"]}
        out = json.dumps(summary, indent=2, sort_keys=True)+"\n"
        if a.output: a.output.write_text(out, encoding='utf-8')
        else: print(out, end="")
        return 0
    out = household_presence_layer_json(layer)
    if a.output: a.output.write_text(out, encoding='utf-8')
    else: print(out, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
