"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

import json, argparse, yaml
from wdm.runner import run_wdm


def main() -> None:
    ap = argparse.ArgumentParser(description="Wild-Dialogue Mode runner")
    ap.add_argument("--seed", required=True)
    ap.add_argument("--context", default="{}")
    ap.add_argument("--config", default="config/wdm.yaml")
    args = ap.parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ctx = json.loads(args.context)
    out = run_wdm(args.seed, ctx, cfg)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

