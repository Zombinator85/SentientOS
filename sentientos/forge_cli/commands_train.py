from __future__ import annotations

from dataclasses import asdict, dataclass

from .context import ForgeContext
from .types import print_json


@dataclass(frozen=True)
class PrArgs:
    pr: int


def handle_status(context: ForgeContext) -> int:
    state = context.merge_train.load_state()
    policy = context.merge_train.load_policy()
    print_json(
        {
            "command": "train-status",
            "enabled": policy.enabled,
            "policy": asdict(policy),
            "state": {
                "entries": [asdict(item) for item in state.entries],
                "last_merged_pr": state.last_merged_pr,
                "last_failure_at": state.last_failure_at,
            },
        },
        indent=2,
    )
    return 0


def handle_enable(context: ForgeContext) -> int:
    policy = context.merge_train.load_policy()
    policy.enabled = True
    context.merge_train.save_policy(policy)
    print_json({"command": "train-enable", "enabled": True})
    return 0


def handle_disable(context: ForgeContext) -> int:
    policy = context.merge_train.load_policy()
    policy.enabled = False
    context.merge_train.save_policy(policy)
    print_json({"command": "train-disable", "enabled": False})
    return 0


def handle_tick(context: ForgeContext) -> int:
    result = context.merge_train.tick()
    print_json({"command": "train-tick", "result": result}, indent=2)
    return 0 if result.get("status") not in {"failed"} else 1


def handle_hold(context: ForgeContext, args: PrArgs) -> int:
    ok = context.merge_train.hold(args.pr)
    print_json({"command": "train-hold", "pr": args.pr, "ok": ok})
    return 0 if ok else 1


def handle_release(context: ForgeContext, args: PrArgs) -> int:
    ok = context.merge_train.release(args.pr)
    print_json({"command": "train-release", "pr": args.pr, "ok": ok})
    return 0 if ok else 1
