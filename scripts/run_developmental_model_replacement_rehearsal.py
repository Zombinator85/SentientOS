from __future__ import annotations
import argparse, json
from pathlib import Path
from sentientos.developmental_model_replacement_rehearsal import prepare, run_next, summarize, verify

def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded synthetic model-replacement rehearsal action")
    parser.add_argument("command", choices=("prepare", "run-next", "verify", "summarize"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fault", choices=("model_b_load_failure", "loaded_identity_drift", "inference_currentness_failure"))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    if args.fault and args.command != "prepare": parser.error("--fault is prepare-only")
    result = {"prepare": lambda: prepare(args.root, fault=args.fault), "run-next": lambda: run_next(args.root),
              "verify": lambda: verify(args.root), "summarize": lambda: summarize(args.root)}[args.command]()
    if args.summary: print(json.dumps(dict(result), sort_keys=True))
    return 0
if __name__ == "__main__": raise SystemExit(main())
