from __future__ import annotations

"""Advisory pruner for Codex prompt/context payloads."""

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ContextBlock:
    name: str
    category: str
    content: str

    def footprint(self) -> int:
        return len(self.content.encode("utf-8"))


@dataclass(frozen=True)
class PrunePlan:
    blocks: tuple[ContextBlock, ...]

    def to_dict(self) -> list[dict[str, object]]:
        return [
            {
                "name": block.name,
                "category": block.category,
                "bytes": block.footprint(),
            }
            for block in self.blocks
        ]


class CodexContextPruner:
    """Measure prompt footprint and recommend safe pruning order."""

    def evaluate(self, blocks: Sequence[ContextBlock]) -> dict[str, object]:
        sorted_blocks = sorted(blocks, key=lambda block: block.footprint(), reverse=True)
        ranked_plan = PrunePlan(tuple(sorted_blocks))
        totals = self._totals(sorted_blocks)
        return {
            "totals": totals,
            "plan": ranked_plan,
            "safe": True,
            "prune_order": [block.name for block in ranked_plan.blocks],
        }

    def _totals(self, blocks: Iterable[ContextBlock]) -> dict[str, object]:
        totals: dict[str, int] = {"bytes": 0, "tokens_estimate": 0}
        for block in blocks:
            footprint = block.footprint()
            totals["bytes"] += footprint
            totals["tokens_estimate"] += max(1, footprint // 4)
        return totals


__all__ = ["CodexContextPruner", "ContextBlock", "PrunePlan"]
