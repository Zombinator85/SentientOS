"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
from sentientos.parliament_bus import ParliamentBus, Turn


def test_multi_pub_sub() -> None:
    async def runner() -> None:
        bus = ParliamentBus()
        turns_a = [Turn("A", str(i)) for i in range(2)]
        turns_b = [Turn("B", str(i)) for i in range(2)]
        all_turns = turns_a + turns_b
        r1: list[Turn] = []
        r2: list[Turn] = []

        async def consume(dest: list[Turn]) -> None:
            async for t in bus.subscribe():
                dest.append(t)
                if len(dest) >= len(all_turns):
                    break

        async def produce(items: list[Turn]) -> None:
            for t in items:
                await bus.publish(t)

        await asyncio.gather(
            consume(r1),
            consume(r2),
            produce(turns_a),
            produce(turns_b),
        )
        assert r1 == all_turns
        assert r2 == all_turns

    asyncio.run(runner())


def test_turn_emotion() -> None:
    async def runner() -> None:
        bus = ParliamentBus()
        turn = Turn("A", "hi", emotion="joy")
        await bus.publish(turn)
        async for t in bus.subscribe():
            assert t.emotion == "joy"
            break

    asyncio.run(runner())
