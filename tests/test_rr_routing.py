from node_registry import NodeRegistry, RoundRobinRouter


def test_capability_round_robin(tmp_path):
    registry = NodeRegistry(tmp_path / "nodes.json")
    registry.register_or_update(
        "core-a",
        "10.0.0.1",
        port=5000,
        capabilities={"llm": True, "stt": False},
        roles=["core"],
        trust_level="trusted",
    )
    registry.register_or_update(
        "core-b",
        "10.0.0.2",
        port=5001,
        capabilities={"llm": True, "stt": True},
        roles=["core"],
        trust_level="trusted",
    )

    router = RoundRobinRouter(registry)
    hosts = []
    for _ in range(4):
        node = router.next("llm")
        assert node is not None
        hosts.append(node.hostname)

    assert set(hosts) == {"core-a", "core-b"}
    assert hosts[0] != hosts[1]

    # Capability filtering should skip nodes without the requested feature.
    stt = router.next("stt")
    assert stt is not None and stt.hostname == "core-b"
