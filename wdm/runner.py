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

    # Redact sensitive patterns before sending to outside AIs
    patterns = cfg.get("redaction", {}).get("patterns", [])
    seed = redact(seed, patterns)

    # Check rate limits
    buckets = build_buckets(cfg)
    if not buckets["default"].allow():
        return {"decision": decision, "reason": "rate_limited"}

    # Cheers mode → short ambient 1-round dialogue
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

    # Seed message
    bus.publish(Message(agent="wdm", role="referee", content=seed, round=0, kind="seed"))
    rounds = cfg.get("max_rounds", 2)

    for r in range(1, rounds + 1):
        # Agents answer
        for a in adapters:
            bus.publish(
                Message(agent=a.name, role="agent", content=a.answer(seed), round=r, kind="answer")
            )
        # Critiques
        last = [m for m in bus.history() if m.round == r and m.kind == "answer"]
        for a in adapters:
            for m in last:
                if m.agent != a.name:
                    bus.publish(
                        Message(agent=a.name, role="agent", content=a.critique(m.content), round=r, kind="critique")
                    )
        # Stop early if stable
        if ref.stable(last):
            break

    # Always dump logs
    outdir = Path(cfg.get("logging", {}).get("jsonl_path", "logs/wdm/"))
    outdir.mkdir(parents=True, exist_ok=True)
    logfile = outdir / f"wdm_{int(time.time())}.jsonl"
    bus.dump_jsonl(logfile)

    # If cheers mode, also dump to cheers channel
    if cheers:
        cheers_path = cfg.get("activation", {}).get("cheers_channel", "logs/wdm/cheers.jsonl")
        bus.dump_jsonl(cheers_path)

    return {"decision": decision, "rounds": r, "log": str(logfile)}
