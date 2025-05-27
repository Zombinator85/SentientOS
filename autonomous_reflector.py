import time
from api import actuator
import memory_manager as mm

INTERVAL = 60


def _plan() -> dict | None:
    """Select the next goal to work on."""
    return mm.next_goal()


def _act(goal: dict) -> dict:
    step = goal.get("critique_step", 0)
    intent = goal.get("intent", {})
    return actuator.act(intent, explanation=goal.get("text", ""), critique_step=step)


def _self_patch(goal: dict, result: dict) -> None:
    """Log a brief self-improvement note based on the outcome."""
    if result.get("status") == "finished":
        note = f"Goal {goal['id']} succeeded"
    else:
        note = f"Goal {goal['id']} failed {goal.get('failure_count',0)} times"
    mm.append_memory(note, tags=["self_patch"], source="agent")


def _reflect(goal: dict, result: dict) -> None:
    goal["last_result"] = result
    if result.get("status") == "finished":
        goal["status"] = "completed"
    else:
        goal["status"] = "failed"
        goal["failure_count"] = goal.get("failure_count", 0) + 1
        goal["critique_step"] = result.get("critique_step", goal.get("critique_step", 0))
        goal["critique"] = result.get("critique")
        if goal["failure_count"] >= 3:
            goal["status"] = "stuck"
            actuator.act({"type": "escalate", "goal": goal["id"], "text": goal.get("text", "")})
    mm.save_goal(goal)
    _self_patch(goal, result)


def run_loop(interval: float = INTERVAL, iterations: int | None = None) -> None:
    """Run the autonomous cycle for ``iterations`` steps."""
    actuator.reload_plugins()
    count = 0
    while iterations is None or count < iterations:
        goal = _plan()
        if goal:
            res = _act(goal)
            _reflect(goal, res)
        if iterations is not None:
            count += 1
        time.sleep(interval)


def run_once() -> None:
    """Execute a single planning cycle."""
    run_loop(iterations=1)


if __name__ == "__main__":  # pragma: no cover - CLI
    import argparse

    p = argparse.ArgumentParser(description="Run autonomous agent")
    p.add_argument("--once", action="store_true", help="Run a single cycle")
    p.add_argument("--cycles", type=int, help="Number of cycles to run")
    args = p.parse_args()

    if args.once:
        run_once()
    else:
        run_loop(iterations=args.cycles)
