from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable

GOAL_GRAPH_PATH = Path("glow/forge/goals/goal_graph.json")
GOAL_STATE_PATH = Path("glow/forge/goals/goal_state.json")


@dataclass(frozen=True, slots=True)
class Goal:
    goal_id: str
    description: str
    weight: float
    priority: int
    dependencies: tuple[str, ...]
    completion_check: str
    risk_cost_estimate: int
    throughput_cost_estimate: int
    tags: tuple[str, ...]
    enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["dependencies"] = list(self.dependencies)
        payload["tags"] = list(self.tags)
        return payload


@dataclass(frozen=True, slots=True)
class GoalGraph:
    schema_version: int
    goals: tuple[Goal, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "goals": [goal.to_dict() for goal in self.goals],
        }


@dataclass(frozen=True, slots=True)
class GoalStateRecord:
    schema_version: int
    progress: float
    status: str
    last_attempt_at: str | None
    last_result: str | None
    last_evidence_paths: tuple[str, ...]
    blocked_reason: str | None
    failure_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "progress": self.progress,
            "status": self.status,
            "last_attempt_at": self.last_attempt_at,
            "last_result": self.last_result,
            "last_evidence_paths": list(self.last_evidence_paths),
            "blocked_reason": self.blocked_reason,
            "failure_count": self.failure_count,
        }


def default_goal_state_record() -> GoalStateRecord:
    return GoalStateRecord(
        schema_version=1,
        progress=0.0,
        status="active",
        last_attempt_at=None,
        last_result=None,
        last_evidence_paths=(),
        blocked_reason=None,
        failure_count=0,
    )


def load_goal_graph(repo_root: Path) -> GoalGraph:
    path = repo_root.resolve() / GOAL_GRAPH_PATH
    if not path.exists():
        graph = GoalGraph(schema_version=1, goals=())
        persist_goal_graph(repo_root, graph)
        return graph
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return GoalGraph(schema_version=1, goals=())
    if not isinstance(payload, dict):
        return GoalGraph(schema_version=1, goals=())
    rows = payload.get("goals")
    if not isinstance(rows, list):
        rows = []
    goals: list[Goal] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        goal_id = row.get("goal_id")
        if not isinstance(goal_id, str) or not goal_id.strip():
            continue
        dependencies = tuple(str(item) for item in row.get("dependencies", []) if isinstance(item, str) and item)
        tags = tuple(sorted({str(item).strip().lower() for item in row.get("tags", []) if isinstance(item, str) and item.strip()}))
        goals.append(
            Goal(
                goal_id=goal_id,
                description=str(row.get("description", "")),
                weight=float(row.get("weight", 0.0)),
                priority=int(row.get("priority", 0)),
                dependencies=dependencies,
                completion_check=str(row.get("completion_check", "")),
                risk_cost_estimate=max(0, int(row.get("risk_cost_estimate", 0))),
                throughput_cost_estimate=max(0, int(row.get("throughput_cost_estimate", 0))),
                tags=tags,
                enabled=bool(row.get("enabled", True)),
            )
        )
    graph = GoalGraph(schema_version=int(payload.get("schema_version", 1)), goals=tuple(goals))
    return GoalGraph(schema_version=1, goals=tuple(order_goals_deterministic(graph.goals)))


def persist_goal_graph(repo_root: Path, graph: GoalGraph) -> None:
    path = repo_root.resolve() / GOAL_GRAPH_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "goals": [goal.to_dict() for goal in order_goals_deterministic(graph.goals)],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_goal_state(repo_root: Path) -> dict[str, GoalStateRecord]:
    path = repo_root.resolve() / GOAL_STATE_PATH
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("goals")
    if not isinstance(rows, dict):
        return {}
    result: dict[str, GoalStateRecord] = {}
    for goal_id, raw in rows.items():
        if not isinstance(goal_id, str) or not isinstance(raw, dict):
            continue
        result[goal_id] = GoalStateRecord(
            schema_version=1,
            progress=max(0.0, min(1.0, float(raw.get("progress", 0.0)))),
            status=str(raw.get("status", "active")),
            last_attempt_at=raw.get("last_attempt_at") if isinstance(raw.get("last_attempt_at"), str) else None,
            last_result=raw.get("last_result") if isinstance(raw.get("last_result"), str) else None,
            last_evidence_paths=tuple(str(item) for item in raw.get("last_evidence_paths", []) if isinstance(item, str)),
            blocked_reason=raw.get("blocked_reason") if isinstance(raw.get("blocked_reason"), str) else None,
            failure_count=max(0, int(raw.get("failure_count", 0))),
        )
    return result


def persist_goal_state(repo_root: Path, state: dict[str, GoalStateRecord]) -> None:
    path = repo_root.resolve() / GOAL_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "goals": {goal_id: record.to_dict() for goal_id, record in sorted(state.items(), key=lambda item: item[0])},
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def order_goals_deterministic(goals: tuple[Goal, ...] | list[Goal]) -> list[Goal]:
    return sorted(
        goals,
        key=lambda goal: (
            -int(goal.priority),
            -float(goal.weight),
            int(goal.risk_cost_estimate),
            int(goal.throughput_cost_estimate),
            str(goal.goal_id),
        ),
    )


def detect_dependency_cycles(graph: GoalGraph) -> list[list[str]]:
    node_ids = {goal.goal_id for goal in graph.goals}
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {goal.goal_id: 0 for goal in graph.goals}
    for goal in graph.goals:
        for dep in goal.dependencies:
            if dep in node_ids:
                adjacency[dep].append(goal.goal_id)
                indegree[goal.goal_id] += 1

    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in sorted(adjacency.get(node, [])):
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)

    if visited == len(node_ids):
        return []

    cycle_nodes = sorted([node for node, degree in indegree.items() if degree > 0])
    return [cycle_nodes] if cycle_nodes else []


def dependency_unmet(goal: Goal, completed_ids: set[str], goal_ids: set[str]) -> bool:
    for dependency in goal.dependencies:
        if dependency in goal_ids and dependency not in completed_ids:
            return True
    return False


def goal_graph_hash(graph: GoalGraph) -> str:
    canonical = json.dumps(
        {
            "schema_version": 1,
            "goals": [goal.to_dict() for goal in order_goals_deterministic(graph.goals)],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def completion_registry_default() -> dict[str, Callable[[Goal], bool]]:
    return {}


__all__ = [
    "GOAL_GRAPH_PATH",
    "GOAL_STATE_PATH",
    "Goal",
    "GoalGraph",
    "GoalStateRecord",
    "completion_registry_default",
    "default_goal_state_record",
    "dependency_unmet",
    "detect_dependency_cycles",
    "goal_graph_hash",
    "load_goal_graph",
    "load_goal_state",
    "order_goals_deterministic",
    "persist_goal_graph",
    "persist_goal_state",
]
