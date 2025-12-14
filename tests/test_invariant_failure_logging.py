import json
import logging
from importlib import reload

import pytest

import policy_engine as pe
import prompt_assembler as pa
import sentient_autonomy as sa
import sentient_mesh as sm


def _parse_payload(record):
    return json.loads(record.message)


def test_prompt_assembler_logs_deterministically(monkeypatch, caplog):
    reload(pa)
    monkeypatch.setattr(pa.up, "format_profile", lambda: "")
    monkeypatch.setattr(pa.em, "average_emotion", lambda: {})
    monkeypatch.setattr(pa.cw, "get_context", lambda: ([], ""))
    monkeypatch.setattr(pa.actuator, "recent_logs", lambda *args, **kwargs: [])
    monkeypatch.setattr(pa.mm, "get_context", lambda _query, k=6: [{"plan": "alpha", "trust": 0.9}])

    caplog.set_level(logging.ERROR, logger="sentientos.invariant")
    with pytest.raises(AssertionError):
        pa.assemble_prompt("execute", [])
    payload_one = _parse_payload(caplog.records[-1])
    caplog.clear()
    with pytest.raises(AssertionError):
        pa.assemble_prompt("execute", [])
    payload_two = _parse_payload(caplog.records[-1])

    expected_hash = pa._compute_input_hash(["alpha"], payload_one["details"]["prompt"])
    assert payload_one == payload_two
    assert payload_one["event"] == "invariant_violation"
    assert payload_one["input_hash"] == expected_hash


def test_sentient_autonomy_logs_priority_violation(caplog, monkeypatch):
    reload(sa)
    monkeypatch.setattr(sa.memory_governor, "mesh_metrics", lambda: {"open_goals": ["alpha"]})
    engine = sa.SentientAutonomyEngine(mesh=object())
    engine.start()

    caplog.set_level(logging.ERROR, logger="sentientos.invariant")
    with pytest.raises(RuntimeError, match="AUTONOMY_PRIORITY_LOCK"):
        engine.reflective_cycle(limit=1)
    payload_one = _parse_payload(caplog.records[-1])
    caplog.clear()
    with pytest.raises(RuntimeError, match="AUTONOMY_PRIORITY_LOCK"):
        engine.reflective_cycle(limit=1)
    payload_two = _parse_payload(caplog.records[-1])

    expected_hash = sa._compute_input_hash(
        {
            "queue": [],
            "selected": ["alpha"],
            "plans": sa._plan_snapshot({}),
            "metrics": {"open_goals": ["alpha"]},
        }
    )
    assert payload_one == payload_two
    assert payload_one["event"] == "invariant_violation"
    assert payload_one["input_hash"] == expected_hash


def test_sentient_mesh_logs_routing_guard(tmp_path, caplog):
    reload(sm)
    mesh = sm.SentientMesh(transcripts_dir=tmp_path)
    job = sm.MeshJob(job_id="job-1", script={"prompt": "hi"}, metadata={"reward": 1})

    caplog.set_level(logging.ERROR, logger="sentientos.invariant")
    with pytest.raises(RuntimeError, match="NO_GRADIENT_INVARIANT"):
        mesh.cycle([job])
    payload_one = _parse_payload(caplog.records[-1])
    caplog.clear()
    with pytest.raises(RuntimeError, match="NO_GRADIENT_INVARIANT"):
        mesh.cycle([job])
    payload_two = _parse_payload(caplog.records[-1])

    expected_hash = sm._compute_input_hash(
        {"nodes": sm._node_roster_snapshot(mesh._nodes), "job": sm._job_signature(job)}
    )
    assert payload_one == payload_two
    assert payload_one["event"] == "invariant_violation"
    assert payload_one["input_hash"] == expected_hash


def test_policy_engine_event_guard_logging(tmp_path, caplog):
    reload(pe)
    engine = pe.PolicyEngine(str(tmp_path / "policy.json"))
    event = {"event": "test", "reward": 1}

    caplog.set_level(logging.ERROR, logger="sentientos.invariant")
    with pytest.raises(RuntimeError, match="NO_GRADIENT_INVARIANT"):
        engine.evaluate(event)
    payload_one = _parse_payload(caplog.records[-1])
    caplog.clear()
    with pytest.raises(RuntimeError, match="NO_GRADIENT_INVARIANT"):
        engine.evaluate(event)
    payload_two = _parse_payload(caplog.records[-1])

    normalized_event = json.loads(json.dumps(event, sort_keys=True))
    expected_hash = pe._compute_input_hash(normalized_event, [])
    assert payload_one == payload_two
    assert payload_one["event"] == "invariant_violation"
    assert payload_one["input_hash"] == expected_hash

