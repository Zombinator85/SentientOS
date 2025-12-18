from pathlib import Path

from sentientos.meta.reflection_loop import ReflectionLoop


def test_reflection_loop_generates_summary_and_replan(tmp_path: Path):
    digests = [
        {"delays": True, "blocked": False},
        {"blocked": True},
    ]
    patches = [
        {"module": "sentient.mesh", "reverts": 1, "over_correction": True},
        {"module": "sentient.shell", "under_correction": True},
    ]
    moods = [
        {"valence": "negative", "stability": "volatile"},
        {"valence": "positive", "stability": "steady"},
    ]
    conflicts = [
        {"id": "conf-1", "status": "unresolved"},
        {"id": "conf-2", "status": "resolved"},
    ]

    queued_tasks: list[dict] = []

    def queue_replan(task: dict) -> None:
        queued_tasks.append(task)

    loop = ReflectionLoop(tmp_path, misalignment_threshold=0.2, queue_replan=queue_replan)
    summary = loop.run(
        daily_digests=digests,
        codex_patches=patches,
        mood_history=moods,
        conflict_resolutions=conflicts,
    )

    log_path = tmp_path / "self_reflection_summary.jsonl"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()

    assert summary["planning_inefficiencies"] == ["blocked_tasks", "delayed_deliverables", "rework_detected"]
    assert summary["correction_patterns"]
    assert summary["behavioral_coherence"]["coherence_rating"] < 1
    assert queued_tasks, "misalignment should queue a replan task"

    # Self-reflection event showing trend awareness
    last_entry = lines[-1]
    assert "turbulence" in last_entry
