import pytest

from sentientos.codex import CodexContextPruner, ContextBlock

pytestmark = pytest.mark.no_legacy_skip


def test_codex_context_pruner_ranks_blocks():
    blocks = [
        ContextBlock(name="governance", category="governance", content="a" * 10),
        ContextBlock(name="memory", category="memory", content="b" * 4),
        ContextBlock(name="narrative", category="narrative", content="c" * 6),
    ]

    result = CodexContextPruner().evaluate(blocks)

    assert result["safe"] is True
    assert result["prune_order"][0] == "governance"
    assert result["totals"]["bytes"] == sum(block.footprint() for block in blocks)
