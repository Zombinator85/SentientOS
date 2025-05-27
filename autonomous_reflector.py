import time
from api import actuator
import memory_manager as mm

INTERVAL = 60


def _plan() -> dict | None:
    goals = mm.get_goals(open_only=False)
    for g in goals:
        if g.get("status") not in {"completed", "stuck"}:
            return g
    return None


def _act(goal: dict) -> dict:
    step = goal.get("critique_step", 0)
    intent = goal.get("intent", {})
    return actuator.act(intent, explanation=goal.get("text", ""), critique_step=step)


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
    mm.save_goal(goal)


def run_loop(interval: float = INTERVAL, iterations: int | None = None) -> None:
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


if __name__ == "__main__":  # pragma: no cover - CLI
    run_loop()
