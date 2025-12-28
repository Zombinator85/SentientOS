from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

import task_admission
import task_executor
from log_utils import append_json, read_json
from logging_config import get_log_path
from sentientos.authority_surface import (
    AUTHORITY_DIFF_LOG_PATH,
    diff_authority_surfaces,
    resolve_snapshot_source,
)
from sentientos.governance.routine_delegation import DEFAULT_LOG_PATH as ROUTINE_LOG_PATH
from sentientos.governance.intentional_forgetting import DEFAULT_LOG_PATH as FORGET_LOG_PATH
from sentientos.governance.intentional_forgetting import (
    read_forget_log,
    read_forget_pressure,
    read_forget_pressure_budgets,
)

NARRATIVE_LOG_PATH = get_log_path(
    "narrative_synthesis.jsonl",
    "SENTIENTOS_NARRATIVE_LOG",
)

_DURATION_PATTERN = re.compile(r"(\d+)\s*(minute|minutes|hour|hours|day|days|week|weeks)")


def parse_since(raw: str | None, *, now: datetime | None = None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip().lower()
    if not text:
        return None
    now = now or datetime.now(timezone.utc)
    if text.startswith("yesterday"):
        return now - timedelta(days=1)
    if text.startswith("today"):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if text.startswith("last week"):
        return now - timedelta(weeks=1)
    if text.startswith("last day"):
        return now - timedelta(days=1)
    if text.startswith("last hour"):
        return now - timedelta(hours=1)
    match = _DURATION_PATTERN.search(text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit.startswith("minute"):
            return now - timedelta(minutes=amount)
        if unit.startswith("hour"):
            return now - timedelta(hours=amount)
        if unit.startswith("day"):
            return now - timedelta(days=amount)
        if unit.startswith("week"):
            return now - timedelta(weeks=amount)
    if text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_narrative_summary(
    *,
    since: datetime | None = None,
    source_from: str | None = None,
    source_to: str | None = None,
    now: datetime | None = None,
    log_output: bool = True,
    forgetting_entries: Iterable[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    current_time = now or datetime.now(timezone.utc)
    authority = _collect_authority_changes(since=since, source_from=source_from, source_to=source_to)
    activity = _collect_activity(since=since, forgetting_entries=forgetting_entries)
    sections = [
        _build_authority_section(authority),
        _build_activity_section(activity),
        _build_idle_section(activity),
        _build_boundary_section(activity),
    ]
    output = {
        "view": "narrative_summary",
        "generated_at": current_time.isoformat(),
        "window": {
            "since": since.isoformat() if since else None,
            "source_from": authority.get("source_from"),
            "source_to": authority.get("source_to"),
        },
        "sections": sections,
        "references": _merge_references(section.get("references", {}) for section in sections),
    }
    if log_output:
        log_narrative_generated("narrative_summary", output.get("window"))
    return output


def build_system_summary(*, since: datetime | None = None) -> dict[str, object]:
    return build_system_summary_with_time(since=since, now=None)


def build_system_summary_with_time(*, since: datetime | None = None, now: datetime | None = None) -> dict[str, object]:
    current_time = now or datetime.now(timezone.utc)
    activity = _collect_activity(since=since)
    sections = [
        _build_activity_section(activity, title="System Summary"),
        _build_idle_section(activity),
        _build_boundary_section(activity),
    ]
    output = {
        "view": "system_summary",
        "generated_at": current_time.isoformat(),
        "window": {"since": since.isoformat() if since else None},
        "sections": sections,
        "references": _merge_references(section.get("references", {}) for section in sections),
    }
    log_narrative_generated("system_summary", output.get("window"))
    return output


def build_authority_summary(
    *,
    since: datetime | None = None,
    source_from: str | None = None,
    source_to: str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    current_time = now or datetime.now(timezone.utc)
    authority = _collect_authority_changes(since=since, source_from=source_from, source_to=source_to)
    section = _build_authority_section(authority, title="Authority Summary")
    output = {
        "view": "authority_summary",
        "generated_at": current_time.isoformat(),
        "window": {
            "since": since.isoformat() if since else None,
            "source_from": authority.get("source_from"),
            "source_to": authority.get("source_to"),
        },
        "sections": [section],
        "references": section.get("references", {}),
    }
    log_narrative_generated("authority_summary", output.get("window"))
    return output


def log_narrative_generated(view: str, detail: Mapping[str, object] | None = None) -> None:
    entry: dict[str, object] = {
        "event": "narrative_generated",
        "authority": "none",
        "side_effects": "none",
        "view": view,
    }
    if detail:
        entry["detail"] = dict(detail)
    append_json(Path(NARRATIVE_LOG_PATH), entry)


def _merge_references(reference_sets: Iterable[Mapping[str, object]]) -> dict[str, object]:
    merged: dict[str, set[str]] = {}
    for refs in reference_sets:
        for key, value in refs.items():
            if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
                continue
            bucket = merged.setdefault(key, set())
            for item in value:
                if item:
                    bucket.add(str(item))
    return {key: sorted(values) for key, values in merged.items()}


def _collect_authority_changes(
    *,
    since: datetime | None,
    source_from: str | None,
    source_to: str | None,
) -> dict[str, object]:
    if source_from or source_to:
        before, source_from = resolve_snapshot_source(source_from)
        after, source_to = resolve_snapshot_source(source_to)
        diff = diff_authority_surfaces(before, after)
        return {
            "source_from": source_from,
            "source_to": source_to,
            "changes": list(diff.get("changes", [])),
            "summary": dict(diff.get("summary", {})),
            "diff_hashes": [diff.get("from_hash"), diff.get("to_hash")],
            "log_entry_ids": [],
        }

    entries = _filter_entries(_read_log(AUTHORITY_DIFF_LOG_PATH), since)
    changes: list[Mapping[str, object]] = []
    diff_hashes: list[str] = []
    for entry in entries:
        diff_hashes.extend([
            str(entry.get("from_hash", "")),
            str(entry.get("to_hash", "")),
        ])
        entry_changes = entry.get("changes")
        if isinstance(entry_changes, list):
            changes.extend(entry_changes)
    summary = _summarize_change_impact(changes)
    return {
        "source_from": "diff_log",
        "source_to": "diff_log",
        "changes": changes,
        "summary": summary,
        "diff_hashes": [item for item in diff_hashes if item],
        "log_entry_ids": _extract_log_ids(entries),
    }


def _collect_activity(
    *,
    since: datetime | None,
    forgetting_entries: Iterable[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    task_entries = _filter_entries(_read_log(task_executor.LOG_PATH), since)
    routine_entries = _filter_entries(_read_log(ROUTINE_LOG_PATH), since)
    admission_entries = _filter_entries(_read_log(task_admission.ADMISSION_LOG_PATH), since)
    if forgetting_entries is None:
        forgetting_entries = read_forget_log(FORGET_LOG_PATH)
    forgetting_entries = _filter_entries(forgetting_entries, since)
    tasks = _summarize_tasks(task_entries)
    routines = _summarize_routines(routine_entries)
    admissions = _summarize_admissions(admission_entries)
    forgetting = _summarize_forgetting(forgetting_entries)
    forgetting_pressure = _summarize_forget_pressure(
        read_forget_pressure(FORGET_LOG_PATH),
        read_forget_pressure_budgets(FORGET_LOG_PATH),
    )
    return {
        "tasks": tasks,
        "routines": routines,
        "admissions": admissions,
        "forgetting": forgetting,
        "forgetting_pressure": forgetting_pressure,
        "task_entries": task_entries,
        "routine_entries": routine_entries,
        "admission_entries": admission_entries,
        "forgetting_entries": forgetting_entries,
    }


def _read_log(path: str | Path) -> list[dict[str, object]]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        return read_json(target)
    except Exception:
        return []


def _filter_entries(entries: Iterable[Mapping[str, object]], since: datetime | None) -> list[dict[str, object]]:
    if since is None:
        return [dict(entry) for entry in entries]
    filtered = []
    for entry in entries:
        ts = _parse_timestamp(entry.get("timestamp"))
        if ts is None or ts < since:
            continue
        filtered.append(dict(entry))
    return filtered


def _parse_timestamp(raw: object) -> datetime | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _summarize_change_impact(changes: Iterable[Mapping[str, object]]) -> dict[str, int]:
    summary = {"total": 0, "authority": 0, "semantic_only": 0}
    for change in changes:
        summary["total"] += 1
        if change.get("impact") == "semantic_only":
            summary["semantic_only"] += 1
        else:
            summary["authority"] += 1
    return summary


def _summarize_tasks(entries: Iterable[Mapping[str, object]]) -> dict[str, object]:
    tasks: dict[str, MutableMapping[str, object]] = {}
    for entry in entries:
        task_id = entry.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            continue
        state = tasks.setdefault(task_id, {
            "task_id": task_id,
            "status": None,
            "blocked": False,
            "block_type": None,
            "block_reason": None,
            "adapters": set(),
            "epr_actions": set(),
            "log_ids": set(),
            "reversibility": set(),
        })
        log_id = entry.get("rolling_hash") or entry.get("prev_hash")
        if log_id:
            state["log_ids"].add(str(log_id))
        event = entry.get("event")
        if event == "task_result":
            state["status"] = entry.get("status")
        if event == "epr_action":
            action_id = entry.get("action_id")
            if action_id:
                state["epr_actions"].add(str(action_id))
            reversibility = entry.get("reversibility")
            if reversibility:
                state["reversibility"].add(str(reversibility))
            if entry.get("status") == "blocked":
                state["blocked"] = True
                state["block_type"] = "missing_approval"
                state["block_reason"] = entry.get("error")
        if event == "unknown_prerequisite":
            status = entry.get("status")
            state["blocked"] = True
            state["block_type"] = "missing_approval" if status == "authority-required" else "unmet_prerequisites"
            state["block_reason"] = entry.get("reason")
        if event == "exhaustion":
            state["blocked"] = True
            state["block_type"] = "exhaustion"
            state["block_reason"] = entry.get("reason")
        if entry.get("kind") == "adapter":
            artifacts = entry.get("artifacts")
            if isinstance(artifacts, Mapping):
                adapter_id = artifacts.get("adapter_id")
                if adapter_id:
                    state["adapters"].add(str(adapter_id))
    tasks_list = []
    for task_id, details in tasks.items():
        tasks_list.append({
            "task_id": task_id,
            "status": details.get("status"),
            "blocked": details.get("blocked"),
            "block_type": details.get("block_type"),
            "block_reason": details.get("block_reason"),
            "adapters": sorted(details.get("adapters", set())),
            "epr_actions": sorted(details.get("epr_actions", set())),
            "log_ids": sorted(details.get("log_ids", set())),
            "reversibility": sorted(details.get("reversibility", set())),
        })
    tasks_list.sort(key=lambda item: item["task_id"])
    return {"tasks": tasks_list}


def _summarize_routines(entries: Iterable[Mapping[str, object]]) -> dict[str, object]:
    routines: dict[str, MutableMapping[str, object]] = {}
    conflicts: set[str] = set()
    for entry in entries:
        routine_id = entry.get("routine_id")
        if not isinstance(routine_id, str) or not routine_id:
            continue
        state = routines.setdefault(routine_id, {
            "routine_id": routine_id,
            "executions": 0,
            "failed": 0,
            "scope_violations": 0,
            "log_ids": set(),
        })
        log_id = entry.get("rolling_hash") or entry.get("prev_hash")
        if log_id:
            state["log_ids"].add(str(log_id))
        event = entry.get("event")
        if event == "delegated_execution":
            state["executions"] += 1
            if entry.get("outcome") == "failed":
                state["failed"] += 1
            if entry.get("scope_adherence") is False:
                state["scope_violations"] += 1
        if event == "routine_evaluation":
            outcome = entry.get("outcome")
            if outcome in {"conflict_paused", "conflict_suppressed"}:
                conflicts.add(routine_id)
    routines_list = []
    for routine_id, details in routines.items():
        routines_list.append({
            "routine_id": routine_id,
            "executions": details.get("executions"),
            "failed": details.get("failed"),
            "scope_violations": details.get("scope_violations"),
            "log_ids": sorted(details.get("log_ids", set())),
            "conflict_paused": routine_id in conflicts,
        })
    routines_list.sort(key=lambda item: item["routine_id"])
    return {"routines": routines_list, "conflicts": sorted(conflicts)}


def _summarize_admissions(entries: Iterable[Mapping[str, object]]) -> dict[str, object]:
    denials: list[dict[str, object]] = []
    for entry in entries:
        if entry.get("event") != "TASK_ADMISSION_DENIED":
            continue
        reason = entry.get("reason")
        denials.append({
            "task_id": entry.get("task_id"),
            "reason": reason,
            "category": _category_from_admission_reason(reason),
            "log_id": entry.get("rolling_hash") or entry.get("prev_hash"),
        })
    return {"denials": denials}


def _category_from_admission_reason(reason: object) -> str:
    if reason == "DENIED_PRIVILEGE_SCOPE":
        return "missing_approval"
    if reason in {
        "DENIED_STEP_KIND",
        "MESH_DISABLED",
        "SHELL_DENIED_IN_AUTONOMOUS",
        "TOO_MANY_STEPS",
        "TOO_MANY_SHELL_STEPS",
        "TOO_MANY_PYTHON_STEPS",
    }:
        return "scope_violations"
    return "unmet_prerequisites"


def _build_authority_section(authority: Mapping[str, object], title: str = "Authority Summary") -> dict[str, object]:
    changes = authority.get("changes", [])
    summary = authority.get("summary", {}) if isinstance(authority.get("summary"), Mapping) else {}
    counts = _count_change_types(changes)
    lines: list[str] = []
    if summary.get("total", 0) == 0:
        lines.append("No authority surface changes recorded.")
    else:
        authority_count = int(summary.get("authority", 0))
        semantic_only = int(summary.get("semantic_only", 0))
        if authority_count == 0:
            lines.append(
                f"{semantic_only} semantic-only change(s) recorded; no authority changes detected."
            )
        else:
            lines.append(
                f"{authority_count} authority-impacting change(s) and {semantic_only} semantic-only change(s) recorded."
            )
        lines.append(
            "Additions: {add}, removals: {remove}, expansions: {expand}, narrows: {narrow}, modifications: {modify}.".format(
                **counts
            )
        )
    references = {
        "authority_diff_hashes": authority.get("diff_hashes", []),
        "authority_log_entry_ids": authority.get("log_entry_ids", []),
        "authority_entity_ids": _extract_entity_ids(changes),
    }
    return {"title": title, "lines": lines, "references": references}


def _build_activity_section(activity: Mapping[str, object], title: str = "System Summary") -> dict[str, object]:
    tasks = activity.get("tasks", {}).get("tasks", [])
    routines = activity.get("routines", {}).get("routines", [])
    admissions = activity.get("admissions", {}).get("denials", [])
    forgetting = activity.get("forgetting", {})
    task_count = len(tasks)
    routine_execs = sum(int(item.get("executions", 0)) for item in routines)
    completed = sum(1 for item in tasks if item.get("status") == "completed")
    failed = sum(1 for item in tasks if item.get("status") == "failed")
    blocked = sum(1 for item in tasks if item.get("blocked"))
    running = task_count - completed - failed - blocked
    routines_failed = sum(int(item.get("failed", 0)) for item in routines)
    scope_violations = sum(int(item.get("scope_violations", 0)) for item in routines)
    adapters = sorted({adapter for item in tasks for adapter in item.get("adapters", []) if adapter})
    epr_actions = sorted({action for item in tasks for action in item.get("epr_actions", []) if action})
    reversibility = sorted({value for item in tasks for value in item.get("reversibility", []) if value})
    lines: list[str] = []
    if task_count == 0 and routine_execs == 0:
        lines.append("No tasks or delegated routines executed in this window.")
    else:
        lines.append(
            f"{task_count} task(s) executed; {completed} completed, {failed} failed, "
            f"{blocked} blocked, {running} in progress."
        )
        if routine_execs:
            lines.append(
                f"{routine_execs} delegated routine execution(s) recorded; "
                f"{routines_failed} failed, {scope_violations} scope violation(s)."
            )
        if adapters:
            lines.append(f"Adapters used: {', '.join(adapters)}.")
        if epr_actions:
            lines.append(f"EPR actions recorded: {len(epr_actions)} (ids: {', '.join(epr_actions)}).")
        else:
            lines.append("No EPR actions recorded.")
        if reversibility:
            lines.append(f"Reversibility signals: {', '.join(reversibility)}.")
        if admissions:
            lines.append(f"Admissions denied: {len(admissions)}.")
    if forgetting.get("count"):
        lines.append(
            f"{forgetting['count']} item(s) were intentionally forgotten. No residual influence remains."
        )
    if forgetting.get("refusals"):
        summary = f"{forgetting['refusals']} intentional forgetting request(s) were refused"
        if forgetting.get("deferrals"):
            summary += f" ({forgetting['deferrals']} deferred)"
        summary += "."
        lines.append(summary)
    pressure = activity.get("forgetting_pressure", {})
    pressure_count = int(pressure.get("count", 0) or 0)
    if pressure_count:
        scope = pressure.get("scope", [])
        if scope:
            scope_summary = ", ".join(scope)
            lines.append(
                f"{pressure_count} unresolved forgetting pressure signal(s) remain across {scope_summary}."
            )
        else:
            lines.append(f"{pressure_count} unresolved forgetting pressure signal(s) remain.")
    overload_count = int(pressure.get("overload_count", 0) or 0)
    if overload_count:
        domains = pressure.get("overload_domains", [])
        lines.append(f"System under sustained tension across {overload_count} domain(s).")
        if domains:
            summary = ", ".join(
                f"{item.get('subsystem')}({item.get('outstanding')})"
                for item in domains
                if item.get("subsystem")
            )
            lines.append(
                f"Sustained overload conditions persist in {overload_count} domain(s): {summary}."
            )
        else:
            lines.append(f"Sustained overload conditions persist in {overload_count} domain(s).")
    references = {
        "task_ids": [item.get("task_id") for item in tasks if item.get("task_id")],
        "routine_ids": [item.get("routine_id") for item in routines if item.get("routine_id")],
        "adapter_ids": adapters,
        "epr_action_ids": epr_actions,
        "task_log_entry_ids": _extract_log_ids(activity.get("task_entries", [])),
        "routine_log_entry_ids": _extract_log_ids(activity.get("routine_entries", [])),
        "admission_log_entry_ids": _extract_log_ids(activity.get("admission_entries", [])),
        "forget_log_entry_ids": _extract_log_ids(activity.get("forgetting_entries", [])),
    }
    return {"title": title, "lines": lines, "references": references}


def _summarize_forgetting(entries: Iterable[Mapping[str, object]]) -> dict[str, object]:
    counts: dict[str, int] = {}
    total = 0
    refusals = 0
    deferrals = 0
    for entry in entries:
        if entry.get("event") != "intentional_forget":
            if entry.get("event") == "intentional_forget_refusal":
                refusals += 1
                for preview in entry.get("previews", []) or []:
                    if preview.get("decision") == "defer":
                        deferrals += 1
            continue
        target_type = entry.get("target_type") or "unknown"
        counts[str(target_type)] = counts.get(str(target_type), 0) + 1
        total += 1
    return {"count": total, "by_type": counts, "refusals": refusals, "deferrals": deferrals}


def _summarize_forget_pressure(
    entries: Iterable[Mapping[str, object]],
    budget_status: Iterable[Mapping[str, object]] = (),
) -> dict[str, object]:
    counts: dict[str, int] = {}
    total = 0
    for entry in entries:
        target_type = entry.get("target_type") or "unknown"
        counts[str(target_type)] = counts.get(str(target_type), 0) + 1
        total += 1
    overload_domains = []
    for item in budget_status:
        if item.get("status") != "exceeded":
            continue
        overload_domains.append({
            "subsystem": item.get("subsystem"),
            "outstanding": item.get("outstanding"),
        })
    overload_domains.sort(key=lambda item: str(item.get("subsystem", "")))
    return {
        "count": total,
        "scope": sorted(counts),
        "overload_count": len(overload_domains),
        "overload_domains": overload_domains,
    }


def _build_idle_section(activity: Mapping[str, object]) -> dict[str, object]:
    tasks = activity.get("tasks", {}).get("tasks", [])
    routines = activity.get("routines", {}).get("routines", [])
    routine_execs = sum(int(item.get("executions", 0)) for item in routines)
    if not tasks and routine_execs == 0:
        lines = ["No actions were taken because no tasks or delegated routines were active."]
    else:
        lines = ["Actions were recorded; no idle window applied in this summary."]
    return {"title": "Why Nothing Happened", "lines": lines, "references": {}}


def _build_boundary_section(activity: Mapping[str, object]) -> dict[str, object]:
    tasks = activity.get("tasks", {}).get("tasks", [])
    routines = activity.get("routines", {}).get("routines", [])
    admissions = activity.get("admissions", {}).get("denials", [])
    boundary_counts: dict[str, int] = {"missing_approval": 0, "unmet_prerequisites": 0, "scope_violations": 0}
    for task in tasks:
        block_type = task.get("block_type")
        if block_type in boundary_counts:
            boundary_counts[block_type] += 1
    for routine in routines:
        scope_violations = int(routine.get("scope_violations", 0) or 0)
        boundary_counts["scope_violations"] += scope_violations
    for denial in admissions:
        category = denial.get("category")
        if category in boundary_counts:
            boundary_counts[category] += 1
    total_boundaries = sum(boundary_counts.values())
    lines: list[str] = []
    if total_boundaries == 0:
        lines.append("No boundary interactions recorded. No boundary was crossed.")
    else:
        lines.append(
            "Blocked actions: {missing} missing approvals, {scope} scope violations, "
            "{unmet} unmet prerequisites.".format(
                missing=boundary_counts["missing_approval"],
                scope=boundary_counts["scope_violations"],
                unmet=boundary_counts["unmet_prerequisites"],
            )
        )
        lines.append("No boundary was crossed.")
    references = {
        "blocked_task_ids": [item.get("task_id") for item in tasks if item.get("blocked")],
        "blocked_routine_ids": [
            item.get("routine_id") for item in routines if int(item.get("scope_violations", 0) or 0) > 0
        ],
        "blocked_log_entry_ids": [
            log_id
            for item in tasks
            for log_id in item.get("log_ids", [])
            if item.get("blocked")
        ],
    }
    return {"title": "Risk & Boundary Report", "lines": lines, "references": references}


def _count_change_types(changes: Iterable[Mapping[str, object]]) -> dict[str, int]:
    counts = {"add": 0, "remove": 0, "expand": 0, "narrow": 0, "modify": 0}
    for change in changes:
        change_type = change.get("change_type")
        if change_type in counts:
            counts[change_type] += 1
    return counts


def _extract_entity_ids(changes: Iterable[Mapping[str, object]]) -> list[str]:
    ids: set[str] = set()
    for change in changes:
        description = change.get("description")
        if not isinstance(description, str):
            continue
        for match in re.findall(r"'([^']+)'", description):
            if match:
                ids.add(match)
    return sorted(ids)


def _extract_log_ids(entries: Iterable[Mapping[str, object]]) -> list[str]:
    ids = {str(entry.get("rolling_hash")) for entry in entries if entry.get("rolling_hash")}
    return sorted(ids)
