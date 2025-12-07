"""Deterministic browser planning primitives for SSA form automation.

Stage-2 builds on selector awareness by generating inert navigation plans.
No browser is driven here—these steps only describe what an orchestrator
*would* do, enabling future OracleRelay execution while remaining
side-effect free.
"""
from __future__ import annotations

from typing import List, Optional


class BrowserStep:
    """A single, immutable browser intention."""

    def __init__(self, page: str, action_type: str, selector: str, value: Optional[str] = None):
        self.page = page
        self.action_type = action_type
        self.selector = selector
        self.value = value

    def as_dict(self) -> dict:
        return {
            "page": self.page,
            "action_type": self.action_type,
            "selector": self.selector,
            "value": self.value,
        }


class BrowserPlan:
    """A deterministic collection of browser steps."""

    def __init__(self, steps: List[BrowserStep]):
        self.steps = steps

    def as_list(self) -> list:
        return [step.as_dict() for step in self.steps]


def build_fill_step(page: str, field: str, selector: str, value: str) -> BrowserStep:
    return BrowserStep(page=page, action_type=f"fill_{field}", selector=selector, value=value)


def build_click_step(page: str, action: str, selector: str) -> BrowserStep:
    return BrowserStep(page=page, action_type=f"click_{action}", selector=selector, value=None)
