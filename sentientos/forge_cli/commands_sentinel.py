from __future__ import annotations

from .context import ForgeContext
from .types import print_json


def handle_status(context: ForgeContext) -> int:
    print_json({"command": "sentinel-status", "status": context.sentinel.summary()}, indent=2)
    return 0


def handle_enable(context: ForgeContext) -> int:
    policy = context.sentinel.load_policy()
    policy.enabled = True
    context.sentinel.save_policy(policy)
    print_json({"command": "sentinel-enable", "enabled": True})
    return 0


def handle_disable(context: ForgeContext) -> int:
    policy = context.sentinel.load_policy()
    policy.enabled = False
    context.sentinel.save_policy(policy)
    print_json({"command": "sentinel-disable", "enabled": False})
    return 0


def handle_tick(context: ForgeContext) -> int:
    print_json({"command": "sentinel-run-tick", "result": context.sentinel.tick()}, indent=2)
    return 0
