import importlib
import json

import logging
from types import ModuleType


def _reload(module_name: str) -> ModuleType:
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def _run_autonomy_cycle(monkeypatch):
    sentient_autonomy = _reload("sentient_autonomy")
    sentient_mesh = _reload("sentient_mesh")
    memory_governor = _reload("memory_governor")

    monkeypatch.setattr(
        memory_governor,
        "mesh_metrics",
        lambda: {
            "nodes": 2,
            "trust_histogram": {"0": 2},
            "active_council_sessions": 0,
            "emotion_consensus": {"calm": 0.25},
        },
    )

    class StaticMesh:
        def cycle(self, jobs):  # pragma: no cover - deterministic stub
            assignments = {job.job_id: "node-alpha" for job in jobs}
            return sentient_mesh.MeshSnapshot(
                timestamp=0.0,
                assignments=assignments,
                trust_vector={"node-alpha": 1.0},
                emotion_matrix={},
                council_sessions={jid: [] for jid in assignments},
                jobs=[job.describe() for job in jobs],
            )

    engine = sentient_autonomy.SentientAutonomyEngine(StaticMesh(), allow_fallback_goals=False)
    engine.start()
    engine.queue_goal("alpha", priority=2)
    engine.queue_goal("beta", priority=1)
    return engine.reflective_cycle(force=True, limit=3)


def _stub_voice(sentient_mesh):
    def _exchange(role: str, content: str):
        return sentient_mesh.VoiceExchange(
            voice="orion",
            role=role,
            content=content,
            signature=f"sig-{role}",
            advisory=False,
            timestamp=0.0,
            metadata={},
        )

    class StubVoice:
        name = "orion"
        advisory = False
        config = {"name": name, "advisory": advisory}

        @property
        def available(self):
            return True

        def identity(self):
            return self.name

        def ask(self, prompt: str, *, trust: float = 1.0):
            return _exchange("ask", f"ask:{prompt}:{trust}")

        def critique(self, statement: str, *, trust: float = 1.0):
            return _exchange("critique", f"critique:{statement}:{trust}")

        def vote(self, transcript, *, trust: float = 1.0):
            payload = json.dumps({"decision": "approve", "confidence": 0.6})
            return _exchange("vote", payload)

    return StubVoice()


def _run_mesh_cycle(monkeypatch, tmp_path):
    sentient_mesh = _reload("sentient_mesh")
    mesh = sentient_mesh.SentientMesh(transcripts_dir=tmp_path / "sessions")
    mesh.register_voice(_stub_voice(sentient_mesh))
    mesh.update_node("node-a", trust=0.5, load=0.1, capabilities=["sentient_script"])
    mesh.update_node("node-b", trust=0.4, load=0.0, capabilities=["sentient_script"])

    job = sentient_mesh.MeshJob(
        job_id="job-01",
        script={"prompt": "stabilise"},
        prompt="stabilise",
        priority=1,
        requirements=("sentient_script",),
        metadata={},
    )
    snapshot = mesh.cycle([job])
    return {
        "assignments": snapshot.assignments,
        "trust_vector": snapshot.trust_vector,
        "jobs": snapshot.jobs,
        "sessions": snapshot.council_sessions,
    }


def _assemble_prompt(monkeypatch):
    prompt_assembler = _reload("prompt_assembler")
    context_window = _reload("context_window")
    memory_manager = _reload("memory_manager")
    user_profile = _reload("user_profile")
    emotion_memory = _reload("emotion_memory")
    actuator = _reload("api.actuator")

    monkeypatch.setattr(user_profile, "format_profile", lambda: "name: lumos")
    monkeypatch.setattr(memory_manager, "get_context", lambda _text, k=6: [{"plan": "alpha"}, "note"], raising=False)
    monkeypatch.setattr(emotion_memory, "average_emotion", lambda: {"calm": 0.2, "focus": 0.1})
    monkeypatch.setattr(context_window, "get_context", lambda: (["msg-a", "msg-b"], "summary"), raising=False)
    monkeypatch.setattr(actuator, "recent_logs", lambda _n, reflect=False: [{"reflection_text": "steady"}])

    return prompt_assembler.assemble_prompt("execute task", recent_messages=["hi"], k=2)


def _invariant_log(monkeypatch, tmp_path, caplog):
    caplog.clear()
    sentient_mesh = _reload("sentient_mesh")
    mesh = sentient_mesh.SentientMesh(transcripts_dir=tmp_path / "sessions")
    mesh.update_node("node-a", trust=1.0, load=0.0, capabilities=["sentient_script"])
    job = sentient_mesh.MeshJob(job_id="job-invariant", script={"prompt": "x"}, metadata={"reward": 1})

    with caplog.at_level(logging.ERROR, logger="sentientos.invariant"):
        try:
            mesh.cycle([job])
        except RuntimeError:
            pass
    return [rec.message for rec in caplog.records if rec.name == "sentientos.invariant"]


def test_autonomy_restart_equivalence(monkeypatch):
    first = _run_autonomy_cycle(monkeypatch)
    second = _run_autonomy_cycle(monkeypatch)
    assert first == second


def test_mesh_restart_equivalence(monkeypatch, tmp_path):
    first = _run_mesh_cycle(monkeypatch, tmp_path)
    second = _run_mesh_cycle(monkeypatch, tmp_path)
    assert first == second


def test_prompt_restart_equivalence(monkeypatch):
    first = _assemble_prompt(monkeypatch)
    second = _assemble_prompt(monkeypatch)
    assert first == second


def test_invariant_logs_restart_equivalence(monkeypatch, tmp_path, caplog):
    first = _invariant_log(monkeypatch, tmp_path, caplog)
    second = _invariant_log(monkeypatch, tmp_path, caplog)
    assert first == second
