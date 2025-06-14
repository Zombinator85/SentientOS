"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Headless Parliament demo using the global reasoning bus."""

import asyncio
import os


import reasoning_engine as re
import parliament_bus
import demo_recorder as dr


async def model_one(msg: str) -> str:
    return msg + "1"


async def model_two(msg: str) -> str:
    return msg + "2"


async def model_three(msg: str) -> str:
    return msg + "3"


async def run_demo() -> None:
    os.environ["SENTIENTOS_HEADLESS"] = "1"

    re.register_model("one", model_one)
    re.register_model("two", model_two)
    re.register_model("three", model_three)

    recorder = dr.DemoRecorder()
    recorder.start()

    prompt = "parliament demo"
    message = prompt
    turn_id = 0
    for cycle in range(2):
        await re.parliament(message, ["one", "two", "three"], profile="default")
        while not re.parliament_bus.empty():
            turn = re.parliament_bus.get()
            turn_id += 1
            await parliament_bus.bus.publish({
                "cycle": cycle + 1,
                "agent": turn.model,
                "turn_id": turn_id,
                "message": turn.message,
                "reply": turn.reply,
                "emotion": turn.emotion,
            })
        message = turn.reply

    recorder.stop()
    out_path = recorder.export()
    print(f"Demo saved to {out_path}")


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()

