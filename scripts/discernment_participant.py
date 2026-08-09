from __future__ import annotations

"""JSON-only CLI wiring for an operator-supplied governed local-model invoker."""

import argparse
import json
from pathlib import Path

from sentientos.discernment_participant import DiscernmentParticipantRequest, generate_participant_judgment, live_discernment_readiness
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=("run", "doctor"), default="run")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    model = LocalModel.autoload()
    authority_map = build_local_model_authority_map(model.config)
    if args.command == "doctor":
        print(json.dumps(live_discernment_readiness(model, authority_map), sort_keys=True, ensure_ascii=False))
        return 0
    if args.request is None:
        parser.error("--request is required for run")
    value = json.loads(args.request.read_text(encoding="utf-8"))
    request = DiscernmentParticipantRequest(repo_root=args.repo_root, **value)
    result = generate_participant_judgment(request, invoker=GovernedLocalModelInvoker(model=model, authority_map=authority_map))
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
