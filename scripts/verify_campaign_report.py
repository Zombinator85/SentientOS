from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.production_self_reflection_campaign import (
    ProductionSelfReflectionError,
)
from sentientos.read_only_campaign_report_verification import (
    verify_persisted_campaign_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a persisted completed campaign report without mutation"
    )
    parser.add_argument("--campaign-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = dict(verify_persisted_campaign_report(args.campaign_root))
    except ProductionSelfReflectionError as exc:
        result = {
            "status": "campaign_report_verification_failed",
            "reason": exc.code,
            "read_only": True,
            "effect_performed": False,
            "campaign_advanced": False,
            "grants_authority": False,
            "execution_allowed": False,
        }
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
