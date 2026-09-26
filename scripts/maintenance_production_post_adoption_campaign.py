"""Explicit operator CLI for one exactly named production attribution campaign."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.maintenance_post_adoption_attribution_campaign import ControlDefinition, make_campaign_protocol
from sentientos.maintenance_post_adoption_evaluation import Baseline, MeasurementDefinition, make_protocol
from sentientos.maintenance_production_post_adoption_campaign import MaintenanceProductionPostAdoptionCampaign


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maintenance-production-post-adoption-campaign")
    parser.add_argument("--state-root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "prepare", "status", "observe-next", "interrupt-next", "finalize", "report", "verify"):
        item = commands.add_parser(name); item.add_argument("--campaign-id")
        if name in {"doctor", "observe-next"}: item.add_argument("--evidence-json", required=True)
        if name == "prepare": item.add_argument("--package-json", required=True)
        if name == "observe-next": item.add_argument("--observation-json", required=True)
        if name in {"interrupt-next", "finalize"}: item.add_argument("--completed-at", required=True)
        if name == "report": item.add_argument("--proposition-id")
        if name == "doctor": item.add_argument("--output")
    args = parser.parse_args(argv); owner = MaintenanceProductionPostAdoptionCampaign(args.state_root)
    if args.command == "prepare":
        package = _load(args.package_json); campaign_data = dict(package["campaign_protocol"])
        campaign_data.pop("campaign_id", None); campaign_data.pop("campaign_digest", None)
        campaign_data.pop("schema_version", None); campaign_data.pop("authority", None)
        campaign_data["controls"] = tuple(ControlDefinition(**x) for x in campaign_data["controls"])
        campaign = make_campaign_protocol(**campaign_data); evaluations = []; baselines = []
        for value in package["evaluation_protocols"]:
            data = dict(value); data.pop("protocol_id", None); data.pop("protocol_digest", None)
            data.pop("schema_version", None); data.pop("authority", None)
            data["measurements"] = tuple(MeasurementDefinition(**x) for x in data["measurements"])
            evaluations.append(make_protocol(**data))
        for value in package["baselines"]:
            data = dict(value); data["authority"] = dict(data["authority"]); baselines.append(Baseline(**data))
        result = owner.prepare(campaign, evaluations, baselines)
    elif args.command == "doctor":
        result = owner.readiness(args.campaign_id, _load(args.evidence_json), artifact_path=args.output)
    elif args.command == "status": result = owner.readiness(args.campaign_id, {})
    elif args.command == "observe-next":
        observation = _load(args.observation_json)
        result = owner.observe_next(args.campaign_id, _load(args.evidence_json), **observation)
    elif args.command == "interrupt-next": result = owner.interrupt_next(args.campaign_id, completed_at=args.completed_at)
    elif args.command == "finalize": result = owner.finalize(args.campaign_id, completed_at=args.completed_at)
    elif args.command == "report": result = owner.report(args.campaign_id, proposition_id=args.proposition_id)
    else: result = owner.verify(args.campaign_id)
    print(json.dumps(result, sort_keys=True, default=list)); return 0


if __name__ == "__main__": raise SystemExit(main())
