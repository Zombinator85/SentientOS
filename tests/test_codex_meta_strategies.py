from __future__ import annotations

from codex.meta_strategies import CodexMetaStrategy, PatternMiningEngine
from codex.strategy import StrategyAdjustmentEngine


def sample_arcs(success_status: str = "success") -> list[dict[str, object]]:
    return [
        {
            "goal": "embodiment anomaly",
            "steps": ["restart", "verify", "quarantine"],
            "operator_response": "review",
            "status": success_status,
            "anomaly_id": f"arc-{index}",
        }
        for index in range(3)
    ]


def varied_arcs() -> list[dict[str, object]]:
    base = sample_arcs()
    base.extend(
        [
            {
                "goal": "embodiment anomaly",
                "steps": ["restart", "verify", "quarantine"],
                "operator_response": "review",
                "status": "failure",
                "anomaly_id": "arc-failure",
            },
            {
                "goal": "network drift",
                "steps": ["diagnose", "restart"],
                "operator_response": "override",
                "status": "success",
                "anomaly_id": "arc-network-1",
            },
            {
                "goal": "network drift",
                "steps": ["diagnose", "restart"],
                "operator_response": "override",
                "status": "success",
                "anomaly_id": "arc-network-2",
            },
        ]
    )
    return base


def test_pattern_mining_detects_clusters(tmp_path) -> None:
    engine = PatternMiningEngine(tmp_path)
    arcs = varied_arcs()
    proposals = engine.analyze(arcs)
    assert proposals, "Expected at least one meta-strategy proposal"
    top = proposals[0]
    assert isinstance(top, CodexMetaStrategy)
    assert "embodiment" in top.pattern
    assert top.metadata["instances"] >= 3


def test_dashboard_proposals_surface_correctly(tmp_path) -> None:
    engine = PatternMiningEngine(tmp_path)
    engine.analyze(varied_arcs())
    panel = engine.dashboard_payload()
    assert panel, "Dashboard should include meta-strategy proposals"
    row = panel[0]
    assert row["status"] == "proposed"
    assert "step_order" in row["abstraction"]


def test_operator_approvals_create_reusable_templates(tmp_path) -> None:
    engine = PatternMiningEngine(tmp_path)
    proposals = engine.analyze(varied_arcs())
    chosen = proposals[0]
    stored = engine.approve(chosen.pattern, operator="Operator-A")
    assert stored.metadata["status"] == "approved"
    reloaded = engine.get(chosen.pattern)
    assert reloaded is not None
    assert reloaded.metadata["status"] == "approved"


def test_adaptive_thresholds_respond_to_operator_input(tmp_path) -> None:
    engine = PatternMiningEngine(tmp_path, confidence_threshold=0.75)
    proposals = engine.analyze(varied_arcs())
    pattern = proposals[0].pattern
    engine.approve(pattern)
    lowered = engine.confidence_threshold
    assert lowered < 0.75
    proposals = engine.analyze(
        [
            {
                "goal": "quarantine drift",
                "steps": ["halt", "notify"],
                "operator_response": "reject",
                "status": "success",
                "anomaly_id": "reject-1",
            },
            {
                "goal": "quarantine drift",
                "steps": ["halt", "notify"],
                "operator_response": "reject",
                "status": "success",
                "anomaly_id": "reject-2",
            },
        ]
    )
    engine.reject(proposals[0].pattern)
    assert engine.confidence_threshold > lowered


def test_strategy_adjustment_engine_meta_strategy_flow(tmp_path) -> None:
    mining_engine = PatternMiningEngine(tmp_path)
    proposals = mining_engine.analyze(varied_arcs())
    approved = mining_engine.approve(proposals[0].pattern)

    adjustment = StrategyAdjustmentEngine(root=tmp_path)
    dashboard = adjustment.meta_strategy_dashboard()
    assert dashboard, "Dashboard should surface stored meta-strategies"
    message = adjustment.apply_meta_strategy(approved.pattern, outcome="success", context={"anomaly": "demo"})
    assert "success rate" in message
