from __future__ import annotations

from dataclasses import dataclass

from .commands_provenance import TargetArgs, WaitArgs, handle_pr_checks, handle_wait_checks
from .context import ForgeContext


@dataclass(frozen=True)
class CanaryTargetArgs:
    target: str


@dataclass(frozen=True)
class CanaryWaitArgs:
    target: str
    timeout: int


def handle_pr_canary(context: ForgeContext, args: CanaryTargetArgs) -> int:
    return handle_pr_checks(context, TargetArgs(target=args.target))


def handle_wait_canary(context: ForgeContext, args: CanaryWaitArgs) -> int:
    return handle_wait_checks(context, WaitArgs(target=args.target, timeout=args.timeout))
