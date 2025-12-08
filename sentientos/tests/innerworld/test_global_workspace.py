import copy

from sentientos.innerworld.global_workspace import GlobalWorkspace


def test_spotlight_rule_order_ethics_priority():
    workspace = GlobalWorkspace()
    qualia = {"errors": 0.2, "progress": 0.8}
    ethics = {"conflicts": [1, 2], "severity": "high"}
    reflection = {"trend_summary": {"volatility": "rising"}}
    identity = {"core_themes": {"qualia": "stable"}}
    meta_notes = [{"message": "note"} for _ in range(5)]

    spotlight = workspace.compute_spotlight(
        qualia=qualia,
        meta_notes=meta_notes,
        ethics=ethics,
        reflection=reflection,
        identity_summary=identity,
    )

    assert spotlight["focus"] == "ethics"
    assert spotlight["drivers"]["ethical_conflict"] is True


def test_spotlight_tension_and_identity_detection():
    workspace = GlobalWorkspace()
    qualia = {"errors": 1.0, "progress": 0.2, "novelty": 0.5}
    ethics = {"conflicts": []}
    reflection = {"trend_summary": {"volatility": "rising"}}
    identity = {"core_themes": {"qualia": "shifting"}}

    spotlight = workspace.compute_spotlight(
        qualia=qualia,
        meta_notes=[],
        ethics=ethics,
        reflection=reflection,
        identity_summary=identity,
    )

    assert spotlight["focus"] == "tension"
    assert spotlight["drivers"]["tension_rising"] is True

    identity_only = workspace.compute_spotlight(
        qualia={"progress": 1.0},
        meta_notes=[{}],
        ethics={"conflicts": []},
        reflection={},
        identity_summary=identity,
    )
    assert identity_only["focus"] == "identity"


def test_spotlight_empty_inputs_safe_defaults():
    workspace = GlobalWorkspace()
    empty_qualia = {}
    empty_meta = []
    empty_ethics = {}
    reflection = {}
    identity = {}

    inputs_snapshot = (
        copy.deepcopy(empty_qualia),
        copy.deepcopy(empty_meta),
        copy.deepcopy(empty_ethics),
        copy.deepcopy(reflection),
        copy.deepcopy(identity),
    )

    spotlight = workspace.compute_spotlight(
        qualia=empty_qualia,
        meta_notes=empty_meta,
        ethics=empty_ethics,
        reflection=reflection,
        identity_summary=identity,
    )

    assert spotlight["focus"] == "planning"
    assert inputs_snapshot == (
        empty_qualia,
        empty_meta,
        empty_ethics,
        reflection,
        identity,
    )


def test_spotlight_deterministic_outputs():
    workspace = GlobalWorkspace()
    data = {
        "qualia": {"errors": 0.5, "novelty": 0.2, "progress": 0.9},
        "meta_notes": [{"message": "note"}],
        "ethics": {"conflicts": ["x"], "severity": "moderate"},
        "reflection": {"trend_summary": {"volatility": "stable"}},
        "identity_summary": {"core_themes": {"qualia": "stable"}},
    }

    first = workspace.compute_spotlight(**data)
    second = workspace.compute_spotlight(**copy.deepcopy(data))

    assert first == second
