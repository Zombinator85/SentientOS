from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.production_self_reflection_campaign import (
    ProductionSelfReflectionCampaign, ProductionSelfReflectionProtocol,
    reconstruct_protocol, verify_production_readiness,
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Operate one fail-closed production self-reflection campaign action")
    parser.add_argument("command", choices=("create", "readiness", "run-one", "status", "report"))
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--observed", type=Path)
    parser.add_argument("--evidence-bundle", type=Path)
    parser.add_argument("--readiness-output", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        if args.config is None: parser.error("create requires --config")
        value = _read(args.config)
        protocol = ProductionSelfReflectionProtocol.create(**value)
        campaign = ProductionSelfReflectionCampaign.create(args.campaign_root, protocol)
        result = {"status": "campaign_created", "protocol_id": protocol.protocol_id,
                  "protocol_digest": protocol.protocol_digest, "campaign_state": dict(campaign.state())}
    else:
        campaign = ProductionSelfReflectionCampaign.reconstruct(args.campaign_root)
        if args.command == "status": result = {"status": "campaign_status", "campaign_state": dict(campaign.state())}
        elif args.command == "report": result = dict(campaign.report())
        else:
            if args.observed is None: parser.error(f"{args.command} requires --observed")
            readiness = verify_production_readiness(campaign.protocol, _read(args.observed), artifact_path=args.readiness_output)
            if args.command == "readiness": result = dict(readiness)
            else:
                if args.evidence_bundle is None: parser.error("run-one requires --evidence-bundle from the live sentientosd transition composition")
                evidence = _read(args.evidence_bundle)
                receipt = campaign.run_one(readiness, lambda trial_id, protocol: evidence)
                result = {"status": "completed_one_trial", "receipt": dict(receipt)}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
