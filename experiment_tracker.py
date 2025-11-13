"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from logging_config import get_log_path
import json
import uuid
import datetime
from typing import Any, Dict, List, Optional, Tuple

from sentientos.experiments.criteria_dsl import (
    CriteriaEvaluationError,
    CriteriaParseError,
    evaluate_criteria,
    parse_criteria,
)

DATA_FILE = get_log_path("experiments.json", "EXPERIMENTS_FILE")
AUDIT_FILE = get_log_path("experiment_audit.jsonl", "EXPERIMENT_AUDIT_FILE")
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def _load() -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(data: List[Dict[str, Any]]) -> None:
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _audit(action: str, exp_id: str, **meta: Any) -> None:
    entry = {"timestamp": _now(), "action": action, "experiment": exp_id, **meta}
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _snapshot_context(context: Dict[str, Any]) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    for key, value in context.items():
        if isinstance(value, (int, float, str, bool)) or value is None:
            snapshot[key] = value
        else:
            snapshot[key] = repr(value)
    return snapshot


def _evaluate_experiment_criteria(
    experiment: Optional[Dict[str, Any]], context: Dict[str, Any]
) -> Tuple[bool, Optional[str], Optional[str]]:
    if not isinstance(context, dict):
        criteria = experiment.get("criteria") if experiment else None
        return False, criteria, "invalid_context"

    if experiment is None:
        return False, None, "missing_experiment"

    criteria = experiment.get("criteria")
    if not criteria:
        return False, None, "no_criteria"

    try:
        parsed = parse_criteria(str(criteria))
    except CriteriaParseError as exc:
        return False, str(criteria), f"parse_error: {exc}"

    try:
        result = bool(evaluate_criteria(parsed, context))
        return result, str(criteria), None
    except CriteriaEvaluationError as exc:
        return False, str(criteria), f"evaluation_error: {exc}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, str(criteria), f"unexpected_error: {exc}"


def auto_propose_experiment(
    description: str,
    conditions: str,
    expected: str,
    *,
    criteria: Optional[str] = None,
    signals: Optional[Dict[str, Any]] = None,
) -> str:
    """Programmatically create and immediately activate an experiment."""
    exp_id = propose_experiment(
        description,
        conditions,
        expected,
        proposer="auto",
        criteria=criteria,
    )
    update_status(exp_id, "active")
    _audit("auto_propose", exp_id, signals=signals)
    return exp_id


def log_trigger(exp_id: str, signals: Optional[Dict[str, Any]] = None) -> None:
    """Record that an experiment was triggered by autonomous logic."""
    _audit("trigger", exp_id, signals=signals)


def propose_experiment(
    description: str,
    conditions: str,
    expected: str,
    *,
    proposer: Optional[str] = None,
    criteria: Optional[str] = None,
) -> str:
    exp_id = uuid.uuid4().hex[:8]
    data = _load()
    info = {
        "id": exp_id,
        "description": description,
        "conditions": conditions,
        "expected": expected,
        "status": "pending",
        "votes": {},
        "comments": [],
        "triggers": 0,
        "success": 0,
    }
    if criteria:
        info["criteria"] = criteria
    data.append(info)
    _save(data)
    _audit("propose", exp_id, by=proposer)
    return exp_id


def list_experiments(status: Optional[str] = None) -> List[Dict[str, Any]]:
    data = _load()
    if status:
        data = [d for d in data if d.get("status") == status]
    return data


def get_experiment(exp_id: str) -> Optional[Dict[str, Any]]:
    for e in _load():
        if e.get("id") == exp_id:
            return e
    return None


def evaluate_experiment_success(exp_id: str, context: Dict[str, Any]) -> bool:
    experiment = get_experiment(exp_id)
    result, _, _ = _evaluate_experiment_criteria(experiment, context)
    return result


def vote_experiment(exp_id: str, user: str, upvote: bool = True, threshold: int = 2) -> bool:
    data = _load()
    changed = False
    for e in data:
        if e.get("id") == exp_id:
            votes = e.setdefault("votes", {})
            votes[user] = 1 if upvote else -1
            pos = sum(1 for v in votes.values() if v > 0)
            if pos >= threshold and e.get("status") == "pending":
                e["status"] = "active"
            changed = True
            _audit("vote", exp_id, by=user, value=1 if upvote else -1)
            break
    if changed:
        _save(data)
    return changed


def comment_experiment(exp_id: str, user: str, text: str) -> bool:
    data = _load()
    changed = False
    for e in data:
        if e.get("id") == exp_id:
            e.setdefault("comments", []).append({
                "user": user,
                "text": text,
                "timestamp": _now(),
            })
            changed = True
            _audit("comment", exp_id, by=user)
            break
    if changed:
        _save(data)
    return changed


def update_status(exp_id: str, status: str) -> bool:
    data = _load()
    for e in data:
        if e.get("id") == exp_id:
            e["status"] = status
            _save(data)
            _audit("status_change", exp_id, status=status)
            return True
    return False


def evaluate_and_log_experiment_success(exp_id: str, context: Dict[str, Any]) -> bool:
    experiment = get_experiment(exp_id)
    result, criteria, error = _evaluate_experiment_criteria(experiment, context)

    if isinstance(context, dict):
        context_snapshot: Any = _snapshot_context(context)
    else:
        context_snapshot = repr(context)

    meta: Dict[str, Any] = {
        "criteria": criteria,
        "context": context_snapshot,
        "result": result,
    }
    if error:
        meta["error"] = error

    _audit("criteria_evaluation", exp_id, **meta)
    status = "PASS" if result else "FAIL"
    print(f"[criteria] Experiment {exp_id}: {status}")
    return result


def record_result(exp_id: str, success: bool) -> bool:
    data = _load()
    for e in data:
        if e.get("id") == exp_id:
            e["triggers"] = e.get("triggers", 0) + 1
            if success:
                e["success"] = e.get("success", 0) + 1
            _save(data)
            _audit("result", exp_id, success=success)
            return True
    return False
