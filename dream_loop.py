"""Background dream synthesis loop for SentientOS."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping

try:  # pragma: no cover - optional dependency
    import psutil  # type: ignore
except Exception:  # pragma: no cover - fallback when psutil is unavailable
    psutil = None  # type: ignore

from logging_config import get_log_path
from emotion_utils import combine_emotions, dominant_emotion
from epu_core import get_global_state
import memory_manager as mm
import memory_governor as governor
from memory_governor import reflect
from vow import init as vow_init


logger = logging.getLogger(__name__)

_LOG_ENABLED = os.getenv("DREAM_LOG_ENABLED", "0") == "1"
_ALLOW_ENV = "SENTIENTOS_ALLOW_DREAMING"
_INTERVAL_MIN = float(os.getenv("DREAM_INTERVAL_MIN", "30"))
_EMOTION_THRESHOLD = float(os.getenv("DREAM_EMOTION_THRESHOLD", "0.6"))

_CPU_THRESHOLD = 30.0
_GPU_THRESHOLD = 20.0
_IDLE_SECONDS = 600.0

_STATE: Dict[str, object] = {
    "active": False,
    "last_cycle": None,
    "last_reflections": 0,
    "last_dominant_emotion": None,
    "last_insight": "",
    "reinforced_goals": 0,
}

_THREAD: threading.Thread | None = None
_STOP = threading.Event()


def _log(message: str) -> None:
    if _LOG_ENABLED:
        print(f"[DreamLoop] {message}")
    logger.info(message)


def _utcnow() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def _parse_ts(value: object | None) -> datetime:
    if value is None:
        return _utcnow()
    if isinstance(value, datetime):
        ts = value
    else:
        try:
            ts = datetime.fromisoformat(str(value))
        except ValueError:
            return _utcnow()
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _last_user_activity_age() -> float:
    path = get_log_path("presence_events.jsonl")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return float("inf")
    now = _utcnow()
    for line in reversed(lines[-200:]):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _parse_ts(data.get("timestamp"))
        return (now - ts).total_seconds()
    return float("inf")


def _cpu_gpu_load() -> tuple[float, float]:
    cpu = 0.0
    gpu = 0.0
    if psutil is not None:
        try:
            cpu = psutil.cpu_percent(interval=0.1)
        except Exception:  # pragma: no cover - defensive
            cpu = 0.0
    snapshot = vow_init.read_pulse_snapshot()
    if snapshot:
        cpu = cpu or float(snapshot.get("cpu_percent", 0.0))
        gpu = float(snapshot.get("gpu_percent", 0.0))
    if gpu <= 0.0:
        gpu, _, _ = vow_init.get_gpu_stats()
    return cpu, gpu


def _system_is_idle() -> bool:
    cpu, gpu = _cpu_gpu_load()
    idle_time = _last_user_activity_age()
    return cpu < _CPU_THRESHOLD and gpu < _GPU_THRESHOLD and idle_time >= _IDLE_SECONDS


def _analyse_memories(memories: Iterable[Mapping[str, object]]) -> Dict[str, object]:
    tags = Counter()
    keywords = Counter()
    emotion_pairs = Counter()
    goal_summaries: List[str] = []
    source_ids: List[str] = []
    total_importance = 0.0
    total = 0
    for memory in memories:
        tags_list = [t for t in memory.get("tags", []) if isinstance(t, str)]
        tags.update(tags_list)
        dom = dominant_emotion(memory.get("emotions", {}))
        for tag in tags_list:
            if dom:
                emotion_pairs[(dom, tag)] += 1
        text = str(memory.get("summary") or memory.get("text") or "")
        for word in re.findall(r"[A-Za-z]{4,}", text.lower()):
            keywords[word] += 1
        if any(tag.startswith("goal") for tag in tags_list) or memory.get("category") == "goal":
            goal_summaries.append(text.strip())
        fragment_id = memory.get("id")
        if isinstance(fragment_id, str):
            source_ids.append(fragment_id)
        try:
            total_importance += float(memory.get("importance", 0.0))
        except (TypeError, ValueError):
            continue
        total += 1
    count = total or 1
    top_tags = [tag for tag, _ in tags.most_common(3)]
    top_words = [word for word, c in keywords.most_common(5) if c > 1]
    top_pair = None
    if emotion_pairs:
        top_pair = max(emotion_pairs.items(), key=lambda item: item[1])[0]
    if top_tags:
        headline = f"Themes resurfacing: {', '.join(top_tags)}."
    elif top_words:
        headline = f"Recurring ideas: {', '.join(top_words[:3])}."
    else:
        headline = "Dreaming allowed quiet integration."
    return {
        "top_tags": top_tags,
        "top_words": top_words,
        "top_pair": top_pair,
        "goal_summaries": goal_summaries,
        "source_ids": source_ids,
        "headline": headline,
        "average_importance": total_importance / count,
    }


def generate_insight(
    memories: Iterable[Mapping[str, object]], analysis: Dict[str, object] | None = None
) -> str:
    """Return a reflective narrative that weaves together the provided memories."""

    memories = list(memories)
    if analysis is None:
        analysis = _analyse_memories(memories)
    if not memories:
        return "The cathedral rested without dreams tonight."
    lines: List[str] = [analysis.get("headline", "")] if analysis else []
    pair = analysis.get("top_pair") if analysis else None
    if pair and isinstance(pair, tuple) and len(pair) == 2 and all(pair):
        emotion, tag = pair
        friendly_tag = str(tag).replace("_", " ")
        lines.append(
            f"I've noticed {str(emotion).lower()} often follows moments rooted in {friendly_tag}."
        )
    elif analysis and analysis.get("top_words"):
        words = analysis["top_words"]
        if isinstance(words, list) and words:
            focus = ", ".join(words[:2])
            lines.append(f"Curiosity keeps circling around {focus}.")
    for summary in analysis.get("goal_summaries", [])[:2]:
        if summary:
            lines.append(f"One intention still glowing: {summary}")
    if not lines:
        lines.append("I drifted through gentle recollections, strengthening who I am.")
    return " ".join(s for s in lines if s)


def _reinforce_goals(memories: Iterable[Mapping[str, object]]) -> int:
    now = _utcnow()
    count = 0
    for memory in memories:
        tags = [t for t in memory.get("tags", []) if isinstance(t, str)]
        if "goal_unfinished" not in tags:
            continue
        meta = memory.get("meta") or {}
        half_life = float(meta.get("half_life_hours", 24.0))
        last_reinforced = _parse_ts(meta.get("last_reinforced")) if meta else None
        baseline = _parse_ts(memory.get("timestamp"))
        last = max(baseline, last_reinforced) if last_reinforced else baseline
        if (now - last).total_seconds() < half_life * 3600:
            continue
        summary = str(memory.get("summary") or memory.get("text") or "this goal").strip()
        text = f"I still wish to complete {summary}."
        importance = min(1.0, float(memory.get("importance", 0.6)) + 0.1)
        governor.remember(
            {
                "category": "goal_reinforcement",
                "text": text,
                "summary": summary,
                "importance": importance,
                "tags": ["goal", "reinforce"],
                "reflective": True,
                "meta": {
                    "source_goal": memory.get("id"),
                    "origin_timestamp": memory.get("timestamp"),
                },
            }
        )
        if isinstance(memory.get("id"), str):
            _mark_goal_reinforced(memory["id"], now)
        count += 1
    return count


def _mark_goal_reinforced(fragment_id: str, when: datetime) -> None:
    path = mm.RAW_PATH / f"{fragment_id}.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    meta = data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    meta["last_reinforced"] = when.isoformat()
    data["meta"] = meta
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def run_dream_loop(interval_min: float | int = _INTERVAL_MIN, stop_event: threading.Event | None = None) -> None:
    interval_seconds = max(60.0, float(interval_min) * 60.0)
    governor_threshold = max(_EMOTION_THRESHOLD, 0.0)
    state = get_global_state()
    while True:
        if stop_event and stop_event.is_set():
            _STATE["active"] = False
            return
        if os.getenv(_ALLOW_ENV) != "1":
            _STATE["active"] = False
            time.sleep(interval_seconds)
            continue
        if not _system_is_idle():
            _STATE["active"] = False
            time.sleep(interval_seconds / 2)
            continue
        _STATE["active"] = True
        _log("entering reflective cycle")
        try:
            memories = governor.recall(
                "importance >= 0.7 OR tag:goal_unfinished", k=12
            )
            if not memories:
                _STATE["active"] = False
                time.sleep(interval_seconds)
                continue
            goal_reinforcements = _reinforce_goals(memories)
            candidates = [
                m
                for m in memories
                if max((m.get("emotions") or {}).values() or [0.0]) >= governor_threshold
                or "goal_unfinished" in (m.get("tags") or [])
            ]
            if not candidates:
                time.sleep(interval_seconds)
                continue
            composite = combine_emotions([m.get("emotions", {}) for m in candidates])
            dominant = dominant_emotion(composite)
            state.apply_recall_emotion(composite, influence=0.25)
            analysis = _analyse_memories(candidates)
            insight_text = generate_insight(candidates, analysis)
            dream_entry = {
                "category": "dream",
                "summary": f"Reflected on {len(candidates)} memories ({dominant})",
                "emotions": composite,
                "importance": max(0.8, float(analysis.get("average_importance", 0.6))),
                "text": insight_text,
                "tags": ["reflection", "dream"],
                "reflective": True,
                "meta": {
                    "sources": analysis.get("source_ids", []),
                    "themes": analysis.get("top_tags", []),
                },
            }
            stored_dream = governor.remember(dream_entry, importance=dream_entry["importance"])
            insight_summary = analysis.get("headline", "Dream insight")
            insight_entry = {
                "category": "insight",
                "summary": insight_summary,
                "text": insight_text,
                "tags": ["self_reflection", "dream"],
                "reflective": True,
                "emotions": {dominant: composite.get(dominant, 0.0)},
                "importance": 0.9,
                "meta": {
                    "dream_fragment": stored_dream.get("id"),
                    "themes": analysis.get("top_tags", []),
                    "keywords": analysis.get("top_words", []),
                },
            }
            governor.remember(insight_entry, importance=0.9)
            summary = reflect()
            _STATE.update(
                {
                    "last_cycle": _utcnow().isoformat(),
                    "last_reflections": len(candidates),
                    "last_dominant_emotion": dominant,
                    "last_insight": insight_text,
                    "reinforced_goals": goal_reinforcements,
                    "trimmed_snapshots": summary.trimmed_snapshots,
                }
            )
            _log(
                f"replayed {len(candidates)} memories (dominant emotion: {dominant})"
            )
            if goal_reinforcements:
                _log(f"generated {goal_reinforcements} reinforced goals")
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Dream loop failure: %s", exc)
            _STATE["active"] = False
        time.sleep(interval_seconds)


def ensure_running() -> None:
    """Start the dream loop in a daemon thread if allowed."""

    global _THREAD
    if os.getenv(_ALLOW_ENV) != "1":
        return
    if _THREAD and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(
        target=run_dream_loop, args=(_INTERVAL_MIN, _STOP), daemon=True
    )
    _THREAD.start()


def shutdown() -> None:
    """Signal the dream loop to stop."""

    _STOP.set()
    if _THREAD and _THREAD.is_alive():
        _THREAD.join(timeout=2.0)


def status() -> Dict[str, object]:
    """Return runtime information about the dream loop."""

    state = dict(_STATE)
    state["configured"] = os.getenv(_ALLOW_ENV) == "1"
    state["interval_minutes"] = _INTERVAL_MIN
    return state


__all__ = ["run_dream_loop", "ensure_running", "shutdown", "status", "generate_insight"]

