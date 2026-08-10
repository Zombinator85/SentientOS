from __future__ import annotations

"""JSON-only CLI for bounded live discernment calibration."""

import argparse
import json
from pathlib import Path

from sentientos.discernment_calibration import DiscernmentCalibrationRunner, calibration_doctor
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run", "doctor"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    model = LocalModel.autoload()
    authority = build_local_model_authority_map(model.config)
    if args.command == "doctor":
        report = calibration_doctor(model=model, authority_map=authority, runtime_root=args.runtime_root)
    else:
        invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
                                            runtime_root=args.runtime_root / "invocations")
        report = DiscernmentCalibrationRunner(args.repo_root, args.runtime_root, model,
                                              authority, invoker).run()
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
