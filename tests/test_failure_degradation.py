import logging
from pathlib import Path

import pytest

import sentient_autonomy as autonomy_module
import sentient_mesh as mesh_module
from sentient_autonomy import SentientAutonomyEngine
from sentient_mesh import MeshJob, SentientMesh


@pytest.mark.parametrize("mode", ["mesh_node_timeout", "empty_mesh_response_set"])
def test_mesh_failure_injection_preserves_state(monkeypatch, caplog, tmp_path, mode):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])
    mesh.update_node("alpha", trust=1.5, load=0.2, capabilities=["sentient_script"])

    caplog.set_level(logging.INFO, logger="sentientos.degradation")

    def injector(context, payload):
        if context == "sentient_mesh.cycle":
            return {"mode": mode, "detail": payload["job_ids"]}
        return None

    monkeypatch.setattr(mesh_module, "_TEST_FAILURE_INJECTOR", injector)

    before_trust = {node: state.trust for node, state in mesh._nodes.items()}
    before_snapshot = mesh._last_snapshot
    before_broadcast = mesh._last_broadcast
    job = MeshJob(job_id="job-degrade", script={"goal": "stabilise"})

    with pytest.raises(RuntimeError, match=f"DETERMINISTIC_DEGRADATION:{mode}"):
        mesh.cycle([job])
    assert mesh._nodes["alpha"].trust == before_trust["alpha"]
    assert mesh._last_snapshot is before_snapshot
    assert mesh._last_broadcast is before_broadcast

    first_log = caplog.records[0].message
    caplog.clear()

    with pytest.raises(RuntimeError, match=f"DETERMINISTIC_DEGRADATION:{mode}"):
        mesh.cycle([job])
    assert caplog.records[0].message == first_log
    assert mesh._nodes["alpha"].trust == before_trust["alpha"]
    assert mesh._last_broadcast is before_broadcast


@pytest.mark.parametrize("mode", ["policy_engine_rejection", "integrity_daemon_veto"])
def test_autonomy_failure_injection_preserves_plan_order(monkeypatch, caplog, tmp_path, mode):
    mesh = SentientMesh(transcripts_dir=tmp_path, voices=[])
    engine = SentientAutonomyEngine(mesh)
    engine.start()
    engine.queue_goal("stabilise trust")
    engine.queue_goal("synchronise council")

    ledger = Path("CAPABILITY_GROWTH_LEDGER.md")
    ledger_before = ledger.read_bytes()

    caplog.set_level(logging.INFO, logger="sentientos.degradation")

    def injector(context, payload):
        if context == "sentient_autonomy.reflective_cycle":
            return {"mode": mode, "queued": list(payload["queued_goals"])}
        return None

    monkeypatch.setattr(autonomy_module, "_TEST_FAILURE_INJECTOR", injector)

    queued_before = list(engine._goal_queue)
    plan_ids_before = list(engine._plans.keys())
    last_cycle_before = engine._last_cycle

    plans = engine.reflective_cycle(force=True)
    assert plans == []
    assert engine._goal_queue == queued_before
    assert list(engine._plans.keys()) == plan_ids_before
    assert engine._last_cycle == last_cycle_before
    assert ledger.read_bytes() == ledger_before

    first_log = caplog.records[0].message
    caplog.clear()
    engine.reflective_cycle(force=True)
    assert caplog.records[0].message == first_log
