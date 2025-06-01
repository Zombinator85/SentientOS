import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict

LOG_PATH = Path("logs/teaching_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_teaching(teacher: str, learner: str, ritual: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "teacher": teacher,
        "learner": learner,
        "ritual": ritual,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_teachings(term: str = "") -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if term and term not in line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Ritual teaching log")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Record a ritual teaching")
    lg.add_argument("teacher")
    lg.add_argument("learner")
    lg.add_argument("ritual")
    lg.set_defaults(func=lambda a: print(json.dumps(log_teaching(a.teacher, a.learner, a.ritual), indent=2)))

    ls = sub.add_parser("list", help="List teachings")
    ls.add_argument("--term", default="")
    ls.set_defaults(func=lambda a: print(json.dumps(list_teachings(a.term), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
