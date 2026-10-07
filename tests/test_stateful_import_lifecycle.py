from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_inertness_verifier_covers_stateful_import_roots(tmp_path: Path) -> None:
    import json as json_module
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "inertness.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "verify_import_inertness.py"),
            "--module-root", str(root), "--output", str(output),
            *[item for module in (
                "integration_memory", "codex", "codex.integrity_daemon", "codex.strategy",
                "memory_manager", "curiosity_goal_helper", "curiosity_executor",
                "sentient_autonomy", "sentientos.autonomy.curiosity_loop",
                "sentientos.autonomy.runtime",
            ) for item in ("--module", module)],
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    result = json_module.loads(output.read_text(encoding="utf-8"))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert result["status"] == "import_inertness_ready"


def test_integration_memory_construction_and_reconfigure_do_not_create_custody(tmp_path: Path) -> None:
    from integration_memory import IntegrationMemory

    root = tmp_path / "absent"
    memory = IntegrationMemory(root)
    assert memory.root == root
    assert not root.exists()
    memory.reconfigure(root)
    assert not root.exists()


def test_integration_memory_reads_existing_custody_and_creates_on_write(tmp_path: Path) -> None:
    from integration_memory import IntegrationEntry, IntegrationMemory

    root = tmp_path / "existing"
    root.mkdir()
    entry = IntegrationEntry("entry-1", "2026-01-01T00:00:00+00:00", "source", "event", "baseline", .8)
    (root / "ledger.jsonl").write_text(json.dumps(entry.to_dict()) + "\n", encoding="utf-8")
    memory = IntegrationMemory(root)
    assert memory.state_vector("source")["total_events"] == 1
    assert len(memory.load_events(None)) == 1

    second_root = tmp_path / "second"
    second_root.mkdir()
    (second_root / "ledger.jsonl").write_text(json.dumps({**entry.to_dict(), "id": "entry-2"}) + "\n", encoding="utf-8")
    memory.reconfigure(second_root)
    assert [item.id for item in memory.load_events(None)] == ["entry-2"]

    fresh = IntegrationMemory(tmp_path / "fresh")
    fresh.record_event("created", source="source", impact="baseline")
    assert (tmp_path / "fresh" / "ledger.jsonl").exists()
    assert (tmp_path / "fresh" / "state_vectors.json").exists()


def test_strategy_engine_construction_is_inert_and_use_creates_storage(tmp_path: Path) -> None:
    from integration_memory import configure_integration_root
    from codex.strategy import StrategyAdjustmentEngine

    configure_integration_root(tmp_path / "integration")
    root = tmp_path / "strategy"
    engine = StrategyAdjustmentEngine(root)
    assert not root.exists()
    assert engine.weights_dict()
    assert not root.exists()
    engine.record_outcome(
        plan_id="plan", plan_goal="goal", step_index=0, step_title="step",
        step_action="inspect", step_kind="read", status="success", operator_action="approve",
    )
    assert (root / "outcomes" / "plan.jsonl").exists()
    assert (root / "strategy_state.json").exists()


def test_strategy_engine_hydrates_existing_state_and_reconfiguration(tmp_path: Path) -> None:
    from codex.strategy import StrategyAdjustmentEngine

    first = tmp_path / "first"
    first.mkdir()
    (first / "strategy_state.json").write_text(
        json.dumps({"version": 7, "locked": True, "weights": {"severity": .5, "frequency": .2, "impact": .2, "confidence": .1}}),
        encoding="utf-8",
    )
    second = tmp_path / "second"
    second.mkdir()
    (second / "strategy_state.json").write_text(
        json.dumps({"version": 11, "locked": False}), encoding="utf-8"
    )
    engine = StrategyAdjustmentEngine(first)
    assert engine.strategy_version == 7
    assert engine.locked is True
    engine.reconfigure(second)
    assert engine.strategy_version == 11
    assert engine.locked is False


def test_codex_public_exports_are_lazy_and_identity_compatible() -> None:
    import codex
    from codex import IntegrityDaemon, StrategyAdjustmentEngine, strategy_engine
    from codex.integrity_daemon import IntegrityDaemon as IntegrityDaemonModule
    from codex.strategy import StrategyAdjustmentEngine as StrategyAdjustmentEngineModule

    assert IntegrityDaemon is IntegrityDaemonModule
    assert StrategyAdjustmentEngine is StrategyAdjustmentEngineModule
    assert strategy_engine is codex.strategy_engine
    assert "strategy_engine" in codex.__all__


@pytest.mark.parametrize(
    "write",
    ["raw", "index", "tomb", "observation", "jsonl", "topic", "session", "turn", "goals"],
)
def test_legacy_memory_mutations_authorize_before_filesystem_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write: str
) -> None:
    import memory_manager as memory

    calls: list[str] = []
    monkeypatch.delenv("LUMOS_AUTO_APPROVE", raising=False)
    monkeypatch.delenv("SENTIENTOS_HEADLESS", raising=False)
    monkeypatch.setattr(memory, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(memory, "require_lumos_approval", lambda: calls.append("lumos"))
    base = tmp_path / "memory"
    monkeypatch.setattr(memory, "MEMORY_DIR", base)
    monkeypatch.setattr(memory, "RAW_PATH", base / "raw")
    monkeypatch.setattr(memory, "VECTOR_INDEX_PATH", base / "vector.idx")
    monkeypatch.setattr(memory, "TOMB_PATH", base / "memory_tomb.jsonl")
    monkeypatch.setattr(memory, "OBSERVATION_LOG_PATH", base / "observations.jsonl")
    monkeypatch.setattr(memory, "CURIOSITY_REFLECTIONS_PATH", base / "reflections.jsonl")
    monkeypatch.setattr(memory, "TOPIC_PATH", base / "topics")
    monkeypatch.setattr(memory, "SESSION_PATH", base / "sessions")
    monkeypatch.setattr(memory, "TURN_PATH", base / "turns")
    monkeypatch.setattr(memory, "GOALS_PATH", base / "goals.json")
    monkeypatch.setattr(memory, "_HEADLESS_APPROVAL_REPORTED", True)

    if write == "raw":
        operation = lambda: memory._write_fragment("fragment", {"id": "fragment"})
    elif write == "index":
        operation = lambda: memory._save_index_records([])
    elif write == "tomb":
        operation = lambda: memory._append_tomb({"fragment": {}})
    elif write == "observation":
        operation = lambda: memory._write_observation_record({"id": "observation"})
    elif write == "jsonl":
        operation = lambda: memory._append_jsonl(base / "other.jsonl", {"id": "item"})
    elif write == "topic":
        operation = lambda: memory._write_topic_summaries([{"tags": ["topic"], "text": "value"}])
    elif write == "session":
        operation = lambda: memory._write_session_digest("session", [{"text": "value"}])
    elif write == "turn":
        operation = lambda: memory._write_turn_summaries([{"meta": {"session": "session"}, "text": "value"}])
    else:
        operation = lambda: memory._save_goals([])

    original_mkdir = Path.mkdir
    def guarded_mkdir(path: Path, *args, **kwargs):
        assert calls[-2:] == ["admin", "lumos"]
        return original_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)
    operation()
    assert len(calls) >= 2 and len(calls) % 2 == 0
    assert all(calls[index : index + 2] == ["admin", "lumos"] for index in range(0, len(calls), 2))


@pytest.mark.parametrize("mode", ["headless", "auto_approve"])
def test_legacy_memory_denial_prevents_write_and_headless_skips_lumos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    import memory_manager as memory

    target = tmp_path / "denied" / "fragment.json"
    monkeypatch.setattr(memory, "RAW_PATH", target.parent)
    monkeypatch.setattr(memory, "require_admin_banner", lambda: (_ for _ in ()).throw(PermissionError("denied")))
    with pytest.raises(PermissionError):
        memory._write_fragment("fragment", {})
    assert not target.exists()

    calls: list[str] = []
    monkeypatch.setattr(memory, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(memory, "require_lumos_approval", lambda: calls.append("lumos"))
    if mode == "headless":
        monkeypatch.setenv("SENTIENTOS_HEADLESS", "1")
    else:
        monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    monkeypatch.setattr(memory, "_HEADLESS_APPROVAL_REPORTED", True)
    memory._prepare_write(tmp_path / "headless" / "x")
    assert calls == ["admin"]


def test_one_legacy_memory_operation_authorizes_once_across_private_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import memory_manager as memory

    calls: list[str] = []
    monkeypatch.delenv("LUMOS_AUTO_APPROVE", raising=False)
    monkeypatch.delenv("SENTIENTOS_HEADLESS", raising=False)
    monkeypatch.setattr(memory, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(memory, "require_lumos_approval", lambda: calls.append("lumos"))
    monkeypatch.setattr(memory, "RAW_PATH", tmp_path / "raw")
    monkeypatch.setattr(memory, "VECTOR_INDEX_PATH", tmp_path / "vector.idx")
    monkeypatch.setattr(memory, "USE_EMBEDDINGS", False)
    monkeypatch.setattr(memory, "_HEADLESS_APPROVAL_REPORTED", True)

    memory.append_memory("one logical write")
    assert calls == ["admin", "lumos"]

    calls.clear()
    memory.append_memory("a separate logical write")
    assert calls == ["admin", "lumos"]


def test_legacy_memory_reads_existing_raw_fragments_and_missing_custody(tmp_path: Path, monkeypatch) -> None:
    import memory_manager as memory

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "entry.json").write_text(json.dumps({"id": "entry", "text": "kept"}), encoding="utf-8")
    monkeypatch.setattr(memory, "RAW_PATH", raw)
    assert memory._load_fragment("entry")["text"] == "kept"
    assert memory._load_fragment("missing") is None
    assert memory.list_tomb() == []


def test_legacy_reflection_authorizes_before_first_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    import memory_manager as memory

    calls: list[str] = []
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "")
    monkeypatch.setenv("SENTIENTOS_HEADLESS", "")
    monkeypatch.setattr(memory, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(memory, "require_lumos_approval", lambda: calls.append("lumos"))
    monkeypatch.setattr(memory, "CURIOSITY_REFLECTIONS_PATH", tmp_path / "reflections.jsonl")
    monkeypatch.setattr(memory, "RAW_PATH", tmp_path / "raw")
    monkeypatch.setattr(memory, "VECTOR_INDEX_PATH", tmp_path / "vector.idx")
    original_open = builtins.open
    def guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+"):
            assert calls[-2:] == ["admin", "lumos"]
        return original_open(file, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", guarded_open)

    memory.store_reflection({"insight_summary": "observed pattern"})
    assert (tmp_path / "reflections.jsonl").exists()
    assert calls[0:2] == ["admin", "lumos"]


def test_legacy_tomb_purge_authorizes_unlink_separately(tmp_path: Path, monkeypatch) -> None:
    import memory_manager as memory

    raw = tmp_path / "raw"
    raw.mkdir()
    fragment = raw / "old.json"
    fragment.write_text(json.dumps({"id": "old", "timestamp": "2000-01-01T00:00:00"}), encoding="utf-8")
    monkeypatch.setattr(memory, "RAW_PATH", raw)
    monkeypatch.setattr(memory, "TOMB_PATH", tmp_path / "tomb.jsonl")
    monkeypatch.setattr(memory, "VECTOR_INDEX_PATH", tmp_path / "vector.idx")
    events: list[str] = []
    monkeypatch.setattr(memory, "require_admin_banner", lambda: events.append("admin"))
    monkeypatch.setattr(memory, "require_lumos_approval", lambda: events.append("lumos"))
    original_unlink = Path.unlink

    def observe_unlink(path: Path, *args, **kwargs):
        if path == fragment:
            events.append("unlink")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", observe_unlink)
    memory.purge_memory(max_files=0)
    assert events == ["admin", "lumos", "unlink"]
    assert not fragment.exists()
    assert (tmp_path / "tomb.jsonl").exists()


def test_legacy_glow_storage_authorizes_before_digest_effect(tmp_path: Path, monkeypatch) -> None:
    import memory_manager as memory

    calls: list[str] = []
    monkeypatch.setattr(memory, "SCREEN_DIGEST_PATH", tmp_path / "screen.jsonl")
    monkeypatch.setattr(memory, "DIGEST_DIR", tmp_path / "digests")
    monkeypatch.setattr(memory, "HIGHLIGHT_DIR", tmp_path / "highlights")
    monkeypatch.setattr(memory, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(memory, "require_lumos_approval", lambda: calls.append("lumos"))
    import builtins

    original_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if Path(file) == tmp_path / "screen.jsonl" and any(flag in mode for flag in "wax+"):
            assert calls[-2:] == ["admin", "lumos"]
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    memory.store_observation({"modality": "screen", "text": "digest text"})
    assert calls == ["admin", "lumos"]
    assert (tmp_path / "screen.jsonl").exists()


def test_node_registry_default_binds_without_materializing_data_root(tmp_path: Path, monkeypatch) -> None:
    from node_registry import NodeRegistry

    root = tmp_path / "data"
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(root))
    registry = NodeRegistry.default(load=False)
    assert registry._path == root / "nodes" / "nodes.json"
    assert not root.exists()
