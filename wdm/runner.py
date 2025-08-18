"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import Dict, List
from pathlib import Path
import time
from council.bus import Bus
from council.schema import Message
from council.referee import Referee
from wdm.policy import should_talk
from wdm.adapters.openai_live import OpenAIAdapter
from wdm.adapters.deepseek_live import DeepSeekAdapter
from wdm.adapters.mistral_live import MistralAdapter
from wdm.utils import redact, build_buckets

def run_wdm(seed: str, context: Dict, cfg: Dict) -> Dict:
    decision = should_talk(context, cfg)
    if decision == "deny":
        return {"decision": "deny", "reason": "policy"}

    patterns = cfg.get("redaction", {}).get("patterns", [])
    seed = redact(seed, patterns)

    buckets = build_buckets(cfg)
    if not buckets["default"].allow():
        return {"decision": decision, "reason": "rate_limited"}

    cheers = cfg.get("activation", {}).get("cheers_enabled", True) and context.get("cheers", False)
    if cheers:
        cfg = {**cfg, "max_rounds": 1}

    bus = Bus()
    ref = Referee(bus, max_rounds=cfg.get("max_rounds", 2))
    adapters_cfg = cfg.get("adapters", {})
    adapters = [
        OpenAIAdapter(model=adapters_cfg.get("openai", {}).get("model", "gpt-4o")),
        DeepSeekAdapter(model=adapters_cfg.get("deepseek", {}).get("model", "deepseek-r1")),
        MistralAdapter(model=adapters_cfg.get("mistral", {}).get("model", "mistral-large")),
    ]

    bus.publish(Message(agent="wdm", role="referee", content=seed, round=0, kind="seed"))
    rounds = cfg.get("max_rounds", 2)

    for r in range(1, rounds+1):
        for a in adapters:
            bus.publish(Message(agent=a.name, role="agent", content=a.answer(seed), round=r, kind="answer"))
        last = [m for m in bus.history() if m.round == r and m.kind == "answer"]
        for a in adapters:
            for m in last:
                if m.agent != a.name:
                    bus.publish(Message(agent=a.name, role="agent", content=a.critique(m.content), round=r, kind="critique"))
        if ref.stable(last):
            break

    outdir = Path(cfg.get("logging", {}).get("jsonl_path", "logs/wdm/"))
    outdir.mkdir(parents=True, exist_ok=True)
    logfile = outdir / f"wdm_{int(time.time())}.jsonl"
    bus.dump_jsonl(logfile)
    if cheers:
        cheers_path = cfg.get("activation", {}).get("cheers_channel", "logs/wdm/cheers.jsonl")
        bus.dump_jsonl(cheers_path)
    return {"decision": decision, "rounds": r, "log": str(logfile)}
