"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import json
import os
import time
from collections import deque
from typing import Deque, Dict

from api import actuator
import council_consensus as council
import memory_manager as mm
from notification import send as notify
from self_patcher import apply_patch
import skill_library as skills
import critic_daemon
import reflexion_loop as reflexion
import goal_curator
import oracle_bridge
import emotion_ledger_analytics as emotion_analytics

INTERVAL = 60
METACOG_INTERVAL = max(2, int(os.getenv("AUTONOMOUS_METACOG_INTERVAL", "5")))
CURATION_INTERVAL = max(METACOG_INTERVAL, int(os.getenv("AUTONOMOUS_CURATION_INTERVAL", "10")))


def _plan() -> dict | None:
    """Select the next goal to work on."""
    return mm.next_goal()


def _inject_skill_hints(goal: dict) -> None:
    hints = skills.suggest_skills(goal.get("text", ""), limit=3)
    if not hints:
        return
    goal["skill_hints"] = [hint.get("description", "") for hint in hints]
    mm.append_memory(
        json.dumps({"skill_hints": {"goal": goal.get("id"), "hints": goal["skill_hints"]}}),
        tags=["skill_hint", goal.get("id", "")],
        source="autonomous_reflector",
    )


def _act(goal: dict) -> tuple[dict, dict]:
    step = goal.get("critique_step", 0)
    intent = goal.get("intent", {})
    consensus = council.deliberate(intent, goal.get("text", ""))
    goal["consensus"] = consensus
    if not consensus.get("approved"):
        oracle_bridge.consult(goal.get("text", ""), intent=intent)
        notify(
            "goal_blocked",
            {
                "id": goal.get("id"),
                "text": goal.get("text", ""),
                "reason": "council rejected intent",
                "votes": consensus.get("votes", []),
            },
        )
        return {
            "status": "blocked",
            "error": "council rejected intent",
            "consensus": consensus,
        }, consensus
    result = actuator.act(intent, explanation=goal.get("text", ""), critique_step=step)
    if result.get("status") not in {"finished", "success"}:
        oracle_bridge.consult(goal.get("text", ""), intent=intent)
    return result, consensus


def _self_patch(goal: dict, result: dict, consensus: dict) -> None:
    """Log a brief self-improvement note based on the outcome."""
    if result.get("status") == "finished":
        note = f"Goal {goal['id']} succeeded"
    elif result.get("status") == "blocked":
        note = f"Goal {goal['id']} blocked by council"
    else:
        note = f"Goal {goal['id']} failed {goal.get('failure_count',0)} times"
    apply_patch(note, auto=True)
    notify("self_patch", {"goal": goal["id"], "note": note})


def _log_reflection(goal: dict, result: dict, consensus: dict) -> None:
    payload = {
        "goal": goal.get("id"),
        "status": result.get("status"),
        "consensus": consensus,
        "failure_count": goal.get("failure_count", 0),
        "skill_hints": goal.get("skill_hints", []),
    }
    mm.append_memory(
        json.dumps({"autonomy_reflection": payload}),
        tags=["reflection", "autonomy"],
        source="autonomous_reflector",
    )


def _reflect(goal: dict, result: dict, consensus: dict) -> None:
    goal["last_result"] = result
    if result.get("status") == "finished":
        goal["status"] = "completed"
        notify("goal_completed", {"id": goal["id"], "text": goal.get("text", "")})
        skills.register_skill(goal, result)
    elif result.get("status") == "blocked":
        goal["status"] = "needs_review"
        goal["critique"] = "council consensus rejected intent"
    else:
        goal["status"] = "failed"
        goal["failure_count"] = goal.get("failure_count", 0) + 1
        goal["critique_step"] = result.get("critique_step", goal.get("critique_step", 0))
        goal["critique"] = result.get("critique")
        if goal["failure_count"] >= 3:
            goal["status"] = "stuck"
            actuator.act({"type": "escalate", "goal": goal["id"], "text": goal.get("text", "")})
            notify("escalation", {"id": goal["id"], "text": goal.get("text", "")})
            notify("goal_stuck", {"id": goal["id"], "text": goal.get("text", "")})
    mm.save_goal(goal)
    critic_daemon.review_action(goal, result, consensus)
    reflexion.record_insight(goal, result, consensus)
    _self_patch(goal, result, consensus)
    _log_reflection(goal, result, consensus)


def _metacognitive_checkpoint(history: Deque[Dict[str, dict]]) -> None:
    if not history:
        return
    completed = sum(1 for item in history if item["result"].get("status") == "finished")
    blocked = sum(1 for item in history if item["result"].get("status") == "blocked")
    failed = sum(1 for item in history if item["result"].get("status") == "failed")
    note = (
        f"Metacognitive checkpoint → completed={completed} blocked={blocked} failed={failed}"
    )
    mm.append_memory(note, tags=["metacognition", "autonomy"], source="autonomous_reflector")
    snapshot = emotion_analytics.capture_snapshot()
    notify(
        "metacognition",
        {
            "completed": completed,
            "blocked": blocked,
            "failed": failed,
            "window": len(history),
            "emotion_severity": snapshot.get("severity"),
        },
    )
    mm.curate_memory()


def run_loop(interval: float = INTERVAL, iterations: int | None = None) -> None:
    """Run the autonomous cycle for ``iterations`` steps."""
    actuator.reload_plugins()
    count = 0
    history: Deque[Dict[str, dict]] = deque(maxlen=METACOG_INTERVAL)
    while iterations is None or count < iterations:
        goal = _plan()
        if goal:
            _inject_skill_hints(goal)
            result, consensus = _act(goal)
            _reflect(goal, result, consensus)
            history.append({"goal": goal, "result": result, "consensus": consensus})
            if len(history) >= METACOG_INTERVAL:
                _metacognitive_checkpoint(history)
                history.clear()
        if iterations is not None:
            count += 1
        else:
            count += 1
        if count and count % CURATION_INTERVAL == 0:
            mm.curate_memory()
            goal_curator.maybe_schedule_goals()
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
