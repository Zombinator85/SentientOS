from sentientos.ethics import EthicsCriticDaemon


def test_ethics_critic_prefers_lowest_harm_strategy(tmp_path):
    daemon = EthicsCriticDaemon(gradient={"harm": 1.0, "safe": -0.2}, log_path=tmp_path / "critic.jsonl")
    report = daemon.evaluate(
        "safe path",
        "harm escalation",
        alternate_strategies={
            "mitigation": "safe patch with consent",
            "neutral": "plain patch",
        },
    )

    assert report["recommended_strategy"] == "mitigation"
    assert report["ethical_delta"] > 0
    log_content = (tmp_path / "critic.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert log_content
