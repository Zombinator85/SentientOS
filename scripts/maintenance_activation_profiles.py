#!/usr/bin/env python3
"""CLI for closed maintenance activation profile bundles."""
from __future__ import annotations
import argparse
import json
from typing import Sequence
from sentientos import maintenance_activation_profiles as profiles

def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True)
    t = sub.add_parser("write-manifest-template"); t.add_argument("--output", required=True)
    for name in ("render-profile-bundle", "verify-profile-bundle", "print-activation-plan", "inspect-profile-bundle"):
        q = sub.add_parser(name); q.add_argument("--manifest", required=True)
        if name != "render-profile-bundle": q.add_argument("--evaluation-time", required=True)
    a = p.parse_args(argv)
    try:
        if a.command == "write-manifest-template": out = profiles.write_manifest_template(a.output)
        elif a.command == "render-profile-bundle": out = profiles.render_profile_bundle(a.manifest)
        elif a.command == "verify-profile-bundle": out = profiles.verify_profile_bundle(a.manifest, a.evaluation_time)
        elif a.command == "print-activation-plan": out = profiles.activation_plan(a.manifest, a.evaluation_time)
        else: out = profiles.inspect_profile_bundle(a.manifest, a.evaluation_time)
        print(profiles.canonical_bytes(out).decode()); return 0 if out.get("status") != "profile_bundle_blocked" else 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(profiles.canonical_bytes({"schema_version":"sentientos.maintenance_activation_profile_error:v1","status":"profile_bundle_blocked","reason_codes":[str(exc)]}).decode()); return 2
if __name__ == "__main__": raise SystemExit(main())
